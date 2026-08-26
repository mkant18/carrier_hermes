"""
disable_grok_use_sonnet.py
Temporarily replaces ALL xai-oauth/grok-4.5 slots (primary and fallback)
with anthropic/claude-sonnet-4-6 across every Hermes profile config.

Run with --restore to undo (reads the .bak files).
Run with --dry-run to preview changes without writing.
"""
import yaml
import json
import shutil
import argparse
from pathlib import Path

HOME = Path(r"C:\Users\micha\AppData\Local\hermes")
BACKUP_MANIFEST = HOME / "carrier" / "grok_disable_backup.json"

OLD_PROVIDER = "xai-oauth"
OLD_MODEL    = "grok-4.5"
NEW_PROVIDER = "anthropic"
NEW_MODEL    = "claude-sonnet-4-6"


def get_all_configs():
    cfgs = [HOME / "config.yaml"] + sorted((HOME / "profiles").glob("*/config.yaml"))
    return [p for p in cfgs if p.exists()]


def swap_grok_in_cfg(cfg: dict) -> tuple[dict, list[str]]:
    """Return (modified_cfg, list_of_changes). Mutates cfg in-place."""
    changes = []

    # 1. Primary model
    model_sec = cfg.get("model", {})
    if isinstance(model_sec, dict):
        if model_sec.get("provider") == OLD_PROVIDER and model_sec.get("default") == OLD_MODEL:
            model_sec["provider"] = NEW_PROVIDER
            model_sec["default"]  = NEW_MODEL
            changes.append(f"  primary: {OLD_PROVIDER}/{OLD_MODEL} → {NEW_PROVIDER}/{NEW_MODEL}")

    # 2. Fallback providers
    fallbacks = cfg.get("fallback_providers") or []
    for i, fb in enumerate(fallbacks):
        if isinstance(fb, dict):
            if fb.get("provider") == OLD_PROVIDER and fb.get("model") == OLD_MODEL:
                fb["provider"] = NEW_PROVIDER
                fb["model"]    = NEW_MODEL
                changes.append(f"  fallback[{i}]: {OLD_PROVIDER}/{OLD_MODEL} → {NEW_PROVIDER}/{NEW_MODEL}")

    return cfg, changes


def backup_config(p: Path) -> Path:
    bak = p.with_suffix(".yaml.grok_bak")
    shutil.copy2(p, bak)
    return bak


def restore_backup(p: Path) -> bool:
    bak = p.with_suffix(".yaml.grok_bak")
    if bak.exists():
        shutil.copy2(bak, p)
        bak.unlink()
        return True
    return False


def run(dry_run=False, restore=False):
    cfgs = get_all_configs()
    manifest = {}

    if restore:
        print("=== RESTORING from .grok_bak files ===\n")
        for p in cfgs:
            name = p.parent.name if p.parent.name != "hermes" else "DEFAULT"
            ok = restore_backup(p)
            status = "✅ restored" if ok else "⚠️  no backup found"
            print(f"  {name}: {status}")
        if BACKUP_MANIFEST.exists():
            BACKUP_MANIFEST.unlink()
        print("\nDone. All grok configs restored.")
        return

    print(f"=== DISABLING Grok / Enabling Claude Sonnet {'[DRY RUN]' if dry_run else ''} ===\n")
    total_changes = 0

    for p in cfgs:
        name = p.parent.name if p.parent.name != "hermes" else "DEFAULT"
        raw  = p.read_text(encoding="utf-8")
        cfg  = yaml.safe_load(raw) or {}
        cfg, changes = swap_grok_in_cfg(cfg)

        if changes:
            total_changes += len(changes)
            print(f"--- {name} ---")
            for c in changes:
                print(c)

            if not dry_run:
                bak = backup_config(p)
                manifest[str(p)] = str(bak)
                new_yaml = yaml.safe_dump(cfg, sort_keys=False, default_flow_style=False, allow_unicode=True)
                p.write_text(new_yaml, encoding="utf-8")
        else:
            print(f"--- {name}: no grok references found ---")

    if not dry_run and manifest:
        BACKUP_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
        BACKUP_MANIFEST.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(f"\n✅ Backup manifest: {BACKUP_MANIFEST}")

    print(f"\n{'[DRY RUN] Would have made' if dry_run else 'Made'} {total_changes} substitution(s) across {sum(1 for p in cfgs)} config(s).")
    if not dry_run:
        print("\n⚡ GROK DISABLED — all slots now route through anthropic/claude-sonnet-4-6.")
        print("   Run with --restore to undo.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run",  action="store_true", help="Preview only, no writes")
    ap.add_argument("--restore",  action="store_true", help="Restore from backups")
    args = ap.parse_args()
    run(dry_run=args.dry_run, restore=args.restore)
