#!/usr/bin/env python3
"""Pre-5am-restart save & protect. Zero-LLM. Runs daily 04:30 ET via Hermes cron (no_agent).
Saves: OMB state backup + WIP commits in carrier_hermes repo/worktrees.
Loud on failure (nonzero exit -> cron error alert). Silent-ish on success (prints summary)."""
import json, os, shutil, subprocess, sys, datetime

HOME = "C:/Users/micha"
OMB = f"{HOME}/.openmausbot"
BACKUP_ROOT = f"{HOME}/.openmausbot_backups"
REPOS = [f"{HOME}/carrier_hermes", f"{HOME}/worktrees/carrier_openmausbot"]
STAMP = datetime.datetime.now().strftime("%Y%m%d_%H%M")
errors, actions = [], []

# 1) Backup OMB state (config, roster, rooms, decisions, token ledger, buildout reports/briefs)
dest = os.path.join(BACKUP_ROOT, STAMP)
try:
    os.makedirs(dest, exist_ok=True)
    for item in ["bots.json", "config.json", "groups.json", "decisions.ndjson",
                 "ollama_fallback_state.json", "carrier-fleet.mausteam.json"]:
        src = os.path.join(OMB, item)
        if os.path.exists(src):
            shutil.copy2(src, dest)
    for tree in ["buildout", "token_ledger"]:
        src = os.path.join(OMB, tree)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(dest, tree), dirs_exist_ok=True)
    actions.append(f"OMB state backed up -> {dest}")
    # prune backups older than 14 days
    cutoff = datetime.datetime.now() - datetime.timedelta(days=14)
    for d in os.listdir(BACKUP_ROOT):
        p = os.path.join(BACKUP_ROOT, d)
        try:
            if os.path.isdir(p) and datetime.datetime.strptime(d[:8], "%Y%m%d") < cutoff:
                shutil.rmtree(p)
        except Exception:
            pass
except Exception as e:
    errors.append(f"OMB backup failed: {e}")

# 2) WIP-commit any dirty repo/worktree (never amend, never push)
for repo in REPOS:
    if not os.path.isdir(repo):
        continue
    try:
        dirty = subprocess.run(["git", "-C", repo, "status", "--porcelain"],
                               capture_output=True, text=True, timeout=60).stdout.strip()
        if dirty:
            subprocess.run(["git", "-C", repo, "add", "-A", "--", ":!.worktrees"], check=True, timeout=60)
            r = subprocess.run(["git", "-C", repo, "commit", "-m",
                                f"wip(pre-5am-save): auto-save {STAMP} before scheduled restart"],
                               capture_output=True, text=True, timeout=60)
            if r.returncode == 0:
                actions.append(f"WIP committed in {repo}")
            else:
                errors.append(f"commit failed in {repo}: {r.stderr.strip()[:200]}")
        else:
            actions.append(f"clean: {repo}")
    except Exception as e:
        errors.append(f"git save failed in {repo}: {e}")

print("PRE-5AM SAVE @", STAMP)
for a in actions: print(" ✅", a)
for e in errors: print(" 🚨", e)
sys.exit(1 if errors else 0)
