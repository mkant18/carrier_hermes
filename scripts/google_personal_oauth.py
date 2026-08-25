#!/usr/bin/env python3
"""Personal Gmail + Calendar OAuth for Carrier Hermes (Inbox / Chronos).

Scopes intentionally EXCLUDE gmail.send. Shared token lives at
~/.hermes/google_token.json and is symlinked into specialist profile homes.

Commands:
  --check
  --auth-url
  --auth-code CODE_OR_REDIRECT_URL
  --install-deps
  --sync-profiles   # symlink client secret + token into Inbox/Chronos homes
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERMES_ROOT = Path(os.environ.get("HERMES_ROOT", Path.home() / ".hermes")).expanduser()
CLIENT_SECRET_PATH = HERMES_ROOT / "google_client_secret.json"
TOKEN_PATH = HERMES_ROOT / "google_token.json"
PENDING_PATH = HERMES_ROOT / "google_oauth_pending_personal.json"
LAST_URL_PATH = HERMES_ROOT / "google_oauth_last_url_personal.txt"

# Personal fleet only — no send, no Drive/Docs/Sheets.
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar",
]

REDIRECT_URI = "http://localhost:1"
CONSUMER_PROFILES = ("email_reader", "calendar_manager")

REQUIRED_PACKAGES = [
    "google-api-python-client==2.194.0",
    "google-auth==2.55.1",
    "google-auth-oauthlib==1.3.1",
    "google-auth-httplib2==0.3.1",
    "httplib2==0.32.0",
    "pyasn1==0.6.4",
]


def _normalize_token(payload: dict) -> dict:
    out = dict(payload)
    if not out.get("type"):
        out["type"] = "authorized_user"
    return out


def install_deps() -> bool:
    missing = []
    from importlib.metadata import version as dist_version

    for spec in REQUIRED_PACKAGES:
        name, _, wanted = spec.partition("==")
        try:
            if dist_version(name) != wanted:
                missing.append(spec)
        except Exception:
            missing.append(spec)
    if not missing:
        print("Dependencies already installed.")
        return True

    print("Installing Google API dependencies...")
    uv = shutil.which("uv")
    try:
        if uv:
            subprocess.check_call(
                [uv, "pip", "install", "--python", sys.executable, "--quiet", *missing]
            )
        else:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "--quiet", *missing]
            )
    except subprocess.CalledProcessError as exc:
        print(f"ERROR: dependency install failed: {exc}")
        return False
    print("Dependencies installed.")
    return True


def sync_profiles() -> None:
    """Point Inbox + Chronos HERMES_HOME at the shared personal token/secret."""
    if not CLIENT_SECRET_PATH.exists():
        print(f"ERROR: missing client secret at {CLIENT_SECRET_PATH}")
        sys.exit(1)

    for bot in CONSUMER_PROFILES:
        home = Path.home() / ".hermes" / "profiles" / bot
        home.mkdir(parents=True, exist_ok=True)
        for src_name in ("google_client_secret.json", "google_token.json"):
            src = HERMES_ROOT / src_name
            dst = home / src_name
            if not src.exists():
                if src_name == "google_token.json":
                    continue
                print(f"ERROR: missing {src}")
                sys.exit(1)
            if dst.is_symlink() or dst.exists():
                dst.unlink()
            dst.symlink_to(src)
            print(f"OK: {dst} -> {src}")
    print("Profiles synced (email_reader, calendar_manager).")


def check_auth() -> bool:
    if not TOKEN_PATH.exists():
        print(f"NOT_AUTHENTICATED: No token at {TOKEN_PATH}")
        return False
    if not install_deps():
        return False
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    try:
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH))
    except Exception as exc:
        print(f"TOKEN_CORRUPT: {exc}")
        return False

    if creds.valid:
        print(f"AUTHENTICATED: Token valid at {TOKEN_PATH}")
        return True
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            TOKEN_PATH.write_text(
                json.dumps(_normalize_token(json.loads(creds.to_json())), indent=2),
                encoding="utf-8",
            )
            print(f"AUTHENTICATED: Token refreshed at {TOKEN_PATH}")
            return True
        except Exception as exc:
            print(f"REFRESH_FAILED: {exc}")
            return False
    print("TOKEN_INVALID: Re-run --auth-url / --auth-code.")
    return False


def auth_url() -> None:
    if not CLIENT_SECRET_PATH.exists():
        print(f"ERROR: No client secret at {CLIENT_SECRET_PATH}")
        sys.exit(1)
    if not install_deps():
        sys.exit(1)
    from google_auth_oauthlib.flow import Flow

    flow = Flow.from_client_secrets_file(
        str(CLIENT_SECRET_PATH),
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
        autogenerate_code_verifier=True,
    )
    url, state = flow.authorization_url(access_type="offline", prompt="consent")
    PENDING_PATH.write_text(
        json.dumps(
            {
                "state": state,
                "code_verifier": flow.code_verifier,
                "redirect_uri": REDIRECT_URI,
                "scopes": SCOPES,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    LAST_URL_PATH.write_text(url + "\n", encoding="utf-8")
    print(url)


def auth_code(code_or_url: str) -> None:
    if not CLIENT_SECRET_PATH.exists():
        print(f"ERROR: No client secret at {CLIENT_SECRET_PATH}")
        sys.exit(1)
    if not PENDING_PATH.exists():
        print("ERROR: No pending personal OAuth session. Run --auth-url first.")
        sys.exit(1)
    if not install_deps():
        sys.exit(1)

    pending = json.loads(PENDING_PATH.read_text(encoding="utf-8"))
    from urllib.parse import parse_qs, urlparse

    from google_auth_oauthlib.flow import Flow

    raw = code_or_url.strip()
    code = raw
    returned_state = None
    granted = list(pending.get("scopes") or SCOPES)
    if raw.startswith("http"):
        params = parse_qs(urlparse(raw).query)
        if "code" not in params:
            print("ERROR: No 'code' parameter found in URL.")
            sys.exit(1)
        code = params["code"][0]
        returned_state = (params.get("state") or [None])[0]
        scope_val = (params.get("scope") or [""])[0].strip()
        if scope_val:
            granted = scope_val.split()

    if returned_state and returned_state != pending.get("state"):
        print("ERROR: OAuth state mismatch. Run --auth-url again.")
        sys.exit(1)

    flow = Flow.from_client_secrets_file(
        str(CLIENT_SECRET_PATH),
        scopes=granted,
        redirect_uri=pending.get("redirect_uri", REDIRECT_URI),
        state=pending["state"],
        code_verifier=pending["code_verifier"],
    )
    os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"
    try:
        flow.fetch_token(code=code)
    except Exception as exc:
        print(f"ERROR: Token exchange failed: {exc}")
        print("The code may have expired. Run --auth-url for a fresh URL.")
        sys.exit(1)

    creds = flow.credentials
    payload = _normalize_token(json.loads(creds.to_json()))
    actually = list(getattr(creds, "granted_scopes", None) or []) or granted
    # Hard strip send if Google ever returns it.
    blocked = {
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/gmail.compose",
    }
    payload["scopes"] = [s for s in actually if s not in blocked]
    TOKEN_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    PENDING_PATH.unlink(missing_ok=True)
    print(f"OK: Authenticated. Token saved to {TOKEN_PATH}")
    print(f"Scopes: {', '.join(payload['scopes'])}")
    sync_profiles()


def main() -> None:
    parser = argparse.ArgumentParser(description="Carrier personal Gmail+Calendar OAuth")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true")
    group.add_argument("--auth-url", action="store_true")
    group.add_argument("--auth-code", metavar="CODE")
    group.add_argument("--install-deps", action="store_true")
    group.add_argument("--sync-profiles", action="store_true")
    args = parser.parse_args()

    if args.install_deps:
        sys.exit(0 if install_deps() else 1)
    if args.sync_profiles:
        sync_profiles()
        return
    if args.check:
        sys.exit(0 if check_auth() else 1)
    if args.auth_url:
        auth_url()
        return
    if args.auth_code:
        auth_code(args.auth_code)
        return


if __name__ == "__main__":
    main()
