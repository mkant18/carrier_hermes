# install_gateway_watchdog.ps1 — Install Windows Scheduled Task for gateway watchdog
#
# PURPOSE: Registers a Windows Scheduled Task (HermesGatewayWatchdog) that:
#   - Runs carrier_gateway_watchdog.py every 5 minutes
#   - Also runs on system startup (after 2 minutes)
#   - Runs as the CURRENT USER (no admin rights required)
#   - Uses the Hermes venv Python interpreter
#
# USAGE:
#   powershell -ExecutionPolicy Bypass -File install_gateway_watchdog.ps1
#
# UNINSTALL:
#   Unregister-ScheduledTask -TaskName "HermesGatewayWatchdog" -Confirm:$false

$ErrorActionPreference = "Stop"

$TaskName      = "HermesGatewayWatchdog"
$HermesHome    = "$env:LOCALAPPDATA\hermes"
$HermesPython  = "$HermesHome\hermes-agent\venv\Scripts\python.exe"
$WatchdogScript = "$env:LOCALAPPDATA\hermes\scripts\carrier_gateway_watchdog.py"
$LogDir        = "$HermesHome\carrier\logs"
$LogFile       = "$LogDir\gateway_watchdog.log"

# --- Verify Python and watchdog script exist --------------------------------
if (-not (Test-Path $HermesPython)) {
    Write-Error "Hermes venv Python not found: $HermesPython"
    Write-Host "Check that Hermes is installed correctly."
    exit 1
}

if (-not (Test-Path $WatchdogScript)) {
    Write-Error "Watchdog script not found: $WatchdogScript"
    Write-Host "Run this after copying carrier_gateway_watchdog.py to $env:LOCALAPPDATA\hermes\scripts\"
    exit 1
}

Write-Host "Installing scheduled task: $TaskName"
Write-Host "  Python:   $HermesPython"
Write-Host "  Script:   $WatchdogScript"
Write-Host "  Log dir:  $LogDir"

# --- Ensure log directory exists --------------------------------------------
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
    Write-Host "Created log directory: $LogDir"
}

# --- Build the action (what to run) -----------------------------------------
# Wrapper: run watchdog, log stdout/stderr, exit code to log
$WrapperCmd = @"
`$out = & '$HermesPython' '$WatchdogScript' 2>&1
`$ts = (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
Add-Content -Path '$LogFile' -Value "[\$ts] [TASK] `$out" -Encoding UTF8
"@

$Action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NonInteractive -WindowStyle Hidden -Command `"$WrapperCmd`""

# --- Build triggers ---------------------------------------------------------
# Trigger 1: Every 5 minutes (repetition on a daily trigger)
$DailyTrigger = New-ScheduledTaskTrigger -Daily -At "00:00"
$Repetition = (New-ScheduledTaskTrigger -RepetitionInterval (New-TimeSpan -Minutes 5) -Once -At "00:00").Repetition
$DailyTrigger.Repetition = $Repetition

# Trigger 2: At startup (with 2-minute delay to let system settle)
$StartupTrigger = New-ScheduledTaskTrigger -AtStartup
$StartupTrigger.Delay = "PT2M"

# --- Settings ---------------------------------------------------------------
$Settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 3) `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable:$false `
    -WakeToRun:$false

# --- Principal (current user, no admin needed) ------------------------------
$Principal = New-ScheduledTaskPrincipal `
    -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
    -LogonType Interactive `
    -RunLevel Highest

# --- Register the task ------------------------------------------------------
# Remove existing task if present
$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Removing existing task: $TaskName"
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger @($DailyTrigger, $StartupTrigger) `
    -Settings $Settings `
    -Principal $Principal `
    -Description "Hermes Gateway self-healing watchdog. Monitors chief_of_staff gateway for HERMES_DELEGATED_CHILD_CONTEXT poisoning and stale dispatcher locks. Auto-restarts on failure." `
    -Force | Out-Null

Write-Host ""
Write-Host "=== INSTALLED: $TaskName ==="
Write-Host "  Schedule:  Every 5 minutes + on startup (2-min delay)"
Write-Host "  Log:       $LogFile"
Write-Host ""
Write-Host "Run now to test:"
Write-Host "  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host ""
Write-Host "Check last run:"
Write-Host "  Get-ScheduledTaskInfo -TaskName '$TaskName' | Select LastRunTime, LastTaskResult"
