"""opus_reference_hard.py — Opus (OAuth) reference solutions for the 10 hard tasks.

Solved by the running Opus session (subscription OAuth, no API key). Run against
the identical test batteries in local_coding_eval_hard.py to establish the Opus
baseline pass-rate for the head-to-head vs local models.
"""

import heapq


# h1_dijkstra
def shortest_path(graph, start, end):
    if start == end:
        return 0
    dist = {start: 0}
    pq = [(0, start)]
    while pq:
        d, u = heapq.heappop(pq)
        if u == end:
            return d
        if d > dist.get(u, float("inf")):
            continue
        for v, w in graph.get(u, []):
            nd = d + w
            if nd < dist.get(v, float("inf")):
                dist[v] = nd
                heapq.heappush(pq, (nd, v))
    return -1


# h2_lru_ttl
from collections import OrderedDict


class TTLCache:
    def __init__(self, capacity):
        self.cap = capacity
        self._d = OrderedDict()  # key -> (value, expiry)

    def put(self, key, value, now, ttl):
        if key in self._d:
            self._d.move_to_end(key)
        self._d[key] = (value, now + ttl)
        if len(self._d) > self.cap:
            self._d.popitem(last=False)

    def get(self, key, now):
        if key not in self._d:
            return None
        value, expiry = self._d[key]
        if now > expiry:
            del self._d[key]
            return None
        self._d.move_to_end(key)
        return value


# h3_wildcard_match
def is_match(s, p):
    n, m = len(s), len(p)
    dp = [[False] * (m + 1) for _ in range(n + 1)]
    dp[0][0] = True
    for j in range(1, m + 1):
        if p[j - 1] == "*":
            dp[0][j] = dp[0][j - 1]
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if p[j - 1] == "*":
                dp[i][j] = dp[i - 1][j] or dp[i][j - 1]
            elif p[j - 1] == "?" or p[j - 1] == s[i - 1]:
                dp[i][j] = dp[i - 1][j - 1]
    return dp[n][m]


# h4_median_stream
class MedianFinder:
    def __init__(self):
        self._lo = []  # max-heap (negated)
        self._hi = []  # min-heap

    def add(self, num):
        heapq.heappush(self._lo, -num)
        heapq.heappush(self._hi, -heapq.heappop(self._lo))
        if len(self._hi) > len(self._lo):
            heapq.heappush(self._lo, -heapq.heappop(self._hi))

    def median(self):
        if len(self._lo) > len(self._hi):
            return -self._lo[0]
        return (-self._lo[0] + self._hi[0]) / 2


# h5_json_parser
def parse_json(s):
    i = 0
    n = len(s)

    def skip_ws():
        nonlocal i
        while i < n and s[i] in " \t\n\r":
            i += 1

    def parse_value():
        nonlocal i
        skip_ws()
        if i >= n:
            raise ValueError("unexpected end")
        ch = s[i]
        if ch == "{":
            return parse_obj()
        if ch == "[":
            return parse_arr()
        if ch == '"':
            return parse_str()
        if ch == "t":
            return parse_lit("true", True)
        if ch == "f":
            return parse_lit("false", False)
        if ch == "n":
            return parse_lit("null", None)
        if ch == "-" or ch.isdigit():
            return parse_num()
        raise ValueError(f"unexpected {ch!r}")

    def parse_lit(word, val):
        nonlocal i
        if s[i:i + len(word)] != word:
            raise ValueError("bad literal")
        i += len(word)
        return val

    def parse_str():
        nonlocal i
        assert s[i] == '"'
        i += 1
        out = []
        while i < n:
            ch = s[i]
            if ch == '"':
                i += 1
                return "".join(out)
            if ch == "\\":
                i += 1
                if i >= n:
                    raise ValueError("bad escape")
                e = s[i]
                out.append({'"': '"', "\\": "\\", "n": "\n", "t": "\t",
                            "/": "/", "b": "\b", "r": "\r", "f": "\f"}.get(e, e))
                i += 1
            else:
                out.append(ch)
                i += 1
        raise ValueError("unterminated string")

    def parse_num():
        nonlocal i
        j = i
        if s[i] == "-":
            i += 1
        while i < n and s[i].isdigit():
            i += 1
        is_float = False
        if i < n and s[i] == ".":
            is_float = True
            i += 1
            while i < n and s[i].isdigit():
                i += 1
        if i < n and s[i] in "eE":
            is_float = True
            i += 1
            if i < n and s[i] in "+-":
                i += 1
            while i < n and s[i].isdigit():
                i += 1
        text = s[j:i]
        return float(text) if is_float else int(text)

    def parse_arr():
        nonlocal i
        i += 1  # [
        arr = []
        skip_ws()
        if i < n and s[i] == "]":
            i += 1
            return arr
        while True:
            arr.append(parse_value())
            skip_ws()
            if i >= n:
                raise ValueError("unterminated array")
            if s[i] == ",":
                i += 1
                continue
            if s[i] == "]":
                i += 1
                return arr
            raise ValueError("bad array")

    def parse_obj():
        nonlocal i
        i += 1  # {
        obj = {}
        skip_ws()
        if i < n and s[i] == "}":
            i += 1
            return obj
        while True:
            skip_ws()
            if i >= n or s[i] != '"':
                raise ValueError("expected key")
            key = parse_str()
            skip_ws()
            if i >= n or s[i] != ":":
                raise ValueError("expected :")
            i += 1
            obj[key] = parse_value()
            skip_ws()
            if i >= n:
                raise ValueError("unterminated object")
            if s[i] == ",":
                i += 1
                continue
            if s[i] == "}":
                i += 1
                return obj
            raise ValueError("bad object")

    val = parse_value()
    skip_ws()
    if i != n:
        raise ValueError("trailing data")
    return val


# h6_edit_distance
def edit_distance(a, b):
    m, k = len(a), len(b)
    prev = list(range(k + 1))
    for i in range(1, m + 1):
        cur = [i] + [0] * k
        for j in range(1, k + 1):
            if a[i - 1] == b[j - 1]:
                cur[j] = prev[j - 1]
            else:
                cur[j] = 1 + min(prev[j], cur[j - 1], prev[j - 1])
        prev = cur
    return prev[k]


# h7_observer
class EventBus:
    def __init__(self):
        self._subs = {}  # event -> dict[token, handler]
        self._tok = 0
        self._tok_event = {}

    def subscribe(self, event, handler):
        self._tok += 1
        token = self._tok
        self._subs.setdefault(event, {})[token] = handler
        self._tok_event[token] = event
        return token

    def unsubscribe(self, token):
        event = self._tok_event.pop(token, None)
        if event is not None:
            self._subs.get(event, {}).pop(token, None)

    def publish(self, event, payload):
        handlers = list(self._subs.get(event, {}).values())
        count = 0
        for h in handlers:
            count += 1
            try:
                h(payload)
            except Exception:
                pass
        return count


# h8_coin_change
def coin_change(coins, amount):
    INF = float("inf")
    dp = [0] + [INF] * amount
    for a in range(1, amount + 1):
        for c in coins:
            if c <= a and dp[a - c] + 1 < dp[a]:
                dp[a] = dp[a - c] + 1
    return dp[amount] if dp[amount] != INF else -1


# h9_trie
class Trie:
    def __init__(self):
        self.children = {}
        self.count = 0      # words passing through (prefix count)
        self.word_end = 0   # words ending here (with duplicates)

    def insert(self, word):
        node = self
        node.count += 1
        for ch in word:
            node = node.children.setdefault(ch, Trie())
            node.count += 1
        node.word_end += 1

    def _find(self, s):
        node = self
        for ch in s:
            if ch not in node.children:
                return None
            node = node.children[ch]
        return node

    def search(self, word):
        node = self._find(word)
        return bool(node and node.word_end > 0)

    def starts_with(self, prefix):
        return self._find(prefix) is not None

    def count_prefix(self, prefix):
        node = self._find(prefix)
        return node.count if node else 0


# h10_async_scheduler
class TaskScheduler:
    def __init__(self, max_parallel):
        self.max_parallel = max_parallel
        self.tasks = []  # (name, deps, duration, order)

    def add_task(self, name, deps, duration):
        self.tasks.append((name, list(deps), duration, len(self.tasks)))

    def run(self):
        done_at = {}          # name -> end time
        started = {}          # name -> (start, end)
        remaining = {t[0]: t for t in self.tasks}
        # running: list of (end_time, name)
        running = []
        time_now = 0
        order = {t[0]: t[3] for t in self.tasks}

        while remaining or running:
            # free finished workers up to time_now
            # find tasks whose deps are all done by time_now
            ready = []
            for name, (nm, deps, dur, od) in remaining.items():
                if all(d in done_at and done_at[d] <= time_now for d in deps):
                    ready.append((od, nm, dur))
            ready.sort()
            # start as many as slots allow
            free = self.max_parallel - len(running)
            for od, nm, dur in ready:
                if free <= 0:
                    break
                start = time_now
                end = start + dur
                started[nm] = (start, end)
                heapq.heappush(running, (end, od, nm))
                done_pending = True
                del remaining[nm]
                free -= 1
            if not running:
                # nothing running and nothing started -> advance to next dep readiness
                # (shouldn't happen for valid DAG, but guard)
                if remaining:
                    # jump to earliest possible: max of unmet dep ends
                    nxt = min(
                        max((done_at.get(d, float("inf")) for d in deps), default=time_now)
                        for _, deps, _, _ in remaining.values()
                    )
                    if nxt == float("inf"):
                        break
                    time_now = max(time_now + 1, nxt)
                continue
            # advance time to next completion
            end_time, od, nm = heapq.heappop(running)
            done_at[nm] = end_time
            time_now = end_time
            # also pop any others finishing at same time
            while running and running[0][0] == end_time:
                e2, o2, n2 = heapq.heappop(running)
                done_at[n2] = e2

        result = [(nm, se[0], se[1]) for nm, se in started.items()]
        result.sort(key=lambda r: (r[1], order[r[0]]))
        return result
