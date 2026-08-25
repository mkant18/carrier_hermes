# carrier_hermes

> Hermes Agent implementation of the Carrier Ops chief-of-staff fleet.

The original [carrier_ops](https://github.com/michaelkanter/carrier_ops) plan described a 5-layer always-on agent stack (OpenClaw → OpenMausBot harness → Podiom → LiteLLM → Obsidian/OB1). This repo re-implements the same fleet using **Hermes Agent as the single runtime**, collapsing those layers while preserving every governance rule, tool scope, agent identity, and model tier from the master plan.

## What maps to what

| carrier_ops layer | Hermes equivalent |
|---|---|
| OpenClaw gateway (Discord/Telegram) | Hermes gateway — `platforms.discord`, `platforms.telegram` in config |
| Podiom durable sessions + scheduler | Hermes profiles + `hermes cron` + Kanban |
| firstmate parallel crew dispatch | **firstmate** profile + worktrees / coding skills (default for coding) |
| OpenMausBot harness / approval cards | Hermes `approvals` mode + per-toolset scoping + no-send tools |
| LiteLLM model routing (aliases) | Hermes model aliases + MoA preset |
| Subscription Watcher | Cron `no_agent` heartbeat scripts + optional cheap summary |
| buzz + maka dual audit | Hermes `state.db` + `_agent/audit/` + Discord webhook |
| Obsidian / OB1 knowledge | **obsidian-second-brain** skills + MCP + vault_librarian |
| Meta optimization (new) | **hermes_ai_explorer** profile (periodic) |

## Model tiers (Hermes-native)

| Alias | Resolves to | Billing |
|---|---|---|
| `chief-of-staff` / `smart` | `xai-oauth / grok-4.5` (fallback Claude Max) | SuperGrok OAuth subscription |
| `quality` | `anthropic / claude-sonnet-4-6` | Claude Max OAuth |
| `frontier-quality` | `anthropic / claude-opus-4-8` | Claude Max OAuth (rare) |
| `specialist` | `openrouter / deepseek/deepseek-chat-v3-0324` **paid pin** | OpenRouter per-token |
| `watcher` | script-first (`no_agent`); optional DeepSeek summary | ~$0 |
| `frontier` | MoA — cheap refs → grok-4.5 aggregator | Mixed |

Do **not** pin email/calendar specialists to OpenRouter `:free` models.

## Directory structure

```
carrier_hermes/
├── README.md
├── ARCHITECTURE.md
├── integrations/
│   └── obsidian-second-brain.md
├── profiles/
│   ├── chief_of_staff/
│   ├── firstmate/                 # coding default (plan)
│   ├── hermes_ai_explorer/        # fleet + AI optimization advisor
│   ├── email_reader/
│   ├── email_drafter/
│   ├── calendar_manager/
│   ├── vault_librarian/           # OSB primary
│   ├── research_agent/
│   └── subscription_watcher/
├── prompts/
│   ├── SETUP_PROMPT.md
│   ├── IMPLEMENT_PROMPT.md        # full plan implementation session
│   └── explorer_cron_prompt.md
├── moa/
│   └── frontier_preset.md
└── .hermes/plans/                 # hardening + cost-optimal plans
```

## Quickstart

1. **Full fleet build (preferred):** paste `prompts/IMPLEMENT_PROMPT.md` into a fresh Hermes session with full tool access. It implements the cost-optimal plan + explorer + OSB.
2. **Legacy bootstrap:** `prompts/SETUP_PROMPT.md` (may lag the plan — prefer IMPLEMENT_PROMPT).
3. **OSB only:** follow `integrations/obsidian-second-brain.md`.

## Profiles (summary)

| Profile | Role |
|---|---|
| chief_of_staff | Inbound classify/dispatch |
| firstmate | Coding crew default |
| hermes_ai_explorer | Periodic workflow/cost/connector advisor → CoS |
| email_reader / email_drafter / calendar_manager | Ops specialists |
| vault_librarian | Obsidian second brain |
| research_agent | General research briefs |
| subscription_watcher | Heartbeat / lock / alerts |
