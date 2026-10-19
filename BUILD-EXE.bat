@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File windows_build\prepare-python.ps1
if errorlevel 1 exit /b 1
.build-python\python.exe -I -m venv --clear .build-venv
if errorlevel 1 exit /b 1
.build-venv\Scripts\python.exe -I -m pip install --disable-pip-version-check --no-input --only-binary=:all: --require-hashes -r windows_build\requirements-build.txt -r windows_build\requirements-runtime.txt
if errorlevel 1 exit /b 1
set PYTHONHASHSEED=0
set SOURCE_DATE_EPOCH=1767225600
set FOLDER_CHANGE_REVIEW_BUILD_TESTS=
.build-venv\Scripts\python.exe -m PyInstaller --noconfirm --clean windows_build\folder-change-review.spec
if errorlevel 1 exit /b 1
.build-venv\Scripts\python.exe -B windows_build\verify_portable.py --exe dist\folder-change-review\folder-change-review.exe --results .build\portable-acceptance.json
if errorlevel 1 exit /b 1
.build-venv\Scripts\python.exe -B windows_build\package_release.py --directory dist\folder-change-review
if errorlevel 1 exit /b 1
.build-venv\Scripts\python.exe -B windows_build\verify_portable.py --archive dist\folder-change-review-windows-x64.zip --results .build\zip-acceptance.json
exit /b %errorlevel%
