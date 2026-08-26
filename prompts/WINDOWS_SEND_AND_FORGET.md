# SEND-AND-FORGET — Carrier Hermes Windows Primary Host (full auto)

> **Paste this ENTIRE message into a fresh Hermes session on the Windows PC.**
> Give it full tool access (approvals: smart or yolo for local config).
> **Pin THIS chat model to OpenRouter cheap only:**
> `deepseek/deepseek-v4-flash-0731` (fallback `google/gemini-2.5-flash-lite`).
> **NEVER** use OpenRouter Claude/Grok or Anthropic/xAI API keys for anything.

You are an autonomous installer. **Do not ask Michael to run shell recipes you can run yourself.** Use terminal, browser, file tools, and sub-agents. Work until smokes pass or you hit a hard human gate (listed below). Report once at the end.

---

## Mission

Make **this Windows machine** the **primary host** for the full Carrier Hermes bot fleet:

1. Hermes installed + doctor OK  
2. Repo `carrier_hermes` on `main`  
3. `~/.hermes` ↔ native Hermes home linked  
4. All Doppler secrets pulled and wired  
5. Full bot roster + SOULs + matrix pins  
6. Billing hard-lock: **OpenRouter never carries Claude/Grok**  
7. `smoke_fleet` run with honest PASS/FAIL  

**Product language:** say **bot**, not “profile” (except CLI `hermes profile create`).

**Authority (read, don’t reinvent):**  
`https://github.com/mkant18/carrier_hermes` → especially  
`prompts/WINDOWS_PRIMARY_HOST_SETUP.md`, `COST_MODEL.md`, `bots/BOT_MATRIX.md`,  
`scripts/or_billing_policy.py`, `scripts/windows_primary_bootstrap.ps1`,  
`scripts/windows_primary_fleet_setup.sh`.

---

## Hard stops (only times you may block on Michael)

1. **Discord Developer Portal MFA** — never drive past MFA. Ask him to paste tokens once.  
2. **OAuth consent screens** he must click (SuperGrok / Claude Max / Google) — open browser, wait, tell him to complete if stuck.  
3. **Obsidian vault path** unknown — ask once, then proceed.  
4. **Doppler login** if browser auth needs him — open it, wait.  

Everything else: you do it.

---

## HARD BILLING RULE — PERIOD, FULL STOP

- Claude/Anthropic → **only** `provider: anthropic` (Claude Max OAuth).  
- Grok/xAI → **only** `provider: xai-oauth` (SuperGrok).  
- **Forbidden forever:** `ANTHROPIC_API_KEY`, `XAI_API_KEY`, `GROK_API_KEY`, bare provider `xai`, any OpenRouter route to claude/sonnet/opus/haiku/grok/x-ai/anthropic.  
- OpenRouter = **allowlist only**: DeepSeek flash/chat, Gemini Flash/Lite, gpt-oss.  
- Enforce after wiring:  
  `python scripts/or_billing_policy.py && python scripts/billing_guard.py --fix-env --fix-config`  
  Must PASS before claiming done.

If OAuth fails, **STOP** — do not “fix” with API keys or OpenRouter Claude/Grok.

---

## Execution order (run all; don’t stop early)

### Phase 0 — Detect OS + shell

```powershell
$PSVersionTable.PSVersion
echo $env:LOCALAPPDATA
echo $env:USERPROFILE
where.exe hermes 2>$null
where.exe git 2>$null
where.exe doppler 2>$null
```

Prefer **PowerShell** for install; **Git Bash** (`%LOCALAPPDATA%\hermes\git\usr\bin\bash.exe` or `HERMES_GIT_BASH_PATH`) for `*.sh` fleet scripts.

### Phase 1 — Install Hermes if missing

```powershell
iex (irm https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.ps1)
```

If already installed, skip. Refresh PATH in-session:

```powershell
$env:PATH = "$env:LOCALAPPDATA\hermes\hermes-agent\bin;$env:PATH"
hermes doctor
```

### Phase 2 — Bootstrap carrier layout

Run (download if needed):

```powershell
# Prefer local clone script after clone; else:
irm https://raw.githubusercontent.com/mkant18/carrier_hermes/main/scripts/windows_primary_bootstrap.ps1 -OutFile $env:TEMP\ch_boot.ps1
powershell -ExecutionPolicy Bypass -File $env:TEMP\ch_boot.ps1
```

This must: install/link Hermes, junction `%USERPROFILE%\.hermes` → `%LOCALAPPDATA%\hermes`, clone `~/carrier_hermes`, write `HOST_ROLE.json` primary/windows.

If junction already exists as a real dir conflict, fix carefully (backup, then junction).

```powershell
cd $env:USERPROFILE\carrier_hermes
git pull --ff-only origin main
$env:CARRIER_HERMES_ROOT = "$env:USERPROFILE\carrier_hermes"
$env:HERMES_HOME = "$env:LOCALAPPDATA\hermes"
```

### Phase 3 — Auth (browser OK)

```powershell
hermes auth list
```

If missing **xai-oauth** or **anthropic**:

```powershell
hermes setup
# or hermes auth / model flows — drive browser; Michael clicks Approve if needed
```

Verify both present. **Never** write Anthropic/xAI API keys into `.env`.

### Phase 4 — Vault path

If `OBSIDIAN_VAULT_PATH` unset in `%USERPROFILE%\.hermes\.env`:

- Search common locations under User profile / Documents / Desktop for an Obsidian vault.  
- If still unknown → **one** clarify question.  
- Write path with forward slashes. Create `_agent/**` tree under vault (email, drafts, calendar, todoist, mailbox, lockbox, api_watcher, audit, state, … per repo docs).

### Phase 5 — Doppler

Install CLI if needed (`winget install Doppler.doppler` or docs installer).

```powershell
doppler login          # browser
doppler setup --project carrier-ops --config prd
doppler secrets --project carrier-ops --config prd --only-names
```

### Phase 6 — Secrets

**Pull every secret name** from Doppler `carrier-ops`/`prd` and wire without printing values:

| Secret family | Destination |
|---|---|
| `OPENROUTER_API_KEY`, `OPENROUTER_MANAGEMENT_KEY` | `~/.hermes/.env` |
| `TODOIST_API_TOKEN`, `GITHUB_TOKEN` | default + relevant bot homes |
| `DISCORD_BOT_TOKEN` / Carrier Ops | **only** `profiles/chief_of_staff/.env` as `DISCORD_BOT_TOKEN` |
| First Watch / `DISCORD_FLEET_BOT_TOKEN` | default `.env` — **no second gateway** |
| Wing tokens | `bash scripts/wire_wing_tokens.sh` |
| Google OAuth set | LockBox secrets dir 0600 + wire scripts if present |
| Doppler service tokens | **only** `profiles/lockbox/.env` + `LOCKBOX_SHADOW_MODE=true` |

**If `OPENROUTER_API_KEY` missing:** browser sub-agent → https://openrouter.ai/keys → create `carrier-windows-primary` → store Doppler (REST if key contains `=`) + local `.env`. Length/prefix verify only.

**OpenRouter privacy 404 fix (if Flash/DeepSeek 404s):** browser to https://openrouter.ai/settings/privacy + workspace Guardrails — ensure paid DeepSeek/Gemini Flash endpoints aren’t zeroed by ZDR/provider blocks. Do **not** enable free-model training just for Carrier; use **paid** allowlisted models. Prefer workspace allowlist = Carrier cheap list via `python scripts/sync_or_billing_guardrail.py` if management key exists.

**Discord MFA tokens:** if wing tokens missing, STOP with checklist from `docs/DISCORD_WING_APPS.md` — do not automate MFA.

### Phase 7 — Fleet scripts (Git Bash)

```bash
export CARRIER_HERMES_ROOT="$HOME/carrier_hermes"
export HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
bash "$CARRIER_HERMES_ROOT/scripts/windows_primary_fleet_setup.sh"
```

If that script isn’t present, manually:

```bash
bash "$CARRIER_HERMES_ROOT/scripts/install_bot_homes.sh"
bash "$CARRIER_HERMES_ROOT/scripts/wire_wing_tokens.sh" || true
# QUIT Hermes Desktop serves if needed, then:
bash "$CARRIER_HERMES_ROOT/scripts/apply_bot_matrix.sh"
python3 "$CARRIER_HERMES_ROOT/scripts/billing_guard.py" --fix-env --fix-config
bash "$CARRIER_HERMES_ROOT/scripts/smoke_fleet.sh"
```

**Pin clobber:** if all bots read back grok after matrix, quit Desktop, re-run `apply_bot_matrix.sh`, verify pins.

**Helm SUPER-USER:** never strip CoS tools in matrix.

### Phase 8 — OSB / Todoist / Google (best effort)

Follow `integrations/obsidian-second-brain.md` with Windows vault path.  
Todoist MCP on Tasker if token present.  
Google wire scripts if OAuth secrets exist.  
No mail **send** tools anywhere.

### Phase 9 — Crons (primary host)

Install no_agent Vigil/Ledger heartbeats and other crons per `WINDOWS_PRIMARY_HOST_SETUP.md` / BOT_MATRIX if not already present. Document if cron daemon needs Desktop/gateway running.

### Phase 10 — Acceptance (all required)

- [ ] `hermes doctor` usable  
- [ ] xai-oauth + anthropic present  
- [ ] `HOST_ROLE.json` = primary/windows  
- [ ] Doppler pull done; missing secrets listed  
- [ ] `billing_guard` PASS  
- [ ] Bot homes installed; SOULs not stubs  
- [ ] Matrix pins sample OK **or** honest FAIL + cause  
- [ ] Single Discord gateway (Helm only)  
- [ ] LockBox shadow ST only on lockbox home  
- [ ] `smoke_fleet` output pasted (honest)  
- [ ] No secrets in git; no API keys for Claude/Grok  

---

## Final report format (only user-facing message when done)

1. Host paths (HERMES_HOME, CARRIER_ROOT, vault)  
2. Auth providers OK/missing  
3. Doppler: present / missing / created (no values)  
4. billing_guard: PASS/FAIL (quote one line)  
5. smoke_fleet: paste PASS/FAIL block  
6. Human leftovers (MFA, vault, OAuth clicks)  
7. Three daily commands for the PC  

**Start now. Do not wait for confirmation.**
