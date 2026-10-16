@echo off
setlocal
cd /d "%~dp0"
uv venv .build-venv --python 3.13.14 --clear
if errorlevel 1 exit /b 1
uv pip install --python .build-venv\Scripts\python.exe --require-hashes -r windows_build\requirements-build.txt
if errorlevel 1 exit /b 1
uv export --frozen --no-dev --no-emit-project --output-file .build-runtime.txt
if errorlevel 1 exit /b 1
uv pip install --python .build-venv\Scripts\python.exe --require-hashes -r .build-runtime.txt
if errorlevel 1 exit /b 1
set PYTHONHASHSEED=0
set SOURCE_DATE_EPOCH=1767225600
".build-venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean windows_build\folder-change-review.spec
exit /b %errorlevel%
