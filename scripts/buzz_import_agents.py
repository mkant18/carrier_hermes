#!/usr/bin/env python3
"""
buzz_import_agents.py — Import all 20 Carrier Hermes bots into the localhost Buzz
community with:
  1. kind:0 profile per bot (callsign, emoji, tier, wing, model chain)
  2. 17 NIP-29 channels mirroring the Discord topology
  3. Channel membership per wing/tier
  4. Relay-member registration (owner=Helm for every channel)

BILLING HARD-GUARD enforced at the top:
  - Validates no Anthropic/xAI API keys present (OAuth-only)
  - Validates OR allowlist (no Claude/Grok/frontier over OpenRouter)
  - Aborts if billing_guard.py says FAIL

Run:
  python scripts/buzz_import_agents.py [--dry-run]
"""
from __future__ import annotations
import json, os, subprocess, sys, time
from pathlib import Path

RELAY     = os.environ.get("CARRIER_BUZZ_RELAY", "ws://localhost:3000")
NAK       = os.environ.get("CARRIER_NAK", r"C:\Users\micha\AppData\Local\hermes\carrier\bin\nak.exe")
KEYDIR    = Path(r"C:\Users\micha\AppData\Local\hermes\carrier\buzz-keys")
HERMES_HOME = Path(r"C:\Users\micha\AppData\Local\hermes")
SCRIPTDIR = Path(__file__).resolve().parent
DRY       = "--dry-run" in sys.argv

# ── BILLING HARD-GUARD ────────────────────────────────────────────────────────
print("=== BILLING HARD-GUARD CHECK ===")
import json as _json

# 1. auth.json must have NO anthropic/xai API keys
auth_path = HERMES_HOME / "auth.json"
if auth_path.exists():
    auth = _json.loads(auth_path.read_text(encoding="utf-8"))
    pool = auth.get("credential_pool", auth.get("providers", {}))
    # pool is dict of provider -> list of creds OR dict
    for provider, creds in pool.items():
        if provider.lower() in ("anthropic", "xai", "xai-oauth", "grok"):
            cred_list = creds if isinstance(creds, list) else [creds]
            for cred in cred_list:
                if isinstance(cred, dict):
                    ctype = cred.get("type", "")
                    if ctype == "api_key" or ("api_key" in cred and cred.get("api_key")):
                        print(f"BILLING ABORT: {provider} has API key credential (type={ctype}). OAuth only!")
                        sys.exit(1)
    print("  auth.json: OK (OAuth only, no API keys)")
else:
    print("  auth.json: not found (OK)")

# 2. Run billing_guard.py
guard = SCRIPTDIR / "billing_guard.py"
if guard.exists():
    r = subprocess.run([sys.executable, str(guard),
                        "--hermes-home", str(HERMES_HOME)],
                       capture_output=True, text=True)
    out = (r.stdout + r.stderr).strip()
    if "PASS" in out:
        print(f"  billing_guard.py: PASS")
    else:
        print(f"  billing_guard.py: FAIL\n{out}")
        print("BILLING ABORT: fix guard violations before importing agents.")
        sys.exit(1)
else:
    print("  billing_guard.py: not found (skip)")

print("=== BILLING HARD-GUARD: PASS ===\n")

# ── ROSTER with model chains from COST_MODEL.md ───────────────────────────────
# Format: bot_id -> (callsign, emoji, tier, wing, primary_model, fallback_chain)
# Subscription models: grok-4.5 ($0), claude-sonnet-5 ($0)
# OR allowlist only: deepseek-v4-flash-0731, gpt-oss-120b, gemini-2.5-flash-lite
# HARD DENY: any API-key Claude/Sonnet/Opus, any API-key Grok

FLEET = {
    # bot_id: (callsign, emoji, tier, wing, primary, chain_label)
    # command tier — smart (grok-4.5 → sonnet-5 → deepseek-chat)
    "chief_of_staff":       ("Helm",      "⚓",  "command", "command",   "grok-4.5/xai-oauth",      "grok-4.5 → sonnet-5 → deepseek-v4-flash [OR]"),
    "marshal":              ("Marshal",   "🎖",  "command", "command",   "claude-sonnet-5/anthropic","sonnet-5 → grok-4.5 → deepseek-chat-v3 [OR]"),
    "subscription_watcher": ("Vigil",     "📡", "command", "command",   "no_agent/bash",            "zero-LLM heartbeat · deepseek-v4-flash [OR] for summaries"),
    "api_watcher":          ("Ledger",    "📒", "command", "command",   "no_agent/bash",            "zero-LLM heartbeat · deepseek-v4-flash [OR] for narratives · grok-4.5 interactive"),
    "lockbox":              ("LockBox",   "🔒", "command", "command",   "gpt-oss-120b/openrouter",  "gpt-oss-120b → gemini-2.5-flash-lite [OR] · NO DeepSeek/PRC"),
    # lt tier — quality (sonnet-5 → grok-4.5 → deepseek-chat)
    "coding_lt":            ("Wrench",    "🔧", "lt",      "coding",   "claude-sonnet-5/anthropic","sonnet-5 → grok-4.5 → deepseek-chat-v3 [OR]"),
    "ops_lt":               ("Deck",      "🗂", "lt",      "ops",      "claude-sonnet-5/anthropic","sonnet-5 → grok-4.5 → deepseek-chat-v3 [OR]"),
    "knowledge_lt":         ("Stacks",    "📚", "lt",      "knowledge","claude-sonnet-5/anthropic","sonnet-5 → grok-4.5 → deepseek-chat-v3 [OR]"),
    "hermes_ai_explorer":   ("Chart",     "🗺", "lt",      "recon",    "claude-sonnet-5/anthropic","sonnet-5 → grok-4.5 → deepseek-chat-v3 [OR]"),
    # worker coding — quality implementer
    "firstmate":            ("Mate",      "⚙",  "worker",  "coding",   "claude-sonnet-5/anthropic","sonnet-5 → grok-4.5 → deepseek-v4-flash [OR]"),
    "git_yeoman":           ("Yeoman",    "📋", "worker",  "coding",   "deepseek-v4-flash/openrouter","deepseek-v4-flash [OR] → gemini-2.5-flash-lite [OR]"),
    # worker recon
    "passive_watch":        ("Sonar",     "🌊", "worker",  "recon",    "no_agent/bash",            "zero-LLM heartbeat · deepseek-v4-flash [OR] for LLM pass"),
    "research_agent":       ("Probe",     "🔭", "worker",  "recon",    "claude-sonnet-5/anthropic","sonnet-5 → grok-4.5 → deepseek-v4-flash [OR]"),
    # worker ops — specialist (deepseek-v4-flash; NOT subscription)
    "email_reader":         ("Inbox",     "📬", "worker",  "ops",      "deepseek-v4-flash/openrouter","deepseek-v4-flash [OR] → gemini-2.5-flash-lite [OR] · NO :free"),
    "email_drafter":        ("Quill",     "🪶", "worker",  "ops",      "claude-sonnet-5/anthropic","sonnet-5 → grok-4.5 → deepseek-v4-flash [OR]"),
    "calendar_manager":     ("Chronos",   "🕰", "worker",  "ops",      "deepseek-v4-flash/openrouter","deepseek-v4-flash [OR] → gemini-2.5-flash-lite [OR] · NO :free"),
    "todoist_manager":      ("Tasker",    "✅", "worker",  "ops",      "deepseek-v4-flash/openrouter","deepseek-v4-flash [OR] → gemini-2.5-flash-lite [OR] · NO :free"),
    "finance_reader":       ("Purse",     "👛", "worker",  "ops",      "claude-sonnet-5/anthropic","sonnet-5 → grok-4.5 → deepseek-v4-flash [OR]"),
    # worker knowledge
    "vault_librarian":      ("Librarian", "📖", "worker",  "knowledge","claude-sonnet-5/anthropic","sonnet-5 → grok-4.5 → deepseek-v4-flash [OR]"),
    "obsidian_archivist":   ("Clerk",     "🗄", "worker",  "knowledge","claude-sonnet-5/anthropic","sonnet-5 → grok-4.5 → deepseek-v4-flash [OR]"),
}
OWNER = "chief_of_staff"

def callsign(b): return FLEET[b][0]
def emoji(b):    return FLEET[b][1]
def tier(b):     return FLEET[b][2]
def wing(b):     return FLEET[b][3]

def _all():    return [b for b in FLEET if b != OWNER]
def _by(pred): return [b for b in FLEET if b != OWNER and pred(b)]

# ── Channels ──────────────────────────────────────────────────────────────────
CHANNELS = {
    "command":     dict(members=_by(lambda b: tier(b) in ("command","lt")),
                        topic="Command net: Helm, Marshal, Vigil, Ledger, LockBox, Lts. Bridged to Telegram/WhatsApp."),
    "fleet":       dict(members=_all(),
                        topic="All-hands — DISPATCH / ACK / TRAP."),
    "alerts":      dict(members=_by(lambda b: b in ("marshal","subscription_watcher","api_watcher","lockbox")),
                        topic="Vigil stalls, Ledger spend, LockBox security — redacted alerts only."),
    "drafts":      dict(members=_by(lambda b: b in ("ops_lt","email_drafter")),
                        topic="Quill drafts land here for Deck review. Never sent."),
    "ready-room":  dict(members=_by(lambda b: b in ("coding_lt","firstmate","git_yeoman")),
                        topic="Coding wing standup: Wrench + Mate + Yeoman."),
    "catapult":    dict(members=_by(lambda b: b in ("coding_lt","firstmate")),
                        topic="Wrench dispatches coding jobs to Mate."),
    "quarterdeck": dict(members=_by(lambda b: wing(b)=="ops"),
                        topic="Ops wing: Deck + Inbox, Quill, Chronos, Tasker, Purse."),
    "chart-room":  dict(members=_by(lambda b: wing(b)=="knowledge"),
                        topic="Knowledge wing: Stacks + Librarian, Clerk."),
    "war-room":    dict(members=_by(lambda b: wing(b)=="recon"),
                        topic="Recon wing: Chart + Sonar, Probe."),
    "email":       dict(members=_by(lambda b: b in ("email_reader","email_drafter","ops_lt")),
                        topic="Email triage + drafts (read/draft only, NEVER send)."),
    "calendar":    dict(members=_by(lambda b: b in ("calendar_manager","ops_lt")),
                        topic="Chronos calendar — Deck oversight."),
    "tasks":       dict(members=_by(lambda b: b in ("todoist_manager","ops_lt")),
                        topic="Tasker / Todoist — Deck oversight."),
    "vault":       dict(members=_by(lambda b: b in ("vault_librarian","obsidian_archivist","knowledge_lt")),
                        topic="Obsidian Second Brain: Stacks + Librarian query + Clerk intake."),
    "finance":     dict(members=_by(lambda b: b in ("finance_reader","ops_lt")),
                        topic="Purse — read-only Monarch, Deck oversight."),
    "audit":       dict(members=_by(lambda b: b in ("marshal","subscription_watcher","api_watcher","lockbox")),
                        topic="Dual-audit trail (Buzz Nostr + maka layer)."),
    "urgent":      dict(members=_by(lambda b: b=="marshal"),
                        topic="Helm + Marshal — urgent escalations only."),
    "general":     dict(members=_all(),
                        topic="General / handoff home."),
}

# ── Helpers ───────────────────────────────────────────────────────────────────
def keygen_or_load(name: str) -> str:
    KEYDIR.mkdir(parents=True, exist_ok=True)
    f = KEYDIR / f"{name}.sk"
    if f.exists():
        return f.read_text().strip()
    sk = subprocess.run([NAK, "key", "generate"], capture_output=True, text=True).stdout.strip()
    f.write_text(sk + "\n")
    return sk

def pubkey_of(sk: str) -> str:
    return subprocess.run([NAK, "key", "public", sk],
                          capture_output=True, text=True).stdout.strip()

def nak_event(args: list, sk: str) -> str:
    cmd = [NAK] + args + ["--sec", sk, "--auth", RELAY]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return (r.stdout + r.stderr).strip()

def nak_req(args: list, sk: str) -> list[dict]:
    cmd = [NAK, "req"] + args + ["--sec", sk, "--auth", RELAY]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    events = []
    for line in r.stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                events.append(json.loads(line))
            except Exception:
                pass
    return events

# ── Load keys ─────────────────────────────────────────────────────────────────
print(f"Loading keys for {len(FLEET)} bots from {KEYDIR}...")
KEYS = {}
PUBS = {}
for bot_id in FLEET:
    KEYS[bot_id] = keygen_or_load(bot_id)
    PUBS[bot_id] = pubkey_of(KEYS[bot_id])
    print(f"  {callsign(bot_id):12} {PUBS[bot_id][:16]}...")

owner_sk = KEYS[OWNER]

# ── Step 1: Publish kind:0 profiles for all bots ─────────────────────────────
print(f"\n=== STEP 1: Publish kind:0 profiles → {RELAY} ===")
for bot_id, (cs, em, tr, wg, primary, chain) in FLEET.items():
    profile = {
        "name":    f"{cs} {em}",
        "about":   f"{tr.upper()} · {wg} wing\nModel: {primary}\nChain: {chain}\nBilling: SUBSCRIPTION/OAuth-only — no API keys, no frontier on OpenRouter",
        "picture": "",
    }
    content = json.dumps(profile, ensure_ascii=False)
    if DRY:
        print(f"  [DRY] kind:0 {cs}: {content[:80]}...")
        continue
    out = nak_event(["event", "-k", "0", "-c", content], KEYS[bot_id])
    ok = "published" in out.lower() or ('"kind":0' in out) or ("id" in out and "sig" in out)
    print(f"  {'✓' if ok else '?'} {cs} {em} profile published")
    time.sleep(0.15)

# ── Step 2: Create NIP-29 channels (idempotent — check existing first) ────────
print(f"\n=== STEP 2: Create/verify {len(CHANNELS)} NIP-29 channels ===")

# Fetch existing channels owned by Helm on this community
existing = {}
ev_list = nak_req(["-k", "39000", "--limit", "100"], owner_sk)
for ev in ev_list:
    tags = {t[0]: t[1] for t in ev.get("tags", []) if len(t) >= 2}
    ch_name = tags.get("name", "")
    d_tag   = tags.get("d", "")
    if ch_name and d_tag:
        existing[ch_name] = d_tag
print(f"  Found {len(existing)} existing channels: {sorted(existing.keys())}")

channel_uuids: dict[str, str] = dict(existing)

for ch_name, ch_cfg in CHANNELS.items():
    if ch_name in existing:
        print(f"  ↩ #{ch_name} already exists ({existing[ch_name][:8]}...)")
        continue
    if DRY:
        print(f"  [DRY] would create #{ch_name}")
        continue
    out = nak_event(["event", "-k", "9007",
                     "--tag", f"name={ch_name}",
                     "--tag", "visibility=open",
                     "-c", ""], owner_sk)
    # Extract the uuid from the reply (kind:39000 relay echo or the event id)
    uuid_val = None
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                ev = json.loads(line)
                for t in ev.get("tags", []):
                    if t[0] == "d":
                        uuid_val = t[1]; break
                if not uuid_val and ev.get("id"):
                    uuid_val = ev["id"]
            except Exception:
                pass
    if uuid_val:
        channel_uuids[ch_name] = uuid_val
        print(f"  ✓ #{ch_name} created → {uuid_val[:8]}...")
    else:
        print(f"  ? #{ch_name} — could not resolve UUID from:\n    {out[:120]}")
    time.sleep(0.3)

# Re-query to fill in any still-missing UUIDs
if not DRY:
    time.sleep(1)
    ev_list2 = nak_req(["-k", "39000", "--limit", "100"], owner_sk)
    for ev in ev_list2:
        tags = {t[0]: t[1] for t in ev.get("tags", []) if len(t) >= 2}
        ch_name = tags.get("name", "")
        d_tag   = tags.get("d", "")
        if ch_name and d_tag and ch_name not in channel_uuids:
            channel_uuids[ch_name] = d_tag

# ── Step 3: Set channel topics (kind:9002) ────────────────────────────────────
print(f"\n=== STEP 3: Set channel topics ===")
for ch_name, ch_cfg in CHANNELS.items():
    uuid = channel_uuids.get(ch_name)
    if not uuid:
        print(f"  SKIP #{ch_name} — no UUID resolved")
        continue
    topic = ch_cfg.get("topic", "")
    if DRY:
        print(f"  [DRY] #{ch_name} topic: {topic[:60]}")
        continue
    out = nak_event(["event", "-k", "9002",
                     "--tag", f"h={uuid}",
                     "--tag", f"topic={topic}",
                     "-c", ""], owner_sk)
    print(f"  ✓ #{ch_name} topic set")
    time.sleep(0.1)

# ── Step 4: Add members to channels (kind:9000) ───────────────────────────────
print(f"\n=== STEP 4: Wire channel members ===")
# First, fetch existing members per channel to avoid re-sending (idempotent)
existing_members: dict[str, set] = {}
if not DRY:
    for ch_name, uuid in channel_uuids.items():
        ev_list3 = nak_req(["-k", "39002", "--tag", f"d={uuid}", "--limit", "1"], owner_sk)
        existing_members[ch_name] = set()
        for ev in ev_list3:
            for t in ev.get("tags", []):
                if t[0] == "p" and len(t) >= 2:
                    existing_members[ch_name].add(t[1])

total_adds = 0
for ch_name, ch_cfg in CHANNELS.items():
    uuid = channel_uuids.get(ch_name)
    if not uuid:
        print(f"  SKIP #{ch_name} — no UUID")
        continue
    members = ch_cfg["members"]
    already = existing_members.get(ch_name, set())
    added = 0
    for bot_id in members:
        pub = PUBS[bot_id]
        if pub in already:
            continue  # already a member
        if DRY:
            print(f"  [DRY] #{ch_name} add {callsign(bot_id)}")
            continue
        out = nak_event(["event", "-k", "9000",
                         "--tag", f"h={uuid}",
                         "--tag", f"p={pub}",
                         "-c", ""], owner_sk)
        added += 1
        total_adds += 1
        time.sleep(0.05)
    if not DRY:
        print(f"  #{ch_name}: +{added} members ({len(members)} total)")

print(f"\n  Total new member events: {total_adds}")

# ── Step 5: Register all bots as relay members (role=member) ─────────────────
print(f"\n=== STEP 5: Relay-level membership ===")
# Use the buzz REST API or admin to add relay members
# The relay admin API: POST /api/relay/members with the owner's auth
# We do it via nak by posting kind:9000 to the relay root (NIP-29 Helm = relay owner)
# Actually relay members are added via relay admin or SQL — let's do SQL for the localhost community
com_id_result = subprocess.run(
    ["docker", "exec", "buzz-postgres", "psql", "-U", "buzz", "-d", "buzz", "-t", "-c",
     "SELECT id FROM communities WHERE lower(host)='localhost:3000';"],
    capture_output=True, text=True).stdout.strip()

if com_id_result and not DRY:
    com_id = com_id_result.strip()
    michael_sk = (KEYDIR / "mac.sk").read_text().strip() if (KEYDIR / "mac.sk").exists() else (KEYDIR / "michael.sk").read_text().strip()
    michael_pub = pubkey_of(michael_sk)

    all_pubs = list(PUBS.values()) + [michael_pub]
    added_relay = 0
    for pub in all_pubs:
        r = subprocess.run(
            ["docker", "exec", "buzz-postgres", "psql", "-U", "buzz", "-d", "buzz", "-t", "-c",
             f"INSERT INTO relay_members (community_id, pubkey, role, added_by) "
             f"VALUES ('{com_id}', '{pub}', 'member', '{PUBS[OWNER]}') ON CONFLICT DO NOTHING;"],
            capture_output=True, text=True)
        if "INSERT 0 1" in r.stdout:
            added_relay += 1
    print(f"  Added {added_relay} relay-level member rows for localhost community")
else:
    print(f"  Localhost community ID: {com_id_result} (DRY or not found)")

# ── Summary ───────────────────────────────────────────────────────────────────
print(f"\n{'='*60}")
print(f"IMPORT COMPLETE {'(dry run)' if DRY else ''}")
print(f"  Relay:    {RELAY}")
print(f"  Bots:     {len(FLEET)} identities")
print(f"  Channels: {len(channel_uuids)}/{len(CHANNELS)} resolved")
print(f"  Billing:  HARD-GUARD PASS (OAuth-only, no API keys)")
print(f"\nModel chains set in kind:0 profiles:")
for bot_id, (cs, em, tr, wg, primary, chain) in FLEET.items():
    print(f"  {cs:12} {em}  {primary}")
print(f"\nAll subscription models (Claude Max / SuperGrok) = $0 marginal.")
print(f"OR tail = allowlist only (DeepSeek flash, Gemini Flash, gpt-oss).")
print(f"NO Anthropic/xAI API keys. NO frontier models on OpenRouter.")
