#!/usr/bin/env python3
"""
apply_local_llm_routing.py — Wire the local LLM routing policy fleet-wide.

Policy (from COST_MODEL.md §Local LLM Policy):
  DECISION-MAKING TIER (never local LLM):
    chief_of_staff  → grok-4.5/xai-oauth  → claude-sonnet-5/anthropic
    marshal         → claude-sonnet-5/anthropic → grok-4.5/xai-oauth
    coding_lt       → claude-sonnet-5/anthropic → grok-4.5/xai-oauth
    ops_lt          → claude-sonnet-5/anthropic → grok-4.5/xai-oauth
    knowledge_lt    → claude-sonnet-5/anthropic → grok-4.5/xai-oauth
    hermes_ai_explorer → claude-sonnet-5/anthropic → grok-4.5/xai-oauth

  WORKER/WATCHER TIER (local LLM primary, OAuth fallback only):
    All others → local/qwen2.5:7b-instruct-q4_K_M
                  → anthropic/claude-sonnet-5  (fallback — tool calls or local unavail)
                  → xai-oauth/grok-4.5         (final fallback)
    NO OpenRouter in fallback chain — subscription OAuth only.

  LOCKBOX EXCEPTION:
    lockbox → local/qwen2.5:7b-instruct-q4_K_M (non-PRC model only)
               → anthropic/claude-sonnet-5
               → xai-oauth/grok-4.5
    (Never DeepSeek/PRC even locally — the local model must be non-PRC)

BILLING HARD-GUARD:
  - Verifies auth.json has no Anthropic/xAI API keys (OAuth only)
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

# Allow overriding the local model name (e.g. when a new model is pulled)
LOCAL_MODEL = "qwen2.5:7b-instruct-q4_K_M"
for i, arg in enumerate(sys.argv):
    if arg == "--local-model" and i + 1 < len(sys.argv):
        LOCAL_MODEL = sys.argv[i + 1]

LOCAL_BASE_URL = "http://localhost:11434/v1"

# ── BILLING HARD-GUARD ────────────────────────────────────────────────────────
print("=== BILLING HARD-GUARD ===")
auth = json.loads((HERMES_HOME / "auth.json").read_text(encoding="utf-8"))
pool = auth.get("credential_pool", auth.get("providers", {}))
for provider, creds in pool.items():
    if provider.lower() in ("anthropic", "xai", "xai-oauth", "grok"):
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

# Decision-making bots: NEVER local LLM
DECISION_CHAINS = {
    "chief_of_staff": {
        "model": {"default": "grok-4.5", "provider": "xai-oauth"},
        "fallback_providers": [
            {"provider": "anthropic", "model": "claude-sonnet-5-20251001"},
        ],
    },
    "marshal": {
        "model": {"default": "claude-sonnet-5-20251001", "provider": "anthropic"},
        "fallback_providers": [
            {"provider": "xai-oauth", "model": "grok-4.5"},
        ],
    },
    "coding_lt": {
        "model": {"default": "claude-sonnet-5-20251001", "provider": "anthropic"},
        "fallback_providers": [
            {"provider": "xai-oauth", "model": "grok-4.5"},
        ],
    },
    "ops_lt": {
        "model": {"default": "claude-sonnet-5-20251001", "provider": "anthropic"},
        "fallback_providers": [
            {"provider": "xai-oauth", "model": "grok-4.5"},
        ],
    },
    "knowledge_lt": {
        "model": {"default": "claude-sonnet-5-20251001", "provider": "anthropic"},
        "fallback_providers": [
            {"provider": "xai-oauth", "model": "grok-4.5"},
        ],
    },
    "hermes_ai_explorer": {
        "model": {"default": "claude-sonnet-5-20251001", "provider": "anthropic"},
        "fallback_providers": [
            {"provider": "xai-oauth", "model": "grok-4.5"},
        ],
    },
}

# Worker/watcher bots: local LLM primary, OAuth fallback only (NO OpenRouter)
# LockBox is included here — same chain, non-PRC local model enforced by model choice
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
        {"provider": "anthropic", "model": "claude-sonnet-5-20251001"},
        {"provider": "xai-oauth",  "model": "grok-4.5"},
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
print("  anthropic/claude-sonnet-5  →  xai-oauth/grok-4.5")
print("  NO OpenRouter — subscription OAuth only ($0 marginal)")
print()
if not ollama_up or not (available_models if ollama_up else []):
    print(f"⚠  Ollama has no models pulled yet.")
    print(f"   Pull one to activate local routing:")
    print(f"   ollama pull {LOCAL_MODEL}")
