#!/usr/bin/env python3
"""local_coding_eval.py — objective coding-quality eval for local models.

Purpose (Michael's ask): don't trust "the local model replied" — PROVE the local
models produce GOOD coding output by running their code against real unit tests,
and compare to an Opus (OAuth) reference.

How it works:
  1. A fixed suite of CODING TASKS, each with:
       - a prompt (the coding problem)
       - a hidden pytest-style test battery (objective pass/fail)
       - the canonical function/signature the solution must expose
  2. For each MODEL under test (llama3.1, qwen2.5, qwen2.5-coder, ...):
       - send the prompt to Ollama's /v1/chat/completions (raw — bypasses the
         Hermes 64K floor so we can eval any local model, even 32K-declared qwen)
       - extract the code block
       - execute it in an isolated subprocess against the task's tests
       - record: passed/total, syntax-ok, runtime, any error
  3. Emit a scoreboard + a JSON artifact. The OPUS REFERENCE column is filled in
     separately by the parent agent (this session, OAuth) solving the SAME tasks,
     so we compare local-model pass-rates against the Opus baseline on identical
     objective tests.

This is deliberately test-driven: a model's output is "good" iff it PASSES THE
TESTS, not iff it looks plausible. That removes eyeballing bias.

Usage:
    python local_coding_eval.py --models llama3.1:8b-instruct-q4_K_M,qwen2.5-coder:7b-instruct-q4_K_M
    python local_coding_eval.py --list          # list tasks
    python local_coding_eval.py --reference-only # print tasks for the Opus baseline

Zero paid tokens: local models via Ollama (free), Opus reference done by the
already-running OAuth session (no API key).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import textwrap
import time
import urllib.request
from pathlib import Path

OLLAMA_URL = "http://localhost:11434/v1/chat/completions"
HPY = sys.executable
OUT_DIR = Path(r"C:\Users\micha\carrier_hermes\_agent\local_eval")

# ─── Task suite ───────────────────────────────────────────────────────────────
# Each task: id, difficulty, prompt, entrypoint (symbol the tests import), tests.
# Tests are a self-contained python snippet that imports `solution` and asserts.

TASKS = [
    {
        "id": "t1_lru_cache",
        "difficulty": "medium",
        "prompt": textwrap.dedent("""\
            Write a Python class `LRUCache` implementing a Least-Recently-Used cache.
            Requirements:
              - `LRUCache(capacity: int)` constructor.
              - `get(key: int) -> int` returns the value or -1 if absent; a get
                counts as a use (most-recently-used).
              - `put(key: int, value: int) -> None` inserts/updates; if over
                capacity, evict the least-recently-used key.
              - All operations must be O(1) average.
            Return ONLY a python code block defining class LRUCache."""),
        "entrypoint": "LRUCache",
        "tests": textwrap.dedent("""\
            from solution import LRUCache
            c = LRUCache(2)
            c.put(1,1); c.put(2,2)
            assert c.get(1) == 1          # 1 used
            c.put(3,3)                    # evicts 2 (LRU)
            assert c.get(2) == -1
            c.put(4,4)                    # evicts 1
            assert c.get(1) == -1
            assert c.get(3) == 3
            assert c.get(4) == 4
            # update existing key doesn't grow size
            c2 = LRUCache(1)
            c2.put(5,5); c2.put(5,6)
            assert c2.get(5) == 6
            print("OK")"""),
    },
    {
        "id": "t2_json_flatten",
        "difficulty": "medium",
        "prompt": textwrap.dedent("""\
            Write a Python function `flatten(d: dict, sep: str = '.') -> dict` that
            flattens a nested dict into a single-level dict where nested keys are
            joined by `sep`. Lists are flattened using their integer index.
            Example: {"a": {"b": 1}, "c": [10, 20]} with sep='.' ->
              {"a.b": 1, "c.0": 10, "c.1": 20}
            Return ONLY a python code block defining function flatten."""),
        "entrypoint": "flatten",
        "tests": textwrap.dedent("""\
            from solution import flatten
            assert flatten({"a": {"b": 1}, "c": [10, 20]}) == {"a.b":1,"c.0":10,"c.1":20}
            assert flatten({"x": {"y": {"z": 5}}}) == {"x.y.z": 5}
            assert flatten({}) == {}
            assert flatten({"a": 1}, sep="/") == {"a": 1}
            assert flatten({"a": [{"b": 1}]}) == {"a.0.b": 1}
            print("OK")"""),
    },
    {
        "id": "t3_interval_merge",
        "difficulty": "medium",
        "prompt": textwrap.dedent("""\
            Write a Python function `merge_intervals(intervals: list[list[int]]) ->
            list[list[int]]` that merges all overlapping intervals and returns them
            sorted by start. Touching intervals (e.g. [1,2] and [2,3]) merge.
            Example: [[1,3],[2,6],[8,10],[15,18]] -> [[1,6],[8,10],[15,18]]
            Return ONLY a python code block defining function merge_intervals."""),
        "entrypoint": "merge_intervals",
        "tests": textwrap.dedent("""\
            from solution import merge_intervals
            assert merge_intervals([[1,3],[2,6],[8,10],[15,18]]) == [[1,6],[8,10],[15,18]]
            assert merge_intervals([[1,4],[4,5]]) == [[1,5]]
            assert merge_intervals([]) == []
            assert merge_intervals([[1,4],[0,4]]) == [[0,4]]
            assert merge_intervals([[1,4],[2,3]]) == [[1,4]]
            print("OK")"""),
    },
    {
        "id": "t4_thread_safe_counter",
        "difficulty": "hard",
        "prompt": textwrap.dedent("""\
            Write a thread-safe Python class `Counter` with methods `increment()`,
            `decrement()`, and `value` (property) returning the current count.
            It must be correct under concurrent access from many threads.
            Return ONLY a python code block defining class Counter."""),
        "entrypoint": "Counter",
        "tests": textwrap.dedent("""\
            from solution import Counter
            import threading
            c = Counter()
            def work():
                for _ in range(10000):
                    c.increment()
            ts = [threading.Thread(target=work) for _ in range(8)]
            [t.start() for t in ts]; [t.join() for t in ts]
            assert c.value == 80000, f"race! got {c.value}"
            c.decrement()
            assert c.value == 79999
            print("OK")"""),
    },
    {
        "id": "t5_topo_sort",
        "difficulty": "hard",
        "prompt": textwrap.dedent("""\
            Write a Python function `topo_sort(graph: dict[str, list[str]]) ->
            list[str] | None` returning a topological ordering of the DAG (keys are
            nodes, values are lists of nodes they point to). Return None if the graph
            has a cycle. Any valid ordering is acceptable.
            Return ONLY a python code block defining function topo_sort."""),
        "entrypoint": "topo_sort",
        "tests": textwrap.dedent("""\
            from solution import topo_sort
            g = {"a":["b","c"],"b":["d"],"c":["d"],"d":[]}
            order = topo_sort(g)
            assert order is not None
            pos = {n:i for i,n in enumerate(order)}
            for u,vs in g.items():
                for v in vs:
                    assert pos[u] < pos[v], f"{u} before {v} violated"
            assert set(order) == set(g)
            # cycle -> None
            assert topo_sort({"a":["b"],"b":["a"]}) is None
            print("OK")"""),
    },
    {
        "id": "t6_expr_eval",
        "difficulty": "hard",
        "prompt": textwrap.dedent("""\
            Write `evaluate(expr: str) -> float` that evaluates an arithmetic
            expression string supporting + - * / , parentheses, unary minus, and
            floating point numbers, with correct operator precedence and left
            associativity. Do NOT use eval/exec. Division is real (float) division.
            Examples: evaluate("2+3*4")==14.0, evaluate("(2+3)*4")==20.0,
            evaluate("-3+5")==2.0, evaluate("2*-(1+2)")==-6.0.
            Raise ValueError on malformed input.
            Return ONLY a python code block defining function evaluate."""),
        "entrypoint": "evaluate",
        "tests": textwrap.dedent("""\
            from solution import evaluate
            import math
            assert math.isclose(evaluate("2+3*4"), 14.0)
            assert math.isclose(evaluate("(2+3)*4"), 20.0)
            assert math.isclose(evaluate("-3+5"), 2.0)
            assert math.isclose(evaluate("2*-(1+2)"), -6.0)
            assert math.isclose(evaluate("10/4"), 2.5)
            assert math.isclose(evaluate("1+2-3+4"), 4.0)
            assert math.isclose(evaluate("2*(3+(4*5))"), 46.0)
            try:
                evaluate("2+*3"); assert False, "should raise"
            except ValueError:
                pass
            print("OK")"""),
    },
    {
        "id": "t7_token_bucket",
        "difficulty": "hard",
        "prompt": textwrap.dedent("""\
            Implement a token-bucket rate limiter class `RateLimiter(rate: float,
            capacity: float)` where `rate` is tokens added per second and `capacity`
            is the max tokens. Method `allow(now: float, cost: float = 1.0) -> bool`
            returns True and consumes `cost` tokens if at least `cost` are available
            at time `now` (seconds), else returns False and consumes nothing. Tokens
            refill continuously based on elapsed time since the last call, capped at
            capacity. The bucket starts full. `now` is monotonic non-decreasing.
            Return ONLY a python code block defining class RateLimiter."""),
        "entrypoint": "RateLimiter",
        "tests": textwrap.dedent("""\
            from solution import RateLimiter
            r = RateLimiter(rate=10.0, capacity=5.0)  # starts full=5
            assert r.allow(0.0) is True   # 4 left
            assert r.allow(0.0, 4.0) is True  # 0 left
            assert r.allow(0.0) is False  # empty
            assert r.allow(0.5) is True   # +5 tokens (0.5*10) capped at 5 -> 5, consume1 ->4
            assert r.allow(0.5, 5.0) is False  # only 4 available
            assert r.allow(1.0, 5.0) is True   # refilled to cap 5
            print("OK")"""),
    },
]


# ─── Model invocation ─────────────────────────────────────────────────────────

def call_ollama(model: str, prompt: str, timeout: int = 180) -> tuple[str, float, str]:
    """Return (content, latency_s, error)."""
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": "You are an expert Python engineer. "
             "Return ONLY a single ```python code block with the requested "
             "definition and any needed imports. No prose."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 1200,
    }).encode()
    req = urllib.request.Request(OLLAMA_URL, data=payload,
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
        content = data["choices"][0]["message"]["content"]
        return content, round(time.time() - t0, 1), ""
    except Exception as e:
        return "", round(time.time() - t0, 1), str(e)[:200]


def extract_code(text: str) -> str:
    """Pull the python code out of a model reply."""
    m = re.search(r"```(?:python)?\s*\n(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1)
    # no fence — assume whole thing is code
    return text


# ─── Test execution ───────────────────────────────────────────────────────────

def run_task(model: str, task: dict) -> dict:
    content, latency, err = call_ollama(model, task["prompt"])
    result = {"task": task["id"], "difficulty": task["difficulty"],
              "model": model, "latency_s": latency, "call_error": err,
              "syntax_ok": False, "passed": False, "detail": ""}
    if err:
        result["detail"] = f"call failed: {err}"
        return result

    code = extract_code(content)
    with tempfile.TemporaryDirectory() as td:
        sol = Path(td) / "solution.py"
        sol.write_text(code, encoding="utf-8")
        test = Path(td) / "run_test.py"
        test.write_text(task["tests"], encoding="utf-8")
        # syntax check
        sc = subprocess.run([HPY, "-c", f"compile(open(r'{sol}').read(),'s','exec')"],
                            capture_output=True, text=True)
        if sc.returncode != 0:
            result["detail"] = "syntax error: " + (sc.stderr or "")[-160:]
            return result
        result["syntax_ok"] = True
        # run tests
        try:
            tr = subprocess.run([HPY, str(test)], cwd=td, capture_output=True,
                                text=True, timeout=30)
        except subprocess.TimeoutExpired:
            result["detail"] = "TIMEOUT (likely infinite loop in generated code)"
            return result
        if tr.returncode == 0 and "OK" in tr.stdout:
            result["passed"] = True
            result["detail"] = "all asserts passed"
        else:
            result["detail"] = ("test fail: " +
                                ((tr.stderr or tr.stdout) or "")[-200:])
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="llama3.1:8b-instruct-q4_K_M",
                    help="comma-separated Ollama model tags")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--reference-only", action="store_true",
                    help="print tasks for the Opus baseline")
    args = ap.parse_args()

    if args.list or args.reference_only:
        for t in TASKS:
            print(f"\n### {t['id']} ({t['difficulty']}) — entrypoint {t['entrypoint']}")
            print(t["prompt"])
            if args.reference_only:
                print("--- tests ---\n" + t["tests"])
        return 0

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    all_results = []
    scoreboard = {}

    for model in models:
        print(f"\n===== {model} =====")
        passed = 0
        for task in TASKS:
            r = run_task(model, task)
            all_results.append(r)
            mark = "✅" if r["passed"] else ("⚠️" if r["syntax_ok"] else "❌")
            print(f"  {mark} {r['task']:22} {r['difficulty']:6} "
                  f"{r['latency_s']:>5}s  {r['detail'][:60]}")
            passed += 1 if r["passed"] else 0
        scoreboard[model] = f"{passed}/{len(TASKS)}"

    print("\n===== SCOREBOARD (objective pass rate) =====")
    for m, s in scoreboard.items():
        print(f"  {m:40} {s}")

    out = OUT_DIR / f"eval_{int(time.time())}.json"
    out.write_text(json.dumps({"scoreboard": scoreboard, "results": all_results},
                              indent=2), encoding="utf-8")
    print(f"\nartifact: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
