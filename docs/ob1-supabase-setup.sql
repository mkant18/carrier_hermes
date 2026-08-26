-- ============================================================================
-- OB1 Fleet Brain — Supabase Cloud Setup Migration
-- Project: carrier_hermes (create at supabase.com with exactly this name)
-- Idempotent: safe to run multiple times (IF NOT EXISTS everywhere)
-- ============================================================================
-- Run this entire file in: Supabase → SQL Editor → New Query → Run
-- Or via psql:
--   psql "postgresql://postgres:$SUPABASE_DB_PASSWORD@db.[project-ref].supabase.co:5432/postgres" \
--        -f docs/ob1-supabase-setup.sql
-- ============================================================================

-- ---------------------------------------------------------------------------
-- Step 1: Enable pgvector extension (required for vector similarity search)
-- ---------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions;

-- ---------------------------------------------------------------------------
-- Step 2: Core thoughts table (OB1-compatible)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.thoughts (
  id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  content             TEXT        NOT NULL,
  embedding           vector(1536),   -- text-embedding-3-small dimension
  metadata            JSONB       NOT NULL DEFAULT '{}'::jsonb,
  content_fingerprint TEXT,           -- SHA-256 hex for dedup
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- HNSW index for fast cosine similarity search
CREATE INDEX IF NOT EXISTS idx_thoughts_embedding_hnsw
  ON public.thoughts USING hnsw (embedding vector_cosine_ops);

-- GIN index for JSONB metadata filtering
CREATE INDEX IF NOT EXISTS idx_thoughts_metadata_gin
  ON public.thoughts USING gin (metadata);

-- Date range queries
CREATE INDEX IF NOT EXISTS idx_thoughts_created_at
  ON public.thoughts (created_at DESC);

-- Dedup index
CREATE UNIQUE INDEX IF NOT EXISTS idx_thoughts_fingerprint
  ON public.thoughts (content_fingerprint)
  WHERE content_fingerprint IS NOT NULL;

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION public.update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS thoughts_updated_at ON public.thoughts;
CREATE TRIGGER thoughts_updated_at
  BEFORE UPDATE ON public.thoughts
  FOR EACH ROW EXECUTE FUNCTION public.update_updated_at();

-- ---------------------------------------------------------------------------
-- Step 3: Semantic search function (pgvector cosine)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.match_thoughts(
  query_embedding   vector(1536),
  match_threshold   float     DEFAULT 0.5,
  match_count       int       DEFAULT 10,
  filter            jsonb     DEFAULT '{}'::jsonb
)
RETURNS TABLE (
  id          uuid,
  content     text,
  metadata    jsonb,
  similarity  float,
  created_at  timestamptz
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    t.id,
    t.content,
    t.metadata,
    1 - (t.embedding <=> query_embedding) AS similarity,
    t.created_at
  FROM public.thoughts t
  WHERE 1 - (t.embedding <=> query_embedding) > match_threshold
    AND (filter = '{}'::jsonb OR t.metadata @> filter)
  ORDER BY t.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;

-- ---------------------------------------------------------------------------
-- Step 4: Upsert function (dedup by content fingerprint)
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.upsert_thought(
  p_content  TEXT,
  p_payload  JSONB DEFAULT '{}'
)
RETURNS JSONB AS $$
DECLARE
  v_fingerprint TEXT;
  v_id          UUID;
BEGIN
  v_fingerprint := encode(sha256(convert_to(
    lower(trim(regexp_replace(p_content, '\s+', ' ', 'g'))),
    'UTF8'
  )), 'hex');

  INSERT INTO public.thoughts (content, content_fingerprint, metadata)
  VALUES (p_content, v_fingerprint, COALESCE(p_payload->'metadata', '{}'::jsonb))
  ON CONFLICT (content_fingerprint)
  WHERE content_fingerprint IS NOT NULL DO UPDATE
  SET updated_at = now(),
      metadata   = public.thoughts.metadata || COALESCE(EXCLUDED.metadata, '{}'::jsonb)
  RETURNING id INTO v_id;

  RETURN jsonb_build_object('id', v_id, 'fingerprint', v_fingerprint);
END;
$$ LANGUAGE plpgsql;

-- ---------------------------------------------------------------------------
-- Step 5: Row Level Security — thoughts table
-- ---------------------------------------------------------------------------
ALTER TABLE public.thoughts ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "thoughts_service_role_all" ON public.thoughts;
CREATE POLICY "thoughts_service_role_all"
  ON public.thoughts
  FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);

-- Grant explicit table permissions (required on new Supabase projects)
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.thoughts TO service_role;

-- ---------------------------------------------------------------------------
-- Step 6: Discord messages table (capture mirror)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.discord_messages (
  id           TEXT        PRIMARY KEY,  -- Discord snowflake message ID
  channel_id   TEXT        NOT NULL,
  channel_name TEXT        NOT NULL DEFAULT '',
  guild_name   TEXT        NOT NULL DEFAULT '',
  author       TEXT        NOT NULL,
  content      TEXT        NOT NULL,
  thought_id   UUID        REFERENCES public.thoughts(id) ON DELETE SET NULL,
  captured_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_discord_messages_channel
  ON public.discord_messages (channel_id, captured_at DESC);

ALTER TABLE public.discord_messages ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "discord_messages_service_role_all" ON public.discord_messages;
CREATE POLICY "discord_messages_service_role_all"
  ON public.discord_messages
  FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.discord_messages TO service_role;

-- ---------------------------------------------------------------------------
-- Step 7: Agent memory sidecars (from schemas/agent-memory/schema.sql)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.agent_memories (
  id                        UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  thought_id                UUID        REFERENCES public.thoughts(id) ON DELETE SET NULL,
  workspace_id              TEXT        NOT NULL DEFAULT 'carrier_hermes',
  project_id                TEXT,
  channel_kind              TEXT,
  channel_id                TEXT,
  channel_thread_id         TEXT,
  visibility                TEXT        NOT NULL DEFAULT 'project'
                                        CHECK (visibility IN ('personal','channel','project','workspace','organization')),
  memory_type               TEXT        NOT NULL DEFAULT 'work_log'
                                        CHECK (memory_type IN (
                                          'decision','output','lesson','constraint',
                                          'open_question','failure','artifact_reference','work_log'
                                        )),
  summary                   TEXT        NOT NULL DEFAULT '',
  content                   TEXT        NOT NULL,
  lifecycle_status          TEXT        NOT NULL DEFAULT 'active'
                                        CHECK (lifecycle_status IN ('active','stale','superseded','disputed','rejected')),
  provenance_status         TEXT        NOT NULL DEFAULT 'generated'
                                        CHECK (provenance_status IN (
                                          'observed','inferred','user_confirmed','imported',
                                          'generated','superseded','disputed'
                                        )),
  confidence                NUMERIC(3,2) NOT NULL DEFAULT 0.50
                                        CHECK (confidence >= 0 AND confidence <= 1),
  created_by                TEXT        NOT NULL DEFAULT 'agent'
                                        CHECK (created_by IN ('user','agent','system','import')),
  runtime_name              TEXT,
  runtime_version           TEXT,
  provider                  TEXT,
  model                     TEXT,
  task_id                   TEXT,
  flow_id                   TEXT,
  can_use_as_instruction    BOOLEAN     NOT NULL DEFAULT false,
  can_use_as_evidence       BOOLEAN     NOT NULL DEFAULT true,
  requires_user_confirmation BOOLEAN    NOT NULL DEFAULT true,
  review_status             TEXT        NOT NULL DEFAULT 'pending'
                                        CHECK (review_status IN (
                                          'pending','confirmed','evidence_only',
                                          'restricted','rejected','stale','merged'
                                        )),
  last_confirmed_at         TIMESTAMPTZ,
  stale_after               TIMESTAMPTZ,
  idempotency_key           TEXT,
  content_hash              TEXT,
  metadata                  JSONB       NOT NULL DEFAULT '{}'::jsonb,
  created_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (
    can_use_as_instruction = false
    OR provenance_status IN ('user_confirmed','imported')
  )
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_memories_idempotency_key
  ON public.agent_memories (idempotency_key)
  WHERE idempotency_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_agent_memories_scope
  ON public.agent_memories (workspace_id, project_id, visibility);

CREATE INDEX IF NOT EXISTS idx_agent_memories_review
  ON public.agent_memories (review_status, lifecycle_status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_agent_memories_runtime_task
  ON public.agent_memories (runtime_name, task_id, flow_id);

CREATE INDEX IF NOT EXISTS idx_agent_memories_content_hash
  ON public.agent_memories (workspace_id, content_hash)
  WHERE content_hash IS NOT NULL;

-- Agent memory source refs
CREATE TABLE IF NOT EXISTS public.agent_memory_source_refs (
  id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  memory_id        UUID        NOT NULL REFERENCES public.agent_memories(id) ON DELETE CASCADE,
  source_kind      TEXT        NOT NULL,
  uri              TEXT,
  title            TEXT,
  source_timestamp TIMESTAMPTZ,
  metadata         JSONB       NOT NULL DEFAULT '{}'::jsonb,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_agent_memory_source_refs_memory
  ON public.agent_memory_source_refs (memory_id);

-- Agent memory artifacts
CREATE TABLE IF NOT EXISTS public.agent_memory_artifacts (
  id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  memory_id     UUID        NOT NULL REFERENCES public.agent_memories(id) ON DELETE CASCADE,
  artifact_kind TEXT        NOT NULL,
  uri           TEXT        NOT NULL,
  description   TEXT,
  metadata      JSONB       NOT NULL DEFAULT '{}'::jsonb,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_agent_memory_artifacts_memory
  ON public.agent_memory_artifacts (memory_id);

-- Agent memory relations
CREATE TABLE IF NOT EXISTS public.agent_memory_relations (
  id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  from_memory_id  UUID        NOT NULL REFERENCES public.agent_memories(id) ON DELETE CASCADE,
  to_memory_id    UUID        NOT NULL REFERENCES public.agent_memories(id) ON DELETE CASCADE,
  relation        TEXT        NOT NULL
                              CHECK (relation IN ('related_to','supersedes','superseded_by','conflicts_with','merged_into')),
  confidence      NUMERIC(3,2) DEFAULT 0.50
                              CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
  metadata        JSONB       NOT NULL DEFAULT '{}'::jsonb,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (from_memory_id, to_memory_id, relation),
  CHECK (from_memory_id <> to_memory_id)
);

-- Agent memory review actions
CREATE TABLE IF NOT EXISTS public.agent_memory_review_actions (
  id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  memory_id    UUID        NOT NULL REFERENCES public.agent_memories(id) ON DELETE CASCADE,
  action       TEXT        NOT NULL
                           CHECK (action IN (
                             'confirm','edit','evidence_only','restrict_scope',
                             'mark_stale','merge','reject','dispute','supersede'
                           )),
  actor_id     TEXT,
  actor_label  TEXT,
  notes        TEXT,
  before       JSONB,
  after        JSONB,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_agent_memory_review_actions_memory
  ON public.agent_memory_review_actions (memory_id, created_at DESC);

-- Agent memory recall traces
CREATE TABLE IF NOT EXISTS public.agent_memory_recall_traces (
  id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  request_id       UUID        NOT NULL DEFAULT gen_random_uuid(),
  workspace_id     TEXT        NOT NULL DEFAULT 'carrier_hermes',
  project_id       TEXT,
  runtime_name     TEXT,
  runtime_version  TEXT,
  task_id          TEXT,
  flow_id          TEXT,
  channel_kind     TEXT,
  channel_id       TEXT,
  query            TEXT        NOT NULL,
  schema_version   TEXT        NOT NULL DEFAULT 'v1',
  request_payload  JSONB       NOT NULL DEFAULT '{}'::jsonb,
  response_policy  JSONB       NOT NULL DEFAULT '{}'::jsonb,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (request_id)
);

CREATE INDEX IF NOT EXISTS idx_agent_memory_recall_traces_scope
  ON public.agent_memory_recall_traces (workspace_id, project_id, created_at DESC);

-- Agent memory recall items
CREATE TABLE IF NOT EXISTS public.agent_memory_recall_items (
  id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  trace_id            UUID        NOT NULL REFERENCES public.agent_memory_recall_traces(id) ON DELETE CASCADE,
  memory_id           UUID        NOT NULL REFERENCES public.agent_memories(id) ON DELETE CASCADE,
  rank                INTEGER     NOT NULL,
  similarity          NUMERIC(5,4),
  ranking_score       NUMERIC(7,4),
  returned            BOOLEAN     NOT NULL DEFAULT true,
  used                BOOLEAN,
  ignored_reason      TEXT,
  use_policy_snapshot JSONB       NOT NULL DEFAULT '{}'::jsonb,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (trace_id, memory_id)
);

CREATE INDEX IF NOT EXISTS idx_agent_memory_recall_items_trace
  ON public.agent_memory_recall_items (trace_id, rank);

-- Agent memory audit events
CREATE TABLE IF NOT EXISTS public.agent_memory_audit_events (
  id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  event_type   TEXT        NOT NULL
                           CHECK (event_type IN (
                             'recall_requested','memory_returned','memory_used','memory_ignored',
                             'memory_written','memory_confirmed','memory_edited',
                             'memory_rejected','memory_superseded','memory_disputed'
                           )),
  workspace_id TEXT,
  project_id   TEXT,
  memory_id    UUID        REFERENCES public.agent_memories(id) ON DELETE SET NULL,
  trace_id     UUID        REFERENCES public.agent_memory_recall_traces(id) ON DELETE SET NULL,
  actor_kind   TEXT        NOT NULL DEFAULT 'system'
                           CHECK (actor_kind IN ('user','agent','system','import')),
  actor_label  TEXT,
  runtime_name TEXT,
  task_id      TEXT,
  payload      JSONB       NOT NULL DEFAULT '{}'::jsonb,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_agent_memory_audit_scope
  ON public.agent_memory_audit_events (workspace_id, project_id, created_at DESC);

-- updated_at trigger for agent_memories
CREATE OR REPLACE FUNCTION public.agent_memories_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_agent_memories_updated_at ON public.agent_memories;
CREATE TRIGGER trg_agent_memories_updated_at
  BEFORE UPDATE ON public.agent_memories
  FOR EACH ROW EXECUTE FUNCTION public.agent_memories_set_updated_at();

-- Content hash helper
CREATE OR REPLACE FUNCTION public.agent_memory_hash_text(p_content TEXT)
RETURNS TEXT
LANGUAGE plpgsql
IMMUTABLE
AS $$
BEGIN
  RETURN encode(sha256(convert_to(
    lower(trim(regexp_replace(coalesce(p_content,''), '\s+', ' ', 'g'))),
    'UTF8'
  )), 'hex');
END;
$$;

-- RLS for agent memory tables
ALTER TABLE public.agent_memories                ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.agent_memory_source_refs      ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.agent_memory_artifacts        ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.agent_memory_relations        ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.agent_memory_review_actions   ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.agent_memory_recall_traces    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.agent_memory_recall_items     ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.agent_memory_audit_events     ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS agent_memories_service_role_all ON public.agent_memories;
CREATE POLICY agent_memories_service_role_all ON public.agent_memories
  FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS agent_memory_source_refs_service_role_all ON public.agent_memory_source_refs;
CREATE POLICY agent_memory_source_refs_service_role_all ON public.agent_memory_source_refs
  FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS agent_memory_artifacts_service_role_all ON public.agent_memory_artifacts;
CREATE POLICY agent_memory_artifacts_service_role_all ON public.agent_memory_artifacts
  FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS agent_memory_relations_service_role_all ON public.agent_memory_relations;
CREATE POLICY agent_memory_relations_service_role_all ON public.agent_memory_relations
  FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS agent_memory_review_actions_service_role_all ON public.agent_memory_review_actions;
CREATE POLICY agent_memory_review_actions_service_role_all ON public.agent_memory_review_actions
  FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS agent_memory_recall_traces_service_role_all ON public.agent_memory_recall_traces;
CREATE POLICY agent_memory_recall_traces_service_role_all ON public.agent_memory_recall_traces
  FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS agent_memory_recall_items_service_role_all ON public.agent_memory_recall_items;
CREATE POLICY agent_memory_recall_items_service_role_all ON public.agent_memory_recall_items
  FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS agent_memory_audit_events_service_role_all ON public.agent_memory_audit_events;
CREATE POLICY agent_memory_audit_events_service_role_all ON public.agent_memory_audit_events
  FOR ALL TO service_role USING (true) WITH CHECK (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.agent_memories TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.agent_memory_source_refs TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.agent_memory_artifacts TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.agent_memory_relations TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.agent_memory_review_actions TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.agent_memory_recall_traces TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.agent_memory_recall_items TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.agent_memory_audit_events TO service_role;

-- ---------------------------------------------------------------------------
-- Step 8: Fleet meta KV table
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.fleet_meta (
  key        TEXT        PRIMARY KEY,
  value      TEXT        NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE public.fleet_meta ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS fleet_meta_service_role_all ON public.fleet_meta;
CREATE POLICY fleet_meta_service_role_all ON public.fleet_meta
  FOR ALL TO service_role USING (true) WITH CHECK (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.fleet_meta TO service_role;

-- ---------------------------------------------------------------------------
-- Verification query — run after migration to confirm all tables exist
-- ---------------------------------------------------------------------------
-- SELECT table_name FROM information_schema.tables
-- WHERE table_schema = 'public'
--   AND table_name IN (
--     'thoughts', 'discord_messages', 'fleet_meta',
--     'agent_memories', 'agent_memory_source_refs', 'agent_memory_artifacts',
--     'agent_memory_relations', 'agent_memory_review_actions',
--     'agent_memory_recall_traces', 'agent_memory_recall_items',
--     'agent_memory_audit_events'
--   )
-- ORDER BY table_name;
-- Expected: 11 rows
