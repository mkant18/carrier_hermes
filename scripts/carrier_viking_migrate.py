#!/usr/bin/env python3
"""
carrier_viking_migrate.py -- Migrate carrier-viking SQLite memories to full OpenViking server.

Usage:
    python scripts/carrier_viking_migrate.py \
        --db C:/Users/micha/AppData/Local/hermes/carrier/viking_memory.db \
        --server http://127.0.0.1:1933 \
        [--api-key YOUR_KEY] \
        [--dry-run]

Requires:
    pip install httpx  (or use requests)
    Full OpenViking server running at --server

This script reads all memories from the Option-B SQLite store and
POSTs them to the OpenViking server's /api/v1/memories endpoint,
preserving bot_id, type, content, tags, created_at, and importance.

After migration, verify with:
    ov memory list --bot-id <bot_id>
and then switch to the carrier-viking-ov plugin.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path
from urllib import request, error


def migrate(db_path: str, server_url: str, api_key: str | None, dry_run: bool) -> None:
    db = Path(db_path)
    if not db.exists():
        print(f"ERROR: DB not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, bot_id, type, content, tags, created_at, importance FROM memories ORDER BY created_at ASC"
    ).fetchall()
    conn.close()

    print(f"Found {len(rows)} memories in {db_path}")

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    ok = 0
    fail = 0
    for row in rows:
        tags = []
        try:
            tags = json.loads(row["tags"] or "[]")
        except (json.JSONDecodeError, TypeError):
            pass

        payload = {
            "content": row["content"],
            "type": row["type"],
            "bot_id": row["bot_id"],
            "tags": tags,
            "importance": row["importance"],
            "created_at": row["created_at"],
            "source": "carrier-viking-migration",
        }

        endpoint = f"{server_url.rstrip('/')}/api/v1/memories"
        if dry_run:
            print(f"[dry-run] Would POST to {endpoint}: {row['id']} [{row['type']}] {row['content'][:60]}")
            ok += 1
            continue

        try:
            req = request.Request(
                endpoint,
                data=json.dumps(payload).encode(),
                headers=headers,
                method="POST",
            )
            with request.urlopen(req, timeout=10) as resp:
                resp_body = resp.read()
                print(f"  ✓ {row['id']} [{row['type']}] {row['content'][:50]}")
                ok += 1
        except error.HTTPError as e:
            print(f"  ✗ {row['id']} HTTP {e.code}: {e.read()[:100]}")
            fail += 1
        except Exception as e:
            print(f"  ✗ {row['id']} ERROR: {e}")
            fail += 1

        time.sleep(0.05)  # gentle rate limiting

    print(f"\nMigration complete: {ok} succeeded, {fail} failed")
    if fail > 0:
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate carrier-viking SQLite to OpenViking server")
    parser.add_argument("--db", default="C:/Users/micha/AppData/Local/hermes/carrier/viking_memory.db")
    parser.add_argument("--server", default="http://127.0.0.1:1933")
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    migrate(args.db, args.server, args.api_key, args.dry_run)


if __name__ == "__main__":
    main()
