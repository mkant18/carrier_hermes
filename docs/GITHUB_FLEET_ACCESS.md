# GITHUB FLEET ACCESS — Runbook

**Author:** Alpha (Mission Bravo)  
**Status:** ACTIVE  
**Last updated:** 2026-08-25

---

## 1. Current Auth Audit (2026-08-25)

| Surface | Status | Method | Token env | Notes |
|---------|--------|--------|-----------|-------|
| default profile | ✅ LOGGED IN | `gh` + macOS Keyring | NOT set in env | `mkant18`, scopes `gist,read:org,repo,workflow` |
| firstmate profile | ✅ INHERITS | Same Mac user → same Keyring | NOT set in env | Subagent → inherits via macOS Keyring on dispatch |
| `carrier_hermes` remote | ✅ PUSH WORKS | HTTPS + `osxkeychain` | — | `git push origin main --dry-run` → "Everything up-to-date" |
| CI/CD | ⚠️ NOT WIRED | — | — | GitHub Actions secrets needed per repo if CI added |
| GITHUB_TOKEN in env | ❌ NOT SET | — | — | Correct — tokens live in Keyring, not env |

---

## 2. Recommended Architecture

### 2a. Human Machine + Local Subagents (Current Setup — Use This)

```
mkant18 @ Mac
└── gh CLI → macOS Keyring → github.com (HTTPS, PAT stored)
    ├── default profile (Helm)       → inherits Keyring ✅
    ├── firstmate profile (Mate)     → inherits Keyring ✅ (same OS user)
    └── all other bots on same Mac   → inherits Keyring ✅
```

**Why this works:** All Hermes profiles run as the same macOS user, so `git credential-osxkeychain` serves any process forked from the same user session. No token injection needed for local bots.

**What NOT to do:**
- ❌ Never put `GITHUB_TOKEN=...` in `.env`, Discord messages, or job packets
- ❌ Never commit tokens to any repo, even private
- ❌ Never let Helm hold GH tokens in memory across sessions (LockBox path for ephemeral grants)

---

### 2b. Isolated Bots / CI — Fine-Grained PAT via LockBox (Recommended Next Step)

For bots that run in isolated environments (Docker, remote machines, GitHub Actions), use a **fine-grained PAT** with least-privilege:

```
Scope needed for most coding work:
  - Contents: Read & Write (for branches + pushes)
  - Pull Requests: Read & Write (for PR creation)
  - Metadata: Read (always required)
  - Workflows: Read & Write (only if touching .github/workflows)

Expiry: 90 days max, rotated via Doppler
```

**Storage flow (LockBox path):**
```
Michael creates PAT in GitHub UI
  → Stores in Doppler: project=carrier-ops, secret=GITHUB_FIRSTMATE_PAT
  → Helm signs LockBox grant: audience=firstmate, secret=GITHUB_FIRSTMATE_PAT, ttl=1h
  → Mate redeems via lockbox_redeem_live.sh → gets token in-process
  → Token used for git operation → discarded (never written to disk)
```

See: `scripts/lockbox_redeem_live.sh` for the redeem side.

---

### 2c. GitHub App — Preferred for Fleet Scale (Future)

When the fleet grows beyond a single Mac or needs CI-level access across many repos:

| Factor | Fine-Grained PAT | GitHub App |
|--------|-----------------|------------|
| Scope granularity | Repo-level | Repo or org-level |
| Expiry | Max 1 year | Installation token: 1 hour |
| Rotation | Manual | Automatic (JWT → installation token) |
| Multi-bot | One PAT per bot (messy) | One App, N installation tokens |
| Audit trail | Per-token | Per-App-installation (cleaner) |
| **Recommendation** | ✅ Use now (single Mac) | ✅ Migrate when fleet grows |

**GitHub App setup (when ready):**
1. Create App at github.com/settings/apps → name `carrier-hermes-fleet`
2. Grant: Contents RW, Pull Requests RW, Metadata R, Workflows RW
3. Install to `mkant18` account
4. Store App ID + private key in Doppler `carrier-ops`
5. Bots get installation tokens (1h) via LockBox grant at dispatch time

---

## 3. FirstMate Credential Inheritance

Mate's `SOUL.md` lists `terminal, file, git` as tools. When dispatched as a subagent on this Mac:

- `git` operations use HTTPS + `osxkeychain` → **just works**, same as user session
- `gh` CLI: Mate can run `gh` commands that read the user's `gh` auth state since keyring is per-OS-user
- **No additional wiring needed for local fleet operation**

If Mate is ever dispatched to a remote environment:
1. Helm signs a LockBox grant for `GITHUB_FIRSTMATE_PAT`
2. Mate runs `scripts/smoke_github_auth.sh` first as a preflight check
3. On failure → Mate must surface `blockers: ["github_auth_missing"]` in return packet

---

## 4. CI Implications (Alpha's Domain)

- GitHub Actions workflows need `GITHUB_TOKEN` (auto-provided by Actions runner) or a repo secret
- If CI calls external agents → store `HERMES_AGENT_TOKEN` in repo Actions secrets
- Discord notifications from CI: use webhook URL stored as Actions secret `DISCORD_WEBHOOK_URL`
- **Do not** hardcode bot tokens in workflow YAML

---

## 5. Smoke Commands

### Quick auth check (run any time):
```bash
bash scripts/smoke_github_auth.sh
```

### Full fleet smoke (includes GitHub check):
```bash
bash scripts/smoke_fleet.sh
```

### Manual verification:
```bash
# Is gh logged in?
gh auth status

# Can we push to carrier_hermes?
cd ~/carrier_hermes && git push origin main --dry-run

# List repos the token can see:
gh repo list mkant18 --limit 10

# Verify no GITHUB_TOKEN in env (should print "Length: 0"):
echo "GITHUB_TOKEN length: ${#GITHUB_TOKEN}"
```

---

## 6. Next Human Steps

These require Michael's action:

| Priority | Action | Why |
|----------|--------|-----|
| **Optional / now** | Create fine-grained PAT for Mate | Needed if Mate ever runs outside this Mac (remote, CI, Docker) |
| **Optional / now** | Add PAT to Doppler `carrier-ops` as `GITHUB_FIRSTMATE_PAT` | Enables LockBox path for ephemeral credential grants |
| **When scaling** | Create `carrier-hermes-fleet` GitHub App | Cleaner multi-bot auth with auto-rotating tokens |
| **If adding CI** | Add `DISCORD_WEBHOOK_URL` to repo Actions secrets | Allows CI to notify Discord on push/PR |

**Fine-grained PAT creation steps:**
1. Go to https://github.com/settings/personal-access-tokens/new
2. Select "Fine-grained, repo-scoped"
3. Repository access: "Only select repositories" → `carrier_hermes` (and any others Mate needs)
4. Permissions: Contents (RW), Pull Requests (RW), Metadata (R)
5. Expiration: 90 days
6. Copy token → `doppler secrets set GITHUB_FIRSTMATE_PAT --project carrier-ops` (or `firstmate-dispatch`)
7. Run `bash scripts/smoke_github_auth.sh` to verify Mate's path

---

## 7. What Mate Should Do at Coding Session Start

In `SOUL.md` / dispatch preamble, Mate should run:

```bash
bash /path/to/carrier_hermes/scripts/smoke_github_auth.sh
```

If `PASS github_auth` → proceed.  
If `FAIL github_auth` → surface blocker, request LockBox grant from Helm.

---

*See also: `scripts/smoke_github_auth.sh`, `scripts/lockbox_redeem_live.sh`, `INTER_AGENT_PROTOCOL.md`*
