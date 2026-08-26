#!/usr/bin/env python3
"""local_coding_eval_hard.py — 10 HIGH-DIFFICULTY coding tasks for local models.

Michael's ask: give all local models 10 new high-difficulty tests and report.
Objective, test-driven (real pass/fail via subprocess), fully-specified prompts
(no unstated requirements — that eval bug is fixed). Compared against the Opus
(OAuth) reference which is scored on the identical batteries.

Reuses the runner from local_coding_eval.py (call_ollama, extract_code, run_task).

Usage:
    python local_coding_eval_hard.py --models llama3.1:8b-instruct-q4_K_M,qwen2.5-coder:7b-instruct-q4_K_M
    python local_coding_eval_hard.py --reference-only   # dump for the Opus baseline
"""
from __future__ import annotations

import argparse
import json
import sys
import textwrap
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import local_coding_eval as base  # reuse call_ollama/extract_code/run_task

OUT_DIR = Path(r"C:\Users\micha\carrier_hermes\_agent\local_eval")

HARD_TASKS = [
    {
        "id": "h1_dijkstra",
        "difficulty": "hard",
        "prompt": textwrap.dedent("""\
            Write `shortest_path(graph, start, end)` returning the minimum total
            weight of a path from start to end in a weighted DIRECTED graph, or -1
            if unreachable. `graph` is dict[str, list[tuple[str, int]]] mapping a
            node to (neighbor, weight) pairs; weights are non-negative ints.
            start==end returns 0. Use Dijkstra's algorithm.
            Return ONLY a python code block defining function shortest_path."""),
        "entrypoint": "shortest_path",
        "tests": textwrap.dedent("""\
            from solution import shortest_path
            g = {"a":[("b",1),("c",4)],"b":[("c",2),("d",5)],"c":[("d",1)],"d":[]}
            assert shortest_path(g,"a","d") == 4   # a->b->c->d = 1+2+1
            assert shortest_path(g,"a","a") == 0
            assert shortest_path(g,"d","a") == -1
            assert shortest_path(g,"a","c") == 3
            g2 = {"x":[("y",10)],"y":[("x",10)],"z":[]}
            assert shortest_path(g2,"x","z") == -1
            print("OK")"""),
    },
    {
        "id": "h2_lru_ttl",
        "difficulty": "hard",
        "prompt": textwrap.dedent("""\
            Implement `TTLCache(capacity: int)` — an LRU cache with per-entry TTL.
            Methods:
              - put(key, value, now: float, ttl: float): insert/update; entry
                expires at now+ttl. On overflow evict least-recently-used.
              - get(key, now: float) -> value or None: returns None if absent or
                expired (expired entries are treated as absent and removed). A
                successful get is a use (MRU). Expiry uses strict '>' (an entry at
                exactly its expiry time is still valid).
            Return ONLY a python code block defining class TTLCache."""),
        "entrypoint": "TTLCache",
        "tests": textwrap.dedent("""\
            from solution import TTLCache
            c = TTLCache(2)
            c.put("a",1,now=0.0,ttl=10.0)
            c.put("b",2,now=0.0,ttl=5.0)
            assert c.get("a",now=1.0) == 1
            assert c.get("b",now=5.0) == 2      # exactly at expiry still valid
            assert c.get("b",now=5.01) is None  # expired
            c.put("x",9,now=6.0,ttl=10.0)       # b gone; a still there -> fits
            c.put("y",8,now=6.0,ttl=10.0)       # capacity 2 -> evict LRU (a)
            assert c.get("a",now=6.0) is None
            assert c.get("x",now=6.0) == 9
            assert c.get("y",now=6.0) == 8
            print("OK")"""),
    },
    {
        "id": "h3_wildcard_match",
        "difficulty": "hard",
        "prompt": textwrap.dedent("""\
            Write `is_match(s: str, p: str) -> bool` implementing wildcard pattern
            matching where '?' matches any single char and '*' matches any sequence
            (including empty). The match must cover the ENTIRE string.
            Return ONLY a python code block defining function is_match."""),
        "entrypoint": "is_match",
        "tests": textwrap.dedent("""\
            from solution import is_match
            assert is_match("aa","a") is False
            assert is_match("aa","*") is True
            assert is_match("cb","?a") is False
            assert is_match("adceb","*a*b") is True
            assert is_match("acdcb","a*c?b") is False
            assert is_match("","*") is True
            assert is_match("","") is True
            assert is_match("abc","") is False
            print("OK")"""),
    },
    {
        "id": "h4_median_stream",
        "difficulty": "hard",
        "prompt": textwrap.dedent("""\
            Implement `MedianFinder` with `add(num: float)` and `median() -> float`.
            median() returns the median of all numbers added so far (average of the
            two middle values when the count is even). Must be efficient for many
            adds (use two heaps — O(log n) add, O(1) median).
            Return ONLY a python code block defining class MedianFinder."""),
        "entrypoint": "MedianFinder",
        "tests": textwrap.dedent("""\
            from solution import MedianFinder
            m = MedianFinder()
            m.add(1); assert m.median() == 1
            m.add(2); assert m.median() == 1.5
            m.add(3); assert m.median() == 2
            m.add(100); m.add(-100)
            # sorted: -100,1,2,3,100 -> median 2
            assert m.median() == 2
            print("OK")"""),
    },
    {
        "id": "h5_json_parser",
        "difficulty": "hard",
        "prompt": textwrap.dedent("""\
            Write `parse_json(s: str)` that parses a JSON string into Python objects
            WITHOUT using the json module or eval. Support objects, arrays, strings
            (with \\" \\\\ \\n \\t escapes), integers, floats, true, false, null.
            Whitespace between tokens is allowed. Raise ValueError on malformed input.
            Return ONLY a python code block defining function parse_json."""),
        "entrypoint": "parse_json",
        "tests": textwrap.dedent("""\
            from solution import parse_json
            assert parse_json('{"a": 1, "b": [true, null, "x"]}') == {"a":1,"b":[True,None,"x"]}
            assert parse_json('[1, 2.5, -3]') == [1, 2.5, -3]
            assert parse_json('"he\\\\"llo"') == 'he"llo'
            assert parse_json('  true ') is True
            assert parse_json('{"nested": {"k": [1,2,{"z": false}]}}') == {"nested":{"k":[1,2,{"z":False}]}}
            try:
                parse_json('{"a": }'); assert False
            except ValueError:
                pass
            print("OK")"""),
    },
    {
        "id": "h6_edit_distance",
        "difficulty": "hard",
        "prompt": textwrap.dedent("""\
            Write `edit_distance(a: str, b: str) -> int` returning the Levenshtein
            distance (min single-char insertions, deletions, substitutions to turn
            a into b). Must run in O(len(a)*len(b)).
            Return ONLY a python code block defining function edit_distance."""),
        "entrypoint": "edit_distance",
        "tests": textwrap.dedent("""\
            from solution import edit_distance
            assert edit_distance("kitten","sitting") == 3
            assert edit_distance("","abc") == 3
            assert edit_distance("abc","abc") == 0
            assert edit_distance("flaw","lawn") == 2
            assert edit_distance("intention","execution") == 5
            print("OK")"""),
    },
    {
        "id": "h7_observer",
        "difficulty": "hard",
        "prompt": textwrap.dedent("""\
            Implement an event system `EventBus` with:
              - subscribe(event: str, handler) -> token   (handler is callable(payload))
              - unsubscribe(token) -> None
              - publish(event: str, payload) -> int   (returns number of handlers
                invoked; invokes in subscription order; a handler unsubscribing
                during publish must NOT affect the current publish's handler set).
            Handlers may raise; a raising handler must not stop others, and publish
            still counts it as invoked.
            Return ONLY a python code block defining class EventBus."""),
        "entrypoint": "EventBus",
        "tests": textwrap.dedent("""\
            from solution import EventBus
            bus = EventBus()
            seen = []
            t1 = bus.subscribe("e", lambda p: seen.append(("a",p)))
            def bad(p):
                raise RuntimeError("boom")
            t2 = bus.subscribe("e", bad)
            t3 = bus.subscribe("e", lambda p: seen.append(("c",p)))
            n = bus.publish("e", 42)
            assert n == 3, n
            assert ("a",42) in seen and ("c",42) in seen
            bus.unsubscribe(t2)
            seen.clear()
            n = bus.publish("e", 7)
            assert n == 2
            # unsubscribe during publish doesn't corrupt current run
            token_holder = {}
            def selfremove(p):
                seen.append(("s",p)); bus.unsubscribe(token_holder["t"])
            token_holder["t"] = bus.subscribe("e", selfremove)
            n = bus.publish("e", 1)
            assert n == 3
            print("OK")"""),
    },
    {
        "id": "h8_coin_change",
        "difficulty": "hard",
        "prompt": textwrap.dedent("""\
            Write `coin_change(coins: list[int], amount: int) -> int` returning the
            fewest coins needed to make `amount`, or -1 if impossible. Unlimited
            supply of each coin. amount can be 0 (answer 0).
            Return ONLY a python code block defining function coin_change."""),
        "entrypoint": "coin_change",
        "tests": textwrap.dedent("""\
            from solution import coin_change
            assert coin_change([1,2,5],11) == 3    # 5+5+1
            assert coin_change([2],3) == -1
            assert coin_change([1],0) == 0
            assert coin_change([1,3,4],6) == 2     # 3+3
            assert coin_change([186,419,83,408],6249) == 20
            print("OK")"""),
    },
    {
        "id": "h9_trie",
        "difficulty": "hard",
        "prompt": textwrap.dedent("""\
            Implement a `Trie` (prefix tree) with:
              - insert(word: str)
              - search(word: str) -> bool  (exact word present)
              - starts_with(prefix: str) -> bool
              - count_prefix(prefix: str) -> int  (how many inserted words, counting
                duplicates, share this prefix)
            Return ONLY a python code block defining class Trie."""),
        "entrypoint": "Trie",
        "tests": textwrap.dedent("""\
            from solution import Trie
            t = Trie()
            for w in ["app","apple","apply","apt","bat"]:
                t.insert(w)
            t.insert("app")  # duplicate
            assert t.search("app") is True
            assert t.search("ap") is False
            assert t.starts_with("ap") is True
            assert t.starts_with("ba") is True
            assert t.starts_with("z") is False
            assert t.count_prefix("app") == 4   # app,app,apple,apply
            assert t.count_prefix("ap") == 5
            assert t.count_prefix("bat") == 1
            print("OK")"""),
    },
    {
        "id": "h10_async_scheduler",
        "difficulty": "hard",
        "prompt": textwrap.dedent("""\
            Implement `TaskScheduler` that runs tasks respecting dependencies and a
            max-parallelism limit, deterministically.
              - TaskScheduler(max_parallel: int)
              - add_task(name: str, deps: list[str], duration: int)
              - run() -> list[tuple[str, int, int]]: returns (name, start, end) for
                every task. A task starts as soon as all deps are complete AND a
                worker slot is free. Time is integer; a task occupies a slot for
                [start, start+duration). When multiple tasks are ready and slots
                free at the same time, start them in the order they were added.
                Return the list sorted by (start, add-order).
            Assume a valid DAG. Return ONLY a python code block defining class TaskScheduler."""),
        "entrypoint": "TaskScheduler",
        "tests": textwrap.dedent("""\
            from solution import TaskScheduler
            s = TaskScheduler(max_parallel=2)
            s.add_task("a",[],2)
            s.add_task("b",[],3)
            s.add_task("c",["a"],2)
            s.add_task("d",["a","b"],1)
            res = dict((r[0],(r[1],r[2])) for r in s.run())
            # a,b start at 0 (2 slots). a ends at 2, b ends at 3.
            assert res["a"] == (0,2)
            assert res["b"] == (0,3)
            # c dep a(done@2), slot free@2 -> start 2 end 4
            assert res["c"] == (2,4)
            # d deps a@2 and b@3 -> ready@3, slot free (a done@2,c uses one@2) at 3 -> start3 end4
            assert res["d"] == (3,4)
            print("OK")"""),
    },
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="llama3.1:8b-instruct-q4_K_M")
    ap.add_argument("--reference-only", action="store_true")
    args = ap.parse_args()

    if args.reference_only:
        for t in HARD_TASKS:
            print(f"\n### {t['id']} ({t['difficulty']}) entry={t['entrypoint']}")
            print(t["prompt"])
            print("--- tests ---\n" + t["tests"])
        return 0

    # monkeypatch the base runner's task list to our hard set
    base.TASKS = HARD_TASKS
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    all_results, scoreboard = [], {}
    for model in models:
        print(f"\n===== {model} =====")
        passed = 0
        for task in HARD_TASKS:
            r = base.run_task(model, task)
            all_results.append(r)
            mark = "✅" if r["passed"] else ("⚠️" if r["syntax_ok"] else "❌")
            print(f"  {mark} {r['task']:20} {r['latency_s']:>6}s  {r['detail'][:55]}")
            passed += 1 if r["passed"] else 0
        scoreboard[model] = f"{passed}/{len(HARD_TASKS)}"
    print("\n===== HARD SCOREBOARD =====")
    for m, s in scoreboard.items():
        print(f"  {m:42} {s}")
    out = OUT_DIR / f"eval_hard_{int(time.time())}.json"
    out.write_text(json.dumps({"scoreboard": scoreboard, "results": all_results}, indent=2), encoding="utf-8")
    print(f"\nartifact: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
