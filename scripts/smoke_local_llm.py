#!/usr/bin/env python3
"""smoke_local_llm.py — one-shot smoke test against the local Ollama server.

POSTs a trivial chat completion request to the OpenAI-compatible endpoint
and verifies a 200 response with a non-empty message content.

Exit codes:
    0 = success
    1 = failure (HTTP error, timeout, malformed response, empty content)

Usage:
    python scripts/smoke_local_llm.py
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

CHAT_URL = "http://localhost:11434/v1/chat/completions"
MODEL = "qwen2.5:7b-instruct-q4_K_M"
TIMEOUT_S = 30


def main() -> int:
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": "Say: OK"}],
        "max_tokens": 10,
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        CHAT_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    start = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            elapsed = time.monotonic() - start
            if resp.status != 200:
                print(f"FAIL: HTTP {resp.status}", file=sys.stderr)
                return 1
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        print(f"FAIL: HTTP error {e.code}: {e.read().decode('utf-8', 'ignore')}", file=sys.stderr)
        return 1
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        print(f"FAIL: request error: {e}", file=sys.stderr)
        return 1

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"FAIL: response is not valid JSON: {e}", file=sys.stderr)
        return 1

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        print(f"FAIL: response missing choices[0].message.content: {e}", file=sys.stderr)
        print(f"raw response: {raw}", file=sys.stderr)
        return 1

    if not content or not str(content).strip():
        print("FAIL: empty message content", file=sys.stderr)
        return 1

    usage = data.get("usage") or {}
    completion_tokens = usage.get("completion_tokens")
    toks_per_sec = None
    if isinstance(completion_tokens, (int, float)) and elapsed > 0:
        toks_per_sec = completion_tokens / elapsed

    print(f"PASS: content={content!r}")
    if toks_per_sec is not None:
        print(f"tok/s: {toks_per_sec:.2f} ({completion_tokens} tokens / {elapsed:.2f}s)")
    else:
        print(f"elapsed: {elapsed:.2f}s (no usage.completion_tokens in response)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
