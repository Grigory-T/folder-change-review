# Licenses and provenance

Application code is [MIT licensed](LICENSE), preserving Folder Review attribution.
Third-party components retain their own licenses; the application license does
not replace them. Full notices in [licenses](licenses) are embedded in the EXE.
Required upstream author names in notices are legal attribution, not project/user
data. CPython is bundled without source-code modifications.

| Component | Role | License / notice | Upstream source |
|---|---|---|---|
| CPython 3.13.16 | Interpreter and standard library | PSF/Python historical terms and incorporated-code notices | [CPython tag](https://github.com/python/cpython/tree/v3.13.16) |
| python-build-standalone 20261013 | Prebuilt Windows Python distribution | Underlying components' individual terms | [Exact release](https://github.com/astral-sh/python-build-standalone/releases/tag/20261013) |
| XlsxWriter 3.2.9 | Sole runtime Python package, XLSX writer | BSD-2-Clause | [Source](https://github.com/jmcnamara/XlsxWriter/tree/RELEASE_3.2.9) |
| PyInstaller 6.22.3 | Bootloader and runtime hooks; build tool | GPL-2.0-or-later WITH Bootloader-exception; applicable runtime-hook notices retained | [Source and exception](https://github.com/pyinstaller/pyinstaller/blob/v6.22.3/COPYING.txt) |
| Tcl/Tk | Native GUI runtime/data | Tcl/Tk permissive terms | [Tcl](https://www.tcl-lang.org/software/tcltk/) |
| OpenSSL | SHA-256 native implementation and Python SSL library | Apache-2.0 | [Source](https://github.com/openssl/openssl) |
| libffi | ctypes support | MIT | [Source](https://github.com/libffi/libffi) |
| zlib | ZIP/deflate support | Zlib | [Source](https://github.com/madler/zlib) |
| liblzma 5.2.5 | Python compression support | Public domain (library); see retained package notice | [Source](https://github.com/tukaani-project/xz) |
| bzip2 | Python compression support | bzip2 license | [Source](https://sourceware.org/bzip2/) |
| Expat | Development/test XML parser; excluded from production | MIT | [Source](https://github.com/libexpat/libexpat) |
| mpdecimal | Python decimal support | BSD-2-Clause | [Source](https://www.bytereef.org/mpdecimal/) |
| HACL* / mimalloc | Code incorporated into CPython | MIT notices | [HACL*](https://github.com/hacl-star/hacl-star), [mimalloc](https://github.com/microsoft/mimalloc) |
| Microsoft Visual C runtime | Windows runtime DLLs | Microsoft redistribution conditions | [CPython redistribution notice](https://github.com/python/cpython/blob/v3.13.16/PC/crtlicense.txt) |

PyInstaller's bootloader exception permits this application's MIT distribution;
its full license/exception is retained. The portable bootloader modification
in `windows_build/portable_bootloader.c` is GPL-2.0-or-later WITH the same
Bootloader-exception. The complete patched corresponding source is published
as `pyinstaller-6.22.3-portable-source.tar.gz` with the release. The build uses
MSVC's static runtime and upstream bundled zlib 1.3.2 (separate retained notice); their notices remain included. Microsoft redistribution conditions apply
only to the Microsoft code; keep its notices and use it on supported Microsoft
platforms. See the full notices rather than interpreting the table as replacing
their terms.

The component inventory identifies exact embedded DLL hashes. CPython distribution
provenance and upstream build recipes provide native dependency versions; some
bundled standard-library support is unused by the application. SQLite and the unused Expat/XML parser are not bundled in production. Network-capable standard-library modules are not an update/telemetry
client; normal runtime network API calls are blocked.

Build-only wheels (hash-pinned in `requirements-build.txt`) include altgraph
(MIT), packaging (Apache-2.0 OR BSD-2-Clause), pefile (MIT),
pyinstaller-hooks-contrib (GPL-2.0-or-later and Apache-2.0 portions), pywin32-ctypes
(BSD-3-Clause), setuptools (MIT) and PyInstaller. Their build environment is not
shipped. Test-only openpyxl and et-xmlfile are MIT licensed and absent from the
production EXE. pip is part of the verified Python preparation environment and
is not bundled in production. Source setup may use uv (MIT OR Apache-2.0), also
not bundled.

Notice provenance is recorded in `licenses/SOURCES.json`, including exact source
URLs, source-archive member names and SHA-256 of each retained notice.
