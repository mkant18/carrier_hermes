"""Discord → Fleet Brain capture bridge.

Mirrors the OB1 discord-capture integration but writes to local SQLite
instead of a Supabase edge function. Compatible with the carrier_hermes
First Watch bot setup.

Usage (standalone):
  python discord_capture.py --channels 123456789,987654321

Usage (from discord bot code — call ingest_message() directly):
  from discord_capture import FleetBrainCapture
  capture = FleetBrainCapture()
  capture.ingest_message(message_id, channel_id, channel_name, guild_name, author, content)

Environment variables:
  OB1_BRAIN_DB          — path to fleet brain SQLite (shares with server.py)
  OB1_MODEL             — embedding model
  DISCORD_BOT_TOKEN     — required for standalone runner
  OB1_DISCORD_CHANNELS  — comma-separated channel IDs to monitor (standalone)
  OB1_DISCORD_GUILD     — guild (server) name for metadata

Notes:
  - Does NOT require Supabase, OpenRouter, or cloud services
  - Uses same embedder as server.py (sentence-transformers or hash fallback)
  - Message→thought mapping stored in discord_messages table
  - Minimal messages (<10 words) are stored but not embedded (noise reduction)
  - Bot messages are captured by default; set OB1_DISCORD_IGNORE_BOTS=1 to skip
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

from embedder import DEFAULT_MODEL, Embedder, chunk_text
from store import DEFAULT_DB_PATH, FleetBrainStore

logger = logging.getLogger(__name__)

# Messages shorter than this won't be embedded (still stored for audit)
MIN_EMBED_LENGTH = 40
# Category assigned to Discord captures
DISCORD_CATEGORY = "discord"


class FleetBrainCapture:
    """Thin wrapper that funnels Discord messages into the fleet brain."""

    def __init__(
        self,
        db_path: Path | None = None,
        model: str | None = None,
        guild_name: str = "",
    ):
        self.store = FleetBrainStore(db_path or Path(os.environ.get("OB1_BRAIN_DB", str(DEFAULT_DB_PATH))))
        self.embedder = Embedder(model or os.environ.get("OB1_MODEL", DEFAULT_MODEL))
        self.guild_name = guild_name or os.environ.get("OB1_DISCORD_GUILD", "carrier")

    def ingest_message(
        self,
        message_id: str,
        channel_id: str,
        channel_name: str,
        author: str,
        content: str,
        guild_name: str = "",
    ) -> str | None:
        """Ingest one Discord message into the fleet brain.

        Returns thought_id if a new thought was created, else None.
        """
        guild = guild_name or self.guild_name
        clean = _clean_content(content)
        if not clean:
            logger.debug("skip empty message %s", message_id)
            return None

        thought_id: str | None = None
        if len(clean) >= MIN_EMBED_LENGTH:
            chunks_txt = chunk_text(clean)
            if not chunks_txt:
                chunks_txt = [clean]
            vectors = self.embedder.embed(chunks_txt)
            chunk_pairs = list(zip(chunks_txt, vectors))

            summary = clean[:120] + ("..." if len(clean) > 120 else "")
            thought_id = self.store.write_thought(
                content=clean,
                source="discord",
                scope="fleet",
                category=DISCORD_CATEGORY,
                summary=summary,
                tags=["discord", channel_name.lstrip("#")],
                metadata={
                    "discord_message_id": message_id,
                    "channel_id": channel_id,
                    "channel_name": channel_name,
                    "guild_name": guild,
                    "author": author,
                },
                agent_id="discord_capture",
                memory_kind="work_log",
                chunks=chunk_pairs,
            )
            logger.info("captured message %s → thought %s", message_id, thought_id)

        self.store.upsert_discord_message(
            message_id=message_id,
            channel_id=channel_id,
            channel_name=channel_name,
            guild_name=guild,
            author=author,
            content=clean,
            thought_id=thought_id,
        )
        return thought_id

    def close(self):
        self.store.close()


def _clean_content(text: str) -> str:
    """Strip Discord formatting noise."""
    if not text:
        return ""
    # Remove embeds markers, excessive whitespace
    text = re.sub(r"<@!?\d+>", "", text)        # @mentions
    text = re.sub(r"<#\d+>", "", text)           # #channels
    text = re.sub(r"<a?:\w+:\d+>", "", text)     # custom emoji
    text = re.sub(r"https?://\S+", "[link]", text)  # URLs → token
    text = re.sub(r"\s{3,}", "\n", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Standalone runner — requires discord.py
# ---------------------------------------------------------------------------

def _run_standalone() -> None:
    """Run as a standalone Discord bot that captures messages."""
    try:
        import discord  # type: ignore
    except ImportError:
        print("ERROR: discord.py not installed. Run: uv pip install discord.py")
        raise SystemExit(1)

    token = os.environ.get("DISCORD_BOT_TOKEN", "")
    if not token:
        print("ERROR: DISCORD_BOT_TOKEN not set")
        raise SystemExit(1)

    raw_channels = os.environ.get("OB1_DISCORD_CHANNELS", "")
    channel_ids: set[int] = set()
    if raw_channels:
        for part in raw_channels.split(","):
            part = part.strip()
            if part.isdigit():
                channel_ids.add(int(part))

    ignore_bots = os.environ.get("OB1_DISCORD_IGNORE_BOTS", "0") == "1"

    capture = FleetBrainCapture()
    intents = discord.Intents.default()
    intents.message_content = True  # Requires privileged intent in Discord Dev Portal

    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        print(f"OB1 Discord capture online: {client.user} | monitoring {len(channel_ids) or 'ALL'} channels")

    @client.event
    async def on_message(message: discord.Message):
        if ignore_bots and message.author.bot:
            return
        if channel_ids and message.channel.id not in channel_ids:
            return
        capture.ingest_message(
            message_id=str(message.id),
            channel_id=str(message.channel.id),
            channel_name=getattr(message.channel, "name", str(message.channel.id)),
            author=str(message.author),
            content=message.content or "",
            guild_name=message.guild.name if message.guild else "",
        )

    client.run(token)


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="OB1 Discord capture bridge")
    parser.add_argument("--channels", default=os.environ.get("OB1_DISCORD_CHANNELS", ""),
                        help="Comma-separated Discord channel IDs to monitor")
    args = parser.parse_args()
    if args.channels:
        os.environ["OB1_DISCORD_CHANNELS"] = args.channels
    _run_standalone()
