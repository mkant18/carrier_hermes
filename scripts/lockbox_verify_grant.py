#!/usr/bin/env python3
"""Verify a LockBox HANDSHAKE_GRANT before any Doppler fetch.

V1 alg: HMAC-SHA256 (key_id allowlisted). Residual: same secret verifies and
could sign — signing is intentionally NOT in this binary (see lockbox_sign_grant.py).
Trust boundary: only Helm-operated hosts run the signer; LockBox home runs verify only.

Canonical body:
  deep-copy grant; integrity.signature=""; json.dumps(sort_keys=True, separators=(',',':'), ensure_ascii=False) UTF-8
  HMAC-SHA256 → lowercase hex

Exit codes:
  0 OK
  1 invalid / deny / scope
  2 usage / IO
  3 expired
  4 replay
  5 path/delivery constraint fail

Does not print secret values. Does not call Doppler. No --sign.
"""
from __future__ import annotations

import argparse
import errno
try:
    import fcntl  # POSIX advisory dir-lock
    _HAVE_FCNTL = True
except ImportError:  # Windows: no fcntl. Replay-prevention still holds because
    fcntl = None      # the guarantee comes from os.O_EXCL (atomic on NTFS too),
    _HAVE_FCNTL = False  # not from the advisory flock wrapping it.
import hashlib
import hmac
import json
import os
import re
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

ALLOWED_KEY_IDS = frozenset({"helm-grant-v1"})
KEY_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$")
ACTIONS = frozenset({"read_once", "read_ttl", "rotate", "create", "delete_meta"})
DELIVERIES = frozenset(
    {"env_file", "stdout_to_caller_job_only", "doppler_inject", "path_under_write_root"}
)


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


def sanitize_key_id(key_id: str) -> str:
    if not key_id or not KEY_ID_RE.match(key_id):
        raise ValueError(f"invalid key_id format: {key_id!r}")
    if key_id not in ALLOWED_KEY_IDS:
        raise ValueError(f"key_id not allowlisted: {key_id!r} allowed={sorted(ALLOWED_KEY_IDS)}")
    if "/" in key_id or "\\" in key_id or ".." in key_id:
        raise ValueError("key_id path components forbidden")
    return key_id


def load_key(key_id: str, key_file: str | None) -> bytes:
    kid = sanitize_key_id(key_id)
    if key_file:
        p = Path(key_file).resolve()
        if not p.is_file():
            raise FileNotFoundError(f"key file not found: {p}")
        return p.read_bytes().strip()
    env = os.environ.get("LOCKBOX_GRANT_HMAC_KEY", "")
    if env:
        if env.startswith("hex:"):
            return bytes.fromhex(env[4:])
        return env.encode("utf-8")
    keys_root = (Path.home() / ".hermes" / "carrier" / "lockbox" / "keys").resolve()
    default = (keys_root / kid).resolve()
    if not str(default).startswith(str(keys_root) + os.sep):
        raise ValueError("key path escapes keys root")
    if default.is_file():
        return default.read_bytes().strip()
    raise FileNotFoundError(
        f"no key for {kid}: set LOCKBOX_GRANT_HMAC_KEY or create {default}"
    )


def verify_hmac(grant: dict, key: bytes) -> bool:
    integrity = grant["integrity"]
    if integrity.get("alg") != "HMAC-SHA256":
        raise ValueError(f"unsupported alg: {integrity.get('alg')}")
    sig = str(integrity.get("signature", "")).strip().lower()
    if sig.startswith("0x"):
        sig = sig[2:]
    expected = hmac.new(key, canonical_bytes(grant), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


def consume_jti_atomic(jti_dir: Path, jti: str) -> bool:
    """Return True if consumed first time; False if replay.

    Uses O_CREAT|O_EXCL per-jti file under jti_dir (atomic on POSIX).
    """
    if not re.match(r"^[A-Za-z0-9_.:-]{8,128}$", jti):
        raise ValueError("invalid jti charset/length")
    jti_dir.mkdir(parents=True, exist_ok=True)
    # flock a dir lock for multi-writer safety around exclusives on some FS
    lock_path = jti_dir / ".lock"
    lock_path.touch(exist_ok=True)
    target = jti_dir / f"{jti}.redeemed"
    with lock_path.open("a+", encoding="utf-8") as lockf:
        if _HAVE_FCNTL:
            fcntl.flock(lockf.fileno(), fcntl.LOCK_EX)
        try:
            fd = os.open(str(target), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except OSError as e:
            if e.errno == errno.EEXIST:
                return False
            raise
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(f"{jti}\t{_utc_now().isoformat()}\n")
        return True


def load_json(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("root must be object")
    return data


def check_subset(grant: dict, request: dict | None, redeem_refs: list[str] | None) -> None:
    g_refs = set(grant.get("secret_refs_allowed") or [])
    g_acts = set(grant.get("actions_allowed") or [])
    if not g_acts <= ACTIONS:
        raise ValueError(f"unknown actions_allowed: {g_acts - ACTIONS}")
    if request is not None:
        if grant.get("request_id") and request.get("request_id") != grant.get("request_id"):
            raise ValueError("request_id mismatch grant vs ACCESS_REQUEST")
        r_refs = set(request.get("secret_refs") or [])
        r_scope = request.get("scope") or {}
        r_acts = set(r_scope.get("actions") or [])
        if not g_refs <= r_refs:
            raise ValueError(f"grant secret_refs not subset of request: {g_refs - r_refs}")
        if r_acts and not g_acts <= r_acts:
            raise ValueError(f"grant actions not subset of request: {g_acts - r_acts}")
        # narrow/approve must not expand delivery beyond request if set
        r_del = r_scope.get("delivery")
        if r_del and grant.get("delivery") and grant.get("delivery") != r_del:
            # allow only if narrow to same family — V1: must match
            raise ValueError("grant delivery must match ACCESS_REQUEST scope.delivery")
    if redeem_refs is not None:
        need = set(redeem_refs)
        if not need <= g_refs:
            raise ValueError(f"redeem refs exceed grant: {need - g_refs}")


def check_delivery_constraints(grant: dict) -> None:
    delivery = grant.get("delivery")
    if delivery not in DELIVERIES:
        raise ValueError(f"invalid delivery: {delivery}")
    paths = grant.get("write_paths_allowed") or []
    if delivery == "path_under_write_root" and not paths:
        raise ValueError("path_under_write_root requires non-empty write_paths_allowed")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Verify LockBox HANDSHAKE_GRANT (no signing)")
    ap.add_argument("grant_path", type=Path)
    ap.add_argument("--key-file", default=None)
    ap.add_argument(
        "--expect-subject",
        required=True,
        help="Required: redeeming bot_id must equal grant subject_bot",
    )
    ap.add_argument(
        "--jti-dir",
        type=Path,
        default=Path.home() / ".hermes" / "carrier" / "lockbox" / "jti",
        help="Directory of O_EXCL jti markers (atomic consume)",
    )
    ap.add_argument(
        "--no-consume",
        action="store_true",
        help="Verify without consuming jti (dry-run)",
    )
    ap.add_argument(
        "--require-decision",
        default="approve,narrow",
    )
    ap.add_argument(
        "--access-request",
        type=Path,
        default=None,
        help="Optional ACCESS_REQUEST JSON for subset checks",
    )
    ap.add_argument(
        "--redeem-refs",
        default=None,
        help="Comma-separated secret refs this redeem wants (must ⊆ grant)",
    )
    ap.add_argument(
        "--allow-break-glass-skew",
        action="store_true",
        help="Skip expires_at <= decided_at + ttl_seconds check",
    )
    args = ap.parse_args(argv)

    try:
        grant = load_json(args.grant_path)
    except Exception as e:
        print(f"ERROR load: {e}", file=sys.stderr)
        return 2

    for field in (
        "grant_id",
        "jti",
        "from",
        "to_lockbox",
        "subject_bot",
        "decision",
        "expires_at",
        "decided_at",
        "integrity",
        "secret_refs_allowed",
        "actions_allowed",
        "delivery",
        "ttl_seconds",
    ):
        if field not in grant:
            print(f"ERROR: missing field {field}", file=sys.stderr)
            return 1

    if grant.get("from") != "chief_of_staff" or grant.get("to_lockbox") != "lockbox":
        print("ERROR: from/to_lockbox mismatch", file=sys.stderr)
        return 1

    if grant.get("subject_bot") != args.expect_subject:
        print(
            f"DENY subject_bot={grant.get('subject_bot')} expected={args.expect_subject}",
            file=sys.stderr,
        )
        return 1

    integrity = grant["integrity"]
    if not isinstance(integrity, dict):
        print("ERROR: integrity must be object", file=sys.stderr)
        return 1

    try:
        key_id = sanitize_key_id(str(integrity.get("key_id") or "helm-grant-v1"))
        key = load_key(key_id, args.key_file)
        ok = verify_hmac(grant, key)
    except Exception as e:
        print(f"ERROR verify: {e}", file=sys.stderr)
        return 1

    if not ok:
        print("INVALID signature", file=sys.stderr)
        return 1

    allowed = {d.strip() for d in args.require_decision.split(",") if d.strip()}
    if grant.get("decision") not in allowed:
        print(f"DENY decision={grant.get('decision')}", file=sys.stderr)
        return 1

    # Expiry always enforced
    try:
        exp = _parse_iso(str(grant["expires_at"]))
        decided = _parse_iso(str(grant["decided_at"]))
        ttl = int(grant.get("ttl_seconds") or 0)
    except Exception as e:
        print(f"ERROR time fields: {e}", file=sys.stderr)
        return 1
    if exp <= _utc_now():
        print(f"EXPIRED {grant['expires_at']}", file=sys.stderr)
        return 3
    if not args.allow_break_glass_skew and ttl >= 0:
        # expires should not exceed decided + ttl (+ 120s clock skew)
        max_exp = decided.timestamp() + ttl + 120
        if exp.timestamp() > max_exp and not grant.get("break_glass"):
            print("DENY expires_at beyond decided_at+ttl_seconds", file=sys.stderr)
            return 1

    try:
        check_delivery_constraints(grant)
    except ValueError as e:
        print(f"DENY delivery: {e}", file=sys.stderr)
        return 5

    request = None
    if args.access_request:
        try:
            request = load_json(args.access_request)
        except Exception as e:
            print(f"ERROR access_request: {e}", file=sys.stderr)
            return 2

    redeem_refs = None
    if args.redeem_refs:
        redeem_refs = [x.strip() for x in args.redeem_refs.split(",") if x.strip()]

    try:
        check_subset(grant, request, redeem_refs)
    except ValueError as e:
        print(f"DENY scope: {e}", file=sys.stderr)
        return 1

    jti = str(grant["jti"])
    if not args.no_consume:
        try:
            first = consume_jti_atomic(args.jti_dir, jti)
        except Exception as e:
            print(f"ERROR jti: {e}", file=sys.stderr)
            return 2
        if not first:
            print(f"REPLAY jti={jti}", file=sys.stderr)
            return 4

    print(
        "OK",
        grant.get("grant_id"),
        f"subject={grant.get('subject_bot')}",
        f"decision={grant.get('decision')}",
        f"jti={jti[:12]}…",
        "dry" if args.no_consume else "consumed",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
