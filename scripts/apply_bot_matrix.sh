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

# Command
pin chief_of_staff grok-4.5 xai-oauth
off chief_of_staff browser computer_use image_gen video video_gen x_search tts web terminal file code_execution vision
mcp_off chief_of_staff todoist hugging_face kiwi vercel dropbox

pin subscription_watcher deepseek/deepseek-chat-v3-0324 openrouter
off subscription_watcher browser computer_use image_gen video video_gen x_search tts web delegation code_execution vision
mcp_off subscription_watcher todoist hugging_face kiwi vercel dropbox obsidian-second-brain

pin api_watcher deepseek/deepseek-chat-v3-0324 openrouter
off api_watcher browser computer_use image_gen video video_gen x_search tts web delegation code_execution vision
mcp_off api_watcher todoist hugging_face kiwi vercel dropbox obsidian-second-brain

# Coding / meta
pin firstmate claude-sonnet-4-6 anthropic
off firstmate tts video video_gen image_gen
mcp_off firstmate todoist kiwi dropbox

pin hermes_ai_explorer claude-sonnet-4-6 anthropic
off hermes_ai_explorer computer_use image_gen video video_gen tts delegation
mcp_off hermes_ai_explorer todoist kiwi vercel

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
