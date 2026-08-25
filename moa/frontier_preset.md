# Frontier MoA Preset Definition

**Preset name:** `frontier`

**Purpose:** On-demand multi-model escalation for hard, ambiguous, or high-stakes reasoning tasks. Invoked with `/moa <prompt>` — runs once and auto-reverts to the main model. For sustained frontier work, switch with `/model frontier --provider moa`.

## Configuration

| Slot | Provider | Model | Role |
|---|---|---|---|
| Reference 1 | `openrouter` | `deepseek/deepseek-chat-v3-0324` | Analytical pass — systematic reasoning |
| Reference 2 | `openrouter` | `meta-llama/llama-4-maverick:free` | Alternative framing — different model family perspective |
| Aggregator | `xai-oauth` | `grok-4.5` | Synthesises references, emits final response, calls tools |

## Billing

- Reference models: OpenRouter, ~$0.27/M + $0.00 = minimal
- Aggregator: SuperGrok OAuth subscription — zero marginal cost
- Total frontier call cost: ~$0.001–0.01 depending on context length

## When Chief of Staff escalates to frontier

- Multi-step strategic decisions
- Ambiguous high-stakes requests where a second model perspective materially reduces error risk
- Architecture / design questions where model disagreement is informative
- Anything where being wrong costs more than the latency of a multi-model call

## How to create this preset

```bash
hermes moa configure
# Name: frontier
# Reference 1: openrouter / deepseek/deepseek-chat-v3-0324
# Reference 2: openrouter / meta-llama/llama-4-maverick:free
# Aggregator: xai-oauth / grok-4.5
```

Verify: `hermes moa list`
