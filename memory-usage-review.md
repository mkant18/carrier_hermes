# Fleet Memory Usage Review — 2026-08-26
**Task:** t_65ae612e — Review and Optimize Memory Usage
**Author:** Bosun (maintenance_lt)
**Parent task:** t_ba35b078 — Fix Crash Loop Issues in System Logs
  (Note: parent completed by local LLM / code_auditor; artifact was empty stub — hallucination pattern.
   This review is based on direct inspection of all memory stores, not the parent artifact.)

---

## Executive Summary

The fleet has 25 active per-profile MEMORY.md files plus 2 global stores. The critical resource
exhaustion risk is at the **global level** (95%+ usage). Per-profile stores are mostly under 85%
but many contain **inaccurate content** seeded by local LLM hallucinations (wrong model names,
non-existent bot references, self-referential changelog noise). The OOM/crash-loop issues flagged
in the parent task's description were traced in the prior audit (audit_report_2026-08-26.md) to
Ollama being offline — the local LLM primary config for code_auditor and patch_writer, not true
memory exhaustion.

---

## Memory Store Inventory

### CRITICAL — Global Stores (Near Cap)

| Store | Chars | Cap | Budget % | Status |
|-------|-------|-----|----------|--------|
| global MEMORY.md | 2,092 | 2,200 | **95%** | CRITICAL |
| global USER.md | 1,313 | 1,375 | **95%** | CRITICAL |

Both global stores are within ~100 chars of their hard cap. Any new fleet fact added will be
rejected. This is the primary memory resource exhaustion risk.

**Root cause:** Multiple incremental additions over time without pruning. The global MEMORY.md
contains some redundant/stale content that can be trimmed.

**Recommended trim for global MEMORY.md:**
- §1 (fleet basics) — keep, essential
- §2 (Discord apps) — keep, essential; note Hermes Handoff token needs rotation (already flagged)
- §3 (roster) — shorten; "20 bots" + marshal/git_yeoman addition note is key; rest redundant
- §4 (local LLM) — keep, high-value
- §5 (xai-oauth) — keep
- §6 (billing policy) — keep, condense slightly
- §7 (silent running) — keep
- §8 (Windows temp path) — keep

Estimated savings: ~150-200 chars from §3 condensation — brings to ~85-90% budget.

**Action required:** Human or Helm session should trim global MEMORY.md §3 (roster entry) to free
headroom. Bosun cannot write global memory stores from this session scope.

### OK — Per-Profile Stores by Size

| Profile | Chars | Cap | Budget % | Quality | Notes |
|---------|-------|-----|----------|---------|-------|
| chief_of_staff | 2,044 | 2,200 | 93% | POOR | Self-referential changelog; wrong model; non-fleet bot refs |
| maintenance_lt | 1,900 | 2,200 | 86% | GOOD | Already updated this session; accurate |
| ops_lt | 1,814 | 2,200 | 82% | GOOD | Accurate, well-structured |
| marshal | 1,777 | 2,200 | 81% | GOOD | Accurate, well-structured |
| git_yeoman | 1,701 | 2,200 | 77% | FAIR | Correct structure; stale error counts in lessons |
| code_auditor | 1,612 | 2,200 | 73% | FAIR | Correct structure; some wrong model refs |
| firstmate | 1,783 | 2,200 | 81% | POOR | Wrong model; phantom task refs in lessons |
| knowledge_lt | 1,475 | 2,200 | 67% | POOR | Non-existent bot refs (alert_central, strategy_lt, etc.) |
| repair_planner | 1,408 | 2,200 | 64% | POOR | Wrong model (llama primary); wrong facts |
| pr_reviewer | 1,192 | 2,200 | 54% | POOR | Wrong model; non-existent bot refs (code-reviewer, buildbot) |
| patch_writer | 1,084 | 2,200 | 49% | FAIR | Wrong model; otherwise OK |
| marshal (old) | 1,534 | 2,200 | 70% | STALE | Overridden by accurate version; old content from local LLM |
| Other profiles (13) | ~900-1,500 | 2,200 | <70% | MIXED | Not inspected in detail; within budget |

---

## Issue Classification

### M1 — CRITICAL: Global stores at 95% cap
**Risk:** Any new memory write will be truncated or rejected.
**Files:** `C:/Users/micha/AppData/Local/hermes/memories/MEMORY.md` (2,092/2,200)
           `C:/Users/micha/AppData/Local/hermes/memories/USER.md` (1,313/1,375)
**Fix:** Trim §3 of MEMORY.md by ~150 chars (condense roster note).
**Who fixes:** Helm (chief_of_staff) session or human. Bosun cannot write global stores.

### M2 — HIGH: chief_of_staff memory has changelog noise + wrong model
**File:** `C:/Users/micha/AppData/Local/hermes/profiles/chief_of_staff/memories/MEMORY.md`
**Issues:**
  - Last 8 lines are the local LLM's self-referential "I made the following changes:" paragraph —
    this is noise injected into the memory, not a memory fact. Wastes ~300 chars.
  - States primary model is llama3.1:8b — wrong; Helm runs on Sonnet/Anthropic.
  - "Ensure secure storage and updating of API keys" — contradicts fleet billing policy (no API keys).
**Fix:** Rewrite to match ops_lt / marshal quality. Cross-profile write — requires explicit user OK
         or done in a chief_of_staff session.

### M3 — HIGH: firstmate memory has phantom task references
**File:** `C:/Users/micha/AppData/Local/hermes/profiles/firstmate/memories/MEMORY.md`
**Issues:**
  - References `t_d977444c [[P0] Create Shipwright Discord Applicati]` as an active issue —
    this task is DONE (completed, Discord app created per prior audit). Stale lesson.
  - States primary model is llama3.1:8b — wrong (firstmate runs on Sonnet).
  - "lama3.1:8b-instruct-q4_K_M" — typo ("lama" vs "llama").
**Fix:** Update in a firstmate session or with cross_profile=True + user OK.

### M4 — MEDIUM: knowledge_lt memory references non-existent bots
**File:** `C:/Users/micha/AppData/Local/hermes/profiles/knowledge_lt/memories/MEMORY.md`
**Issues:**
  - Cites interactions with "alert_central", "strategy_lt", "ops_support", "data_archive" —
    none of these profiles exist in the carrier_hermes fleet (20-bot roster).
  - Hallucinated by local LLM during seeding.
**Fix:** Replace Interactions section with accurate fleet roster contacts.

### M5 — MEDIUM: repair_planner / pr_reviewer memories have wrong model facts
**Files:** repair_planner and pr_reviewer MEMORY.md
**Issues:** Both state primary model is llama3.1:8b — these profiles use claude-opus-4-5 primary
            (per audit P4b). The fix plan deferred the Opus cost question but the model fact
            should still be accurate.
**Fix:** Update primary model lines in those profiles' sessions.

### M6 — LOW: git_yeoman memory has stale error counts
**File:** git_yeoman MEMORY.md
**Issues:** "15x 'error_line'" and "11x, 6x issues" are log-snapshot counts from a past scan,
            not durable lessons. These will be stale within days.
**Fix:** Remove the raw counts; keep the lesson about checking agent.log for errors.

### M7 — LOW: old marshal memory seeded by local LLM still on disk
The marshal profile had two versions — the local-LLM-seeded stub was superseded by a correctly
written version. The correct version is in place. No action needed.

---

## Resource Exhaustion / OOM Root Cause Clarification

The task title references "resource exhaustion or out-of-memory errors." Per the audit report
(audit_report_2026-08-26.md P1), the actual crash-loop / OOM errors in the system logs were:

1. **Ollama service offline** — when code_auditor and patch_writer had local LLM (llama3.1:8b)
   as primary and Ollama was not running, workers crashed at model-load time with "pid not alive."
   This is NOT a memory leak or RAM exhaustion — it's a missing service endpoint.

2. **GPU VRAM** — The local_llm_safety.py guard handles thermal/VRAM protection (80°C ceiling,
   sustained 85% util cap). The local_llm_idle_watcher.py only starts HermesOllama when the PC
   is idle AND GPU is <30% utilized. No VRAM overcommit issue found.

3. **Agent memory stores** — The Hermes memory cap (2,200 chars/store) is NOT RAM; it's a
   character budget for context injection. No actual OOM errors linked to memory stores.

**Conclusion:** The OOM/crash-loop root cause was Ollama-offline + local LLM primary config.
Fix F1a/F1b (move code_auditor + patch_writer to Sonnet primary) from fix_plan_2026-08-26.md
is the correct remediation. Memory store optimization is a separate hygiene task.

---

## Actions Taken This Session

1. maintenance_lt MEMORY.md — already updated externally to accurate, well-structured content.
   No further changes needed (1,900/2,200 chars, 86%).

2. Cross-profile edits attempted but correctly blocked by soft guard. All other fixes require
   either a session under the target profile or explicit user authorization with cross_profile=True.

---

## Recommended Actions (Priority Order)

| Priority | Action | Who | File |
|----------|--------|-----|------|
| P1-CRITICAL | Trim global MEMORY.md §3 (~150 chars) | Helm session / human | global/memories/MEMORY.md |
| P1-CRITICAL | Trim global USER.md if possible | Helm session / human | global/memories/USER.md |
| P2-HIGH | Fix chief_of_staff memory (remove changelog noise, correct model) | Helm session | chief_of_staff/memories/MEMORY.md |
| P2-HIGH | Fix firstmate memory (stale task ref, wrong model, typo) | firstmate session | firstmate/memories/MEMORY.md |
| P3-MEDIUM | Fix knowledge_lt memory (remove non-existent bot refs) | knowledge_lt session | knowledge_lt/memories/MEMORY.md |
| P3-MEDIUM | Fix repair_planner memory (correct model line) | repair_planner session | repair_planner/memories/MEMORY.md |
| P3-MEDIUM | Fix pr_reviewer memory (correct model + bot refs) | pr_reviewer session | pr_reviewer/memories/MEMORY.md |
| P4-LOW | Fix git_yeoman memory (remove stale error counts) | git_yeoman session | git_yeoman/memories/MEMORY.md |

---

## Summary

No actual RAM/VRAM resource exhaustion found in fleet code. The crash-loop OOM errors from the
parent task were caused by Ollama-offline + local LLM primary config — already addressed by
fix_plan_2026-08-26.md F1a/F1b (move code_auditor/patch_writer to Sonnet primary).

The real memory-usage risk is the global Hermes context stores at 95% capacity. Per-profile
stores are within budget but several contain inaccurate local-LLM-seeded content. Remediation
requires sessions under each profile's identity (cross-profile writes are correctly blocked).
