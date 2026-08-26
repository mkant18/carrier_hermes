"""opus_reference_solutions.py — Opus (OAuth) reference solutions for the eval.

Solved by the running Opus session (this agent), NOT via API — subscription OAuth
only. Each function/class is the reference implementation for the corresponding
task in local_coding_eval.py, run against the IDENTICAL test batteries so we get a
true Opus baseline pass-rate to compare the local models against.
"""

# ── t1_lru_cache ──────────────────────────────────────────────────────────────
from collections import OrderedDict


class LRUCache:
    def __init__(self, capacity: int):
        self.capacity = capacity
        self._d: "OrderedDict[int,int]" = OrderedDict()

    def get(self, key: int) -> int:
        if key not in self._d:
            return -1
        self._d.move_to_end(key)
        return self._d[key]

    def put(self, key: int, value: int) -> None:
        if key in self._d:
            self._d.move_to_end(key)
        self._d[key] = value
        if len(self._d) > self.capacity:
            self._d.popitem(last=False)


# ── t2_json_flatten ───────────────────────────────────────────────────────────
def flatten(d: dict, sep: str = ".") -> dict:
    out: dict = {}

    def _walk(obj, prefix: str):
        if isinstance(obj, dict):
            if not obj and prefix:
                out[prefix] = obj
                return
            for k, v in obj.items():
                key = f"{prefix}{sep}{k}" if prefix else str(k)
                _walk(v, key)
        elif isinstance(obj, list):
            if not obj and prefix:
                out[prefix] = obj
                return
            for i, v in enumerate(obj):
                key = f"{prefix}{sep}{i}" if prefix else str(i)
                _walk(v, key)
        else:
            out[prefix] = obj

    _walk(d, "")
    return out


# ── t3_interval_merge ─────────────────────────────────────────────────────────
def merge_intervals(intervals: list[list[int]]) -> list[list[int]]:
    if not intervals:
        return []
    s = sorted(intervals, key=lambda x: x[0])
    merged = [list(s[0])]
    for start, end in s[1:]:
        if start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged


# ── t4_thread_safe_counter ────────────────────────────────────────────────────
import threading


class Counter:
    def __init__(self):
        self._lock = threading.Lock()
        self._n = 0

    def increment(self) -> None:
        with self._lock:
            self._n += 1

    def decrement(self) -> None:
        with self._lock:
            self._n -= 1

    @property
    def value(self) -> int:
        with self._lock:
            return self._n


# ── t5_topo_sort ──────────────────────────────────────────────────────────────
def topo_sort(graph: dict) -> list | None:
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n: WHITE for n in graph}
    order: list = []
    has_cycle = False

    def dfs(u):
        nonlocal has_cycle
        color[u] = GRAY
        for v in graph.get(u, []):
            if color.get(v, WHITE) == GRAY:
                has_cycle = True
                return
            if color.get(v, WHITE) == WHITE:
                dfs(v)
                if has_cycle:
                    return
        color[u] = BLACK
        order.append(u)

    for node in graph:
        if color[node] == WHITE:
            dfs(node)
            if has_cycle:
                return None
    return order[::-1]


# ── t6_expr_eval ──────────────────────────────────────────────────────────────
def evaluate(expr: str) -> float:
    tokens = []
    i, n = 0, len(expr)
    while i < n:
        ch = expr[i]
        if ch.isspace():
            i += 1
            continue
        if ch in "+-*/()":
            tokens.append(ch)
            i += 1
        elif ch.isdigit() or ch == ".":
            j = i
            while j < n and (expr[j].isdigit() or expr[j] == "."):
                j += 1
            tokens.append(float(expr[i:j]))
            i = j
        else:
            raise ValueError(f"bad char {ch!r}")

    pos = 0

    def peek():
        return tokens[pos] if pos < len(tokens) else None

    def advance():
        nonlocal pos
        t = tokens[pos]
        pos += 1
        return t

    def parse_expr():  # + -
        val = parse_term()
        while peek() in ("+", "-"):
            op = advance()
            rhs = parse_term()
            val = val + rhs if op == "+" else val - rhs
        return val

    def parse_term():  # * /
        val = parse_factor()
        while peek() in ("*", "/"):
            op = advance()
            rhs = parse_factor()
            val = val * rhs if op == "*" else val / rhs
        return val

    def parse_factor():  # unary minus, parens, number
        t = peek()
        if t == "-":
            advance()
            return -parse_factor()
        if t == "+":
            advance()
            return parse_factor()
        if t == "(":
            advance()
            v = parse_expr()
            if peek() != ")":
                raise ValueError("missing )")
            advance()
            return v
        if isinstance(t, float):
            return advance()
        raise ValueError(f"unexpected {t!r}")

    result = parse_expr()
    if pos != len(tokens):
        raise ValueError("trailing tokens")
    return result


# ── t7_token_bucket ───────────────────────────────────────────────────────────
class RateLimiter:
    def __init__(self, rate: float, capacity: float):
        self.rate = rate
        self.capacity = capacity
        self.tokens = capacity
        self.last = None

    def allow(self, now: float, cost: float = 1.0) -> bool:
        if self.last is not None:
            elapsed = now - self.last
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.last = now
        if self.tokens >= cost:
            self.tokens -= cost
            return True
        return False
