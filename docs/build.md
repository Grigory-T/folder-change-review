# Auditing and reproducing the Windows release

Build on Windows x86-64 with PowerShell and `tar.exe` (included in current Windows
10/11). No administrator rights, global Python installation or uv installation
are needed for the production build.
The unmodified upstream PyInstaller bootloader is used: no C compiler or custom
bootloader build is required. Windows 11 x86-64 is the validated target.
Build-time internet access is separate from the offline application runtime.

1. Obtain the source at the release tag, for example:

   ```powershell
   git clone https://github.com/Grigory-T/folder-change-review.git
   cd folder-change-review
   git checkout v0.10.0
   .\BUILD-EXE.bat
   ```

2. `windows_build/python-distribution.json` identifies the exact CPython 3.13.16
   Windows x86-64 archive, build 20261013, upstream URL and SHA-256. The preparation
   script checks the hash before extracting a fresh `.build-python`. A mismatched
   cached archive aborts. Python is not installed globally. The archive includes
   its interpreter, Tcl/Tk and native dependencies from python-build-standalone.
3. A fresh `.build-venv` installs only hash-locked wheels from
   `requirements-build.txt` and `requirements-runtime.txt`. PyInstaller 6.22.3
   packages a standard onedir application with the stock wheel bootloader.
   The EXE and `_internal` stay together; there is no runtime extraction.
   Packaging uses fixed `PYTHONHASHSEED=0`, `SOURCE_DATE_EPOCH=1767225600`, sorted
   standard-library ZIP members, preserved checkout bytes via `.gitattributes`,
   no UPX and no signing step. The spec and entry
   point are in the repository; third-party notices are bundled in the portable folder.
4. Verify the output against `SHA256SUMS`/`components.json` from the release:

   ```powershell
   Get-FileHash .\dist\folder-change-review\folder-change-review.exe -Algorithm SHA256
   .\.build-venv\Scripts\python.exe windows_build\inspect_exe.py dist\folder-change-review\folder-change-review.exe
   .\.build-venv\Scripts\python.exe windows_build\audit_artifact.py dist\folder-change-review\folder-change-review.exe --output local-components.json
   ```

   The inspector checks application bytecode against source and rejects absolute
   code filenames and production test-reader dependencies. The inventory includes
   hashes for every archive payload, Python module, standard-library member,
   build input and bootloader input. Every DLL/PYD must match the pinned Python
   distribution exactly. Inventories contain relative names, never build paths.

`BUILD-EXE.bat` must pass `verify_portable.py` against both the candidate folder
and the extracted ZIP. It tests all modes, relocated folders, legacy history,
external-storage sentinels, supporting-data junctions and unwritable storage.
`package_release.py` uses an explicit allow-list: EXE, exact `_internal` file set,
manifest and neutral documents. States, settings, reports and unrelated nested
build copies are never package members. ZIP timestamps and ordering are fixed.

For an independent path check, check out the same tag in a second empty directory
and run `BUILD-EXE.bat` there. Compare every runtime file and both EXE and ZIP SHA-256 values. The component
inventory records the complete relative runtime file/hash set. Do not reuse a
venv or an extracted interpreter. The published finalization receipt records the
actual separate-directory rebuild. This reproduces application packaging from
prebuilt hash-pinned upstream binaries; it does not claim to recompile CPython,
Tcl/Tk, OpenSSL, Microsoft runtimes or the upstream bootloader from source.
Their licenses and PyInstaller bootloader exception remain in force; the
combined application remains MIT licensed. Their upstream
source/provenance links are listed in the notices and inventory.

For offline rebuilding after preparation, preserve the verified Python archive
at `.build\python-build.tar.gz` and download the locked wheels to a wheel folder.
Set `PIP_NO_INDEX=1` and `PIP_FIND_LINKS` to that folder before building. The build
still checks all hashes. It fails rather than bypassing unavailable inputs.

# Development verification

`BUILD-TEST-EXE.bat` adds separately pinned test-reader wheels to the build venv and
creates `dist\folder-change-review-tests` with its EXE and `_internal`. This binary is development-only:

```powershell
.\BUILD-TEST-EXE.bat
.\dist\folder-change-review-tests\folder-change-review-tests.exe --results frozen-suite.json
.\.build-venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

The frozen runner rejects skips as well as failures. Re-run `BUILD-EXE.bat` before
building production again; it recreates the venv and clears the test-build flag.
Source development on Linux may use uv and `uv.lock`; use Xvfb for Tk tests.
`RUN.bat` never installs or downloads anything. Setup and build scripts are not
runtime components.

The published `security-audit.json` records package-advisory and local antivirus
results at their check time. Those are observations, not permanent guarantees.
Do not upload private states or reports to scanning services.
