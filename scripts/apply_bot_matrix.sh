#!/usr/bin/env bash
# Apply BOT_MATRIX model pins + toolset disables to each bot home.
set -euo pipefail

# ---------------------------------------------------------------------------
# PITFALL (2026-08-25): a live `hermes --profile <id> serve` process holds that
# bot's config.yaml in memory and writes it back on its own cadence. Pinning a
# model while one is running gets silently CLOBBERED seconds later — pins
# reverted to the global grok-4.5 default and smokes failed with
# "expected claude-sonnet-4-6, got grok-4.5".
#
# Hermes Desktop auto-respawns these serve processes, which is fine: a respawn
# reads the fresh config. We only need them out of the way DURING the write.
# So: stop every roster serve process first, then pin. Do not "fix" this by
# re-running the script — the second run gets clobbered exactly the same way.
# ---------------------------------------------------------------------------
ROSTER_IDS="chief_of_staff subscription_watcher api_watcher lockbox \
coding_lt firstmate hermes_ai_explorer passive_watch ops_lt email_reader \
email_drafter calendar_manager todoist_manager knowledge_lt vault_librarian \
obsidian_archivist research_agent finance_reader"

quiesce_serves() {
  local stopped=0 id pids
  for id in $ROSTER_IDS; do
    pids=$(pgrep -f "profile $id serve" 2>/dev/null || true)
    if [[ -n "$pids" ]]; then
      kill $pids 2>/dev/null || true
      stopped=$((stopped + 1))
    fi
  done
  [[ "$stopped" -gt 0 ]] && sleep 3
  echo "quiesced $stopped serve process(es) before pinning"
}

verify_pin() {
  local id="$1" want="$2" got
  got=$(python3 - "$id" <<'PY'
import sys, yaml, pathlib
p = pathlib.Path.home() / ".hermes/profiles" / sys.argv[1] / "config.yaml"
try:
    print(((yaml.safe_load(p.read_text()) or {}).get("model") or {}).get("default", ""))
except Exception:
    print("")
PY
)
  if [[ "$got" != "$want" ]]; then
    echo "WARN  $id pin drifted: wanted '$want' got '$got' (stale serve process?)" >&2
    return 1
  fi
  return 0
}

quiesce_serves

pin() {
  local id="$1" model="$2" provider="$3" attempt got
  # Quiesce THIS bot's serve immediately before writing. Quiescing once up-front
  # is not enough: Desktop respawns serves mid-run, so a bot pinned late in the
  # script gets clobbered by a process that came back while earlier bots pinned.
  for attempt in 1 2 3; do
    pkill -f "profile $id serve" 2>/dev/null || true
    sleep 1
    hermes -p "$id" config set model "$model" >/dev/null
    hermes -p "$id" config set model.provider "$provider" --force >/dev/null
    got=$(python3 - "$id" <<'PY'
import sys, yaml, pathlib
p = pathlib.Path.home() / ".hermes/profiles" / sys.argv[1] / "config.yaml"
try:
    print(((yaml.safe_load(p.read_text()) or {}).get("model") or {}).get("default", ""))
except Exception:
    print("")
PY
)
    if [[ "$got" == "$model" ]]; then
      echo "pinned $id -> $provider/$model"
      return 0
    fi
  done
  echo "WARN  $id would not hold pin $model (got '$got') after 3 attempts" >&2
  return 0
}

# ---------------------------------------------------------------------------
# FLEET MODEL CHAIN (single source of truth)
#
# Every bot defaults to Grok 4.5 (SuperGrok sub, $0 marginal), then Sonnet 5
# (Claude Max, $0 marginal). Paid OpenRouter models are LAST-RESORT ONLY.
#
# Two paid tails:
#   command  — CoS + Lieutenants. Quality tail (DeepSeek V3 / Gemini 3.7 Flash).
#   cheap    — every other subagent. ~9x cheaper tail; these are high-volume
#              rote workers (watchers, readers, drafters) so the paid tail must
#              be as close to free as possible.
#   nocn     — LockBox only: non-China, never DeepSeek (see LockBox note below).
#
# All tail models are tool-calling verified — a worker that cannot emit a
# tool call exits rc=0 without kanban_complete and the board scores it a crash.
# ---------------------------------------------------------------------------
chain() {
  local id="$1" tier="$2"
  CHAIN_ID="$id" CHAIN_TIER="$tier" python3 - <<'PY'
import os
from pathlib import Path
import yaml

TAILS = {
    "command": [
        {"provider": "openrouter", "model": "deepseek/deepseek-chat-v3-0324"},
        {"provider": "openrouter", "model": "google/gemini-3.7-flash"},
    ],
    "cheap": [
        {"provider": "openrouter", "model": "deepseek/deepseek-v4-flash-0731"},
        {"provider": "openrouter", "model": "google/gemini-2.5-flash-lite"},
    ],
    "nocn": [
        {"provider": "openrouter", "model": "openai/gpt-oss-120b"},
        {"provider": "openrouter", "model": "google/gemini-2.5-flash-lite"},
    ],
}

bot = os.environ["CHAIN_ID"]
tier = os.environ["CHAIN_TIER"]
p = Path.home() / ".hermes/profiles" / bot / "config.yaml"
cfg = (yaml.safe_load(p.read_text()) if p.exists() else {}) or {}

m = cfg.setdefault("model", {})
m["default"] = "grok-4.5"
m["provider"] = "xai-oauth"
# Legacy single-fallback key shadows the list form — must not survive.
m.pop("fallback", None)
cfg.pop("fallback_model", None)

cfg["fallback_providers"] = [
    {"provider": "anthropic", "model": "claude-sonnet-5"},
] + [dict(x) for x in TAILS[tier]]

p.parent.mkdir(parents=True, exist_ok=True)
p.write_text(yaml.safe_dump(cfg, sort_keys=False, default_flow_style=False))
print(f"chain {bot} -> grok-4.5 > sonnet-5 > {tier} tail")
PY
}

off() {
  local id="$1"; shift
  hermes -p "$id" tools disable "$@" >/dev/null || true
}

mcp_off() {
  local id="$1"; shift
  for srv in "$@"; do
    hermes -p "$id" config set "mcp_servers.${srv}.enabled" false --force >/dev/null || true
  done
}

# Command — Helm is SUPER-AGENT (near-user perms). Never free tier.
# Do NOT strip tools/MCP here — Helm needs full hermes-cli surface.
pin chief_of_staff grok-4.5 xai-oauth
hermes -p chief_of_staff tools enable web browser terminal file code_execution vision image_gen x_search tts skills todo memory session_search clarify delegation cronjob computer_use --platform cli >/dev/null || true
# Prefer hermes-cli meta bundle if present
python3 - <<'PY'
from pathlib import Path
import yaml, copy
default = yaml.safe_load((Path.home()/".hermes/config.yaml").read_text()) or {}
p = Path.home() / ".hermes/profiles/chief_of_staff/config.yaml"
cfg = yaml.safe_load(p.read_text()) or {}
m = cfg.setdefault("model", {})
m["default"] = "grok-4.5"
m["provider"] = "xai-oauth"
m.pop("fallback", None)
cfg.pop("fallback_model", None)
bu = str(m.get("base_url") or "")
if "opencode" in bu or ":free" in bu or bu.strip() == "":
    m.pop("base_url", None)
# Helm keeps the QUALITY paid tail (command tier) — it coordinates the fleet.
cfg["fallback_providers"] = [
    {"provider": "anthropic", "model": "claude-sonnet-5"},
    {"provider": "openrouter", "model": "deepseek/deepseek-chat-v3-0324"},
    {"provider": "openrouter", "model": "google/gemini-3.7-flash"},
]
# Keep the alias map aligned with the live chain so `smart`/`quality`/`cheap`
# don't silently route to retired pins.
aliases = m.get("aliases")
if isinstance(aliases, dict):
    aliases.update({
        "smart": "xai-oauth/grok-4.5",
        "chief-of-staff": "xai-oauth/grok-4.5",
        "quality": "anthropic/claude-sonnet-5",
        "specialist": "openrouter/deepseek/deepseek-v4-flash-0731",
        "rote": "openrouter/deepseek/deepseek-v4-flash-0731",
        "cheap": "openrouter/deepseek/deepseek-v4-flash-0731",
        "watcher-summary": "openrouter/deepseek/deepseek-v4-flash-0731",
        "specialist-coding": "anthropic/claude-sonnet-5",
        "gemini-flash": "openrouter/google/gemini-2.5-flash-lite",
        "fallback-flash": "openrouter/google/gemini-2.5-flash-lite",
    })
# Super-agent tool surface
cfg["platform_toolsets"] = {"cli": ["hermes-cli"]}
# MCP: mirror default useful servers; Helm gets FULL OSB including write tools
mcp = copy.deepcopy(default.get("mcp_servers") or {})
osb = mcp.get("obsidian-second-brain") or {}
if osb:
    osb = copy.deepcopy(osb)
    osb["enabled"] = True
    # Strip vault-write excludes so Helm can save/capture/update like Michael
    tools = osb.get("tools") or {}
    if isinstance(tools, dict) and tools.get("exclude"):
        write_tools = {
            "obsidian_save_note",
            "obsidian_capture",
            "obsidian_update_note",
            "save_note",
            "capture",
            "update_note",
        }
        tools["exclude"] = [x for x in tools["exclude"] if x not in write_tools]
        if not tools["exclude"]:
            tools.pop("exclude", None)
        if tools:
            osb["tools"] = tools
        else:
            osb.pop("tools", None)
    mcp["obsidian-second-brain"] = osb
for name in ("todoist", "hugging_face", "kiwi", "vercel"):
    if name in mcp:
        mcp[name]["enabled"] = True
if "dropbox" in mcp:
    mcp["dropbox"]["enabled"] = False
cfg["mcp_servers"] = mcp
p.write_text(yaml.safe_dump(cfg, sort_keys=False, default_flow_style=False))
print("chief_of_staff SUPER-AGENT locked (full tools + OSB writes, no free model)")
PY
# No off/mcp_off for Helm — specialists stay constrained below.

pin subscription_watcher grok-4.5 xai-oauth
chain subscription_watcher cheap
off subscription_watcher browser computer_use image_gen video video_gen x_search tts web delegation code_execution vision
mcp_off subscription_watcher todoist hugging_face kiwi vercel dropbox obsidian-second-brain

pin api_watcher grok-4.5 xai-oauth
chain api_watcher cheap
off api_watcher browser computer_use image_gen video video_gen x_search tts web delegation code_execution vision
mcp_off api_watcher todoist hugging_face kiwi vercel dropbox obsidian-second-brain

# LockBox — non-China only; never DeepSeek (nocn tail: gpt-oss-120b / gemini-lite)
pin lockbox grok-4.5 xai-oauth
chain lockbox nocn
off lockbox browser computer_use image_gen video video_gen x_search tts web delegation code_execution vision cronjob
mcp_off lockbox todoist hugging_face kiwi vercel dropbox obsidian-second-brain

# ---------------------------------------------------------------------------
# Lieutenants (Wing Leads) — dispatch / review / routing ONLY.
# Advanced model (Grok 4.5 > Sonnet 5, both $0 marginal on subs) because they
# coordinate; they must NEVER hold execution tools. Lts keep the QUALITY paid
# tail (command tier); sub-specialists drop to the ~9x cheaper tail. Stripping
# these tools is the whole point of the layer — unlike Helm (SUPER-USER), Lts
# are deliberately constrained.
# ---------------------------------------------------------------------------
LT_EXEC_OFF="terminal code_execution browser computer_use delegation web \
image_gen video video_gen tts x_search vision cronjob"

# Wrench 🔧 — Coding Wing lead over Mate
pin coding_lt grok-4.5 xai-oauth
chain coding_lt command
off coding_lt $LT_EXEC_OFF
mcp_off coding_lt todoist hugging_face kiwi vercel dropbox obsidian-second-brain

# Deck 🗂️ — Ops Wing lead over Inbox, Quill, Chronos, Tasker, Purse
pin ops_lt grok-4.5 xai-oauth
chain ops_lt command
off ops_lt $LT_EXEC_OFF
mcp_off ops_lt todoist hugging_face kiwi vercel dropbox obsidian-second-brain

# Stacks 📚 — Knowledge Wing lead over Librarian, Clerk.
# Keeps OSB but READ-ONLY: write tools stay excluded (intake is Clerk's, gated).
pin knowledge_lt grok-4.5 xai-oauth
chain knowledge_lt command
off knowledge_lt $LT_EXEC_OFF
mcp_off knowledge_lt todoist hugging_face kiwi vercel dropbox
python3 - <<'PY'
from pathlib import Path
import yaml, copy
default = yaml.safe_load((Path.home() / ".hermes/config.yaml").read_text()) or {}
p = Path.home() / ".hermes/profiles/knowledge_lt/config.yaml"
cfg = yaml.safe_load(p.read_text()) if p.exists() else {}
cfg = cfg or {}
mcp = cfg.get("mcp_servers") or {}
osb = copy.deepcopy((default.get("mcp_servers") or {}).get("obsidian-second-brain") or {})
if osb:
    osb["enabled"] = True
    tools = osb.get("tools") or {}
    excl = set(tools.get("exclude") or [])
    # Stacks is a routing node: vault WRITE stays with Clerk under grant.
    excl |= {
        "obsidian_save_note", "obsidian_capture", "obsidian_update_note",
        "save_note", "capture", "update_note",
    }
    tools["exclude"] = sorted(excl)
    osb["tools"] = tools
    mcp["obsidian-second-brain"] = osb
    cfg["mcp_servers"] = mcp
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(cfg, sort_keys=False, default_flow_style=False))
    print("knowledge_lt OSB read-only (write tools excluded)")
else:
    print("knowledge_lt: no OSB server in default config — skipped")
PY

# Coding / meta
pin firstmate grok-4.5 xai-oauth
chain firstmate cheap
off firstmate tts video video_gen image_gen
mcp_off firstmate todoist kiwi dropbox

pin hermes_ai_explorer grok-4.5 xai-oauth
chain hermes_ai_explorer cheap
off hermes_ai_explorer computer_use image_gen video video_gen tts delegation
mcp_off hermes_ai_explorer todoist kiwi vercel

# Recon Wing: Sonar — passive signal watcher; LLM pass on diff only
pin passive_watch grok-4.5 xai-oauth
chain passive_watch cheap
off passive_watch browser computer_use image_gen video video_gen x_search tts web delegation code_execution vision cronjob
mcp_off passive_watch todoist hugging_face kiwi vercel dropbox obsidian-second-brain

# Ops
pin email_reader grok-4.5 xai-oauth
chain email_reader cheap
off email_reader browser computer_use image_gen video video_gen x_search tts web delegation cronjob terminal code_execution vision
mcp_off email_reader todoist hugging_face kiwi vercel dropbox obsidian-second-brain

pin email_drafter grok-4.5 xai-oauth
chain email_drafter cheap
off email_drafter browser computer_use image_gen video video_gen x_search tts web delegation cronjob terminal code_execution
mcp_off email_drafter todoist hugging_face kiwi vercel dropbox

pin calendar_manager grok-4.5 xai-oauth
chain calendar_manager cheap
off calendar_manager browser computer_use image_gen video video_gen x_search tts web delegation cronjob terminal code_execution vision
mcp_off calendar_manager todoist hugging_face kiwi vercel dropbox obsidian-second-brain

pin todoist_manager grok-4.5 xai-oauth
chain todoist_manager cheap
off todoist_manager browser computer_use image_gen video video_gen x_search tts web delegation cronjob terminal code_execution vision
mcp_off todoist_manager hugging_face kiwi vercel dropbox obsidian-second-brain

pin finance_reader grok-4.5 xai-oauth
chain finance_reader cheap
off finance_reader browser computer_use image_gen video video_gen x_search tts web delegation cronjob code_execution
mcp_off finance_reader todoist hugging_face kiwi vercel dropbox obsidian-second-brain

# Knowledge / research
pin vault_librarian grok-4.5 xai-oauth
chain vault_librarian cheap
off vault_librarian browser computer_use image_gen video video_gen tts delegation cronjob terminal code_execution
mcp_off vault_librarian todoist hugging_face kiwi vercel dropbox

pin obsidian_archivist grok-4.5 xai-oauth
chain obsidian_archivist cheap
off obsidian_archivist browser computer_use image_gen video video_gen tts delegation cronjob terminal code_execution
mcp_off obsidian_archivist todoist hugging_face kiwi vercel dropbox

pin research_agent grok-4.5 xai-oauth
chain research_agent cheap
off research_agent computer_use image_gen video video_gen tts delegation cronjob terminal
mcp_off research_agent todoist hugging_face kiwi vercel dropbox

echo "BOT_MATRIX applied"

# ---------------------------------------------------------------------------
# Verify every pin actually stuck. A live serve process can clobber a write,
# so never trust the "pinned ..." lines alone — read the files back.
# ---------------------------------------------------------------------------
drift=0
verify_pin chief_of_staff       grok-4.6                          || drift=1
verify_pin subscription_watcher deepseek/deepseek-chat-v3-0324    || drift=1
verify_pin api_watcher          deepseek/deepseek-chat-v3-0324    || drift=1
verify_pin lockbox              google/gemini-2.5-flash           || drift=1
verify_pin coding_lt            claude-sonnet-4-6                 || drift=1
verify_pin ops_lt               claude-sonnet-4-6                 || drift=1
verify_pin knowledge_lt         claude-sonnet-4-6                 || drift=1
verify_pin firstmate            claude-sonnet-4-6                 || drift=1
verify_pin hermes_ai_explorer   claude-sonnet-4-6                 || drift=1
verify_pin passive_watch        deepseek/deepseek-chat-v3-0324    || drift=1
verify_pin email_reader         deepseek/deepseek-chat-v3-0324    || drift=1
verify_pin email_drafter        claude-sonnet-4-6                 || drift=1
verify_pin calendar_manager     deepseek/deepseek-chat-v3-0324    || drift=1
verify_pin todoist_manager      deepseek/deepseek-chat-v3-0324    || drift=1
verify_pin finance_reader       claude-sonnet-4-6                 || drift=1
verify_pin vault_librarian      claude-sonnet-4-6                 || drift=1
verify_pin obsidian_archivist   claude-sonnet-4-6                 || drift=1
verify_pin research_agent       claude-sonnet-4-6                 || drift=1

if [[ "$drift" -ne 0 ]]; then
  echo "FAIL: one or more pins drifted — check for live 'serve' processes." >&2
  exit 1
fi
echo "all 18 pins verified on disk"
