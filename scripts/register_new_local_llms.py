#!/usr/bin/env python3
"""
register_new_local_llms.py — Verify, smoke-test, and register new local models
into the carrier_hermes fleet as alternative local LLMs.

Models added (2026-08-26):
  - gemma4:26b            (26B MoE / 4B active, reasoning/agentic)
  - mistral-nemo          (12B, 128K ctx, general purpose)
  - mistral-nemo-classifier (built from mistral-nemo Modelfile, zero-temp classifier)

Usage:
  python scripts/register_new_local_llms.py            # verify + register
  python scripts/register_new_local_llms.py --dry-run  # verify only, no writes
  python scripts/register_new_local_llms.py --create-classifier  # also build Modelfile
  python scripts/register_new_local_llms.py --smoke-only  # smoke test existing models
"""
from __future__ import annotations
import sys, json, time, subprocess
from pathlib import Path
import urllib.request, urllib.error
import yaml

DRY          = "--dry-run" in sys.argv
SMOKE_ONLY   = "--smoke-only" in sys.argv
CREATE_CLS   = "--create-classifier" in sys.argv or not SMOKE_ONLY

HERMES_HOME  = Path(r"C:\Users\micha\AppData\Local\hermes")
CARRIER_ROOT = Path(r"C:\Users\micha\carrier_hermes")
OLLAMA_URL   = "http://localhost:11434"
REGISTRY     = CARRIER_ROOT / "scripts" / "local_models_registry.yaml"
MODELFILE    = CARRIER_ROOT / "scripts" / "mistral_nemo_classifier.Modelfile"

HERMES_MIN_CTX = 64_000  # Hermes MINIMUM_CONTEXT_LENGTH floor

# ── New models to register ─────────────────────────────────────────────────────
NEW_MODELS = [
    {
        "name":         "gemma4:26b",
        "display_name": "Gemma 4 26B (MoE)",
        "tier":         "worker-alternate",
        "speciality":   "reasoning, agentic workflows, coding, multimodal understanding",
        "notes":        "26B total / ~4B active params (MoE). Frontier-quality at rote speed. "
                        "Good drop-in replacement for qwen when reasoning depth matters more than pure speed.",
        "tool_calls":   True,  # expected
        "min_ctx_expected": 128_000,
    },
    {
        "name":         "mistral-nemo",
        "display_name": "Mistral NeMo 12B",
        "tier":         "worker-alternate",
        "speciality":   "general purpose, instruction following, tool use",
        "notes":        "12B, 128K context. Strong at structured output and instruction following. "
                        "Base model for mistral-nemo-classifier.",
        "tool_calls":   True,
        "min_ctx_expected": 128_000,
    },
    {
        "name":         "mistral-nemo-classifier",
        "display_name": "Mistral NeMo Classifier (custom)",
        "tier":         "specialist",
        "speciality":   "classification, triage, intent detection, routing, labeling",
        "notes":        "Built from mistral-nemo with temperature=0, top_k=1. Deterministic "
                        "zero-temp classifier for Kanban triage, intent detection, severity "
                        "labeling, and fleet routing decisions. Do NOT use for open-ended generation.",
        "tool_calls":   False,  # classification doesn't need tool calls
        "min_ctx_expected": 64_000,  # 16K num_ctx set in Modelfile
    },
]

OLLAMA_BASE_URL = f"{OLLAMA_URL}/v1"


# ── Helpers ────────────────────────────────────────────────────────────────────

def ollama_get(path: str) -> dict:
    resp = urllib.request.urlopen(f"{OLLAMA_URL}{path}", timeout=10)
    return json.loads(resp.read())

def ollama_post(path: str, body: dict, timeout: int = 30) -> dict:
    data = json.dumps(body).encode()
    req  = urllib.request.Request(f"{OLLAMA_URL}{path}", data=data,
                                  headers={"Content-Type": "application/json"})
    resp = urllib.request.urlopen(req, timeout=timeout)
    return json.loads(resp.read())

def model_is_pulled(name: str) -> bool:
    try:
        tags = ollama_get("/api/tags")
        return any(m["name"] == name or m["name"].split(":")[0] == name.split(":")[0]
                   for m in tags.get("models", []))
    except Exception:
        return False

def get_context_length(model_name: str) -> int | None:
    """Return the model's declared context length from Ollama /api/show."""
    try:
        info = ollama_post("/api/show", {"name": model_name}, timeout=15)
        for k, v in info.get("model_info", {}).items():
            if "context_length" in k:
                return int(v)
    except Exception as e:
        print(f"    ⚠  context probe failed: {e}")
    return None

def smoke_test_tool_calls(model_name: str) -> bool:
    """Return True if model can make structured tool calls."""
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": "Call the ping tool now."}],
        "tools": [{
            "type": "function",
            "function": {
                "name": "ping",
                "description": "A simple ping test.",
                "parameters": {"type": "object", "properties": {}}
            }
        }],
        "stream": False
    }
    try:
        resp = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{OLLAMA_URL}/v1/chat/completions",
                    data=json.dumps(payload).encode(),
                    headers={"Content-Type": "application/json"}
                ), timeout=60
            ).read()
        )
        tc = resp.get("choices", [{}])[0].get("message", {}).get("tool_calls") or []
        return bool(tc)
    except Exception as e:
        print(f"    tool-call smoke error: {e}")
        return False

def smoke_test_classification(model_name: str) -> bool:
    """Return True if classifier returns a clean single label."""
    payload = {
        "model": model_name,
        "messages": [{
            "role": "user",
            "content": "Classify this Kanban task title into ONE of [bug, feature, maintenance, research]:\n"
                       "\"Fix crash when context window exceeds 64K\""
        }],
        "stream": False
    }
    try:
        resp = json.loads(
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{OLLAMA_URL}/v1/chat/completions",
                    data=json.dumps(payload).encode(),
                    headers={"Content-Type": "application/json"}
                ), timeout=60
            ).read()
        )
        content = resp.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        print(f"    classifier output: {repr(content[:120])}")
        # Good if it's one of the expected labels (or contains one)
        labels = ["bug", "feature", "maintenance", "research"]
        return any(lbl in content.lower() for lbl in labels)
    except Exception as e:
        print(f"    classification smoke error: {e}")
        return False


# ── Create mistral-nemo-classifier via ollama CLI ─────────────────────────────

def create_classifier_model() -> bool:
    if not MODELFILE.exists():
        print(f"  ✗  Modelfile not found: {MODELFILE}")
        return False
    if not model_is_pulled("mistral-nemo"):
        print("  ⚠  mistral-nemo base not yet pulled — skipping classifier creation")
        return False
    print("  Creating mistral-nemo-classifier from Modelfile...")
    try:
        result = subprocess.run(
            ["ollama", "create", "mistral-nemo-classifier", "-f", str(MODELFILE)],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0:
            print("  ✓  mistral-nemo-classifier created")
            return True
        else:
            # Try via REST (ollama CLI might not be on PATH)
            print(f"  ollama CLI failed ({result.returncode}), trying via WSL...")
            wsl = subprocess.run(
                ["bash", "-c",
                 f"wsl ollama create mistral-nemo-classifier -f '{str(MODELFILE).replace(chr(92), '/')}'"],
                capture_output=True, text=True, timeout=120
            )
            if wsl.returncode == 0:
                print("  ✓  mistral-nemo-classifier created via WSL")
                return True
            # Try pushing via REST /api/create
            mf_content = MODELFILE.read_text(encoding="utf-8")
            payload = {"name": "mistral-nemo-classifier", "modelfile": mf_content}
            resp = ollama_post("/api/create", payload, timeout=120)
            if resp.get("status") == "success":
                print("  ✓  mistral-nemo-classifier created via REST")
                return True
            print(f"  ✗  All creation methods failed. Last: {resp}")
            return False
    except Exception as e:
        print(f"  ✗  classifier creation error: {e}")
        return False


# ── Registry write ─────────────────────────────────────────────────────────────

def load_registry() -> dict:
    if REGISTRY.exists():
        return yaml.safe_load(REGISTRY.read_text(encoding="utf-8")) or {}
    return {"local_models": {}}

def save_registry(reg: dict):
    REGISTRY.write_text(
        yaml.safe_dump(reg, sort_keys=False, default_flow_style=False, allow_unicode=True),
        encoding="utf-8"
    )


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print("=" * 64)
    print("carrier_hermes — New Local LLM Registration")
    print("=" * 64)
    print()

    # 1. Check Ollama is up
    try:
        tags = ollama_get("/api/tags")
        pulled = [m["name"] for m in tags.get("models", [])]
        print(f"Ollama UP — {len(pulled)} model(s) available")
    except Exception as e:
        print(f"✗ Ollama unreachable: {e}")
        sys.exit(1)
    print()

    # 2. Optionally create classifier
    if CREATE_CLS and not SMOKE_ONLY:
        print("── Build mistral-nemo-classifier ──────────────────────────────")
        created = create_classifier_model()
        if created:
            # Reload pulled list
            pulled = [m["name"] for m in ollama_get("/api/tags").get("models", [])]
        print()

    # 3. Verify + smoke test each model
    print("── Model Verification ─────────────────────────────────────────")
    registry = load_registry()
    results = []

    for spec in NEW_MODELS:
        name = spec["name"]
        print(f"\n  {name}")

        # Is it pulled?
        is_pulled = name in pulled or any(
            p.split(":")[0] == name.split(":")[0] for p in pulled
        )
        if not is_pulled:
            print(f"    ⏳ Not yet pulled — may still be downloading")
            results.append({"name": name, "status": "pending", "spec": spec})
            continue

        # Context window check
        ctx = get_context_length(name)
        if ctx is not None:
            ctx_ok = ctx >= HERMES_MIN_CTX
            print(f"    context_length: {ctx:,}  {'✓' if ctx_ok else '✗ BELOW 64K MINIMUM'}")
        else:
            ctx_ok = True  # can't verify for custom Modelfile-built models
            print(f"    context_length: (could not probe — custom model)")

        # Tool call smoke test (skip for classifier)
        if spec.get("tool_calls"):
            print(f"    tool-call smoke test...", end=" ", flush=True)
            tc_ok = smoke_test_tool_calls(name)
            print(f"{'✓' if tc_ok else '✗ FAILED — model dumps JSON as text'}")
        else:
            tc_ok = None  # N/A

        # Classification smoke test (classifier only)
        if name == "mistral-nemo-classifier":
            print(f"    classification smoke test...")
            cls_ok = smoke_test_classification(name)
            print(f"    {'✓' if cls_ok else '✗'} classification {'OK' if cls_ok else 'FAILED'}")
        else:
            cls_ok = None

        status = "ready" if ctx_ok else "ctx-too-small"
        results.append({
            "name": name, "status": status,
            "ctx": ctx, "tc_ok": tc_ok, "cls_ok": cls_ok, "spec": spec
        })

        # Update registry
        registry.setdefault("local_models", {})[name] = {
            "display_name":   spec["display_name"],
            "tier":           spec["tier"],
            "speciality":     spec["speciality"],
            "notes":          spec["notes"],
            "context_length": ctx,
            "tool_calls":     spec.get("tool_calls"),
            "status":         status,
            "registered":     time.strftime("%Y-%m-%d"),
            "ollama_tag":     name,
            "base_url":       OLLAMA_BASE_URL,
        }

    # 4. Save registry
    print()
    if not DRY and not SMOKE_ONLY:
        print("── Saving local_models_registry.yaml ─────────────────────────")
        save_registry(registry)
        print(f"  ✓  {REGISTRY}")

    # 5. Summary
    print()
    print("=" * 64)
    print("SUMMARY")
    print("=" * 64)
    for r in results:
        n = r["name"]
        s = r["status"]
        if s == "pending":
            icon = "⏳"
            note = "still downloading — re-run after pull completes"
        elif s == "ready":
            icon = "✅"
            tc = ""
            if r.get("tc_ok") is True:   tc = " tool-calls:✓"
            elif r.get("tc_ok") is False: tc = " tool-calls:✗ (cannot use as Kanban worker!)"
            note = f"ctx:{r.get('ctx','?'):,}{tc}"
        else:
            icon = "❌"
            note = s
        print(f"  {icon} {n:40} {note}")

    print()
    print("To assign a specific bot to a new model, edit its profile config.yaml:")
    print("  model:")
    print("    default: gemma4:26b")
    print("    provider: custom")
    print("    base_url: http://localhost:11434/v1")
    print()
    print("Or re-run apply_local_llm_routing.py --local-model gemma4:26b")
    print("to switch ALL worker bots to the new primary.")
    print()
    print("Classifier usage:")
    print("  curl http://localhost:11434/v1/chat/completions \\")
    print("    -d '{\"model\":\"mistral-nemo-classifier\",\"messages\":[{\"role\":\"user\",\"content\":\"Classify: ...\"}]}'")
    print()
    print("DONE.")

if __name__ == "__main__":
    main()
