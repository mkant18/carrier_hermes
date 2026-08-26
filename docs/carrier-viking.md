# carrier-viking: Persistent Agent Memory

Lightweight [OpenViking](https://github.com/volcengine/OpenViking)-compatible
persistent memory layer for carrier_hermes bots.

## What this plugin adds

Four tools available to every carrier bot session:

| Tool | Description |
|------|-------------|
| `remember(content, type)` | Store a memory that persists across sessions |
| `recall(query, type)` | Semantic search over stored memories |
| `forget(memory_id)` | Delete a specific memory |
| `list_memories(type)` | List all memories with quota usage |
| `viking_stats()` | Quota and DB health check |

## Memory types and quotas

| Type | Quota | Purpose |
|------|-------|---------|
| `task` | 50/bot | Current work, objectives, in-progress items |
| `fact` | 100/bot | Learned facts, user preferences, domain knowledge |
| `error` | 30/bot | Mistakes made, anti-patterns, lessons learned |
| `decision` | 25/bot | Decisions made with rationale |

Quotas are enforced by LRU eviction (oldest-accessed memory is dropped when full).
Set `VIKING_QUOTA_<TYPE>` env vars to override.

## Storage

SQLite at `VIKING_MEMORY_DB_PATH`
(default: `~/AppData/Local/hermes/carrier/viking_memory.db`)

Schema is forward-compatible with OpenViking's memory import API.

## Environment variables

```
VIKING_MEMORY_DB_PATH   Path to SQLite DB
HERMES_BOT_ID           Default bot_id for this session
VIKING_QUOTA_TASK       Quota for 'task' type (default: 50)
VIKING_QUOTA_FACT       Quota for 'fact' type (default: 100)
VIKING_QUOTA_ERROR      Quota for 'error' type (default: 30)
VIKING_QUOTA_DECISION   Quota for 'decision' type (default: 25)
VIKING_MAX_RECALL       Max results from recall() (default: 10)
```

## Implementation

**Option B** (lightweight compatible layer) — no external pip dependencies.
Uses stdlib `sqlite3` + TF-IDF cosine-similarity search implemented in pure Python.

### Why Option B, not full OpenViking

Full OpenViking requires:
1. A running server (Rust binary or Docker) at port 1933
2. Embedding API credentials for vector indexing
3. Complex build chain (Rust + Python + TypeScript)

Option B gives bots working persistent memory immediately, using only stdlib.
The OpenViking interface is fully compatible — swap to the full server by:
1. Running `docker run -p 1933:1933 openviking/openviking`
2. Setting `OPENVIKING_URL=http://127.0.0.1:1933`
3. Enabling the `carrier-viking-ov` plugin instead

## Enabling for a bot

1. Ensure `enabled_by_default: false` in `plugin.yaml` (it is)
2. Do NOT add to any config.yaml fleet-wide yet (human review required)
3. To test with a single bot: `HERMES_PLUGINS=carrier-viking hermes run --bot my_bot`

## Recommended usage pattern

```python
# At session start — recall relevant context
memories = recall("what was I working on last time", type="task", k=5)

# During work — remember key facts
remember("User prefers concise bullet-point summaries", type="fact")
remember("Task: Integrate carrier-viking memory plugin", type="task")

# On error — capture lesson
remember("sqlite3.connect() on Windows needs forward slashes in path", type="error")

# On decision
remember("Chose TF-IDF over embedding search: stdlib-only, no server dependency", type="decision")

# At session end — clean up completed tasks
forget(task_memory_id)
```

## Files

Plugin (Hermes plugins dir):
- `C:/Users/micha/AppData/Local/hermes/plugins/carrier-viking/plugin.yaml`
- `C:/Users/micha/AppData/Local/hermes/plugins/carrier-viking/__init__.py`

Carrier repo docs (this directory):
- `docs/carrier-viking.md` — this file
- `scripts/carrier_viking_migrate.py` — migration script to full OpenViking

Data (never committed to git):
- `C:/Users/micha/AppData/Local/hermes/carrier/viking_memory.db`

## Security notes

- Memories are scoped per `bot_id`; `forget()` enforces ownership
- No network calls — fully local
- DB contains bot experiences; treat as sensitive (don't expose via HTTP)
