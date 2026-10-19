"""Verify bundled project code and relative Python code filenames."""
import argparse
import hashlib
import io
import json
import marshal
import ntpath
from pathlib import Path
import types
import zipfile

from PyInstaller.archive.readers import CArchiveReader


def normalize(code):
    return code.replace(co_filename='module.py', co_consts=tuple(normalize(value) if isinstance(value, types.CodeType) else value for value in code.co_consts))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('exe', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    archive = CArchiveReader(str(args.exe))
    pyz = archive.open_embedded_archive('PYZ.pyz')
    filenames = set()
    def inspect(code):
        assert not ntpath.isabs(code.co_filename), code.co_filename
        filenames.add(code.co_filename)
        for value in code.co_consts:
            if isinstance(value, types.CodeType):
                inspect(value)
    for name in ('folder_change_review', 'folder_change_review_ui', 'state_store', 'runtime_safety'):
        embedded = pyz.extract(name)
        expected = compile((root / (name + '.py')).read_bytes(), name + '.py', 'exec', optimize=0)
        assert marshal.dumps(normalize(embedded)) == marshal.dumps(normalize(expected)), name
    for name, entry in pyz.toc.items():
        if entry[0] in (0, 1):
            inspect(pyz.extract(name))
    for name, entry in archive.toc.items():
        if entry[-1] == 's':
            inspect(marshal.loads(archive.extract(name)))
    with zipfile.ZipFile(args.exe.parent/'_internal/base_library.zip') as standard:
        assert standard.namelist() == sorted(standard.namelist())
        for name in standard.namelist():
            if name.endswith('.pyc'):
                inspect(marshal.loads(standard.read(name)[16:]))
    assert 'tkinter' in pyz.toc and 'xlsxwriter' in pyz.toc
    assert not any(name.split('.')[0] in ('openpyxl', 'setuptools', 'pkg_resources', 'xml', 'pyexpat', '_elementtree') for name in pyz.toc)
    print(json.dumps({'source_bytecode_equal': True, 'relative_code_filenames': len(filenames), 'exe_bytes': args.exe.stat().st_size, 'sha256': hashlib.sha256(args.exe.read_bytes()).hexdigest()}, indent=2))


if __name__ == '__main__':
    main()
