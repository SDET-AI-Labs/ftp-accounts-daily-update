param(
    [Parameter(Mandatory=$true)] [string]$ExePath,
    [Parameter(Mandatory=$false)] [string]$Time = "08:00",
    [Parameter(Mandatory=$false)] [string]$TaskName = "FTP Accounts Daily Update (EXE)",
    [Alias('Args')][Parameter(Mandatory=$false)] [string]$Arguments = "",
    [ValidateSet("Daily","Weekdays","Weekend","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday")]
    [Parameter(Mandatory=$false)] [string]$Days = "Daily",
    [switch]$Weekly
)

$ErrorActionPreference = 'Stop'
if (-not (Test-Path $ExePath)) {
    Write-Error "EXE not found at $ExePath"
    exit 1
}

# Normalize time
try {
    $parts = $Time.Split(':')
    if ($parts.Count -lt 2) { throw "Time must be in HH:MM format" }
    $hours = [int]$parts[0]
    $minutes = [int]$parts[1]
    # New-ScheduledTaskTrigger -At expects a DateTime (date portion is ignored for Daily/Weekly)
    $at = [datetime]::Today.Date.AddHours($hours).AddMinutes($minutes)
}
catch {
    Write-Error "Invalid -Time '$Time'. Use HH:MM (24h). Example: -Time '09:15'"
    exit 1
}

$exeDir = Split-Path -Parent $ExePath
$action = New-ScheduledTaskAction -Execute $ExePath -Argument $Arguments -WorkingDirectory $exeDir

# Determine trigger based on -Days (or legacy -Weekly switch)
if ($Weekly -and -not $PSBoundParameters.ContainsKey('Days')) {
    # Backward compatibility: -Weekly implies weekdays
    $Days = 'Weekdays'
}

switch ($Days) {
    'Daily'    { $trigger = New-ScheduledTaskTrigger -Daily -At $at }
    'Weekdays' { $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At $at }
    'Weekend'  { $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek @('Saturday','Sunday') -At $at }
    default    { $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $Days -At $at }
}

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false | Out-Null
}

try {
    # Register under current user with interactive logon and limited privilege (no password prompt)
    $userId = if ($env:USERDOMAIN) { "$($env:USERDOMAIN)\$($env:USERNAME)" } else { $env:USERNAME }
    $principal = New-ScheduledTaskPrincipal -UserId $userId -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Description "Runs the FTP report (EXE)." | Out-Null
}
catch {
    Write-Error "Failed to register scheduled task. $_"
    exit 1
}

$argText = if ([string]::IsNullOrWhiteSpace($Arguments)) { $null } else { $Arguments }
$msg = if ($null -ne $argText) {
    [string]::Format("Scheduled task '{0}' created for {1} ({2}): {3} {4}", $TaskName, $Time, $Days, $ExePath, $argText)
} else {
    [string]::Format("Scheduled task '{0}' created for {1} ({2}): {3}", $TaskName, $Time, $Days, $ExePath)
}
Write-Host $msg