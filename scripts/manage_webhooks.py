#!/usr/bin/env python3
"""
manage_webhooks.py — CLI for managing carrier webhook triggers.

Commands:
  create   Create a new webhook trigger and print the bearer secret.
  list     List all registered webhook triggers.
  show     Show details + recent attempts for one trigger.
  update   Update name / bot / prompt / event_types / enabled flag.
  rotate   Rotate the bearer secret for a trigger.
  delete   Delete a trigger permanently.
  test     Send a test POST to the receiver (requires server running).

Usage examples:
  python manage_webhooks.py create --name "GitHub push" --bot coding_lt --events push,pull_request
  python manage_webhooks.py list
  python manage_webhooks.py show <trigger_id>
  python manage_webhooks.py rotate <trigger_id>
  python manage_webhooks.py update <trigger_id> --enabled false
  python manage_webhooks.py delete <trigger_id>
  python manage_webhooks.py test <trigger_id> --event-type push
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import webhook_db as wdb

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

WEBHOOK_BASE_URL = "http://{}:{}".format(
    os.environ.get("CARRIER_WEBHOOK_HOST", "127.0.0.1"),
    os.environ.get("CARRIER_WEBHOOK_PORT", "8800"),
)


def _ts(epoch: int | None) -> str:
    if epoch is None:
        return "—"
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _open_conn() -> "wdb.sqlite3.Connection":  # type: ignore[name-defined]
    return wdb.open_db()


def _resolve_trigger(conn, id_or_endpoint: str) -> "wdb.WebhookTrigger":
    # Try by id first, then by endpoint_id
    trigger = wdb.get_trigger_by_id(conn, id_or_endpoint)
    if trigger is None:
        trigger = wdb.get_trigger_by_endpoint(conn, id_or_endpoint)
    if trigger is None:
        print(f"ERROR: No trigger found for '{id_or_endpoint}'", file=sys.stderr)
        sys.exit(1)
    return trigger


# ---------------------------------------------------------------------------
# Command: create
# ---------------------------------------------------------------------------

def cmd_create(args: argparse.Namespace) -> None:
    conn = _open_conn()
    event_types = [e.strip() for e in args.events.split(",")] if args.events else []

    trigger, raw_secret = wdb.create_trigger(
        conn,
        name=args.name,
        bot_id=args.bot,
        prompt=args.prompt or "",
        event_types=event_types,
        endpoint_id=args.endpoint_id or None,
    )

    print()
    print("=" * 60)
    print("Webhook trigger created successfully.")
    print("=" * 60)
    print(f"  ID          : {trigger.id}")
    print(f"  Endpoint ID : {trigger.endpoint_id}")
    print(f"  Name        : {trigger.name}")
    print(f"  Bot         : {trigger.bot_id}")
    print(f"  Event types : {trigger.event_types or '(any)'}")
    print(f"  Enabled     : {trigger.enabled}")
    print(f"  Verified    : NO (first auth request will verify)")
    print()
    print("BEARER SECRET (shown once — save it now):")
    print()
    print(f"  {raw_secret}")
    print()
    print("Webhook URL:")
    print(f"  POST {WEBHOOK_BASE_URL}/hooks/{trigger.endpoint_id}")
    print()
    print("Authorization header:")
    print(f"  Authorization: Bearer {raw_secret}")
    print()
    print("Capability URL (lower security, secret in path):")
    print(f"  POST {WEBHOOK_BASE_URL}/hooks/{trigger.endpoint_id}/{raw_secret}")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Command: list
# ---------------------------------------------------------------------------

def cmd_list(args: argparse.Namespace) -> None:
    conn = _open_conn()
    triggers = wdb.list_triggers(conn)

    if not triggers:
        print("No webhook triggers registered.")
        return

    fmt = "{:<12} {:<20} {:<16} {:<14} {:<6} {:<8} {}"
    print(fmt.format("ID (short)", "Name", "Endpoint ID", "Bot", "Enabled", "Verified", "Deliveries"))
    print("-" * 90)
    for t in triggers:
        verified = "YES" if not t.verification_pending else "pending"
        enabled = "YES" if t.enabled else "NO"
        short_id = t.id[:8] + "…"
        short_ep = t.endpoint_id[:14]
        print(fmt.format(short_id, t.name[:20], short_ep, t.bot_id[:14], enabled, verified, t.delivery_count))


# ---------------------------------------------------------------------------
# Command: show
# ---------------------------------------------------------------------------

def cmd_show(args: argparse.Namespace) -> None:
    conn = _open_conn()
    trigger = _resolve_trigger(conn, args.id)

    print()
    print(f"Trigger: {trigger.name}")
    print("=" * 60)
    print(f"  ID              : {trigger.id}")
    print(f"  Endpoint ID     : {trigger.endpoint_id}")
    print(f"  Bot (assignee)  : {trigger.bot_id}")
    print(f"  Enabled         : {trigger.enabled}")
    print(f"  Verified        : {'YES' if not trigger.verification_pending else 'NO (pending)'}")
    print(f"  Created         : {_ts(trigger.created_at)}")
    print(f"  Updated         : {_ts(trigger.updated_at)}")
    print(f"  Last received   : {_ts(trigger.last_received_at)}")
    print(f"  Verified at     : {_ts(trigger.verified_at)}")
    print(f"  Deliveries      : {trigger.delivery_count}")
    print(f"  Event types     : {trigger.event_types or '(any)'}")
    print(f"  Prompt          : {trigger.prompt[:100] if trigger.prompt else '(parse payload)'}")
    print()
    print(f"  Webhook URL     : POST {WEBHOOK_BASE_URL}/hooks/{trigger.endpoint_id}")
    print()

    attempts = wdb.list_attempts(conn, trigger.id, limit=10)
    if attempts:
        print("Recent attempts (latest first):")
        print(f"  {'Time':<22} {'Outcome':<12} {'Status':<6} {'Event':<20} {'Task ID'}")
        print("  " + "-" * 80)
        for a in attempts:
            ts = _ts(a.received_at)
            task = a.task_id or "—"
            print(f"  {ts:<22} {a.outcome:<12} {a.status_code:<6} {(a.event_name or '—'):<20} {task}")
            if a.reason:
                print(f"    reason: {a.reason}")
    else:
        print("No attempts logged yet.")


# ---------------------------------------------------------------------------
# Command: update
# ---------------------------------------------------------------------------

def cmd_update(args: argparse.Namespace) -> None:
    conn = _open_conn()
    trigger = _resolve_trigger(conn, args.id)

    updates = {}
    if args.name is not None:
        updates["name"] = args.name
    if args.bot is not None:
        updates["bot_id"] = args.bot
    if args.prompt is not None:
        updates["prompt"] = args.prompt
    if args.events is not None:
        updates["event_types"] = [e.strip() for e in args.events.split(",")]
    if args.enabled is not None:
        val = args.enabled.lower()
        if val not in ("true", "false", "1", "0", "yes", "no"):
            print("ERROR: --enabled must be true/false", file=sys.stderr)
            sys.exit(1)
        updates["enabled"] = val in ("true", "1", "yes")

    if not updates:
        print("Nothing to update. Pass at least one of: --name, --bot, --prompt, --events, --enabled")
        return

    wdb.update_trigger(conn, trigger.id, **updates)
    print(f"Trigger {trigger.id[:8]}… updated: {list(updates.keys())}")


# ---------------------------------------------------------------------------
# Command: rotate
# ---------------------------------------------------------------------------

def cmd_rotate(args: argparse.Namespace) -> None:
    conn = _open_conn()
    trigger = _resolve_trigger(conn, args.id)

    new_secret, _ = wdb.rotate_secret(conn, trigger.id)
    print()
    print(f"Secret rotated for trigger '{trigger.name}' ({trigger.id[:8]}…)")
    print()
    print("NEW BEARER SECRET (shown once — save it now):")
    print()
    print(f"  {new_secret}")
    print()
    print(f"New Authorization header: Bearer {new_secret}")
    print()


# ---------------------------------------------------------------------------
# Command: delete
# ---------------------------------------------------------------------------

def cmd_delete(args: argparse.Namespace) -> None:
    conn = _open_conn()
    trigger = _resolve_trigger(conn, args.id)

    if not args.yes:
        confirm = input(
            f"Delete trigger '{trigger.name}' ({trigger.id[:8]}…)? "
            f"This cannot be undone. [y/N] "
        ).strip().lower()
        if confirm not in ("y", "yes"):
            print("Aborted.")
            return

    ok = wdb.delete_trigger(conn, trigger.id)
    if ok:
        print(f"Deleted trigger {trigger.id[:8]}… ({trigger.name})")
    else:
        print(f"ERROR: trigger {args.id} not found (already deleted?)", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Command: test
# ---------------------------------------------------------------------------

def cmd_test(args: argparse.Namespace) -> None:
    conn = _open_conn()
    trigger = _resolve_trigger(conn, args.id)

    # We need the secret to send an authenticated request.
    # Since we never store the raw secret, the user must provide it.
    if not args.secret:
        print("ERROR: --secret is required for test (we never store the raw secret).", file=sys.stderr)
        print("  Rotate the trigger if you've lost the secret: manage_webhooks.py rotate <id>", file=sys.stderr)
        sys.exit(1)

    payload = {
        "test": True,
        "trigger_id": trigger.id,
        "sent_at": int(time.time()),
        "message": args.message or "Manual test from manage_webhooks.py",
    }
    body = json.dumps(payload).encode()
    delivery_id = f"test-{int(time.time())}"
    event_type = args.event_type or "test"

    url = f"{WEBHOOK_BASE_URL}/hooks/{trigger.endpoint_id}"
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {args.secret}",
            "Content-Type": "application/json",
            "X-Delivery-ID": delivery_id,
            "X-Event-Type": event_type,
        },
        method="POST",
    )

    print(f"Sending test webhook to {url}")
    print(f"  Event-Type : {event_type}")
    print(f"  Delivery-ID: {delivery_id}")
    print()

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            response_body = json.loads(resp.read().decode())
            print(f"Response {resp.status}: {json.dumps(response_body, indent=2)}")
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        try:
            error_body = json.dumps(json.loads(error_body), indent=2)
        except Exception:
            pass
        print(f"Response {e.code}: {error_body}")
    except urllib.error.URLError as e:
        print(f"ERROR: Could not connect to webhook receiver at {WEBHOOK_BASE_URL}")
        print(f"  Is it running? Start with: python webhook_receiver.py")
        print(f"  Reason: {e.reason}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage carrier_hermes webhook triggers.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # create
    p_create = sub.add_parser("create", help="Create a new webhook trigger")
    p_create.add_argument("--name", required=True, help="Human label for this trigger")
    p_create.add_argument("--bot", required=True, help="Kanban assignee bot ID (e.g. coding_lt)")
    p_create.add_argument("--prompt", default="", help="Static task body (empty = parse payload)")
    p_create.add_argument("--events", default="", help="Comma-separated event type allowlist (empty = any)")
    p_create.add_argument("--endpoint-id", default=None, help="Custom endpoint path fragment (generated if omitted)")

    # list
    sub.add_parser("list", help="List all registered triggers")

    # show
    p_show = sub.add_parser("show", help="Show details and recent attempts for a trigger")
    p_show.add_argument("id", help="Trigger ID or endpoint_id")

    # update
    p_update = sub.add_parser("update", help="Update trigger fields")
    p_update.add_argument("id", help="Trigger ID or endpoint_id")
    p_update.add_argument("--name", default=None)
    p_update.add_argument("--bot", default=None)
    p_update.add_argument("--prompt", default=None)
    p_update.add_argument("--events", default=None, help="Comma-separated event allowlist")
    p_update.add_argument("--enabled", default=None, help="true or false")

    # rotate
    p_rotate = sub.add_parser("rotate", help="Rotate the bearer secret for a trigger")
    p_rotate.add_argument("id", help="Trigger ID or endpoint_id")

    # delete
    p_delete = sub.add_parser("delete", help="Delete a trigger permanently")
    p_delete.add_argument("id", help="Trigger ID or endpoint_id")
    p_delete.add_argument("--yes", action="store_true", help="Skip confirmation prompt")

    # test
    p_test = sub.add_parser("test", help="Send a test POST to the receiver (server must be running)")
    p_test.add_argument("id", help="Trigger ID or endpoint_id")
    p_test.add_argument("--secret", required=False, help="Raw bearer secret (required for auth)")
    p_test.add_argument("--event-type", default="test", help="X-Event-Type header value")
    p_test.add_argument("--message", default=None, help="Custom message in test payload")

    return parser


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

COMMANDS = {
    "create": cmd_create,
    "list": cmd_list,
    "show": cmd_show,
    "update": cmd_update,
    "rotate": cmd_rotate,
    "delete": cmd_delete,
    "test": cmd_test,
}


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    COMMANDS[args.command](args)


if __name__ == "__main__":
    main()
