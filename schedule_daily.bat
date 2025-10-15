@echo off
setlocal
set ROOT=%~dp0
cd /d "%ROOT%"

if "%~1"=="" (
  echo Usage: schedule_daily.bat HH:MM [extra arguments]
  echo Example: schedule_daily.bat 07:30 --skip Wizard
  exit /b 1
)

set TIME=%~1
shift
set ARGS=%*

powershell -ExecutionPolicy Bypass -File "%ROOT%schedule_task.ps1" -Time "%TIME%" -Arguments "%ARGS%"
if errorlevel 1 (
  echo Failed to create daily schedule.
  exit /b 1
)

echo Scheduled daily run at %TIME%.
exit /b 0
