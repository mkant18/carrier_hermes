#!/usr/bin/env bash
# smoke_github_auth.sh — GitHub auth smoke check for carrier fleet.
# Prints PASS/FAIL/SKIP per check. Exits 1 if any required check fails.
# Safe: never prints tokens. Reports length/status only.
# Usage: bash scripts/smoke_github_auth.sh [--quiet]
set -euo pipefail

QUIET="${1:-}"
fail=0
pass() { [[ "$QUIET" == "--quiet" ]] || echo "PASS  $1"; }
failc() { echo "FAIL  $1 — $2"; fail=1; }
skip() { [[ "$QUIET" == "--quiet" ]] || echo "SKIP  $1 — $2"; }

echo "=== GitHub auth smoke ==="

# 1. gh CLI present
if ! command -v gh >/dev/null 2>&1; then
  failc "gh_cli_present" "gh not in PATH — install: brew install gh"
else
  pass "gh_cli_present ($(gh --version | head -1))"
fi

# 2. gh logged in
if gh auth status >/tmp/gh_auth_out 2>&1; then
  account=$(grep -o 'account [^ ]*' /tmp/gh_auth_out | head -1 | awk '{print $2}')
  pass "gh_logged_in (account=${account:-unknown})"
else
  failc "gh_logged_in" "run: gh auth login"
fi

# 3. Scopes include 'repo' (needed for push)
if grep -q "'repo'" /tmp/gh_auth_out 2>/dev/null; then
  pass "gh_scope_repo"
else
  failc "gh_scope_repo" "re-auth with repo scope: gh auth refresh -s repo"
fi

# 4. git credential helper configured
cred_helper=$(git config --global credential.helper 2>/dev/null || echo "")
if [[ -n "$cred_helper" ]]; then
  pass "git_credential_helper ($cred_helper)"
else
  skip "git_credential_helper" "not set globally — may still work per-repo"
fi

# 5. No long-lived token in environment (security check)
if [[ -n "${GITHUB_TOKEN:-}" ]]; then
  token_len=${#GITHUB_TOKEN}
  failc "no_env_token" "GITHUB_TOKEN is set in env (length=$token_len) — remove from env; use keyring instead"
else
  pass "no_env_GITHUB_TOKEN"
fi
if [[ -n "${GH_TOKEN:-}" ]]; then
  token_len=${#GH_TOKEN}
  failc "no_env_GH_TOKEN" "GH_TOKEN is set in env (length=$token_len) — remove from env; use keyring instead"
else
  pass "no_env_GH_TOKEN"
fi

# 6. carrier_hermes remote reachable + push dry-run
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [[ -d "$REPO_ROOT/.git" ]]; then
  remote_url=$(git -C "$REPO_ROOT" remote get-url origin 2>/dev/null || echo "")
  if [[ -n "$remote_url" ]]; then
    pass "carrier_hermes_remote ($remote_url)"
    # Push dry-run (only on main; skip on feature branches to avoid noise)
    current_branch=$(git -C "$REPO_ROOT" branch --show-current 2>/dev/null || echo "")
    if [[ "$current_branch" == "main" ]]; then
      if git -C "$REPO_ROOT" push origin main --dry-run >/dev/null 2>&1; then
        pass "push_dry_run (branch=main)"
      else
        failc "push_dry_run" "git push --dry-run failed — check credentials"
      fi
    else
      skip "push_dry_run" "on branch $current_branch, not main — skipping dry-run push"
    fi
  else
    failc "carrier_hermes_remote" "no origin remote configured"
  fi
else
  skip "carrier_hermes_remote" "not run from within carrier_hermes repo"
fi

# 7. API connectivity (rate limit check — no auth scope needed, proves network + token ok)
if gh api rate_limit --jq '.rate.limit' >/dev/null 2>&1; then
  remaining=$(gh api rate_limit --jq '.rate.remaining' 2>/dev/null || echo "?")
  limit=$(gh api rate_limit --jq '.rate.limit' 2>/dev/null || echo "?")
  pass "gh_api_reachable (rate_limit=$remaining/$limit)"
else
  failc "gh_api_reachable" "gh api rate_limit failed — check network or token"
fi

echo "=== done fail=$fail ==="
exit "$fail"
