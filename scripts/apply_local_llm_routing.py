#!/usr/bin/env python3
"""
apply_local_llm_routing.py — Wire the local LLM routing policy fleet-wide.

Policy (from COST_MODEL.md §Local LLM Policy):
  DECISION-MAKING TIER (never local LLM):
    Grok/xai-oauth primary → OpenAI Codex OAuth frontier fallback → Anthropic OAuth

  WORKER/WATCHER TIER (local LLM primary, OAuth fallback only):
    All others → local/qwen2.5:7b-instruct-q4_K_M
                  → xai-oauth/grok-4.5
                  → openai-codex/gpt-5.6-luna  (cheap OpenAI OAuth local substitute)
                  → anthropic/claude-haiku-4-5 (cheap Claude OAuth final fallback)
    NO OpenRouter in fallback chain — subscription OAuth only.

  LOCKBOX EXCEPTION:
    lockbox → local/llama3.1:8b or qwen2.5 → grok-4.5 → gpt-5.6-luna → claude-haiku-4-5
    (DeepSeek allowed — no PRC restriction applies)

BILLING HARD-GUARD:
  - Verifies auth.json has no Anthropic/xAI/OpenAI API keys (OAuth only)
  - Runs billing_guard.py — aborts on FAIL
  - Removes all OpenRouter entries from worker/watcher fallback chains
  - No metered frontier models anywhere in the config

Usage:
  python scripts/apply_local_llm_routing.py [--dry-run] [--local-model <model>]
"""
from __future__ import annotations
import sys, json, subprocess, shutil
from pathlib import Path
import yaml

# ── Config ────────────────────────────────────────────────────────────────────
HERMES_HOME = Path(r"C:\Users\micha\AppData\Local\hermes")
SCRIPTDIR   = Path(__file__).resolve().parent
DRY         = "--dry-run" in sys.argv

# ── Known local models (added/updated 2026-08-26) ─────────────────────────────
# All of these are available as the LOCAL_MODEL primary for worker bots.
# Specialist models (mistral-nemo-classifier) should NOT be used as general workers.
#
# Context requirement: Hermes minimum is 64K. Models below that cannot be Kanban workers.
#
#  Model                              | Ctx    | Tool calls | Notes
#  -----------------------------------|--------|------------|-----------------------------
#  qwen2.5:7b-instruct-q4_K_M        | 32K ⚠ | Yes        | Fast; CANNOT be Kanban worker
#  llama3.1:8b-instruct-q4_K_M       | 128K   | Yes        | Reliable Kanban worker
#  gemma4:26b                         | 128K+  | Yes        | MoE reasoning; ~4B active
#  mistral-nemo                       | 128K   | Yes        | 12B, strong structured output
#  mistral-nemo-classifier            | 16K    | No         | Specialist: classification only
KNOWN_LOCAL_MODELS = [
    "qwen2.5:7b-instruct-q4_K_M",       # fast rote (ctx too small for kanban worker)
    "llama3.1:8b-instruct-q4_K_M",      # reliable kanban worker (128K ctx)
    "gemma4:26b",                         # reasoning-capable MoE worker
    "mistral-nemo",                       # 12B 128K general purpose
    # mistral-nemo-classifier is specialist-only; don't use as general worker primary
]

# Allow overriding the local model name (e.g. when a new model is pulled)
LOCAL_MODEL = "qwen2.5:7b-instruct-q4_K_M"
for i, arg in enumerate(sys.argv):
    if arg == "--local-model" and i + 1 < len(sys.argv):
        LOCAL_MODEL = sys.argv[i + 1]
        if LOCAL_MODEL == "mistral-nemo-classifier":
            print("ERROR: mistral-nemo-classifier is a specialist (classification-only) model.")
            print("       It should NOT be used as the general worker primary.")
            print("       Use mistral-nemo, gemma4:26b, or llama3.1:8b-instruct-q4_K_M instead.")
            sys.exit(1)

LOCAL_BASE_URL = "http://localhost:11434/v1"

# ── BILLING HARD-GUARD ────────────────────────────────────────────────────────
print("=== BILLING HARD-GUARD ===")
auth = json.loads((HERMES_HOME / "auth.json").read_text(encoding="utf-8"))
pool = auth.get("credential_pool", auth.get("providers", {}))
for provider, creds in pool.items():
    if provider.lower() in ("anthropic", "xai", "xai-oauth", "grok", "openai", "openai-api", "openai-codex"):
        for cred in (creds if isinstance(creds, list) else [creds]):
            if isinstance(cred, dict) and cred.get("type") == "api_key":
                print(f"ABORT: {provider} has API key cred — OAuth only!")
                sys.exit(1)
print("  auth.json: OK (OAuth only)")

guard = SCRIPTDIR / "billing_guard.py"
if guard.exists():
    r = subprocess.run([sys.executable, str(guard),
                        "--hermes-home", str(HERMES_HOME)],
                       capture_output=True, text=True)
    out = (r.stdout + r.stderr).strip()
    if "PASS" in out:
        print("  billing_guard.py: PASS")
    else:
        print(f"  billing_guard.py: FAIL\n{out}")
        sys.exit(1)
print("=== BILLING HARD-GUARD: PASS ===\n")

# ── Check Ollama availability ─────────────────────────────────────────────────
import urllib.request, urllib.error
try:
    resp = urllib.request.urlopen("http://localhost:11434/api/tags", timeout=2)
    tags = json.loads(resp.read())
    available_models: list[str] = [m["name"] for m in tags.get("models", [])]
    ollama_up = True
    print(f"Ollama: UP — {len(available_models)} model(s): {available_models or '(none pulled yet)'}")
    if LOCAL_MODEL not in available_models and available_models:
        LOCAL_MODEL = available_models[0]
        print(f"  → using available model: {LOCAL_MODEL}")
    elif LOCAL_MODEL not in available_models:
        print(f"  ⚠ Local model '{LOCAL_MODEL}' not yet pulled — configuring anyway (will activate on pull)")
except Exception as e:
    ollama_up = False
    print(f"Ollama: DOWN or unreachable ({e}) — configuring anyway (activates when Ollama is up)")

print()

# ── Routing tables ────────────────────────────────────────────────────────────

GROK = {"provider": "xai-oauth", "model": "grok-4.5"}
OPENAI_FRONTIER = {"provider": "openai-codex", "model": "gpt-5.6-sol"}
OPENAI_MID = {"provider": "openai-codex", "model": "gpt-5.6-terra"}
OPENAI_CHEAP = {"provider": "openai-codex", "model": "gpt-5.6-luna"}
CLAUDE_SONNET = {"provider": "anthropic", "model": "claude-sonnet-4-6"}
CLAUDE_HAIKU = {"provider": "anthropic", "model": "claude-haiku-4-5"}

# Decision-making bots: NEVER local LLM. Grok remains highest priority; OpenAI
# frontier sits below Grok and above Anthropic, all via OAuth/subscription.
DECISION_CHAINS = {
    "chief_of_staff": {
        "model": {"default": GROK["model"], "provider": GROK["provider"]},
        "fallback_providers": [dict(OPENAI_FRONTIER), dict(CLAUDE_SONNET)],
    },
}

for _bot in ("marshal", "coding_lt", "ops_lt", "knowledge_lt", "hermes_ai_explorer"):
    DECISION_CHAINS[_bot] = {
        "model": {"default": GROK["model"], "provider": GROK["provider"]},
        "fallback_providers": [dict(OPENAI_FRONTIER), dict(CLAUDE_SONNET)],
    }

# Worker/watcher bots: local LLM primary, OAuth fallback only (NO OpenRouter)
# LockBox is included here — same chain, DeepSeek allowed (PRC restriction removed 2026-08-26)
WORKER_BOTS = [
    "api_watcher",
    "subscription_watcher",
    "firstmate",
    "git_yeoman",
    "passive_watch",
    "research_agent",
    "email_reader",
    "email_drafter",
    "calendar_manager",
    "todoist_manager",
    "finance_reader",
    "vault_librarian",
    "obsidian_archivist",
    "lockbox",
]

WORKER_CHAIN = {
    "model": {"default": LOCAL_MODEL, "provider": "custom", "base_url": LOCAL_BASE_URL},
    "fallback_providers": [
        dict(GROK),
        dict(OPENAI_CHEAP),
        dict(CLAUDE_HAIKU),
        # NO OpenRouter — subscription OAuth is already $0, no metered fallback needed
    ],
}

ALL_CHAINS = {**DECISION_CHAINS, **{b: WORKER_CHAIN for b in WORKER_BOTS}}

# ── Apply to each profile config.yaml ─────────────────────────────────────────
print(f"Applying routing to {len(ALL_CHAINS)} profiles...")
print(f"  Local model: {LOCAL_MODEL} @ {LOCAL_BASE_URL}")
print()

results = {"updated": [], "skipped": [], "missing": []}

for bot_id, chain in ALL_CHAINS.items():
    cfg_path = HERMES_HOME / "profiles" / bot_id / "config.yaml"
    if not cfg_path.exists():
        print(f"  ⚠  {bot_id}: profile not found — skipping")
        results["missing"].append(bot_id)
        continue

    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}

    # Snapshot what's changing
    old_model    = cfg.get("model", {})
    old_fallback = cfg.get("fallback_providers", [])

    # Apply new chain
    cfg["model"] = chain["model"]
    cfg["fallback_providers"] = chain["fallback_providers"]

    tier = "DECISION" if bot_id in DECISION_CHAINS else "WORKER"
    primary = f"{chain['model']['provider']}/{chain['model']['default']}"
    fallback_str = " → ".join(
        f"{f['provider']}/{f['model']}" for f in chain["fallback_providers"]
    )

    if DRY:
        print(f"  [DRY] {bot_id:25} [{tier}]  {primary}  → {fallback_str}")
    else:
        # Backup original
        backup = cfg_path.with_suffix(".yaml.pre-local-llm")
        if not backup.exists():
            shutil.copy2(cfg_path, backup)

        cfg_path.write_text(
            yaml.safe_dump(cfg, sort_keys=False, default_flow_style=False,
                           allow_unicode=True),
            encoding="utf-8"
        )
        print(f"  ✓  {bot_id:25} [{tier}]  {primary}  → {fallback_str}")
        results["updated"].append(bot_id)

print()
if not DRY:
    print(f"Updated:  {len(results['updated'])} profiles")
    print(f"Missing:  {len(results['missing'])} profiles {results['missing'] or ''}")

# ── Post-apply billing guard ───────────────────────────────────────────────────
if not DRY and guard.exists():
    print()
    r = subprocess.run([sys.executable, str(guard),
                        "--hermes-home", str(HERMES_HOME)],
                       capture_output=True, text=True)
    out = (r.stdout + r.stderr).strip()
    print(f"Post-apply billing_guard: {out}")
    if "PASS" not in out:
        print("WARNING: billing guard failed after apply — check configs")
        sys.exit(2)

print()
print("=" * 60)
print("LOCAL LLM ROUTING APPLIED" if not DRY else "DRY RUN COMPLETE")
print()
print("Decision-making tier (subscription always):")
for b in DECISION_CHAINS:
    c = DECISION_CHAINS[b]
    print(f"  {b:25} {c['model']['provider']}/{c['model']['default']}")
print()
print(f"Worker/watcher tier (local LLM primary):")
for b in WORKER_BOTS:
    print(f"  {b:25} custom/{LOCAL_MODEL}")
print()
print("Fallback chain for ALL workers (tool calls / local unavail):")
print("  xai-oauth/grok-4.5  →  openai-codex/gpt-5.6-luna  →  anthropic/claude-haiku-4-5")
print("  NO OpenRouter — subscription OAuth only ($0 marginal)")
print()
if not ollama_up or not (available_models if ollama_up else []):
    print(f"⚠  Ollama has no models pulled yet.")
    print(f"   Pull one to activate local routing:")
    print(f"   ollama pull {LOCAL_MODEL}")
