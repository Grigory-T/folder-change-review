"""Synthetic source/frozen parity and SMB timing. Never inventories existing share data."""
import argparse
import contextlib
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import folder_change_review as app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--share', type=Path, help='Existing writable SMB share; a unique synthetic subfolder is created and removed')
    parser.add_argument('--files', type=int, default=5000)
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)
    root = (args.share or args.work) / ('fcr-synthetic-' + uuid.uuid4().hex)
    root.mkdir()
    results = {'dataset': 'synthetic', 'storage': 'SMB' if args.share else 'local', 'files': args.files, 'captures': []}
    try:
        block = hashlib.shake_256(b'folder-change-review synthetic dataset').digest(65536)
        paths = []
        for index in range(args.files):
            folder = root / f'Area-{index % 40:02d}' / f'Section-{index % 7:02d}'
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / (f'Document-{index:05d}.' + ('pdf', 'docx', 'xlsx', 'zip', 'rar', '7z')[index % 6])
            path.write_bytes(block + str(index).encode())
            paths.append(path)
        for name in ('~$lock.docx', 'Thumbs.db', 'scratch.tmp'):
            (root / name).write_bytes(b'ignored')
        (root / 'Empty').mkdir()
        output = args.work / 'source.fcrstate'
        started = time.perf_counter()
        with contextlib.redirect_stdout(io.StringIO()):
            source = app.create_snapshot(root, output, 16)
        results['captures'].append({'delivery': 'Python', 'workers': 16, 'seconds': round(time.perf_counter() - started, 3)})
        assert len(source['files']) == args.files and source['excluded_files'] == 3
        for workers, suffix in ((16, 'a'), (32, 'a'), (16, 'b'), (32, 'b')):
            output = args.work / f'exe-{workers}-{suffix}.fcrstate'
            started = time.perf_counter()
            subprocess.run([str(args.exe), 'snapshot', '--root', str(root), '--output', str(output), '--workers', str(workers)], check=True, timeout=600)
            frozen = app.load_snapshot(output)
            assert frozen['files'] == source['files']
            results['captures'].append({'delivery': 'EXE', 'workers': workers, 'seconds': round(time.perf_counter() - started, 3), 'scan_hash_seconds': round(frozen['statistics']['scan_hash_seconds'], 3)})
        results['bytes'] = source['statistics']['bytes']
        results['state_bytes'] = output.stat().st_size
        results['legacy_json_bytes'] = len(json.dumps(source, ensure_ascii=False).encode('utf-8'))
        # Same-length edit, delete, move and addition.
        paths[0].write_bytes(b'X' * paths[0].stat().st_size)
        paths[1].unlink()
        paths[2].rename(root / paths[2].name)
        (root / 'New document.pdf').write_bytes(b'new document')
        after = args.work / 'after.fcrstate'
        subprocess.run([str(args.exe), 'snapshot', '--root', str(root), '--output', str(after), '--workers', '32'], check=True, timeout=600)
        report = args.work / 'changes.xlsx'
        started = time.perf_counter()
        subprocess.run([str(args.exe), 'compare', '--before', str(output), '--after', str(after), '--output', str(report)], check=True, timeout=300)
        results['compare_export_seconds'] = round(time.perf_counter() - started, 3)
        counts = dict(__import__('collections').Counter(row['Status'] for row in app.compare_snapshots(source, app.load_snapshot(after))))
        assert counts == {'Added': 2, 'Deleted': 2, 'Changed': 1, 'Unchanged': args.files - 3}, counts
        results['counts'] = counts
        # Input project writes and network outputs must fail, not create files.
        invalid = root / 'must-not-exist.fcrstate'
        assert subprocess.run([str(args.exe), 'snapshot', '--root', str(root), '--output', str(invalid)], timeout=60).returncode == 1
        assert not invalid.exists()
        # Compare after source disappears: saved states are sufficient.
        shutil.rmtree(root)
        subprocess.run([str(args.exe), 'compare', '--before', str(output), '--after', str(after), '--output', str(args.work / 'offline.xlsx')], check=True, timeout=300)
        results.update({'source_exe_records_equal': True, 'compare_without_source': True, 'input_write_rejected': True})
        (args.work / 'acceptance.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
        print(json.dumps(results, indent=2), flush=True)
    finally:
        if root.exists():
            shutil.rmtree(root)


if __name__ == '__main__':
    main()
