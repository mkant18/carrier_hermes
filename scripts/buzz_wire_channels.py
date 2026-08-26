#!/usr/bin/env python3
"""
buzz_wire_channels.py — Fix channel membership + permissions on both Buzz communities.

Idempotent: reads current kind:39002 roster per channel, only sends kind:9000
for missing members. Also promotes key bots to admin role (kind:9000 with role=admin).

Targets both:
  ws://localhost:3000              (localhost community)
  ws://mks-pc.taileda46c.ts.net:3000  (Tailscale community)

Usage:
  python scripts/buzz_wire_channels.py [--dry-run] [--relay ws://...]
"""
from __future__ import annotations
import json, os, subprocess, sys, time
from pathlib import Path

KEYDIR = Path(r"C:\Users\micha\AppData\Local\hermes\carrier\buzz-keys")
NAK    = r"C:\Users\micha\AppData\Local\hermes\carrier\bin\nak.exe"
DRY    = "--dry-run" in sys.argv

# Allow targeting a single relay
RELAY_FILTER = None
for i, a in enumerate(sys.argv):
    if a == "--relay" and i + 1 < len(sys.argv):
        RELAY_FILTER = sys.argv[i + 1]

RELAYS = [
    "ws://localhost:3000",
    "ws://mks-pc.taileda46c.ts.net:3000",
] if not RELAY_FILTER else [RELAY_FILTER]

# ── Roster ────────────────────────────────────────────────────────────────────
def sk(bot): return (KEYDIR / f"{bot}.sk").read_text().strip()
def pub(bot):
    r = subprocess.run([NAK, "key", "public", sk(bot)], capture_output=True, text=True)
    return r.stdout.strip()

OWNER = "chief_of_staff"
MICHAEL_SK_FILE = KEYDIR / "michael.sk"

ROSTER = {
    "chief_of_staff":       ("command", "command"),
    "marshal":              ("command", "command"),
    "subscription_watcher": ("command", "command"),
    "api_watcher":          ("command", "command"),
    "lockbox":              ("command", "command"),
    "coding_lt":            ("lt",      "coding"),
    "ops_lt":               ("lt",      "ops"),
    "knowledge_lt":         ("lt",      "knowledge"),
    "hermes_ai_explorer":   ("lt",      "recon"),
    "firstmate":            ("worker",  "coding"),
    "git_yeoman":           ("worker",  "coding"),
    "passive_watch":        ("worker",  "recon"),
    "research_agent":       ("worker",  "recon"),
    "email_reader":         ("worker",  "ops"),
    "email_drafter":        ("worker",  "ops"),
    "calendar_manager":     ("worker",  "ops"),
    "todoist_manager":      ("worker",  "ops"),
    "finance_reader":       ("worker",  "ops"),
    "vault_librarian":      ("worker",  "knowledge"),
    "obsidian_archivist":   ("worker",  "knowledge"),
}

def tier(b): return ROSTER[b][0]
def wing(b): return ROSTER[b][1]
def _all(): return [b for b in ROSTER if b != OWNER]
def _by(pred): return [b for b in ROSTER if b != OWNER and pred(b)]

# Channel definitions — members are the NON-owner bots
# Admin role: Helm (owner always), Marshal (co-admin), LTs in their wing channels
CHANNELS = {
    "command":     {
        "members": _by(lambda b: tier(b) in ("command","lt")),
        "admins":  ["marshal"],  # Helm is implicit owner/admin
        "topic":   "Command net: Helm, Marshal, Vigil, Ledger, LockBox, Lts. Bridged to Telegram.",
        "add_michael": True,
    },
    "fleet":       {
        "members": _all(),
        "admins":  ["marshal"],
        "topic":   "All-hands — DISPATCH / ACK / TRAP.",
        "add_michael": True,
    },
    "alerts":      {
        "members": _by(lambda b: b in ("marshal","subscription_watcher","api_watcher","lockbox")),
        "admins":  ["marshal"],
        "topic":   "Vigil stalls, Ledger spend, LockBox security — redacted alerts only.",
        "add_michael": True,
    },
    "drafts":      {
        "members": _by(lambda b: b in ("ops_lt","email_drafter")),
        "admins":  ["ops_lt"],
        "topic":   "Quill drafts for Deck review. Never sent directly.",
        "add_michael": False,
    },
    "ready-room":  {
        "members": _by(lambda b: b in ("coding_lt","firstmate","git_yeoman")),
        "admins":  ["coding_lt"],
        "topic":   "Coding wing standup: Wrench + Mate + Yeoman.",
        "add_michael": False,
    },
    "catapult":    {
        "members": _by(lambda b: b in ("coding_lt","firstmate")),
        "admins":  ["coding_lt"],
        "topic":   "Wrench dispatches coding jobs to Mate.",
        "add_michael": False,
    },
    "quarterdeck": {
        "members": _by(lambda b: wing(b) == "ops"),
        "admins":  ["ops_lt"],
        "topic":   "Ops wing: Deck + Inbox, Quill, Chronos, Tasker, Purse.",
        "add_michael": False,
    },
    "chart-room":  {
        "members": _by(lambda b: wing(b) == "knowledge"),
        "admins":  ["knowledge_lt"],
        "topic":   "Knowledge wing: Stacks + Librarian, Clerk.",
        "add_michael": False,
    },
    "war-room":    {
        "members": _by(lambda b: wing(b) == "recon"),
        "admins":  ["hermes_ai_explorer"],
        "topic":   "Recon wing: Chart + Sonar, Probe.",
        "add_michael": False,
    },
    "email":       {
        "members": _by(lambda b: b in ("email_reader","email_drafter","ops_lt")),
        "admins":  ["ops_lt"],
        "topic":   "Email triage + drafts (read/draft only, NEVER send).",
        "add_michael": False,
    },
    "calendar":    {
        "members": _by(lambda b: b in ("calendar_manager","ops_lt")),
        "admins":  ["ops_lt"],
        "topic":   "Chronos calendar — Deck oversight.",
        "add_michael": False,
    },
    "tasks":       {
        "members": _by(lambda b: b in ("todoist_manager","ops_lt")),
        "admins":  ["ops_lt"],
        "topic":   "Tasker / Todoist — Deck oversight.",
        "add_michael": False,
    },
    "vault":       {
        "members": _by(lambda b: b in ("vault_librarian","obsidian_archivist","knowledge_lt")),
        "admins":  ["knowledge_lt"],
        "topic":   "Obsidian Second Brain: Stacks + Librarian query + Clerk intake.",
        "add_michael": False,
    },
    "finance":     {
        "members": _by(lambda b: b in ("finance_reader","ops_lt")),
        "admins":  ["ops_lt"],
        "topic":   "Purse — read-only Monarch, Deck oversight.",
        "add_michael": False,
    },
    "audit":       {
        "members": _by(lambda b: b in ("marshal","subscription_watcher","api_watcher","lockbox")),
        "admins":  ["marshal"],
        "topic":   "Dual-audit trail (Buzz Nostr + maka layer).",
        "add_michael": False,
    },
    "urgent":      {
        "members": _by(lambda b: b == "marshal"),
        "admins":  ["marshal"],
        "topic":   "Helm + Marshal — urgent escalations only.",
        "add_michael": True,
    },
    "general":     {
        "members": _all(),
        "admins":  ["marshal"],
        "topic":   "General / handoff home.",
        "add_michael": True,
    },
}

# ── Helpers ───────────────────────────────────────────────────────────────────
PUBS = {}
print("Loading public keys...")
for bot_id in list(ROSTER.keys()):
    PUBS[bot_id] = pub(bot_id)
    print(f"  {bot_id:25} {PUBS[bot_id][:16]}...")

MICHAEL_PUB = None
if MICHAEL_SK_FILE.exists():
    r = subprocess.run([NAK, "key", "public", MICHAEL_SK_FILE.read_text().strip()],
                       capture_output=True, text=True)
    MICHAEL_PUB = r.stdout.strip()
    print(f"  {'michael':25} {MICHAEL_PUB[:16]}...")
OWNER_SK = sk(OWNER)

def nak_event(args: list, sec: str, relay: str) -> str:
    cmd = [NAK] + args + ["--sec", sec, "--auth", relay]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return (r.stdout + r.stderr).strip()

def nak_req(args: list, sec: str, relay: str) -> list[dict]:
    cmd = [NAK, "req"] + args + ["--sec", sec, "--auth", relay]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    events = []
    for line in r.stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try: events.append(json.loads(line))
            except: pass
    return events

def resolve_channels(relay: str) -> dict[str, str]:
    """Returns {channel_name: uuid}"""
    evs = nak_req(["-k", "39000", "--limit", "100"], OWNER_SK, relay)
    result = {}
    for ev in evs:
        tags = {t[0]: t[1] for t in ev.get("tags", []) if len(t) >= 2}
        name = tags.get("name", "")
        d    = tags.get("d", "")
        if name and d:
            result[name] = d
    return result

def get_current_members(uuid: str, relay: str) -> set[str]:
    """Returns set of pubkeys currently in the channel roster (from kind:39002)."""
    evs = nak_req(["-k", "39002", "--tag", f"d={uuid}", "--limit", "1"], OWNER_SK, relay)
    members = set()
    for ev in evs:
        for t in ev.get("tags", []):
            if t[0] == "p" and len(t) >= 2:
                members.add(t[1])
    return members

def get_current_admins(uuid: str, relay: str) -> set[str]:
    """Returns set of pubkeys with admin role from kind:39002."""
    evs = nak_req(["-k", "39002", "--tag", f"d={uuid}", "--limit", "1"], OWNER_SK, relay)
    admins = set()
    for ev in evs:
        for t in ev.get("tags", []):
            # NIP-29: ["p", pubkey, relay, role] where role = "admin"
            if t[0] == "p" and len(t) >= 4 and t[3] == "admin":
                admins.add(t[1])
    return admins

# ── Main loop ─────────────────────────────────────────────────────────────────
total_adds = 0
total_admin_sets = 0

for relay in RELAYS:
    print(f"\n{'='*60}")
    print(f"RELAY: {relay}")
    print(f"{'='*60}")

    # Resolve channel UUIDs
    channel_uuids = resolve_channels(relay)
    print(f"Found {len(channel_uuids)} channels: {sorted(channel_uuids.keys())}")

    missing_channels = [c for c in CHANNELS if c not in channel_uuids]
    if missing_channels:
        print(f"⚠  Missing channels (need creation): {missing_channels}")
        # Create missing channels
        for ch_name in missing_channels:
            if DRY:
                print(f"  [DRY] create #{ch_name}")
                continue
            out = nak_event(["event", "-k", "9007",
                             "--tag", f"name={ch_name}",
                             "--tag", "visibility=open",
                             "-c", ""], OWNER_SK, relay)
            print(f"  created #{ch_name}")
            time.sleep(0.4)
        # Re-resolve after creation
        time.sleep(1)
        channel_uuids = resolve_channels(relay)

    # Wire each channel
    for ch_name, ch_cfg in CHANNELS.items():
        uuid = channel_uuids.get(ch_name)
        if not uuid:
            print(f"  SKIP #{ch_name} — still no UUID")
            continue

        # Build full expected member list
        expected_members = list(ch_cfg["members"])
        if ch_cfg.get("add_michael") and MICHAEL_PUB:
            expected_members_pubs = {PUBS[b] for b in expected_members} | {MICHAEL_PUB}
        else:
            expected_members_pubs = {PUBS[b] for b in expected_members}

        current = get_current_members(uuid, relay)
        missing = expected_members_pubs - current
        current_admins = get_current_admins(uuid, relay)

        # Expected admin pubkeys
        expected_admin_pubs = {PUBS[b] for b in ch_cfg.get("admins", [])}

        adds = 0
        admin_sets = 0

        # Add missing members
        for mpub in missing:
            if DRY:
                print(f"  [DRY] #{ch_name} add member {mpub[:12]}...")
                adds += 1
                continue
            nak_event(["event", "-k", "9000",
                       "--tag", f"h={uuid}",
                       "--tag", f"p={mpub}",
                       "-c", ""], OWNER_SK, relay)
            adds += 1
            time.sleep(0.04)

        # Set admin roles for missing admins
        for apub in expected_admin_pubs - current_admins:
            if DRY:
                print(f"  [DRY] #{ch_name} set admin {apub[:12]}...")
                admin_sets += 1
                continue
            # NIP-29 kind:9000 with role=admin tag
            nak_event(["event", "-k", "9000",
                       "--tag", f"h={uuid}",
                       "--tag", f"p={apub}",
                       "--tag", "role=admin",
                       "-c", ""], OWNER_SK, relay)
            admin_sets += 1
            time.sleep(0.04)

        total_adds   += adds
        total_admin_sets += admin_sets

        status = "✓" if (adds == 0 and admin_sets == 0) else "+"
        print(f"  {status} #{ch_name:15} {len(current)}/{len(expected_members_pubs)} members"
              f"  +{adds} added  +{admin_sets} admin roles set")

    # Set channel topics (kind:9002) for correctness
    print(f"\n  Setting topics...")
    for ch_name, ch_cfg in CHANNELS.items():
        uuid = channel_uuids.get(ch_name)
        if not uuid or "topic" not in ch_cfg:
            continue
        if DRY:
            continue
        nak_event(["event", "-k", "9002",
                   "--tag", f"h={uuid}",
                   "--tag", f"topic={ch_cfg['topic']}",
                   "-c", ""], OWNER_SK, relay)
        time.sleep(0.05)
    print(f"  Topics set.")

print(f"\n{'='*60}")
print(f"DONE {'(dry run)' if DRY else ''}")
print(f"  Total member adds:   {total_adds}")
print(f"  Total admin grants:  {total_admin_sets}")
print(f"\nPermission model:")
print(f"  Owner (implicit):  Helm ⚓ — all channels")
print(f"  Co-admin:          Marshal 🎖 — command, fleet, alerts, audit, urgent, general")
print(f"  Wing admin in own channels:")
print(f"    Wrench 🔧  → ready-room, catapult")
print(f"    Deck 🗂   → drafts, quarterdeck, email, calendar, tasks, finance")
print(f"    Stacks 📚 → chart-room, vault")
print(f"    Chart 🗺  → war-room")
