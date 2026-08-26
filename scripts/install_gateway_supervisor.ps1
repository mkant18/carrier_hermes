# install_gateway_supervisor.ps1 — Install HermesGateway NSSM service supervisor
#
# PURPOSE: Installs a Windows Service via NSSM that supervises the Hermes
# chief_of_staff gateway process, auto-restarting it on crash and at boot.
#
# USAGE (run as Administrator for service install):
#   powershell -ExecutionPolicy Bypass -File install_gateway_supervisor.ps1
#
# NOTE: Windows Services run as SYSTEM by default. Since the gateway needs
# user-level OAuth tokens, this script first tries to configure the service
# to run as .\micha. If that requires a password and we're non-interactive,
# it falls back to a Scheduled Task approach (restart-on-failure, password-free).
#
# DOES NOT start the service — the gateway is already running. Start manually
# when ready to cut over.

param(
    [string]$ServiceName  = "HermesGateway",
    [string]$RunAsUser    = ".\micha",
    [switch]$UseSchedTask = $false,   # Force the scheduled-task fallback
    [switch]$StartNow     = $false    # Start the service/task immediately
)

$ErrorActionPreference = "Stop"

# ─────────────────────────────────────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────────────────────────────────────
$NssmExe      = "C:\Users\micha\AppData\Local\Microsoft\WinGet\Links\nssm.exe"
$PythonExe    = "C:\Users\micha\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe"
$GwArgs       = "-m hermes_cli.main --profile chief_of_staff gateway run"
$WorkDir      = "C:\Users\micha\AppData\Local\hermes\profiles\chief_of_staff"
$LogDir       = "C:\Users\micha\AppData\Local\hermes\profiles\chief_of_staff\logs"
$StdoutLog    = "$LogDir\nssm_stdout.log"
$StderrLog    = "$LogDir\nssm_stderr.log"

# Env vars the gateway needs (AppEnvironmentExtra format: KEY=VALUE one per line)
$EnvExtra = @(
    "HERMES_HOME=C:\Users\micha\AppData\Local\hermes\profiles\chief_of_staff",
    "PYTHONIOENCODING=utf-8",
    "HERMES_GATEWAY_DETACHED=1",
    "VIRTUAL_ENV=C:\Users\micha\AppData\Local\hermes\hermes-agent\venv",
    "PYTHONPATH=C:\Users\micha\AppData\Local\hermes\hermes-agent"
) -join "`n"

# ─────────────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────────────
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

# ─────────────────────────────────────────────────────────────────────────────
# Pre-flight checks
# ─────────────────────────────────────────────────────────────────────────────
if (-not (Test-Path $NssmExe)) {
    Log "NSSM not found at $NssmExe" "ERROR"
    Log "Install via: winget install nssm" "ERROR"
    exit 1
}
if (-not (Test-Path $PythonExe)) {
    Log "Python not found at $PythonExe" "ERROR"
    exit 1
}

# Ensure log directory exists
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
    Log "Created log dir: $LogDir"
}

# ─────────────────────────────────────────────────────────────────────────────
# Check if we're running as Administrator (needed for NSSM service install)
# ─────────────────────────────────────────────────────────────────────────────
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Log "Not running as Administrator. NSSM service install requires elevation." "WARN"
    Log "Falling back to Scheduled Task approach (password-free, runs as current user)." "WARN"
    $UseSchedTask = $true
}

# ─────────────────────────────────────────────────────────────────────────────
# Helper: Install via NSSM Windows Service
# ─────────────────────────────────────────────────────────────────────────────
function Install-NssmService {
    Log "─── Installing NSSM Windows Service: $ServiceName ───"

    # Remove existing service cleanly
    $existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if ($existing) {
        Log "Service '$ServiceName' already exists — removing cleanly..."
        if ($existing.Status -eq "Running") {
            Log "  Stopping service first..."
            Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 3
        }
        & $NssmExe remove $ServiceName confirm 2>&1 | Out-Null
        Start-Sleep -Seconds 2
        Log "  Old service removed."
    }

    # Install the service
    Log "Running: nssm install $ServiceName ..."
    & $NssmExe install $ServiceName $PythonExe $GwArgs
    if ($LASTEXITCODE -ne 0) {
        Log "nssm install failed (exit $LASTEXITCODE)" "ERROR"
        return $false
    }

    # Configure all settings
    Log "Configuring NSSM service settings..."

    # Application directory
    & $NssmExe set $ServiceName AppDirectory $WorkDir

    # Restart on crash: 5000ms delay, unlimited retries
    & $NssmExe set $ServiceName AppRestartDelay 5000
    & $NssmExe set $ServiceName AppThrottle 5000
    & $NssmExe set $ServiceName AppExit Default Restart

    # Environment variables
    & $NssmExe set $ServiceName AppEnvironmentExtra $EnvExtra

    # Stdout / stderr logging
    & $NssmExe set $ServiceName AppStdout $StdoutLog
    & $NssmExe set $ServiceName AppStderr $StderrLog

    # Log rotation: 10MB max
    & $NssmExe set $ServiceName AppStdoutCreationDisposition 2   # Append
    & $NssmExe set $ServiceName AppStderrCreationDisposition 2   # Append
    & $NssmExe set $ServiceName AppRotateFiles 1
    & $NssmExe set $ServiceName AppRotateBytes 10485760           # 10MB
    & $NssmExe set $ServiceName AppRotateOnline 1

    # Startup type: Automatic (Delayed)
    & $NssmExe set $ServiceName Start SERVICE_DELAYED_AUTO_START

    # Run as current user (to access OAuth tokens in user profile)
    # Note: Services running as a local user require the user's password.
    # If this is running unattended/non-interactively, skip ObjectName and
    # let it run as LocalSystem — the OAuth tokens must then be in SYSTEM's profile.
    # For interactive installs, prompt for password here.
    $userPassword = $null
    if (-not $UseSchedTask) {
        # Try to get password interactively
        try {
            $securePw = Read-Host -AsSecureString "Enter password for $RunAsUser (or press Enter to skip/use LocalSystem)"
            $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePw)
            $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
            if ($plain -ne "") {
                $userPassword = $plain
            }
        } catch {
            Log "Could not prompt for password (non-interactive) — using LocalSystem." "WARN"
        }
    }

    if ($userPassword) {
        Log "Setting service to run as $RunAsUser"
        & $NssmExe set $ServiceName ObjectName $RunAsUser $userPassword
    } else {
        Log "No password provided — service will run as LocalSystem." "WARN"
        Log "OAuth tokens may not be accessible. Consider running as $RunAsUser." "WARN"
        # LocalSystem doesn't need ObjectName set
    }

    # Service display name and description
    & $NssmExe set $ServiceName DisplayName "Hermes Gateway (chief_of_staff)"
    & $NssmExe set $ServiceName Description "Hermes Discord+Telegram gateway for the chief_of_staff profile. Supervised by NSSM with auto-restart on crash."

    Log "NSSM service configured successfully." "OK"

    if ($StartNow) {
        Log "Starting service (--StartNow specified)..."
        Start-Service -Name $ServiceName
        Start-Sleep -Seconds 5
        $status = (Get-Service -Name $ServiceName).Status
        Log "Service status: $status"
    } else {
        Log "Service NOT started (gateway already running under VBS)."
        Log "When ready to cut over, run: Start-Service -Name $ServiceName"
    }

    return $true
}

# ─────────────────────────────────────────────────────────────────────────────
# Helper: Install via Scheduled Task (password-free fallback)
# ─────────────────────────────────────────────────────────────────────────────
function Install-SchedTaskFallback {
    $TaskName = "HermesGateway"
    Log "─── Installing Scheduled Task fallback: $TaskName ───"
    Log "(Scheduled tasks run as current user — no password needed)"

    # Watchdog script path (preferred entry point)
    $WatchdogScript = "C:\Users\micha\carrier_hermes\scripts\gateway_watchdog.py"
    $PythonWExe     = "C:\Users\micha\AppData\Local\hermes\hermes-agent\venv\Scripts\pythonw.exe"

    # Remove existing task if present
    $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($existing) {
        Log "Removing existing task: $TaskName"
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    }

    # Build environment setup prefix for the action
    $EnvSetup = @"
`$env:HERMES_HOME='C:\Users\micha\AppData\Local\hermes\profiles\chief_of_staff';
`$env:PYTHONIOENCODING='utf-8';
`$env:HERMES_GATEWAY_DETACHED='1';
`$env:VIRTUAL_ENV='C:\Users\micha\AppData\Local\hermes\hermes-agent\venv';
`$env:PYTHONPATH='C:\Users\micha\AppData\Local\hermes\hermes-agent';
"@

    # Decide what to run: watchdog if available, else gateway directly
    if (Test-Path $WatchdogScript) {
        $RunCmd = "$EnvSetup & '$PythonWExe' '$WatchdogScript'"
        Log "Action: Launch gateway_watchdog.py (manages gateway lifecycle)"
    } else {
        $RunCmd = "$EnvSetup & '$PythonExe' $GwArgs"
        Log "Action: Launch gateway directly (watchdog not found)"
    }

    $Action = New-ScheduledTaskAction `
        -Execute "powershell.exe" `
        -Argument "-NonInteractive -WindowStyle Hidden -Command `"$RunCmd`""

    # Trigger: at logon
    $LogonTrigger = New-ScheduledTaskTrigger -AtLogOn

    # Settings: restart on failure x3
    $Settings = New-ScheduledTaskSettingsSet `
        -ExecutionTimeLimit (New-TimeSpan -Days 365) `
        -MultipleInstances IgnoreNew `
        -StartWhenAvailable `
        -RestartCount 3 `
        -RestartInterval (New-TimeSpan -Minutes 1) `
        -RunOnlyIfNetworkAvailable:$false

    $Principal = New-ScheduledTaskPrincipal `
        -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
        -LogonType Interactive `
        -RunLevel Highest

    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $Action `
        -Trigger $LogonTrigger `
        -Settings $Settings `
        -Principal $Principal `
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

# ─────────────────────────────────────────────────────────────────────────────
# Main: try NSSM service first, fall back to scheduled task
# ─────────────────────────────────────────────────────────────────────────────
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

# ─────────────────────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "══════════════════════════════════════════════════════"
if ($success) {
    Write-Host "  ✅ HermesGateway supervisor INSTALLED SUCCESSFULLY"
} else {
    Write-Host "  ❌ Installation encountered errors — see output above"
}
Write-Host ""
Write-Host "  Gateway command : $PythonExe $GwArgs"
Write-Host "  Working dir     : $WorkDir"
Write-Host "  NSSM stdout     : $StdoutLog"
Write-Host "  NSSM stderr     : $StderrLog"
Write-Host ""
Write-Host "  ⚠  Service is NOT started (existing gateway is still running)."
Write-Host "     Cut over when ready:"
Write-Host "       # Stop current VBS-launched gateway gracefully"
Write-Host "       hermes -p chief_of_staff gateway stop"
Write-Host "       # Then start the NSSM service"
Write-Host "       Start-Service -Name HermesGateway"
Write-Host "     OR re-run this script with -StartNow to force-start now."
Write-Host "══════════════════════════════════════════════════════"

exit $(if ($success) { 0 } else { 1 })
