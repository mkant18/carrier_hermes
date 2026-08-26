#!/usr/bin/env python3
"""
carrier_buzz_setup.py — give every Carrier Hermes bot a real Nostr identity on
the Buzz relay, mirror the Discord channel topology as NIP-29 groups, wire
membership per the wing/tier structure, and designate the WhatsApp command
group (command tier + Lieutenants + Michael).

Idempotent: re-running reuses existing keys (from KEYDIR) and existing channels
(matched by name in relay kind:39000 metadata). Secret keys NEVER leave KEYDIR
(gitignored); only public keys + the channel map are written to committable JSON.

Usage:
  python scripts/carrier_buzz_setup.py            # full setup
  python scripts/carrier_buzz_setup.py --dry-run  # print plan only
"""
from __future__ import annotations
import json, os, subprocess, sys, time
from pathlib import Path

RELAY = os.environ.get("CARRIER_BUZZ_RELAY", "ws://mks-pc.taileda46c.ts.net:3000")
NAK = os.environ.get("CARRIER_NAK", r"C:\Users\micha\AppData\Local\hermes\carrier\bin\nak.exe")
KEYDIR = Path(os.environ.get("CARRIER_BUZZ_KEYDIR", r"C:\Users\micha\AppData\Local\hermes\carrier\buzz-keys"))
OUTDIR = Path(__file__).resolve().parent.parent / "buzz"   # committable artifacts land here
DRY = "--dry-run" in sys.argv

# ── Roster: bot_id -> (callsign, emoji, tier, wing) ─────────────────────────
# tier: command | lt | worker ;  wing: command | coding | ops | knowledge | recon
ROSTER = {
    "chief_of_staff":       ("Helm",      "\u2693",     "command", "command"),
    "marshal":              ("Marshal",   "\U0001F396", "command", "command"),
    "subscription_watcher": ("Vigil",     "\U0001F4E1", "command", "command"),
    "api_watcher":          ("Ledger",    "\U0001F4B5", "command", "command"),
    "lockbox":              ("LockBox",   "\U0001F512", "command", "command"),
    "coding_lt":            ("Wrench",    "\U0001F527", "lt",      "coding"),
    "ops_lt":               ("Deck",      "\U0001F5C2", "lt",      "ops"),
    "knowledge_lt":         ("Stacks",    "\U0001F4DA", "lt",      "knowledge"),
    "hermes_ai_explorer":   ("Chart",     "\U0001F5FA", "lt",      "recon"),
    "firstmate":            ("Mate",      "\u2699",     "worker",  "coding"),
    "git_yeoman":           ("Yeoman",    "\U0001F4CB", "worker",  "coding"),
    "passive_watch":        ("Sonar",     "\U0001F30A", "worker",  "recon"),
    "research_agent":       ("Probe",     "\U0001F52D", "worker",  "recon"),
    "email_reader":         ("Inbox",     "\U0001F4EC", "worker",  "ops"),
    "email_drafter":        ("Quill",     "\U0001FAB6", "worker",  "ops"),
    "calendar_manager":     ("Chronos",   "\U0001F570", "worker",  "ops"),
    "todoist_manager":      ("Tasker",    "\U0001F4CB", "worker",  "ops"),
    "finance_reader":       ("Purse",     "\U0001F45B", "worker",  "ops"),
    "vault_librarian":      ("Librarian", "\U0001F4D6", "worker",  "knowledge"),
    "obsidian_archivist":   ("Clerk",     "\U0001F5C4", "worker",  "knowledge"),
}
OWNER = "chief_of_staff"  # Helm owns every channel (SUPER-USER); Marshal co-admin later.

def tier(b): return ROSTER[b][2]
def wing(b): return ROSTER[b][3]

# ── Channels: mirror the Discord server. name -> membership predicate ────────
# Helm owns all (auto-member). Values are the NON-owner bot members.
def _all(): return [b for b in ROSTER if b != OWNER]
def _by(pred): return [b for b in ROSTER if b != OWNER and pred(b)]

CHANNELS = {
    # leadership room — command tier + Lts. This is the WhatsApp-bridged group.
    "command":     dict(members=_by(lambda b: tier(b) in ("command","lt")), whatsapp=True,
                        topic="Command net: Helm, Marshal, watchers, LockBox, Lieutenants. Bridged to WhatsApp."),
    "fleet":       dict(members=_all(),
                        topic="All-hands fleet channel — DISPATCH / ACK / TRAP."),
    "alerts":      dict(members=_by(lambda b: b in ("marshal","subscription_watcher","api_watcher","lockbox")),
                        topic="Vigil stalls, Ledger spend, LockBox security — redacted alerts."),
    "drafts":      dict(members=_by(lambda b: b in ("ops_lt","email_drafter")),
                        topic="Quill drafts land here for review. Never sent."),
    "ready-room":  dict(members=_by(lambda b: b in ("coding_lt","firstmate","git_yeoman")),
                        topic="Coding wing standup."),
    "catapult":    dict(members=_by(lambda b: b in ("coding_lt","firstmate")),
                        topic="Wrench dispatches coding jobs to Mate."),
    "quarterdeck": dict(members=_by(lambda b: wing(b)=="ops"),
                        topic="Ops wing home: Deck + Inbox, Quill, Chronos, Tasker, Purse."),
    "chart-room":  dict(members=_by(lambda b: wing(b)=="knowledge"),
                        topic="Knowledge wing home: Stacks + Librarian, Clerk."),
    "war-room":    dict(members=_by(lambda b: wing(b)=="recon"),
                        topic="Recon wing home: Chart + Sonar, Probe."),
    "email":       dict(members=_by(lambda b: b in ("email_reader","email_drafter","ops_lt")),
                        topic="Email triage + drafts (read/draft only, never send)."),
    "calendar":    dict(members=_by(lambda b: b in ("calendar_manager","ops_lt")),
                        topic="Chronos calendar."),
    "tasks":       dict(members=_by(lambda b: b in ("todoist_manager","ops_lt")),
                        topic="Tasker / Todoist."),
    "vault":       dict(members=_by(lambda b: b in ("vault_librarian","obsidian_archivist","knowledge_lt")),
                        topic="Obsidian Second Brain: Librarian query, Clerk intake."),
    "finance":     dict(members=_by(lambda b: b in ("finance_reader","ops_lt")),
                        topic="Purse — read-only Monarch."),
    "audit":       dict(members=_by(lambda b: b in ("marshal","subscription_watcher","api_watcher","lockbox")),
                        topic="Dual-audit trail (the Buzz 'buzz' + maka layer)."),
    "urgent":      dict(members=_by(lambda b: b=="marshal"), whatsapp=False,
                        topic="Helm + Marshal — urgent escalations."),
    "general":     dict(members=_all(),
                        topic="General / handoff home."),
}
# Discord channel-id correspondence (for the future bridge)
DISCORD_IDS = {
    "command":"1541866378255011980","fleet":"1541866443765977138","alerts":"1541866423427801148",
    "drafts":"1541866401432871002","ready-room":"1541919952599130132","catapult":"1541919999894229053",
    "quarterdeck":"1541929900586565783","chart-room":"1541929921176281170","war-room":"1541931585220255894",
    "email":"1541155152726204416","calendar":"1541155189019517078","tasks":"1541155241746239658",
    "vault":"1541155274528915577","finance":"1541155307860795503","audit":"1541155342833025114",
    "urgent":"1541155373371621507","general":"1541154516811120762",
}

def nak(args, sk=None):
    cmd = [NAK] + args
    if sk:
        cmd += ["--sec", sk, "--auth"]
    cmd += [RELAY]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    return (r.stdout or "") + (r.stderr or "")

def keygen_or_load(name):
    KEYDIR.mkdir(parents=True, exist_ok=True)
    f = KEYDIR / f"{name}.sk"
    if f.exists():
        return f.read_text().strip()
    sk = subprocess.run([NAK, "key", "generate"], capture_output=True, text=True).stdout.strip()
    f.write_text(sk)
    try: os.chmod(f, 0o600)
    except Exception: pass
    return sk

def pubkey(sk):
    return subprocess.run([NAK, "key", "public", sk], capture_output=True, text=True).stdout.strip()

def list_channels(owner_sk):
    """Return {name: uuid} from relay-signed kind:39000 metadata."""
    out = nak(["req", "-k", "39000"], sk=owner_sk)
    m = {}
    for line in out.splitlines():
        line = line.strip()
        if not line.startswith("{"): continue
        try: e = json.loads(line)
        except Exception: continue
        if e.get("kind") != 39000: continue
        d = name = None
        for t in e.get("tags", []):
            if t and t[0] == "d": d = t[1] if len(t) > 1 else None
            if t and t[0] == "name": name = t[1] if len(t) > 1 else None
        if d and name:
            m[name] = d
    return m

def main():
    print(f"relay: {RELAY}\nnak:   {NAK}\nkeys:  {KEYDIR}\n")

    # 1) keys + pubkeys for every bot + Michael
    ident = {}
    for bot,(cs,em,ti,wg) in ROSTER.items():
        sk = keygen_or_load(bot); pk = pubkey(sk)
        ident[bot] = dict(callsign=cs, emoji=em, tier=ti, wing=wg, pubkey=pk)
    michael_sk = keygen_or_load("michael"); michael_pk = pubkey(michael_sk)
    ident["_michael"] = dict(callsign="Michael", emoji="\U0001F9D1\u200D\u2708", tier="human", wing="-", pubkey=michael_pk)
    print(f"identities: {len(ROSTER)} bots + Michael")

    if DRY:
        for b,i in ident.items():
            print(f"  {i['callsign']:10} {i['emoji']}  {i['pubkey'][:16]}  [{i['tier']}/{i['wing']}]")
        print("\nchannels:")
        for name,c in CHANNELS.items():
            wa = " (WhatsApp)" if c.get("whatsapp") else ""
            print(f"  #{name:12} {len(c['members'])+1} members{wa}")
        return

    owner_sk = KEYDIR.joinpath(f"{OWNER}.sk").read_text().strip()

    # 2) profiles (kind 0) for every bot
    for bot,(cs,em,ti,wg) in ROSTER.items():
        sk = KEYDIR.joinpath(f"{bot}.sk").read_text().strip()
        meta = json.dumps({"name": f"{cs} {em}", "about": f"Carrier Hermes {ti}/{wg} — bot_id {bot}"})
        nak(["event","-k","0","-c",meta], sk=sk)
    nak(["event","-k","0","-c",json.dumps({"name":"Michael \U0001F9D1\u200D\u2708","about":"Fleet owner"})], sk=michael_sk)
    print("profiles set")

    # 3) channels (create if missing) + membership
    existing = list_channels(owner_sk)
    chan_map = {}
    for name, cfg in CHANNELS.items():
        if name in existing:
            uuid = existing[name]
        else:
            nak(["event","-k","9007","--tag",f"name={name}","--tag","visibility=open"], sk=owner_sk)
            # re-query to get the assigned uuid
            uuid = list_channels(owner_sk).get(name)
        if not uuid:
            print(f"  ! failed to resolve channel #{name}"); continue
        # set topic (kind 9002 edit metadata — any member may set topic)
        nak(["event","-k","9002","--tag",f"h={uuid}","--tag",f"topic={cfg['topic']}"], sk=owner_sk)
        # add members (kind 9000). Serial invocations are safe (relay bumps ts).
        for bot in cfg["members"]:
            pk = ident[bot]["pubkey"]
            nak(["event","-k","9000","--tag",f"h={uuid}","--tag",f"p={pk}"], sk=owner_sk)
        if cfg.get("whatsapp"):
            nak(["event","-k","9000","--tag",f"h={uuid}","--tag",f"p={michael_pk}"], sk=owner_sk)
        chan_map[name] = dict(uuid=uuid, discord_id=DISCORD_IDS.get(name),
                              members=["chief_of_staff"]+cfg["members"],
                              whatsapp=bool(cfg.get("whatsapp")), topic=cfg["topic"])
        wa = " (WhatsApp)" if cfg.get("whatsapp") else ""
        print(f"  #{name:12} {uuid[:8]}  {len(cfg['members'])+1} members{wa}")

    # 4) write committable artifacts (public keys + channel map — NO secrets)
    OUTDIR.mkdir(parents=True, exist_ok=True)
    pub = {b:{k:v for k,v in i.items()} for b,i in ident.items()}
    (OUTDIR/"buzz_identities.json").write_text(json.dumps(pub, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUTDIR/"buzz_channels.json").write_text(json.dumps(chan_map, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {OUTDIR/'buzz_identities.json'} and buzz_channels.json")
    wa = [n for n,c in chan_map.items() if c["whatsapp"]]
    print(f"WhatsApp-bridged channel(s): {wa}")

if __name__ == "__main__":
    main()
