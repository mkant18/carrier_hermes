#!/usr/bin/env python3
"""Send an AIPass hybrid mailbox message between Carrier Hermes bots."""
from __future__ import annotations

import argparse
import importlib.util
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_mod_path = ROOT / "vendored" / "aipass-mailbox" / "aipass_mailbox.py"


def _load_aipass():
    name = "carrier_aipass_mailbox"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, _mod_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {_mod_path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


aipass = _load_aipass()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--from", dest="frm", required=True, help="bot_id sender")
    p.add_argument("--to", dest="to", required=True, help="bot_id recipient")
    p.add_argument("--mission", required=True)
    p.add_argument("--body", default="", help="markdown body")
    p.add_argument("--body-file", type=Path, help="read body from file")
    p.add_argument(
        "--vault",
        default=os.environ.get(
            "OBSIDIAN_VAULT_PATH",
            str(Path.home() / "Desktop/Existing Folders/OBSIDIAN"),
        ),
    )
    args = p.parse_args()
    body = args.body_file.read_text(encoding="utf-8") if args.body_file else args.body
    if not str(body).strip():
        body = f"## REPORT\n\n(mission: {args.mission})\n"
    if not str(body).endswith("\n"):
        body = str(body) + "\n"

    msg = aipass.Message(
        from_agent=args.frm,
        to_agent=args.to,
        mission=args.mission,
        status="unread",
        body=body,
    )
    vault = Path(args.vault)
    inbox = vault / "_agent" / "mailbox" / args.to / "inbox"
    outbox = vault / "_agent" / "mailbox" / args.frm / "outbox"
    inbox.mkdir(parents=True, exist_ok=True)
    outbox.mkdir(parents=True, exist_ok=True)
    name = aipass.message_filename(args.frm, args.mission)
    text = msg.render()
    (inbox / name).write_text(text, encoding="utf-8")
    (outbox / name).write_text(text, encoding="utf-8")
    print(inbox / name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
