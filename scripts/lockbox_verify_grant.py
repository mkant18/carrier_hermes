#!/usr/bin/env python3
"""Verify a LockBox HANDSHAKE_GRANT (HMAC-SHA256 or ed25519 stub).

Phase A structural verifier — used before any Doppler fetch in Phase B.

Canonical body for signing:
  - Parse grant as JSON object
  - Deep-copy; set integrity.signature to ""
  - Serialize with sort_keys=True, separators=(",", ":"), ensure_ascii=False
  - UTF-8 bytes → HMAC-SHA256(key) → hex digest (lowercase)

Key resolution (first hit):
  1. LOCKBOX_GRANT_HMAC_KEY env (raw or hex if prefixed hex:)
  2. ~/.hermes/carrier/lockbox/keys/<key_id>  (raw file bytes stripped)
  3. --key-file PATH

Exit codes:
  0  valid signature (+ optional time/decision checks)
  1  invalid signature / schema / decision
  2  usage / IO error
  3  expired (when --check-expiry)
  4  replay (when --jti-db provided and jti seen)

Does not print secret values. Does not call Doppler.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(s: str) -> datetime:
    s = s.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def canonical_bytes(grant: dict) -> bytes:
    body = deepcopy(grant)
    integrity = body.get("integrity")
    if not isinstance(integrity, dict):
        raise ValueError("missing integrity object")
    integrity = dict(integrity)
    integrity["signature"] = ""
    body["integrity"] = integrity
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def load_key(key_id: str, key_file: str | None) -> bytes:
    if key_file:
        p = Path(key_file)
        if not p.is_file():
            raise FileNotFoundError(f"key file not found: {p}")
        return p.read_bytes().strip()
    env = os.environ.get("LOCKBOX_GRANT_HMAC_KEY", "")
    if env:
        if env.startswith("hex:"):
            return bytes.fromhex(env[4:])
        return env.encode("utf-8")
    home = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
    # keys live under carrier lockbox, not profile home
    default = Path.home() / ".hermes" / "carrier" / "lockbox" / "keys" / key_id
    if default.is_file():
        return default.read_bytes().strip()
    raise FileNotFoundError(
        f"no key for {key_id}: set LOCKBOX_GRANT_HMAC_KEY or create {default}"
    )


def verify_hmac(grant: dict, key: bytes) -> bool:
    integrity = grant["integrity"]
    if integrity.get("alg") != "HMAC-SHA256":
        raise ValueError(f"unsupported alg for hmac path: {integrity.get('alg')}")
    sig = str(integrity.get("signature", "")).strip().lower()
    if sig.startswith("0x"):
        sig = sig[2:]
    expected = hmac.new(key, canonical_bytes(grant), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


def jti_seen(jti_db: Path, jti: str) -> bool:
    if not jti_db.is_file():
        return False
    for line in jti_db.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        if line == jti or line.startswith(jti + "\t") or line.startswith(jti + " "):
            return True
    return False


def mark_jti(jti_db: Path, jti: str) -> None:
    jti_db.parent.mkdir(parents=True, exist_ok=True)
    with jti_db.open("a", encoding="utf-8") as f:
        f.write(f"{jti}\t{_utc_now().isoformat()}\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Verify LockBox HANDSHAKE_GRANT integrity")
    ap.add_argument("grant_path", type=Path, help="Path to grant JSON")
    ap.add_argument("--key-file", default=None, help="Override HMAC key file")
    ap.add_argument(
        "--check-expiry",
        action="store_true",
        help="Fail exit 3 if expires_at is past",
    )
    ap.add_argument(
        "--require-decision",
        default="approve,narrow",
        help="Comma list of allowed decisions (default approve,narrow)",
    )
    ap.add_argument(
        "--expect-subject",
        default=None,
        help="Require subject_bot equals this bot_id",
    )
    ap.add_argument(
        "--jti-db",
        type=Path,
        default=None,
        help="Append-only jti log; fail exit 4 on replay; --consume marks jti",
    )
    ap.add_argument(
        "--consume",
        action="store_true",
        help="Append jti to --jti-db after successful verify",
    )
    ap.add_argument(
        "--sign",
        action="store_true",
        help="Dev helper: write signature into grant file (requires key). Not for production release path.",
    )
    args = ap.parse_args(argv)

    try:
        raw = args.grant_path.read_text(encoding="utf-8")
        grant = json.loads(raw)
    except Exception as e:
        print(f"ERROR load: {e}", file=sys.stderr)
        return 2

    if not isinstance(grant, dict):
        print("ERROR: grant root must be object", file=sys.stderr)
        return 1

    for field in (
        "grant_id",
        "jti",
        "from",
        "to_lockbox",
        "subject_bot",
        "decision",
        "expires_at",
        "integrity",
    ):
        if field not in grant:
            print(f"ERROR: missing field {field}", file=sys.stderr)
            return 1

    if grant.get("from") != "chief_of_staff" or grant.get("to_lockbox") != "lockbox":
        print("ERROR: from/to_lockbox mismatch", file=sys.stderr)
        return 1

    integrity = grant["integrity"]
    if not isinstance(integrity, dict):
        print("ERROR: integrity must be object", file=sys.stderr)
        return 1

    key_id = integrity.get("key_id") or "helm-grant-v1"
    alg = integrity.get("alg") or "HMAC-SHA256"

    try:
        key = load_key(str(key_id), args.key_file)
    except Exception as e:
        print(f"ERROR key: {e}", file=sys.stderr)
        return 2

    if args.sign:
        if alg != "HMAC-SHA256":
            print("ERROR: --sign only supports HMAC-SHA256 in V1", file=sys.stderr)
            return 2
        sig = hmac.new(key, canonical_bytes(grant), hashlib.sha256).hexdigest()
        grant = deepcopy(grant)
        grant["integrity"] = dict(grant["integrity"])
        grant["integrity"]["signature"] = sig
        args.grant_path.write_text(json.dumps(grant, indent=2) + "\n", encoding="utf-8")
        print(f"SIGNED {args.grant_path} key_id={key_id}")
        return 0

    if alg == "HMAC-SHA256":
        try:
            ok = verify_hmac(grant, key)
        except Exception as e:
            print(f"ERROR verify: {e}", file=sys.stderr)
            return 1
    elif alg == "ed25519":
        print("ERROR: ed25519 verify not implemented in V1 script (use HMAC-SHA256)", file=sys.stderr)
        return 1
    else:
        print(f"ERROR: unknown alg {alg}", file=sys.stderr)
        return 1

    if not ok:
        print("INVALID signature", file=sys.stderr)
        return 1

    allowed = {d.strip() for d in args.require_decision.split(",") if d.strip()}
    if grant.get("decision") not in allowed:
        print(f"DENY decision={grant.get('decision')}", file=sys.stderr)
        return 1

    if args.expect_subject and grant.get("subject_bot") != args.expect_subject:
        print(
            f"DENY subject_bot={grant.get('subject_bot')} expected={args.expect_subject}",
            file=sys.stderr,
        )
        return 1

    if args.check_expiry:
        try:
            exp = _parse_iso(str(grant["expires_at"]))
        except Exception as e:
            print(f"ERROR expires_at: {e}", file=sys.stderr)
            return 1
        if exp <= _utc_now():
            print(f"EXPIRED {grant['expires_at']}", file=sys.stderr)
            return 3

    jti = str(grant["jti"])
    if args.jti_db is not None:
        if jti_seen(args.jti_db, jti):
            print(f"REPLAY jti={jti}", file=sys.stderr)
            return 4
        if args.consume:
            mark_jti(args.jti_db, jti)

    print(
        "OK",
        grant.get("grant_id"),
        f"subject={grant.get('subject_bot')}",
        f"decision={grant.get('decision')}",
        f"jti={jti[:12]}…",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
