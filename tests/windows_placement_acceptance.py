"""Native portable-folder acceptance using disposable fixtures only.

The optional SMB share must be a test destination. The harness creates and
removes only its own UUID subtree; production never launches subprocesses.
"""
import argparse
import contextlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import uuid
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import folder_change_review as app
from runtime_safety import extended, portable_directory
from state_store import StateHistory
from windows_build.verify import normalized_workbook


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--share', type=Path)
    args = parser.parse_args()
    args.exe = args.exe.resolve(); args.work.mkdir(parents=True, exist_ok=True)
    result = {}
    with tempfile.TemporaryDirectory(prefix='portable-', dir=args.work) as temporary:
        base = Path(temporary)
        outside = base/'Outside'; outside.mkdir()
        poison = os.environ.copy()
        for name in ('TEMP', 'TMP', 'LOCALAPPDATA', 'APPDATA'):
            poison[name] = str(outside)
        def run(exe, *arguments):
            return subprocess.run([str(exe), *map(str, arguments)], cwd=outside,
                                  env=poison, capture_output=True, timeout=120).returncode
        def exercise(tool, smb=False):
            tool.mkdir(parents=True)
            exe = tool/'folder-change-review.exe'; shutil.copyfile(args.exe, exe)
            document = tool/'Document.pdf'; document.write_bytes(b'before')
            unrelated = tool/'Documents/states'; unrelated.mkdir(parents=True)
            (unrelated/'Actual.pdf').write_bytes(b'actual')
            history = StateHistory(tool)
            a = history.new_state_path(); b = history.new_state_path()
            with portable_directory(tool):
                history.save_settings({'project': str(tool), 'workers': 32, 'review_mode': 'quick'})
                assert run(exe, 'snapshot', '--root', tool, '--output', a, '--workers', 32) == 0
                first = app.load_snapshot(a)
                assert first['file_count'] == 2 and first['statistics']['content_bytes_read'] == 0
                document.write_bytes(b'after longer')
                assert run(exe, 'snapshot', '--root', tool, '--output', b, '--workers', 16) == 0
                second = app.load_snapshot(b)
                assert {r['Status'] for r in app.compare_snapshots(first, second)} == {'Changed', 'Unchanged'}
                assert run(exe, 'compare', '--before', a, '--after', b) == 0
                report = tool/app.OUTPUT_FILE
                app.compare_files(a, b, tool/'source.xlsx')
                assert normalized_workbook(report) == normalized_workbook(tool/'source.xlsx')
                (tool/'source.xlsx').unlink()
                c = history.new_state_path()
                assert run(exe, 'snapshot', '--root', tool, '--output', c) == 0
                assert app.load_snapshot(c)['files'] == second['files']
                assert run(exe, 'compare', '--before', a, '--after', b, '--output', outside/'escaped.xlsx') == 1
                assert run(exe, 'snapshot', '--root', tool, '--output', outside/'escaped.fcrstate') == 1
                assert not list((tool/'work').iterdir())
                assert not list((tool/'runtime').iterdir())
                assert history.settings()['project'] == str(tool)
            shutil.copyfile(report, args.work/('SMB.xlsx' if smb else 'portable.xlsx'))
            return a.name, b.name
        original = base/'Tool with spaces'; names = exercise(original)
        result['in_project_support_paths_excluded'] = True
        result['unrelated_states_directory_preserved'] = True
        result['launch_cwd_and_profile_temp_ignored'] = not list(outside.iterdir())
        assert result['launch_cwd_and_profile_temp_ignored']
        copied = base/'Copied tool'; shutil.copytree(original, copied)
        shutil.rmtree(original)
        with portable_directory(copied):
            history = StateHistory(copied)
            assert len(history.list_states()[0]) == 3
            assert history.settings()['project'] == str(copied)
            # Remove the project documents; compare must use saved states only.
            (copied/'Document.pdf').unlink(); shutil.rmtree(copied/'Documents')
            assert run(copied/'folder-change-review.exe', 'compare', '--before', copied/'states'/names[0],
                       '--after', copied/'states'/names[1]) == 0
            assert not list((copied/'runtime').iterdir())
        result['copied_folder_keeps_history_settings_and_offline_compare'] = True
        # Long project and state paths under an ordinary executable location.
        long_root = copied/'Project'
        for i in range(5): long_root /= str(i)+'-'+'long-path-'*6
        Path(extended(long_root)).mkdir(parents=True)
        Path(extended(long_root/'File.pdf')).write_bytes(b'file')
        state = copied/'states'
        for i in range(5): state /= str(i)+'-'+'long-state-'*6
        Path(extended(state)).mkdir(parents=True)
        state /= 'long.fcrstate'
        assert run(copied/'folder-change-review.exe','snapshot','--root',long_root,'--output',state) == 0
        with portable_directory(copied): assert app.load_snapshot(state)['file_count'] == 1
        result['long_project_and_state_paths'] = True
        if args.share:
            remote = args.share/('portable-'+uuid.uuid4().hex)
            try:
                exercise(remote, smb=True)
                result['SMB_complete_portable_folder'] = True
            finally:
                if remote.exists(): shutil.rmtree(remote)
        assert not list(outside.iterdir())
    (args.work/'placement.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result))


if __name__ == '__main__': main()
