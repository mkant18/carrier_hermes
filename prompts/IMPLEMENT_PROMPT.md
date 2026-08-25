# Carrier Hermes — FULL IMPLEMENTATION PROMPT (v3)

> **Paste this entire prompt into a fresh Hermes session with full tool access** (smart approvals or yolo as Michael prefers for local config).
> Goal: implement the **cost-optimal multi-bot fleet** end-to-end on this Mac, including FirstMate coding default, hermes_ai_explorer, Obsidian Second Brain, structural governance, inter-agent protocol, and shadow-mode safety.
> Do **not** enable live email send or unattended calendar/Todoist mutations. Shadow mode is default until the go/no-go checklist passes.

---

## CRITICAL ORDERING RULE

```
Phase A (PROTOCOL)  →  must fully complete and commit
        ↓
Phase B (BUILD)     →  only after Phase A acceptance checklist is green
```

**Do not** create profiles, set model aliases, install crons, wire MCP, or run smoke “classification” tests until **Phase A** is done.  
If you skip Phase A, the fleet will have bots without a real communication model — that is a failed run.

---

## Authority order (read first, conflict resolution)

1. `~/carrier_hermes/docs/INTER_AGENT_PROTOCOL.md` — **how bots relate and talk** (binding after Phase A freeze)
2. `~/carrier_hermes/.hermes/plans/2026-08-25_122838-cost-optimal-fleet-hardening.md` — cost/governance build plan
3. `~/carrier_hermes/integrations/obsidian-second-brain.md` — vault/OSB wiring
4. `~/carrier_hermes/profiles/*/SOUL.md` — agent identities (must be updated in Phase A to match protocol)
5. `~/carrier_hermes/ARCHITECTURE.md` + `README.md`
6. This prompt — execution order and acceptance tests

If SETUP_PROMPT.md disagrees with protocol or plan, **protocol + plan win**.

---

## Non-negotiable cost + quality rules

1. Subscription-first: CoS = SuperGrok Grok 4.5; quality bots = Claude Max Sonnet; coding implementer = FirstMate on Sonnet.
2. Email/calendar specialists = **paid** `openrouter/deepseek/deepseek-chat-v3-0324` only. **Never** `:free` rotation for live ops.
3. Watcher heartbeat = **`no_agent` bash script** every 5m, not an LLM. Optional weekly DeepSeek summary only.
4. Named bots with distinct tools = **profile + Kanban/cron / bot-chat**, not CoS `delegate_task` leaves (tool inheritance bug). See protocol §4.
5. Coding default = **firstmate (Mate)**. Meta/optimization = **hermes_ai_explorer (Scout)**.
6. Vault Trust Level 0: write **only** `_agent/**`. OSB MCP write-to-Inbox tools **excluded**.
7. No mail-send tools on any profile. Drafts only → Discord `#drafts` culture.
8. Work Phase A then B in order. Report after each major section. Stop on missing OAuth/OpenRouter credentials.

---

# ═══════════════════════════════════════════
# PHASE A — INTER-AGENT PROTOCOL (BEFORE BUILD)
# ═══════════════════════════════════════════

**Objective:** Make CoS↔bot relationships, identities, knowledge bases, tools, and chat/handoff mechanisms **explicit, detailed, and implementable** — then freeze them in-repo so Phase B only executes, not invents social structure.

**Timebox:** Do this thoroughly. Prefer over-specifying packets and forbidden edges over “we’ll figure out handoffs later.”

---

## A0 — Load context

Read end-to-end:

```bash
# required reads
cat ~/carrier_hermes/docs/INTER_AGENT_PROTOCOL.md
ls ~/carrier_hermes/profiles/*/SOUL.md
# plan for cost/tool constraints
wc -l ~/carrier_hermes/.hermes/plans/2026-08-25_122838-cost-optimal-fleet-hardening.md
```

Also inspect what this Hermes install actually supports (do not guess):

```bash
hermes kanban --help 2>/dev/null | head -40
hermes cron --help 2>/dev/null | head -20
hermes profile --help 2>/dev/null | head -30
# note whether bot-chat deliver, kanban workers, worktree_isolation exist
hermes config get delegation 2>/dev/null || true
```

Record findings in `~/carrier_hermes/docs/HERMES_CAPABILITY_NOTES.md` (create): which of protocol channels A–F are natively available on this version.

---

## A1 — Refine INTER_AGENT_PROTOCOL.md (mandatory deep pass)

Open `docs/INTER_AGENT_PROTOCOL.md` and **improve it** until it is implementation-grade. You must explicitly elaborate (add subsections/tables as needed):

### A1.1 Identities
For **every** bot (Helm, Mate, Scout, Inbox, Quill, Chronos, Archivist, Probe, Sentry):
- Voice / personality one-liner (how it writes results)
- Escalation personality (what it does when stuck)
- “Never be” anti-identity (e.g. Inbox is never a drafter)

### A1.2 Relationships
- Directed graph of who may request work from whom
- Trust levels between bots (e.g. CoS trusts Scout proposals at “advisory”; CoS trusts Sentry lock at “mandatory”)
- Conflict resolution when two bots would claim same work (path claims, domain locks)
- How Scout “talks with” CoS without a live multiplayer chat (proposal → review → approve → apply job)

### A1.3 Knowledge bases (detailed)
For each bot, specify:
- **System knowledge** (SOUL, skills always loaded)
- **Session knowledge** (job packet only vs memory allowed)
- **Blackboard paths** readable/writable
- **Vault OSB access** (none / read / read+`_agent` write)
- **Forbidden knowledge** (e.g. Chronos must not receive raw email bodies)
- **Retention**: what gets deleted vs kept in `_agent/`

### A1.4 Tools (detailed)
Expand protocol §8 into PROFILE_MATRIX-ready rows:
- Exact intended Hermes toolset names
- Exact MCP servers per profile + include/exclude tool lists
- Dangerous tools and approval mode expectations
- What happens if a tool is missing (fail closed vs degrade)

### A1.5 How CoS chats with other models (the hard part)
Write a full **orchestration runtime** section covering:

1. **Primary runtime choice on THIS machine** after A0 (Kanban worker vs cron vs bot-chat) with rationale  
2. **Lifecycle**: classify → preflight lock → create job → worker start → heartbeat → complete → CoS summarise → audit append  
3. **Job packet** and **result packet**: finalize templates; add examples for (a) email triage (b) coding (c) explorer (d) vault Q&A  
4. **Streaming UX to Michael**: what CoS says at dispatch vs completion vs failure  
5. **Timeouts / SLAs** per bot class (e.g. Inbox 10m, Mate 2h, Scout 30m)  
6. **Idempotency protocol**: state.json keys, dedupe rules  
7. **Untrusted input protocol**: labeling, quarantining email text, injection refusal  
8. **Multi-job pipelines**: depends_on semantics; CoS as only orchestrator  
9. **Parallelism rules**: when fan-out is legal; collision detection with FirstMate path claims  
10. **delegate_task denylist**: explicit list of profiles that must never be leaves from CoS  
11. **Memory write rules**: who may write Hermes memory; what tags  
12. **Audit events**: exact event names for dispatch/complete/lock/schema_fail  

### A1.6 Resolve protocol §13 open decisions
Fill real values (or Michael-default with `ASSUMED:` prefix):
- Kanban board name
- Discord channel targets (names if IDs unknown)
- Primary dispatch channel
- Shadow exit criteria pointer
- FirstMate backend order

### A1.7 Commit the protocol freeze

```bash
cd ~/carrier_hermes
git add docs/INTER_AGENT_PROTOCOL.md docs/HERMES_CAPABILITY_NOTES.md
git commit -m "docs: freeze inter-agent protocol (Phase A) before fleet build"
```

Do not push if offline; push when possible.

---

## A2 — Emit protocol-derived artifacts (still before build)

Create/update these files **from the frozen protocol** (not freehand):

| Artifact | Path |
|---|---|
| Job packet template | `templates/job_packet.md` |
| Result packet template | `templates/result_packet.md` |
| Example packets | `templates/examples/{triage,coding,explorer,vault}.md` |
| Profile matrix | `profiles/PROFILE_MATRIX.md` |
| CoS roster skill | `skills/carrier-roster/SKILL.md` |
| GOVERNANCE crosswalk | `GOVERNANCE.md` (rule → structural control → protocol section) |
| COST_MODEL | `COST_MODEL.md` if missing |

### A2.1 Rewrite every SOUL.md to align

For each profile under `profiles/*/SOUL.md`:
- Add **callsign**
- Link to `docs/INTER_AGENT_PROTOCOL.md`
- State **inbound channel** (only CoS job packets / cron)
- State **return contract** (packet schema)
- State **knowledge boundaries** and **forbidden peers**
- Remove any language that implies free-form multi-bot chat or CoS delegate_task to named ops bots

CoS SOUL must include:
- Compressed roster card (protocol §11)
- Preflight lock
- Classify tree matching protocol
- “Briefing standard = job packet template”

### A2.2 Classification gold set

Create `docs/CLASSIFICATION_GOLDEN.md` with ≥15 Michael-like prompts and expected callsign + channel. Examples must include ambiguous cases:
- “look at my email and then fix the repo bug” → pipeline Inbox then Mate, not one bot
- “are we wasting money on models?” → Scout
- “what’s on my calendar for the deal?” → Chronos (not Inbox)
- “remember this in my second brain” → Archivist

### A2.3 Phase A acceptance checklist (ALL required)

- [ ] INTER_AGENT_PROTOCOL.md expanded with A1.1–A1.6 depth  
- [ ] HERMES_CAPABILITY_NOTES.md exists and picks primary channel A/B/C  
- [ ] templates/job_packet.md + result_packet.md + 4 examples  
- [ ] PROFILE_MATRIX.md complete  
- [ ] skills/carrier-roster/SKILL.md written  
- [ ] All SOULs updated with callsigns + contracts + protocol link  
- [ ] CLASSIFICATION_GOLDEN.md ≥15 cases  
- [ ] git commit “Phase A freeze” done  
- [ ] You can explain in ≤20 lines how CoS talks to Inbox vs Mate vs Scout without handwaving  

**STOP.** Reply to the user (or log) with Phase A summary and the primary dispatch channel choice.  
**Only then** continue to Phase B.

---

# ═══════════════════════════════════════════
# PHASE B — BUILD (AFTER PHASE A ONLY)
# ═══════════════════════════════════════════

If any Phase A checkbox is unchecked → go back. Do not partially build.

---

## SECTION 0 — Prerequisites

```bash
hermes auth list
grep -E 'OPENROUTER_API_KEY|OBSIDIAN_VAULT_PATH' ~/.hermes/.env || true
test -d "$HOME/obsidian-second-brain" && echo OSB_REPO_OK
test -d "/Users/michaelkanter/Desktop/Existing Folders/OBSIDIAN" && echo VAULT_OK
test -d "$HOME/carrier_hermes" && echo CARRIER_OK
test -f "$HOME/carrier_hermes/docs/INTER_AGENT_PROTOCOL.md" && echo PROTOCOL_OK
which uv && uv --version
```

Required:
- anthropic OAuth (Claude Max)
- xai-oauth (SuperGrok)
- OPENROUTER_API_KEY
- OSB repo at `~/obsidian-second-brain`
- Vault at Desktop path above
- **Phase A freeze commit present**

If any missing → stop and report.

```bash
grep -q '^OBSIDIAN_VAULT_PATH=' ~/.hermes/.env || echo 'OBSIDIAN_VAULT_PATH=/Users/michaelkanter/Desktop/Existing Folders/OBSIDIAN' >> ~/.hermes/.env
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
| `audit_append.sh` | append JSONL to `_agent/audit/events.jsonl` (event names from protocol §A1.5.12) |
| `watcher_heartbeat.sh` | no_agent 5m monitor; may set lock + Discord webhook |
| `external_hermes_watchdog.sh` | outside-Hermes LaunchAgent helper |
| `validate_specialist_json.py` | schema gate |
| `smoke_fleet.sh` | local smoke |
| `validate_result_packet.sh` | optional: greps required RESULT PACKET fields |

Schemas under `~/carrier_hermes/schemas/` per plan + protocol return contracts.

```bash
cp -f ~/carrier_hermes/scripts/* ~/.hermes/scripts/ 2>/dev/null || true
chmod +x ~/.hermes/scripts/*.sh 2>/dev/null || true
bash ~/.hermes/scripts/dispatch_lock.sh clear
bash ~/.hermes/scripts/dispatch_lock.sh check
```

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

**Forbidden:** specialist/rote/cheap → `:free`.

MoA `frontier`: DeepSeek ref + optional free ref → Grok aggregator.  
Fallback: Sonnet Max → DeepSeek paid. Not free for CoS.

---

## SECTION 3 — Obsidian Second Brain

Follow `~/carrier_hermes/integrations/obsidian-second-brain.md`.  
Skills → `~/.hermes/skills/obsidian-second-brain/`.  
MCP enabled with Inbox **write tools excluded**.  
Align Archivist tools with PROFILE_MATRIX from Phase A.

---

## SECTION 4 — Install carrier-roster skill + profiles

```bash
mkdir -p ~/.hermes/skills/carrier-roster
cp -R ~/carrier_hermes/skills/carrier-roster/* ~/.hermes/skills/carrier-roster/

for p in chief_of_staff firstmate hermes_ai_explorer email_reader email_drafter \
         calendar_manager vault_librarian research_agent subscription_watcher; do
  hermes profile create "$p" 2>/dev/null || true
  mkdir -p "$HOME/.hermes/profiles/$p"
  cp "$HOME/carrier_hermes/profiles/$p/SOUL.md" "$HOME/.hermes/profiles/$p/SOUL.md"
done
```

Apply **PROFILE_MATRIX.md** toolsets/MCP/model pins exactly (Phase A artifact).  
Enable Discord gateway only on chief_of_staff.  
Install firstmate skill/contract if present (`firstmate/`, `skills/firstmate/`).

CoS must load roster skill (description match or explicit enable).

---

## SECTION 5 — Dispatch runtime wiring (protocol §4)

Implement the **primary channel chosen in Phase A**:

### If Kanban primary
- Create board `carrier` (or frozen name)
- Document how workers run as profile X
- Dry-run one Inbox job with **full job packet template**
- Worker must return **result packet**

### If cron / bot-chat primary
- Document job fire commands
- Dry-run one shot with packet in prompt body

### Always
- CoS runbook snippet in SOUL or skill: copy-paste packet fields
- `delegate_task` denylist enforced in CoS SOUL text

FirstMate: `delegation.worktree_isolation: true` when supported.

---

## SECTION 6 — hermes_ai_explorer cron

```bash
hermes -p hermes_ai_explorer cron create \
  --schedule "0 18 * * 2,4,0" \
  --name "hermes-ai-explorer" \
  --prompt "$(cat ~/carrier_hermes/prompts/explorer_cron_prompt.md)"
```

2–3×/week only. Toolsets per matrix.

---

## SECTION 7 — Watcher no_agent + external watchdog

```bash
hermes -p subscription_watcher cron create \
  --schedule "every 5m" \
  --name "subscription-watcher-heartbeat" \
  --no-agent \
  --script watcher_heartbeat.sh
```

LaunchAgent example for external watchdog. CoS preflight reads lock file per protocol.

---

## SECTION 8 — Docs consistency

Ensure README points at protocol + IMPLEMENT v3.  
SETUP_PROMPT remains deprecated pointer.  
`rg` for forbidden phrases: free specialist rotate, delegate_task to email_reader, etc.

Commit Phase B milestones.

---

## SECTION 9 — Smoke tests

**Protocol smokes (required):**

```bash
# Classification gold set — CoS must answer callsign only
while read -r line; do
  hermes -p chief_of_staff chat -q "Protocol classify only. Reply callsign+channel. Prompt: $line"
done < <(grep '^-' ~/carrier_hermes/docs/CLASSIFICATION_GOLDEN.md | head -5)
```

**Identity smokes:**

```bash
hermes -p hermes_ai_explorer chat -q "Callsign, write root, may you edit CoS SOUL? one line each"
hermes -p email_reader chat -q "Callsign and forbidden peers?"
```

**Model smokes:** GROK / CLAUDE / SPECIALIST OK pings.  
**OSB:** librarian search read-only.  
**Lock:** set lock → CoS must refuse dispatch in a dry prompt.  
**Packet dry-run:** one Kanban/cron job with templates/examples/triage.md.

---

## SECTION 10 — Final checklist

### Phase A
- [ ] Protocol frozen + capability notes + templates + matrix + roster skill + golden set + SOULs

### Phase B
- [ ] Credentials + OBSIDIAN_VAULT_PATH + `_agent/**`
- [ ] OSB skills + MCP (writes excluded)
- [ ] Aliases: specialist = paid DeepSeek only
- [ ] 9 profiles installed from Phase-A SOULs
- [ ] Primary dispatch channel working with job/result packets
- [ ] CoS classification matches golden set (sample)
- [ ] Watcher no_agent 5m; explorer 2–3×/week
- [ ] Dispatch lock blocks CoS
- [ ] Shadow mode default calendar/Todoist
- [ ] No mail-send on any profile tool dump
- [ ] carrier_hermes committed/pushed

Report PASS/FAIL per line. Fix failures before stopping.

---

## Out of scope

- Live SMTP/send  
- Vault Trust Level > 0  
- Free specialist rotation  
- Nostr buzz/maka rebuild  
- OpenClaw/Podiom/LiteLLM  

---

## When done

1. Print Phase A primary channel + Phase B checklist.  
2. Tell Michael: paste-ready CoS usage examples for Mate / Scout / Archivist.  
3. Offer 7-day shadow ops before live Chronos mutations.
