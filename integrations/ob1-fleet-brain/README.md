# ob1-fleet-brain — OB1-Compatible Fleet Brain MCP Server

Shared persistent memory layer for carrier_hermes bots. Built using **Path B** (OB1-compatible local SQLite) because OB1's native server requires Supabase + OpenRouter — cloud dependencies we cannot use.

## What It Does

Gives every carrier_hermes bot a **shared, persistent, searchable brain**:

- Probe stores research findings → all bots can recall them
- Mate logs errors → next Mate session doesn't repeat the same mistakes
- Helm decisions are recorded → all bots can check current policy
- Discord messages are indexed → fleet conversations searchable

## Tool Surface (OB1-compatible)

| Tool | Description |
|------|-------------|
| `ob1_write_thought(content, source, scope, category, …)` | Store a memory/knowledge fragment |
| `ob1_search(query, top_k, scope, source, category, …)` | Semantic + keyword search |
| `ob1_recall(query, agent_id, scope, memory_kind)` | Governed recall with trace logging |
| `ob1_list_thoughts(scope, source, category, limit, offset)` | Paginated list |
| `ob1_get_thought(thought_id)` | Fetch one thought by ID |
| `ob1_brain_stats()` | DB health / counts |

## Scope System

| Scope | Who sees it |
|-------|-------------|
| `fleet` | All bots (default — use for shared knowledge) |
| `bot:<name>` | Private to one bot (e.g. `bot:firstmate`) |

## Storage

```
C:/Users/micha/AppData/Local/hermes/carrier/ob1_brain.db
```

SQLite with float32 embedding blobs + numpy cosine search. No cloud, no API keys for search.

## Embedding Backend

1. **`sentence-transformers/all-MiniLM-L6-v2`** (local, 384-d) — installed automatically via `uv sync`
2. **Hash fallback** — if sentence-transformers is unavailable, returns deterministic pseudo-vectors; keyword search (`ob1_search`) still works

## Running

```bash
cd carrier_hermes/integrations/ob1-fleet-brain

# First time — sync deps
uv sync

# Optional: also install sentence-transformers for real semantic search
uv pip install sentence-transformers

# Start MCP server
uv run python server.py
```

Or via the Hermes MCP config (see below).

## Hermes MCP Config

Add to `~/.hermes/config.yaml` (or use `hermes mcp add`):

```yaml
mcp_servers:
  ob1-fleet-brain:
    enabled: true
    command: uv
    args:
      - run
      - --directory
      - C:\Users\micha\carrier_hermes\integrations\ob1-fleet-brain
      - python
      - server.py
    env:
      OB1_BRAIN_DB: C:\Users\micha\AppData\Local\hermes\carrier\ob1_brain.db
```

## Discord Capture

The `discord_capture.py` bridge captures fleet Discord messages into the brain.

**Prerequisites:** First Watch bot token + channel IDs.

```bash
export DISCORD_BOT_TOKEN=<First Watch token>
export OB1_DISCORD_CHANNELS=<comma-separated channel IDs>
export OB1_DISCORD_GUILD=carrier

uv pip install discord.py
uv run python discord_capture.py
```

Or call programmatically from First Watch:

```python
from discord_capture import FleetBrainCapture
capture = FleetBrainCapture()
capture.ingest_message(message_id, channel_id, "#fleet-general", author, content)
```

**Note:** Requires `MESSAGE CONTENT INTENT` enabled in Discord Developer Portal (same as First Watch bot already has).

## What OB1's discord-capture would give us vs. what we get

| Feature | OB1 native | This implementation |
|---------|-----------|---------------------|
| Message ingestion | Supabase edge function | Local Python bridge |
| Embeddings | OpenRouter API | sentence-transformers (local) |
| Storage | PostgreSQL + pgvector | SQLite + numpy |
| Functionality | Identical | ✅ Equivalent |

## Relationship to Existing Systems

| System | Role | OB1 Brain role |
|--------|------|----------------|
| Obsidian vault | Personal knowledge base (Michael) | Untouched — OB1 brain is fleet-only |
| Carrier Kanban | Task tracking | Untouched — brain stores knowledge, not tasks |
| ob1-mcp-server (vault indexer) | Semantic search over vault notes | Separate — different DB, different purpose |
| **ob1-fleet-brain** (this) | **Shared bot memory across sessions** | ✅ New |

## Migrating to Real Supabase Later

When/if you want to migrate to OB1's cloud backend:

1. Export: `python -c "from store import FleetBrainStore; ..."` (dump thoughts to JSON)
2. Set up Supabase project following OB1's `docs/01-getting-started.md`
3. Run `schemas/agent-memory/schema.sql` in Supabase SQL editor
4. Import JSON → `thoughts` table via bulk insert
5. Swap MCP config URL to `https://YOUR_REF.supabase.co/functions/v1/mcp?key=...`

The tool names (`ob1_write_thought`, `ob1_search`, etc.) are compatible — bot prompts don't need updating.

## Running Tests

```bash
cd carrier_hermes/integrations/ob1-fleet-brain
uv pip install pytest numpy
uv run pytest test_brain.py -v
```
