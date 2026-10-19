"""Windows acceptance of the complete portable folder or its extracted ZIP."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from runtime_safety import DATA_DIRECTORY, portable_directory
from state_store import StateHistory
import folder_change_review as app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--exe', type=Path)
    group.add_argument('--archive', type=Path)
    parser.add_argument('--results', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if os.name != 'nt': parser.error('Run this acceptance on Windows.')
    (root/'.build').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='portable-check-',dir=root/'.build') as temporary:
        base = Path(temporary); tool = base/'Tool with spaces-пример'; tool.mkdir()
        if args.archive:
            with zipfile.ZipFile(args.archive) as archive:
                names=archive.namelist()
                assert names and all(not Path(n).is_absolute() and '..' not in Path(n).parts and ':' not in n for n in names)
                archive.extractall(tool)
        else:
            exe=args.exe.resolve()
            shutil.copyfile(exe,tool/'folder-change-review.exe')
            shutil.copytree(exe.parent/'_internal',tool/'_internal')
        outside=base/'Unused profile temp cwd';outside.mkdir()
        env=os.environ.copy()
        for key in ('TEMP','TMP','TMPDIR','APPDATA','LOCALAPPDATA','PYTHONPYCACHEPREFIX'):env[key]=str(outside)
        def run(folder,*arguments,expected=0):
            process=subprocess.run([str(folder/'folder-change-review.exe'),*map(str,arguments)],env=env,cwd=outside,capture_output=True,timeout=60)
            assert process.returncode==expected,(process.returncode,process.stdout,process.stderr)
            assert not list(outside.iterdir()),'External storage was used.'
        project=tool/'Project';project.mkdir();file=project/'Document.pdf';file.write_bytes(b'before')
        with portable_directory(tool):
            history=StateHistory(tool)
            for mode in app.REVIEW_MODES:
                a=history.new_state_path();b=history.new_state_path()
                original=file.read_bytes();mtime=file.stat().st_mtime_ns
                run(tool,'snapshot','--root',project,'--output',a,'--mode',mode)
                file.write_bytes(original+b'changed');os.utime(file,ns=(mtime+10_000_000_000,mtime+10_000_000_000))
                run(tool,'snapshot','--root',project,'--output',b,'--mode',mode)
                run(tool,'compare','--before',a,'--after',b)
                assert app.compare_snapshots(app.load_snapshot(a),app.load_snapshot(b))[0]['Status']=='Changed'
            # The entire runtime and support data are omitted from a self scan.
            before=history.new_state_path();run(tool,'snapshot','--root',tool,'--output',before)
            loaded=app.load_snapshot(before)
            assert not any(row['parts'][0] in ('_internal',DATA_DIRECTORY) for row in loaded['files'])
            run(tool,'compare','--before',a,'--after',b,'--output',outside/'escaped.xlsx',expected=1)
            assert not (tool/'runtime').exists()
            assert not list((tool/DATA_DIRECTORY/'work').iterdir())
            # A prior root-level v0.9 state/settings remains available unchanged.
            legacy=tool/'states';legacy.mkdir();source=legacy/'older.fcrstate';shutil.copyfile(a,source)
            original=source.read_bytes();(tool/'settings.json').write_text('{"workers":32}')
            assert StateHistory(tool).settings()['workers']==32
            history.save_settings({'workers':16})
            assert source.read_bytes()==original and (history.states/source.name).read_bytes()==original
        copied=base/'Copied complete tool';shutil.copytree(tool,copied);shutil.rmtree(tool)
        run(copied,'compare','--before',copied/DATA_DIRECTORY/'states'/a.name,'--after',copied/DATA_DIRECTORY/'states'/b.name)
        assert not list(outside.iterdir())
        support=copied/DATA_DIRECTORY; saved=copied/'Saved data'
        support.rename(saved)
        subprocess.run(['cmd','/c','mklink','/J',str(support),str(outside)],check=True,capture_output=True)
        try:
            run(copied,'snapshot','--root',copied/'Project',expected=1)
        finally:
            support.rmdir();saved.rename(support)
        readonly=base/'Write denied';readonly.mkdir()
        shutil.copyfile(copied/'folder-change-review.exe',readonly/'folder-change-review.exe')
        shutil.copytree(copied/'_internal',readonly/'_internal')
        # Some build transports enable backup/restore privileges that bypass ACLs.
        # Drop those privileges in this acceptance process before testing denial.
        import ctypes
        from ctypes import wintypes
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        security=ctypes.WinDLL('advapi32',use_last_error=True)
        kernel.GetCurrentProcess.restype=wintypes.HANDLE
        security.OpenProcessToken.argtypes=(wintypes.HANDLE,wintypes.DWORD,ctypes.POINTER(wintypes.HANDLE))
        security.AdjustTokenPrivileges.argtypes=(wintypes.HANDLE,wintypes.BOOL,ctypes.c_void_p,wintypes.DWORD,ctypes.c_void_p,ctypes.c_void_p)
        kernel.CloseHandle.argtypes=(wintypes.HANDLE,)
        token=wintypes.HANDLE()
        assert security.OpenProcessToken(kernel.GetCurrentProcess(),0x20,ctypes.byref(token))
        try:
            assert security.AdjustTokenPrivileges(token,True,None,0,None,None)
        finally:
            kernel.CloseHandle(token)
        # SID syntax avoids localized account names and elevated-token differences.
        principal='*S-1-1-0'
        subprocess.run(['icacls',str(readonly),'/deny',principal+':(WD,AD)'],check=True,capture_output=True)
        try:
            try:
                (readonly/'Denied probe').mkdir()
            except PermissionError:
                pass
            else:
                raise AssertionError('The test token bypasses the write-denied ACL.')
            run(readonly,'snapshot','--root',copied/'Project',expected=1)
        finally:
            subprocess.run(['icacls',str(readonly),'/remove:d',principal],check=True,capture_output=True)
        result={'standard_onedir':True,'exe_sha256':hashlib.sha256((copied/'folder-change-review.exe').read_bytes()).hexdigest(),
                'all_modes':True,'external_profile_temp_cwd_canary_unchanged':True,'runtime_extraction':False,
                'self_scan_excludes_internal_and_data':True,'work_cleaned':True,'whole_folder_copy_and_offline_compare':True,
                'previous_root_history_import_preserves_originals':True,'outside_output_rejected':True,'data_junction_rejected':True,'unwritable_tool_fails_without_fallback':True,'ZIP_extraction_tested':bool(args.archive)}
    args.results.parent.mkdir(parents=True,exist_ok=True)
    args.results.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__': main()
