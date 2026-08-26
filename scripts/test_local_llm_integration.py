#!/usr/bin/env python3
"""test_local_llm_integration.py — end-to-end integration test for the
HermesOllama service lifecycle.

Steps:
    1. Start HermesOllama via `sc start`.
    2. Wait up to 60s for GET /api/tags to return 200.
    3. Send a chat completion request and verify the response model field
       contains "qwen2.5".
    4. Stop HermesOllama via `sc stop`.
    5. Wait 5s, then verify /api/tags is no longer reachable (service stopped).

Prints PASS/FAIL for each check. Exits 0 if all checks pass, 1 otherwise.

Note: this only exercises the Ollama service directly. A full bot-level
smoke test (routing an actual Hermes rote-bot request through the fallback
chain to the local provider) requires the model to be pulled first and
should be run manually by the user (see docs / Step 11 in the build plan).
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request

SERVICE_NAME = "HermesOllama"
TAGS_URL = "http://localhost:11434/api/tags"
CHAT_URL = "http://localhost:11434/v1/chat/completions"
MODEL = "qwen2.5:7b-instruct-q4_K_M"
STARTUP_TIMEOUT_S = 60
STARTUP_POLL_INTERVAL_S = 2
POST_STOP_WAIT_S = 5


def sc(cmd: str) -> subprocess.CompletedProcess:
    return subprocess.run(["sc", cmd, SERVICE_NAME], capture_output=True, text=True)


def tags_reachable() -> bool:
    try:
        with urllib.request.urlopen(TAGS_URL, timeout=3) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError, TimeoutError):
        return False


def report(label: str, ok: bool, detail: str = "") -> bool:
    status = "PASS" if ok else "FAIL"
    suffix = f" — {detail}" if detail else ""
    print(f"[{status}] {label}{suffix}")
    return ok


def main() -> int:
    all_ok = True

    print(f"Starting {SERVICE_NAME} ...")
    result = sc("start")
    start_issued = result.returncode == 0 or "already" in (result.stdout + result.stderr).lower()
    all_ok &= report("sc start HermesOllama issued", start_issued, result.stdout.strip() or result.stderr.strip())

    print(f"Waiting up to {STARTUP_TIMEOUT_S}s for /api/tags ...")
    deadline = time.monotonic() + STARTUP_TIMEOUT_S
    became_ready = False
    while time.monotonic() < deadline:
        if tags_reachable():
            became_ready = True
            break
        time.sleep(STARTUP_POLL_INTERVAL_S)
    all_ok &= report("service became ready (/api/tags 200)", became_ready)

    chat_ok = False
    model_ok = False
    model_field = ""
    if became_ready:
        payload = {
            "model": MODEL,
            "messages": [{"role": "user", "content": "Say: OK"}],
            "max_tokens": 10,
        }
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            CHAT_URL, data=body, headers={"Content-Type": "application/json"}, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8")
                chat_ok = resp.status == 200
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
            raw = ""
            chat_ok = False
            print(f"  chat completion request error: {e}")
        all_ok &= report("chat completion request succeeded (HTTP 200)", chat_ok)

        if chat_ok:
            try:
                data = json.loads(raw)
                model_field = str(data.get("model", ""))
                model_ok = "qwen2.5" in model_field
            except json.JSONDecodeError:
                model_ok = False
            all_ok &= report(
                "response model field contains 'qwen2.5'", model_ok, f"model={model_field if chat_ok else ''}"
            )
    else:
        report("chat completion request succeeded (HTTP 200)", False, "skipped — service never became ready")
        report("response model field contains 'qwen2.5'", False, "skipped — service never became ready")
        all_ok = False

    print(f"Stopping {SERVICE_NAME} ...")
    result = sc("stop")
    stop_issued = result.returncode == 0 or "not" in (result.stdout + result.stderr).lower()
    all_ok &= report("sc stop HermesOllama issued", stop_issued, result.stdout.strip() or result.stderr.strip())

    print(f"Waiting {POST_STOP_WAIT_S}s ...")
    time.sleep(POST_STOP_WAIT_S)

    stopped_confirmed = not tags_reachable()
    all_ok &= report("service confirmed stopped (/api/tags unreachable)", stopped_confirmed)

    print()
    if all_ok:
        print("OVERALL: PASS")
        return 0
    print("OVERALL: FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(main())
