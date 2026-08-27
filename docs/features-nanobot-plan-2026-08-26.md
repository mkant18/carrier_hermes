# Integration Design Plan: nanobot Dream Memory System
## Silent Running Cycle 12 — FEATURES Step 2 of 4

**Date:** 2026-08-26
**Author:** coding_lt (Wrench)
**Source scout:** docs/features-scout-2026-08-26.md (t_36cff371)
**Status:** Planning — no code written or modified

---

## 1. Dream Memory Architecture

### What is it?

nanobot (https://github.com/HKUDS/nanobot) is an ultra-lightweight Python AI agent
framework that ships a "Dream" long-term memory subsystem as a first-class component.
Dream memory is designed to solve the persistent-agent problem: how does a conversational
agent remember what happened last week without requiring a dedicated vector database?

### How it works (from nanobot README and source analysis)

Dream memory operates in two layers:

**Layer 1 — Session record (what happened)**
Every conversation turn is written to a local flat-file or SQLite log keyed by
session-id and timestamp. No embedding, no vector store. The raw transcript is the
record. Storage cost: ~1-2 KB per turn, negligible.

**Layer 2 — Dream index (how to find it)**
Periodically (or at session end), nanobot runs a lightweight "dream pass" that:
1. Summarizes recent conversation turns into semantic chunks (via the configured LLM —
   Ollama/local by default; any OpenAI-compatible endpoint works).
2. Writes chunk embeddings using a local embedding model (default: FastEmbed /
   bge-small-en-v1.5 — same model the Qdrant ecosystem uses as its default).
3. Upserts chunks into a local SQLite FTS5 index (BM25 full-text) or a Qdrant
   collection depending on config. The FTS5 path has zero external dependencies.
4. On the next session, retrieval fans out over both the FTS5 index (keyword) and the
   embedding index (semantic) and merges results by score before injecting into context.

**Key properties:**
- No vector-DB required for the default FTS5 path (SQLite is already present everywhere).
- Local-model-first: summarization and embedding default to Ollama endpoints.
- Incremental: only new turns are processed; old chunks are not re-embedded.
- Per-agent: each nanobot agent instance has its own Dream index. No cross-agent leakage.
- Format: Dream index stored under `~/.nanobot/<agent_id>/memory/` (configurable).

**Discord allow-list:**
nanobot also ships a channel whitelist feature for Discord: agents only respond in
explicitly whitelisted channel IDs, configured per-agent in the YAML. This solves the
exact problem carrier_hermes faces in shared Discord servers (bots responding everywhere).

### Why this matters (2026 context)

The scout report noted "Memory is the new middleware." Dream's key innovation is the
two-path retrieval (BM25 + semantic) without requiring a running vector-DB service.
The ecosystem default (FTS5) means zero ops burden for the first adoption step.

---

## 2. carrier_hermes Fit

### Current memory state in carrier_hermes

Each Hermes bot profile has a native `memory` tool backed by a per-profile SQLite store
(`~/.hermes/profiles/<bot_id>/memory.db`). Entries are short declarative facts written
manually by the agent, injected at every turn. The memory store has a ~2,200-char cap
per profile (observed: coding_lt memory at 22% / 487 chars). Key limitations:

- **No conversation history retrieval.** The memory tool stores facts, not conversations.
  Once a session ends, the transcript is only accessible via `session_search` (full-text
  search over the session DB). There is no semantic "what did we discuss last month about X?"
- **Manual curation only.** Agents must explicitly call `memory add/replace/remove`. Nothing
  is automatically learned from conversations.
- **No cross-session context injection.** When a kanban task spawns a fresh agent session,
  the agent receives only: its SOUL.md, injected memory facts, and the task body. Prior
  conversation context must be manually reconstructed via `session_search`.
- **Silent Running Tier 3** is explicitly "optimize/perfect agent memories via the
  OpenViking L0/L1/L2 concept" — acknowledging this as the current gap. The silent_running_memory.py
  script builds a review queue but relies on manual LT + Helm OAuth review of each change.

### Which bots would benefit most

**Priority 1 — Helm (chief_of_staff)**
Helm has the richest conversation history and the most to gain from semantic retrieval.
Michael's instructions, past decisions, carrier config preferences — these accumulate
over weeks and are currently either in the manual memory store (capped) or lost in
session DB. Dream memory would let Helm answer "what did Michael decide about X two
weeks ago?" without session_search guesswork.

**Priority 2 — Mate (firstmate) / coding_lt**
Every coding sortie starts from a fresh session. Mate currently depends on Wrench
packaging a self-contained job packet every time. Dream memory would let Mate recall
recurring patterns: preferred test frameworks, known blockers, repo conventions. Reduces
job packet boilerplate and Mate re-learning the same context.

**Priority 3 — Probe (research_agent)**
Research sorties currently produce docs written to `_agent/research/`. There is no
mechanism to ask "what did Probe learn about X during its last 10 runs?" Dream memory
across research sessions would build an incremental knowledge base, reducing repeated
web crawls on the same topic.

**Priority 4 — Fleet-wide (all bots)**
Any bot that spawns repeatedly (crons, Vigil, Ledger) could benefit from automated
conversation logging and Dream indexing, eliminating the need for manual memory curation
entirely.

### OpenViking / viking_search relationship

The viking_search research (docs/viking-mcp-research.md) addresses cross-source unified
search over Obsidian vault + AIPass mailbox + fleet docs + Hermes memory SQLite. That is
an orthogonal need. Dream memory is per-agent conversation history — it answers "what
did this bot do and learn?" not "what's in the vault?" The two are complementary:
- Dream memory: per-bot conversation indexing, automatic, low-ops
- viking_search: cross-corpus unified semantic search for humans + Helm

Dream is lower-lift and higher-value for the immediate memory gap. viking_search remains
on the backlog but is not a prerequisite.

---

## 3. Integration Options

### Option A: Adopt nanobot Dream as a standalone Python module (pip + config)

Install nanobot directly. Run it as a memory sidecar: each Hermes bot session, after
completing a kanban task, triggers a nanobot Dream "dream pass" that ingests the session
transcript. Retrieval is available via nanobot's Python API or CLI.

**How it would work:**
1. `pip install nanobot` (or install from source, MIT license).
2. Configure a nanobot agent config per bot profile: session log path points to Hermes
   session DB or transcript export. Embedding model: local FastEmbed/bge-small-en-v1.5.
   LLM: Ollama (qwen2.5:7b already available on carrier host).
3. Add a post-task script to kanban task completion hook (or a cron) that calls
   `nanobot dream --agent <bot_id> --ingest-session <session_id>`.
4. Add a Dream retrieval MCP tool or skill that agents can call to query their own
   Dream index before starting a new task.

**Pros:** Zero re-implementation. Proven, 47k-star codebase. Fast to pilot.
**Cons:** External dependency; nanobot's data model may not map cleanly to Hermes session DB
format; requires Mate to write an ingestion adapter and a retrieval tool/skill; nanobot's
own Discord/Telegram channel layer is a distraction (we only want Dream, not the whole framework).
**Risk:** Medium. The session-transcript-to-nanobot-format adapter is the unknown.

### Option B: Lift the core Dream memory algorithm and reimplement as a carrier_hermes plugin

Study nanobot's Dream source (MIT license), extract the algorithm (session chunking +
FTS5/BM25 index + embedding upsert + hybrid retrieval), and implement it as a
carrier_hermes native plugin. The plugin would add two tools: `dream_ingest` and
`dream_search`, available to any bot with the plugin enabled.

**How it would work:**
1. Probe reads the nanobot Dream source files in detail and documents the exact algorithm.
2. Mate implements a Python plugin (`plugins/dream_memory/`) with:
   - `dream_ingest(session_id)`: reads Hermes session DB, chunks + embeds new turns,
     upserts to per-profile SQLite FTS5 + optional Qdrant collection.
   - `dream_search(query, top_k=5)`: hybrid BM25 + semantic search over the profile's
     Dream index, returns ranked excerpts for context injection.
3. Hermes plugin registration + tool exposure in BOT_MATRIX.md for approved profiles.
4. Optional: post-task kanban hook or Tier 3 Silent Running cron calls `dream_ingest`
   automatically after each session.

**Pros:** No external framework dependency. Plugin lives in carrier_hermes repo, fully
auditable and tunable. Integrates natively with Hermes tool system. Avoids nanobot's
non-memory components entirely.
**Cons:** Higher implementation effort. Algorithm bugs are on us, not nanobot upstream.
Requires Probe research sortie + Mate implementation sortie.
**Risk:** Low-medium. The algorithm is well-understood (FTS5 BM25 + embeddings is mature tech).
The carrier_hermes plugin system is operational; this is a greenfield plugin with no
migration risk.

### Option C: Study and inform current MEMORY.md / OpenViking Tier 3 approach (no new code)

Probe reads nanobot's Dream design in detail. The findings inform how Helm and coding_lt
manually curate agent memories during Tier 3 Silent Running runs: specifically, adopting
nanobot's session-chunking heuristics (what to summarize, what to discard) as a manual
protocol for the existing memory tool. No new code.

**How it would work:**
1. Probe produces a "Dream patterns for manual memory curation" reference doc.
2. Tier 3 Silent Running memory.py script is updated to apply nanobot's chunking
   heuristics when building the memory review queue.
3. No new storage. No new indexing. Same ~2,200-char cap, same manual process.

**Pros:** Zero risk. Zero implementation. Can be done this week.
**Cons:** Doesn't actually solve the problem. Memory cap stays at 2,200 chars. No
conversation history retrieval. No semantic search. Tier 3 stays manual and OAuth-expensive.
**Risk:** None (but so is the benefit).

---

## 4. Recommended Option

**Recommendation: Option B — Reimplement as a carrier_hermes plugin.**

Justification:

1. **Scope.** Option A (pip install nanobot) requires writing an adapter between Hermes
   session DB and nanobot's transcript format — an unknown that makes the lift closer to
   Option B anyway, with the added cost of pulling in an entire framework we only want
   10% of.

2. **Risk.** Option B's algorithm is well-documented and the nanobot source is MIT-licensed
   reference material. FTS5 BM25 is a Python stdlib operation (sqlite3). FastEmbed is
   already the Qdrant ecosystem default. Mate has implemented more complex plugins.

3. **Benefit.** A native carrier_hermes plugin integrates with the Hermes tool system
   directly: `dream_search` becomes a first-class tool callable from any bot's turn, no
   subprocess or sidecar required. It appears in BOT_MATRIX.md with proper scope controls.

4. **Strategic fit.** The plugin doubles as the foundation for Tier 3 Silent Running
   automation: instead of manual OAuth-expensive memory review, the Dream ingest cron
   handles session archiving automatically, and Tier 3 becomes a curator pass over the
   Dream index rather than a from-scratch recall effort.

5. **Option C is insufficient.** The memory gap is structural, not procedural. Manual
   curation of a 2,200-char flat store cannot replace semantic conversation retrieval.

**Risk acceptance:** The main unknown is embedding model performance on the carrier
host (CPU-only unless Ollama GPU is warmed). FastEmbed bge-small-en-v1.5 is validated
at ~255 chunks/s CPU — sufficient for background ingest. This should be verified in
Phase 1 before committing to the full implementation.

---

## 5. Implementation Phases (Option B)

### Phase 1 — Research & Spec (Probe + Wrench)
**Output:** `docs/dream-memory-spec.md`

- Probe reads nanobot source (specifically `nanobot/memory/`, `nanobot/dream.py` or
  equivalent memory modules) and documents:
  - Exact chunking strategy (turn count, token budget, overlap)
  - Summarization prompt template
  - FTS5 schema (table structure, indexing fields)
  - Embedding model call pattern (FastEmbed API)
  - Hybrid retrieval merge algorithm (BM25 score normalization + cosine similarity blend)
- Wrench reviews spec for carrier_hermes fit and signs off.
- **Gate:** Wrench approves spec before Phase 2 begins.

### Phase 2 — Plugin skeleton (Mate)
**Output:** `plugins/dream_memory/__init__.py`, `plugins/dream_memory/schema.sql`, unit tests

- Mate creates the plugin directory structure in the carrier_hermes repo.
- Implements `dream_ingest(profile_id, session_id)`:
  - Reads Hermes session DB (read-only connection)
  - Chunks session messages per spec
  - Runs local FastEmbed embedding (bge-small-en-v1.5)
  - Upserts to per-profile FTS5 SQLite Dream index at
    `~/.hermes/profiles/<profile_id>/dream.db`
- Implements `dream_search(profile_id, query, top_k=5)`:
  - BM25 FTS5 query
  - Embedding similarity query
  - Merge and re-rank by score
  - Returns ranked list of (session_id, timestamp, excerpt) tuples
- Unit tests: ingest a synthetic 10-turn session, verify FTS5 hit + embedding hit.
- **Gate:** Tests pass, Wrench reviews output before Phase 3.

### Phase 3 — Tool registration & BOT_MATRIX wiring (Mate + Wrench)
**Output:** Updated BOT_MATRIX.md, plugin config, `dream_search` tool available to Helm + Wrench + Mate

- Register `dream_memory` plugin in Hermes plugin system.
- Add `dream_search` tool to: `chief_of_staff`, `coding_lt`, `firstmate`,
  `research_agent` (flagged as Phase 3 scope).
- Add `dream_ingest` as a post-task kanban hook (called by the dispatcher after
  `kanban_complete` with the session ID — check if Hermes dispatcher supports a
  post-complete hook; if not, implement as a Tier 3 cron script instead).
- Manual smoke test: Helm runs `dream_search("what did Michael decide about X")` and
  retrieves a real past session excerpt.
- **Gate:** End-to-end smoke test passes, Michael approves tool exposure.

### Phase 4 — Tier 3 Silent Running automation (Mate)
**Output:** Updated `silent_running_memory.py` — replaces manual queue with Dream ingest

- Replace the current "build review queue → manual Helm OAuth review" loop with
  automated Dream ingest cron:
  - Every Tier 3 activation: run `dream_ingest` for all profiles with sessions
    since last ingest.
  - Memory tool manual curation (the current Tier 3 work) now focuses only on
    the high-level fact store (stable preferences, conventions) — not on session recall.
- Update `docs/silent-running.md` Tier 3 section to reflect the new split:
  - Dream index: automated (Tier 3 cron, no LLM cost for ingest)
  - Memory fact store: manual OAuth curation, much lower frequency (weekly vs. per-cycle)
- **Gate:** One full Silent Running cycle with automated Dream ingest, no regressions.

### Phase 5 — Discord allow-list port (Mate + Helm)
**Output:** Discord gateway config per-channel allow-list feature

- Separate from Dream memory but part of the nanobot study scope.
- Helm reviews nanobot's Discord allow-list YAML config pattern.
- Mate implements an equivalent in carrier_hermes's Discord gateway config:
  per-bot channel whitelist (bot only responds in listed channel IDs).
- Wrench dispatches to Mate only after Phases 1-4 are stable.
- **Gate:** Helm + Michael test in #fleet and #command before enabling on Helm.

---

## 6. Open Questions for Michael

**Q1 — Implementation option confirmation**
This plan recommends Option B (reimplementing Dream as a carrier_hermes plugin). Do
you want to proceed with Option B, or would you prefer Option A (pip nanobot, faster
but heavier dependency) or Option C (study only, no implementation)?

**Q2 — Embedding infrastructure**
Phase 2 requires FastEmbed to run on the carrier host for local embedding. FastEmbed
uses ONNX Runtime (no PyTorch, CPU-only viable). Is it acceptable to `pip install
fastembed` on the carrier host (Windows 11, Michael's PC)? Or should embeddings route
to Ollama instead (slower but no new Python dependency)?

**Q3 — Dream index storage location**
Plan puts per-bot Dream indexes at `~/.hermes/profiles/<profile_id>/dream.db`. Is that
acceptable, or should all Dream indexes go under a shared path (e.g.
`C:/Users/micha/AppData/Local/hermes/dream/`) for easier backup and inspection?

**Q4 — Which profiles get dream_search first?**
Phase 3 proposes enabling `dream_search` for Helm, Wrench, Mate, and Probe first.
Any profiles that should be excluded (e.g. Vigil/Ledger — these are monitoring bots
where conversation history retrieval is less useful)?

**Q5 — Post-task ingest hook**
The cleanest trigger for `dream_ingest` is a post-`kanban_complete` hook in the
dispatcher. Does the Hermes kanban dispatcher support a post-complete hook (a script or
tool call triggered automatically when a task is marked done)? If not, the fallback is
a Tier 3 cron — slightly less immediate but still functional. Wrench doesn't have
terminal access to verify dispatcher internals.

**Q6 — Discord allow-list priority**
Should the Discord allow-list feature (Phase 5) be deprioritized until Dream memory is
stable (Phases 1-4), or is it urgent enough to run in parallel? It's a simpler change
but involves the Discord gateway config, which touches Helm directly.

---

## 7. Kanban Decomposition Sketch

Tasks for Marshal to create (titles only, for Helm review before Marshal acts):

1. DREAM P1: Probe reads nanobot Dream source and produces dream-memory-spec.md
2. DREAM P1 Review: Wrench reviews dream-memory-spec.md (dependency: task 1)
3. DREAM P2: Mate implements dream_ingest + dream_search plugin with unit tests (dependency: task 2)
4. DREAM P2 Review: Wrench reviews Phase 2 plugin output (dependency: task 3)
5. DREAM P3: Mate wires dream_memory plugin to Hermes tool system + BOT_MATRIX (dependency: task 4)
6. DREAM P3 Smoke: Helm + Michael smoke test dream_search end-to-end (dependency: task 5)
7. DREAM P4: Mate updates silent_running_memory.py to automated Dream ingest (dependency: task 6)
8. DREAM P4 Validation: One full Silent Running cycle with Dream ingest active (dependency: task 7)
9. DREAM P5: Mate implements Discord channel allow-list in carrier_hermes gateway (can start after task 6)
10. DREAM Retro: Helm publishes Cycle 12 Features retrospective to #fleet

Total: 10 tasks across 5 phases. Parallel opportunity: Task 9 (Discord allow-list) can
run concurrently with Tasks 7-8 once the gateway config is understood.

---

## Next Step

**Features pipeline step 3: Marshal decomposition.**

On Michael's approval of this plan, Helm tasks Marshal to create the 10 Kanban tasks
listed in Section 7 on the `carrier` board, with correct `parents` dependencies
encoding the phase gates. Marshal will not act until Helm explicitly says "go" —
this plan is for Michael's review first.

Assignees by task:
- Tasks 1, 3, 5, 7, 9: `firstmate` (implementation) or `research_agent` (task 1)
- Tasks 2, 4, 6: `coding_lt` (Wrench review gate)
- Task 8: `chief_of_staff` (Helm validation)
- Task 10: `chief_of_staff` (Helm retro)

Step 4 (build cycle) begins when Marshal's cards are created and the Phase 1 Probe
sortie completes with an approved spec.

---

*Plan produced by coding_lt (Wrench) — planning/research only, no code written or modified.*
