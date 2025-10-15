@echo off
setlocal ENABLEDELAYEDEXPANSION

REM Change to the folder where this script lives
set "ROOT=%~dp0"
cd /d "%ROOT%"

REM Create virtual environment if missing
if not exist ".venv\Scripts\python.exe" (
  echo [setup] Creating virtual environment .venv
  py -3 -m venv .venv 2>nul || python -m venv .venv
  if errorlevel 1 (
    echo [error] Failed to create virtual environment. Ensure Python 3 is installed and on PATH.
    exit /b 1
  )
  echo [setup] Upgrading pip
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  if errorlevel 1 (
    echo [error] Failed to upgrade pip.
    exit /b 1
  )
  echo [setup] Installing requirements
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo [error] Failed to install requirements.
    exit /b 1
  )
)

REM Run the report; pass any extra arguments through
set "ARGS=%*"
echo [run] python main.py %ARGS%
".venv\Scripts\python.exe" ".\main.py" %ARGS%
set EXITCODE=%ERRORLEVEL%

if %EXITCODE% neq 0 (
  echo [error] Script exited with code %EXITCODE%.
  exit /b %EXITCODE%
)

echo [done] Report finished. Check the 'result' and 'logs' folders.
exit /b 0
