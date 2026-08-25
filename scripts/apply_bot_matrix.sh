#!/usr/bin/env bash
# Apply BOT_MATRIX model pins + toolset disables to each bot home.
set -euo pipefail

pin() {
  local id="$1" model="$2" provider="$3"
  hermes -p "$id" config set model "$model" >/dev/null
  hermes -p "$id" config set model.provider "$provider" --force >/dev/null
  echo "pinned $id -> $provider/$model"
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
pin chief_of_staff grok-4.6 xai-oauth
hermes -p chief_of_staff tools enable web browser terminal file code_execution vision image_gen x_search tts skills todo memory session_search clarify delegation cronjob computer_use --platform cli >/dev/null || true
# Prefer hermes-cli meta bundle if present
python3 - <<'PY'
from pathlib import Path
import yaml, copy
default = yaml.safe_load((Path.home()/".hermes/config.yaml").read_text()) or {}
p = Path.home() / ".hermes/profiles/chief_of_staff/config.yaml"
cfg = yaml.safe_load(p.read_text()) or {}
m = cfg.setdefault("model", {})
m["default"] = "grok-4.6"
m["provider"] = "xai-oauth"
bu = str(m.get("base_url") or "")
if "opencode" in bu or ":free" in bu or bu.strip() == "":
    m.pop("base_url", None)
cfg["fallback_providers"] = [
    {"provider": "anthropic", "model": "claude-sonnet-4-6"},
    {"provider": "xai-oauth", "model": "grok-4.5"},
    {"provider": "openrouter", "model": "deepseek/deepseek-chat-v3-0324"},
    {"provider": "openrouter", "model": "google/gemini-3.7-flash"},
]
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

pin subscription_watcher deepseek/deepseek-chat-v3-0324 openrouter
off subscription_watcher browser computer_use image_gen video video_gen x_search tts web delegation code_execution vision
mcp_off subscription_watcher todoist hugging_face kiwi vercel dropbox obsidian-second-brain

pin api_watcher deepseek/deepseek-chat-v3-0324 openrouter
off api_watcher browser computer_use image_gen video video_gen x_search tts web delegation code_execution vision
mcp_off api_watcher todoist hugging_face kiwi vercel dropbox obsidian-second-brain

# LockBox — non-China only; never DeepSeek
pin lockbox google/gemini-2.5-flash openrouter
hermes -p lockbox config set model.fallback "openai/gpt-4o-mini" --force >/dev/null || true
off lockbox browser computer_use image_gen video video_gen x_search tts web delegation code_execution vision cronjob
mcp_off lockbox todoist hugging_face kiwi vercel dropbox obsidian-second-brain

# Coding / meta
pin firstmate claude-sonnet-4-6 anthropic
off firstmate tts video video_gen image_gen
mcp_off firstmate todoist kiwi dropbox

pin hermes_ai_explorer claude-sonnet-4-6 anthropic
off hermes_ai_explorer computer_use image_gen video video_gen tts delegation
mcp_off hermes_ai_explorer todoist kiwi vercel

# Recon Wing: Sonar — passive signal watcher; LLM pass on diff only
pin passive_watch deepseek/deepseek-chat-v3-0324 openrouter
off passive_watch browser computer_use image_gen video video_gen x_search tts web delegation code_execution vision cronjob
mcp_off passive_watch todoist hugging_face kiwi vercel dropbox obsidian-second-brain

# Ops
pin email_reader deepseek/deepseek-chat-v3-0324 openrouter
off email_reader browser computer_use image_gen video video_gen x_search tts web delegation cronjob terminal code_execution vision
mcp_off email_reader todoist hugging_face kiwi vercel dropbox obsidian-second-brain

pin email_drafter claude-sonnet-4-6 anthropic
off email_drafter browser computer_use image_gen video video_gen x_search tts web delegation cronjob terminal code_execution
mcp_off email_drafter todoist hugging_face kiwi vercel dropbox

pin calendar_manager deepseek/deepseek-chat-v3-0324 openrouter
off calendar_manager browser computer_use image_gen video video_gen x_search tts web delegation cronjob terminal code_execution vision
mcp_off calendar_manager todoist hugging_face kiwi vercel dropbox obsidian-second-brain

pin todoist_manager deepseek/deepseek-chat-v3-0324 openrouter
off todoist_manager browser computer_use image_gen video video_gen x_search tts web delegation cronjob terminal code_execution vision
mcp_off todoist_manager hugging_face kiwi vercel dropbox obsidian-second-brain

pin finance_reader claude-sonnet-4-6 anthropic
off finance_reader browser computer_use image_gen video video_gen x_search tts web delegation cronjob code_execution
mcp_off finance_reader todoist hugging_face kiwi vercel dropbox obsidian-second-brain

# Knowledge / research
pin vault_librarian claude-sonnet-4-6 anthropic
off vault_librarian browser computer_use image_gen video video_gen tts delegation cronjob terminal code_execution
mcp_off vault_librarian todoist hugging_face kiwi vercel dropbox

pin obsidian_archivist claude-sonnet-4-6 anthropic
off obsidian_archivist browser computer_use image_gen video video_gen tts delegation cronjob terminal code_execution
mcp_off obsidian_archivist todoist hugging_face kiwi vercel dropbox

pin research_agent claude-sonnet-4-6 anthropic
off research_agent computer_use image_gen video video_gen tts delegation cronjob terminal
mcp_off research_agent todoist hugging_face kiwi vercel dropbox

echo "BOT_MATRIX applied"
