# Integration Session Summary — Aug 26 2026

This branch tracks the full-session integration PR. All code is already on main or in open PRs #5-#14.

## What was shipped directly to main
- carrier-peers broker + client (peer discovery)
- carrier-viking + carrier-peers enabled fleet-wide (25 profiles)
- OB1 brain wired to runtime + startup scripts
- VM fleet docker files + carrier_vm_manager.py
- Self-healing gateway: watchdog, clean startup, stale lock fix (ZERO LLM)
- Billing policy: cron OR rules, fleet_checkin.py zero-cost rewrite
- Model name fix: claude-sonnet-5-20251001 → claude-sonnet-4-6 (19 bot configs)
- PRC/DeepSeek restriction removed
- agent-browser skill

## Open PRs (pending review before merge)
- PR #5: carrier-peers broker worktree
- PR #7: carrier-viking full (Option B stdlib)
- PR #8: OB1 brain (SQLite fallback)
- PR #9: OpenMausBot architecture patterns + specs
- PR #10: OpenMausBot implementation (approval gate, webhook, VM scaffold)
- PR #11: Full OpenViking server + all P1-P7 gap fixes
- PR #12: OpenMausBot deep (approval gate, full VM fleet, driver SPI)
- PR #13: OB1 full Supabase + SQLite fallback
- PR #14: Qwen local fix + cost watchdog

## Gateway failsafe (on main, ZERO LLM verified)
carrier_gateway_watchdog.py: psutil + file I/O only. No model calls ever.
start_gateway.ps1: env var scrub + hermes CLI. No model calls.
Hermes cron 69479f6f787b: no_agent=True, every 5 min.
