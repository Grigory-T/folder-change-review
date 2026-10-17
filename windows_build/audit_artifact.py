"""Inventory a Windows release without executing it. Requires build dependencies.

Native payloads must match the checksum-verified Python distribution. The
manifest contains only relative names, hashes and versions, never build paths.
"""
import argparse
import hashlib
import importlib.metadata
import io
import json
import marshal
from pathlib import Path
import platform
import sys
import zipfile

import pefile
from PyInstaller.archive.readers import CArchiveReader


def sha(data):
    return hashlib.sha256(data).hexdigest()


def imports(data):
    image = pefile.PE(data=data, fast_load=True)
    image.parse_data_directories(directories=[
        pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_IMPORT'],
        pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT']])
    names = sorted({entry.dll.decode('ascii') for attribute in (
        'DIRECTORY_ENTRY_IMPORT', 'DIRECTORY_ENTRY_DELAY_IMPORT')
        for entry in getattr(image, attribute, [])})
    image.close()
    return names


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('exe', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    python = root/'.build-python'
    archive = CArchiveReader(str(args.exe))
    pyz = archive.open_embedded_archive('PYZ.pyz')
    known = {sha(p.read_bytes()): p.relative_to(python).as_posix()
             for p in python.rglob('*') if p.is_file() and p.suffix.lower() in ('.dll', '.pyd')}
    payloads = []
    for name, entry in sorted(archive.toc.items()):
        data = archive.extract(name)
        item = {'path': name.replace('\\', '/'), 'type': entry[-1],
                'bytes': len(data), 'sha256': sha(data)}
        if name.lower().endswith(('.dll', '.pyd')):
            if item['sha256'] not in known:
                raise ValueError('Unknown native payload: '+name)
            item['origin'] = 'python-distribution:'+known[item['sha256']]
            item['imports'] = imports(data)
        payloads.append(item)
    modules = []
    for name, entry in sorted(pyz.toc.items()):
        data = pyz.extract(name)
        encoded = marshal.dumps(data) if entry[0] in (0, 1) else data
        modules.append({'name': name, 'sha256': sha(encoded)})
    with zipfile.ZipFile(io.BytesIO(archive.extract('base_library.zip'))) as library:
        standard = [{'path': n, 'sha256': sha(library.read(n))} for n in sorted(library.namelist())]
    inputs = ['.gitattributes', 'BUILD-EXE.bat', 'windows_build/prepare-python.ps1',
              'windows_build/python-distribution.json', 'windows_build/requirements-build.txt',
              'windows_build/requirements-runtime.txt', 'windows_build/folder-change-review.spec',
              'windows_build/entry.py', 'windows_build/audit_artifact.py',
              'windows_build/inspect_exe.py', 'LICENSE', 'folder_change_review.py',
              'folder_change_review_ui.py', 'runtime_safety.py', 'state_store.py']
    inputs += [p.relative_to(root).as_posix() for p in sorted((root/'licenses').glob('*.txt'))]
    pyinstaller = Path(importlib.metadata.distribution('pyinstaller').locate_file('PyInstaller'))
    bootloader = pyinstaller/'bootloader'/'Windows-64bit-intel'/'runw.exe'
    receipt = {'schema': 1, 'application': 'folder-change-review',
               'artifact': {'name': args.exe.name, 'bytes': args.exe.stat().st_size,
                            'sha256': sha(args.exe.read_bytes()), 'authenticode_signed': False,
                            'imports': imports(args.exe.read_bytes())},
               'build': {'python': platform.python_version(), 'architecture': 'x86-64',
                         'python_distribution': json.loads((root/'windows_build/python-distribution.json').read_text()),
                         'PYTHONHASHSEED': '0', 'SOURCE_DATE_EPOCH': '1767225600',
                         'tools': {name: importlib.metadata.version(name) for name in (
                             'pip', 'pyinstaller', 'pyinstaller-hooks-contrib', 'altgraph',
                             'packaging', 'pefile', 'pywin32-ctypes', 'setuptools', 'xlsxwriter')},
                         'bootloader_input_sha256': sha(bootloader.read_bytes())},
               'source_inputs': {n: sha((root/n).read_bytes()) for n in sorted(inputs)},
               'payloads': payloads, 'python_modules': modules, 'standard_library': standard,
               'all_native_payloads_match_pinned_python': True}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'payloads': len(payloads), 'python_modules': len(modules),
                      'native_origin_verified': True, 'exe_sha256': receipt['artifact']['sha256']}))


if __name__ == '__main__':
    main()
