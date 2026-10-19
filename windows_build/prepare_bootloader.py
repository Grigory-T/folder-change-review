"""Build a portable Windows bootloader from verified upstream source and a public patch."""
import gzip
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import urllib.request

root = Path(__file__).resolve().parents[1]
pin = json.loads((root/'windows_build/bootloader-pin.json').read_text())
cache = root/'.build'; cache.mkdir(exist_ok=True)
archive = cache/pin['filename']
if not archive.exists():
    with urllib.request.urlopen(pin['url']) as response: archive.write_bytes(response.read())
if hashlib.sha256(archive.read_bytes()).hexdigest() != pin['sha256']:
    raise ValueError('Bootloader source checksum mismatch.')
source = cache/('pyinstaller-'+pin['version'])
if source.exists(): shutil.rmtree(source)
with tarfile.open(archive) as package: package.extractall(cache, filter='data')
for name, expected in pin['patched_files'].items():
    if hashlib.sha256((source/name).read_bytes()).hexdigest() != expected:
        raise ValueError('Unexpected upstream bootloader source: '+name)
path = source/'bootloader/src/pyi_utils_win32.c'
text = path.read_text()
marker = 'int\npyi_create_temporary_application_directory(struct PYI_CONTEXT *pyi_ctx)\n{'
assert text.count(marker) == 1
text = text.replace(marker, (root/'windows_build/portable_bootloader.c').read_text() + '\n' + marker)
marker = '    /* If user specified the temporary directory via runtime_tmpdir'
assert text.count(marker) == 1
text = text.replace(marker, '''    if (pyi_ctx->runtime_tmpdir && strcmp(pyi_ctx->runtime_tmpdir, "@executable") == 0) {
        return _pyi_create_portable_application_directory(pyi_ctx);
    }

''' + marker)
path.write_text(text, newline='\n')
path = source/'bootloader/wscript'
text = path.read_text();marker = "ctx.env.append_value('LINKFLAGS', '/SUBSYSTEM:CONSOLE')"
assert text.count(marker) == 1
text = text.replace(marker, marker + "\n            ctx.env.append_value('LINKFLAGS', '/Brepro')")
path.write_text(text,newline='\n')
# Publish the complete corresponding patched source, with reproducible metadata.
source_asset = cache/('pyinstaller-'+pin['version']+'-portable-source.tar.gz')
with source_asset.open('wb') as raw, gzip.GzipFile(fileobj=raw, mode='wb', filename='', mtime=0) as compressed:
    with tarfile.open(fileobj=compressed, mode='w') as package:
        for member in sorted(source.rglob('*')):
            info = package.gettarinfo(str(member), arcname=source.name+'/'+member.relative_to(source).as_posix())
            info.uid = info.gid = 0; info.uname = info.gname = ''; info.mtime = 1767225600
            if info.isfile():
                with member.open('rb') as data: package.addfile(info, data)
            else: package.addfile(info)
# MSVC selection is pinned; no compiler is downloaded or silently substituted.
env = os.environ.copy(); env.pop('CL', None); env['CFLAGS'] = '/Brepro'
subprocess.run([sys.executable,'waf','configure','--msvc_version=msvc 17.14','--msvc_targets=x64','--static-zlib','build_release','install_release','build_releasew','install_releasew'],cwd=source/'bootloader',env=env,check=True)
# Confirm the compiler and SDK actually selected by Waf, rather than trusting
# the machine's default developer environment. Keep paths out of public receipts.
config = (source/'bootloader/build/config.log').read_text(errors='replace')
if ('MSVC\\'+pin['MSVC_toolset']+'\\') not in config or ('Kits\\10\\include\\'+pin['Windows_SDK']) not in config:
    raise ValueError('The build selected an unpinned MSVC toolset or Windows SDK.')
installed = Path(importlib.metadata.distribution('pyinstaller').locate_file('PyInstaller/bootloader/Windows-64bit-intel'))
produced = source/'PyInstaller/bootloader/Windows-64bit-intel'
for name in ('run.exe','runw.exe'): shutil.copyfile(produced/name,installed/name)
receipt = {'source':pin, 'corresponding_source_sha256':hashlib.sha256(source_asset.read_bytes()).hexdigest(), 'portable_patch_sha256':hashlib.sha256((root/'windows_build/portable_bootloader.c').read_bytes()).hexdigest(),
           'bootloaders':{name:hashlib.sha256((installed/name).read_bytes()).hexdigest() for name in ('run.exe','runw.exe')}}
(cache/'bootloader-build.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt['bootloaders']))
