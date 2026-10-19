"""Package only the verified EXE/runtime and neutral release documents."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
import zipfile

NAME = 'folder-change-review'
DOCUMENTS = ('LICENSE', 'USAGE.txt', 'THIRD-PARTY-NOTICES.md')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory(directory):
    directory = Path(directory)
    runtime = directory/'_internal'
    if not runtime.is_dir() or runtime.is_symlink():
        raise ValueError('The complete _internal runtime is required.')
    files = {}
    for path in sorted(runtime.rglob('*')):
        if path.is_symlink() or getattr(path.lstat(), 'st_file_attributes', 0) & 0x400:
            raise ValueError('The runtime must not contain links or junctions.')
        if path.is_file():
            files[path.relative_to(directory).as_posix()] = sha(path)
    if not files:
        raise ValueError('The portable runtime is empty.')
    return files


def package(directory, target, acceptance):
    directory, target = Path(directory), Path(target)
    exe = directory/(NAME+'.exe')
    manifest = json.loads((directory/'build-manifest.json').read_text())
    if manifest['executable_sha256'] != sha(exe) or manifest['runtime_file_sha256'] != inventory(directory):
        raise ValueError('The EXE or exact runtime file set differs from the manifest.')
    if not acceptance.get('standard_onedir') or acceptance.get('exe_sha256') != sha(exe):
        raise ValueError('This exact executable must pass portable-folder acceptance before packaging.')
    members = [NAME+'.exe', *manifest['runtime_file_sha256'], *DOCUMENTS, 'build-manifest.json']
    descriptor, staging = tempfile.mkstemp(prefix='portable-package-', suffix='.zip', dir=target.parent)
    os.close(descriptor)
    try:
        with zipfile.ZipFile(staging, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name in sorted(members):
                path = directory/name
                info = zipfile.ZipInfo(name, (1980,1,1,0,0,0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, path.read_bytes(), compresslevel=9)
        os.replace(staging, target)
    finally:
        if Path(staging).exists(): Path(staging).unlink()
    return {'zip':target.name, 'bytes':target.stat().st_size, 'sha256':sha(target), 'files':len(members)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--acceptance', type=Path, default=Path('.build/portable-acceptance.json'))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    import shutil
    for name in DOCUMENTS:
        source = root/'windows_build/USAGE.txt' if name == 'USAGE.txt' else root/name
        shutil.copyfile(source, args.directory/name)
    manifest = {'schema':1, 'application':NAME, 'executable_sha256':sha(args.directory/(NAME+'.exe')),
                'runtime_file_sha256':inventory(args.directory)}
    (args.directory/'build-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    target = args.directory.parent/(NAME+'-windows-x64.zip')
    result = package(args.directory,target,json.loads(args.acceptance.read_text()))
    print(json.dumps(result))


if __name__ == '__main__': main()
