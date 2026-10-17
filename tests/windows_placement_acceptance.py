"""Native portable placement, long paths, SMB output and atomic-save checks.

Only new UUID fixtures are created/changed/deleted, including on the supplied
share. The application never launches these test harness subprocesses.
"""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import folder_change_review as app
from runtime_safety import extended, local_storage
from state_store import StateHistory
from windows_build.verify import normalized_workbook

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe',type=Path,required=True)
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--share',type=Path)
    args=parser.parse_args();args.work.mkdir(parents=True,exist_ok=True)
    result={'cases':[]}
    def run(exe,*arguments):
        return subprocess.run([extended(exe) if len(str(exe))>240 else str(exe),*map(str,arguments)],capture_output=True,timeout=180).returncode
    with tempfile.TemporaryDirectory(prefix='placement-',dir=args.work) as temporary:
        base=Path(temporary)
        for long in (False,True):
            root=base/('Long' if long else 'Project')
            if long:
                for i in range(5):root/=f'{i}-'+('long-path-'*7)
            Path(extended(root)).mkdir(parents=True)
            document=root/'Document-пример.pdf';Path(extended(document)).write_bytes(b'before')
            exe=root/'folder-change-review.exe';shutil.copyfile(args.exe,extended(exe))
            launcher=args.exe if long else exe
            history=StateHistory(root);before=history.new_state_path();after=history.new_state_path()
            assert run(launcher,'snapshot','--root','"'+str(root)+'"','--output',before,'--workers',32)==0
            a=app.load_snapshot(before);assert a['file_count']==1 and a['complete']
            Path(extended(document)).write_bytes(b'after longer')
            assert run(launcher,'snapshot','--root',root,'--output',after,'--workers',16)==0
            # No --output: report belongs beside the relocated executable, not cwd.
            assert run(launcher,'compare','--before',before,'--after',after,*(['--output',str(root/app.OUTPUT_FILE)] if long else []))==0
            report=root/app.OUTPUT_FILE;assert Path(extended(report)).is_file()
            source=base/('long-source.xlsx' if long else 'source.xlsx')
            app.compare_files(before,after,source)
            assert normalized_workbook(extended(report))==normalized_workbook(source)
            previous=Path(extended(report)).read_bytes()
            assert run(launcher,'compare','--before',before,'--after',after,*(['--output',str(root/app.OUTPUT_FILE)] if long else []))==0
            latest=history.new_state_path()
            assert run(launcher,'snapshot','--root',root,'--output',latest)==0
            assert app.load_snapshot(latest)['files']==app.load_snapshot(after)['files']
            assert not list(Path(extended(root)).glob('.folder-change-review-*'))
            shutil.copyfile(extended(report),args.work/('long-path.xlsx' if long else 'inside-project.xlsx'))
            result['cases'].append({'case':'long-path' if long else 'inside-project','path_over_260':len(str(report))>260,'files':1,'source_exe_workbook_equal':True,'report_and_history_excluded':True,'fixed_report_overwrite':True})
        # A directory junction gives output another spelling of the same folder.
        project=base/'AliasProject';project.mkdir();(project/'file.pdf').write_bytes(b'file')
        a=base/'alias-A.fcrstate';b=base/'alias-B.fcrstate'
        app.create_snapshot(project,a);app.create_snapshot(project,b)
        alias=base/'Alias';subprocess.run(['cmd','/c','mklink','/J',str(alias),str(project)],check=True,capture_output=True)
        assert run(args.exe,'compare','--before',a,'--after',b,'--output',alias/app.OUTPUT_FILE)==0
        assert (project/app.OUTPUT_FILE).is_file()
        with tempfile.TemporaryDirectory(prefix='offline-output-',dir=args.work) as out:
            # Compare must not need the original path at all.
            project.rename(base/'Gone')
            assert run(args.exe,'compare','--before',a,'--after',b,'--output',Path(out)/app.OUTPUT_FILE)==0
        result['junction_output_and_offline_compare']=True
        if args.share:
            root=args.share/('fcr-placement-'+uuid.uuid4().hex);root.mkdir()
            history=StateHistory(root)
            try:
                assert local_storage(history.states)
                exe=root/'folder-change-review.exe';shutil.copyfile(args.exe,exe)
                (root/'file.pdf').write_bytes(b'before')
                a=history.new_state_path();b=history.new_state_path()
                try:
                    code=run(exe,'snapshot','--root',root,'--output',a,'--workers',32)
                    result['SMB_executable_execute_permission']=True
                except PermissionError as error:
                    # A data share may intentionally omit FILE_EXECUTE. Keep
                    # testing SMB output without changing server permissions.
                    result['SMB_executable_execute_permission']=False
                    result['SMB_launch_os_error']=error.winerror
                    exe=args.exe
                    code=run(exe,'snapshot','--root',root,'--output',a,'--workers',32)
                assert code==0
                (root/'file.pdf').write_bytes(b'after larger')
                assert run(exe,'snapshot','--root',root,'--output',b,'--workers',16)==0
                assert run(exe,'compare','--before',a,'--after',b,'--output',root/app.OUTPUT_FILE)==0
                report=root/app.OUTPUT_FILE
                assert report.is_file()
                app.compare_files(a,b,base/'smb-source.xlsx')
                assert normalized_workbook(report)==normalized_workbook(base/'smb-source.xlsx')
                # Selected report and staging are the only SMB write exceptions.
                assert run(exe,'snapshot','--root',root,'--output',root/'rejected.fcrstate')==1
                assert not (root/'rejected.fcrstate').exists()
                assert run(exe,'compare','--before',a,'--after',b,'--output',root/app.OUTPUT_FILE)==0
                c=history.new_state_path()
                assert run(exe,'snapshot','--root',root,'--output',c)==0
                assert app.load_snapshot(c)['files']==app.load_snapshot(b)['files']
                shutil.copyfile(report,args.work/'SMB-report.xlsx')
                result['SMB_report_with_local_history']=True
                result['SMB_source_exe_workbook_equal']=True
                result['SMB_repeated_capture_excludes_report']=True
                result['SMB_state_output_rejected']=True
            finally:
                shutil.rmtree(root)
                if history.states.exists():shutil.rmtree(history.states.parent)
    (args.work/'placement.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result),flush=True)

if __name__=='__main__':main()
