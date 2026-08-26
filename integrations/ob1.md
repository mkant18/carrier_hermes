# OB1 Fleet Brain — Shared Bot Memory Layer

**Status:** implemented feature/carrier-ob1-brain  
**Path chosen:** B (OB1-compatible local SQLite, no Supabase required)  
**MCP server:** `integrations/ob1-fleet-brain/server.py`  
**DB:** `C:/Users/micha/AppData/Local/hermes/carrier/ob1_brain.db`

## What Was Built

A local OB1-compatible memory layer that gives all carrier_hermes bots shared persistent knowledge without any cloud dependency.

### Files

| File | Purpose |
|------|---------|
| `integrations/ob1-fleet-brain/schema.py` | SQLite schema (thoughts + agent_memory sidecars + discord_messages + recall_traces + audit_events) |
| `integrations/ob1-fleet-brain/store.py` | Vector store (cosine search via numpy float32 blobs) |
| `integrations/ob1-fleet-brain/embedder.py` | sentence-transformers 384-d embedder with hash-vector fallback |
| `integrations/ob1-fleet-brain/server.py` | FastMCP server exposing 6 OB1-compatible tools |
| `integrations/ob1-fleet-brain/discord_capture.py` | Discord → brain bridge (replaces OB1 Supabase edge function) |
| `integrations/ob1-fleet-brain/test_brain.py` | Smoke tests (8/8 passing) |
| `integrations/ob1-fleet-brain/pyproject.toml` | uv project (mcp, numpy; sentence-transformers optional) |
| `integrations/ob1-fleet-brain/README.md` | Setup, usage, migration-to-Supabase guide |

## MCP Tools Exposed

```
ob1_write_thought   — store fleet knowledge (with scope + provenance)
ob1_search          — semantic + keyword search
ob1_recall          — governed recall with trace logging
ob1_list_thoughts   — paginated list with filters
ob1_get_thought     — fetch single thought by ID
ob1_brain_stats     — DB health check
```

## OB1 Research Findings

1. **OB1 requires Supabase** — the MCP server is a Deno/TypeScript Supabase Edge Function; all examples point to `https://YOUR_REF.supabase.co/...`
2. **OB1 requires OpenRouter** — embeddings are generated via OR API (`text-embedding-3-small`)
3. **discord-capture requires both** — it's also a Supabase edge function + OR embeddings
4. **Path B is the right call** — local SQLite with sentence-transformers gives identical functionality; Supabase migration path documented in README
5. **agent-memory schema** — fully implemented as SQLite sidecars (`agent_memories`, `recall_traces`, `audit_events`)

## Relationship to Other Systems

| System | Status |
|--------|--------|
| Obsidian vault | Untouched — OB1 brain is fleet-only bot memory |
| ob1-mcp-server (vault indexer) | Untouched — different DB, indexes vault notes for Librarian/Chart |
| Carrier Kanban | Untouched — brain stores knowledge, not tasks |
| **ob1-fleet-brain** | **New: shared bot memory layer** |

## To Enable (needs human review)

1. `hermes mcp add ob1-fleet-brain --command uv --args "run --directory C:\Users\micha\carrier_hermes\integrations\ob1-fleet-brain python server.py" --env OB1_BRAIN_DB="C:\Users\micha\AppData\Local\hermes\carrier\ob1_brain.db"`
2. Add `ob1-fleet-brain` to bot profile MCP lists (especially firstmate, probe, research_agent, chief_of_staff)
3. For Discord capture: set `DISCORD_BOT_TOKEN` and `OB1_DISCORD_CHANNELS` and run `discord_capture.py`
4. Optionally install `sentence-transformers` for real semantic search: `uv pip install sentence-transformers` in the ob1-fleet-brain dir

## Why knowledge_lt / Helm Review

- Bot prompts need updating to call `ob1_write_thought` after significant events (decisions, errors, research)
- Scope policy decisions: what should be `fleet` vs `bot:<name>`? 
- Discord channel list for capture needs to be specified by operator
