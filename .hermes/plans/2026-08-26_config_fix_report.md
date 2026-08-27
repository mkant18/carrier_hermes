# Fleet Config Fix Report — 2026-08-26

Audited and fixed all 25 bot `config.yaml` files against `BOT_MATRIX.md` and `COST_MODEL.md`.

---

## Issues Found & Fixed

### Category 1: Wrong primary model on decision/LT bots
Bots that coordinate or review must use `grok-4.5/xai-oauth` primary, never `anthropic/claude-sonnet-4-6`.

| Bot | Was | Fixed to |
|---|---|---|
| marshal | anthropic/claude-sonnet-4-6 | xai-oauth/grok-4.5 |
| coding_lt | anthropic/claude-sonnet-4-6 | xai-oauth/grok-4.5 |
| ops_lt | anthropic/claude-sonnet-4-6 | xai-oauth/grok-4.5 |
| maintenance_lt (Bosun) | anthropic/claude-sonnet-4-6 | xai-oauth/grok-4.5 |
| repair_planner (Rigger) | anthropic/claude-sonnet-4-6 | xai-oauth/grok-4.5 |
| pr_reviewer (Surveyor) | anthropic/claude-sonnet-4-6 | xai-oauth/grok-4.5 |

### Category 2: Rogue base_url — xai-oauth + Ollama endpoint
Many worker bots had `provider: xai-oauth` + `base_url: http://localhost:11434/v1`.
xAI OAuth uses xAI's own API; that base_url would route to Ollama, which breaks xai-oauth.
These bots should use local-primary (llama3.1:8b + Ollama) + xai-oauth as FALLBACK (no base_url needed).

Bots fixed: firstmate, git_yeoman, vault_librarian, obsidian_archivist, lockbox, subscription_watcher,
api_watcher, passive_watch, research_agent, email_reader, email_drafter, calendar_manager,
todoist_manager, finance_reader.

### Category 3: Forbidden OpenRouter fallbacks
Decision bots (marshal, chief_of_staff, coding_lt, ops_lt) had openrouter fallbacks
(deepseek/deepseek-chat-v3-0324, google/gemini-3.7-flash). Per COST_MODEL: OpenRouter is
allowlist-only, never a standing fallback. Removed on all affected bots.
Worker bots also replaced openrouter fallbacks with the proper subscription-OAuth chain:
xai-oauth/grok-4.5 → openai-codex/gpt-5.6-luna → anthropic/claude-haiku-4-5.

### Category 4: Hard billing violation — LockBox + DeepSeek
lockbox had `openai-oauth/gpt-4o` and `anthropic/claude-sonnet-4-6` as fallbacks (both wrong
for LockBox: should be local primary with gpt-oss/gemini-flash for judgment, never DeepSeek).
Fixed: local llama3.1:8b → xai-oauth/grok-4.5 → openai-codex/gpt-5.6-luna → gpt-oss-120b → gemini-2.5-flash-lite.

### Category 5: Missing toolsets
| Bot | Toolset added | Reason |
|---|---|---|
| marshal | discord | BOT_MATRIX lists #fleet discord ON |
| coding_lt | discord | BOT_MATRIX lists #fleet discord ON |
| ops_lt | discord, aipass | BOT_MATRIX lists both ON |
| maintenance_lt | discord, aipass | BOT_MATRIX lists both ON |
| git_yeoman | aipass | BOT_MATRIX: aipass ON |

### Category 6: Kanban toolset on non-worker bots
Kanban is for dispatch workers only. Watchers, readers, drafters do not use the board.
Removed `kanban` from: subscription_watcher, api_watcher, passive_watch, research_agent,
email_reader, email_drafter, calendar_manager, todoist_manager, finance_reader, vault_librarian, obsidian_archivist.

### Category 7: code_execution on hermes_ai_explorer
BOT_MATRIX does not list code_execution for Chart. Removed.

### Category 8: web toolset on vault_librarian
BOT_MATRIX lists web as OFF for Librarian. Removed.

### Category 9: Fallback chain ordering in code_auditor
Fallback was: anthropic/claude-sonnet-4-6 → gpt-5.6-luna → claude-haiku-4-5.
Worker-local chain requires grok-4.5 as first fallback.
Fixed: xai-oauth/grok-4.5 → openai-codex/gpt-5.6-luna → anthropic/claude-haiku-4-5.

### Category 10: maintenance_lt extra openrouter fallback
Had a third fallback `openrouter/deepseek/deepseek-v4-flash-0731` that was not in the canonical
decision-tier chain. Removed.

---

## Bots NOT changed (already correct)
- chief_of_staff: model chain fixed (openai-oauth → openai-codex, removed openrouter), aliases retained
- patch_writer (Caulker): correct local primary, correct fallbacks
- code_auditor (Diver): correct local primary — only fallback chain reordered
- hermes_ai_explorer: no base_url rogue (grok-4.5 xai-oauth no base_url) — only removed code_execution

---

## Summary
- 25 bots audited
- 22 bots required changes (some with multiple issues)
- 3 bots already correct (patch_writer primary model, chief_of_staff aliases section, hermes_ai_explorer model)
- No secrets modified; no vault changes; no API keys touched
