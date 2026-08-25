#!/usr/bin/env python3
"""
bot_identities.py — single source of truth for every bot's Discord identity.

Imported by fleet_signal.sh (via python3), alert_signal.sh, and wire_wing_tokens.sh.
Every bot has:
  - callsign:     display name used in Discord username override
  - emoji:        mark appended to callsign (appears in username field)
  - wing_token_env: which env var holds this wing's Discord bot token
  - color:        embed color (decimal) for rich embeds
  - avatar_url:   optional — Discord CDN or external URL for per-message avatar

Wing token env vars (set by wire_wing_tokens.sh):
  CODING_WING_DISCORD_TOKEN    — coding_lt, firstmate
  OPS_WING_DISCORD_TOKEN       — ops_lt, email_reader, email_drafter,
                                  calendar_manager, todoist_manager, finance_reader
  KNOWLEDGE_WING_DISCORD_TOKEN — knowledge_lt, vault_librarian, obsidian_archivist
  RECON_WING_DISCORD_TOKEN     — hermes_ai_explorer, passive_watch, research_agent
  DISCORD_FLEET_BOT_TOKEN      — command tier: chief_of_staff (outbound fallback only),
                                  subscription_watcher, api_watcher, lockbox

Note: chief_of_staff uses DISCORD_BOT_TOKEN (Carrier Ops) for its gateway.
      For REST SENDS from Helm on behalf of the fleet, DISCORD_FLEET_BOT_TOKEN is used.
"""

# Bot identity registry
BOTS = {
    # ── Command tier ────────────────────────────────────────────────────────
    "chief_of_staff": {
        "callsign": "Helm",
        "emoji": "⚓",
        "wing_token_env": "DISCORD_BOT_TOKEN",          # Carrier Ops — gateway token
        "color": 0x1a3a5c,                              # navy blue
        "avatar_url": None,
    },
    "subscription_watcher": {
        "callsign": "Vigil",
        "emoji": "📡",
        "wing_token_env": "DISCORD_FLEET_BOT_TOKEN",    # First Watch (command tier shares)
        "color": 0xff8800,                              # amber — watch / alert
        "avatar_url": None,
    },
    "api_watcher": {
        "callsign": "Ledger",
        "emoji": "💵",
        "wing_token_env": "DISCORD_FLEET_BOT_TOKEN",
        "color": 0x00cc44,                              # green — spend / money
        "avatar_url": None,
    },
    "lockbox": {
        "callsign": "LockBox",
        "emoji": "🔒",
        "wing_token_env": "DISCORD_FLEET_BOT_TOKEN",
        "color": 0xcc0000,                              # red — secrets / security
        "avatar_url": None,
    },

    # ── Coding Wing ─────────────────────────────────────────────────────────
    "coding_lt": {
        "callsign": "Wrench",
        "emoji": "🔧",
        "wing_token_env": "CODING_WING_DISCORD_TOKEN",
        "color": 0x5865f2,                              # Discord blurple — coding
        "avatar_url": None,
    },
    "firstmate": {
        "callsign": "Mate",
        "emoji": "⚙️",
        "wing_token_env": "CODING_WING_DISCORD_TOKEN",
        "color": 0x7289da,                              # softer blurple — crew
        "avatar_url": None,
    },

    # ── Ops Wing ────────────────────────────────────────────────────────────
    "ops_lt": {
        "callsign": "Deck",
        "emoji": "🗂️",
        "wing_token_env": "OPS_WING_DISCORD_TOKEN",
        "color": 0xf0a500,                              # gold — operations
        "avatar_url": None,
    },
    "email_reader": {
        "callsign": "Inbox",
        "emoji": "📬",
        "wing_token_env": "OPS_WING_DISCORD_TOKEN",
        "color": 0xe8d5b7,                              # parchment — mail
        "avatar_url": None,
    },
    "email_drafter": {
        "callsign": "Quill",
        "emoji": "🪶",
        "wing_token_env": "OPS_WING_DISCORD_TOKEN",
        "color": 0xd4af37,                              # gold — drafting
        "avatar_url": None,
    },
    "calendar_manager": {
        "callsign": "Chronos",
        "emoji": "🕰️",
        "wing_token_env": "OPS_WING_DISCORD_TOKEN",
        "color": 0x3498db,                              # sky blue — time
        "avatar_url": None,
    },
    "todoist_manager": {
        "callsign": "Tasker",
        "emoji": "📋",
        "wing_token_env": "OPS_WING_DISCORD_TOKEN",
        "color": 0xe44232,                              # Todoist red — tasks
        "avatar_url": None,
    },
    "finance_reader": {
        "callsign": "Purse",
        "emoji": "👛",
        "wing_token_env": "OPS_WING_DISCORD_TOKEN",
        "color": 0x2ecc71,                              # emerald — finance
        "avatar_url": None,
    },

    # ── Knowledge Wing ───────────────────────────────────────────────────────
    "knowledge_lt": {
        "callsign": "Stacks",
        "emoji": "📚",
        "wing_token_env": "KNOWLEDGE_WING_DISCORD_TOKEN",
        "color": 0x8e44ad,                              # purple — knowledge
        "avatar_url": None,
    },
    "vault_librarian": {
        "callsign": "Librarian",
        "emoji": "📖",
        "wing_token_env": "KNOWLEDGE_WING_DISCORD_TOKEN",
        "color": 0xa569bd,                              # lilac — vault query
        "avatar_url": None,
    },
    "obsidian_archivist": {
        "callsign": "Clerk",
        "emoji": "📥",
        "wing_token_env": "KNOWLEDGE_WING_DISCORD_TOKEN",
        "color": 0x6c3483,                              # deep purple — intake
        "avatar_url": None,
    },

    # ── Recon Wing ───────────────────────────────────────────────────────────
    "hermes_ai_explorer": {
        "callsign": "Chart",
        "emoji": "🗺️",
        "wing_token_env": "RECON_WING_DISCORD_TOKEN",
        "color": 0x1abc9c,                              # teal — synthesis
        "avatar_url": None,
    },
    "passive_watch": {
        "callsign": "Sonar",
        "emoji": "🔊",
        "wing_token_env": "RECON_WING_DISCORD_TOKEN",
        "color": 0x16a085,                              # dark teal — passive watch
        "avatar_url": None,
    },
    "research_agent": {
        "callsign": "Probe",
        "emoji": "🔍",
        "wing_token_env": "RECON_WING_DISCORD_TOKEN",
        "color": 0x27ae60,                              # green — research
        "avatar_url": None,
    },
}

# Channel registry
CHANNELS = {
    # Core command/fleet channels
    "command":    "1541866378255011980",
    "fleet":      "1541866443765977138",
    "alerts":     "1541866423427801148",
    "drafts":     "1541866401432871002",
    "ready_room": "1541919952599130132",
    "catapult":   "1541919999894229053",
    # Wing home channels (internal coordination)
    "quarterdeck": "1541929900586565783",   # Ops Wing home
    "chart_room":  "1541929921176281170",   # Knowledge Wing home
    # Domain specialist channels
    "email":      "1541155152726204416",
    "calendar":   "1541155189019517078",
    "tasks":      "1541155241746239658",
    "vault":      "1541155274528915577",
    "finance":    "1541155307860795503",
    "audit":      "1541155342833025114",
    "urgent":     "1541155373371621507",
    "general":    "1541154516811120762",
}

# Wing membership (for wire_wing_tokens.sh)
WINGS = {
    "CODING_WING_DISCORD_TOKEN":    ["coding_lt", "firstmate"],
    "OPS_WING_DISCORD_TOKEN":       ["ops_lt", "email_reader", "email_drafter",
                                     "calendar_manager", "todoist_manager", "finance_reader"],
    "KNOWLEDGE_WING_DISCORD_TOKEN": ["knowledge_lt", "vault_librarian", "obsidian_archivist"],
    "RECON_WING_DISCORD_TOKEN":     ["hermes_ai_explorer", "passive_watch", "research_agent"],
    "DISCORD_FLEET_BOT_TOKEN":      ["subscription_watcher", "api_watcher", "lockbox"],
}

# Michael's Discord user ID — the ONLY user permitted to trigger agent turns
MICHAEL_DISCORD_ID = "174349224870150144"

if __name__ == "__main__":
    import json, sys
    if len(sys.argv) == 2:
        bot_id = sys.argv[1]
        if bot_id in BOTS:
            print(json.dumps(BOTS[bot_id]))
        else:
            print(json.dumps({"error": f"unknown bot_id: {bot_id}"}), file=sys.stderr)
            sys.exit(1)
    else:
        print(json.dumps({"bots": list(BOTS.keys()), "channels": CHANNELS, "wings": {k: v for k, v in WINGS.items()}}))
