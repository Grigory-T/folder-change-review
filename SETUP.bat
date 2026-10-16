@echo off
setlocal
cd /d "%~dp0"
rem Developer setup only. May download Python and locked dependencies.
uv sync --frozen --no-dev --python 3.13.14
exit /b %errorlevel%
