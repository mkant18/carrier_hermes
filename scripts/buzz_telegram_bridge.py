#!/usr/bin/env python3
"""
buzz_telegram_bridge.py — two-way mirror between the Buzz #command Nostr channel
and a Telegram group, so Michael reads the command bots' activity on his phone
and can command Helm from it. Telegram = official Bot API, ZERO ban risk.

DIRECTION 1  Buzz -> Telegram (this daemon):
  Subscribe (nak --stream) to kind:9 events in #command. Coalesce them into a
  short digest and flush every FLUSH_SECS (default 20s) via `hermes send --to
  telegram:<chat_id>` — official Bot API, no running gateway/LLM needed. This
  batching keeps the group readable and pacing human-like. De-dupes by event id.

DIRECTION 2  Telegram -> Buzz / Helm:
  Inbound Telegram group messages already reach Helm's gateway (hermes-telegram
  platform, gated by TELEGRAM_ALLOWED_USERS). A gateway hook forwards allowed
  group messages here via `--inject` (stdin JSON {from,text}); we post them into
  Buzz #command signed by Michael's key. Commands (!/@helm) also reach Helm,
  which is in the same group and handles them normally.

Config (env):
  CARRIER_BUZZ_RELAY    ws://mks-pc.taileda46c.ts.net:3000
  CARRIER_NAK           path to nak.exe
  CARRIER_TG_CHAT_ID    Telegram group chat id (e.g. -1001234567890) — set after
                        the group exists + the bot is added (human gate)
  CARRIER_TG_FLUSH_SECS coalesce window seconds (default 20)
  CARRIER_TG_MIRROR     'all' (default) or 'high' (only TRAP/DISPATCH, skip ACK)
  HERMES_HOME           C:\\Users\\micha\\AppData\\Local\\hermes
"""
from __future__ import annotations
import json, os, subprocess, sys, time
from pathlib import Path

RELAY = os.environ.get("CARRIER_BUZZ_RELAY", "ws://mks-pc.taileda46c.ts.net:3000")
NAK = os.environ.get("CARRIER_NAK", r"C:\Users\micha\AppData\Local\hermes\carrier\bin\nak.exe")
KEYDIR = Path(os.environ.get("CARRIER_BUZZ_KEYDIR", r"C:\Users\micha\AppData\Local\hermes\carrier\buzz-keys"))
HOME = Path(os.environ.get("HERMES_HOME", r"C:\Users\micha\AppData\Local\hermes"))
REPO = Path(__file__).resolve().parent.parent
TG_CHAT = os.environ.get("CARRIER_TG_CHAT_ID", "")
FLUSH_SECS = int(os.environ.get("CARRIER_TG_FLUSH_SECS", "20"))
MIRROR = os.environ.get("CARRIER_TG_MIRROR", "all").lower()
SEEN_PATH = HOME / "carrier" / "buzz_tg_seen.json"
OUTBOX = HOME / "carrier" / "tg_relay_outbox.jsonl"

IDENT = json.loads((REPO / "buzz" / "buzz_identities.json").read_text(encoding="utf-8"))
CHANS = json.loads((REPO / "buzz" / "buzz_channels.json").read_text(encoding="utf-8"))
CMD_UUID = CHANS["command"]["uuid"]
PK2CS = {v["pubkey"]: f"{v['callsign']} {v['emoji']}" for v in IDENT.values()}
MICHAEL_PK = IDENT["_michael"]["pubkey"]

HIGH_MARKERS = ("TRAP", "DISPATCH", "\U0001F6EC", "\U0001F6EB")  # trap/dispatch emoji


def _load_seen() -> set[str]:
    try:
        return set(json.loads(SEEN_PATH.read_text()))
    except Exception:
        return set()


def _save_seen(seen: set[str]) -> None:
    SEEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    SEEN_PATH.write_text(json.dumps(list(seen)[-3000:]))


def tg_send(text: str) -> bool:
    """Send to the Telegram group via `hermes send` (official Bot API).

    Requires CARRIER_TG_CHAT_ID + TELEGRAM_BOT_TOKEN configured (human gate).
    Before that, queue to an outbox so nothing is lost.
    """
    if not TG_CHAT:
        OUTBOX.parent.mkdir(parents=True, exist_ok=True)
        with OUTBOX.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.time(), "text": text}) + "\n")
        return True
    cmd = ["hermes", "send", "--to", f"telegram:{TG_CHAT}", "--quiet", text]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        # fall back to outbox on failure so we don't drop messages
        OUTBOX.parent.mkdir(parents=True, exist_ok=True)
        with OUTBOX.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.time(), "text": text, "err": (r.stderr or "")[:200]}) + "\n")
        return False
    return True


def inject_from_telegram(sender: str, text: str) -> int:
    """Direction 2: a Telegram group message -> post into Buzz #command as Michael."""
    sk = (KEYDIR / "michael.sk").read_text().strip()
    body = f"\U0001F4F1 {sender}: {text}"
    cmd = [NAK, "event", "-k", "9", "-c", body, "--tag", f"h={CMD_UUID}",
           "--sec", sk, "--auth", RELAY]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
    ok = "success" in ((r.stdout or "") + (r.stderr or "")).lower()
    print(f"bridge: TG->Buzz {'ok' if ok else 'FAIL'}")
    return 0 if ok else 1


def _is_high(content: str) -> bool:
    return any(m in content for m in HIGH_MARKERS)


def pump() -> int:
    """Direction 1: stream #command -> coalesce -> flush to Telegram every FLUSH_SECS."""
    seen = _load_seen()
    proc = subprocess.Popen(
        [NAK, "req", "-k", "9", "--tag", f"h={CMD_UUID}", "--stream",
         "--auth", "--sec", (KEYDIR / "chief_of_staff.sk").read_text().strip(), RELAY],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
    )
    print(f"bridge: Buzz->Telegram pump live on #command ({CMD_UUID[:8]}), "
          f"flush={FLUSH_SECS}s mirror={MIRROR} chat={'set' if TG_CHAT else 'UNSET(queue)'}")
    buf: list[str] = []
    last_flush = time.time()

    def flush():
        nonlocal buf, last_flush
        if buf:
            header = "\U0001F5FA *Buzz #command*"
            tg_send(header + "\n" + "\n".join(buf[-20:]))
            buf = []
        last_flush = time.time()

    import select  # not on Windows for pipes; use a poll loop instead
    try:
        while True:
            line = proc.stdout.readline() if proc.stdout else ""
            now = time.time()
            if line:
                line = line.strip()
                if line.startswith("{"):
                    try:
                        e = json.loads(line)
                    except Exception:
                        e = None
                    if e and e.get("kind") == 9:
                        eid = e.get("id")
                        pk = e.get("pubkey", "")
                        content = e.get("content", "")
                        if eid and eid not in seen and pk != MICHAEL_PK:
                            seen.add(eid)
                            _save_seen(seen)
                            if MIRROR != "high" or _is_high(content):
                                buf.append(f"• {content}")
            if now - last_flush >= FLUSH_SECS:
                flush()
            if proc.poll() is not None:
                break
    except KeyboardInterrupt:
        pass
    finally:
        flush()
        proc.terminate()
    return 0


def main(argv: list[str]) -> int:
    if "--inject" in argv:
        data = json.loads(sys.stdin.read() or "{}")
        return inject_from_telegram(data.get("from", "?"), data.get("text", ""))
    if "--send-test" in argv:
        i = argv.index("--send-test")
        msg = argv[i + 1] if i + 1 < len(argv) else "Carrier bridge test"
        ok = tg_send(msg)
        print("sent" if ok else "queued/failed (chat id + token set?)")
        return 0 if ok else 1
    if "--flush-outbox" in argv:
        # drain queued messages once TG_CHAT + token are live
        if not TG_CHAT or not OUTBOX.exists():
            print("nothing to flush (chat unset or no outbox)")
            return 0
        lines = OUTBOX.read_text(encoding="utf-8").splitlines()
        sent = 0
        for ln in lines:
            try:
                msg = json.loads(ln).get("text", "")
            except Exception:
                continue
            if msg and tg_send(msg):
                sent += 1
                time.sleep(1)  # human-like pacing
        OUTBOX.unlink(missing_ok=True)
        print(f"flushed {sent} queued message(s) to Telegram")
        return 0
    return pump()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
