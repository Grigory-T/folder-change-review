@echo off
setlocal
cd /d "%~dp0"
if not exist .build-venv\Scripts\python.exe (
  echo Run BUILD-EXE.bat first.
  exit /b 1
)
.build-venv\Scripts\python.exe -I -m pip install --disable-pip-version-check --no-input --only-binary=:all: --require-hashes -r windows_build\requirements-test.txt
if errorlevel 1 exit /b 1
set PYTHONHASHSEED=0
set SOURCE_DATE_EPOCH=1767225600
set FOLDER_CHANGE_REVIEW_BUILD_TESTS=1
.build-venv\Scripts\python.exe -m PyInstaller --noconfirm --clean windows_build\folder-change-review.spec
exit /b %errorlevel%
