"""Fleet brain SQLite schema.

OB1-compatible memory layer for carrier_hermes bots.
Tables mirror the OB1 agent-memory spec but run entirely local via SQLite.

Scope system:
  'fleet'      — visible to all bots (e.g. Helm decisions, Probe research)
  'bot:<name>' — private to one bot (e.g. Mate's active error context)
"""

SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- ---------------------------------------------------------------------------
-- Core thoughts table  (OB1-compatible: same column names as Supabase OB1)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS thoughts (
  id            TEXT    PRIMARY KEY,          -- UUID
  content       TEXT    NOT NULL,
  summary       TEXT    NOT NULL DEFAULT '',
  source        TEXT    NOT NULL DEFAULT 'fleet',  -- 'fleet' | 'discord' | 'probe' | bot name
  scope         TEXT    NOT NULL DEFAULT 'fleet',  -- 'fleet' | 'bot:<name>'
  category      TEXT    NOT NULL DEFAULT 'knowledge',
  tags          TEXT    NOT NULL DEFAULT '[]',     -- JSON array
  metadata      TEXT    NOT NULL DEFAULT '{}',     -- JSON object
  created_at    REAL    NOT NULL,
  updated_at    REAL    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_thoughts_scope    ON thoughts(scope);
CREATE INDEX IF NOT EXISTS idx_thoughts_source   ON thoughts(source);
CREATE INDEX IF NOT EXISTS idx_thoughts_category ON thoughts(category);

-- ---------------------------------------------------------------------------
-- Embedding chunks (cosine search layer — same pattern as ob1-mcp-server)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS thought_chunks (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  thought_id TEXT    NOT NULL REFERENCES thoughts(id) ON DELETE CASCADE,
  chunk_idx  INTEGER NOT NULL DEFAULT 0,
  text       TEXT    NOT NULL,
  embedding  BLOB    NOT NULL,   -- float32 little-endian packed
  dim        INTEGER NOT NULL,
  UNIQUE(thought_id, chunk_idx)
);
CREATE INDEX IF NOT EXISTS idx_tc_thought ON thought_chunks(thought_id);

-- ---------------------------------------------------------------------------
-- Agent memory sidecars  (from schemas/agent-memory/schema.sql)
-- ---------------------------------------------------------------------------

-- Provenance & governed metadata for each thought
CREATE TABLE IF NOT EXISTS agent_memories (
  id                        TEXT    PRIMARY KEY,   -- same as thoughts.id
  thought_id                TEXT    NOT NULL REFERENCES thoughts(id) ON DELETE CASCADE,
  agent_id                  TEXT    NOT NULL,       -- bot name that wrote this
  lifecycle_status          TEXT    NOT NULL DEFAULT 'active'
                                    CHECK (lifecycle_status IN ('active','archived','superseded','retracted')),
  review_status             TEXT    NOT NULL DEFAULT 'pending'
                                    CHECK (review_status IN ('pending','approved','rejected','superseded')),
  confidence                REAL    NOT NULL DEFAULT 0.8
                                    CHECK (confidence BETWEEN 0.0 AND 1.0),
  can_use_as_instruction    INTEGER NOT NULL DEFAULT 0,  -- boolean
  can_use_as_evidence       INTEGER NOT NULL DEFAULT 1,  -- boolean
  requires_user_confirmation INTEGER NOT NULL DEFAULT 1,  -- boolean
  memory_kind               TEXT    NOT NULL DEFAULT 'knowledge'
                                    CHECK (memory_kind IN (
                                      'knowledge','decision','constraint','open_question',
                                      'failure','artifact_reference','work_log'
                                    )),
  scope                     TEXT    NOT NULL DEFAULT 'fleet',
  provenance_chain          TEXT    NOT NULL DEFAULT '[]',  -- JSON list of source refs
  created_at                REAL    NOT NULL,
  updated_at                REAL    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_am_agent  ON agent_memories(agent_id);
CREATE INDEX IF NOT EXISTS idx_am_scope  ON agent_memories(scope);
CREATE INDEX IF NOT EXISTS idx_am_kind   ON agent_memories(memory_kind);
CREATE INDEX IF NOT EXISTS idx_am_review ON agent_memories(review_status);

-- Recall traces (what a bot recalled and when)
CREATE TABLE IF NOT EXISTS recall_traces (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  agent_id      TEXT    NOT NULL,
  query         TEXT    NOT NULL,
  top_k         INTEGER NOT NULL DEFAULT 5,
  results       TEXT    NOT NULL DEFAULT '[]',  -- JSON [{thought_id, score}, ...]
  recalled_at   REAL    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rt_agent ON recall_traces(agent_id);

-- Audit events
CREATE TABLE IF NOT EXISTS audit_events (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  thought_id    TEXT    REFERENCES thoughts(id) ON DELETE SET NULL,
  agent_id      TEXT    NOT NULL,
  event_type    TEXT    NOT NULL
                        CHECK (event_type IN ('write','recall','review','retract','compact')),
  detail        TEXT    NOT NULL DEFAULT '{}',  -- JSON
  created_at    REAL    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ae_type  ON audit_events(event_type);
CREATE INDEX IF NOT EXISTS idx_ae_agent ON audit_events(agent_id);

-- Discord capture mirror  (replaces the Supabase edge function)
CREATE TABLE IF NOT EXISTS discord_messages (
  id          TEXT  PRIMARY KEY,    -- Discord message snowflake ID
  channel_id  TEXT  NOT NULL,
  channel_name TEXT NOT NULL DEFAULT '',
  guild_name  TEXT  NOT NULL DEFAULT '',
  author      TEXT  NOT NULL,
  content     TEXT  NOT NULL,
  thought_id  TEXT  REFERENCES thoughts(id) ON DELETE SET NULL,  -- link to thought
  captured_at REAL  NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_dm_channel ON discord_messages(channel_id);

-- Fleet meta (persistent KV)
CREATE TABLE IF NOT EXISTS fleet_meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""
