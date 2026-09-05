@echo off
setlocal
cd /d "%~dp0"
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
if not errorlevel 1 (
  py -3 -m sentinel serve
  pause
  exit /b
)
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
if errorlevel 1 (
  echo Python 3.11+ is required. See docs/INSTALL.md or docs/INSTALL.cs.md.
  pause
  exit /b 1
)
python -m sentinel serve
pause
