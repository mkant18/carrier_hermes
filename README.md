# carrier_hermes

> Hermes Agent implementation of the Carrier Ops chief-of-staff fleet.

The original [carrier_ops](https://github.com/michaelkanter/carrier_ops) plan described a 5-layer always-on agent stack (OpenClaw → OpenMausBot harness → Podiom → LiteLLM → Obsidian/OB1). This repo re-implements the same fleet using **Hermes Agent as the single runtime**, collapsing those layers while preserving every governance rule, tool scope, agent identity, and model tier from the master plan.

## What maps to what

| carrier_ops layer | Hermes equivalent |
|---|---|
| OpenClaw gateway (Discord/Telegram) | Hermes gateway — `platforms.discord`, `platforms.telegram` in config |
| Podiom durable sessions + scheduler | Hermes profiles + `hermes cron` |
| firstmate parallel crew dispatch | `delegate_task` + cron workers |
| OpenMausBot harness / approval cards | Hermes `approvals` mode + per-toolset scoping |
| LiteLLM model routing (aliases) | Hermes model aliases + MoA preset |
| Subscription Watcher | Hermes cron job every 5 min (cheap model) |
| buzz + maka dual audit | Hermes `state.db` sessions + Discord webhook hook |

## Model tiers (Hermes-native)

| Alias | Resolves to | Billing |
|---|---|---|
| `chief-of-staff` | `xai-oauth / grok-4.5` **or** `anthropic / claude-opus-4-8` **or** `anthropic / claude-sonnet-4-6` | SuperGrok OAuth subscription OR Claude Max OAuth |
| `specialist` | `openrouter / deepseek/deepseek-chat-v3-0324` (rotated pool) | OpenRouter per-token (~$0.27/M) |
| `watcher` | `openrouter / google/gemma-3n-e4b-it:free` (or any free tier) | OpenRouter free tier |
| `frontier` | MoA preset — cheap reference models → grok-4.5 aggregator | Mixed |

## Directory structure

```
carrier_hermes/
├── README.md                  # this file
├── ARCHITECTURE.md            # full design rationale
├── profiles/
│   ├── chief_of_staff/        # SOUL.md + config overrides
│   ├── email_reader/
│   ├── email_drafter/
│   ├── calendar_manager/
│   ├── vault_librarian/
│   ├── research_agent/
│   └── subscription_watcher/
├── prompts/
│   └── SETUP_PROMPT.md        # the prompt to run in a new Hermes session to build the whole fleet
└── moa/
    └── frontier_preset.md     # MoA preset definition for the frontier escalation tier
```

## Quickstart

See `prompts/SETUP_PROMPT.md` — paste it into a fresh Hermes session with full tool access. It will create every bot profile, wire every tool, set up the model aliases, configure the MoA preset, and start the Subscription Watcher cron.
