#!/usr/bin/env python3
"""
bootstrap_peer_webhooks.py — One-time setup: register the 3 peer webhook triggers
that the peers broker needs to dispatch kanban tasks.

Run AFTER install_webhook_services.ps1 has started both services (the broker
will have generated the local secret at startup).

Creates:
  endpoint_id=peer-registered  bot=ops_lt          event_types=["peer_registered"]
  endpoint_id=peer-task        bot=ops_lt (default) event_types=["peer_task"]
  endpoint_id=peer-left        bot=passive_watch    event_types=["peer_left"]

The bearer secret used by the peers broker is read from:
  C:/Users/micha/AppData/Local/hermes/carrier/webhook_local_secret
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import webhook_db as wdb

LOCAL_SECRET_PATH = Path(
    r"C:\Users\micha\AppData\Local\hermes\carrier\webhook_local_secret"
)

PEER_TRIGGERS = [
    {
        "endpoint_id": "peer-registered",
        "name": "Peer fleet registered",
        "bot_id": "ops_lt",
        "event_types": ["peer_registered"],
        "prompt": "",
    },
    {
        "endpoint_id": "peer-task",
        "name": "Peer fleet task message",
        "bot_id": "ops_lt",  # runtime: peers broker sends to_bot in payload
        "event_types": ["peer_task"],
        "prompt": "",
    },
    {
        "endpoint_id": "peer-left",
        "name": "Peer fleet left network",
        "bot_id": "passive_watch",
        "event_types": ["peer_left"],
        "prompt": "",
    },
]


def main() -> None:
    # Read local secret
    if not LOCAL_SECRET_PATH.exists():
        print(f"ERROR: Local secret not found at {LOCAL_SECRET_PATH}")
        print("Has the peers broker started yet? Check: sc.exe query carrier-peers-broker")
        sys.exit(1)

    local_secret = LOCAL_SECRET_PATH.read_text(encoding="utf-8").strip()
    print(f"Local secret loaded ({len(local_secret)} chars)")

    conn = wdb.open_db()

    for spec in PEER_TRIGGERS:
        # Skip if already registered
        existing = wdb.get_trigger_by_endpoint(conn, spec["endpoint_id"])
        if existing is not None:
            print(f"  SKIP (already exists): endpoint_id={spec['endpoint_id']} id={existing.id[:8]}...")
            continue

        trigger, _ = wdb.create_trigger(
            conn,
            name=spec["name"],
            bot_id=spec["bot_id"],
            prompt=spec["prompt"],
            event_types=spec["event_types"],
            endpoint_id=spec["endpoint_id"],
            secret=local_secret,  # use the shared local secret for all 3
        )
        print(f"  CREATED: {trigger.name}")
        print(f"    endpoint_id : {trigger.endpoint_id}")
        print(f"    id          : {trigger.id}")
        print(f"    bot         : {trigger.bot_id}")
        print(f"    event_types : {trigger.event_types}")
        print()

    print("Bootstrap complete.")
    print()
    print("Verify with:")
    print("  python manage_webhooks.py list")
    print("  curl http://127.0.0.1:8800/health")


if __name__ == "__main__":
    main()
