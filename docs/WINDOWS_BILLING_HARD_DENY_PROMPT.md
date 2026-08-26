# Windows Hermes — paste this entire prompt

Copy everything below the line into your Windows Hermes chat (or run via `hermes chat -q`).

---

```
MISSION: Install Carrier Hermes BILLING HARD DENY on this Windows host. PERIOD FULL STOP.

HARD RULE (never violate):
- Anthropic/Claude → provider anthropic (Claude Max OAuth) ONLY. NEVER OpenRouter.
- xAI/Grok → provider xai-oauth (SuperGrok) ONLY. NEVER OpenRouter or bare xai API key.
- OpenRouter = ALLOWLIST ONLY: DeepSeek flash/chat, Gemini Flash/Lite, openai/gpt-oss-*.
- No GPT-4/5, o-series, Gemini Pro, or any expensive frontier via OpenRouter — ever.
- Manual /model switch, fallbacks, aliases, aux, background review: same rules.

WHY: OpenRouter ignored_models denylists used dated slugs; Hermes called undated
anthropic/claude-sonnet-5 and it billed. Fix is allowlist + local refuse layers.

DO THIS END-TO-END (do not stop at a plan):

1) Locate or clone carrier_hermes main:
   - Prefer existing clone (search for carrier_hermes with scripts/or_billing_policy.py).
   - Else: git clone https://github.com/mkant18/carrier_hermes.git into %USERPROFILE%\carrier_hermes
   - git checkout main && git pull origin main

2) Ensure secrets (do not print full keys):
   - %USERPROFILE%\.hermes\.env must contain OPENROUTER_API_KEY and OPENROUTER_MANAGEMENT_KEY
   - If missing, stop and tell me — do not invent keys.

3) Run installer (Git Bash or WSL bash):
   cd /path/to/carrier_hermes
   bash scripts/install_billing_hard_deny.sh
   If bash unavailable, run the Python steps manually:
   - Copy plugins/carrier-billing-guard → %USERPROFILE%\.hermes\plugins\carrier-billing-guard
   - hermes plugins enable carrier-billing-guard
   - python scripts/or_billing_policy.py
   - python scripts/billing_guard.py --fix-env --fix-config
   - python scripts/sync_or_billing_guardrail.py
   - python scripts/apply_hermes_core_billing_patches.py
   - bash scripts/apply_bot_matrix.sh   # if fleet bots exist on this box

4) Verify (must all pass; report output):
   - python scripts/or_billing_policy.py
   - python scripts/billing_guard.py
   - python scripts/sync_or_billing_guardrail.py
   - Confirm hermes plugins list shows carrier-billing-guard enabled
   - Confirm CARRIER_BILLING_HARD_DENY appears in local hermes-agent files
     (conversation_loop.py, agent_runtime_helpers.py, chat_completion_helpers.py, model_switch.py)
   - Optional live probe: OR request model=anthropic/claude-sonnet-5 must FAIL;
     deepseek/deepseek-chat-v3-0324 may succeed.

5) Restart Hermes desktop/gateway/bot sessions on this machine so the plugin loads.

6) Set a reminder/note: after every `hermes update`, re-run
   bash scripts/install_billing_hard_deny.sh
   (core patches live in the install tree and can be wiped by updates).

7) Report back with: pass/fail per step, any drift fixed, and absolute paths used.
   Do NOT weaken the allowlist. Do NOT add Claude/Grok to OpenRouter fallbacks.
```
