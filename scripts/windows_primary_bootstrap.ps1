#Requires -Version 5.1
<#
.SYNOPSIS
  Carrier Hermes — Windows primary-host bootstrap (Phase 0–1).

.DESCRIPTION
  Installs Hermes (native Windows), clones carrier_hermes, links HERMES data
  so fleet scripts that expect ~/.hermes work, installs Doppler CLI if missing,
  writes HOST_ROLE=primary, and prints the next Git Bash commands.

  Does NOT paste secrets into chat. Does NOT drive Discord MFA.
  After this script: open a NEW terminal, run oauth, then the bash fleet script.

.NOTES
  Repo: https://github.com/mkant18/carrier_hermes
  Full agent prompt: prompts/WINDOWS_PRIMARY_HOST_SETUP.md
#>

$ErrorActionPreference = "Stop"

function Write-Step($msg) { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "OK  $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "WARN  $msg" -ForegroundColor Yellow }

Write-Step "0) Preflight"
Write-Host "User: $env:USERNAME"
Write-Host "HOME: $env:USERPROFILE"
Write-Host "LOCALAPPDATA: $env:LOCALAPPDATA"

# ---------------------------------------------------------------------------
Write-Step "1) Install Hermes (native Windows)"
# Official: https://hermes-agent.nousresearch.com/docs/user-guide/windows-native
try {
  $hermesCmd = Get-Command hermes -ErrorAction SilentlyContinue
} catch { $hermesCmd = $null }

if (-not $hermesCmd) {
  Write-Host "Running official install.ps1 (no admin required)..."
  # Skip interactive setup wizard so this script stays non-blocking; run hermes setup after.
  & ([scriptblock]::Create((irm https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.ps1))) -SkipSetup
  Write-Ok "Installer finished — OPEN A NEW PowerShell/Windows Terminal window so PATH refreshes"
  Write-Host "Then re-run this script, or continue from step 2 manually."
  Write-Host "Quick check after new terminal:  hermes doctor"
} else {
  Write-Ok "hermes already on PATH: $($hermesCmd.Source)"
}

# Refresh PATH for this session if possible
$hermesBin = Join-Path $env:LOCALAPPDATA "hermes\hermes-agent\bin"
if (Test-Path $hermesBin) {
  if ($env:PATH -notlike "*$hermesBin*") {
    $env:PATH = "$hermesBin;$env:PATH"
  }
}

# ---------------------------------------------------------------------------
Write-Step "2) HERMES_HOME layout (critical on Windows)"
# Native Hermes data: %LOCALAPPDATA%\hermes
# Fleet bash/Python scripts expect: %USERPROFILE%\.hermes
$nativeHome = Join-Path $env:LOCALAPPDATA "hermes"
$userHermes = Join-Path $env:USERPROFILE ".hermes"

if (-not (Test-Path $nativeHome)) {
  New-Item -ItemType Directory -Path $nativeHome -Force | Out-Null
  Write-Ok "Created $nativeHome"
}

if (Test-Path $userHermes) {
  $item = Get-Item $userHermes -Force
  if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
    Write-Ok "~/.hermes already a junction/symlink"
  } else {
    Write-Warn "$userHermes exists as a real directory (not a junction)."
    Write-Warn "Fleet scripts and native Hermes may diverge. Prefer renaming it and re-running."
    Write-Host "  Suggested: Rename-Item '$userHermes' '$userHermes.bak-pre-carrier'"
  }
} else {
  # Directory junction so both paths share one store
  cmd /c mklink /J "$userHermes" "$nativeHome" | Out-Null
  Write-Ok "Junction: $userHermes  =>  $nativeHome"
}

# Persist HERMES_HOME for User scope
[Environment]::SetEnvironmentVariable("HERMES_HOME", $nativeHome, "User")
$env:HERMES_HOME = $nativeHome
Write-Ok "HERMES_HOME (User) = $nativeHome"

# ---------------------------------------------------------------------------
Write-Step "3) Clone carrier_hermes"
$repo = Join-Path $env:USERPROFILE "carrier_hermes"
if (Test-Path (Join-Path $repo ".git")) {
  Push-Location $repo
  git pull --ff-only origin main
  Pop-Location
  Write-Ok "Updated $repo"
} else {
  git clone https://github.com/mkant18/carrier_hermes.git $repo
  Write-Ok "Cloned $repo"
}

$env:CARRIER_HERMES_ROOT = $repo
[Environment]::SetEnvironmentVariable("CARRIER_HERMES_ROOT", $repo, "User")

# ---------------------------------------------------------------------------
Write-Step "4) Primary-host marker"
$carrierDir = Join-Path $userHermes "carrier"
New-Item -ItemType Directory -Path $carrierDir -Force | Out-Null
$hostJson = Join-Path $carrierDir "HOST_ROLE.json"
@"
{
  "role": "primary",
  "platform": "windows",
  "fleet": "carrier_hermes",
  "hermes_home": "$($nativeHome -replace '\\','/')",
  "carrier_root": "$($repo -replace '\\','/')",
  "notes": "Default runtime for bots/crons/Kanban. Mac is secondary."
}
"@ | ForEach-Object { $_ } | Out-File -FilePath $hostJson -Encoding utf8
# Strip BOM if PowerShell added one
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[IO.File]::WriteAllText($hostJson, ([IO.File]::ReadAllText($hostJson)).Trim() + "`n", $utf8NoBom)
Write-Ok "Wrote $hostJson"

# Non-secret env seeds (create if missing)
$envFile = Join-Path $userHermes ".env"
if (-not (Test-Path $envFile)) {
  New-Item -ItemType File -Path $envFile -Force | Out-Null
}
function Ensure-EnvLine([string]$key, [string]$value) {
  $lines = Get-Content $envFile -ErrorAction SilentlyContinue
  if ($lines | Where-Object { $_ -match "^$key=" }) { return }
  Add-Content -Path $envFile -Value "$key=$value"
}
Ensure-EnvLine "CARRIER_HERMES_ROOT" ($repo -replace '\\','/')
Ensure-EnvLine "CARRIER_HOST_ROLE" "primary"
Ensure-EnvLine "HERMES_HOME" ($nativeHome -replace '\\','/')
Write-Ok "Seeded non-secret keys in $envFile (set OBSIDIAN_VAULT_PATH yourself)"

# ---------------------------------------------------------------------------
Write-Step "5) Doppler CLI (optional install via winget)"
$doppler = Get-Command doppler -ErrorAction SilentlyContinue
if (-not $doppler) {
  $winget = Get-Command winget -ErrorAction SilentlyContinue
  if ($winget) {
    Write-Host "Installing Doppler CLI via winget..."
    winget install --id Doppler.doppler -e --accept-source-agreements --accept-package-agreements
  } else {
    Write-Warn "winget not found. Install Doppler from https://docs.doppler.com/docs/install-cli"
  }
} else {
  Write-Ok "doppler on PATH"
}

# ---------------------------------------------------------------------------
Write-Step "6) Locate Git Bash (for fleet *.sh scripts)"
$bashCandidates = @(
  $env:HERMES_GIT_BASH_PATH,
  (Join-Path $env:LOCALAPPDATA "hermes\git\usr\bin\bash.exe"),
  (Join-Path $env:LOCALAPPDATA "hermes\git\bin\bash.exe"),
  "C:\Program Files\Git\bin\bash.exe",
  "C:\Program Files\Git\usr\bin\bash.exe"
) | Where-Object { $_ -and (Test-Path $_) }

if ($bashCandidates.Count -gt 0) {
  $bash = $bashCandidates[0]
  Write-Ok "Git Bash: $bash"
  [Environment]::SetEnvironmentVariable("HERMES_GIT_BASH_PATH", $bash, "User")
  $env:HERMES_GIT_BASH_PATH = $bash
} else {
  Write-Warn "bash.exe not found yet — finish Hermes install / open new terminal, then re-run"
  $bash = $null
}

# ---------------------------------------------------------------------------
Write-Step "DONE — human steps next"
Write-Host @"

NEXT (in a NEW PowerShell window):

  1) hermes doctor
  2) hermes auth   # or: hermes setup
       - complete SuperGrok (xai-oauth)
       - complete Claude Max (anthropic OAuth)
       - NEVER set ANTHROPIC_API_KEY or XAI_API_KEY
  3) Set vault path (edit %USERPROFILE%\.hermes\.env):
       OBSIDIAN_VAULT_PATH=C:/path/to/your/ObsidianVault
  4) doppler login
     doppler setup --project carrier-ops --config prd
  5) Fleet wire-up via Git Bash:

"@

if ($bash) {
  Write-Host "     & `"$bash`" -lc `"export CARRIER_HERMES_ROOT=`$HOME/carrier_hermes; bash `$HOME/carrier_hermes/scripts/windows_primary_fleet_setup.sh`""
} else {
  Write-Host "     bash ~/carrier_hermes/scripts/windows_primary_fleet_setup.sh"
}

Write-Host @"

  6) OR paste the full agent prompt into Hermes Desktop chat (cheap model):
       $repo\prompts\WINDOWS_PRIMARY_HOST_SETUP.md
       Model for that chat: openrouter/deepseek/deepseek-v4-flash-0731

"@
