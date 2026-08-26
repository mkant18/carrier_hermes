#!/usr/bin/env python3
"""local_llm_health.py — Health check for the local Ollama LLM.

Exit codes:
    0 = healthy (state file says online AND /api/tags responds 200)
    1 = not available (Hermes should fall back to the next provider)

Usage:
    python scripts/local_llm_health.py
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

STATE_FILE = "C:/Users/micha/AppData/Local/hermes/carrier/local_llm_state.json"
OLLAMA_TAGS_URL = "http://localhost:11434/api/tags"
MODEL = "qwen2.5:7b-instruct-q4_K_M"


def main() -> int:
    state_path = Path(STATE_FILE)
    if not state_path.exists():
        print("LOCAL_LLM: OFFLINE")
        return 1

    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        print("LOCAL_LLM: OFFLINE")
        return 1

    if state.get("status") != "online":
        print("LOCAL_LLM: OFFLINE")
        return 1

    try:
        with urllib.request.urlopen(OLLAMA_TAGS_URL, timeout=3) as resp:
            if resp.status == 200:
                model = state.get("model", MODEL)
                print(f"LOCAL_LLM: ONLINE model={model}")
                return 0
            print("LOCAL_LLM: UNREACHABLE")
            return 1
    except (urllib.error.URLError, OSError, TimeoutError):
        print("LOCAL_LLM: UNREACHABLE")
        return 1


if __name__ == "__main__":
    sys.exit(main())
