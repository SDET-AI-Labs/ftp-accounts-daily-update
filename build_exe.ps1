# Build a standalone EXE using PyInstaller
# Requirements: pip install pyinstaller
# Usage: run in PowerShell:  .\build_exe.ps1

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

# Ensure venv exists
if (-not (Test-Path '.\.venv\Scripts\python.exe')) {
    py -3 -m venv .venv 2>$null
    if ($LASTEXITCODE -ne 0) { python -m venv .venv }
}

. .\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller

# Build
$version = Get-Date -Format 'yyyyMMdd_HHmm'
pyinstaller --noconfirm `
  --clean `
  --name "ftp-accounts-report" `
  --onefile `
  --add-data "src\credentials.txt;src" `
  --collect-all "paramiko" `
  --hidden-import "pandas" `
  --hidden-import "openpyxl" `
  --console main.py

Write-Host "Build complete. EXE is in dist/ftp-accounts-report/"
