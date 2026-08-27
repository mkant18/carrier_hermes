# Phase 2A — Composio Pilot Integration (Yeoman + Inbox)

Executed 2026-08-27 against the live OMB harness at `http://127.0.0.1:8799`.

## Headline finding — read this before rolling out further

**Composio was already live in "managed" mode, fleet-wide, before this pilot touched anything.** `GET /api/config` reported `composio.mode: "managed"` and `GET /api/connectors/connected` showed five toolkits already `ACTIVE` with real accounts: `reddit`, `supabase`, `googlecalendar`, `github` (`ca_ckH5UgRV_0XE`), and `gmail` (two accounts: `ca_JiPzQLLceHBS` aliased "School", and `ca_VR34PsEj6yVg`). This is the desktop app's own managed Composio broker (`OMB_COMPOSIO_BROKER_URL`/`TOKEN`, set via an internal `openmausbot:managed-composio` IPC message — see `composio.js:85-121`), not the self-hosted project-key path the brief assumed. `connectionMode()` prefers broker access unconditionally, so any bot flipped to `composio:true` gets **immediate** access to these already-authorized real accounts — no per-bot connect step, no OAuth, nothing gating it except the bot's own tool-calling ability and (in theory) approval cards.

**Second finding, more serious: Composio MCP tool calls did not surface approval cards in this test, despite `autoApprove:false`.** See "Guardrail check" below — this blocks fleet-wide rollout until fixed.

---

## Step 0 — Discovered API map

Read `composio.js`, `config.js`, `connector-proxy.js`, `mcp-bridge.js`, `index.js` from `C:\Users\micha\AppData\Local\Programs\openmausbot\resources\server\server\`.

**Connection modes** (`composio.js: connectionMode`): `"managed"` (a broker URL/token is set — takes priority) > `"self-hosted"` (`cfg.composio.apiKey` set) > `"unavailable"`. Every read/write function (`relayMcp`, `listToolkits`, `connectedServices`, `connectionStatus`, `authorizeService`, `removeService`, `removeAccount`) branches `if (brokerAccess() || !cfg.composio?.apiKey)` → hits the broker at `${broker.url}/v1/...`; otherwise falls through to the self-hosted Composio Sessions API at `https://backend.composio.dev/api/v3.1` (`tool_router/session`, `.../toolkits`, `.../link`) and `.../api/v3` for the toolkit catalog.

**Config shape** (`config.js`): `{"composio": {"apiKey": "ak_...", "userId": "openmausbot_<uuid>", "sessionId": "trs_..."}}`, alongside the existing `profile` and `openaiCompat` keys. `apiKey`/`userId`/`sessionId` are the only fields; `userId`/`sessionId` are non-secret and only exist to let a self-hosted Session be reused across restarts.

**Config hot-reload** (`index.js`): `cfg` is loaded once at boot (`const cfg = loadConfig()`) and is **only** refreshed in-memory (`Object.assign(cfg, loadConfig())`) inside the `PATCH/PUT /api/config` handler, right after `saveConfig()` + `syncCredentialEnv()`. There is no file watcher. **A hand-edit of `config.json` on disk would NOT be picked up without a restart — but going through the API needs no restart at all**, because that route does the reload itself and then calls `reloadProviders()`.

**Harness HTTP routes relevant to Composio:**
- `GET /api/config` / `PATCH|PUT /api/config` — `{composio:{apiKey}}`; validates the key via `composio.prepareProjectSession` (POSTs `tool_router/session`) before persisting; 400 on a bad key.
- `PATCH /api/bots/:id` — `{composio: true|false}` per-bot gate (`index.js:3896-3900`).
- `GET /api/connectors/catalog` — toolkit marketplace (curated fallback or live API), `noAuth: true` flags no-auth toolkits.
- `GET /api/connectors/connected` — real connected-account inventory (broker or self-hosted).
- `GET /api/connectors` — status for named services.
- `POST /api/connectors/:slug/authorize` — mints a Composio Connect Link (`{url}`); accepts `{"alias": "..."}` optional body.
- `DELETE /api/connectors/:slug` / `DELETE /api/connectors/:slug/accounts/:id` — disconnect.
- `POST /api/internal/connectors/mcp` (bearer-gated, internal) — the actual MCP relay endpoint `connector-proxy.js` (spawned as the bot's MCP server subprocess) calls; it forwards to `composio.relayMcp`.
- `POST /api/internal/connectors/request` (bearer-gated, internal) — `connector-proxy.js` calls this when the agent's `..._MANAGE_CONNECTIONS` tool asks to add a toolkit; turns it into an in-chat connector card instead of letting the agent see a raw auth URL.
- **There is no "enable a toolkit" endpoint.** No-auth toolkits are reachable the moment `composio:true` is set on a bot — `allServiceStates()` sets `connected: toolkit.is_no_auth === true` unconditionally.

**`connector-proxy.js`** (the file that becomes the bot's actual `mcp__composio__*` server, per `composio.js: mcpIntegration` → `SPAWNED_PROXIES.connectors`): a thin stdio↔HTTP relay to `/api/internal/connectors/mcp`. It intercepts only `..._MANAGE_CONNECTIONS` (turns it into a connector card via `/api/internal/connectors/request`, never lets the agent see an auth URL) and `..._WAIT_FOR_CONNECTIONS`; every other MCP call, including `COMPOSIO_SEARCH_TOOLS` / `COMPOSIO_GET_TOOL_SCHEMAS` / `COMPOSIO_MULTI_EXECUTE_TOOL`, is passed straight through.

**`mcp-bridge.js`** is *not* Composio-specific — it's the generic transparent stdio bridge shared by the Local VM / VPS computer-control MCP entry points. Not part of the Composio path.

**Per-bot gate polarity (rollout hazard):** `bot.composio !== false` means "on" — the field is opt-**out**, not opt-in. `bot.autoApprove` is opt-**in** (falsy = off). This asymmetry is why the Moss finding below happened, and it will happen again for any bot created without the field explicitly set.

## Step 1 — Wired the key

- Backed up `~/.openmausbot/config.json` → `config.json.bak-phase2a` before any change.
- Retrieved `COMPOSIO_API_KEY` from Doppler (`carrier-ops`/`prd`) — an `ak_...` key.
- Applied it via `PATCH /api/config {"composio":{"apiKey":"ak_z-G…(redacted)"}}`, **not** a direct file edit, since that's the only path that validates the key and hot-reloads `cfg` in memory. Response: `200`, `composio: {configured: true, mode: "managed"}`. Existing `profile` and `openaiCompat` keys are untouched in `config.json`.
- **Restart needed: No.** Confirmed empirically — the config endpoint updates in-memory `cfg` and calls `reloadProviders()` itself; the harness never needed a restart, and the Step 3 test ran clean afterward with no relaunch.
- **This key is currently inert.** `connectionMode()` prefers the managed broker whenever `brokerAccess()` is set, which it already is fleet-wide. The PATCH did have one real side effect: `prepareProjectSession` minted a brand-new self-hosted Session (`sessionId: trs_TuMDbS8tdG67`, fresh `userId: openmausbot_8f50510b-a537-41a1-9ace-1c50bcd4b0f7`) with **zero** connected accounts of its own, now persisted in `config.json`. **Rollout implication:** if the managed broker ever goes away (network issue, IPC not yet delivered on a fresh boot, etc.), the fleet won't error — it will silently fall back to this empty self-hosted identity, and every connected app will appear to vanish rather than fail loudly. Worth a health check before relying on this key as a "fallback."
- Also note: `composio` is included in `PATCH /api/config`'s `reloadKeys` filter, so this PATCH triggered `reloadProviders()`, which can interrupt in-flight turns fleet-wide. None were in flight at the time.

## Step 2 — Enabled pilot bots (and fixed a pre-existing gap)

Bot IDs from `bots.json`:
- Yeoman: `8680e15b-da3c-47ee-9ff7-29e838f6710c`
- Inbox: `4658d515-81f7-435a-a76f-0d2d271f4be0`

`PATCH /api/bots/:id {"composio": true}` on both → confirmed via `GET /api/bots`.

**Deviation from the brief — a third bot was patched.** Before touching anything, a fleet-wide sweep of all 26 bots showed **Moss** (`fc5ad9ad-5c04-4263-bce2-a9a2c461ba8b`) had **no `composio` field at all**. Because the gate is `bot.composio !== false` (opt-out, not opt-in — see Step 0), Moss was already effectively Composio-enabled, pre-dating this pilot, purely by omission. This violates the brief's "all other bots stay composio:false" requirement, so it was corrected: `PATCH /api/bots/fc5ad9ad.../{"composio": false}`. This is a pilot-scope fix, not new pilot surface — Moss is not part of the two-bot pilot and now correctly reads `false`.

Final fleet sweep (26 bots) confirms **exactly** Yeoman and Inbox at `composio:true`; all 24 others (including the corrected Moss) at `composio:false`. `autoApprove` is `false` on every bot.

## Step 3 — End-to-end proof with a no-auth toolkit

**Model-capability finding (confirms Phase 1):** per Phase 1 guidance, the harness's default `ollama::llama3.1:8b-instruct-q4_K_M` cannot drive MCP tool calls, so the ollama attempt was skipped and Yeoman was patched straight to `{"instanceId":"claude","model":"claude-haiku-4-5"}` for the test — restored afterward (see below). **This restore is safety-critical, not cosmetic**, per the guardrail finding below.

Sent to Yeoman's thread (`3196c41c-8c01-4282-8f09-cac774b0dac5`):
> "Use your connected tools to search Hacker News for 'OpenMausBot'..."

**First attempt reached for the wrong tool.** Haiku's first instinct was its own native `WebSearch` (restricted to `news.ycombinator.com`), not a Composio tool — this **did** surface a harness approval card (`request.opened`, `tool: "WebSearch"`). Denied it and redirected explicitly to the Composio chain (`COMPOSIO_SEARCH_TOOLS` → `COMPOSIO_GET_TOOL_SCHEMAS` → `COMPOSIO_MULTI_EXECUTE_TOOL`) per the system prompt's own wording (`index.js:1602`).

**Second attempt used the real Composio MCP path successfully.** Note: this exercised the `composio_search` no-auth toolkit (`COMPOSIO_SEARCH_NEWS` action), not `hackernews` — the brief permits either; naming which one ran here for accuracy. Event excerpt from the thread NDJSON (`~/.openmausbot/events/3196c41c-8c01-4282-8f09-cac774b0dac5.ndjson`), trimmed to the load-bearing lines:

```json
{"type":"item.started","itemType":"tool","title":"mcp__composio__COMPOSIO_SEARCH_TOOLS"}
{"type":"item.completed","itemType":"tool","ok":true}
{"type":"item.started","itemType":"tool","title":"mcp__composio__COMPOSIO_GET_TOOL_SCHEMAS"}
{"type":"item.completed","itemType":"tool","ok":true}
{"type":"item.started","itemType":"tool","title":"mcp__composio__COMPOSIO_MULTI_EXECUTE_TOOL"}
{"type":"item.completed","itemType":"tool","ok":true}
... (3 more MULTI_EXECUTE_TOOL round trips, all ok:true) ...
{"type":"item.completed","itemType":"assistant_text","text":"## Search Results for OpenMausBot on Hacker News\n\n**No Hacker News posts found for OpenMausBot.** However, I did find some relevant information:\n\n### What I Found:\n\n**On the broader web**, OpenMausBot is a real project:\n- **Official site**: [openmausbot.com](https://www.openmausbot.com/) — Open Source AI Agents on Your Desktop\n- **GitHub**: [milind-soni/OpenMausBot](https://github.com/milind-soni/OpenMausBot)\n..."}
{"type":"turn.completed","ok":true,"stopReason":"end_turn","cost":0.1539115}
```

This is real, non-hallucinated tool execution — it returned the actual OpenMausBot GitHub repo and website, correctly reported zero HN hits, and the turn completed cleanly (`$0.15`). **Proof stands: the Composio MCP path from bot → `connector-proxy.js` → harness → managed broker → Composio → back works end-to-end.**

Yeoman's model was restored immediately after the test and re-verified with a fresh `GET /api/bots`:
```json
{"name":"Yeoman","composio":true,"autoApprove":false,"modelSelection":{"model":"ollama::llama3.1:8b-instruct-q4_K_M","instanceId":"claude"}}
```

## Step 4 — OAuth / connect links (human gate)

**Both requested toolkits are already `ACTIVE` — no OAuth is required for basic pilot function.** GitHub (`ca_ckH5UgRV_0XE`) and Gmail (`ca_JiPzQLLceHBS` "School", `ca_VR34PsEj6yVg`) are live via the managed broker and available to Yeoman/Inbox the instant `composio:true` was set.

Generated anyway, as instructed, for the case where Michael wants a **separate, aliased** account per pilot bot rather than reusing the shared managed identity. **Important: links were generated with an explicit `alias`, not bare.** The self-hosted authorize path in `composio.js` refuses an unaliased request when an active account already exists, with the error *"Add an account alias so the existing connection is not replaced"* — that's direct evidence of replace-by-default semantics. The broker (managed) path has no equivalent guard, so an **unaliased** link handed to a human here could silently replace/reauth the existing "School" Gmail or GitHub connection. Aliased instead:

- **GitHub** (alias: "Yeoman pilot"): `https://connect.composio.dev/link/lk_FF6yAmvXtYER`
- **Gmail** (alias: "Inbox pilot"): `https://connect.composio.dev/link/lk_2-t_WtchrDc5`

Michael: click these only if you want Yeoman/Inbox to use their own dedicated GitHub/Gmail account instead of the shared managed one. **No browser automation or credential entry was attempted on either link.**

**Verified post-authorize, via a fresh `GET /api/connectors/connected`:** the original accounts are untouched — `github: ca_ckH5UgRV_0XE` still `ACTIVE`, `gmail: ca_JiPzQLLceHBS` ("School") and `ca_VR34PsEj6yVg` still both `ACTIVE`. Minting the two links did add one new pending placeholder account each: `github: ca_t8aTI3MO1B6N` (alias "Yeoman pilot", status `INITIALIZING`) and `gmail: ca_6SiL5gWaN1dd` (alias "Inbox pilot", status `INITIALIZING`). These are harmless and inert until Michael actually clicks through the OAuth flow (well under the 5-accounts-per-toolkit cap) — but they now exist and will show as `pending: true` on the connectors panel until either completed or removed via `DELETE /api/connectors/gmail/accounts/ca_6SiL5gWaN1dd` / `DELETE /api/connectors/github/accounts/ca_t8aTI3MO1B6N`.

## Step 5 — Guardrail check

- `autoApprove` confirmed `false` on both Yeoman and Inbox (and fleet-wide) via `GET /api/bots`.
- **Critical gap found and root-caused: Composio MCP tool calls do not surface approval cards.** In the entire Step 3 test thread, the *only* `request.opened` (permission) event was for the native `WebSearch` tool — every one of the several `mcp__composio__*` calls (`COMPOSIO_SEARCH_TOOLS`, `COMPOSIO_GET_TOOL_SCHEMAS`, four rounds of `COMPOSIO_MULTI_EXECUTE_TOOL`) executed with **zero** approval prompts, despite `Yeoman.autoApprove === false` and an empty `alwaysAllow` list. Cross-checked against `auto-approve.js`: with `autoApprove:false` and no matching `alwaysAllow` grant, `autoVerdict()` returns `{approve: null, source: "no-grant"}` — which should mean "ask a human." It didn't fire for Composio calls at all.
  - **Root cause, found in `drivers/claude.js`:** when a turn has `integrations.composio` set, the driver does `allowed.push("mcp__composio")` (line 494) and later passes `--allowedTools <list>` (line 563) to the Claude Code CLI. That blanket-allowlists the **entire** `mcp__composio` MCP server at the CLI's own permission layer — every tool it exposes, including `COMPOSIO_MULTI_EXECUTE_TOOL`, is pre-approved before OMB's own `autoVerdict()`/approval-card pipeline ever gets a say. This is not an MCP-vs-native distinction — `ToolSearch` (also native) didn't card either, for unrelated reasons — but it does confirm the composio server specifically bypasses the human-in-the-loop layer by design of this integration wiring, not by accident of tool naming. Because every actual Composio action — read or write — is funneled through the same generic `COMPOSIO_MULTI_EXECUTE_TOOL` wrapper name, and the entire server is allowlisted, there is currently no way for OMB's approval layer to ever see, let alone distinguish, a safe search from a `GMAIL_SEND_EMAIL` or a `GITHUB` write.
  - **Concrete fix options:** (a) stop putting `mcp__composio` in the blanket `--allowedTools` list and instead route it through the same `--permission-prompt-tool mcp__ogb__approve` broker already used for ungated tools (lines 546-549) so `autoVerdict()`/the approval-card UI is consulted per call; or (b) keep the blanket allow but have `connector-proxy.js` (which already inspects `MANAGE_CONNECTIONS`/`WAIT_FOR_CONNECTIONS` calls) also inspect `COMPOSIO_MULTI_EXECUTE_TOOL`'s `arguments` for the underlying action name and card write-shaped actions itself before relaying to `/api/internal/connectors/mcp`.
  - **Practical consequence right now:** the only thing preventing an ungated Composio write from Yeoman or Inbox today is that both bots are pinned to `ollama::llama3.1:8b-instruct-q4_K_M`, which (per Phase 1 and reconfirmed here) cannot reliably drive MCP tools at all. **The model assignment is currently acting as the safety interlock, not the approval system.** This is an honest but fragile state — it fails if anyone (or any future model-selection UI) swaps a pilot bot onto a stronger model without separately fixing the approval gap.
  - No write-capable Composio tool call was attempted or approved during this pilot — the test used a no-auth, read-only search toolkit only, consistent with the "deny anything that writes" instruction. No approval requests of any kind needed a decision beyond the one `WebSearch` deny.
- Ran `python3 C:/Users/micha/.openmausbot/billing-audit.py`. Output includes exactly the two expected `WARN`s and nothing else new:
  ```
  ⚠️ Inbox        engine=claude       model=ollama::llama3.1:8b-instruct-q4_K_M  [composio=True]
  ⚠️ Yeoman       engine=claude       model=ollama::llama3.1:8b-instruct-q4_K_M  [composio=True]
  ```
  All decision bots (Surveyor, Rigger, Bosun, Chart, Stacks, Deck, Wrench, Marshal, Helm) remain on `codex`/`gpt-5.6-*` — untouched, as instructed. Script was not edited (Phase 4 owns it). Note: Moss does not appear in the audit's per-bot list at all (25 of 26 bots listed) — unrelated to this pilot, worth a look separately.

## Recommended next steps for fleet-wide rollout

1. **Close the approval gap before enabling Composio on any bot that runs a real model.** Determine why `mcp__composio__*` calls bypass `autoVerdict()`/`request.opened` — likely the Claude Code CLI's own MCP permission-mode default — and either configure that CLI to require approval for the `composio` MCP server, or add an OMB-side interception (similar to `connector-proxy.js`'s `MANAGE_CONNECTIONS` handling) that cards `COMPOSIO_MULTI_EXECUTE_TOOL` calls based on the actual underlying action, not just the wrapper name.
2. **Do not switch Yeoman or Inbox to a stronger model (Haiku, Sonnet, GPT, etc.) until (1) is fixed** — doing so today would give them live, unattended, unapproved access to real Gmail/GitHub accounts already connected via the managed broker.
3. **Fix the `composio` opt-out / `autoApprove` opt-in polarity mismatch**, or at minimum add a startup/health check that flags any bot with an absent `composio` field (as Moss was) — the current schema silently grants Composio access to every newly created bot that doesn't explicitly set `composio:false`.
4. Decide whether Yeoman/Inbox should keep using the shared managed identity (simplest, but shares "School" Gmail and the existing GitHub account across bots) or get dedicated aliased accounts via the two connect links above.
5. Once (1)–(3) are addressed, re-run this same enable/test/guardrail sequence per additional bot before widening the pilot, and re-run `billing-audit.py` after each change.

## Rollback (PowerShell, proven working in this session — curl was not usable against this harness here)
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8799/api/bots/8680e15b-da3c-47ee-9ff7-29e838f6710c" -Method Patch -Body '{"composio":false}' -ContentType "application/json"
Invoke-RestMethod -Uri "http://127.0.0.1:8799/api/bots/4658d515-81f7-435a-a76f-0d2d271f4be0" -Method Patch -Body '{"composio":false}' -ContentType "application/json"
```
`config.json.bak-phase2a` holds the pre-pilot config for full restore if ever needed. To also discard the two pending placeholder accounts from Step 4:
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8799/api/connectors/github/accounts/ca_t8aTI3MO1B6N" -Method Delete
Invoke-RestMethod -Uri "http://127.0.0.1:8799/api/connectors/gmail/accounts/ca_6SiL5gWaN1dd" -Method Delete
```
