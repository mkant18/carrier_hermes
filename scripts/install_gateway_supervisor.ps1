#Requires -Version 5.0
# install_gateway_supervisor.ps1
#
# PURPOSE: Installs a Windows Service via NSSM that supervises the Hermes
#          chief_of_staff gateway, auto-restarting it on crash and at boot.
#
# USAGE (run as Administrator for service install):
#   powershell -ExecutionPolicy Bypass -File install_gateway_supervisor.ps1
#
# If not run as admin, automatically falls back to a Scheduled Task
# (password-free, runs as the current interactive user).
#
# DOES NOT start the service -- the gateway is already running via VBS.
# Start it manually when ready to cut over.

param(
    [string]$ServiceName  = "HermesGateway",
    [string]$RunAsUser    = ".\micha",
    [switch]$UseSchedTask = $false,
    [switch]$StartNow     = $false
)

$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
$NssmExe     = "C:\Users\micha\AppData\Local\Microsoft\WinGet\Links\nssm.exe"
$PythonExe   = "C:\Users\micha\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe"
$PythonWExe  = "C:\Users\micha\AppData\Local\hermes\hermes-agent\venv\Scripts\pythonw.exe"
$GwArgs      = "-m hermes_cli.main --profile chief_of_staff gateway run"
$WorkDir     = "C:\Users\micha\AppData\Local\hermes\profiles\chief_of_staff"
$LogDir      = "C:\Users\micha\AppData\Local\hermes\profiles\chief_of_staff\logs"
$StdoutLog   = "$LogDir\nssm_stdout.log"
$StderrLog   = "$LogDir\nssm_stderr.log"
$WatchdogPy  = "C:\Users\micha\carrier_hermes\scripts\gateway_watchdog.py"

# Env vars for AppEnvironmentExtra (one KEY=VALUE per line)
$EnvExtra = "HERMES_HOME=C:\Users\micha\AppData\Local\hermes\profiles\chief_of_staff`nPYTHONIOENCODING=utf-8`nHERMES_GATEWAY_DETACHED=1`nVIRTUAL_ENV=C:\Users\micha\AppData\Local\hermes\hermes-agent\venv`nPYTHONPATH=C:\Users\micha\AppData\Local\hermes\hermes-agent"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
function Log {
    param([string]$Msg, [string]$Level = "INFO")
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Host "[$ts] [$Level] $Msg"
}

Log "=== HermesGateway Supervisor Install ==="
Log "Service name : $ServiceName"
Log "Python       : $PythonExe"
Log "Arguments    : $GwArgs"
Log "WorkDir      : $WorkDir"
Log "Logs         : $LogDir"

# ---------------------------------------------------------------------------
# Pre-flight
# ---------------------------------------------------------------------------
if (-not (Test-Path $NssmExe)) {
    Log "NSSM not found at $NssmExe" "ERROR"
    Log "Install via: winget install nssm" "ERROR"
    exit 1
}
if (-not (Test-Path $PythonExe)) {
    Log "Python not found at $PythonExe" "ERROR"
    exit 1
}
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
    Log "Created log dir: $LogDir"
}

# ---------------------------------------------------------------------------
# Elevation check
# ---------------------------------------------------------------------------
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Log "Not running as Administrator -- NSSM service install requires elevation." "WARN"
    Log "Falling back to Scheduled Task approach (password-free, runs as current user)." "WARN"
    $UseSchedTask = $true
}

# ---------------------------------------------------------------------------
# Install via NSSM Windows Service
# ---------------------------------------------------------------------------
function Install-NssmService {
    Log "--- Installing NSSM Windows Service: $ServiceName ---"

    $existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if ($existing) {
        Log "Service '$ServiceName' already exists -- removing cleanly..."
        if ($existing.Status -eq "Running") {
            Log "  Stopping service first..."
            Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 3
        }
        & $NssmExe remove $ServiceName confirm 2>&1 | Out-Null
        Start-Sleep -Seconds 2
        Log "  Old service removed."
    }

    Log "Running: nssm install $ServiceName ..."
    & $NssmExe install $ServiceName $PythonExe $GwArgs
    if ($LASTEXITCODE -ne 0) {
        Log "nssm install failed (exit $LASTEXITCODE)" "ERROR"
        return $false
    }

    Log "Configuring NSSM service settings..."

    & $NssmExe set $ServiceName AppDirectory   $WorkDir
    & $NssmExe set $ServiceName AppRestartDelay 5000
    & $NssmExe set $ServiceName AppThrottle     5000
    & $NssmExe set $ServiceName AppExit         Default Restart
    & $NssmExe set $ServiceName AppEnvironmentExtra $EnvExtra
    & $NssmExe set $ServiceName AppStdout       $StdoutLog
    & $NssmExe set $ServiceName AppStderr       $StderrLog
    & $NssmExe set $ServiceName AppStdoutCreationDisposition 2
    & $NssmExe set $ServiceName AppStderrCreationDisposition 2
    & $NssmExe set $ServiceName AppRotateFiles  1
    & $NssmExe set $ServiceName AppRotateBytes  10485760
    & $NssmExe set $ServiceName AppRotateOnline 1
    & $NssmExe set $ServiceName Start           SERVICE_DELAYED_AUTO_START
    & $NssmExe set $ServiceName DisplayName     "Hermes Gateway (chief_of_staff)"
    & $NssmExe set $ServiceName Description     "Hermes Discord+Telegram gateway. Supervised by NSSM with auto-restart on crash."

    # Run as the local user (needs password to access OAuth tokens in user profile)
    $userPassword = $null
    try {
        $securePw = Read-Host -AsSecureString "Enter password for $RunAsUser (or press Enter to use LocalSystem)"
        $bstr  = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePw)
        $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
        if ($plain -ne "") { $userPassword = $plain }
    } catch {
        Log "Could not prompt for password (non-interactive) -- using LocalSystem." "WARN"
    }

    if ($userPassword) {
        Log "Setting service to run as $RunAsUser"
        & $NssmExe set $ServiceName ObjectName $RunAsUser $userPassword
    } else {
        Log "No password provided -- service will run as LocalSystem." "WARN"
        Log "OAuth tokens may not be accessible. Consider running as $RunAsUser." "WARN"
    }

    Log "NSSM service configured successfully." "OK"

    if ($StartNow) {
        Log "Starting service (--StartNow specified)..."
        Start-Service -Name $ServiceName
        Start-Sleep -Seconds 5
        $status = (Get-Service -Name $ServiceName).Status
        Log "Service status: $status"
    } else {
        Log "Service NOT started (existing gateway is still running under VBS)."
        Log "When ready to cut over, run: Start-Service -Name $ServiceName"
    }

    return $true
}

# ---------------------------------------------------------------------------
# Install via Scheduled Task (password-free fallback)
# ---------------------------------------------------------------------------
function Install-SchedTaskFallback {
    $TaskName = "HermesGateway"
    Log "--- Installing Scheduled Task: $TaskName ---"
    Log "Scheduled tasks run as the current user -- no password needed."

    $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($existing) {
        Log "Removing existing task: $TaskName"
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    }

    # Choose entry point: watchdog (preferred) or gateway directly
    if (Test-Path $WatchdogPy) {
        $Executable = $PythonWExe
        $ScriptArg  = $WatchdogPy
        Log "Action: launch gateway_watchdog.py (manages gateway lifecycle)"
    } else {
        $Executable = $PythonExe
        $ScriptArg  = "-m hermes_cli.main --profile chief_of_staff gateway run"
        Log "Action: launch gateway directly (watchdog not found)"
    }

    $Action = New-ScheduledTaskAction `
        -Execute  $Executable `
        -Argument $ScriptArg `
        -WorkingDirectory $WorkDir

    $LogonTrigger = New-ScheduledTaskTrigger -AtLogOn

    $Settings = New-ScheduledTaskSettingsSet `
        -ExecutionTimeLimit  (New-TimeSpan -Days 365) `
        -MultipleInstances   IgnoreNew `
        -StartWhenAvailable `
        -RestartCount        3 `
        -RestartInterval     (New-TimeSpan -Minutes 1) `
        -RunOnlyIfNetworkAvailable:$false

    $Principal = New-ScheduledTaskPrincipal `
        -UserId    ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
        -LogonType Interactive `
        -RunLevel  Highest

    Register-ScheduledTask `
        -TaskName   $TaskName `
        -Action     $Action `
        -Trigger    $LogonTrigger `
        -Settings   $Settings `
        -Principal  $Principal `
        -Description "Hermes gateway supervisor. Launches the gateway watchdog at logon with restart-on-failure." `
        -Force | Out-Null

    Log "Scheduled Task '$TaskName' installed." "OK"

    if ($StartNow) {
        Log "Starting task now..."
        Start-ScheduledTask -TaskName $TaskName
        Start-Sleep -Seconds 5
        $info = Get-ScheduledTaskInfo -TaskName $TaskName
        Log "Last result: $($info.LastTaskResult), Last run: $($info.LastRunTime)"
    }

    return $true
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
$success = $false

if (-not $UseSchedTask) {
    try {
        $success = Install-NssmService
    } catch {
        Log "NSSM service install failed: $_" "ERROR"
        Log "Falling back to Scheduled Task approach..." "WARN"
        $success = Install-SchedTaskFallback
    }
} else {
    $success = Install-SchedTaskFallback
}

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "======================================================"
if ($success) {
    Write-Host "  OK  HermesGateway supervisor INSTALLED SUCCESSFULLY"
} else {
    Write-Host "  !! Installation encountered errors -- see output above"
}
Write-Host ""
Write-Host "  Gateway exe  : $PythonExe"
Write-Host "  Gateway args : $GwArgs"
Write-Host "  Working dir  : $WorkDir"
Write-Host "  NSSM stdout  : $StdoutLog"
Write-Host "  NSSM stderr  : $StderrLog"
Write-Host ""
Write-Host "  NOTE: Service/task is NOT started (existing gateway still running)."
Write-Host "  Cut over when ready:"
Write-Host "    hermes -p chief_of_staff gateway stop"
Write-Host "    Start-Service -Name HermesGateway    (NSSM path)"
Write-Host "    -- or --"
Write-Host "    Start-ScheduledTask -TaskName HermesGateway  (task path)"
Write-Host "======================================================"

exit $(if ($success) { 0 } else { 1 })
