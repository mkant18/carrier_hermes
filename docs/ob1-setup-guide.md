# OB1 Fleet Brain — Setup Guide

> **Project name:** `carrier_hermes`
> Supabase cloud as primary backend, SQLite as automatic local fallback.
> **SQLite fallback works immediately — no Supabase setup required to use the fleet brain.**

---

## Architecture Overview

```
carrier_hermes bots
      │
      ▼
ob1-fleet-brain MCP server (Python, stdio)
      │
      ├─► Supabase cloud (pgvector, RLS)   ← primary
      │   carrier_hermes project
      │   URL: https://[project-ref].supabase.co
      │   Reads: SUPABASE_URL + SUPABASE_SERVICE_KEY
      │
      └─► SQLite local (carrier/ob1_brain.db)  ← auto-fallback
          Activates automatically if Supabase unreachable or not configured
```

---

## Quick Start — Local Only (No Supabase Needed)

The MCP server auto-falls back to SQLite if Supabase env vars are absent or the
connection fails. All tools work identically in both modes.

SQLite DB location:
```
C:/Users/micha/AppData/Local/hermes/carrier/ob1_brain.db
```

---

## Full Cloud Setup (Supabase Free Tier)

### ⚠️ Manual Steps Required

The following steps require human action in web dashboards.
The SQLite fallback works without any of these steps.

---

### Step 1 — Create the Supabase Project

1. Go to [supabase.com](https://supabase.com) → **Sign in** (GitHub login fastest)
2. Click **New Project**
3. Set **Project name:** `carrier_hermes` ← use exactly this name
4. The database password is already stored in Doppler as `SUPABASE_DB_PASSWORD`
   - Retrieve it: `doppler secrets get SUPABASE_DB_PASSWORD --project carrier-ops --config prd`
   - Paste it into the Supabase "Database Password" field
5. Pick the region closest to you (US East or EU West recommended)
6. Click **Create new project** — wait ~90 seconds

**Your Supabase URL will look like:**
```
https://[random-8-char-ref].supabase.co
```
Supabase slugifies the project name — it may not literally say `carrier-hermes`.
Find the exact URL in: **Settings (⚙) → API → Project URL**

---

### Step 2 — Run the SQL Migration

**Option A: Supabase SQL Editor (recommended)**

1. Supabase dashboard → **SQL Editor → New query**
2. Open `docs/ob1-supabase-setup.sql` from this repo
3. Paste the **entire file** into the editor
4. Click **Run**

**Option B: psql CLI**

```bash
# Get DB password from Doppler
DB_PASS=$(doppler secrets get SUPABASE_DB_PASSWORD --plain --project carrier-ops --config prd)

# Replace [project-ref] with your actual project ref from the dashboard URL
psql "postgresql://postgres:${DB_PASS}@db.[project-ref].supabase.co:5432/postgres" \
  -f docs/ob1-supabase-setup.sql
```

**Done when Table Editor shows all 11 tables:**
- `thoughts`
- `discord_messages`
- `fleet_meta`
- `agent_memories`
- `agent_memory_source_refs`
- `agent_memory_artifacts`
- `agent_memory_relations`
- `agent_memory_review_actions`
- `agent_memory_recall_traces`
- `agent_memory_recall_items`
- `agent_memory_audit_events`

Also confirm: **Database → Extensions** → `vector` is enabled (pgvector).

---

### Step 3 — Get Your API Keys from Supabase

In the Supabase dashboard: **Settings (⚙) → API**

You need **three values**:

| # | What to find | Where it is | Env var |
|---|---|---|---|
| 1 | **Project URL** | Top of the API page | `SUPABASE_URL` |
| 2 | **Anon/public key** | "Publishable keys" section, `anon` key, starts with `eyJ` | `SUPABASE_ANON_KEY` |
| 3 | **Service role key** | "Secret keys" section, `service_role` or `default`, starts with `eyJ` | `SUPABASE_SERVICE_KEY` |

> **⚠ Warning:** `SUPABASE_SERVICE_KEY` is the service role key — it bypasses all RLS policies.
> Never expose it in frontend code. The fleet brain uses it server-side only.
>
> The anon key (`SUPABASE_ANON_KEY`) is safe to expose publicly but is not used by
> the fleet brain itself (included for completeness).

---

### Step 4 — Add API Keys to Doppler

Run these commands, replacing the placeholder values with what you copied from Supabase:

```bash
# Replace https://[project-ref].supabase.co with your actual Project URL
doppler secrets set SUPABASE_URL='https://[project-ref].supabase.co' \
  --project carrier-ops --config prd

# Replace eyJ... with your actual anon key
doppler secrets set SUPABASE_ANON_KEY='eyJ...' \
  --project carrier-ops --config prd

# Replace eyJ... with your actual service role key
doppler secrets set SUPABASE_SERVICE_KEY='eyJ...' \
  --project carrier-ops --config prd
```

Verify everything is set:
```bash
doppler secrets get SUPABASE_URL SUPABASE_ANON_KEY SUPABASE_SERVICE_KEY \
  --project carrier-ops --config prd
```

---

### Step 5 — Test the Connection

```bash
cd C:/Users/micha/carrier_hermes
doppler run --project carrier-ops --config prd -- \
  python "C:/Users/micha/AppData/Local/hermes/carrier/ob1_brain/server.py"
```

**Expected output (Supabase connected):**
```
[ob1-fleet-brain] Supabase backend: connected (https://xxxx.supabase.co)
[ob1-fleet-brain] MCP server running on stdio
```

**Expected output (SQLite fallback):**
```
[ob1-fleet-brain] Supabase unreachable: <error> — falling back to SQLite
[ob1-fleet-brain] SQLite backend: C:/Users/micha/AppData/Local/hermes/carrier/ob1_brain.db
```

---

## MCP Tools Reference

All tools work identically regardless of backend (Supabase or SQLite).

| Tool | Description |
|---|---|
| `ob1_write_thought` | Store fleet knowledge with embeddings + agent memory sidecar |
| `ob1_search` | Semantic + keyword search across all memories |
| `ob1_recall` | Structured recall with trace logging |
| `ob1_list_thoughts` | Paginated list with scope/source/category filters |
| `ob1_get_thought` | Fetch one thought by ID |
| `ob1_brain_stats` | DB health, counts, active backend |
| `discord_capture_status` | Discord capture bot status + last captured message |
| `write_thought` | OB1 alias for `ob1_write_thought` |
| `search_thoughts` | OB1 alias for `ob1_search` |
| `list_thoughts` | OB1 alias for `ob1_list_thoughts` |
| `thought_stats` | OB1 alias for `ob1_brain_stats` |

---

## Discord Capture

The Discord capture bot monitors channel `1541866378255011980` (First Watch fleet channel).
Captured messages become `fleet_message` thoughts with `source=discord`.

**Bot token** is pulled automatically from Doppler:
```
DISCORD_FLEET_BOT_TOKEN (project: carrier-ops, config: prd)
```

**⚠ Manual step:** The Discord bot must have **Message Content Intent** enabled:
- Discord Developer Portal → Your App → **Bot** → Privileged Gateway Intents
- Toggle **Message Content Intent** ON

Start full stack (MCP server + Discord capture):
```bash
python C:/Users/micha/carrier_hermes/scripts/start_ob1_brain.py
```

Watchdog (checks if running, starts if not):
```bash
python C:/Users/micha/carrier_hermes/scripts/carrier_ob1_watchdog.py
# Prints: OB1_UP (already running) or OB1_STARTED (just launched)
```

---

## Supabase Features Used

| Feature | Usage |
|---|---|
| **pgvector** | 1536-dim embeddings for semantic search |
| **HNSW index** | Fast approximate nearest-neighbor search |
| **Row Level Security** | All tables locked to `service_role` only |
| **JSONB + GIN index** | Flexible metadata filtering |
| **PostgreSQL functions** | `match_thoughts` (cosine search), `upsert_thought` (dedup) |
| **Triggers** | Auto-update `updated_at` timestamps |
| **Free tier limits** | 500MB DB, 2 active projects — well within fleet needs |

---

## Doppler Secrets Summary

| Secret | Description | Source |
|---|---|---|
| `SUPABASE_DB_PASSWORD` | PostgreSQL password | Already in Doppler |
| `SUPABASE_URL` | Project URL from dashboard | Add after project creation |
| `SUPABASE_ANON_KEY` | Publishable key | Add after project creation |
| `SUPABASE_SERVICE_KEY` | Service role key | Add after project creation |
| `DISCORD_FLEET_BOT_TOKEN` | First Watch Discord bot token | Already in Doppler |

---

## Troubleshooting

**"permission denied for table thoughts"**
→ Re-run the `GRANT` statements in `ob1-supabase-setup.sql`

**"extension 'vector' does not exist"**
→ Run `CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions;` in SQL Editor,
  or Dashboard → Database → Extensions → search "vector" → enable pgvector

**Supabase connection times out**
→ Server auto-falls back to SQLite; check your `SUPABASE_URL` has `https://` prefix

**"Invalid API key" from Supabase**
→ Confirm you used the **service role** key (from "Secret keys" section), not the anon key

**Discord bot online but not capturing**
→ Verify "Message Content Intent" is enabled in Discord Developer Portal

**Discord messages not in Supabase**
→ Check that `SUPABASE_SERVICE_KEY` is correct; watch logs at
  `C:/Users/micha/AppData/Local/hermes/carrier/logs/discord_capture.log`
