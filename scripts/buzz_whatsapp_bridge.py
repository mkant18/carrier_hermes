#!/usr/bin/env python3
"""
buzz_whatsapp_bridge.py — two-way mirror between the Buzz #command Nostr channel
and a WhatsApp group, so Michael can read the command bots' activity on his phone
and post/command from it (Phase 3).

DIRECTION 1  Buzz -> WhatsApp:
  Subscribe (nak --stream) to kind:9 events in the #command channel. For each NEW
  event authored by a fleet bot, send its text to the WhatsApp group via the
  Hermes gateway outbound API (the same bridge Helm uses). De-dupes by event id.

DIRECTION 2  WhatsApp -> Buzz:
  Inbound WhatsApp group messages are delivered to Helm's gateway (Baileys ->
  hermes-whatsapp platform). A small gateway hook (installed separately) forwards
  each allowed group message here on stdin as JSON {from, text}; we post it into
  Buzz #command signed by Michael's key, and — if it starts with '!' or '@helm' —
  leave it for Helm's normal command handling (Helm is in the same group).

This process is the Buzz->WA pump (Direction 1). Direction 2 is event-driven via
the gateway hook calling `--inject`. Runs as a tracked background process.

Config (env, all have defaults):
  CARRIER_BUZZ_RELAY   ws://mks-pc.taileda46c.ts.net:3000
  CARRIER_NAK          path to nak.exe
  CARRIER_WA_GROUP_ID  WhatsApp group JID (set after group is created + discovered)
  HERMES_HOME          C:\\Users\\micha\\AppData\\Local\\hermes

No secrets printed. Michael's Nostr key read from KEYDIR (gitignored).
"""
from __future__ import annotations
import json, os, subprocess, sys, time
from pathlib import Path

RELAY = os.environ.get("CARRIER_BUZZ_RELAY", "ws://mks-pc.taileda46c.ts.net:3000")
NAK = os.environ.get("CARRIER_NAK", r"C:\Users\micha\AppData\Local\hermes\carrier\bin\nak.exe")
KEYDIR = Path(os.environ.get("CARRIER_BUZZ_KEYDIR", r"C:\Users\micha\AppData\Local\hermes\carrier\buzz-keys"))
HOME = Path(os.environ.get("HERMES_HOME", r"C:\Users\micha\AppData\Local\hermes"))
REPO = Path(__file__).resolve().parent.parent
WA_GROUP = os.environ.get("CARRIER_WA_GROUP_ID", "")  # set once the group exists
SEEN_PATH = HOME / "carrier" / "buzz_wa_seen.json"

IDENT = json.loads((REPO / "buzz" / "buzz_identities.json").read_text(encoding="utf-8"))
CHANS = json.loads((REPO / "buzz" / "buzz_channels.json").read_text(encoding="utf-8"))
CMD_UUID = CHANS["command"]["uuid"]
PK2CS = {v["pubkey"]: f"{v['callsign']} {v['emoji']}" for v in IDENT.values()}
MICHAEL_PK = IDENT["_michael"]["pubkey"]


def _load_seen() -> set[str]:
    try:
        return set(json.loads(SEEN_PATH.read_text()))
    except Exception:
        return set()


def _save_seen(seen: set[str]) -> None:
    SEEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    # cap the file so it doesn't grow unbounded
    SEEN_PATH.write_text(json.dumps(list(seen)[-2000:]))


def send_to_whatsapp(text: str) -> bool:
    """Send a message to the WhatsApp group.

    ARCHITECTURE NOTE: the Baileys bridge's HTTP /send port is managed
    internally by Helm's gateway subprocess and is NOT a stable third-party
    API. So the Buzz->WhatsApp mirror is delivered THROUGH Helm: we drop the
    line into Helm's WhatsApp-relay inbox file, which a small gateway hook
    picks up and sends to the WA group over Helm's already-paired session.
    This reuses Helm's paired WhatsApp session and needs no port discovery.

    Until WhatsApp is paired (human gate) + CARRIER_WA_GROUP_ID is set, this
    queues the message to the relay inbox; the hook drains it once live.
    """
    if not WA_GROUP:
        # queue to relay inbox so nothing is lost before pairing
        inbox = HOME / "carrier" / "wa_relay_outbox.jsonl"
        inbox.parent.mkdir(parents=True, exist_ok=True)
        with inbox.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.time(), "group": WA_GROUP, "text": text}) + "\n")
        return True
    # WA_GROUP is set: append to the relay outbox the Helm hook drains.
    inbox = HOME / "carrier" / "wa_relay_outbox.jsonl"
    inbox.parent.mkdir(parents=True, exist_ok=True)
    with inbox.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": time.time(), "group": WA_GROUP, "text": text}) + "\n")
    return True


def inject_from_whatsapp(sender: str, text: str) -> int:
    """Direction 2: a WhatsApp group message -> post into Buzz #command as Michael."""
    sk = (KEYDIR / "michael.sk").read_text().strip()
    body = f"\U0001F4F1 {sender}: {text}"
    cmd = [NAK, "event", "-k", "9", "-c", body, "--tag", f"h={CMD_UUID}",
           "--sec", sk, "--auth", RELAY]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
    ok = "success" in ((r.stdout or "") + (r.stderr or "")).lower()
    print(f"bridge: WA->Buzz {'ok' if ok else 'FAIL'}")
    return 0 if ok else 1


def pump_buzz_to_whatsapp() -> int:
    """Direction 1: stream #command kind:9 -> WhatsApp (skip Michael's own + dupes)."""
    seen = _load_seen()
    proc = subprocess.Popen(
        [NAK, "req", "-k", "9", "--tag", f"h={CMD_UUID}", "--stream",
         "--auth", "--sec", (KEYDIR / "chief_of_staff.sk").read_text().strip(), RELAY],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
    )
    print(f"bridge: Buzz->WhatsApp pump live on #command ({CMD_UUID[:8]})")
    try:
        for line in proc.stdout:  # type: ignore[union-attr]
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                e = json.loads(line)
            except Exception:
                continue
            if e.get("kind") != 9:
                continue
            eid = e.get("id")
            if not eid or eid in seen:
                continue
            seen.add(eid)
            _save_seen(seen)
            pk = e.get("pubkey", "")
            if pk == MICHAEL_PK:
                continue  # don't echo Michael's own messages back to him
            who = PK2CS.get(pk, pk[:8])
            content = e.get("content", "")
            send_to_whatsapp(f"[Buzz #command] {content}")
    except KeyboardInterrupt:
        pass
    finally:
        proc.terminate()
    return 0


def main(argv: list[str]) -> int:
    if "--inject" in argv:
        # stdin JSON: {"from": "...", "text": "..."}
        data = json.loads(sys.stdin.read() or "{}")
        return inject_from_whatsapp(data.get("from", "?"), data.get("text", ""))
    if "--send-test" in argv:
        i = argv.index("--send-test")
        msg = argv[i + 1] if i + 1 < len(argv) else "bridge test"
        ok = send_to_whatsapp(msg)
        print("sent" if ok else "send failed (group id set? paired?)")
        return 0 if ok else 1
    # default: run the Buzz->WhatsApp pump
    return pump_buzz_to_whatsapp()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
