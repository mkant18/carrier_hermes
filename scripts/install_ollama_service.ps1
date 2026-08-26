<#
.SYNOPSIS
    Install Ollama + NSSM, register HermesOllama (demand-start) and
    HermesLocalLLMWatcher (auto-start) Windows services.

.DESCRIPTION
    Phase 1: Install Ollama silently, install NSSM via winget, register the
             HermesOllama service with OLLAMA_CONTEXT_LENGTH=64000 baked into
             its environment. Service is SERVICE_DEMAND_START — lifecycle is
             owned by the idle watcher, not Windows.
    Phase 2: Register HermesLocalLLMWatcher (local_llm_idle_watcher.py) as an
             auto-start service that starts/stops HermesOllama based on idle
             GPU + input signals.

    Run this script from an elevated (Administrator) PowerShell prompt.

.NOTES
    Model: qwen2.5:7b-instruct-q4_K_M (NOT qwen2.5:7b — exact tag required).
    After this script completes, you MUST manually run:
        ollama pull qwen2.5:7b-instruct-q4_K_M
    pip dependency for the watcher: pip install pynvml
#>

[CmdletBinding()]
param(
    [string]$OllamaSetupUrl = "https://ollama.com/download/OllamaSetup.exe",
    [string]$WatcherScript  = "C:\Users\micha\carrier_hermes\scripts\local_llm_idle_watcher.py"
)

$ErrorActionPreference = "Stop"

function Assert-Admin {
    $currentIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($currentIdentity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "This script must be run from an elevated (Administrator) PowerShell prompt."
    }
}

Write-Host "=== Phase 0: Preflight ===" -ForegroundColor Cyan
Assert-Admin

# ---------------------------------------------------------------------------
# Phase 1: Ollama + NSSM install, HermesOllama service registration
# ---------------------------------------------------------------------------
Write-Host "=== Phase 1: Install Ollama ===" -ForegroundColor Cyan

$installerPath = Join-Path $env:TEMP "OllamaSetup.exe"
Write-Host "Downloading Ollama installer from $OllamaSetupUrl ..."
Invoke-WebRequest -Uri $OllamaSetupUrl -OutFile $installerPath -UseBasicParsing

Write-Host "Running silent install: $installerPath /S"
Start-Process -FilePath $installerPath -ArgumentList "/S" -Wait

Write-Host "=== Phase 1: Install NSSM (via winget) ===" -ForegroundColor Cyan
winget install NSSM.NSSM --silent --accept-source-agreements --accept-package-agreements

# Resolve nssm.exe and ollama.exe on PATH after install (winget/ollama installers
# update PATH for new shells, but this process may still have a stale PATH).
function Resolve-ExeOrFail {
    param([string]$Name, [string[]]$ExtraSearchDirs = @())
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    foreach ($dir in $ExtraSearchDirs) {
        $candidate = Join-Path $dir $Name
        if (Test-Path $candidate) { return $candidate }
    }
    throw "$Name not found on PATH or in known install locations. Open a new shell and re-run, or pass an explicit path."
}

$nssmExe = Resolve-ExeOrFail -Name "nssm.exe" -ExtraSearchDirs @(
    "$env:ProgramFiles\nssm\win64",
    "${env:ProgramFiles(x86)}\nssm\win64",
    "$env:LOCALAPPDATA\Microsoft\WinGet\Packages"
)
$ollamaExe = Resolve-ExeOrFail -Name "ollama.exe" -ExtraSearchDirs @(
    "$env:LOCALAPPDATA\Programs\Ollama",
    "$env:ProgramFiles\Ollama"
)

Write-Host "Using nssm: $nssmExe"
Write-Host "Using ollama: $ollamaExe"

Write-Host "=== Phase 1: Register HermesOllama service (DEMAND_START) ===" -ForegroundColor Cyan

# Remove pre-existing registration so re-runs are idempotent.
& $nssmExe stop HermesOllama 2>$null | Out-Null
& $nssmExe remove HermesOllama confirm 2>$null | Out-Null

& $nssmExe install HermesOllama $ollamaExe serve
& $nssmExe set HermesOllama AppEnvironmentExtra "OLLAMA_CONTEXT_LENGTH=64000"
& $nssmExe set HermesOllama Start SERVICE_DEMAND_START

Write-Host "Verifying HermesOllama service registration ..."
sc.exe query HermesOllama

Write-Host ""
Write-Host "IMPORTANT: after this script finishes, manually run:" -ForegroundColor Yellow
Write-Host "    ollama pull qwen2.5:7b-instruct-q4_K_M" -ForegroundColor Yellow
Write-Host ""

# ---------------------------------------------------------------------------
# Phase 2: HermesLocalLLMWatcher service registration (AUTO_START)
# ---------------------------------------------------------------------------
Write-Host "=== Phase 2: Register HermesLocalLLMWatcher service (AUTO_START) ===" -ForegroundColor Cyan

$pythonExe = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
if (-not $pythonExe) {
    $pythonExe = (Get-Command python -ErrorAction SilentlyContinue).Source
}
if (-not $pythonExe) {
    throw "python not found on PATH. Install Python and/or ensure pynvml is installed (pip install pynvml), then re-run Phase 2."
}

if (-not (Test-Path $WatcherScript)) {
    throw "Watcher script not found at $WatcherScript"
}

Write-Host "Using python: $pythonExe"
Write-Host "Watcher script: $WatcherScript"

& $nssmExe stop HermesLocalLLMWatcher 2>$null | Out-Null
& $nssmExe remove HermesLocalLLMWatcher confirm 2>$null | Out-Null

& $nssmExe install HermesLocalLLMWatcher $pythonExe $WatcherScript
& $nssmExe set HermesLocalLLMWatcher Start SERVICE_AUTO_START
& $nssmExe set HermesLocalLLMWatcher AppNoConsole 1

Write-Host "Starting HermesLocalLLMWatcher ..."
sc.exe start HermesLocalLLMWatcher

Write-Host ""
Write-Host "Verifying HermesLocalLLMWatcher service registration ..."
sc.exe query HermesLocalLLMWatcher

Write-Host ""
Write-Host "=== Done ===" -ForegroundColor Green
Write-Host "Reminder: run 'ollama pull qwen2.5:7b-instruct-q4_K_M' if you have not already."
Write-Host "Reminder: pip install pynvml is required for the watcher process."
