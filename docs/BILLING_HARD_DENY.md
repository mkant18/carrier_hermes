# Billing HARD DENY — OpenRouter must never carry Claude / Grok / OpenAI frontier

**PERIOD. FULL STOP.**

| Family | Allowed path | Forbidden |
|--------|--------------|-----------|
| Claude / Anthropic | `provider: anthropic` (Claude Max OAuth) only | Any OpenRouter / metered aggregator route |
| Grok / xAI | `provider: xai-oauth` (SuperGrok) only | OpenRouter, bare `xai` API key |
| OpenAI / ChatGPT Codex | `provider: openai-codex` (ChatGPT/Codex OAuth) only | OpenAI API keys, bare `openai`/`openai-api`, OpenRouter GPT-4/5/o-series |
| OpenRouter | Allowlist only: DeepSeek flash/chat, Gemini Flash·Lite, `gpt-oss` | Everything else (GPT-4/5, Gemini Pro, …) |

## Why denylists failed before

OpenRouter `ignored_models` used **dated** slugs (`anthropic/claude-sonnet-5-20260630`).  
Hermes requested **undated** `anthropic/claude-sonnet-5` with `allowed_models: null` → call billed.

**Fix:** workspace **allowlist** of cheap models only + local Hermes refuse layers.

## Install (Mac or Windows)

From a clone of this repo:

```bash
# Git Bash on Windows or terminal on Mac
cd ~/carrier_hermes   # or your clone path
git pull origin main
bash scripts/install_billing_hard_deny.sh
```

Requires:

- `OPENROUTER_API_KEY` and `OPENROUTER_MANAGEMENT_KEY` in `~/.hermes/.env` (Windows: `%USERPROFILE%\.hermes\.env`)
- `python3` + PyYAML
- Hermes installed

Then **restart** Hermes desktop / gateway / bot sessions.

After every `hermes update`, re-run:

```bash
bash scripts/install_billing_hard_deny.sh
```

## Verify

```bash
python3 scripts/or_billing_policy.py
python3 scripts/billing_guard.py
python3 scripts/sync_or_billing_guardrail.py
```

Optional live OR probe (uses a few DeepSeek tokens):

```bash
# Claude must fail; DeepSeek may succeed
python3 - <<'PY'
import json, os, urllib.request, urllib.error
from pathlib import Path
def env():
    e=dict(os.environ)
    p=Path.home()/'.hermes'/'.env'
    if p.exists():
        for line in p.read_text().splitlines():
            if '=' in line and not line.strip().startswith('#'):
                k,v=line.split('=',1); e.setdefault(k.strip(),v.strip().strip('"'))
    return e
E=env(); k=E['OPENROUTER_API_KEY']
for model in ['anthropic/claude-sonnet-5','openai/gpt-4o','deepseek/deepseek-chat-v3-0324']:
    body=json.dumps({'model':model,'messages':[{'role':'user','content':'hi'}],'max_tokens':1}).encode()
    r=urllib.request.Request('https://openrouter.ai/api/v1/chat/completions',data=body,method='POST',
        headers={'Authorization':f'Bearer {k}','Content-Type':'application/json'})
    try:
        urllib.request.urlopen(r,timeout=30)
        print(model, 'UNEXPECTED ALLOW')
    except urllib.error.HTTPError as err:
        print(model, 'blocked/status', err.code)
PY
```

## Components (source of truth in this repo)

| Path | Role |
|------|------|
| `scripts/or_billing_policy.py` | Single policy SoT (allowlist + absolute Claude/Grok/OpenAI-frontier deny) |
| `scripts/billing_policy.py` | Compat shim |
| `scripts/billing_guard.py` | Scan/fix all profile configs + env |
| `scripts/sync_or_billing_guardrail.py` | Push OR workspace allowlist via management key |
| `scripts/apply_hermes_core_billing_patches.py` | Patch local hermes-agent refuse points |
| `scripts/install_billing_hard_deny.sh` | One-shot installer |
| `plugins/carrier-billing-guard/` | Runtime plugin (`llm_execution` hard deny) |
| `scripts/apply_bot_matrix.sh` | Final gate after matrix apply |
| `scripts/api_watcher_heartbeat.sh` | Recurring config scan |

## Windows Hermes — copy-paste prompt

See bottom of this file or `docs/WINDOWS_BILLING_HARD_DENY_PROMPT.md`.
