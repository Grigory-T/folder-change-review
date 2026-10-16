@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run SETUP.bat once before using the Python source version.
  exit /b 1
)
".venv\Scripts\python.exe" -B folder_change_review.py %*
exit /b %errorlevel%
