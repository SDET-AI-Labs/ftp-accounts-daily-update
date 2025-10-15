param(
    [Parameter(Mandatory=$false)] [string]$Time = "08:00",
    [Parameter(Mandatory=$false)] [string]$TaskName = "FTP Accounts Daily Update",
    [Parameter(Mandatory=$false)] [string]$Arguments = "",
    [switch]$Weekly
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

# Normalize time to TimeSpan
try {
    $parts = $Time.Split(':')
    if ($parts.Count -lt 2) { throw "Time must be in HH:MM format" }
    $hours = [int]$parts[0]
    $minutes = [int]$parts[1]
    $at = New-TimeSpan -Hours $hours -Minutes $minutes
}
catch {
    Write-Error "Invalid -Time '$Time'. Use HH:MM (24h). Example: -Time '09:15'"
    exit 1
}

# Build the action; call the runner .bat which handles venv and deps
$runner = Join-Path $root 'run_report.bat'
if (-not (Test-Path $runner)) {
    Write-Error "Runner not found at $runner"
    exit 1
}

# Use cmd.exe /c so .bat runs reliably; the .bat itself cd's to its own dir
$action = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument "/c `"$runner`" $Arguments"

# Daily or Weekly trigger
if ($Weekly) {
    $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At $at
} else {
    $trigger = New-ScheduledTaskTrigger -Daily -At $at
}

$desc = "Runs the FTP Accounts Daily Update report. Args: $Arguments"

# Create or update the task
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false | Out-Null
}

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Description $desc | Out-Null

Write-Host "Scheduled task '$TaskName' created. It will run at $Time."