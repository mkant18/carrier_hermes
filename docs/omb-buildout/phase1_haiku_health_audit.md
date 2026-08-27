# Phase 1A — OMB Fleet Health Audit (READ-MOSTLY, report only)

You are a subagent auditing an OpenMausBot (OMB) install on Windows. Do NOT modify any config, bots, or source files. Produce a report only.

## Facts
- Harness API: http://127.0.0.1:8799 (running). UI: http://127.0.0.1:5199.
- Data dir: C:/Users/micha/.openmausbot/ (bots.json, config.json, groups.json, events/, workspaces/)
- OMB app source (bundled JS, readable): C:/Users/micha/AppData/Local/Programs/openmausbot/resources/server/server/
- Ollama: http://127.0.0.1:11434 (WSL2 behind netsh portproxy)
- Expected fleet: 25 carrier bots (Helm, Marshal, Wrench, Mate, Yeoman, Deck, Inbox, Quill, Chronos, Tasker, Purse, Stacks, Librarian, Clerk, Chart, Sonar, Probe, Bosun, Diver, Rigger, Caulker, Surveyor, Vigil, Ledger, LockBox) + 6 rooms (Fleet Command, Coding Wing, Ops Wing, Knowledge Wing, Recon Wing, Shipwright Wing).
- Billing policy: decision tier (Helm, Marshal, Wrench, Deck, Stacks, Chart, Bosun, Rigger, Surveyor) = grok/claude subscription models; worker tier = ollama::llama3.1:8b-instruct-q4_K_M; monitor tier (Vigil, Sonar, Ledger, LockBox) = ollama::qwen2.5:7b-instruct-q4_K_M. autoApprove must be false on ALL bots.
- A fallback watchdog SHOULD be running: script C:/Users/micha/carrier_hermes/scripts/ollama_fallback_watchdog.py (check with: wmic process where "name like '%python%'" get processid,commandline  — or via powershell Get-CimInstance Win32_Process).

## Tasks (all read-only)
1. GET /api/bots — verify all 25 bots exist, list each bot's name, engine (modelSelection.instanceId), model, autoApprove, composio flags. Flag any policy violations per the tiers above.
2. GET /api/groups — verify the 6 rooms exist with correct members.
3. Check Ollama: curl http://127.0.0.1:11434/v1/models — confirm reachable via IPv4 and list models. Confirm llama3.1:8b-instruct-q4_K_M and qwen2.5:7b-instruct-q4_K_M are present.
4. Check whether ollama_fallback_watchdog.py is running as a process. Check state file ~/.openmausbot/ollama_fallback_state.json.
5. Check netsh portproxy rule exists: netsh interface portproxy show v4tov4 (works unelevated for reads). Check scheduled task OllamaWslPortproxy exists: schtasks /query /tn OllamaWslPortproxy
6. Run the billing audit: python3 "C:/Users/micha/.openmausbot/billing-audit.py" and capture output.
7. Scan the last 3 days of events/ NDJSON logs for errors: grep for "EADDRINUSE", "permission broker unavailable", "error" (case-insensitive, dedupe, count occurrences).
8. GET /api/instances — summarize engine availability (which are available/unavailable).

## Output
Write the full report to C:/Users/micha/.openmausbot/buildout/reports/phase1a_health_audit.md with sections: SUMMARY (pass/fail table), VIOLATIONS, WARNINGS, ERRORS-IN-LOGS, RECOMMENDED-FIXES (do not apply fixes). Be exhaustive — no truncation.
