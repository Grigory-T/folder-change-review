@echo off
setlocal
cd /d "%~dp0"
if not exist .build-venv\Scripts\python.exe (
  echo Run BUILD-EXE.bat first.
  exit /b 1
)
uv export --frozen --group test --no-emit-project --output-file .build-tests.txt
if errorlevel 1 exit /b 1
uv pip install --python .build-venv\Scripts\python.exe --require-hashes -r .build-tests.txt
if errorlevel 1 exit /b 1
set PYTHONHASHSEED=0
set SOURCE_DATE_EPOCH=1767225600
set FOLDER_CHANGE_REVIEW_BUILD_TESTS=1
.build-venv\Scripts\python.exe -m PyInstaller --noconfirm --clean windows_build\folder-change-review.spec
exit /b %errorlevel%
