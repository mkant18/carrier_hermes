"""Discord capture bot for OB1 Fleet Brain.

Monitors Discord channel 1541866378255011980 (First Watch fleet channel)
and writes captured messages as thoughts with type=fleet_message, source=discord.

Works with both Supabase (primary) and SQLite (fallback) backends — just
imports the same write_thought tool the MCP server exposes.

Bot token: fetched from Doppler (DISCORD_FLEET_BOT_TOKEN) or environment.
Channel:   1541866378255011980 (fleet channel — hardcoded, also reads OB1_DISCORD_CHANNELS)

Adapted from: https://github.com/NateBJones-Projects/OB1/tree/main/integrations/discord-capture
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

log = logging.getLogger("ob1-discord-capture")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

FLEET_CHANNEL_ID = int(os.environ.get("OB1_DISCORD_CHANNELS", "1541866378255011980").split(",")[0].strip())
IGNORE_BOTS = os.environ.get("OB1_DISCORD_IGNORE_BOTS", "1").strip() == "1"
UPDATE_ON_EDIT = os.environ.get("UPDATE_ON_EDIT", "0").strip() == "1"

# Supabase config (mirrors server.py)
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

# SQLite fallback path
DEFAULT_DB_PATH = Path(
    os.environ.get("OB1_BRAIN_DB",
                   "C:/Users/micha/AppData/Local/hermes/carrier/ob1_brain.db")
)

# ---------------------------------------------------------------------------
# Doppler fetch
# ---------------------------------------------------------------------------

def _doppler_get(key: str, project: str = "carrier-ops", config: str = "prd") -> str:
    try:
        r = subprocess.run(
            ["doppler", "secrets", "get", key, "--plain", "--project", project, "--config", config],
            capture_output=True, text=True, timeout=15,
        )
        if r.returncode == 0:
            return r.stdout.strip()
        log.warning("Doppler fetch failed for %s: %s", key, r.stderr.strip())
    except Exception as exc:
        log.warning("Doppler unavailable: %s", exc)
    return ""


def get_bot_token() -> str:
    token = os.environ.get("DISCORD_FLEET_BOT_TOKEN", "")
    if not token:
        log.info("Fetching DISCORD_FLEET_BOT_TOKEN from Doppler...")
        token = _doppler_get("DISCORD_FLEET_BOT_TOKEN")
        if token:
            os.environ["DISCORD_FLEET_BOT_TOKEN"] = token
            log.info("Got DISCORD_FLEET_BOT_TOKEN from Doppler OK")
        else:
            log.error("No DISCORD_FLEET_BOT_TOKEN available — capture disabled")
    return token


def _resolve_supabase_creds() -> None:
    """Fetch Supabase creds from Doppler if not in env."""
    global SUPABASE_URL, SUPABASE_SERVICE_KEY
    if not SUPABASE_URL:
        SUPABASE_URL = _doppler_get("SUPABASE_URL")
        if SUPABASE_URL:
            os.environ["SUPABASE_URL"] = SUPABASE_URL
    if not SUPABASE_SERVICE_KEY:
        SUPABASE_SERVICE_KEY = _doppler_get("SUPABASE_SERVICE_KEY")
        if SUPABASE_SERVICE_KEY:
            os.environ["SUPABASE_SERVICE_KEY"] = SUPABASE_SERVICE_KEY


# ---------------------------------------------------------------------------
# Storage backend (mirrors server.py logic)
# ---------------------------------------------------------------------------

class _SupabaseWriter:
    def __init__(self):
        from supabase import create_client  # type: ignore
        self._client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        self._client.table("thoughts").select("id", count="exact", head=True).execute()
        log.info("Discord capture: Supabase backend connected")

    def write_discord_message(
        self,
        msg_id: str,
        channel_id: str,
        channel_name: str,
        guild_name: str,
        author: str,
        content: str,
        timestamp: str,
    ) -> str:
        """Write message to Supabase thoughts + discord_messages tables."""
        sb = self._client

        # Build thought content
        thought_text = (
            f"[Discord #{channel_name} @ {guild_name}] {author}: {content}"
        )
        metadata = {
            "source": "discord",
            "type": "fleet_message",
            "topics": ["fleet", "discord"],
            "category": "fleet_message",
            "scope": "fleet",
            "channel_id": str(channel_id),
            "channel_name": channel_name,
            "guild_name": guild_name,
            "author": author,
            "timestamp": timestamp,
            "discord_msg_id": msg_id,
        }

        # Upsert thought
        payload = {"metadata": metadata}
        result = sb.rpc("upsert_thought", {
            "p_content": thought_text,
            "p_payload": payload,
        }).execute()
        thought_id = result.data.get("id") if isinstance(result.data, dict) else None

        # Insert discord_messages mirror
        try:
            sb.table("discord_messages").upsert({
                "id": msg_id,
                "channel_id": str(channel_id),
                "channel_name": channel_name,
                "guild_name": guild_name,
                "author": author,
                "content": content,
                "thought_id": thought_id,
                "captured_at": timestamp,
            }).execute()
        except Exception as exc:
            log.warning("discord_messages upsert failed: %s", exc)

        return thought_id or "unknown"


class _SQLiteWriter:
    def __init__(self):
        # Add ob1_brain dir to sys.path
        brain_dir = Path(__file__).parent
        if str(brain_dir) not in sys.path:
            sys.path.insert(0, str(brain_dir))
        from store import FleetBrainStore  # type: ignore
        from embedder import Embedder, DEFAULT_MODEL, chunk_text  # type: ignore
        self._store = FleetBrainStore(DEFAULT_DB_PATH)
        self._embedder = Embedder(os.environ.get("OB1_MODEL", DEFAULT_MODEL))
        self._chunk_text = chunk_text
        log.info("Discord capture: SQLite backend at %s", DEFAULT_DB_PATH)

    def write_discord_message(
        self,
        msg_id: str,
        channel_id: str,
        channel_name: str,
        guild_name: str,
        author: str,
        content: str,
        timestamp: str,
    ) -> str:
        thought_text = (
            f"[Discord #{channel_name} @ {guild_name}] {author}: {content}"
        )
        metadata = {
            "source": "discord",
            "type": "fleet_message",
            "channel_id": str(channel_id),
            "channel_name": channel_name,
            "guild_name": guild_name,
            "author": author,
            "timestamp": timestamp,
            "discord_msg_id": msg_id,
        }

        chunks_txt = self._chunk_text(thought_text) or [thought_text]
        vectors = self._embedder.embed(chunks_txt)
        chunk_pairs = list(zip(chunks_txt, vectors))

        thought_id = self._store.write_thought(
            content=thought_text,
            source="discord",
            scope="fleet",
            category="fleet_message",
            summary=f"{author}: {content[:100]}",
            tags=["fleet", "discord"],
            metadata=metadata,
            agent_id="discord_capture",
            memory_kind="work_log",
            chunks=chunk_pairs,
        )

        # Also record in discord_messages table
        now = time.time()
        try:
            self._store._conn.execute(
                """INSERT OR IGNORE INTO discord_messages
                   (id, channel_id, channel_name, guild_name, author, content, thought_id, captured_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (msg_id, str(channel_id), channel_name, guild_name, author, content, thought_id, now),
            )
            self._store._conn.commit()
        except Exception as exc:
            log.warning("discord_messages insert failed: %s", exc)

        return thought_id


def _get_writer():
    """Return the best available writer (Supabase or SQLite)."""
    _resolve_supabase_creds()
    if SUPABASE_URL and SUPABASE_SERVICE_KEY:
        try:
            return _SupabaseWriter()
        except Exception as exc:
            log.warning("Supabase writer failed: %s — using SQLite", exc)
    return _SQLiteWriter()


# ---------------------------------------------------------------------------
# Discord bot
# ---------------------------------------------------------------------------

async def run_discord_capture(token: str) -> None:
    """Run the Discord capture bot. Requires discord.py."""
    try:
        import discord  # type: ignore
    except ImportError:
        log.error(
            "discord.py not installed. Install with: pip install discord.py\n"
            "Capture disabled."
        )
        return

    writer = _get_writer()

    intents = discord.Intents.default()
    intents.message_content = True  # requires Message Content Intent in Dev Portal
    intents.guilds = True
    intents.messages = True

    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        log.info("Discord capture bot connected as %s", client.user)
        log.info("Monitoring channel: %s", FLEET_CHANNEL_ID)

    @client.event
    async def on_message(message: discord.Message):
        if message.channel.id != FLEET_CHANNEL_ID:
            return
        if IGNORE_BOTS and message.author.bot:
            return
        if not message.content.strip():
            return

        channel_name = getattr(message.channel, "name", str(message.channel.id))
        guild_name = message.guild.name if message.guild else "DM"
        author = str(message.author)
        timestamp = message.created_at.isoformat()

        try:
            thought_id = writer.write_discord_message(
                msg_id=str(message.id),
                channel_id=str(message.channel.id),
                channel_name=channel_name,
                guild_name=guild_name,
                author=author,
                content=message.content,
                timestamp=timestamp,
            )
            log.info(
                "Captured from %s#%s (%s): thought_id=%s snippet=%r",
                author, channel_name, guild_name, thought_id, message.content[:60],
            )
        except Exception as exc:
            log.error("Failed to capture message %s: %s", message.id, exc)

    @client.event
    async def on_message_edit(before: discord.Message, after: discord.Message):
        if not UPDATE_ON_EDIT:
            return
        if after.channel.id != FLEET_CHANNEL_ID:
            return
        if IGNORE_BOTS and after.author.bot:
            return
        if not after.content.strip():
            return

        channel_name = getattr(after.channel, "name", str(after.channel.id))
        guild_name = after.guild.name if after.guild else "DM"
        author = str(after.author)
        timestamp = after.edited_at.isoformat() if after.edited_at else after.created_at.isoformat()

        try:
            thought_id = writer.write_discord_message(
                msg_id=str(after.id),
                channel_id=str(after.channel.id),
                channel_name=channel_name,
                guild_name=guild_name,
                author=author,
                content=after.content + " [edited]",
                timestamp=timestamp,
            )
            log.info("Captured edit from %s: thought_id=%s", author, thought_id)
        except Exception as exc:
            log.error("Failed to capture edit %s: %s", after.id, exc)

    try:
        await client.start(token)
    except discord.LoginFailure:
        log.error("Discord login failed — check DISCORD_FLEET_BOT_TOKEN")
    except Exception as exc:
        log.error("Discord client error: %s", exc)
        raise


def main() -> None:
    """Standalone entry point for discord_capture.py."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(
                Path("C:/Users/micha/AppData/Local/hermes/carrier/logs/discord_capture.log"),
                encoding="utf-8",
            ),
            logging.StreamHandler(sys.stdout),
        ],
    )
    Path("C:/Users/micha/AppData/Local/hermes/carrier/logs").mkdir(parents=True, exist_ok=True)

    token = get_bot_token()
    if not token:
        log.error("No Discord token available — exiting")
        sys.exit(1)

    asyncio.run(run_discord_capture(token))


if __name__ == "__main__":
    main()
