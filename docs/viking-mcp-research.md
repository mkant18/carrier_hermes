# viking-mcp: Cross-Source Search Stack Research

Date: 2026-08-26
Researcher: research_agent (Probe)
Job: t_329158b2 (parent t_62e8ced6, Silent Running cycle 3)

## Context

`volcengine/OpenViking` does not exist (confirmed by prior Probe research). The
fleet needs a `viking_search` MCP that adds **cross-source unified search**
over four corpora that currently have no shared index:

- Obsidian vault (`C:/Users/micha/Documents/Obsidian Vault/`)
- AIPass mailbox (`C:/Users/micha/AppData/Local/hermes/_agent/mailbox/`)
- Fleet docs (`C:/Users/micha/carrier_hermes/docs/` and `bots/`)
- Hermes memory/state (SQLite)

OB1 already does semantic vault search — viking_search is additive, not a
replacement.

---

## 1. Vector store recommendation: **Qdrant**

| | ChromaDB | Qdrant | Weaviate | Milvus-lite |
|---|---|---|---|---|
| Docker deploy | Yes, simple | Yes, simple | Yes, heavier (needs extra services) | Milvus-lite is embedded-only, not really a Docker story; full Milvus needs etcd+MinIO+Pulsar |
| Resource footprint | Very light | Light (Rust, single binary) | Moderate-heavy (JVM-adjacent, modules) | Heavy (multi-service) unless using milvus-lite (embedded, no server) |
| Scale ceiling | ~500k vectors before SQLite/DuckDB backend degrades | 10M+ vectors, sub-2ms search at scale | Good at scale but overkill for this use case | Best at massive scale, wrong tool for a laptop fleet |
| File/local mode (no server) | Yes (embedded/persistent client) | Yes (`QdrantClient(path=...)` local mode, no server needed) | No (always needs server) | Yes, but abandons the "shared server multiple agents query" model |
| Built-in snapshot/backup | Manual directory copy | Built-in HTTP snapshot API | Built-in | N/A |
| Windows/Docker Desktop fit | Good | Good, this is the most common local-agent deployment pattern in practice | Possible but more moving parts for no real benefit here | Not a good fit |

**Recommendation: Qdrant.** Rationale specific to this fleet:
- Single container, single volume, REST+gRPC API — matches the "one small
  service per concern" pattern already used elsewhere in carrier_hermes.
- Official first-party MCP server already exists (`qdrant/mcp-server-qdrant`)
  — see §4 — so viking_search doesn't need to be written from scratch, only
  extended for multi-source ingestion.
- Room to grow: current corpora are small (a few thousand notes/messages/docs
  combined), well inside ChromaDB's comfort zone too, but Qdrant costs nothing
  extra at this scale and removes a future migration if the vault/mailbox
  grow. ChromaDB remains the fallback if the team wants zero extra containers
  (it can run embedded inside the MCP server process itself, no Docker at
  all) — flag this as the "cheaper alt" in the decision, not a wrong choice.

## 2. SQLite / file-based ingestion (for Hermes memory)

Neither Qdrant nor ChromaDB ingests SQLite natively — both only accept
vectors (+ optional payload/metadata) via their client API. Hermes
memory/state must be **read out of SQLite by an ingestion script and pushed
in as documents**, same as the vault markdown files and mailbox JSON. This is
normal; there is no vector DB that speaks SQL directly.

Practical pattern for viking_search:
1. A small Python ingestion job (`ingest.py`) run periodically (or on file
   change) that:
   - Walks the vault for `.md` files, chunks them, embeds, upserts to a
     `vault` collection (skip if OB1 already indexes these — check for reuse
     before duplicating).
   - Walks the AIPass mailbox `inbox/`/`outbox/` JSON/text files, embeds,
     upserts to a `mailbox` collection.
   - Walks `carrier_hermes/docs/` and `bots/` markdown, upserts to a `fleet_docs`
     collection.
   - Opens the Hermes memory SQLite file read-only (`sqlite3.connect(path,
     uri=True, mode=ro)` via `file:...?mode=ro`), `SELECT` the memory rows,
     embeds their text content, upserts to a `memory` collection.
2. viking_search's `search` tool fans a query out across all four Qdrant
   collections (or one collection with a `source` payload field + filter —
   simpler to maintain) and merges/re-ranks results by score before
   returning to the caller.
3. Use a `source` payload filter model (one collection, `source` field) over
   four separate collections unless access-control per source becomes a
   requirement — it is less code and the fan-out query becomes a single
   Qdrant call with `should` filters instead of four round trips.

Qdrant also supports `QDRANT_LOCAL_PATH` (embedded, file-backed, no server
process) if the team decides a Docker container is unnecessary overhead for
a single-machine fleet — worth a go/no-go conversation, since it removes the
container from the compose file entirely and viking_search would embed
Qdrant directly. Trade-off: no HTTP dashboard, and only one process can hold
the local-path DB open at a time (a problem if two agents want to query
concurrently) — this is the deciding factor in favor of the server mode
recommended above, since the fleet has multiple concurrent agents.

## 3. Embedding model: **BAAI/bge-small-en-v1.5** via **FastEmbed**

No Anthropic/Grok API keys are usable for embeddings, so this must be a
local CPU model.

| Model | Dims | Size | MTEB (eng) | CPU throughput | Notes |
|---|---|---|---|---|---|
| all-MiniLM-L6-v2 | 384 | ~90MB | ~56.3 | Fastest (~500 chunks/s) | Weakest retrieval quality of the three; fine for prototyping only |
| **bge-small-en-v1.5** | 384 | ~130MB | ~62 (beats MiniLM meaningfully) | ~255 chunks/s, still CPU-friendly | **Recommended** — best quality/speed balance for CPU-only |
| bge-base-en-v1.5 | 768 | ~440MB | ~63.5 | ~99 chunks/s | Marginal quality gain over bge-small, 2x storage, notably slower on CPU |

**Recommendation: `BAAI/bge-small-en-v1.5`**, run through **FastEmbed**
(Qdrant's own embedding library):
- Same dimensionality (384) as MiniLM so storage stays cheap, but
  consistently better retrieval accuracy in benchmarks.
- FastEmbed uses ONNX Runtime, not PyTorch — no GPU, small dependency
  footprint, good fit for a container that just needs to embed markdown/text
  chunks.
- This is literally the `DefaultEmbedding` in FastEmbed and the default
  `EMBEDDING_MODEL` in `qdrant/mcp-server-qdrant` — using it means the
  official MCP server template needs zero embedding-config changes.

## 4. MCP server template: **qdrant/mcp-server-qdrant** (official, Python)

Repo: https://github.com/qdrant/mcp-server-qdrant

- Official Qdrant-maintained MCP server, Python, ships a Dockerfile.
- Ships two tools out of the box: `qdrant-store` and `qdrant-find`
  (semantic memory pattern) — this is the base to extend into
  `viking_search`'s multi-source search tool.
- Config via env vars: `QDRANT_URL`, `QDRANT_API_KEY` (optional),
  `COLLECTION_NAME`, `EMBEDDING_PROVIDER=fastembed`,
  `EMBEDDING_MODEL=BAAI/bge-small-en-v1.5`, `QDRANT_LOCAL_PATH` (alt to URL).
- Supports stdio, SSE, and streamable-http transports — stdio is what
  Hermes/Claude Code MCP clients expect by default.
- Effort to extend for viking_search: fork or wrap this server, add:
  1. A `source` metadata field on every point.
  2. A custom `viking_search` tool (instead of / alongside `qdrant-find`)
     that accepts an optional `sources: []` filter param and returns
     results tagged with which corpus they came from.
  3. The ingestion script from §2, run as a separate one-shot/cron
     container or a Windows scheduled task — do NOT put ingestion inside
     the MCP server's request path, keep it async so search stays fast.

ChromaDB alternative if the team prefers to avoid a second container:
`chroma-core/chroma-mcp` (official) or `djm81/chroma_mcp_server` both exist
and support embedded/persistent file-mode with no separate server — viable
fallback, same effort tier, but loses the built-in snapshot/backup API and
the multi-agent-concurrent-access story since ChromaDB's SQLite-backed
persistent mode has the same single-writer caveat.

## 5. Sample docker-compose.yml (Windows + Docker Desktop, NTFS volumes)

```yaml
services:
  qdrant:
    image: qdrant/qdrant:latest
    container_name: viking-qdrant
    restart: unless-stopped
    ports:
      - "6333:6333"   # REST + dashboard
      - "6334:6334"   # gRPC
    volumes:
      # NTFS bind mount from the Windows host. Fine for a low-write-volume
      # local index; do NOT expect fast filesystem semantics here (see gotcha #1).
      - C:/Users/micha/AppData/Local/hermes/viking/qdrant_storage:/qdrant/storage
    environment:
      - QDRANT__LOG_LEVEL=INFO

  viking-mcp:
    build: ./viking-mcp        # fork of qdrant/mcp-server-qdrant + custom tool
    container_name: viking-mcp
    restart: unless-stopped
    depends_on:
      - qdrant
    environment:
      - QDRANT_URL=http://qdrant:6333
      - COLLECTION_NAME=viking_unified
      - EMBEDDING_PROVIDER=fastembed
      - EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
      - FASTMCP_SERVER_HOST=0.0.0.0
      - FASTMCP_SERVER_PORT=8000
    ports:
      - "8000:8000"
    volumes:
      # Read-only source mounts for the ingestion job to walk.
      - C:/Users/micha/Documents/Obsidian Vault:/sources/vault:ro
      - C:/Users/micha/AppData/Local/hermes/_agent/mailbox:/sources/mailbox:ro
      - C:/Users/micha/carrier_hermes/docs:/sources/fleet_docs:ro
      - C:/Users/micha/carrier_hermes/bots:/sources/fleet_bots:ro
      - C:/Users/micha/AppData/Local/hermes:/sources/hermes_state:ro

  viking-ingest:
    build: ./viking-mcp
    container_name: viking-ingest
    command: ["python", "ingest.py", "--once"]
    depends_on:
      - qdrant
    environment:
      - QDRANT_URL=http://qdrant:6333
      - EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
    volumes:
      - C:/Users/micha/Documents/Obsidian Vault:/sources/vault:ro
      - C:/Users/micha/AppData/Local/hermes/_agent/mailbox:/sources/mailbox:ro
      - C:/Users/micha/carrier_hermes/docs:/sources/fleet_docs:ro
      - C:/Users/micha/carrier_hermes/bots:/sources/fleet_bots:ro
      - C:/Users/micha/AppData/Local/hermes:/sources/hermes_state:ro
    # Run manually or via Windows Task Scheduler / cron on a timer;
    # do not leave this as a long-running restart:always service.
```

## 6. Windows-specific gotchas

1. **NTFS bind mounts are slow relative to a native Linux/WSL2 filesystem.**
   Docker Desktop on Windows runs containers in a WSL2 VM; every read/write
   to a `C:/Users/...` bind mount crosses the 9P/VirtioFS translation
   boundary. For a low-frequency ingestion job (run every few minutes/hours,
   not per-request) this is a non-issue. It would matter if the MCP server
   tried to re-scan the whole vault on every search call — don't do that;
   ingest ahead of time into Qdrant and only query Qdrant on the hot path.
2. **Qdrant's own storage volume should NOT sit on a slow bind mount if
   write-heavy.** Qdrant's index storage benefits from being inside the
   Linux/WSL2 filesystem rather than an NTFS bind mount. For this fleet's
   scale (a few thousand points) it's fine either way, but if performance
   ever becomes noticeable, switch `qdrant_storage` to a Docker **named
   volume** instead of a host bind mount — named volumes live inside the
   WSL2 VM's own filesystem and are fast regardless of host OS.
3. **inotify/file-change events do not cross the Windows→Linux boundary.**
   If viking-mcp ever wants "watch the vault and re-index automatically,"
   file-system-watch approaches (inotify) won't fire for files edited from
   Windows-side apps (Obsidian, VS Code, Notepad) into a bind-mounted
   directory. Use a polling ingestion job (timer-based, e.g. every 5-15 min)
   instead of a watch-based one.
4. **Path spaces.** `C:/Users/micha/Documents/Obsidian Vault` has a space in
   it — always quote paths in compose files and Dockerfiles; forward slashes
   work fine in `docker-compose.yml` volume entries on Windows, backslashes
   need escaping and are best avoided.
5. **Docker Desktop must be running and WSL2 backend up to date** (WSL
   ≥2.1.5 per Docker's own best-practices doc) — stale WSL causes Desktop
   hangs and `vmmem.exe` runaway memory; worth a version check before
   deployment, not just at first install.
6. **Read-only source mounts (`:ro`)** are recommended for the vault/mailbox/
   docs mounts — viking-mcp and viking-ingest only need to read these
   corpora, never write into them; prevents an ingestion bug from ever
   corrupting the Obsidian vault or mailbox.

## 7. Effort estimate for coding_lt

| Task | Estimate |
|---|---|
| Stand up Qdrant container + verify healthz/dashboard | 0.5 hr |
| Fork `qdrant/mcp-server-qdrant`, wire FastEmbed + bge-small-en-v1.5 | 0.5–1 hr |
| Write `ingest.py`: walk vault + mailbox + fleet docs + SQLite memory, chunk, embed, upsert with `source` payload field | 3–4 hr (bulk of the work; SQLite read path and mailbox JSON parsing need care) |
| Add custom `viking_search` MCP tool (query + optional `sources` filter, merged/ranked results) | 1–2 hr |
| docker-compose.yml + Windows path wiring + smoke test end-to-end | 1 hr |
| Dedup check against OB1 (avoid double-indexing the vault) + docs | 0.5 hr |
| **Total** | **~6.5–9 hours** (roughly one focused day), assuming no surprises in the AIPass mailbox JSON schema or Hermes memory SQLite schema — recommend coding_lt inspect those two schemas first since they weren't available during this research pass. |

## Sources

- https://qdrant.tech/documentation/quickstart/ (Qdrant local Docker quickstart)
- https://qdrant.tech/documentation/installation/ (docker-compose reference)
- https://hub.docker.com/r/qdrant/qdrant (local-mode client usage)
- https://github.com/qdrant/mcp-server-qdrant (official MCP server, env vars, Docker)
- https://github.com/chroma-core/chroma-mcp and https://github.com/djm81/chroma_mcp_server (ChromaDB MCP alternatives)
- https://github.com/qdrant/fastembed and https://qdrant.github.io/fastembed/Getting%20Started (FastEmbed, bge-small-en-v1.5 default)
- https://d-central.tech/local-embedding-models and https://adityarajsingh.com/best-local-embedding-model (embedding model benchmarks: MiniLM vs bge-small vs bge-base, CPU throughput)
- https://airbyte.com/data-engineering-resources/chroma-db-vs-qdrant and https://facsiaginsa.com/ai/qdrant-vs-chromadb-vector-database-comparison (Chroma vs Qdrant architecture/scale comparison)
- https://docs.docker.com/desktop/features/wsl/best-practices/ (Docker Desktop WSL2 bind-mount performance guidance)

## Confidence

- Vector store recommendation (Qdrant): **high** — corroborated by official
  docs, multiple independent comparisons, and an existing official MCP
  server that fits the fleet's needs directly.
- Embedding model recommendation (bge-small-en-v1.5 via FastEmbed): **high**
  — consistent across benchmark sources and is the Qdrant ecosystem default.
- Docker-compose specifics and Windows gotchas: **medium** — based on
  official Docker Desktop docs and community reports; not tested against
  this specific machine/WSL version, so coding_lt should smoke-test the
  compose file on the actual box before considering it final.
- Effort estimate: **medium** — depends on unseen schemas (AIPass mailbox
  JSON, Hermes memory SQLite) which should be inspected before commit.

## Next steps

1. coding_lt inspects the Hermes memory SQLite schema and AIPass mailbox
   JSON/text format (not available during this research pass) before
   implementing `ingest.py`.
2. Confirm with OB1's owner whether OB1 already indexes the vault in a way
   viking_search's `ingest.py` can reuse (avoid double embedding).
3. Decide server-mode Qdrant (recommended, supports concurrent agent access)
   vs. embedded `QDRANT_LOCAL_PATH` mode (fewer moving parts, single-writer
   limitation) — flagged in §2, needs a go/no-go from Helm/chief_of_staff.
