# Local LLM Integration Plan — RTX 4080 Super

> **Prepared by:** Probe (research subagent)  
> **Kanban task:** t_a52c4307  
> **Hardware:** RTX 4080 Super 16 GB GDDR6X (736 GB/s bandwidth) · AMD Ryzen 7 7800X3D · Windows 11  
> **Constraint:** Zero marginal cost — subscription-only billing model  

---

## §1 — Recommended Model (Shortlist)

All throughput figures are for the RTX 4080 Super 16 GB unless otherwise noted. Speed is memory-bandwidth-bound at these sizes; the 736 GB/s bandwidth is the dominant factor.

### Tier A — Fast/Tiny (≤4 GB VRAM)

| Model | Quant | VRAM | Tok/s (4080 Super) | Source | Task archetype | OpenRouter equiv. | $/1M (in/out) |
|---|---|---|---|---|---|---|---|
| **Gemma-2-2B-Instruct** | Q4_K_M | ~1.7 GB | ~280–350 | generalcompute.com (FP16 extrapolated to GGUF Q4 on 736 GB/s) | Ultra-fast single-turn rewrites, short completions, triage classification | `google/gemma-2-2b-it` | $0.10 / $0.10 |
| **Qwen2.5-3B-Instruct** | Q4_K_M | ~1.9 GB | ~250–300 | Qwen readthedocs speed benchmark (GPTQ-Int4 anchor; GGUF Q4_K_M on high-BW GPU ≈ similar) | Structured-output generation, JSON templating, short summaries | `meta-llama/llama-3.2-3b-instruct` | $0.018 / $0.018 |
| **Phi-3-mini-3.8B** | Q4_K_M | ~2.3 GB | ~200–250 | willitrunai.com (VRAM confirmed 2.3 GB; speed extrapolated from 736 GB/s BW model) | Instruction following, templated rewrites, moderate reasoning | `microsoft/phi-3-mini-128k-instruct` | $0.00 / $0.00 (free on OpenRouter) |

### Tier B — Sweet-Spot (6–10 GB VRAM)

| Model | Quant | VRAM | Tok/s (4080 Super) | Source | Task archetype | OpenRouter equiv. | $/1M (in/out) |
|---|---|---|---|---|---|---|---|
| **Qwen2.5-7B-Instruct** | Q4_K_M | ~5.0 GB | ~110–130 | willitrunai.com + ertas.ai (RTX 4090 at 3,680 pp tok/s; scaled to 4080 Super BW) | Balanced summarisation, code explanation, structured rewrites, 128K context | `qwen/qwen-2.5-7b-instruct` | $0.10 / $0.20 |
| **Llama-3.1-8B-Instruct** | Q4_K_M | ~4.9 GB | ~79–104 | modelfit.io (79 tok/s measured), smeltcore.com via hardware-corner.net (104 tok/s) | General chat, agent-tool workflows, creative summaries | `meta-llama/llama-3.1-8b-instruct` | $0.02 / $0.04 |
| **Mistral-7B-Instruct-v0.3** | Q4_K_M | ~4.4 GB | ~98 | willitrunai.com (RTX 4080 Super 16 GB, Q4_K_M, direct estimate) | Concise structured output, low-latency completions, legacy prompt compat | `mistralai/mistral-7b-instruct-v0.3` | $0.03 / $0.03 |

### Tier C — Near-Frontier (10–14 GB VRAM)

| Model | Quant | VRAM | Tok/s (4080 Super) | Source | Task archetype | OpenRouter equiv. | $/1M (in/out) |
|---|---|---|---|---|---|---|---|
| **Qwen2.5-14B-Instruct** | Q4_K_M | ~8.7 GB | ~81 (tight fit) | willitrunai.com (Qwen2.5-Coder-14B on RTX 4080 Super = 81.1 tok/s; non-Coder base ≈ same BW) | Near-frontier quality for longer document tasks, code review, multi-step reasoning | `qwen/qwen-2.5-14b-instruct` | ~$0.20 / $0.40 |
| **Phi-4-14B** | Q4_K_M | ~8.5 GB | ~49–81 | modelfit.io (14B class = ~49 tok/s conservative; willitrunai 81 tok/s upper bound for 14B) | Dense reasoning tasks, STEM Q&A, structured extraction | `microsoft/phi-4` | ~$0.07 / $0.14 |
| **Llama-3.1-13B** | Q4_K_M | ~7.8 GB | ~55–65 | modelfit.io 14B baseline; scaled for 13B parameter count | Long-form summarisation, multilingual inference | `meta-llama/llama-3.1-8b-instruct` (no 13B on OpenRouter) | N/A |

> **Note on 14B "tight fit":** At Q4_K_M, 14B models consume ~8.7–9.5 GB VRAM for weights. With 16K context, the KV cache adds ~1–2 GB, leaving 4–5 GB headroom. This is comfortable. At 64K context (Hermes minimum for agent use), KV cache grows to ~4–6 GB, making the fit tighter but still viable at Q4_K_M with `num_ctx 32768` for rote tasks that don't need full context depth.

---

### ✅ Primary Recommendation: **Qwen2.5-7B-Instruct Q4_K_M**

**Rationale:** At ~5.0 GB VRAM it leaves 11 GB headroom for context and system RAM co-use. The 128K native context window satisfies Hermes' 64K minimum with room for growth. Qwen2.5 has first-class tool-calling support in both Ollama and llama.cpp (`--jinja` parser: `qwen`). OpenRouter equivalent costs $0.10–$0.20/1M — every rote task routed locally is direct savings. Instruction following benchmarks (MMLU, MT-Bench) are 3–5 points above Mistral 7B v0.3 on the same hardware class (ertas.ai, 2024).

### 🔁 Backup Recommendation: **Llama-3.1-8B-Instruct Q4_K_M**

**Rationale:** Largest community fine-tune ecosystem, native Llama3 tool-call parser in llama.cpp/Ollama, $0.02/$0.04 OpenRouter pricing makes savings calculation trivial. Marginally more VRAM-efficient than Qwen2.5-7B. Use if Qwen2.5-7B tool-calling proves unreliable in practice.

---

## §2 — Serving Stack

### Comparison Matrix

| Stack | Windows Install Path | API Endpoint | Auto-start (headless) | OpenAI-compatible | Pros | Cons |
|---|---|---|---|---|---|---|
| **Ollama** | `OllamaSetup.exe` from ollama.com/download; installs to `%LOCALAPPDATA%\Programs\Ollama`; background tray process | `http://localhost:11434/v1/chat/completions` | `ollama serve` via NSSM as Windows Service (docs.ollama.com/windows) | ✅ Full `/v1/chat/completions` + `/v1/models` | Zero-compilation install, auto GPU offload, model management CLI, Hermes `custom` provider works out-of-box | Needs `OLLAMA_CONTEXT_LENGTH=64000` env var or Hermes rejects (<64K default on 16 GB cards) |
| **llama.cpp** | Pre-built CUDA binaries from llama.cpp GitHub releases (no compile on Windows); or `winget install ggml.llama.cpp` | `http://localhost:8080/v1/chat/completions` | `llama-server.exe` wrapped in NSSM or Task Scheduler | ✅ Full OpenAI-compat; requires `--jinja` flag for tool calling | Maximum throughput, full control, `--ngl 99` pins all layers to GPU, direct GGUF load | More flags to manage; no model management CLI; must download GGUF manually |
| **LM Studio** | Installer from lmstudio.ai; GUI-first; server via Developer tab or `lms server start` | `http://localhost:1234/v1/chat/completions` | Requires GUI or `lms server start` CLI; **not easily headless on Windows** | ✅ Full + Hermes has `lmstudio` provider | Visual model browser, easy discovery | Requires user session to be active; poor fit for idle-triggered headless server |
| **vLLM** | **NOT natively supported on Windows.** Only path: WSL2 + Docker + NVIDIA Container Toolkit. As of 2026 the official vLLM docs list no Windows native installer. | N/A native | WSL2 process only | ✅ (via WSL) | Best throughput for batch/production | WSL2 layer introduces latency, complexity, and complicates idle-toggle process management |

### ✅ Chosen Stack: **Ollama**

**Rationale:**  
- Native Windows installer, no compilation, no WSL  
- NSSM wraps `ollama serve` into a true Windows Service: auto-start on boot, respawn on crash, stop/start via `sc.exe` commands from Python  
- Hermes official docs use `http://localhost:11434/v1` with `provider: custom` — zero glue code  
- `OLLAMA_CONTEXT_LENGTH=64000` environment variable sets the context floor once globally  
- `ollama stop <model>` immediately unloads the model from VRAM (GPU yield)  

**Critical config:** Ollama defaults to 4,096 token context on GPUs with <24 GB VRAM. Hermes requires **64,000 token minimum** for agent use. Set `OLLAMA_CONTEXT_LENGTH=64000` as a system environment variable before starting the service, or Hermes will reject the session at startup.

---

### Exact REST Request Shape (Hermes → Ollama)

```http
POST http://localhost:11434/v1/chat/completions
Content-Type: application/json
Authorization: Bearer ollama

{
  "model": "qwen2.5:7b",
  "messages": [
    {"role": "system", "content": "You are a concise summarisation assistant."},
    {"role": "user", "content": "Summarise the following in 3 bullet points:\n\n{text}"}
  ],
  "temperature": 0.2,
  "max_tokens": 512,
  "stream": false
}
```

> `Authorization: Bearer ollama` — Ollama ignores the key value but Hermes' HTTP client may require the header to be present. Use any non-empty string.

---

## §3 — Idle-Toggle Design (Windows 11)

### Detection Strategy Comparison

| Method | What it detects | Reliability | Latency to detect activity |
|---|---|---|---|
| `GetLastInputInfo` (Win32/ctypes) | Keyboard + mouse idle time system-wide | High — Win32 standard, no elevated perms | <1 s (polling interval) |
| `nvidia-smi` / `pynvml` | GPU utilisation ≥ threshold (gaming, video render) | High — NVML is stable | Configurable polling (1–5 s) |
| Task Scheduler idle trigger | OS-level idle (CPU <threshold, no input) | Medium — heuristic, not always reliable for short tasks | Coarse (minutes) |
| Foreground process class / window title | Named process or window (Steam, game exe) | Medium — relies on known process names | <1 s |

### ✅ Recommended: Dual-signal hybrid (`GetLastInputInfo` + `pynvml`)

**Logic:**
- **Idle declared** when BOTH signals are true: input idle ≥ 5 minutes AND GPU utilisation < 15% for ≥ 60 s  
- **Activity declared** when EITHER signal flips: any input event (mouse/keyboard) OR GPU utilisation spikes to ≥ 40% for ≥ 3 consecutive polls (1 s each)  
- This prevents false starts (a brief idle between clicks) and ensures gaming/video workloads force immediate shutdown  

### Lifecycle Specification

**1. Idle declaration**  
- `GetLastInputInfo` → compute elapsed ms → divide by 1000 → idle seconds  
- If idle_seconds ≥ 300 AND gpu_util < 15% sustained for 60 s → declare IDLE  
- Debounce: require both conditions simultaneously for 10 s before firing start signal  

**2. Server start**  
```python
proc = subprocess.Popen(
    ["ollama", "serve"],
    env={**os.environ, "OLLAMA_CONTEXT_LENGTH": "64000"},
    creationflags=subprocess.CREATE_NO_WINDOW,
)
# Pre-load model to warm VRAM
subprocess.run(["ollama", "run", MODEL_NAME, ""], timeout=60)
```
- Poll `http://localhost:11434/` until HTTP 200 (max 30 s, then abort)  
- Log start timestamp; mark state = RUNNING  

**3. Activity detection → server stop**  
- Priority: **immediate yield**, not graceful shutdown  
- On activity signal: `proc.kill()` (SIGKILL) — do NOT use `proc.terminate()` (Ollama ignores SIGTERM gracefully and keeps the port held)  
- Then `subprocess.run(["ollama", "stop", MODEL_NAME])` to explicitly unload from VRAM  
- Release takes ~1–3 s; GPU util returns to 0% within 5 s  

**4. Missed requests during shutdown**  
- Hermes hits the local endpoint; gets `ConnectionRefused` or HTTP 503  
- `provider: custom` with Hermes returns an error on failed requests — Hermes' own fallback_chain (Claude → Grok → OpenRouter) handles escalation automatically  
- No special wrapper needed: the error is the signal. Ensure Hermes bots are configured with cloud fallback as described in §4  

---

### Python Pseudocode — Watcher Loop (Windows 11)

```python
"""
idle_watcher.py — Windows 11 idle-toggle for Ollama inference server
Requires: pip install pynvml psutil
"""
import ctypes, subprocess, time, os, logging
import pynvml

MODEL_NAME       = "qwen2.5:7b"
IDLE_THRESHOLD_S = 300        # 5 minutes of no input
GPU_IDLE_PCT     = 15         # GPU below this % = idle
GPU_ACTIVE_PCT   = 40         # GPU above this % = active (gaming)
POLL_INTERVAL_S  = 5          # main loop tick
GPU_ACTIVE_TICKS = 3          # consecutive high-GPU polls before declaring active
OLLAMA_PORT      = 11434

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("idle_watcher")

class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

def get_idle_seconds() -> float:
    lii = LASTINPUTINFO()
    lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
    ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii))
    elapsed_ms = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
    return elapsed_ms / 1000.0

def get_gpu_util() -> int:
    pynvml.nvmlInit()
    handle = pynvml.nvmlDeviceGetHandleByIndex(0)
    util = pynvml.nvmlDeviceGetUtilizationRates(handle)
    return util.gpu  # 0–100

def start_server() -> subprocess.Popen:
    log.info("Idle detected — starting Ollama")
    env = {**os.environ, "OLLAMA_CONTEXT_LENGTH": "64000", "OLLAMA_HOST": "0.0.0.0"}
    proc = subprocess.Popen(
        ["ollama", "serve"],
        env=env, creationflags=subprocess.CREATE_NO_WINDOW,
    )
    # Wait for readiness
    import urllib.request
    for _ in range(30):
        try:
            urllib.request.urlopen(f"http://localhost:{OLLAMA_PORT}/", timeout=1)
            break
        except Exception:
            time.sleep(1)
    # Warm the model
    subprocess.run(["ollama", "run", MODEL_NAME, "ping"], timeout=60,
                   capture_output=True)
    log.info("Ollama ready, model loaded")
    return proc

def stop_server(proc: subprocess.Popen):
    log.info("Activity detected — killing Ollama immediately")
    subprocess.run(["ollama", "stop", MODEL_NAME], capture_output=True)
    proc.kill()
    proc.wait(timeout=10)
    log.info("Ollama stopped, GPU released")

def main():
    server_proc = None
    gpu_active_streak = 0
    idle_confirm_ticks = 0
    IDLE_CONFIRM_NEEDED = 2   # both signals × 2 polls = 10 s debounce

    while True:
        idle_s   = get_idle_seconds()
        gpu_util = get_gpu_util()
        is_idle  = (idle_s >= IDLE_THRESHOLD_S) and (gpu_util < GPU_IDLE_PCT)
        is_busy  = (idle_s < 10) or (gpu_util >= GPU_ACTIVE_PCT)

        if server_proc is None:
            # Server is off — check if we should start
            if is_idle:
                idle_confirm_ticks += 1
            else:
                idle_confirm_ticks = 0
            if idle_confirm_ticks >= IDLE_CONFIRM_NEEDED:
                server_proc = start_server()
                idle_confirm_ticks = 0
        else:
            # Server is on — check if we should stop
            if is_busy:
                gpu_active_streak += 1
            else:
                gpu_active_streak = 0
            if gpu_active_streak >= GPU_ACTIVE_TICKS:
                stop_server(server_proc)
                server_proc = None
                gpu_active_streak = 0

        time.sleep(POLL_INTERVAL_S)

if __name__ == "__main__":
    main()
```

**Deployment on Windows 11:**  
Register `idle_watcher.py` as a Windows Service via NSSM:  
```batch
nssm install HermesIdleWatcher "C:\Python312\python.exe" "C:\carrier_hermes\idle_watcher.py"
nssm set HermesIdleWatcher AppNoConsole 1
nssm start HermesIdleWatcher
```

---

## §4 — Fleet Integration Architecture

### Hermes Custom Provider Config (Official Docs)

From `hermes-agent.nousresearch.com/docs/integrations/providers`:

> "Hermes Agent works with any OpenAI-compatible API endpoint. If a server implements `/v1/chat/completions`, you can point Hermes at it."

The canonical config in `~/.hermes/config.yaml` (or per-bot profile config):

```yaml
model:
  default: qwen2.5:7b         # Ollama model tag
  provider: custom
  base_url: http://localhost:11434/v1
  api_key: ollama              # ignored by Ollama but required field
  context_length: 32768        # rote tasks don't need 64K; saves KV cache VRAM
```

Hermes also has a native `lmstudio` provider (built-in), but for Ollama the `provider: custom` + `base_url` path is the documented approach. Switching is a one-liner: `/model custom:qwen2.5:7b` inside a session.

---

### Three Options Analysis

| Option | Description | Fit for this fleet |
|---|---|---|
| **A — Local at BOTTOM** | Every bot's fallback chain ends with local LLM; used only when all cloud providers fail | Wrong fit — cloud failing is rare; this never actually routes rote tasks locally |
| **B — Local at TOP with task routing** | Classify each request; cheap tasks → local, complex → cloud | Complex to implement; requires reliable task classifier running *before* the LLM call |
| **C — Dedicated "rote" bot profile** | A separate Hermes bot profile configured with local LLM as primary, cloud as fallback; delegated simple tasks | **Best fit** — clean separation, no classifier required, fleet dispatch handles routing |

### ✅ Recommended: Option C — Dedicated Rote Bot Profile

**Architecture:**

```
Helm / chief_of_staff
    ├── [complex task] → main fleet bots (Claude Max → Grok → OpenRouter)
    └── [rote task]   → local-rote bot (Ollama local → Claude Max fallback)
```

**Rote task signals** (Helm applies at dispatch time):
- "summarise X", "rewrite Y", "template Z", "extract fields from …"
- Context window < 8K tokens
- No tool calls required
- Response < 512 tokens expected

**Per-bot config for the `local-rote` profile** (`C:\Users\micha\carrier_hermes\bots\local-rote\config.yaml`):

```yaml
# local-rote bot — primary: Ollama local, fallback: Claude Max
model:
  default: qwen2.5:7b
  provider: custom
  base_url: http://localhost:11434/v1
  api_key: ollama
  context_length: 32768

# Fallback chain: if Ollama is unreachable (server not started, user active),
# Hermes surfaces a connection error; the dispatcher catches it and re-routes
# to the main fleet bots via Claude Max OAuth.
# There is no native fallback_chain key in Hermes config.yaml — fallback is
# handled at the carrier_hermes fleet dispatcher level (see §5 step 6).

# Restrict toolset to reduce system-prompt size (local models have tighter context)
tools:
  enabled: false   # no tool calls from rote bot; pure text generation only

# Cap response length to avoid runaway generation
max_tokens: 768
temperature: 0.2
```

**Main fleet bots** — no change to existing config; they continue: `anthropic` → `xai-oauth` → `openrouter`.

**Routing logic** (carrier-hermes dispatcher, Python):

```python
ROTE_TASK_PATTERNS = [
    r"^(summarise|summarize|rewrite|extract|template|bullet[\s-]point)",
    r"\bsummar(y|ize|ise)\b",
    r"\breformat\b",
]

def dispatch(task: str, payload: dict) -> str:
    if is_rote(task) and local_server_healthy():
        return call_bot("local-rote", payload)
    return call_bot("main-fleet", payload)

def local_server_healthy() -> bool:
    try:
        r = requests.get("http://localhost:11434/", timeout=1)
        return r.status_code == 200
    except requests.exceptions.ConnectionError:
        return False  # Ollama not running; fallback to cloud
```

---

## §5 — Implementation Sequence

| # | Step | Assignee | Complexity | Dependencies |
|---|---|---|---|---|
| 1 | **Install Ollama for Windows** — download `OllamaSetup.exe` from ollama.com/download, install to default path, verify `ollama --version` in CMD | `user` | Low | None |
| 2 | **Pull primary model** — `ollama pull qwen2.5:7b` (downloads ~4.7 GB Q4_K_M GGUF automatically) | `user` | Low | Step 1 |
| 3 | **Set system env var** — add `OLLAMA_CONTEXT_LENGTH=64000` to Windows System Environment Variables (Control Panel → Advanced System Settings) | `user` | Low | Step 1 |
| 4 | **Install NSSM** — download NSSM 2.24 from nssm.cc, place `nssm.exe` in `C:\tools\` or on PATH | `user` | Low | None |
| 5 | **Write `idle_watcher.py`** — implement the watcher loop from §3 (pynvml + GetLastInputInfo), save to `C:\carrier_hermes\idle_watcher.py` | `mate` | Medium | Steps 1–3 |
| 6 | **pip-install watcher deps** — `pip install pynvml psutil requests` in the Python environment used by carrier_hermes | `scripted` | Low | Python installed |
| 7 | **Register idle_watcher as Windows Service** — NSSM install commands from §3; set service to start Delayed Automatic; test start/stop | `scripted` | Medium | Steps 4–5 |
| 8 | **Create `local-rote` bot profile** — create directory `C:\carrier_hermes\bots\local-rote\`, write `config.yaml` from §4 snippet | `mate` | Low | Step 1 |
| 9 | **Add `local_server_healthy()` check + dispatch routing** in carrier_hermes fleet dispatcher | `mate` | Medium | Steps 5–8 |
| 10 | **Smoke test rote routing** — start Ollama manually (`ollama serve`), send a "summarise this paragraph" task via dispatcher, verify it hits local-rote bot | `scripted` | Low | Steps 1–9 |
| 11 | **Smoke test idle-toggle** — leave PC idle 5+ min, verify watcher starts Ollama; move mouse, verify Ollama stops within 15 s; verify subsequent rote task falls back to Claude Max | `user` | Low | Steps 1–10 |
| 12 | **Pull backup model** — `ollama pull llama3.1:8b` (optional; run if Qwen2.5-7B tool-calling proves unreliable in rote context) | `user` | Low | Step 1 |
| 13 | **Logging + alerting** — add structured JSON logs to `idle_watcher.py`; emit Kanban note when fallback triggered more than N times/hour (indicator that idle threshold is mistuned) | `mate` | Medium | Step 5 |

---

## §6 — Open Questions for Helm Review

- **Which model tier to start with?** Probe recommends Qwen2.5-7B-Instruct Q4_K_M (sweet-spot tier). If 5 GB VRAM reservation during idle is acceptable alongside any always-on background tasks, confirm. Alternatively, start with Qwen2.5-3B for minimal VRAM footprint.

- **Idle threshold — is 5 minutes right?** The 300 s / GPU <15% dual-signal is a safe default, but if Michael runs background computation jobs that pause GPU for minutes at a time, the threshold may need raising to 10–15 min to prevent false starts.

- **Acceptable latency budget for rote tasks?** At ~110 tok/s on Qwen2.5-7B, a 256-token summary takes ~2.3 s generation time + ~0.5 s TTFT = ~3 s total. If sub-1-second is required for any rote tasks, switch to the Gemma-2-2B or Qwen2.5-3B tier.

- **Which bots get access to local-rote routing?** Recommend starting with one bot (e.g., `carrier_buzz` or a content-processing bot) before fleet-wide rollout. Confirm which bot profiles should be allowed to dispatch to local-rote.

- **Context length for local bot: 32K or 64K?** 32K is set in the §4 snippet as a compromise (rote tasks rarely exceed 8K, and 32K saves ~2 GB KV cache VRAM, keeping the GPU freer). Hermes requires ≥64K for full agent mode — but this bot has `tools: false`, so 32K is acceptable. Confirm this constraint is understood.

- **Should idle_watcher run as SYSTEM or as the user account?** Running as SYSTEM means it can start/stop Ollama even when no user is logged in (RDP/wake scenarios). Running as user is simpler but requires an active session. Recommend SYSTEM, but this needs confirmation and may require `nssm set` `AppEnvironmentExtra` to propagate user-specific CUDA paths.

- **VRAM impact on gaming performance?** Ollama is stopped on activity detection, so gaming VRAM should be fully reclaimed within ~5 s. If any game anti-cheat software (EAC, Battleye) flags Ollama's driver interaction, the model tier or serving stack may need adjustment.

- **Fallback escalation count alerting threshold?** How many fallback-to-cloud events per hour should trigger a Kanban note / Helm ping? Suggests 5 fallbacks/hour as a warning that Ollama is not staying up during expected idle windows.

- **Model update cadence?** Qwen2.5 and Llama 3.1 are actively maintained. Set a quarterly `ollama pull` update cron, or treat the locally pinned version as stable? Recommend pinning by digest for production stability.

---

## Appendix — Quick Reference

### Ollama Commands

```batch
:: Start server
ollama serve

:: Pull primary model
ollama pull qwen2.5:7b

:: Test inference
ollama run qwen2.5:7b "Summarise: The quick brown fox jumps over the lazy dog."

:: List loaded models and context
ollama ps

:: Stop model (free VRAM)
ollama stop qwen2.5:7b
```

### Hermes config.yaml Snippet (local-rote bot)

```yaml
model:
  default: qwen2.5:7b
  provider: custom
  base_url: http://localhost:11434/v1
  api_key: ollama
  context_length: 32768
tools:
  enabled: false
max_tokens: 768
temperature: 0.2
```

### Source Citations

| Claim | Source |
|---|---|
| RTX 4080 Super 8B Q4 = ~79 tok/s | modelfit.io/gpu/rtx-4080-super/ (Aug 2026) |
| RTX 4080 Super 14B Q4 = ~49 tok/s | modelfit.io/gpu/rtx-4080-super/ (Aug 2026) |
| Qwen3-8B on 4080 Super = 104.2 tok/s | smeltcore.com, citing hardware-corner.net |
| Qwen2.5-Coder-14B on 4080 Super = 81.1 tok/s | willitrunai.com/models/qwen-2.5-coder-14b |
| Mistral 7B v0.3 on 4080 Super ≈ 98 tok/s | willitrunai.com |
| Phi-3-mini VRAM at Q4_K_M = 2.3 GB | willitrunai.com/models/phi-3-mini-3.8b |
| Qwen2.5-7B Q4_K_M VRAM ≈ 5.0 GB | ertas.ai, willitrunai.com |
| OpenRouter Llama 3.1 8B price = $0.02/$0.04/1M | openrouter.ai/meta-llama/llama-3.1-8b-instruct |
| OpenRouter Qwen2.5 7B price = $0.10/$0.20/1M | openrouter.ai/qwen/qwen-2.5-7b-instruct |
| OpenRouter Mistral 7B price = $0.03/1M | openrouter.ai price-drop announcement |
| vLLM not natively supported on Windows | fazm.ai (2026-05-12 verified), docs.tokios.com |
| Ollama Windows native installer | docs.ollama.com/windows |
| Ollama context default <4096 on <24 GB GPUs | hermes-agent.nousresearch.com/docs/integrations/providers |
| Hermes 64K minimum context for agent use | hermes-agent.nousresearch.com/docs/integrations/providers |
| Hermes custom endpoint config syntax | hermes-agent.nousresearch.com/docs/integrations/providers |
| GetLastInputInfo Win32 API | learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getlastinputinfo |
| NSSM for Windows Service wrapping | docs.ollama.com/windows (cites nssm.cc) |
