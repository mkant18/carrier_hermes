# OpenViking Integration

> **Status:** Architecture DECISION — standup task dispatched (see Kanban `t_8144c4e2` children)
> **Author:** Stacks (knowledge_lt) via Kanban t_8144c4e2
> **Date:** 2026-08-25
> **License note:** OpenViking is AGPLv3. Run as a separate service, never vendored.

---

## What Is OpenViking?

Open-source self-evolving Context Database for AI agents (volcengine).
- Unifies Agent Memory + Knowledge RAG + Skills under one `viking://` virtual filesystem.
- Agents browse their own context with `ls/tree/find` instead of querying a black-box vector store.
- Content is processed into 3 tiers:
  - **L0 (abstract):** One-line summary — always resident in context
  - **L1 (overview):** Section headers + short summaries — loaded on demand
  - **L2 (details):** Full content — lazy-loaded when needed
- Every retrieval leaves an observable trajectory (debuggable).
- Polyglot: C/C++/Go/Rust/Python/TypeScript clients.
- Studio playground available for exploration.

---

## Architecture Decision

### How OpenViking sits relative to existing layers

```
┌─────────────────────────────────────────────────────────────────┐
│                    QUERY PATH (what bots see)                   │
│                                                                 │
│   Bot (Librarian / Helm / Chart / Stacks)                       │
│       │                                                         │
│       ▼                                                         │
│   ┌────────────────────────────────────────────────────────┐    │
│   │              OpenViking (viking:// MCP tool)           │    │
│   │         UNIFYING retrieval layer                       │    │
│   │   - L0/L1/L2 tier loading (cheap on queries)           │    │
│   │   - Observable trajectory per retrieval               │    │
│   │   - Unified namespace over all sources below          │    │
│   └────────────────────────────────────────────────────────┘    │
│         │              │                │           │            │
│         ▼              ▼                ▼           ▼            │
│   ┌──────────┐  ┌──────────────┐  ┌─────────┐  ┌──────────┐   │
│   │ Obsidian │  │  AIPass mail │  │  OB1    │  │ Hermes   │   │
│   │ Vault    │  │  _agent/     │  │ semantic│  │ state.db │   │
│   │ (notes)  │  │  mailbox/    │  │ index   │  │ (bot mem)│   │
│   └──────────┘  └──────────────┘  └─────────┘  └──────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### Decision: Does OpenViking REPLACE or SIT ABOVE OB1 / OSB MCP?

**Decision: OpenViking sits ABOVE OB1 and OSB MCP as a unifying retrieval broker.**

Rationale:

1. **Do not replace OSB MCP.** The obsidian-second-brain MCP server provides keyword/BM25 search
   and note read/health/validate tools. These are low-cost, zero-infrastructure, and already
   wired. They remain the direct read path for Librarian on simple keyword queries.

2. **Do not replace OB1.** OB1 (t_5e0ae4a3, in progress under firstmate) is a local
   semantic/embeddings index (sentence-transformers + sqlite-vec) over the vault only.
   It is lightweight and vault-scoped. Do NOT cancel or merge OB1 into OpenViking at this
   stage — OB1 is simpler, may complete first, and can feed INTO OpenViking as a source.

3. **OpenViking is the cross-source unifier.** Its value is the `viking://` virtual filesystem
   that spans vault notes + AIPass mail + bot memory in one browsable namespace. OSB MCP and
   OB1 answer "what does the vault say?" — OpenViking answers "what does the fleet know?"

4. **Tier mapping to cost model:**
   - L0 (abstract): embedded in system prompt / resident in context — $0 per query
   - L1 (overview): loaded on nav events — cheap (small text)
   - L2 (details): lazy, only when needed — cost is content size, not embedding API
   - Embedding model: local `all-MiniLM-L6-v2` (sentence-transformers) per fleet cost model;
     NO Anthropic/Grok API keys for embedding

5. **AGPLv3 constraint:** Keep OpenViking as a standalone Docker service. Do not vendor its
   source into carrier_hermes. Any internal tooling that calls it via MCP or HTTP is not
   a derivative work under standard AGPLv3 interpretation. Document the service boundary clearly.

### Sequence of operations

1. OB1 (firstmate, t_5e0ae4a3) — vault semantic index only, ships first
2. OpenViking standup (coding_lt child task) — Docker service, indexes vault + AIPass + Hermes state.db
3. OpenViking MCP wiring — `viking_search` tool added to Librarian / Chart / Helm / Stacks
4. OB1 may eventually become a source adapter INTO OpenViking (future, not now)

---

## Vault Indexing Policy

Per vault `CLAUDE.md` (TL 3, 2026-08-25):
- OpenViking has READ access to all vault notes
- EXCLUDED from indexing: `_agent/**`, `.obsidian/**`, `Archive/**` (low signal)
- Source of truth: Obsidian vault is the ground truth; OpenViking is a search index only
- No vault writes by OpenViking; index state stored at `_agent/openviking/` (TL allows writes there)

---

## Sources to Index

| Source | viking:// path | Notes |
|---|---|---|
| Obsidian vault notes | `viking://vault/` | Exclude `_agent/`, `.obsidian/`, `Archive/` |
| AIPass mailbox | `viking://aipass/` | `_agent/mailbox/**` |
| Hermes per-bot memory | `viking://hermes/` | `state.db` memory entries; read-only |
| Carrier Hermes docs | `viking://docs/` | `carrier_hermes/docs/`, `carrier_hermes/bots/` |

---

## Fleet Wiring Plan

| Bot profile | Access | Tool | Notes |
|---|---|---|---|
| `vault_librarian` | READ | `viking_search` | Primary consumer |
| `hermes_ai_explorer` (Chart) | READ | `viking_search` | Cross-source intel |
| `chief_of_staff` (Helm) | READ | `viking_search` | High-level context queries |
| `knowledge_lt` (Stacks) | READ | `viking_search` | Routing context only |
| `obsidian_archivist` (Clerk) | NONE | — | Clerk writes vault directly; does not need search layer |

---

## Infrastructure (to be built by coding_lt)

- Docker Compose service: `carrier_hermes/docker/openviking/docker-compose.yml`
- Local port: 18080 (or per compose default)
- Index storage: `C:/Users/micha/AppData/Local/hermes/openviking-data/` (outside vault; no git)
- MCP server adapter: `carrier_hermes/integrations/openviking-mcp/server.py`
  - Tool: `viking_search(query: str, sources: list[str] = None, top_k: int = 5)`
  - Returns: `[{path, source, score, l0_abstract, snippet}]`
- Rebuild cron: `carrier_hermes/scripts/openviking_reindex.sh` (no_agent, daily)

---

## License Note

OpenViking is AGPLv3. The fleet uses it as a **network service** (Docker container, HTTP/MCP
boundary). Our MCP adapter and wiring code is MIT/internal. This service boundary is the
standard AGPLv3 "network use" interpretation — we are not distributing or modifying OpenViking
source. If OpenViking source is modified, those changes must be published per AGPLv3.

---

## Open Items (post-standup)

- [ ] Verify OpenViking Docker compose works on Windows 11 (MSYS/WSL2 Docker Desktop)
- [ ] Choose embedding model: local sentence-transformers vs. OpenViking built-in
- [ ] Confirm viking:// protocol MCP adapter shape (REST vs stdio)
- [ ] Validate cross-source query trajectory output format
- [ ] OB1 completion (t_5e0ae4a3) — assess if OB1 index can feed INTO OpenViking as an adapter
