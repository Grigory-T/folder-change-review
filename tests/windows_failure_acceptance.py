"""Real Windows file locks, ACL-denied folders and atomic output preservation.

Run without elevation so ACL cases exercise normal user permissions.
ACL changes apply only to newly created disposable fixtures. icacls is a test
harness dependency; the production application never launches subprocesses.
"""
import argparse
import ctypes
import csv
import io
from ctypes import wintypes
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import folder_change_review as app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    args.work.mkdir(parents=True,exist_ok=True)
    create = ctypes.windll.kernel32.CreateFileW
    create.argtypes = [wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
    create.restype = wintypes.HANDLE
    close = ctypes.windll.kernel32.CloseHandle
    close.argtypes = [wintypes.HANDLE]
    def lock(path):
        handle = create(str(path),0x80000000,0,None,3,0,None)
        assert handle != ctypes.c_void_p(-1).value
        return handle
    identity = subprocess.check_output(['whoami','/user','/fo','csv','/nh'],text=True)
    principal = '*'+next(row[1] for row in csv.reader(io.StringIO(identity)) if len(row)==2 and row[1].startswith('S-1-'))
    def acl(path, deny):
        command=['icacls',str(path),'/deny',principal+':(RD)'] if deny else ['icacls',str(path),'/remove:d',principal]
        subprocess.run(command,check=True,capture_output=True,timeout=30)
    result={}
    with tempfile.TemporaryDirectory(prefix='fcr-failure-',dir=args.work) as temporary:
        base=Path(temporary);project=base/'Project';project.mkdir()
        nested=project/'Restricted';nested.mkdir()
        document=nested/'report.docx';document.write_bytes(b'document')
        (project/'readable.pdf').write_bytes(b'readable')
        before=base/'A.fcrstate';after=base/'B.fcrstate'
        def capture(output=after,workers=32,mode='full'):
            return subprocess.run([str(args.exe),'snapshot','--root',str(project),'--output',str(output),'--workers',str(workers),'--mode',mode],timeout=60).returncode
        assert capture(before)==0
        checksum=hashlib.sha256(before.read_bytes()).hexdigest()
        for workers in (16,32):
            handle=lock(document)
            try:
                assert capture(workers=workers)==0
                state=app.load_snapshot(after)
                assert state['read_error_count']==1 and state['read_errors'][0]['winerror'] in (None,32)
                assert state['read_errors'][0]['errno']==13
                assert state['read_errors'][0]['kind']=='file'
                assert {row['Status'] for row in app.compare_snapshots(app.load_snapshot(before),state)}=={'Unknown','Unchanged'}
            finally:close(handle)
        result['exclusive_file_lock_partial_unknown_16_32']=True
        assert capture()==0 and app.load_snapshot(after)['complete']
        result['retry_after_unlock_complete']=True
        acl(nested,True)
        try:
            assert capture()==0
            state=app.load_snapshot(after)
            assert state['read_error_count']==1 and state['read_errors'][0]['winerror']==5, (state['file_count'],state['read_errors'])
            assert state['read_errors'][0]['kind']=='directory'
            assert {row['Status'] for row in app.compare_snapshots(app.load_snapshot(before),state)}=={'Unknown','Unchanged'}
            report=base/'Partial.xlsx'
            subprocess.run([str(args.exe),'compare','--before',str(before),'--after',str(after),'--output',str(report)],check=True,timeout=60)
            # Both source and frozen runtime honor the same denied folder.
            source=app.create_snapshot(project,base/'source.fcrstate',16,mode='full')
            assert source['files']==state['files'] and source['read_errors']==state['read_errors']
            app.compare_files(before,base/'source.fcrstate',base/'Partial-source.xlsx')
            from windows_build.verify import normalized_workbook
            assert normalized_workbook(report)==normalized_workbook(base/'Partial-source.xlsx')
        finally:acl(nested,False)
        result['acl_denied_subfolder_partial_unknown']=True
        assert capture()==0 and app.load_snapshot(after)['complete']
        result['retry_after_restoring_fixture_acl_complete']=True
        acl(project,True)
        try:
            assert capture(before)==1
        finally:acl(project,False)
        assert hashlib.sha256(before.read_bytes()).hexdigest()==checksum
        result['acl_denied_root_aborts_preserves_state']=True
        handle=lock(before)
        try:assert capture(before)==1
        finally:close(handle)
        assert hashlib.sha256(before.read_bytes()).hexdigest()==checksum
        result['locked_output_aborts_preserves_state']=True
        report=base/'Partial.xlsx'
        previous_report=hashlib.sha256(report.read_bytes()).hexdigest()
        handle=lock(report)
        compare=[str(args.exe),'compare','--before',str(before),'--after',str(after),'--output',str(report)]
        try:assert subprocess.run(compare,timeout=60).returncode==1
        finally:close(handle)
        assert hashlib.sha256(report.read_bytes()).hexdigest()==previous_report
        result['locked_report_aborts_preserves_previous']=True
        subprocess.run(compare,check=True,timeout=60)
        result['report_retry_after_unlock_succeeds']=True
        # Excluded Office/temp files never need to be opened.
        excluded=project/'~$office.docx';excluded.write_bytes(b'lock')
        handle=lock(excluded)
        try:assert capture()==0 and app.load_snapshot(after)['complete']
        finally:close(handle)
        result['excluded_locked_file_does_not_affect_capture']=True
        # Quick review intentionally does not open a content-locked file.
        quick_a,quick_b=base/'quick-A.fcrstate',base/'quick-B.fcrstate'
        assert capture(quick_a,mode='quick')==0
        handle=lock(document)
        try:
            assert capture(quick_b,mode='quick')==0
            state=app.load_snapshot(quick_b)
            assert state['complete'] and state['statistics']['content_bytes_read']==0
            assert {r['Status'] for r in app.compare_snapshots(app.load_snapshot(quick_a),state)}=={'Unchanged'}
        finally:close(handle)
        result['quick_content_lock_requires_no_content_access']=True
        acl(nested,True)
        try:
            assert capture(quick_b,mode='quick')==0
            state=app.load_snapshot(quick_b)
            assert state['read_error_count']==1
            assert {r['Status'] for r in app.compare_snapshots(app.load_snapshot(quick_a),state)}=={'Unknown','Unchanged'}
        finally:acl(nested,False)
        result['quick_denied_subtree_is_unknown']=True
        sample_a,sample_b=base/'sample-A.fcrstate',base/'sample-B.fcrstate'
        assert capture(sample_a,mode='sampled')==0
        handle=lock(document)
        try:
            assert capture(sample_b,mode='sampled')==0
            state=app.load_snapshot(sample_b)
            assert state['read_error_count']==1
            assert {r['Status'] for r in app.compare_snapshots(app.load_snapshot(sample_a),state)}=={'Unknown','Unchanged'}
        finally:close(handle)
        result['sampled_content_lock_is_unknown']=True
        assert not list(base.glob('.folder-change-review-*'))
        result['staging_cleaned']=True
        # Leave only generic aggregate results; fixture and paths are removed.
    (args.work/'failure-acceptance.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':main()
