# ISSUE: Enable Qwen2.5 (esp. Qwen2.5-Coder) as a local Hermes bot model

> Filed 2026-08-26 (Michael request). Priority: high for the coding wing.
> Owner: coding wing / maintenance. Related: all-hands crash-loop fix.

## Want

Run **Qwen2.5-Coder** (and qwen2.5 generally) as the local model for carrier bots
— especially the coding wing (firstmate/Mate, code_auditor, patch_writer). Qwen2.5-
Coder is a stronger coder than Llama-3.1-8B for our use case.

## Why it was blocked (root cause)

Hermes enforces `MINIMUM_CONTEXT_LENGTH = 64,000` at agent init
(`agent/agent_init.py:2841`). The stock `qwen2.5:7b-instruct-q4_K_M` GGUF
*advertises* only **32,768** tokens in its metadata (`qwen2.context_length`), so
Hermes refused to initialize and the worker crashed at ~1s (the code_auditor/
patch_writer crash-loop). Qwen2.5 actually supports **131,072** via YaRN rope
scaling — the GGUF just ships the conservative 32K default.

## What we found (2026-08-26) — likely ALREADY UNBLOCKED

After setting `OLLAMA_CONTEXT_LENGTH=65536` on the WSL Ollama service (done for the
llama fix), Hermes' `model_metadata.get_model_context_length()` now RESOLVES qwen to
**131072**, which PASSES the 64K floor:

```
qwen2.5:7b-instruct-q4_K_M   -> Hermes resolves 131072 | passes 64000 floor: True
qwen2.5-7b-64k (num_ctx patch) -> 131072 | True
llama3.1:8b-instruct-q4_K_M  -> 131072 | True
```

So the server-side `OLLAMA_CONTEXT_LENGTH` is what fixed the resolution. This needs
a REAL bot spawn to confirm (resolver passing ≠ init passing — the init reads
`context_compressor.context_length`, which may or may not track the resolver).

## Action items

- [ ] Pull `qwen2.5-coder:7b-instruct-q4_K_M` (in progress).
- [ ] Confirm a real bot spawn on qwen2.5-coder does NOT crash at init (the true
      test — the resolver returning 131072 is necessary but verify init agrees).
- [ ] If init still reads 32768 despite the resolver: add `model.context_length:
      65536` to the bot config.yaml (the escape hatch the error message names), OR
      build a YaRN-scaled Modelfile that bakes the declared context to ≥64K.
- [ ] Run the coding-quality eval (llama3.1 vs qwen2.5 vs qwen2.5-coder vs Opus
      reference) and pick the coding-wing default on evidence.
- [ ] DURABLE core fix (from sa-2): make init-time context-floor failures
      failover-eligible so a below-floor local primary fails OVER to OAuth instead
      of crashing — closes the crash-loop CLASS, not just this model.

## Notes

- Keep local-primary + OAuth-fallback policy.
- base_url must be `http://localhost:11434/v1` on this host (NOT 127.0.0.1 — WSL
  NAT quirk: 127.0.0.1 returns HTTP 000 from Windows; localhost works & is_local).
- billing unaffected (custom/localhost not metered).
