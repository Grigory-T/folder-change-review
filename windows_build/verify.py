"""Compare source and production EXE states, reports and failure behavior on Windows."""
import argparse
from collections import Counter
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import folder_change_review as app


def normalized_workbook(path):
    # Preserve every worksheet, cell, type, style, layout and ZIP member.
    # Only workbook creation/modification timestamps vary between launches.
    result = {}
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None
        for name in archive.namelist():
            data = archive.read(name)
            if name == 'docProps/core.xml':
                tree = ET.fromstring(data)
                for element in tree:
                    if element.tag.rsplit('}', 1)[-1] in ('created', 'modified'):
                        element.text = 'VOLATILE'
                data = ET.tostring(tree)
            result[name] = data
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', type=Path, required=True)
    parser.add_argument('--results', type=Path, required=True)
    parser.add_argument('--previous-exe', type=Path, help='Optional previous release for old-state compatibility')
    args = parser.parse_args()
    args.results.mkdir(parents=True, exist_ok=True)
    cases = [
        ('empty', {}, {}, {}),
        ('single', {'one.pdf': b'one'}, {'one.pdf': b'one'}, {'Unchanged': 1}),
        ('all-statuses-move', {'stable.pdf': b'same','changed.docx': b'before','deleted.pdf': b'delete','move.pdf': b'move'},
         {'stable.pdf': b'same','changed.docx': b'AFTER!','added.pdf': b'add','New/move.pdf': b'move'},
         {'Added':2,'Deleted':2,'Changed':1,'Unchanged':1}),
        ('nested-lca', {'Top/Finance/a.pdf':b'a','Top/Legal/b.pdf':b'b'},
         {'Top/Finance/a.pdf':b'a','Top/Plans/c.pdf':b'c'}, {'Added':1,'Deleted':1,'Unchanged':1}),
        ('literal-unicode', {'=1+1.txt':b'a','00123.txt':b'b','пример-😀.pdf':b'c','literal_x000D_.txt':b'd'},
         {'=1+1.txt':b'a','00123.txt':b'B','пример-😀.pdf':b'c','literal_x000D_.txt':b'd'}, {'Changed':1,'Unchanged':3}),
        ('extensionless-dotfile', {'README':b'a','.gitignore':b'b','Report.TAR.GZ':b'c'},
         {'README':b'a','.gitignore':b'b','Report.TAR.GZ':b'C'}, {'Changed':1,'Unchanged':2}),
        ('opaque-archives', {'bundle.zip':b'not a zip','bundle.rar':b'not a rar','bundle.7z':b'not a 7z'},
         {'bundle.zip':b'changed archive','bundle.rar':b'not a rar','bundle.7z':b'not a 7z'}, {'Changed':1,'Unchanged':2}),
        ('excluded-and-empty', {'~$lock.docx':b'a','Thumbs.db':b'b','scratch.tmp':b'c','scratch.TEMP':b'd'},
         {'~$lock.docx':b'A','Thumbs.db':b'B','scratch.tmp':b'C','scratch.TEMP':b'D'}, {}),
        ('all-added', {}, {'one.pdf':b'','two.docx':b'two'}, {'Added':2}),
        ('all-deleted', {'one.pdf':b'','two.docx':b'two'}, {}, {'Deleted':2}),
        ('buffer-boundaries', {'zero.pdf':b'','one.pdf':b'x','exact.pdf':b'a'*app.HASH_BUFFER_SIZE,
                               'over.pdf':b'a'*(app.HASH_BUFFER_SIZE*2+17)},
         {'zero.pdf':b'','one.pdf':b'x','exact.pdf':b'a'*app.HASH_BUFFER_SIZE,
          'over.pdf':b'a'*(app.HASH_BUFFER_SIZE*2+16)+b'b'}, {'Changed':1,'Unchanged':3}),
        ('timestamp-only', {'same.pdf':b'content'}, {'same.pdf':b'content'}, {'Unchanged':1}),
    ]
    previous_compatible = False
    comparisons = []
    with tempfile.TemporaryDirectory(prefix='fcr-parity-',dir=args.results) as temporary:
        base = Path(temporary)
        for index, (name, old_files, new_files, expected) in enumerate(cases):
            work = base / name; work.mkdir()
            project = work/'project'; project.mkdir()
            snapshots = {}
            workers = 16 if index % 2 == 0 else 32
            for label, files in (('A',old_files),('B',new_files)):
                # Remove only this fixture's files and directories.
                import shutil
                for child in project.iterdir():
                    shutil.rmtree(child) if child.is_dir() else child.unlink()
                (project/'Empty').mkdir()
                for relative, data in files.items():
                    path = project/relative
                    path.parent.mkdir(parents=True,exist_ok=True)
                    path.write_bytes(data)
                    if label == 'B' and name == 'timestamp-only':
                        os.utime(path,(1_700_000_000,1_700_000_000))
                source = work/f'source-{label}.fcrstate'
                frozen = work/f'exe-{label}.fcrstate'
                with contextlib.redirect_stdout(io.StringIO()):
                    snapshot = app.create_snapshot(project,source,workers, mode="full")
                subprocess.run([str(args.exe),'snapshot','--root',str(project),'--output',str(frozen),'--workers',str(workers),'--mode','full'],check=True,timeout=60)
                assert snapshot['files'] == app.load_snapshot(frozen)['files'], name
                snapshots[label] = source, frozen
            source_report = work/'source.xlsx'; frozen_report = work/'exe.xlsx'
            with contextlib.redirect_stdout(io.StringIO()):
                counts = app.compare_files(snapshots['A'][0],snapshots['B'][0],source_report)
            assert counts == Counter(expected), (name,counts,expected)
            subprocess.run([str(args.exe),'compare','--before',str(snapshots['A'][1]),'--after',str(snapshots['B'][1]),'--output',str(frozen_report)],check=True,timeout=60)
            assert normalized_workbook(source_report) == normalized_workbook(frozen_report), name
            # Keep representative workbooks for native Excel acceptance.
            if name in ('empty','single','all-statuses-move','literal-unicode','nested-lca'):
                shutil.copy2(frozen_report,args.results/(name+'.xlsx'))
            comparisons.append({'case':name,'workers':workers,'rows':sum(counts.values()),'all_workbook_members_equal':True})
        # Exercise the shipped CLI defaults and each capture mode, preserving
        # stable-file timestamps instead of rewriting the entire fixture tree.
        for mode in app.REVIEW_MODES:
            project = base/('mode-'+mode); project.mkdir()
            for name,data in [('stable.pdf',b'stable'),('changed.docx',b'before'),('deleted.pdf',b'delete'),('move.pdf',b'move')]:
                (project/name).write_bytes(data)
            snapshots = {}
            for label in ('A','B'):
                if label == 'B':
                    changed = project/'changed.docx'; old_time = changed.stat().st_mtime_ns
                    changed.write_bytes(b'AFTER!'); os.utime(changed,ns=(old_time+10_000_000_000,old_time+10_000_000_000))
                    (project/'deleted.pdf').unlink(); (project/'New').mkdir()
                    (project/'move.pdf').rename(project/'New/move.pdf')
                    (project/'added.pdf').write_bytes(b'added')
                source = base/f'{mode}-source-{label}.fcrstate'
                frozen = base/f'{mode}-exe-{label}.fcrstate'
                with contextlib.redirect_stdout(io.StringIO()):
                    snapshot = app.create_snapshot(project,source,32,mode=mode)
                flags = [] if mode == 'quick' else ['--mode',mode]
                subprocess.run([str(args.exe),'snapshot','--root',str(project),'--output',str(frozen),'--workers','32',*flags],check=True,timeout=60)
                actual = app.load_snapshot(frozen)
                assert snapshot['files'] == actual['files']
                assert actual['review_mode'] == mode
                if mode == 'quick':
                    assert actual['statistics']['content_bytes_read'] == 0
                    assert all(row['sha256'] is None for row in actual['files'])
                snapshots[label] = source,frozen
            source_report=base/(mode+'-source.xlsx'); frozen_report=args.results/(mode+'-report.xlsx')
            with contextlib.redirect_stdout(io.StringIO()):
                counts=app.compare_files(snapshots['A'][0],snapshots['B'][0],source_report)
            assert counts == {'Added':2,'Deleted':2,'Changed':1,'Unchanged':1}, (mode,counts)
            subprocess.run([str(args.exe),'compare','--before',str(snapshots['A'][1]),'--after',str(snapshots['B'][1]),'--output',str(frozen_report)],check=True,timeout=60)
            assert normalized_workbook(source_report) == normalized_workbook(frozen_report)
            comparisons.append({'case':'mode-'+mode,'workers':32,'rows':6,'all_workbook_members_equal':True})
        # Different modes must fail without replacing the previous report.
        preserved=base/'mode-preserved.xlsx';preserved.write_bytes(b'previous report')
        command=['compare','--before',str(base/'quick-exe-A.fcrstate'),'--after',str(base/'full-exe-B.fcrstate'),'--output',str(preserved)]
        assert subprocess.run([str(args.exe),*command],timeout=60).returncode == 1
        assert preserved.read_bytes() == b'previous report'
        # Previous production release states remain readable without rehashing.
        if args.previous_exe:
            project = base/'compatibility'; project.mkdir()
            (project/'sample.pdf').write_bytes(b'previous release content')
            previous = base/'previous.fcrstate'; current = base/'current.fcrstate'
            subprocess.run([str(args.previous_exe),'snapshot','--root',str(project),'--output',str(previous)],check=True,timeout=60)
            subprocess.run([str(args.exe),'snapshot','--root',str(project),'--output',str(current),'--mode','full'],check=True,timeout=60)
            assert [{k: v for k, v in row.items() if k != 'mtime_ns'} for row in app.load_snapshot(previous)['files']] == [{k: v for k, v in row.items() if k != 'mtime_ns'} for row in app.load_snapshot(current)['files']]
            source_report = base/'compat-source.xlsx'; frozen_report = base/'compat-exe.xlsx'
            with contextlib.redirect_stdout(io.StringIO()):
                counts = app.compare_files(previous,current,source_report)
            assert counts == {'Unchanged':1}
            subprocess.run([str(args.exe),'compare','--before',str(previous),'--after',str(current),'--output',str(frozen_report)],check=True,timeout=60)
            assert normalized_workbook(source_report) == normalized_workbook(frozen_report)
            rejected = base/'old-runtime-must-not-export.xlsx'
            previous_compatible = app.load_snapshot(previous)['version'] == app.load_snapshot(current)['version']
            code = subprocess.run([str(args.previous_exe),'compare','--before',str(current),'--after',str(current),'--output',str(rejected)],timeout=60).returncode
            assert code == (0 if previous_compatible else 1)
            assert rejected.exists() == previous_compatible
            comparisons.append({'case':'previous-release-state','rows':1,'all_workbook_members_equal':True})
        sentinel = base/'preserved.xlsx'; sentinel.write_bytes(b'previous output')
        broken = base/'broken.fcrstate'; broken.write_bytes(b'not a state')
        failures = [
            ['snapshot','--root',str(base/'missing'),'--output',str(base/'absent.fcrstate')],
            ['compare','--before',str(broken),'--after',str(broken),'--output',str(project/'inside.xlsx')],
            ['snapshot','--root',str(project),'--output',str(base/'invalid.fcrstate'),'--workers','0'],
            ['snapshot','--root',str(project),'--output',str(base/'invalid.fcrstate'),'--workers','33'],
            ['compare','--before',str(broken),'--after',str(broken),'--output',str(sentinel)],
            ['compare','--before',str(base/'missing.fcrstate'),'--after',str(broken),'--output',str(sentinel)],
            ['compare','--before',str(broken),'--after',str(broken),'--output',str(base/'invalid.csv')],
        ]
        for command in failures:
            with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
                assert app.main(command) == 1, command[0]
            assert subprocess.run([str(args.exe),*command],timeout=60).returncode == 1, command[0]
        assert sentinel.read_bytes() == b'previous output'
        assert not (project/'inside.fcrstate').exists()
        assert not list(base.rglob('.folder-change-review-*'))
    result = {'comparisons':comparisons,'matching_failure_cases':len(failures),'only_workbook_timestamps_normalized':True,
              'older_runtime_rejects_current_state_format': bool(args.previous_exe) and not previous_compatible,
              'previous_runtime_reads_current_state_format': previous_compatible}
    (args.results/'parity.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
