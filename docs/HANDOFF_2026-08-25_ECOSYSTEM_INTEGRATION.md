# ECO Mission Handoff — 2026-08-25 Ecosystem Integration Pass

- job_id: ECO-20260825-EPIC
- epic: t_1abdb103
- filled_by: firstmate (Mate) on DOC-01 t_377a0ffc
- skeleton_by: coding_lt (Wrench)
- written_at: 2026-08-25
- status: COMPLETE (docs handoff) — production enablement of deferred items still needs Helm

---

## Summary

Carrier Hermes ran ecosystem integration pass ECO-20260825 across workspace, telemetry/cost plugins, interop bridge, skills catalogs, MCP candidates, and mobile feasibility. This document is the mission handoff for Helm: what is ADOPT / DEFER / REJECT, what landed on disk as eval artifacts, and the follow-on queue.

**Hard findings this pass**

1. **hermes-workspace** installs zero-fork against vanilla Hermes 0.20.5 and sees the full BOT_MATRIX roster, but it is an **operator control plane**, not a read-only fleet HUD (Agent View create/update and domain MCP catalog are live on loopback).
2. **Plugin hard-stop before next LLM call is not achievable** on current Hermes hooks. Fleet kill switch remains Ledger `SPEND_HALT` + Vigil `DISPATCH_LOCK` + Helm preflight.
3. **AIPass + Kanban stay frozen primary coordination.** 42-evey bridge/goals/status REJECT; cost-guard concepts only as future Ledger inspiration.
4. **SkillClaw REJECT.** Official optional catalog + fleet-authored skills ADOPT; community awesome lists ADOPT-AS-DISCOVERY only.
5. **MCP:** keep OSB + Tasker Todoist; REJECT Obsidian Local REST fleet path; Consensus ADOPT-draft (OAuth first); Monarch MCP and Granola DEFER.
6. **Mobile:** no production bot enablement. Chat companions ADOPT-LATER; device-control / AGI Phone DEFER; Mercury REJECT.

Eval artifacts (local, under gitignored `_agent/coding/` on the operator machine):

| Phase | Path |
|---|---|
| WS-01 | `_agent/coding/workspace/INSTALL.md`, `SMOKE.md` |
| TEL-01 | `_agent/coding/cost/EVAL.md`, `draft_budget.yaml`, `SMOKE_PLAN.md` |
| PLG-01 | `_agent/coding/interop/BRIDGE_VS_AIPASS.md` |
| SKL-01 | `_agent/coding/skills/POLICY.md` |
| MCP-01 | `_agent/coding/mcp/MCP_CANDIDATES.md`, `SMOKE_MCP.md` |
| MOB-01 | `_agent/coding/mobile/FEASIBILITY.md` |

---

## ADOPT / DEFER / REJECT — every P0/P1/P2-class candidate

### Already decided (pre-ECO or prior Mate sorties)

| Candidate | Priority class | Decision | Source |
|---|---|---|---|
| AIPass hybrid mailbox | P0 | **ADOPT — LIVE** | integrations/aipass-mailbox.md |
| Google Workspace (Gmail + Calendar) | P0 | **ADOPT — LIVE** (ops bots; OAuth operator path) | integrations/google-workspace-personal.md / Mate t_04d794d0 |
| Obsidian Second Brain (OSB MCP + skill) | P0 | **ADOPT — LIVE** (Clerk write; others read-only) | integrations/obsidian-second-brain.md |
| Todoist MCP on Tasker | P0 | **ADOPT — LIVE** (no template import/export) | BOT_MATRIX `todoist_manager` |
| Todoist MCP on Helm | P0 | **REJECT** | Helm dispatch-only |
| Purse (`finance_reader`) Monarch via narrow terminal | P1 | **ADOPT — LIVE** | BOT_MATRIX; not as fleet MCP |
| Lt layer (coding_lt / ops_lt / knowledge_lt) | P0 | **ADOPT — LIVE** | BOT_MATRIX |
| Chart as Recon Lt | P0 | **ADOPT — LIVE** | BOT_MATRIX |
| Free `:free` model pins on specialists | P0 doctrine | **REJECT** | COST_MODEL |
| Clerk TL>0 permanent vault writes | P1 | **DEFER** — Shadow until TL + golden smoke | prompts/SHADOW_MODE.md |
| Todoist mutations (fleet PM) | P1 | **DEFER** — Shadow until TL | prompts/SHADOW_MODE.md |
| Calendar mutations Chronos | P1 | **DEFER** — Shadow until TL | prompts/SHADOW_MODE.md |

### WS-01 — hermes-workspace (Phase 1) — cards t_6fca67b3 / t_7ef67def

| Candidate | Priority | Decision | Rationale |
|---|---|---|---|
| `outsourc-e/hermes-workspace` v2.3.0 zero-fork install | P0 | **ADOPT (ops install)** | Vanilla Hermes 0.20.5; no core fork; Conductor roster matches BOT_MATRIX when `HERMES_HOME=~/.hermes` |
| Workspace as daily operator surface | P0 | **DEFER production daily-drive** | SMOKE **PARTIAL PASS**: RO fleet posture **FAIL** (POST tasks, domain MCP visible) |
| Workspace read-only / viewer mode | P0 policy | **DEFER** — needs hardening sortie | Proxy GET allowlist, dedicated viewer profile, or upstream flag — not solved by install |
| Permanent gateway `:8642` + `API_SERVER_KEY` | P0 ops | **DEFER** — ACCESS_REQUEST via LockBox | Smoke used ephemeral process env on firstmate |

### TEL-01 — Telemetry / cost plugins (Phase 2) — t_94ba0f76 / t_9b51e2a7

| Candidate | Priority | Decision | Rationale |
|---|---|---|---|
| `nujovich/hermes-telemetry` | P1 | **ADAPT / DEFER install** | Strong local telemetry + tool-gate budget; no SPEND_HALT bridge; cannot hard-stop pre-LLM |
| `42-evey` `evey-cost-guard` | P1 | **REJECT** | Soft Langfuse warnings only; new secrets; no hard stop |
| SPEND_HALT / DISPATCH_LOCK / Ledger ownership | P0 | **KEEP — unchanged** | Still the only fleet hard stop before new dispatch |
| Telemetry→SPEND_HALT bridge script | P2 | **DEFER** | Optional no_agent watcher later; Ledger still owns clear + `#alerts` |

### PLG-01 — Inter-agent bridge (Phase 3) — t_2cc289a0 / t_508cc8e3

| Candidate | Priority | Decision | Rationale |
|---|---|---|---|
| evey-bridge (full) | P1 | **REJECT** | Second coordination SoT vs AIPass + Kanban |
| evey-goals | P1 | **REJECT** | Superseded by Kanban; invisible to Helm |
| evey-status | P1 | **REJECT** | Wrong topology; dashboard dependency |
| evey-cost-guard install | P1 | **REJECT** (install) | See TEL-01 |
| evey-cost-guard analytics *concepts* for Ledger | P2 | **DEFER** | Reimplement against OpenRouter observation if Helm wants; no upstream plugin install |
| Thin adapter wrapping bridge | P1 | **REJECT** | Any translation layer is still a second path |
| AIPass replacement | P0 | **REJECT** | Frozen primary |

### SKL-01 — Skills catalogs (Phase 4) — t_8eb18474 / t_67aac972

| Candidate | Priority | Decision | Rationale |
|---|---|---|---|
| Official `hermes skills` optional catalog (117) | P0 source | **ADOPT** | Named installs only under Wrench packet |
| Built-in skills (82) | P0 | **ADOPT-CONFIG** | Scope per bot; do not re-hub-install |
| `carrier_hermes/skills/*` | P0 | **ADOPT** | Fleet-authored |
| ZeroPointRepo/awesome-hermes-skills | P1 catalog | **ADOPT-AS-DISCOVERY** | HEAD-only named lookups; never bulk install |
| 0xNyk/awesome-hermes-agent | P1 catalog | **ADOPT-AS-DISCOVERY** | Same rule |
| SkillClaw (AMAP-ML) | P1 | **REJECT** | Rewrites config; auto-evolves skills; pin-unsafe |
| Broad hubs / skill factories / unfiltered browse-install | P2 | **REJECT** | Deny list |
| P0 skills: carrier-roster, signal-lamp-discord, boatswain-new-bot | P0 | **ADOPT** (packeted) | Smoke candidate: carrier-roster → chief_of_staff only |
| P1 skills: watchers (Sonar), ast-grep (Mate), etc. | P1 | **ADOPT** under packet | See POLICY.md allowlist |
| godmode, agentmail, web-pentest (unauthz), mass install | — | **REJECT** | Safety / constitution |
| ML/creative packs, email-inbox-triage, etc. | P2+ | **DEFER** | Propose to Helm first |

### MCP-01 — MCP include/exclude (Phase 4) — Chart t_08b88b53 (+ Mate twin gated on WS)

| Candidate | Priority | Decision | bot_ids | Rationale |
|---|---|---|---|---|
| OSB `obsidian-second-brain` | P0 | **ADOPT** | Clerk write; Librarian/Stacks/Chart read-only; optional Quill People/ read | Existing fleet vault path + TL2 filters |
| Obsidian Local REST API MCP | P1 | **REJECT** (fleet) | none | Duplicates OSB; secret surface; full CRUD |
| Consensus MCP | P1 | **ADOPT (draft)** | `research_agent`, `hermes_ai_explorer` | Read-only papers; **Helm OAuth grant before prod** |
| Todoist MCP | P0 | **ADOPT keep + tighten** | `todoist_manager` only | Include/exclude tighter than prose via tools.include |
| Monarch as Hermes MCP | P1 | **DEFER / REJECT-as-MCP** | none as MCP | Keep Purse narrow terminal |
| Granola MCP | P2 | **DEFER** | none this pass | Browser OAuth only; headless bots cannot complete |
| Default desktop MCP sprawl on specialists | P0 | **REJECT inherit** | apply_bot_matrix mcp_off | Specialists must not inherit default home |

### MOB-01 — Mobile / phone (Phase 5) — t_5d1f33a9

| Candidate | Priority | Decision | Rationale |
|---|---|---|---|
| AGI Agentic Phone MCP | P2 | **DEFER** | Third-party screen/control; send-path risk; needs Helm + LockBox + new SOUL |
| hermes-android chat clients (e.g. rusty4444 / adebnar) | P2 | **ADOPT-LATER** | Operator mobility only; Tailscale; not a bot MCP |
| Hermes-Relay Play chat/manage | P2 | **ADOPT-LATER** | Best Hermes-native companion story; still human surface |
| Hermes-Relay Device Control / desktop daemon Always-On | P2 | **DEFER** | High risk; Helm unblock required |
| raulvidis-style bridge / agent phone automation | P2 | **DEFER** | Same class as device control |
| Mercury (Yene96 on-device harness) | P2 | **REJECT** | Parallel stack; send intents; immature; not Hermes gateway client |
| Any candidate weakening LockBox/HMAC | — | **REJECT** | Hard rule |

---

## BOT_MATRIX deltas this ECO docs pass

| Row | Change | Source |
|---|---|---|
| `research_agent` (Probe) | MCP note: Consensus **draft ADOPT** pending Helm OAuth (not enabled) | MCP-01 |
| `hermes_ai_explorer` (Chart) | MCP note: Consensus **draft ADOPT** pending Helm OAuth alongside OSB read-only | MCP-01 |

No other matrix rows changed by ECO phase decisions. Purse/Tasker/Lt/OSB rows were already correct. Google Workspace row wiring belongs to the separate Mate Google PR, not this docs branch.

---

## CAPABILITY_NOTES deltas

1. Machine roster note: LTs and full bot homes are live (not pre–Phase B three-home snapshot).
2. New **Ecosystem integration (2026-08-25)** section summarizing WS/TEL/PLG/SKL/MCP/MOB.
3. Tools/MCP snapshot: Consensus draft; Local REST reject; telemetry deferred.
4. Frozen open decisions: add workspace RO hardening + telemetry install gate.

---

## Integrations notes

| Integration | File | Status |
|---|---|---|
| AIPass mailbox | integrations/aipass-mailbox.md | LIVE |
| Obsidian Second Brain | integrations/obsidian-second-brain.md | LIVE |
| Google Workspace | integrations/google-workspace-personal.md | LIVE (other PR / local) |
| hermes-workspace | integrations/hermes-workspace.md | **ADOPT install / DEFER daily-drive** (RO fail) |
| hermes-telemetry | integrations/hermes-telemetry.md | **ADAPT / DEFER install** |
| Consensus MCP | integrations/mcp-consensus.md | **ADOPT draft** (OAuth gate) |

---

## Follow-on queue for Helm (max 10)

1. **Workspace RO hardening** — before daily-drive hermes-workspace: GET-only proxy or viewer profile; strip domain MCP from workspace process; close B1/B2 from SMOKE.md.
2. **LockBox ACCESS_REQUEST** — permanent gateway `API_SERVER_KEY` for `:8642` (and any workspace remote password); never commit keys.
3. **Raise Trust Level + golden smokes** — unlock Clerk permanent vault writes, Tasker real mutations, Chronos calendar mutations (SHADOW_MODE).
4. **Consensus OAuth grant** — if paper search wanted on Probe/Chart; then enable draft YAML from MCP_CANDIDATES only on those two homes.
5. **Optional hermes-telemetry pilot** — single non-specialist or Mate scratch home only after budget.yaml maps to spend-state soft/hard; no SPEND_HALT ownership transfer; no evey-cost-guard.
6. **Ledger analytics ticket (optional)** — reimplement per-model token analytics against OpenRouter observation; do not install 42-evey plugins.
7. **SKL smoke** — Wrench packet for `carrier-roster` → `chief_of_staff` only; then P0 signal-lamp / boatswain one-at-a-time.
8. **OSB matrix apply gaps** — ensure Librarian/Stacks/Chart actually have OSB read-only entries (Chart MCP_CANDIDATES §3).
9. **Mobile ADOPT-LATER** — pick one companion (Relay Play or hermes-android) over Tailscale for Michael only; no bot MCP; Device Control remains DEFER.
10. **Merge hygiene** — Wrench reviews this docs PR; Helm approves merge; do not self-merge. Parallel Google Workspace PR stays separate.

---

## Governance carried forward

- No SOUL / specialist tool-power expansion without a linked phase decision record.
- No secrets in docs or `_agent/coding` artifacts.
- No mass `hermes skills install`.
- No production mobile device-control until Helm authorizes.
- PRs from Mate are docs-only on this card; Wrench reviews; Helm merges.

---

## Open blockers (at handoff write)

| Blocker | Owner | Notes |
|---|---|---|
| Workspace RO FAIL | Helm / Mate follow-on | Blocks daily-drive ADOPT |
| API_SERVER_KEY permanent | Michael + LockBox | ACCESS_REQUEST |
| Canonical DOC parent twins PLG/MCP Mate cards may still be todo | Dispatcher | Sibling artifacts already on disk; this handoff uses those |
| Discord Manage Messages for pins | Michael | t_30ba3166 |
| Shadow TL gates | Michael | Clerk / Tasker / Chronos writes |

---

## Appendix — Card registry (ECO-20260825)

| Key | Task ID | Assignee | Role |
|---|---|---|---|
| EPIC | t_1abdb103 | coding_lt | Epic |
| WS-01 | t_6fca67b3 / t_7ef67def | firstmate | Workspace install+smoke |
| TEL-01 | t_94ba0f76 / t_9b51e2a7 | firstmate | Telemetry eval |
| PLG-01 | t_2cc289a0 / t_508cc8e3 | firstmate | Bridge vs AIPass |
| SKL-01 | t_8eb18474 / t_67aac972 | hermes_ai_explorer | Skills policy |
| MCP-01 | t_08b88b53 / t_8ba4a9be | Chart / Mate | MCP candidates |
| MOB-01 | t_5d1f33a9 | hermes_ai_explorer | Mobile feasibility |
| DOC-01 | t_377a0ffc / t_0e87548e | firstmate | This handoff + docs PR |
| DOC skeleton | t_0d748ab0 | coding_lt | Handoff framework |

---

*Mate DOC-01 — plain external English. Internal voice not used in this file.*
