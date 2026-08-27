# Phase 1A OMB Fleet Health Audit Report
**Date**: 2026-08-27  
**Audit Type**: READ-MOSTLY (no modifications applied)  
**Status**: 🔴 CRITICAL — Multiple blocking violations detected

---

## SUMMARY

| Check | Status | Finding |
|-------|--------|---------|
| Harness API (8799) | ✅ PASS | Running and responsive |
| Bot Count | 🔴 FAIL | 26 found vs. 25 expected (1 extra bot) |
| Bot Config Compliance | 🔴 FAIL | 1 bot violates autoApprove policy (Helm=True) |
| Group Endpoint | 🔴 FAIL | GET /api/groups returns "no route" error |
| Ollama Reachability | ✅ PASS | 127.0.0.1:11434 responds |
| Ollama Models | ✅ PASS | llama3.1:8b-instruct-q4_K_M and qwen2.5:7b-instruct-q4_K_M present |
| Ollama Fallback Watchdog | ✅ PASS | Process running (PID 42496) |
| Ollama State File | ✅ PASS | ~/.openmausbot/ollama_fallback_state.json exists, ollama_was_down=false |
| netsh Portproxy Rules | ✅ PASS | 2 IPv4→IPv4 rules configured (100.87.88.30:11434, 127.0.0.1:11434 → 172.17.197.146:11434) |
| Scheduled Task | 🔴 FAIL | OllamaWslPortproxy task not found |
| Billing Policy | 🔴 FAIL | 9 decision-tier bots using wrong engine (claude instead of grok/codex) |
| Event Log Errors | 🟡 WARNING | Permission broker unavailable, Grok runtime errors detected |
| Engine Instances | 🟢 AVAILABLE | grok=available; kimi=unavailable |

---

## VIOLATIONS (10)

### 1. Helm Bot: autoApprove=True (CRITICAL)
- **Policy**: All bots must have autoApprove=false
- **Actual**: Helm has autoApprove=true
- **Impact**: Destructive actions auto-approved without user confirmation on chief-of-staff operations
- **Risk Level**: CRITICAL

### 2. Decision-Tier Bots Using Wrong Engine (9 violations)
Per billing policy, decision-tier bots should use grok/codex subscription models, NOT local claude engine.

**Violations**:
1. **Surveyor** (PR Reviewer): engine=claude, model=claude-sonnet-4-6 (WRONG ENGINE LABEL for policy check)
2. **Rigger** (Repair Planner): engine=claude, model=claude-sonnet-4-6 (WRONG ENGINE LABEL for policy check)
3. **Bosun** (Shipwright Wing Lead): engine=claude, model=claude-sonnet-4-6 (WRONG ENGINE LABEL for policy check)
4. **Chart** (Recon Wing Lead): engine=claude, model=claude-sonnet-4-6 (WRONG ENGINE LABEL for policy check)
5. **Stacks** (Knowledge Wing Lead): engine=claude, model=claude-sonnet-4-6 (WRONG ENGINE LABEL for policy check)
6. **Deck** (Ops Wing Lead): engine=claude, model=claude-sonnet-4-6 (WRONG ENGINE LABEL for policy check)
7. **Wrench** (Coding Wing Lead): engine=claude, model=claude-sonnet-4-6 (WRONG ENGINE LABEL for policy check)
8. **Marshal** (Fleet Commander): engine=claude, model=claude-sonnet-4-6 (WRONG ENGINE LABEL for policy check)
9. **Helm** (Chief of Staff): engine=claude, model=claude-sonnet-5 (WRONG ENGINE LABEL for policy check)

**Root Cause**: The bots are configured with correct subscription models (claude-sonnet-4-6, claude-sonnet-5) but the instanceId field is set to "claude" instead of "grok" or "codex", causing billing policy audits to flag them incorrectly. The actual models are subscription-based, but the routing layer is misconfigured.

**Policy Impact**: Decision bots should route through grok/codex engines per billing requirements. Current config may route through local/fallback incorrectly.

### 3. GET /api/groups Returns "no route" Error
- **Endpoint**: GET /api/groups
- **Response**: `{"error":"no route: GET /api/groups"}`
- **Expected**: 6 rooms (Fleet Command, Coding Wing, Ops Wing, Knowledge Wing, Recon Wing, Shipwright Wing) with member lists
- **Impact**: Cannot verify room structure or membership

### 4. Scheduled Task OllamaWslPortproxy Not Found
- **Expected**: Scheduled task named "OllamaWslPortproxy" to manage WSL portproxy lifecycle
- **Actual**: Task does not exist (ERROR: The system cannot find the file specified)
- **Impact**: WSL portproxy rules are configured statically but not managed by a scheduled task. If WSL or the proxy rule is reset, it will not auto-restore.

### 5. Bot Count Mismatch
- **Expected**: 25 carrier bots
- **Found**: 26 bots
- **Impact**: Roster does not match spec. Unknown if this is a duplicate or an undocumented bot.

---

## WARNINGS (3)

### 1. Permission Broker Outage Detected in Recent Logs
**Time**: 2026-08-26 ~18:08-18:12 UTC  
**Severity**: 🔴 CRITICAL  
**Evidence**:
- Event logs show: `"permission broker unavailable"` errors
- Affected: Bash, Glob, Write, AskUserQuestion (action-type tools)
- Unaffected: Read, Skill, ToolSearch (read-only tools)
- Duration: Multiple minutes (at least 4 minutes based on timestamps)

**Impact**: 
- Blocked bot-to-bot messaging and Kanban board updates
- Helm (Chief of Staff) unable to file cards or delegate tasks
- Permission-gating mechanism temporarily failed closed (rejected all actions) rather than prompting

### 2. Grok Agent Runtime Errors in Marshal Workspace
**Time**: 2026-08-26 18:08:35 to 20:53:31 UTC  
**Errors**: Multiple `"Internal error"` events from grokAgent provider  
**Affected Bot**: Marshal (Fleet Commander)  
**Pattern**: Repeated turn.completed with stopReason="rpc_error", no error message detail  
**Impact**: Fleet command operations may have been impaired during this window

### 3. Helm Watchdog State OK, But No Recent Outage Detected
**File**: ~/.openmausbot/ollama_fallback_state.json  
**Content**: `{"ollama_was_down": false, "originals": {}}`  
**Interpretation**: Ollama has NOT gone down since watchdog started (or state was reset). No fallback triggering has occurred in current session.

---

## ERRORS-IN-LOGS (Past 3 Days)

### Unique Error Patterns Found (Deduplicated)

**1. Permission Broker Unavailable (1 occurrence)**
- **Source**: Helm bot events (081c75b9-1273-4bcf-a6f6-90c19c99d7df.ndjson)
- **Message**: `"permission broker unavailable"` (in assistant text describing blocked Write/Bash/Glob/AskUserQuestion calls)
- **Date**: 2026-08-26 ~18:08 UTC
- **Classification**: System-level infrastructure failure, not application error

**2. Grok Agent Internal Error (4 occurrences)**
- **Source**: Marshal workspace (051dc7cd-9b32-4756-bd4d-1a1e79cd3db4.ndjson)
- **Type**: `runtime.error` with message="Internal error"
- **StopReason**: rpc_error (Remote Procedure Call error)
- **Timestamps**:
  - 2026-08-26 18:08:35.356-357 UTC
  - 2026-08-26 18:08:45.164-165 UTC
  - 2026-08-26 18:10:34.168-170 UTC
  - 2026-08-26 20:53:31.718-719 UTC
- **Cost**: None recorded (errors occurred before completion)
- **Classification**: Grok subscription service intermittent failures (not local)

**3. No EADDRINUSE Errors Found** ✅
**4. No Other Application Errors Found** ✅

**Summary**: 5 errors total, all infrastructure-level (permission broker + grok RPC), zero application-level bugs detected in audit scope.

---

## RECOMMENDED FIXES (Do Not Apply)

### CRITICAL (Block Production)

1. **Fix Helm autoApprove=True Violation**
   - **Action**: Set Helm's autoApprove to false in config/bots config
   - **Rationale**: Helm is chief-of-staff; all actions must be user-confirmed
   - **Effort**: 5 minutes (config edit + restart)
   - **Verification**: GET /api/bots, check Helm.autoApprove == false

2. **Restore OllamaWslPortproxy Scheduled Task**
   - **Action**: Create scheduled task to maintain WSL portproxy rule:
     - Trigger: System startup + daily (to detect resets)
     - Action: Run `netsh interface portproxy add v4tov4 listenport=11434 listenaddress=127.0.0.1 connectport=11434 connectaddress=172.17.197.146`
   - **Rationale**: Portproxy rules do not persist across WSL restart or `ipconfig /flushdns`; task ensures recovery
   - **Effort**: 10 minutes (PowerShell script + schtasks registration)
   - **Verification**: schtasks /query /tn OllamaWslPortproxy, confirm runs at startup

3. **Fix Decision-Tier Engine Routing (9 bots)**
   - **Action**: Update instanceId from "claude" to "grok" for all 9 decision-tier bots:
     - Surveyor, Rigger, Bosun, Chart, Stacks, Deck, Wrench, Marshal, Helm
   - **Rationale**: Billing policy requires decision bots to route through grok/codex engine, not claude engine
   - **Effort**: 15 minutes (update bots.json, validate with billing-audit.py)
   - **Verification**: Run C:/Users/micha/.openmausbot/billing-audit.py, all 9 should show ✅

### HIGH (Restore Visibility)

4. **Implement GET /api/groups Endpoint**
   - **Action**: Add route to OMB harness API that returns groups structure:
     ```json
     {
       "groups": [
         {"id": "...", "name": "Fleet Command", "members": ["Helm", "Marshal", ...]},
         ...6 total rooms...
       ]
     }
     ```
   - **Rationale**: Audit requires verification that 6 rooms exist with correct membership; currently no endpoint
   - **Effort**: 30 minutes (add route to harness, return groups.json data)
   - **Verification**: GET /api/groups returns 6 groups with correct bot members

5. **Clarify Bot Roster (26 vs. 25)**
   - **Action**: 
     - Run: `curl -s http://127.0.0.1:8799/api/bots | jq '.bots[] | .name' | sort`
     - Identify the extra bot (may be test bot or duplicate)
     - Either delete it or add it to expected roster spec
   - **Rationale**: Spec calls for 25 bots; unclear if 26th is intentional or stray
   - **Effort**: 5 minutes (identification only, deletion if needed)

### MEDIUM (Improve Observability)

6. **Investigate Grok Agent RPC Errors**
   - **Action**: 
     - Check Grok subscription health (https://x.ai/account, quota/rate-limit status)
     - Review Grok service logs on 2026-08-26 18:08-20:53 window
     - Correlate with any Grok API incidents
   - **Rationale**: Marshal (fleet commander) hit 4 rpc_error failures; may indicate quota exhaustion or service degradation
   - **Effort**: 15 minutes (account check + logs review)
   - **Verification**: Confirm Grok quota is not exhausted; no service incident during window

7. **Post-Mortem: Permission Broker Outage (2026-08-26 18:08-18:12)**
   - **Action**: 
     - Review OMB harness logs for permission broker crash/restart
     - Check system resource usage (memory, disk) during outage window
     - Identify why broker failed closed (rejected) vs. open (prompted)
   - **Rationale**: 4-minute outage blocked chief-of-staff operations; risk of recurrence
   - **Effort**: 30 minutes (log analysis)
   - **Deliverable**: Root cause + prevention plan (e.g., broker restart trigger, resource monitoring)

---

## ENGINE AVAILABILITY SUMMARY

**Instances** (via GET /api/instances):

| Engine | Driver | State | Version | Auth |
|--------|--------|-------|---------|------|
| Grok | grokAgent | **available** | grok 1.0.5 (5115b46bc9) [stable] | ✅ Yes (subscription) |
| Kimi | kimiAgent | **unavailable** | — | CLI not found |
| Claude | claudeAgent | [implicit, local] | — | N/A (local Ollama) |
| Codex | codexAgent | [implicit, local] | — | N/A (local Ollama) |

**Ollama Models Available**:
- ✅ llama3.1:8b-instruct-q4_K_M (required for worker bots)
- ✅ qwen2.5:7b-instruct-q4_K_M (required for monitor tier)
- ✅ qwen2.5-coder:7b-instruct-q4_K_M (available for specialty bots)
- ✅ gemma4:26b (available)
- ✅ mistral-nemo:latest (available)
- ✅ qwen2.5-7b-64k:latest (available)

---

## CONFIGURATION AUDIT

### Billing Audit Output
```
=== OMB Billing Audit ===

✅ Clerk        engine=claude       model=ollama::llama3.1:8b-instruct-q4_K_M
✅ Librarian    engine=claude       model=ollama::llama3.1:8b-instruct-q4_K_M
✅ Purse        engine=claude       model=ollama::llama3.1:8b-instruct-q4_K_M
✅ Tasker       engine=claude       model=ollama::llama3.1:8b-instruct-q4_K_M
✅ Chronos      engine=claude       model=ollama::llama3.1:8b-instruct-q4_K_M
✅ Quill        engine=claude       model=ollama::llama3.1:8b-instruct-q4_K_M
✅ Inbox        engine=claude       model=ollama::llama3.1:8b-instruct-q4_K_M
✅ Probe        engine=claude       model=ollama::llama3.1:8b-instruct-q4_K_M
✅ Sonar        engine=claude       model=ollama::llama3.1:8b-instruct-q4_K_M
🚨 Surveyor     engine=claude       model=claude-sonnet-4-6  [BAD ENGINE for decision bot: claude]
✅ Caulker      engine=claude       model=ollama::qwen2.5:7b-instruct-q4_K_M
🚨 Rigger       engine=claude       model=claude-sonnet-4-6  [BAD ENGINE for decision bot: claude]
✅ Diver        engine=claude       model=ollama::qwen2.5:7b-instruct-q4_K_M
🚨 Bosun        engine=claude       model=claude-sonnet-4-6  [BAD ENGINE for decision bot: claude]
✅ Yeoman       engine=claude       model=ollama::llama3.1:8b-instruct-q4_K_M
✅ Mate         engine=claude       model=ollama::llama3.1:8b-instruct-q4_K_M
🚨 Chart        engine=claude       model=claude-sonnet-4-6  [BAD ENGINE for decision bot: claude]
🚨 Stacks       engine=claude       model=claude-sonnet-4-6  [BAD ENGINE for decision bot: claude]
🚨 Deck         engine=claude       model=claude-sonnet-4-6  [BAD ENGINE for decision bot: claude]
🚨 Wrench       engine=claude       model=claude-sonnet-4-6  [BAD ENGINE for decision bot: claude]
✅ LockBox      engine=claude       model=ollama::llama3.1:8b-instruct-q4_K_M
✅ Ledger       engine=claude       model=ollama::llama3.1:8b-instruct-q4_K_M
✅ Vigil        engine=claude       model=ollama::llama3.1:8b-instruct-q4_K_M
🚨 Marshal      engine=claude       model=claude-sonnet-4-6  [BAD ENGINE for decision bot: claude]
🚨 Helm         engine=claude       model=claude-sonnet-5  [autoApprove=True, BAD ENGINE for decision bot: claude]

✅ openaiCompat key set (zero-model OR guard)

🚨 VIOLATIONS (9):
   Surveyor: decision bot using engine=claude (expected grok/codex)
   Rigger: decision bot using engine=claude (expected grok/codex)
   Bosun: decision bot using engine=claude (expected grok/codex)
   Chart: decision bot using engine=claude (expected grok/codex)
   Stacks: decision bot using engine=claude (expected grok/codex)
   Deck: decision bot using engine=claude (expected grok/codex)
   Wrench: decision bot using engine=claude (expected grok/codex)
   Marshal: decision bot using engine=claude (expected grok/codex)
   Helm: decision bot using engine=claude (expected grok/codex)

⚠️ WARNINGS (1):
   Helm: autoApprove=True (destructive actions auto-allowed)
```

---

## PROCESS STATUS

| Item | Status | PID | Details |
|------|--------|-----|---------|
| ollama_fallback_watchdog.py | ✅ Running | 42496 | C:\Users\micha\AppData\Local\Microsoft\WindowsApps\python3.exe ollama_fallback_watchdog.py --interval 30 |
| Harness API | ✅ Running | (varies) | http://127.0.0.1:8799 responding to GET /api/bots, /api/instances |
| Ollama | ✅ Running | (WSL) | http://127.0.0.1:11434/v1/models responds with 8 models |
| Portproxy Rules | ✅ Configured | (system) | 2 v4tov4 rules active (100.87.88.30 + 127.0.0.1 → 172.17.197.146) |

---

## NEXT STEPS

**Blocking Issues** (must fix before production operations resume):
1. ⛔ Helm autoApprove=True → set to false
2. ⛔ 9 decision bots with wrong engine (claude → grok) → update instanceId field
3. ⛔ OllamaWslPortproxy task missing → recreate scheduled task

**High-Priority** (visibility + robustness):
4. 🟠 Implement GET /api/groups endpoint
5. 🟠 Clarify 26 vs. 25 bot roster discrepancy
6. 🟠 Investigate Grok RPC errors in Marshal workspace

**Medium-Priority** (observability):
7. 🟡 Post-mortem on permission broker outage (2026-08-26 18:08-18:12)
8. 🟡 Monitor Grok subscription quota/rate-limit

---

## AUDIT COMPLETION

**Auditor**: Phase 1A Health Audit Script (read-only)  
**Run Date**: 2026-08-27  
**Scope**: OMB fleet health, config compliance, system infrastructure  
**Modifications Applied**: None (audit only)  
**Next Audit**: After fixes applied; re-run Phase 1A to verify closure

---

**Report End**
