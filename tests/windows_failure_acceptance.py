"""Check real Windows sharing violations and atomic state preservation."""
import argparse
import ctypes
from ctypes import wintypes
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    args.work.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='fcr-failure-',dir=args.work) as temporary:
        base = Path(temporary)
        project = base/'project'; project.mkdir()
        document = project/'locked.docx'; document.write_bytes(b'document')
        output = base/'previous.fcrstate'
        command = [str(args.exe),'snapshot','--root',str(project),'--output',str(output),'--workers','32']
        subprocess.run(command,check=True,timeout=60)
        checksum = hashlib.sha256(output.read_bytes()).hexdigest()
        create = ctypes.windll.kernel32.CreateFileW
        create.argtypes = [wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
        create.restype = wintypes.HANDLE
        close = ctypes.windll.kernel32.CloseHandle
        close.argtypes = [wintypes.HANDLE]
        handle = create(str(document),0x80000000,0,None,3,0,None)
        assert handle != ctypes.c_void_p(-1).value
        try:
            assert subprocess.run(command,timeout=60).returncode == 1
        finally:
            close(handle)
        assert hashlib.sha256(output.read_bytes()).hexdigest() == checksum
        assert not list(base.glob('.folder-change-review-*'))
        subprocess.run(command,check=True,timeout=60)
    result = {'locked_file_aborts':True,'previous_state_preserved':True,'staging_cleaned':True,'retry_after_unlock_succeeds':True}
    (args.work/'failure-acceptance.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
