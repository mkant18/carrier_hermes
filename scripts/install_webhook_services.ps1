<#
.SYNOPSIS
    Register carrier-webhook-receiver and carrier-peers-broker as Windows
    NSSM services.

.DESCRIPTION
    Registers two always-on services for the carrier_hermes webhook/peers layer:

    carrier-webhook-receiver — Python Flask server on port 8800.
        Receives authenticated webhook events and dispatches kanban tasks.

    carrier-peers-broker — Python HTTP server on port 9876.
        Manages peer fleet registry and forwards peer events to the webhook receiver.

    Both services run as SERVICE_AUTO_START, stdout/stderr redirected to log
    files under C:\Users\micha\AppData\Local\hermes\carrier\logs\.

    Run from an elevated (Administrator) PowerShell prompt.

.PARAMETER ScriptsDir
    Path to carrier_hermes\scripts\ directory.
    Default: C:\Users\micha\carrier_hermes\scripts

.PARAMETER PythonExe
    Full path to python.exe to use for the services.
    Default: resolved from PATH.

.PARAMETER NssmExe
    Full path to nssm.exe.
    Default: resolved from PATH and common install locations.

.NOTES
    NSSM must be installed first (winget install NSSM.NSSM or from nssm.cc).
    Python must have webhook_db deps available (no extra deps for stdlib-only operation).
    Flask is optional (carrier-webhook-receiver falls back to http.server if missing).

.EXAMPLE
    # Install services with defaults
    .\install_webhook_services.ps1

    # Dry-run (WhatIf): see what would be registered without running
    .\install_webhook_services.ps1 -WhatIf
#>

[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$ScriptsDir = "C:\Users\micha\carrier_hermes\scripts",
    [string]$PythonExe  = "",
    [string]$NssmExe    = ""
)

$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

function Assert-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($id)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "This script must be run from an elevated (Administrator) PowerShell prompt."
    }
}

function Resolve-ExeOrFail {
    param([string]$Name, [string[]]$ExtraSearchDirs = @())
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    foreach ($dir in $ExtraSearchDirs) {
        $candidate = Join-Path $dir $Name
        if (Test-Path $candidate) { return $candidate }
    }
    throw "$Name not found on PATH or in $($ExtraSearchDirs -join ', '). Install it first."
}

function Register-NssmService {
    param(
        [string]$ServiceName,
        [string]$Exe,
        [string]$Args,
        [hashtable]$EnvExtra = @{},
        [string]$LogDir
    )

    Write-Host "  Removing existing $ServiceName (if any)..." -ForegroundColor DarkGray
    & $nssmPath stop   $ServiceName 2>$null | Out-Null
    & $nssmPath remove $ServiceName confirm 2>$null | Out-Null

    if ($PSCmdlet.ShouldProcess($ServiceName, "nssm install")) {
        & $nssmPath install $ServiceName $Exe $Args
        & $nssmPath set     $ServiceName Start SERVICE_AUTO_START
        & $nssmPath set     $ServiceName AppNoConsole 1
        & $nssmPath set     $ServiceName AppRestartDelay 5000

        $stdout = Join-Path $LogDir "${ServiceName}_stdout.log"
        $stderr = Join-Path $LogDir "${ServiceName}_stderr.log"
        & $nssmPath set $ServiceName AppStdout $stdout
        & $nssmPath set $ServiceName AppStderr $stderr
        & $nssmPath set $ServiceName AppRotateFiles 1
        & $nssmPath set $ServiceName AppRotateBytes 10485760  # 10 MB

        foreach ($kv in $EnvExtra.GetEnumerator()) {
            & $nssmPath set $ServiceName AppEnvironmentExtra "$($kv.Key)=$($kv.Value)"
        }
    }
}

# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------

Write-Host "=== Carrier Webhook Services — NSSM Registration ===" -ForegroundColor Cyan
Write-Host ""

Assert-Admin

# Resolve NSSM
$nssmSearchDirs = @(
    "$env:ProgramFiles\nssm\win64",
    "${env:ProgramFiles(x86)}\nssm\win64",
    "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\NSSM.NSSM_Microsoft.Winget.Source_8wekyb3d8bbwe\nssm-2.24\win64"
)
if ($NssmExe -ne "") {
    $nssmPath = $NssmExe
} else {
    $nssmPath = Resolve-ExeOrFail -Name "nssm.exe" -ExtraSearchDirs $nssmSearchDirs
}
Write-Host "NSSM      : $nssmPath"

# Resolve Python
if ($PythonExe -ne "") {
    $pythonPath = $PythonExe
} else {
    $pythonPath = Resolve-ExeOrFail -Name "python.exe" -ExtraSearchDirs @(
        "C:\Python311", "C:\Python312",
        "$env:LOCALAPPDATA\Programs\Python\Python311",
        "$env:LOCALAPPDATA\Programs\Python\Python312"
    )
}
Write-Host "Python    : $pythonPath"

# Validate scripts
$receiverScript = Join-Path $ScriptsDir "webhook_receiver.py"
$brokerScript   = Join-Path $ScriptsDir "peers_broker.py"

if (-not (Test-Path $receiverScript)) {
    throw "webhook_receiver.py not found at $receiverScript"
}
if (-not (Test-Path $brokerScript)) {
    throw "peers_broker.py not found at $brokerScript"
}
Write-Host "Scripts   : $ScriptsDir"
Write-Host ""

# Ensure log dir exists
$logDir = "C:\Users\micha\AppData\Local\hermes\carrier\logs"
if ($PSCmdlet.ShouldProcess($logDir, "mkdir")) {
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
}
Write-Host "Log dir   : $logDir"
Write-Host ""

# ---------------------------------------------------------------------------
# Register carrier-webhook-receiver (port 8800)
# ---------------------------------------------------------------------------

Write-Host "=== Registering carrier-webhook-receiver (port 8800) ===" -ForegroundColor Cyan

Register-NssmService `
    -ServiceName "carrier-webhook-receiver" `
    -Exe         $pythonPath `
    -Args        $receiverScript `
    -EnvExtra    @{
        CARRIER_WEBHOOK_PORT = "8800"
        CARRIER_WEBHOOK_HOST = "127.0.0.1"
    } `
    -LogDir      $logDir

if ($PSCmdlet.ShouldProcess("carrier-webhook-receiver", "sc.exe start")) {
    Write-Host "  Starting carrier-webhook-receiver..."
    sc.exe start "carrier-webhook-receiver" | Out-Null
    Start-Sleep -Seconds 2
    sc.exe query "carrier-webhook-receiver"
}

Write-Host ""

# ---------------------------------------------------------------------------
# Register carrier-peers-broker (port 9876)
# ---------------------------------------------------------------------------

Write-Host "=== Registering carrier-peers-broker (port 9876) ===" -ForegroundColor Cyan

Register-NssmService `
    -ServiceName "carrier-peers-broker" `
    -Exe         $pythonPath `
    -Args        $brokerScript `
    -EnvExtra    @{
        CARRIER_PEERS_PORT   = "9876"
        CARRIER_PEERS_HOST   = "127.0.0.1"
        CARRIER_WEBHOOK_HOST = "127.0.0.1"
        CARRIER_WEBHOOK_PORT = "8800"
    } `
    -LogDir      $logDir

if ($PSCmdlet.ShouldProcess("carrier-peers-broker", "sc.exe start")) {
    Write-Host "  Starting carrier-peers-broker..."
    sc.exe start "carrier-peers-broker" | Out-Null
    Start-Sleep -Seconds 2
    sc.exe query "carrier-peers-broker"
}

Write-Host ""
Write-Host "=== Registration complete ===" -ForegroundColor Green
Write-Host ""
Write-Host "Services registered:"
Write-Host "  carrier-webhook-receiver  -> POST http://127.0.0.1:8800/hooks/<endpoint_id>"
Write-Host "  carrier-peers-broker      -> POST http://127.0.0.1:9876/peers/register"
Write-Host ""
Write-Host "Health checks:"
Write-Host "  curl http://127.0.0.1:8800/health"
Write-Host "  curl http://127.0.0.1:9876/health"
Write-Host ""
Write-Host "Manage webhooks:"
Write-Host "  python $ScriptsDir\manage_webhooks.py list"
Write-Host "  python $ScriptsDir\manage_webhooks.py create --name 'My hook' --bot ops_lt"
Write-Host ""
Write-Host "Logs at: $logDir"
Write-Host ""
Write-Host "NEXT: Register webhook triggers for peer events."
Write-Host "  The peers broker needs 3 webhook endpoints registered in the receiver:"
Write-Host "  1. endpoint_id=peer-registered  bot=ops_lt"
Write-Host "  2. endpoint_id=peer-task         bot=<target determined by payload.to_bot>"
Write-Host "  3. endpoint_id=peer-left         bot=passive_watch"
Write-Host ""
Write-Host "  The local secret at:"
Write-Host "  C:\Users\micha\AppData\Local\hermes\carrier\webhook_local_secret"
Write-Host "  is auto-generated by the broker at first start. Use it as the bearer"
Write-Host "  secret when creating those 3 triggers with manage_webhooks.py."
