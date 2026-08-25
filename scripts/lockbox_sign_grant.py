#!/usr/bin/env python3
"""Helm-only: sign a HANDSHAKE_GRANT JSON (HMAC-SHA256).

Do NOT install or run this on the lockbox bot home. LockBox verifies only
via lockbox_verify_grant.py.

Usage:
  scripts/lockbox_sign_grant.py path/to/grant.json [--key-file ...]
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import sys
from copy import deepcopy
from pathlib import Path

ALLOWED_KEY_IDS = frozenset({"helm-grant-v1"})
KEY_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$")


def canonical_bytes(grant: dict) -> bytes:
    body = deepcopy(grant)
    integrity = dict(body.get("integrity") or {})
    integrity["signature"] = ""
    body["integrity"] = integrity
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def sanitize_key_id(key_id: str) -> str:
    if not key_id or not KEY_ID_RE.match(key_id) or key_id not in ALLOWED_KEY_IDS:
        raise ValueError(f"key_id not allowlisted: {key_id!r}")
    return key_id


def load_key(key_id: str, key_file: str | None) -> bytes:
    kid = sanitize_key_id(key_id)
    if key_file:
        return Path(key_file).read_bytes().strip()
    env = os.environ.get("LOCKBOX_GRANT_HMAC_KEY", "")
    if env:
        if env.startswith("hex:"):
            return bytes.fromhex(env[4:])
        return env.encode("utf-8")
    keys_root = (Path.home() / ".hermes" / "carrier" / "lockbox" / "keys").resolve()
    p = (keys_root / kid).resolve()
    if not str(p).startswith(str(keys_root) + os.sep):
        raise ValueError("key path escape")
    if not p.is_file():
        raise FileNotFoundError(p)
    return p.read_bytes().strip()


def main() -> int:
    ap = argparse.ArgumentParser(description="Sign HANDSHAKE_GRANT (Helm only)")
    ap.add_argument("grant_path", type=Path)
    ap.add_argument("--key-file", default=None)
    args = ap.parse_args()
    grant = json.loads(args.grant_path.read_text(encoding="utf-8"))
    if grant.get("from") != "chief_of_staff" or grant.get("to_lockbox") != "lockbox":
        print("ERROR: refuse to sign non-Helm→LockBox grant", file=sys.stderr)
        return 1
    integ = dict(grant.get("integrity") or {})
    integ.setdefault("alg", "HMAC-SHA256")
    integ.setdefault("key_id", "helm-grant-v1")
    if integ.get("alg") != "HMAC-SHA256":
        print("ERROR: V1 signer is HMAC-SHA256 only", file=sys.stderr)
        return 1
    grant["integrity"] = integ
    key = load_key(str(integ["key_id"]), args.key_file)
    grant["integrity"]["signature"] = hmac.new(
        key, canonical_bytes(grant), hashlib.sha256
    ).hexdigest()
    args.grant_path.write_text(json.dumps(grant, indent=2) + "\n", encoding="utf-8")
    print(f"SIGNED {args.grant_path} key_id={integ['key_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
