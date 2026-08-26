# All-Hands Crash-Loop Fix — Findings & Pending Decisions (2026-08-26)

> Status: root cause fully diagnosed + measured. Infra + config fixes landed.
> The actual crash fix + GPU-safety measure are BLOCKED on two Michael decisions
> and one elevated-shell action. Nothing is crash-looping (2 bad tasks parked).

## Root cause (confirmed, not theory)

- code_auditor / patch_writer die in ~1s at `AIAgent.__init__` via a hard
  `raise ValueError` (`agent/agent_init.py:2841`): the local model
  `qwen2.5:7b-instruct-q4_K_M` advertises a **32,768** context window, below
  Hermes' hard **MINIMUM_CONTEXT_LENGTH = 64,000** floor (`model_metadata.py:413`).
- The failure is at INIT, before the conversation loop — so the (valid) OAuth
  `fallback_providers` are structurally unreachable; failover only wraps API-call
  errors inside the loop, not init. Worker exits; dispatcher reaps the dead PID one
  ~60s poll after a 30s grace → the misleading "pid not alive @ 61s".

## What was measured (empirical, this host)

- `qwen2.context_length = 32768` is a HARD GGUF ceiling. Setting
  `OLLAMA_CONTEXT_LENGTH=65536` AND per-request `num_ctx=65536` both get CLAMPED —
  `ollama ps` still shows CONTEXT 32768. **The env-var fix cannot work.**
- VRAM (RTX 4080 SUPER, 16GB): desktop baseline ~2.4GB (Parsec/browser/overlays);
  qwen2.5-7b @32K = 6.6GB, 100% on GPU. A 64K KV cache ≈ 8.3GB total — fits with
  ~5GB headroom, no spill, no crash.
- GPU util during active token generation spikes to **~91%** (inherent to GPU
  inference — cannot be held at 80% during the burst). Peak temp 82°C (spec ok).
- GPU power: default 320W, range 150–352W. `nvidia-smi -pl` needs an ELEVATED
  shell (Insufficient Permissions from the normal shell).

## Fixes already landed

- **Infra (sa-0):** Ollama correctly found running in **WSL2 systemd** (not native
  Windows; the :11434 listener is wslrelay.exe). Added systemd override
  `OLLAMA_HOST=0.0.0.0:11434` + a Windows portproxy so mks-pc serves over
  Tailscale. VERIFIED reachable at `100.87.88.30:11434` and
  `mks-pc.taileda46c.ts.net:11434`. Server stays on mks-pc RTX 4080. ⚠️ WSL IP can
  change on reboot → needs a boot task to rebuild the portproxy (tracked, not built).
- **Config (sa-1):** repointed 4 rote-bot base_urls localhost→tailscale, valid
  YAML, local-primary preserved. ⚠️ sa-2 warning: Hermes `is_local_endpoint`
  matches Tailscale CGNAT **IPs** (100.x) but NOT `.ts.net` MagicDNS names → a
  `.ts.net` base_url is treated as REMOTE (loses local-endpoint timeout semantics).
  **Prefer the `100.87.88.30` IP over the MagicDNS name in bot base_urls.**

## PENDING — needs Michael

1. **Model strategy (the real fix).** qwen2.5:7b can't serve 64K. Recommended:
   swap rote-bots' local primary to **Llama-3.1-8B-Instruct** (documented backup,
   native 128K, ~4.9GB). Needs a ~5GB `ollama pull`. Alternatives: a YaRN/128K
   qwen2.5 tag, or lower Hermes' 64K floor in core (affects ALL bots; the floor
   exists to give context-compression headroom — least preferred).
2. **GPU safety.** Recommended: `nvidia-smi -pl 250` (elevated shell) to bound
   temp/watts, keep MAX 1 concurrent local inference, keep idle-only. Accepts brief
   ~90% util bursts during generation but physically bounded.
3. **base_url IP vs name:** change the 4 configs from `mks-pc.taileda46c.ts.net` to
   `100.87.88.30` so Hermes keeps local-endpoint timeout semantics (sa-2 finding).

## Follow-up (durable, lower priority)

- Option A from sa-2: make init-time feasibility failures failover-eligible (wrap
  worker `AIAgent` construction so a below-floor/init error walks
  `fallback_providers` before exiting). This closes the crash-loop CLASS, not just
  this instance. Core change — file as a normal maintenance/coding task.
- WSL-IP portproxy boot task (infra durability).
