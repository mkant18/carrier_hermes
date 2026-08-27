# FEATURES Scout Report — 2026-08-26
**Job ID:** SR-FEATURES-2026-08-26-C11
**From:** research_agent (Probe)
**To:** chief_of_staff (Helm)
**Date:** 2026-08-26
**Tier:** 7 — FEATURES scout (step 1 of pipeline)

---

## Executive Summary

Scouted GitHub trending and LLM-tooling ecosystem for projects that could add concrete capability
to carrier_hermes. Five candidates identified, ranked by carrier_hermes fit. Top recommendation:
**HKUDS/nanobot** (47k stars, direct Telegram/Discord/Ollama alignment, low integration lift).
Two others are near-certain wins on narrow problems. Two are watch-and-assess.

---

## Candidates

---

### Candidate 1 — HKUDS/nanobot

**URL:** https://github.com/HKUDS/nanobot
**Stars:** 47,366 (created 2026-02-01, ~6 months to 47k — extreme momentum)
**License:** MIT
**Language:** Python
**Focus area:** Multi-agent orchestration + Discord/Telegram infrastructure + Memory/RAG

**What it is:**
Ultra-lightweight self-hosted personal AI agent framework. 4,000-line readable core with:
- Native Telegram, Discord, Slack, WeChat, Email, Mattermost channels (all first-class)
- MCP client out-of-the-box (mounts multiple MCP servers per config)
- "Dream" long-term memory system (conversation history + semantic retrieval, no vector-DB tax)
- Multi-agent delegation (subagents, goal-mode loops)
- Ollama / vLLM / LM Studio as local providers — no cloud key required
- Built-in cron scheduler for scheduled automations
- OpenAI-compatible API on localhost:8000 for programmatic access
- ClawHub skill marketplace integration (same SKILL.md format as Hermes)

**Why it matters for carrier_hermes:**
nanobot's channel architecture directly parallels carrier_hermes's gateway layer (Telegram, Discord).
The Dream memory system is a proven alternative to rolling our own RAG.
The ClawHub/SKILL.md format compatibility means Hermes skills could be imported directly.
Most importantly: the allow-list feature for Discord channels (only respond in whitelisted channels)
solves a real problem carrier_hermes faces in shared servers.

**Scoring:**

| Criterion | Score (1-5) | Notes |
|-----------|-------------|-------|
| Architecture alignment | 5 | Telegram+Discord+Ollama+MCP+Skills — exact match to carrier_hermes stack |
| Stars trajectory | 5 | 47k in 6 months; still gaining ~1k/week |
| Integration lift | 4 | Could adopt Dream memory as a standalone module; or lift channel patterns |
| Non-overlap | 3 | Some feature overlap with existing fleet (gateway, cron). Additive on memory. |

**Total: 17/20**

**Recommendation:** HIGH PRIORITY. Study nanobot's Dream memory implementation for potential
adoption. Evaluate Discord allow-list implementation for carrier_hermes's Discord gateway.

---

### Candidate 2 — MakazhanAlpamys/Soup

**URL:** https://github.com/MakazhanAlpamys/Soup
**Stars:** 2,951 (created 2026-02-20; climbing steadily; v0.73.x actively shipped)
**License:** Apache 2.0
**Language:** Python
**Focus area:** Local LLM fine-tuning / model training

**What it is:**
One-YAML LLM fine-tuning CLI that trains 8B models on a 4 GB laptop GPU via layer streaming.
Key capabilities:
- Layer streaming: frozen base streams from RAM/NVMe one decoder layer at a time; peak VRAM
  = one layer, not the whole model. RTX 3050 4GB can train Llama-3.1-8B at 119 tok/s.
- NF4 quantization of the streamed base (~4x smaller)
- SFT, DPO, GRPO, ORPO, KTO — all over layer streaming as of v0.72.4
- MCP server mode (`soup mcp serve`) so Claude Code / Cursor can drive training conversationally
- Export to GGUF for direct Ollama / llama.cpp loading
- Autopilot mode: give it a dataset and a goal, it picks hyperparams automatically
- Validated on Windows 11 (same OS as carrier_hermes host)

**Why it matters for carrier_hermes:**
The Training tier (Tier 6) in Silent Running currently has no local fine-tuning tool.
Soup would let carrier_hermes fine-tune its own correction-replay datasets on Michael's GPU
without cloud spend. The MCP server means Helm could trigger training jobs via tool call.
The GGUF export → Ollama path closes the loop: train locally, serve locally, route locally.

**Scoring:**

| Criterion | Score (1-5) | Notes |
|-----------|-------------|-------|
| Architecture alignment | 4 | Windows-validated, Ollama GGUF export, MCP server — fits Hermes stack |
| Stars trajectory | 3 | 2.9k moderate — but technically novel (layer streaming is real innovation) |
| Integration lift | 4 | One YAML config, `soup train`, `soup export --format gguf`. Very low. |
| Non-overlap | 5 | Nothing in fleet can do this today. Purely additive. |

**Total: 16/20**

**Recommendation:** HIGH PRIORITY. Pilot with Training tier. Soup + Ollama = complete local
fine-tune-to-serve pipeline for carrier_hermes without any cloud dependency.

---

### Candidate 3 — 0xranx/GolemBot

**URL:** https://github.com/0xranx/golembot
**Stars:** 315 (created recently; small but hyper-relevant)
**License:** MIT
**Language:** TypeScript / Node.js
**Focus area:** Discord/Telegram bot infrastructure — coding-agent gateway

**What it is:**
"Any Agent × Any Provider × Anywhere" — a gateway that connects Cursor, Claude Code, OpenCode,
or Codex to Slack, Telegram, Discord, Feishu, DingTalk, WeChat. One config block to swap
providers. Compatible with 13,000+ ClawHub/OpenClaw community skills (SKILL.md format).
- Built-in cron scheduler for scheduled tasks pushed to IM channels
- Skill system: drop a SKILL.md directory in, agent gains the capability
- Docker-deployable, OpenAI-compatible provider routing
- Supports Claude Code explicitly as a backend harness
- 1,252+ unit tests

**Why it matters for carrier_hermes:**
GolemBot is essentially a TS implementation of the gateway layer carrier_hermes already has,
but with explicit Claude Code harness support and the ClawHub skill marketplace baked in.
The value is not in replacing carrier_hermes's gateway but in studying its harness-adapter
pattern — specifically how it routes Claude Code through arbitrary providers (OpenRouter,
MiniMax, DeepSeek, SiliconFlow) with zero code changes. This is a model for carrier_hermes's
own provider-routing tier.

Stars are modest (315) but rising and the project has direct architectural relevance.

**Scoring:**

| Criterion | Score (1-5) | Notes |
|-----------|-------------|-------|
| Architecture alignment | 5 | Claude Code + Telegram + Discord + SKILL.md = exact carrier_hermes shape |
| Stars trajectory | 2 | 315 stars — early, rising, but unproven momentum |
| Integration lift | 3 | TS not Python; would be reference implementation, not direct import |
| Non-overlap | 3 | Overlaps gateway. Additive on provider-routing patterns and ClawHub integration. |

**Total: 13/20**

**Recommendation:** MEDIUM — watch and study. Consider pulling GolemBot's provider-routing
config pattern into carrier_hermes's own routing layer design. Not for direct adoption yet.

---

### Candidate 4 — omnigent-ai/omnigent

**URL:** https://github.com/omnigent-ai/omnigent
**Stars:** 9,200 (created 2026-06-11; 9.2k in ~2.5 months — strong momentum)
**License:** Apache 2.0
**Language:** Python + TypeScript
**Focus area:** Multi-agent orchestration / meta-harness

**What it is:**
Open-source meta-harness that orchestrates Claude Code, Codex, Cursor, Hermes, Pi, and custom
agents in a common layer. Key features:
- YAML-defined agents with tool declarations, MCP servers, and sub-agent references
- Cross-device session sync (terminal → browser → phone)
- Policy enforcement and sandboxing across harnesses
- "Polly" meta-agent that delegates to coding sub-agents in parallel git worktrees, then
  routes diffs to a reviewer from a different vendor
- Explicitly lists Hermes as a supported harness (executor: hermes / hermes-native)
- Cloud sandbox support (Modal, E2B, Kubernetes, etc.)
- Alpha stage, actively shipping

**Why it matters for carrier_hermes:**
Omnigent already knows about Hermes and has a `hermes` executor type. The parallel-worktree
delegation pattern ("Polly") is architecturally close to what carrier_hermes does in its
fleet — assign tasks to specialist agents, collect outputs. The YAML agent spec could inform
how carrier_hermes defines its own bot profiles more formally.

**Scoring:**

| Criterion | Score (1-5) | Notes |
|-----------|-------------|-------|
| Architecture alignment | 4 | Has Hermes executor; multi-agent + worktree delegation = direct fit |
| Stars trajectory | 4 | 9.2k in 2.5 months; strong trajectory for alpha software |
| Integration lift | 2 | Alpha. macOS desktop app only; no Windows desktop. CLI path still usable. |
| Non-overlap | 2 | Significant overlap with Helm's orchestration role. Risk of redundancy. |

**Total: 12/20**

**Recommendation:** MEDIUM — monitor. Do not adopt yet (alpha, macOS desktop). Track for
when it stabilizes. The Hermes executor integration is a potential upstream contribution
opportunity — could give carrier_hermes visibility in a fast-growing ecosystem.

---

### Candidate 5 — MakazhanAlpamys/Soup + ulab-uiuc/LLMRouter (pair)

**URL:** https://github.com/ulab-uiuc/LLMRouter
**Stars:** 1,000+ (crossed 1k Jan 2026; latest release adds TSRouter for time-series Aug 2026)
**License:** Research / open
**Language:** Python
**Focus area:** Local LLM routing / model routing

**What it is:**
Unified library for LLM routing — formulates routing as a sequential decision process across
single-turn, multi-turn, and personalized scenarios. 16+ routing methods, CLI, Gradio UI,
11 benchmark datasets. Latest addition: TSRouter for time-series tasks.

**Why it matters for carrier_hermes:**
carrier_hermes has a Smart Router task already (t_7857d271 — researched routing strategies).
LLMRouter provides a ready-made routing library with benchmarks rather than requiring Hermes
to build routing heuristics from scratch. The xRouteBench benchmark could validate any routing
implementation. The library supports Ollama-compatible endpoints.

**Scoring:**

| Criterion | Score (1-5) | Notes |
|-----------|-------------|-------|
| Architecture alignment | 3 | Routing is a carrier_hermes need; library is research-grade, not production |
| Stars trajectory | 2 | Modest; research project, not a product |
| Integration lift | 3 | pip install; needs benchmark data to configure routing policies |
| Non-overlap | 4 | Smart Router work is ongoing but no lib adopted yet |

**Total: 12/20**

**Recommendation:** LOW-MEDIUM — use as a reference for the Smart Router feature design.
Not for direct adoption; use for algorithm selection and benchmarking methodology.

---

## Summary Table

| Rank | Project | Stars | Momentum | Score | Action |
|------|---------|-------|----------|-------|--------|
| 1 | HKUDS/nanobot | 47k | Extreme (47k in 6mo) | 17/20 | Adopt — study Dream memory + Discord allow-list |
| 2 | MakazhanAlpamys/Soup | 2.9k | Steady (active releases) | 16/20 | Adopt — pilot local fine-tune pipeline |
| 3 | 0xranx/GolemBot | 315 | Early/rising | 13/20 | Watch — reference for provider-routing patterns |
| 4 | omnigent-ai/omnigent | 9.2k | Strong (9.2k in 2.5mo) | 12/20 | Monitor — track for Hermes executor stabilization |
| 5 | ulab-uiuc/LLMRouter | 1k+ | Steady research | 12/20 | Reference only — use for Smart Router algorithm selection |

---

## Key Trends Observed

1. **Memory is the new middleware (2026 consensus).** Flat RAG is considered solved; graph memory,
   temporal reasoning, and persistent agent identity are where the ecosystem is investing.
   carrier_hermes should adopt a structured memory layer (nanobot's Dream is the lowest-lift option).

2. **SKILL.md is becoming a de-facto standard.** ClawHub, nanobot, GolemBot, and Omnigent all use
   the same SKILL.md format. carrier_hermes is already using this format — this is a strategic
   advantage. Publishing select carrier_hermes skills to ClawHub would give fleet visibility.

3. **Local fine-tuning on consumer hardware is now real.** Soup's layer-streaming proves 8B
   models on 4 GB GPUs. Training tier is viable without cloud. This changes the economics of
   carrier_hermes's self-improvement loop significantly.

4. **MCP has won.** Donated to Linux Foundation, adopted by Anthropic/OpenAI/Microsoft/Google
   (MCP 2026-07-28 spec shipped). Every new agent framework ships MCP support. carrier_hermes's
   existing MCP integration is correctly positioned.

---

## Sources

- https://github.com/HKUDS/nanobot (direct extraction)
- https://github.com/MakazhanAlpamys/Soup (direct extraction)
- https://github.com/0xranx/golembot (direct extraction)
- https://github.com/omnigent-ai/omnigent (direct extraction)
- https://github.com/ulab-uiuc/LLMRouter
- https://startupcorners.com/digest/devtools-digest-2026-08-13
- https://agentconn.com/blog/agent-memory-wars-memgraphrag-supermemory-flat-rag-2026
- https://github.com/Supersynergy/awesome-ai-agents-2025 (Aug 2026 snapshot)
- https://andrew.ooo/posts/nanobot-hkuds-ultra-lightweight-personal-ai-agent/
- https://github.com/caramaschiHG/awesome-ai-agents-2026

**Confidence:**
- Star counts: HIGH (pulled from live GitHub pages)
- Created dates: HIGH (GitHub API metadata)
- Feature descriptions: HIGH (extracted from READMEs directly)
- Trend assessments: MEDIUM (synthesized from multiple secondary sources)

---

*Report produced by research_agent (Probe) for Helm review. Recon only — no code modified.*
