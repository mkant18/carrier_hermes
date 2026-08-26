# start_gateway.ps1 — Clean-room gateway start for chief_of_staff
#
# PURPOSE: Starts the Hermes gateway in a child-context-free environment.
# ROOT CAUSE FIXED: When Hermes spawns a gateway from inside a Hermes session,
# the child process inherits HERMES_DELEGATED_CHILD_CONTEXT=1, which causes
# kanban_db.py to raise PermissionError on any kanban mutation, breaking the
# dispatcher permanently.
#
# USAGE:
#   powershell -ExecutionPolicy Bypass -File start_gateway.ps1
#   Or run from carrier_gateway_watchdog.py for auto-restarts.
#
# EXIT:  0 = gateway started and healthy
#        1 = failed (see gateway_watchdog.log)

param(
    [string]$Profile = "chief_of_staff",
    [int]$WaitSeconds = 10
)

$ErrorActionPreference = "Stop"

# --- Paths ------------------------------------------------------------------
$HermesHome = "$env:LOCALAPPDATA\hermes"
$LogDir     = "$HermesHome\carrier\logs"
$LogFile    = "$LogDir\gateway_watchdog.log"
$LockFile   = "$HermesHome\kanban\.dispatcher.lock"
$GwLogFile  = "$HermesHome\profiles\$Profile\logs\gateway.log"

# --- Logging helper ----------------------------------------------------------
function Log {
    param([string]$Msg, [string]$Level = "INFO")
    $ts = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
    $line = "[$ts] [$Level] [start_gateway] $Msg"
    Write-Host $line
    if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

Log "=== start_gateway.ps1 BEGIN (profile=$Profile) ==="

# --- Step 1: Scrub poisoned environment variables ---------------------------
Log "Clearing child-context env vars: HERMES_DELEGATED_CHILD_CONTEXT, HERMES_IS_CHILD, HERMES_CHILD_SESSION_ID"
$env:HERMES_DELEGATED_CHILD_CONTEXT = $null
$env:HERMES_IS_CHILD                = $null
$env:HERMES_CHILD_SESSION_ID        = $null
[System.Environment]::SetEnvironmentVariable("HERMES_DELEGATED_CHILD_CONTEXT", $null, "Process")
[System.Environment]::SetEnvironmentVariable("HERMES_IS_CHILD",                $null, "Process")
[System.Environment]::SetEnvironmentVariable("HERMES_CHILD_SESSION_ID",        $null, "Process")
Log "Child-context env vars cleared."

# --- Step 2: Verify no existing gateway is running --------------------------
Log "Checking for existing gateway process..."
$GwPidFile = "$HermesHome\profiles\$Profile\gateway.pid"
if (Test-Path $GwPidFile) {
    $existingPid = Get-Content $GwPidFile -Raw -ErrorAction SilentlyContinue
    $existingPid = $existingPid.Trim()
    if ($existingPid -match '^\d+$') {
        $proc = Get-Process -Id ([int]$existingPid) -ErrorAction SilentlyContinue
        if ($proc) {
            Log "Gateway already running (PID $existingPid). Exiting clean." "WARN"
            exit 0
        } else {
            Log "Stale PID file (PID $existingPid not alive). Continuing." "WARN"
        }
    }
}

# --- Step 3: Remove stale dispatcher lock if no gateway is running ----------
if (Test-Path $LockFile) {
    $lockContent = Get-Content $LockFile -Raw -ErrorAction SilentlyContinue
    $lockContent = $lockContent.Trim()
    $lockPid = $null
    try {
        $lockJson = $lockContent | ConvertFrom-Json -ErrorAction SilentlyContinue
        $lockPid  = $lockJson.pid
    } catch {
        # Plain text PID
        if ($lockContent -match '^\d+$') { $lockPid = [int]$lockContent }
    }

    $lockOwnerAlive = $false
    if ($lockPid) {
        $lockProc = Get-Process -Id $lockPid -ErrorAction SilentlyContinue
        if ($lockProc) { $lockOwnerAlive = $true }
    }

    if (-not $lockOwnerAlive) {
        Log "Removing stale dispatcher lock (lock owner PID $lockPid not running): $LockFile" "WARN"
        Remove-Item -Path $LockFile -Force
        Log "Stale lock removed."
    } else {
        Log "Dispatcher lock is held by live PID $lockPid — not removing."
    }
}

# --- Step 4: Start the gateway in a fresh environment -----------------------
Log "Launching: hermes -p $Profile gateway start"
try {
    $proc = Start-Process `
        -FilePath "hermes" `
        -ArgumentList "-p", $Profile, "gateway", "start" `
        -NoNewWindow `
        -PassThru `
        -RedirectStandardOutput "$env:TEMP\gw_start_stdout.txt" `
        -RedirectStandardError  "$env:TEMP\gw_start_stderr.txt"

    Log "hermes process started (PID $($proc.Id)). Waiting ${WaitSeconds}s for gateway to become healthy..."
    $proc.WaitForExit($WaitSeconds * 1000) | Out-Null
} catch {
    Log "Failed to start hermes gateway: $_" "ERROR"
    exit 1
}

# --- Step 5: Wait for gateway log to confirm success ------------------------
Log "Checking $GwLogFile for startup confirmation..."
$startTime = Get-Date
$deadline  = $startTime.AddSeconds($WaitSeconds)
$healthy   = $false

while ((Get-Date) -lt $deadline) {
    if (Test-Path $GwLogFile) {
        $tail = Get-Content $GwLogFile -Tail 50 -ErrorAction SilentlyContinue
        $indicator = $tail | Where-Object {
            $_ -match "(gateway.*started|discord.*connected|telegram.*connected|platforms.*connected|gateway_state.*running)"
        }
        if ($indicator) {
            $healthy = $true
            break
        }
    }
    Start-Sleep -Milliseconds 500
}

if ($healthy) {
    Log "=== Gateway HEALTHY — startup confirmed in gateway.log ===" "SUCCESS"
    exit 0
} else {
    Log "=== Gateway did NOT confirm healthy within ${WaitSeconds}s — check $GwLogFile ===" "ERROR"
    # Capture any startup stdout/stderr for the log
    if (Test-Path "$env:TEMP\gw_start_stdout.txt") {
        $out = Get-Content "$env:TEMP\gw_start_stdout.txt" -Raw -ErrorAction SilentlyContinue
        if ($out) { Log "STDOUT: $out" "DEBUG" }
    }
    if (Test-Path "$env:TEMP\gw_start_stderr.txt") {
        $err = Get-Content "$env:TEMP\gw_start_stderr.txt" -Raw -ErrorAction SilentlyContinue
        if ($err) { Log "STDERR: $err" "DEBUG" }
    }
    exit 1
}
