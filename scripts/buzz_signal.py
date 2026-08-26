#!/usr/bin/env python3
"""
buzz_signal.py — post fleet activity into the Buzz Nostr relay as SIGNED events,
each from the bot's own Nostr identity. The Buzz counterpart of fleet_signal.sh
(which posts to Discord via First Watch REST).

Every command bot + Lt (and any roster bot) posts DISPATCH / ACK / TRAP / RAW
lines into a channel as a NIP-29 kind:9 message signed by its own key, so the
event is cryptographically attributable — the real "dual audit" layer from
carrier_hermes/ARCHITECTURE.md ("Dual audit | buzz (Nostr) + maka").

Identity/channel maps come from buzz/buzz_identities.json + buzz/buzz_channels.json
(committed, public). Secret keys are read from KEYDIR (gitignored) and never printed.

Usage:
  buzz_signal.py DISPATCH <bot_id> <job_id> <text> [channel]
  buzz_signal.py ACK      <bot_id> <job_id> <text> [channel]
  buzz_signal.py TRAP     <bot_id> <job_id> <text> [channel]
  buzz_signal.py RAW      <bot_id> <text>          [channel]

  channel defaults to 'fleet'. Valid: any name in buzz_channels.json
  (command, fleet, alerts, drafts, ready-room, catapult, quarterdeck,
   chart-room, war-room, email, calendar, tasks, vault, finance, audit,
   urgent, general).

Exit 0 on success; non-zero with a stderr reason otherwise. No secrets in output.
"""
from __future__ import annotations
import json, os, subprocess, sys, typing
from pathlib import Path

RELAY = os.environ.get("CARRIER_BUZZ_RELAY", "ws://mks-pc.taileda46c.ts.net:3000")
NAK = os.environ.get("CARRIER_NAK", r"C:\Users\micha\AppData\Local\hermes\carrier\bin\nak.exe")
KEYDIR = Path(os.environ.get("CARRIER_BUZZ_KEYDIR", r"C:\Users\micha\AppData\Local\hermes\carrier\buzz-keys"))
REPO = Path(__file__).resolve().parent.parent
IDENT = json.loads((REPO / "buzz" / "buzz_identities.json").read_text(encoding="utf-8"))
CHANS = json.loads((REPO / "buzz" / "buzz_channels.json").read_text(encoding="utf-8"))

VERBS = {
    "DISPATCH": "\U0001F6EB DISPATCH",
    "ACK":      "\u2693 ACK",
    "TRAP":     "\U0001F6EC TRAP",
    "RAW":      "",
}


def die(msg: str, code: int = 1) -> "typing.NoReturn":
    print(f"buzz_signal: {msg}", file=sys.stderr)
    sys.exit(code)


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        die("usage: buzz_signal.py DISPATCH|ACK|TRAP|RAW <bot_id> <...>", 2)
    verb = argv[1].upper()
    if verb not in VERBS:
        die(f"unknown verb '{verb}' (DISPATCH|ACK|TRAP|RAW)", 2)
    bot = argv[2]
    if bot not in IDENT:
        die(f"unknown bot_id '{bot}' — not in buzz_identities.json")
    info = IDENT[bot]
    cs, em = info["callsign"], info["emoji"]

    if verb == "RAW":
        if len(argv) < 4:
            die("RAW needs: <bot_id> <text> [channel]", 2)
        text = argv[3]
        channel = argv[4] if len(argv) > 4 else "fleet"
        body = text
    else:
        if len(argv) < 5:
            die(f"{verb} needs: <bot_id> <job_id> <text> [channel]", 2)
        job_id, text = argv[3], argv[4]
        channel = argv[5] if len(argv) > 5 else "fleet"
        body = f"{VERBS[verb]} | **{cs}** {em} | [{job_id}] {text}"

    if channel not in CHANS:
        die(f"unknown channel '{channel}' (see buzz_channels.json)")
    uuid = CHANS[channel]["uuid"]

    sk_path = KEYDIR / f"{bot}.sk"
    if not sk_path.exists():
        die(f"no Nostr key for {bot} at {sk_path} — run carrier_buzz_setup.py")
    sk = sk_path.read_text().strip()

    # Membership guard: the bot must be a member of the channel it posts to.
    if bot not in CHANS[channel]["members"]:
        die(f"{cs} ({bot}) is not a member of #{channel} — refusing to post")

    cmd = [NAK, "event", "-k", "9", "-c", body, "--tag", f"h={uuid}",
           "--sec", sk, "--auth", RELAY]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
    out = (r.stdout or "") + (r.stderr or "")
    if "success" in out.lower():
        print(f"buzz_signal: [{cs} {em}] -> #{channel} {verb}")
        return 0
    die(f"post failed for {bot} -> #{channel}: {out.strip()[:200]}")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
