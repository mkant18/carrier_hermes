# Carrier Hermes — WINDOWS PRIMARY HOST SETUP (one-shot)

> **Paste this entire prompt into a fresh Hermes session on the Windows PC** with full tool access.
>
> **Goal:** Make **this Windows machine** the **default primary host** for the full Carrier Hermes bot fleet (more RAM / GPU / storage). Stand up Hermes + clone the frozen fleet repo + pull **all** secrets from Doppler + wire bot homes + apply matrix + **hard-block Anthropic/Grok API-token billing** + smokes.
>
> **Do not re-invent Phase A** — protocol is frozen on `main`.
>
> **Product language:** always **bot**. CLI `hermes profile create` = create bot home only.
>
> **Host:** Windows primary. Never assume Mac paths (`/Users/michaelkanter/...`).

---

## Which model should RUN THIS SETUP PROMPT? (cheap OpenRouter)

This session is mostly shell + file + browser wiring — **not** fleet production traffic.

| Priority | Model (OpenRouter) | When |
|---|---|---|
| **1 — recommended** | `openrouter/deepseek/deepseek-v4-flash-0731` | Default for this one-shot. Tool-calling verified, ~cheapest paid tail in `COST_MODEL.md`. |
| **2 — fallback** | `openrouter/google/gemini-2.5-flash-lite` | If DeepSeek flakes/timeouts. |
| **3 — only if both fail** | `openrouter/deepseek/deepseek-chat-v3-0324` | Heavier; use sparingly. |

**Do NOT run this setup prompt on:**

- Claude Opus / Sonnet via **API key** or OpenRouter
- Grok via **API key** or OpenRouter
- Any `:free` rotator as the sole decider for writing secrets/matrix

**OAuth on the PC is still required for the fleet itself** (after setup): SuperGrok (`xai-oauth`) + Claude Max (`anthropic`). Those are for **bots**, not required as the model *driving this install session* if you pin the session to DeepSeek Flash.

**Session pin example (before pasting this prompt):**

```bash
hermes model   # or Desktop model picker
# set provider openrouter + deepseek/deepseek-v4-flash-0731 for THIS chat only
```

---

## CRITICAL ORDERING

```
W0  Prereqs + Hermes install + doctor
W1  Clone carrier_hermes + Windows primary paths
W2  Doppler login + FULL secret pull + wire
W3  Create MISSING secrets (browser sub-agent; MFA stop for Discord)
W4  BILLING HARD-LOCK (Anthropic/Grok API tokens NEVER)
W5  Bot homes + SOULs + AIPass
W6  apply_bot_matrix + billing_guard verify
W7  OSB / Todoist / Google
W8  Discord posture + crons
W9  smoke_fleet + report
```

---

## Authority order

1. `docs/INTER_AGENT_PROTOCOL.md`
2. `bots/BOT_MATRIX.md` + `bots/*/SOUL.md`
3. `COST_MODEL.md` + `GOVERNANCE.md`
4. `docs/DISCORD_*.md`
5. `scripts/apply_bot_matrix.sh` + `scripts/billing_guard.py` + `scripts/wire_wing_tokens.sh` + `scripts/smoke_fleet.sh`
6. This prompt (Windows delta)

Repo: `https://github.com/mkant18/carrier_hermes.git`  
Clone: `%USERPROFILE%\carrier_hermes` → `$HOME/carrier_hermes`

---

## Non-negotiables

1. Full bot roster from repo scripts/matrix (18+ including Lts, LockBox, Marshal/Yeoman if present).
2. **Helm SUPER-USER** — never strip CoS tools in matrix apply. **No Doppler ST on Helm.**
3. **LockBox** sole Doppler service-token holder; `LOCKBOX_SHADOW_MODE=true` until Michael enables live redeem.
4. **HARD BILLING RULE — PERIOD, FULL STOP:**
   - Anthropic/Claude + xAI/Grok = **OAuth/subscription ONLY** (`provider: anthropic`, `provider: xai-oauth`).
   - **OpenRouter is ALLOWLIST-ONLY (default deny).** Only DeepSeek flash/chat, Gemini Flash/Lite, gpt-oss may ride OR.  
     Any other OR model — including **every** `anthropic/*`, `x-ai/*`, bare `claude*`, bare `grok*`, GPT-4/5, Gemini Pro — is a hard fail.
   - Also blocks `base_url: https://openrouter.ai/...` + Claude/Grok even if `provider` is disguised.
   - Also blocks other metered aggregators (together, fireworks, bedrock, …) for the same families.
   - **Forbidden env:** `ANTHROPIC_API_KEY`, `XAI_API_KEY`, `GROK_API_KEY`, etc.
   - SSoT: `scripts/or_billing_policy.py`. Enforce:
     `python3 scripts/or_billing_policy.py && python3 scripts/billing_guard.py --fix-env --fix-config`
     (matrix apply + smoke_fleet both gate). Optionally push workspace allowlist:
     `python3 scripts/sync_or_billing_guardrail.py` (needs `OPENROUTER_MANAGEMENT_KEY`).
   - If SuperGrok or Claude Max OAuth is broken: **STOP**. Never “fix” via OpenRouter Claude/Grok or API keys.
5. Named bots via Kanban/cron/AIPass — never CoS `delegate_task` leaves for ops/command bots.
6. One Discord gateway: Carrier Ops on Helm only. First Watch + wings = REST outbound.
7. No mail send. Secrets never in git/chat/SOUL. Values with `=` → Doppler REST write (not CLI `KEY=value`).
8. Windows: UTF-8 no BOM; prefer `/` paths; Git Bash for `*.sh`.
9. Write `~/.hermes/carrier/HOST_ROLE.json` with `"role":"primary","platform":"windows"`.

---

# W0 — Hermes install

```powershell
# Official Windows install per https://hermes-agent.nousresearch.com/docs/
irm https://hermes-agent.nousresearch.com/install.ps1 | iex
```

```bash
hermes doctor
hermes auth list
```

Michael completes on this PC (fleet runtime, not optional long-term):

- `xai-oauth` SuperGrok
- `anthropic` Claude Max OAuth

If missing → stop and ask. **Do not** “fix” with OpenRouter Claude/Grok or API keys.

Report: Hermes version, RAM, disk, GPU name (optional), auth providers (no tokens).

---

# W1 — Clone + paths

```bash
cd "$HOME"
git clone https://github.com/mkant18/carrier_hermes.git 2>/dev/null || true
cd "$HOME/carrier_hermes"
git pull --ff-only origin main
export CARRIER_HERMES_ROOT="$HOME/carrier_hermes"
```

Create `docs/HOST_WINDOWS_PRIMARY.md` recording real paths. **Ask Michael for Windows `OBSIDIAN_VAULT_PATH`** — never copy Mac Desktop path.

```bash
mkdir -p "$HOME/.hermes/carrier"
cat > "$HOME/.hermes/carrier/HOST_ROLE.json" <<'EOF'
{
  "role": "primary",
  "platform": "windows",
  "fleet": "carrier_hermes",
  "notes": "Default runtime for bots/crons/Kanban. Mac is secondary."
}
EOF
```

`~/.hermes/.env` (non-secret lines):

```bash
CARRIER_HERMES_ROOT=C:/Users/<user>/carrier_hermes
CARRIER_HOST_ROLE=primary
OBSIDIAN_VAULT_PATH=<michael-confirmed>
```

Vault `_agent/**` tree per `integrations/aipass-mailbox.md` + IMPLEMENT paths (email, drafts, calendar, todoist, mailbox, lockbox, api_watcher, …).

---

# W2 — Doppler full pull

```bash
doppler --version || echo "install Doppler CLI"
doppler login
doppler setup --project carrier-ops --config prd
doppler secrets --project carrier-ops --config prd --only-names
```

### Pull EVERY name that exists (baseline inventory)

Discord: `DISCORD_BOT_TOKEN`, `DISCORD_FLEET_BOT_TOKEN`, `DISCORD_FIRSTWATCH_BOT_TOKEN`, app IDs, `DISCORD_GUILD_ID`, `DISCORD_CHANNEL_*`, wing tokens `CODING|OPS|KNOWLEDGE|RECON_WING_DISCORD_TOKEN` + `*_APP_ID` / `*_HOME_CHANNEL_ID` / `*_PUBLIC_KEY`, `DISCORD_AUDIT_WEBHOOK`.

APIs: `OPENROUTER_API_KEY` (may be absent), `OPENROUTER_MANAGEMENT_KEY`, `TODOIST_API_TOKEN`, `GITHUB_TOKEN`.

Google: `GOOGLE_OAUTH_*`, `GOG_KEYRING_PASSWORD`.

Meta: `OBSIDIAN_VAULT_PATH`, `DOPPLER_*`.

### Wire map (never print values)

| Secret family | Destination |
|---|---|
| OpenRouter keys | `~/.hermes/.env` |
| Todoist | default + `todoist_manager` |
| GitHub | default + Mate/Yeoman as needed |
| `DISCORD_BOT_TOKEN` (Carrier Ops) | **only** `profiles/chief_of_staff/.env` |
| First Watch | `~/.hermes/.env` as `DISCORD_FLEET_BOT_TOKEN` — **no gateway** |
| Wing tokens | `bash scripts/wire_wing_tokens.sh` |
| Google | `~/.hermes/carrier/lockbox/secrets/google_gsuite/` 0600 + wire script |
| Doppler service tokens | **only** `profiles/lockbox/.env` + `LOCKBOX_SHADOW_MODE=true` |

Verify length+prefix only via Python (never echo secrets).

Produce **present / missing / deferred** table → W3 for gaps.

---

# W3 — Create missing secrets

### Browser sub-agent OK (no MFA wall)

Spawn sub-agent with browser for:

- `OPENROUTER_API_KEY` @ https://openrouter.ai/keys — name `carrier-windows-primary`
- `OPENROUTER_MANAGEMENT_KEY` if needed
- `TODOIST_API_TOKEN`, `GITHUB_TOKEN` if session already logged in

Parent writes Doppler (REST if value contains `=`) + local 0600 `.env`. Never narrate values.

### MFA / human only — STOP

Discord Developer Portal app create/token reset — Michael pastes; you store Doppler. **Never drive portal past MFA.**

---

# W4 — BILLING HARD-LOCK (mandatory; do before trusting any bot chat)

### 4.1 Strip forbidden API keys everywhere

```bash
python3 "$CARRIER_HERMES_ROOT/scripts/billing_guard.py" --fix-env
```

This **comments out** any `ANTHROPIC_API_KEY` / `XAI_API_KEY` / `GROK_API_KEY` / related keys in `~/.hermes/.env` and every `profiles/*/.env`.

Also ensure process env does not export those keys in the shell that will run bots.

### 4.2 Default-home aliases (OAuth + cheap OR only)

On default home, set aliases consistent with `COST_MODEL.md` / matrix:

```text
smart, chief-of-staff     → xai-oauth/grok-4.5
quality, specialist-coding → anthropic/claude-sonnet-5   # OAuth Max — NOT openrouter
specialist, rote, cheap   → openrouter/deepseek/deepseek-v4-flash-0731
gemini-flash              → openrouter/google/gemini-2.5-flash-lite
lockbox / security-cheap  → openrouter/openai/gpt-oss-120b   # nocn
```

**Delete / never create** aliases:

- `openrouter/anthropic/*`
- `openrouter/x-ai/*` or any `*grok*`
- `frontier-quality` → OpenRouter Opus
- anything pointing Claude/Grok at OpenRouter

### 4.3 Refuse silent “fixes”

If SuperGrok or Claude Max OAuth is broken, **stop and tell Michael**.  
Do **not** add `ANTHROPIC_API_KEY`, `XAI_API_KEY`, or OpenRouter Claude/Grok routes.

### 4.4 Guard must pass (absolute)

```bash
python3 "$CARRIER_HERMES_ROOT/scripts/or_billing_policy.py"   # self_test OK
python3 "$CARRIER_HERMES_ROOT/scripts/billing_guard.py" --fix-env --fix-config
# expect: billing_guard: PASS — OpenRouter allowlist-only; zero Anthropic/Claude/Grok...
# optional account-level lock (management key):
python3 "$CARRIER_HERMES_ROOT/scripts/sync_or_billing_guardrail.py" || true
```

If FAIL → do not proceed to bot chats. Fix or stop.

---

# W5 — Bot homes + AIPass

```bash
bash "$CARRIER_HERMES_ROOT/scripts/install_bot_homes.sh"
mkdir -p "$HOME/.hermes/scripts"
cp -f "$CARRIER_HERMES_ROOT/scripts/"*.sh "$CARRIER_HERMES_ROOT/scripts/"*.py "$HOME/.hermes/scripts/" 2>/dev/null || true
```

Copy `skills/carrier-roster` → Helm home + global skills.  
AIPass dirs + smoke `aipass_send.py` Helm→Clerk.

---

# W6 — apply_bot_matrix + billing_guard

1. **Quit Hermes Desktop** during pin (serve clobber bug).
2. `bash "$CARRIER_HERMES_ROOT/scripts/apply_bot_matrix.sh"`
3. Script ends with `billing_guard.py --fix-env` — must exit 0.
4. Windows: if `pgrep` missing, adapt quiesce (PowerShell stop hermes serve for roster) then re-run.
5. Sample verify:

```bash
hermes -p coding_lt config get model
hermes -p email_reader config get model
hermes -p lockbox config get model
python3 "$CARRIER_HERMES_ROOT/scripts/billing_guard.py"
```

**Never strip Helm SUPER-USER tools.**

---

# W7 — OSB / Todoist / Google

Follow `integrations/obsidian-second-brain.md` with Windows vault path.  
Mirror Mac policy from `docs/PHASE_B_STATUS.md` (live Todoist/calendar, TL2 grant-gated intake) unless Michael wants PC more conservative.  
No mail send tools.

---

# W8 — Discord + crons (primary host only)

- Helm: Carrier Ops gateway + `#command`
- Wings: `wire_wing_tokens.sh`
- `gateway_guard.sh` PASS
- Crons: Vigil 5m no_agent, Ledger 10–15m no_agent, Sonar daily, Chart 2–3×/week

---

# W9 — Smokes

```bash
bash "$CARRIER_HERMES_ROOT/scripts/smoke_fleet.sh"
```

Must include **PASS `billing_guard_no_anthropic_grok_api`**.

### Acceptance checklist

- [ ] Windows `HOST_ROLE.json` primary  
- [ ] Doppler inventory complete / gaps deferred explicitly  
- [ ] OPENROUTER key present or deferred  
- [ ] **No** `ANTHROPIC_API_KEY` / `XAI_API_KEY` in any fleet `.env`  
- [ ] **No** openrouter Claude/Grok routes in any bot `config.yaml`  
- [ ] `billing_guard.py` PASS  
- [ ] Bot homes + SOULs ready  
- [ ] Matrix pins verified or honest FAIL  
- [ ] Single Discord gateway  
- [ ] LockBox ST only on lockbox + shadow  
- [ ] smoke_fleet structural PASS  
- [ ] No secrets in git  

Commit only safe docs (e.g. `docs/HOST_WINDOWS_PRIMARY.md`). Never `.env`/tokens.

---

## Out of scope

- Live SMTP send  
- Discord MFA automation  
- OpenRouter Anthropic/Grok  
- Anthropic/xAI API keys as “backup”  
- Disabling LockBox shadow without Michael  
- Full local GPU LLM (optional later)

---

## Done report format

1. Host paths  
2. Auth providers  
3. Doppler present/missing/created  
4. Browser sub-agent secret creates  
5. MFA still needed from Michael  
6. **billing_guard PASS/FAIL** (quote output)  
7. Roster count  
8. Matrix sample pins  
9. smoke_fleet block  
10. Crons  
11. Blockers  

Then 3 daily-use commands for the PC.
