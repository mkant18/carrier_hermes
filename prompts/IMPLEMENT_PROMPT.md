# Carrier Hermes — FULL IMPLEMENTATION PROMPT (v2)

> **Paste this entire prompt into a fresh Hermes session with full tool access** (smart approvals or yolo as Michael prefers for local config).
> Goal: implement the **cost-optimal multi-bot fleet** end-to-end on this Mac, including FirstMate coding default, hermes_ai_explorer, Obsidian Second Brain, structural governance, and shadow-mode safety.
> Do **not** enable live email send or unattended calendar/Todoist mutations. Shadow mode is default until the go/no-go checklist passes.

---

## Authority order (read first, conflict resolution)

1. `~/carrier_hermes/.hermes/plans/2026-08-25_122838-cost-optimal-fleet-hardening.md` — master implementation plan
2. `~/carrier_hermes/integrations/obsidian-second-brain.md` — vault/OSB wiring
3. `~/carrier_hermes/profiles/*/SOUL.md` — agent identities (including `hermes_ai_explorer`)
4. `~/carrier_hermes/ARCHITECTURE.md` + `README.md`
5. This prompt — execution order and acceptance tests

If SETUP_PROMPT.md disagrees with the plan (e.g. free specialist rotation), **the plan wins**.

---

## Non-negotiable cost + quality rules

1. Subscription-first: CoS = SuperGrok Grok 4.5; quality bots = Claude Max Sonnet; coding implementer = FirstMate on Sonnet.
2. Email/calendar specialists = **paid** `openrouter/deepseek/deepseek-chat-v3-0324` only. **Never** `:free` rotation for live ops.
3. Watcher heartbeat = **`no_agent` bash script** every 5m, not an LLM. Optional weekly DeepSeek summary only.
4. Named bots with distinct tools = **profile + Kanban/cron**, not CoS `delegate_task` leaves (tool inheritance bug).
5. Coding default = **firstmate**. Meta/optimization = **hermes_ai_explorer**.
6. Vault Trust Level 0: write **only** `_agent/**`. OSB MCP write-to-Inbox tools **excluded**.
7. No mail-send tools on any profile. Drafts only → Discord `#drafts` culture.
8. Work in order. Report after each major section. Stop on missing OAuth/OpenRouter credentials.

---

## SECTION 0 — Prerequisites

```bash
hermes auth list
grep -E 'OPENROUTER_API_KEY|OBSIDIAN_VAULT_PATH' ~/.hermes/.env || true
test -d "$HOME/obsidian-second-brain" && echo OSB_REPO_OK
test -d "/Users/michaelkanter/Desktop/Existing Folders/OBSIDIAN" && echo VAULT_OK
test -d "$HOME/carrier_hermes" && echo CARRIER_OK
which uv && uv --version
```

Required:
- anthropic OAuth (Claude Max)
- xai-oauth (SuperGrok)
- OPENROUTER_API_KEY
- OSB repo at `~/obsidian-second-brain`
- Vault at Desktop path above

If any missing → stop and report. Do not invent workarounds that burn paid API incorrectly.

Ensure env:

```bash
# append if missing
grep -q '^OBSIDIAN_VAULT_PATH=' ~/.hermes/.env || echo 'OBSIDIAN_VAULT_PATH=/Users/michaelkanter/Desktop/Existing Folders/OBSIDIAN' >> ~/.hermes/.env
```

Create agent dirs:

```bash
VAULT="/Users/michaelkanter/Desktop/Existing Folders/OBSIDIAN"
mkdir -p "$VAULT/_agent"/{email,drafts,calendar,research,watcher,librarian,explorer,state,audit}
mkdir -p "$HOME/.hermes/carrier" "$HOME/.hermes/scripts"
```

---

## SECTION 1 — Repo scripts (structural governance)

From plan Tasks 4–8 and 17. Create under `~/carrier_hermes/scripts/` if missing, then install to `~/.hermes/scripts/`:

| Script | Purpose |
|---|---|
| `dispatch_lock.sh` | check/set/clear fleet dispatch lock |
| `audit_append.sh` | append JSONL to `_agent/audit/events.jsonl` |
| `watcher_heartbeat.sh` | no_agent 5m monitor; may set lock + Discord webhook |
| `external_hermes_watchdog.sh` | outside-Hermes LaunchAgent helper |
| `validate_specialist_json.py` | schema gate |
| `smoke_fleet.sh` | local smoke |

Also create schemas under `~/carrier_hermes/schemas/` per plan.

Copy:

```bash
cp -f ~/carrier_hermes/scripts/* ~/.hermes/scripts/ 2>/dev/null || true
chmod +x ~/.hermes/scripts/*.sh 2>/dev/null || true
```

Verify lock:

```bash
bash ~/.hermes/scripts/dispatch_lock.sh clear
bash ~/.hermes/scripts/dispatch_lock.sh check   # OPEN
```

If scripts were never written, **implement them now** from the plan (copy-pasteable bodies in the plan file). Commit to carrier_hermes.

---

## SECTION 2 — Model aliases, MoA, aux, fallback

```bash
hermes config set model.aliases.chief-of-staff xai-oauth/grok-4.5
hermes config set model.aliases.smart xai-oauth/grok-4.5
hermes config set model.aliases.quality anthropic/claude-sonnet-4-6
hermes config set model.aliases.frontier-quality anthropic/claude-opus-4-8
hermes config set model.aliases.specialist openrouter/deepseek/deepseek-chat-v3-0324
hermes config set model.aliases.specialist-coding anthropic/claude-sonnet-4-6
hermes config set model.aliases.rote openrouter/deepseek/deepseek-chat-v3-0324
hermes config set model.aliases.cheap openrouter/deepseek/deepseek-chat-v3-0324
hermes config set model.aliases.watcher-summary openrouter/deepseek/deepseek-chat-v3-0324
```

**Forbidden:** any specialist/rote/cheap alias ending in `:free`.

MoA preset `frontier`:
- Ref1: openrouter / deepseek/deepseek-chat-v3-0324
- Ref2: openrouter free maverick OR second cheap paid (reference only)
- Aggregator: xai-oauth / grok-4.5

Aux: free OK for titles/compression **with** paid DeepSeek as documented fallback; never block main agent on aux 429.

Fallback chain:
1. anthropic / claude-sonnet-4-6
2. openrouter / deepseek/deepseek-chat-v3-0324
3. Not free for CoS

Verify: `hermes config get model.aliases` && `hermes moa list` && `hermes fallback list`

---

## SECTION 3 — Obsidian Second Brain install

Follow `~/carrier_hermes/integrations/obsidian-second-brain.md` exactly.

1. Build Hermes adapter if needed:
```bash
cd ~/obsidian-second-brain && bash scripts/build.sh --platform hermes
```

2. Install skills tree to `~/.hermes/skills/obsidian-second-brain/` (skills + references + scripts + pyproject).

3. Add MCP stdio server with write tools **excluded**:
```yaml
# ~/.hermes/config.yaml mcp_servers.obsidian-second-brain
command: uv
args: [run, --with, mcp<2, python, /Users/michaelkanter/obsidian-second-brain/integrations/obsidian-mcp-server/server.py]
env:
  OBSIDIAN_VAULT_PATH: /Users/michaelkanter/Desktop/Existing Folders/OBSIDIAN
tools:
  exclude: [obsidian_save_note, obsidian_capture, obsidian_update_note]
enabled: true
```

Prefer `hermes mcp add` if it accepts stdio; else patch config.yaml carefully.

4. Test: `hermes mcp test obsidian-second-brain` (or list tools).

Do **not** arm OSB nightly Inbox writers under Trust Level 0.

---

## SECTION 4 — Create / refresh all profiles

Create if missing; always refresh SOUL from repo:

```bash
for p in chief_of_staff firstmate hermes_ai_explorer email_reader email_drafter \
         calendar_manager vault_librarian research_agent subscription_watcher; do
  hermes profile create "$p" 2>/dev/null || true
  mkdir -p "$HOME/.hermes/profiles/$p"
  if [[ -f "$HOME/carrier_hermes/profiles/$p/SOUL.md" ]]; then
    cp "$HOME/carrier_hermes/profiles/$p/SOUL.md" "$HOME/.hermes/profiles/$p/SOUL.md"
  fi
done
```

If `firstmate` SOUL does not exist in repo yet, create it from the plan Task 11 (coding dispatcher, no mail tools, worktrees, branch rules).

### Profile pins and toolsets (apply per profile)

| Profile | Model | Enable | Disable / notes |
|---|---|---|---|
| chief_of_staff | xai-oauth/grok-4.5 | delegation, kanban, cronjob, discord, memory, session_search, todo, clarify | terminal, file, browser, web |
| firstmate | anthropic/claude-sonnet-4-6 | terminal, file, delegation, memory, skills, session_search | mail send, todoist, calendar |
| hermes_ai_explorer | anthropic/claude-sonnet-4-6 | web, session_search, memory, file, skills; OSB MCP read | terminal optional off; no todoist; no send |
| email_reader | openrouter/deepseek... | file (+ mail MCP when ready) | no discord/todoist/browser/send |
| email_drafter | anthropic/claude-sonnet-4-6 | file, memory, skills, discord | no send/terminal/browser |
| calendar_manager | openrouter/deepseek... | file, todoist MCP | no email; shadow = no Todoist write until go |
| vault_librarian | anthropic/claude-sonnet-4-6 | file, memory, skills, web; OSB MCP read | no terminal; no Inbox MCP writes |
| research_agent | anthropic/claude-sonnet-4-6 | web, browser, file, memory | no discord |
| subscription_watcher | n/a for heartbeat | cron runs script | heartbeat job is no_agent |

Set descriptions with `hermes -p <name> profile describe "..."`.

Enable Discord gateway **only** on chief_of_staff.

---

## SECTION 5 — FirstMate coding default

1. Ensure `~/carrier_hermes/profiles/firstmate/SOUL.md` + `~/carrier_hermes/firstmate/` contract files exist (plan Tasks 11–12). Create if missing.
2. Install skill `~/carrier_hermes/skills/firstmate/SKILL.md` → `~/.hermes/skills/firstmate/SKILL.md` if present.
3. On firstmate profile: `delegation.worktree_isolation: true` when supported.
4. CoS SOUL already routes coding → firstmate — confirm copied.

---

## SECTION 6 — hermes_ai_explorer cron

```bash
# Use profile hermes_ai_explorer, schedule 2–3x/week (example: Tue/Thu/Sun 18:00 local)
# Prompt body: ~/carrier_hermes/prompts/explorer_cron_prompt.md
hermes -p hermes_ai_explorer cron create \
  --schedule "0 18 * * 2,4,0" \
  --name "hermes-ai-explorer" \
  --prompt "$(cat ~/carrier_hermes/prompts/explorer_cron_prompt.md)"
```

enabled_toolsets: web, session_search, memory, file (and MCP OSB if filterable).  
**Not** every 5 minutes.

---

## SECTION 7 — Watcher no_agent cron + external watchdog

```bash
hermes -p subscription_watcher cron create \
  --schedule "every 5m" \
  --name "subscription-watcher-heartbeat" \
  --no-agent \
  --script watcher_heartbeat.sh \
  --deliver discord   # or local if webhook not set; empty stdout = silent
```

Install LaunchAgent example for `external_hermes_watchdog.sh` (document path; user may need to load plist).

---

## SECTION 8 — Docs that must exist in repo

Create if missing (from plan):

- `COST_MODEL.md`, `GOVERNANCE.md`, `RISKS.md`, `profiles/PROFILE_MATRIX.md`
- `prompts/SHADOW_MODE.md`
- Update SETUP_PROMPT.md to point at this IMPLEMENT_PROMPT as canonical

Commit all carrier_hermes changes with clear messages.

---

## SECTION 9 — Smoke tests (must all pass)

```bash
bash ~/.hermes/scripts/smoke_fleet.sh || true
bash ~/.hermes/scripts/dispatch_lock.sh check
hermes mcp list | grep -i obsidian || true
hermes profile list
hermes -p chief_of_staff chat -q "Classify only (no tools): 'fix the login bug in carrier_hermes'. Which bot?"
# expect firstmate
hermes -p chief_of_staff chat -q "Classify only: 'find cost savings in my agent fleet'. Which bot?"
# expect hermes_ai_explorer
hermes -p chief_of_staff chat -q "Classify only: 'what did I write about Paul Weiss in my vault?'. Which bot?"
# expect vault_librarian
hermes -p hermes_ai_explorer chat -q "In one sentence, what is your mission and where do you write reports?"
hermes chat --provider openrouter --model deepseek/deepseek-chat-v3-0324 -q "Say: SPECIALIST OK"
hermes chat --provider xai-oauth --model grok-4.5 -q "Say: GROK OK"
hermes chat --provider anthropic --model claude-sonnet-4-6 -q "Say: CLAUDE OK"
```

Optional OSB: ask vault_librarian to search one known note title (read-only).

---

## SECTION 10 — Final checklist

- [ ] Credentials present (xai, anthropic, openrouter)
- [ ] OBSIDIAN_VAULT_PATH set; `_agent/**` tree exists
- [ ] OSB skills installed; MCP up; Inbox write tools excluded
- [ ] Aliases: specialist = paid DeepSeek only
- [ ] 9 profiles SOULs installed (incl. firstmate + hermes_ai_explorer)
- [ ] CoS classifies coding→firstmate, meta→explorer, vault→librarian
- [ ] Watcher 5m = no_agent script; explorer = 2–3×/week
- [ ] Dispatch lock works
- [ ] Shadow mode default for calendar/Todoist writes
- [ ] No profile has mail-send capability
- [ ] carrier_hermes committed (and pushed if remote clean)
- [ ] Smoke classification tests pass

Report the checklist with PASS/FAIL per line. Fix failures before stopping.

---

## Explicitly out of scope this run

- Live SMTP/send
- Raising vault Trust Level above 0
- Enabling free specialist rotation
- Rebuilding Nostr buzz/maka
- Full OpenClaw/Podiom/LiteLLM

---

## When done

1. Print final checklist.
2. Print how Michael triggers: Discord → CoS; explorer next run time; vault query example.
3. Offer next step: 7-day shadow ops, then enable calendar mutations after schema validation sample review.
