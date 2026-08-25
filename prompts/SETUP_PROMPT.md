# Carrier Hermes Fleet Setup Prompt

> Paste this entire prompt into a fresh Hermes session with full tool access (yolo mode or smart approval).
> The session will build the entire chief-of-staff fleet from scratch.
> Prerequisites: OPENROUTER_API_KEY in ~/.hermes/.env, xai-oauth credential active, anthropic OAuth credential active.

---

You are setting up Michael Kanter's personal AI agent fleet called "Carrier Hermes" — a Hermes Agent implementation of the Carrier Ops chief-of-staff system. Work through each section in order. Report what you've done after each section. Do not skip steps; do not ask for confirmation between steps unless an error requires it.

Reference files are at: ~/carrier_hermes/
- README.md — system overview
- ARCHITECTURE.md — full design rationale and governance rules
- profiles/*/SOUL.md — each agent's identity and constraints

---

## SECTION 1: Verify prerequisites

Run each of these and confirm they pass before continuing:

```bash
hermes auth list
```

Required credentials:
- `anthropic` — must show `anthropic-oauth-1` or `claude_code` (Claude Max OAuth)
- `xai-oauth` — must show `device_code` (SuperGrok OAuth)
- OpenRouter key: `grep OPENROUTER_API_KEY ~/.hermes/.env`

If any credential is missing, stop and report which one is absent. Do not proceed until all three are present.

---

## SECTION 2: Set model aliases

Run these commands to wire the tier aliases:

```bash
hermes config set model.aliases.chief-of-staff xai-oauth/grok-4.5
hermes config set model.aliases.specialist openrouter/deepseek/deepseek-chat-v3-0324
hermes config set model.aliases.watcher openrouter/google/gemma-3n-e4b-it:free
hermes config set model.aliases.quality anthropic/claude-sonnet-4-6
hermes config set model.aliases.frontier-quality anthropic/claude-opus-4-8
hermes config set model.aliases.smart xai-oauth/grok-4.5
hermes config set model.aliases.cheap openrouter/meta-llama/llama-4-scout:free
```

Verify with: `hermes config get model.aliases`

---

## SECTION 3: Configure the frontier MoA preset

Run this interactively:

```bash
hermes moa configure
```

When prompted, create a preset named `frontier` with:
- Reference model 1: `openrouter` / `deepseek/deepseek-chat-v3-0324`
- Reference model 2: `openrouter` / `meta-llama/llama-4-maverick:free`
- Aggregator: `xai-oauth` / `grok-4.5`

After creation, verify with: `hermes moa list`

---

## SECTION 4: Set auxiliary model slots to cheap OpenRouter

These side-jobs (context compression, title generation, vision) should never burn subscription quota:

```bash
hermes config set model.aux_model openrouter/google/gemma-3n-e4b-it:free
hermes config set model.aux_provider openrouter
```

If those exact keys don't exist, use `hermes config edit` and add under the `model:` section:
```yaml
  aux_model: google/gemma-3n-e4b-it:free
  aux_provider: openrouter
```

---

## SECTION 5: Set fallback chain

Configure automatic fallback so if SuperGrok hits a rate limit the fleet falls back gracefully:

```bash
hermes fallback add
```

Add in order:
1. Provider: `anthropic`, Model: `claude-sonnet-4-6` (Claude Max OAuth — quality fallback)
2. Provider: `openrouter`, Model: `anthropic/claude-sonnet-4-6` (paid fallback of last resort)

Verify with: `hermes fallback list`

---

## SECTION 6: Create bot profiles

Create each profile below using `hermes profile create <name>`. After creating each one, copy its SOUL.md from ~/carrier_hermes/profiles/<name>/SOUL.md into the profile's config directory at ~/.hermes/profiles/<name>/SOUL.md.

### 6a. chief_of_staff

```bash
hermes profile create chief_of_staff
```

- Set model pin: `xai-oauth` / `grok-4.5`
- Fallback model pin: `anthropic` / `claude-opus-4-8`
- Copy SOUL: `cp ~/carrier_hermes/profiles/chief_of_staff/SOUL.md ~/.hermes/profiles/chief_of_staff/SOUL.md`
- Enable toolsets: `delegation`, `cronjob`, `discord`, `memory`, `session_search`, `todo`, `clarify`
- Enable MCP servers: `todoist`, `vercel`
- Disable toolsets: `terminal`, `file`, `browser` (Chief of Staff does not directly edit files or browse)

Set profile description (shown to other bots as its role):
```bash
hermes -p chief_of_staff profile describe "Chief of Staff. Receives all inbound requests. Classifies by complexity. Routes to specialists. Enforces the fleet constitution. Always-on gateway for Discord and Telegram."
```

### 6b. subscription_watcher

```bash
hermes profile create subscription_watcher
```

- Set model pin: `openrouter` / `google/gemma-3n-e4b-it:free`
- Copy SOUL: `cp ~/carrier_hermes/profiles/subscription_watcher/SOUL.md ~/.hermes/profiles/subscription_watcher/SOUL.md`
- Enable toolsets: `session_search`, `memory`, `discord`
- Disable ALL others (terminal, file, browser, delegation, cronjob, web, etc.)

Set description:
```bash
hermes -p subscription_watcher profile describe "Subscription Watcher. Monitors fleet for stalls, rate limit proximity, and redundant work. Runs every 5 minutes. Alert-only write capability."
```

### 6c. email_reader

```bash
hermes profile create email_reader
```

- Set model pin: `openrouter` / `deepseek/deepseek-chat-v3-0324`
- Copy SOUL: `cp ~/carrier_hermes/profiles/email_reader/SOUL.md ~/.hermes/profiles/email_reader/SOUL.md`
- Enable toolsets: `file`, `web`
- Disable: `terminal`, `browser`, `delegation`, `cronjob`, `discord`, `todoist` MCP, `memory`

Set description:
```bash
hermes -p email_reader profile describe "Email Reader. Reads and triages email. Writes to _agent/email/ only. No send capability. No Todoist. No calendar access."
```

### 6d. email_drafter

```bash
hermes profile create email_drafter
```

- Set model pin: `anthropic` / `claude-sonnet-4-6` (Claude Max OAuth — drafting quality)
- Copy SOUL: `cp ~/carrier_hermes/profiles/email_drafter/SOUL.md ~/.hermes/profiles/email_drafter/SOUL.md`
- Enable toolsets: `file`, `memory`, `skills`, `discord`
- Enable skills: load `my-writing-style` skill if available
- Disable: `terminal`, `browser`, `delegation`, `web`

Set description:
```bash
hermes -p email_drafter profile describe "Email Drafter. Produces draft email replies using Michael's writing style. Posts drafts to Discord #drafts for approval. Never sends."
```

### 6e. calendar_manager

```bash
hermes profile create calendar_manager
```

- Set model pin: `openrouter` / `deepseek/deepseek-chat-v3-0324`
- Copy SOUL: `cp ~/carrier_hermes/profiles/calendar_manager/SOUL.md ~/.hermes/profiles/calendar_manager/SOUL.md`
- Enable toolsets: `file`
- Enable MCP: `todoist`
- Disable: `terminal`, `browser`, `web`, `memory`, `discord`

Set description:
```bash
hermes -p calendar_manager profile describe "Calendar Manager. Reads calendar events and syncs to Todoist tasks. Writes to _agent/calendar/ only. No email access."
```

### 6f. vault_librarian

```bash
hermes profile create vault_librarian
```

- Set model pin: `anthropic` / `claude-sonnet-4-6` (Claude Max OAuth)
- Copy SOUL: `cp ~/carrier_hermes/profiles/vault_librarian/SOUL.md ~/.hermes/profiles/vault_librarian/SOUL.md`
- Enable toolsets: `file`, `memory`, `skills`, `web` (read-only)
- Enable skills: `obsidian` skill
- Disable: `terminal`, `browser`, `delegation`, `discord`

Set description:
```bash
hermes -p vault_librarian profile describe "Vault Librarian. Reads and queries the Obsidian knowledge base. Writes only to _agent/. Proposes but never executes structural vault changes."
```

### 6g. research_agent

```bash
hermes profile create research_agent
```

- Set model pin: `anthropic` / `claude-sonnet-4-6` (Claude Max OAuth)
- Copy SOUL: `cp ~/carrier_hermes/profiles/research_agent/SOUL.md ~/.hermes/profiles/research_agent/SOUL.md`
- Enable toolsets: `web`, `browser`, `file`, `memory`
- Disable: `terminal`, `delegation`, `discord`

Set description:
```bash
hermes -p research_agent profile describe "Research Agent. Conducts web research and produces structured reports. Writes to _agent/research/. Read-only browser use."
```

---

## SECTION 7: Wire Discord gateway for Chief of Staff

The Chief of Staff profile should receive inbound Discord messages and route the fleet.

```bash
hermes -p chief_of_staff gateway start
```

Check that Discord is enabled in the chief_of_staff profile config:
```bash
hermes -p chief_of_staff config get platforms
```

If Discord is not enabled:
```bash
hermes -p chief_of_staff config set platforms.discord.enabled true
```

The Discord bot token is shared from the default profile's credentials — confirm it's present:
```bash
grep -i discord ~/.hermes/.env | head -3
```

---

## SECTION 8: Set up Subscription Watcher cron

This is the fleet's always-on efficiency monitor. It runs on the cheapest model every 5 minutes.

```bash
hermes -p subscription_watcher cron create \
  --schedule "every 5m" \
  --name "subscription-watcher" \
  --prompt "You are the Subscription Watcher. Run your monitoring routine: (1) use session_search to find sessions active in the last 15 minutes — flag any with no new messages for 10+ min as potentially stalled; (2) check hermes monitoring for rate limit warnings — alert Discord if >70% of any tier limit; (3) check for two active sessions with overlapping task descriptions and flag redundancy; (4) append a brief entry to _agent/watcher/daily-report-$(date +%Y-%m-%d).md with your findings. Post to Discord #alerts only for critical issues (stall >15min, rate limit >90%). Keep your total response under 300 tokens."
```

Verify it's scheduled:
```bash
hermes -p subscription_watcher cron list
```

---

## SECTION 9: Create _agent/ directory structure

This is the vault write target for all agents. Create it in the Obsidian vault:

```bash
VAULT_PATH="$HOME/Desktop/Existing Folders/Second Brain"
# If vault path differs, adjust above

mkdir -p "$VAULT_PATH/_agent/email"
mkdir -p "$VAULT_PATH/_agent/drafts"
mkdir -p "$VAULT_PATH/_agent/calendar"
mkdir -p "$VAULT_PATH/_agent/research"
mkdir -p "$VAULT_PATH/_agent/watcher"
mkdir -p "$VAULT_PATH/_agent/librarian"

# Create initial state files
echo '{"last_processed_id": null, "last_run": null}' > "$VAULT_PATH/_agent/email/state.json"
echo '{"last_processed_id": null, "last_run": null}' > "$VAULT_PATH/_agent/calendar/state.json"
echo '{"completed_topics": [], "last_run": null}' > "$VAULT_PATH/_agent/research/state.json"
```

---

## SECTION 10: Smoke test

Run a brief smoke test to confirm the fleet is wired correctly:

1. Test Chief of Staff model:
```bash
hermes -p chief_of_staff chat -q "Introduce yourself in one sentence and confirm your model."
```

2. Test Subscription Watcher (trigger one run):
```bash
hermes cron run <watcher-job-id>
```
(Get job ID from `hermes -p subscription_watcher cron list`)

3. Test a specialist delegation: ask Chief of Staff to delegate a trivial research task:
```bash
hermes -p chief_of_staff chat -q "Delegate a task to the research_agent profile asking it to write one sentence about the weather to _agent/research/smoke-test.md"
```

4. Confirm model aliases resolve:
```bash
hermes chat --provider xai-oauth --model grok-4.5 -q "Say: GROK OK"
hermes chat --provider anthropic --model claude-sonnet-4-6 -q "Say: CLAUDE OK"
hermes chat --provider openrouter --model deepseek/deepseek-chat-v3-0324 -q "Say: SPECIALIST OK"
```

---

## SECTION 11: Final checklist

Report the status of each item:

- [ ] All 3 credentials present (xai-oauth, anthropic OAuth, openrouter key)
- [ ] 7 model aliases set (chief-of-staff, specialist, watcher, quality, frontier-quality, smart, cheap)
- [ ] Frontier MoA preset created with 2 references + grok-4.5 aggregator
- [ ] Aux model slots pointing to free OpenRouter model
- [ ] Fallback chain: anthropic/sonnet → openrouter/sonnet
- [ ] 7 bot profiles created with correct model pins (chief_of_staff, subscription_watcher, email_reader, email_drafter, calendar_manager, vault_librarian, research_agent)
- [ ] SOUL.md files copied into each profile directory
- [ ] Discord gateway enabled for chief_of_staff
- [ ] Subscription Watcher cron running every 5 minutes
- [ ] _agent/ directory tree created in Obsidian vault
- [ ] All 4 smoke tests passing

If any item fails, fix it before marking it complete. Report the final checklist state when done.
