# Phase 2A — Composio Pilot Integration (Yeoman + Inbox)

You are a subagent wiring Composio into OpenMausBot (OMB) as a PILOT on exactly two bots. Harness: http://127.0.0.1:8799. Data dir: C:/Users/micha/.openmausbot/. Source: C:/Users/micha/AppData/Local/Programs/openmausbot/resources/server/server/.

A `composio` skill is installed for Claude Code (from ComposioHQ/composio) — use it if helpful.

## Step 0 — Discover, don't guess
Read these source files FIRST to learn the exact config shape and API surface OMB expects:
- composio.js (Sessions API client — note how the API key is read from config, what endpoints exist under /api/... on the harness for composio, connect-link generation, toolkit enable/disable)
- config.js (config schema/saveConfig)
- connector-proxy.js and mcp-bridge.js (how the Composio MCP endpoint gets mounted into a bot's engine)
- index.js (harness HTTP routes for composio/connectors)
Document the discovered API map in your report.

## Step 1 — Wire the key
- Get key: doppler secrets get COMPOSIO_API_KEY --plain --project carrier-ops --config prd  (an ak_... key, verified valid).
- Back up config.json to config.json.bak-phase2a, then add the key in EXACTLY the shape composio.js expects (discovered in step 0). Do not remove existing keys (profile, openaiCompat).
- Restart the harness if required for config pickup: taskkill //IM OpenMausBot.exe //F then relaunch via: cmd //c start "" "C:\Users\micha\AppData\Local\Programs\openmausbot\OpenMausBot.exe" — wait and poll http://127.0.0.1:8799/api/instances until up. (Restart ONLY if config is not hot-reloaded; check saveConfig/watchers first.)
- Verify the harness reports a working Composio session (whatever health endpoint step 0 revealed).

## Step 2 — Enable pilot bots
- Find bot ids for Yeoman and Inbox in C:/Users/micha/.openmausbot/bots.json.
- PATCH http://127.0.0.1:8799/api/bots/:id {"composio": true} for those two ONLY. All other bots stay composio:false.

## Step 3 — Prove end-to-end with a no-auth toolkit
- Via the discovered harness/Composio API, enable a no-auth toolkit (e.g. HACKERNEWS or COMPOSIO_SEARCH — list toolkits with is_no_auth=true and pick one).
- Send a message to Yeoman's thread asking it to use that tool (e.g. "search hackernews for OpenMausBot"). Verify in the thread events NDJSON that a Composio MCP tool call executed and returned data. Capture the event excerpt as proof.
- NOTE: Yeoman runs ollama::llama3.1 (weak at MCP). If it fails to call the tool after 2 tries, PATCH Yeoman temporarily to {"modelSelection":{"instanceId":"claude","model":"claude-haiku-4-5"}} for the test, then RESTORE the ollama model afterwards and note this in the report (model capability finding, important for rollout planning).

## Step 4 — Generate OAuth links (human gate — do NOT try to complete OAuth)
- Generate Composio connect/auth links for toolkits: GITHUB (for Yeoman) and GMAIL (for Inbox).
- Write both URLs clearly into the report. Michael will click them himself. Do not attempt browser automation or credential entry.

## Step 5 — Guardrails
- Confirm autoApprove is still false on both pilot bots (Composio tool calls must surface approval cards).
- Run python3 "C:/Users/micha/.openmausbot/billing-audit.py" — it may WARN about composio=true on the two pilots; that is EXPECTED now. Note it; do not edit the audit script (Phase 4 owns that).

## Output
Report to C:/Users/micha/.openmausbot/buildout/reports/phase2a_composio_pilot.md: discovered API map, config change made (redact the key), restart needed y/n, pilot enablement proof, no-auth tool call proof (event excerpts), model-capability finding, the two OAuth URLs, guardrail check results, and recommended next steps for fleet-wide rollout.
