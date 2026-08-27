# OpenMausBot Architecture Patterns — carrier_hermes Mapping

> **Research date:** 2026-08-26  
> **Source:** https://github.com/milind-soni/OpenMausBot (v0.1.37, Apache-2.0)  
> **Scope:** Pattern extraction only — no code execution, no install.

---

## Executive Summary

OpenMausBot is a Grok-Bot-clone desktop app where every chat contact is a real AI agent running on the user's machine. Its architecture solves five problems that carrier_hermes faces right now: pluggable providers, human-in-the-loop approvals, fleet roster management, external webhook triggers, and multi-provider event normalization. Each pattern below includes verbatim code excerpts and a concrete carrier_hermes adoption plan.

**Priority order for adoption:**
1. **Webhook trigger system** (Spec C) — connects directly to Wave 1 peers broker; low friction
2. **Approval card system** (Spec A) — fills the biggest fleet safety gap; Discord is our "UI"
3. **Provider-normalized event stream** (Spec B) — enables clean routing across Grok/Claude/Ollama/DeepSeek
4. **Driver SPI** — worth adopting after Spec B lands; lowers cost of adding new providers
5. **Agent-as-contact roster** — informational for Discord sidebar design

---

## Pattern 1: Driver SPI (`server/contracts.ts` + `server/drivers/`)

### What it is

A tiny, stable TypeScript interface (`ProviderDriver<Config>`) that every provider must implement. Adding a new AI provider requires exactly one file in `server/drivers/` and one registration line. The harness, routing logic, and UI never touch provider-specific code.

### Exact interface (from `server/contracts.ts`)

```typescript
// Every driver must export one of these
export interface ProviderDriver<Config = unknown> {
  readonly driverKind: DriverKind;            // slug: "claudeAgent", "grokAgent", etc.
  readonly metadata: {
    displayName: string;
    supportsMultipleInstances?: boolean;
    access?: EngineAccess;                    // "subscription" | "custom"
  };
  readonly install?: EngineInstall;           // platform-specific install commands
  decodeConfig(raw: unknown): Config;         // validates the config envelope
  defaultConfig(): Config;
  readonly models: ModelCatalog;              // { default: string, options: [...] }
  create(input: DriverCreateInput<Config>): Promise<ProviderInstance>;
}

// The live object produced by create()
export interface ProviderInstance {
  readonly instanceId: InstanceId;
  readonly driverKind: DriverKind;
  readonly models: ModelCatalog;
  readonly adapter: ProviderAdapter;          // the actual comms interface
  snapshot(): Promise<ProviderSnapshot>;      // availability check
  generateText?(prompt: string): Promise<string>; // cheap one-shot (titles/summaries)
  dispose(): Promise<void>;
}

// All providers are flattened into this adapter — drivers translate their
// native protocol (stdio JSON, REST, etc.) into these methods
export interface ProviderAdapter {
  readonly provider: DriverKind;
  readonly capabilities: {
    sessionModelSwitch: "in-session" | "unsupported";
    agentsMcp?: boolean;
    computerMcp?: boolean;
    images?: boolean;
    effortLevels?: readonly EffortLevel[];
    queueing?: boolean;
    localComputerMcp?: boolean;
  };
  sendTurn(input: SendTurnInput): Promise<TurnStartResult>;
  interruptTurn(threadId: ThreadId, turnId?: TurnId): Promise<void>;
  respondToRequest(
    threadId: ThreadId,
    requestId: string,
    decision: { behavior: "allow" | "deny" | "answer"; message?: string },
  ): Promise<RequestOutcome>;
  steer?(threadId: ThreadId, text: string): Promise<boolean>; // mid-turn steering
  hasSession(threadId: ThreadId): boolean;
  stopAll(): Promise<void>;
  onEvent(listener: RuntimeEventListener): () => void;
}
```

### How a real driver implements it (from `server/drivers/claude.ts`)

```typescript
const DRIVER_KIND = "claudeAgent";

// 1. Static model catalog
export const STATIC_CLAUDE_MODELS: ModelCatalog = {
  default: "claude-sonnet-5",
  options: [
    { id: "claude-sonnet-5", label: "Claude Sonnet 5" },
    { id: "claude-opus-5", label: "Claude Opus 5" },
  ],
};

// 2. Config type (driver-specific, decoded/validated by decodeConfig)
export interface ClaudeConfig {
  cli: string;
  permissionMode: "acceptEdits" | "auto" | "bypassPermissions";
}

// 3. create() spins up a ProviderInstance with an embedded ProviderAdapter
// The adapter translates stdout events from `claude --print --output-format stream-json`
// into the canonical RuntimeEvent union (see Pattern 5)
```

### carrier_hermes mapping

Helm currently selects providers through ad-hoc prompt routing (Grok 4.5 → Claude → Ollama → DeepSeek Flash). A driver SPI would:
- Let each provider declare its capabilities (`images`, `effortLevels`, `queueing`) so Helm never offers a feature a provider can't honor
- Allow adding DeepSeek R1 or Qwen without touching Helm's routing logic
- Standardize the `snapshot()` / availability check so the billing guard can inspect all providers uniformly
- Support `generateText()` for cheap single-shot calls (task titling, summaries) without spinning up a full agent session

**Implementation path:** Define a Python `ProviderDriver` protocol in `carrier_hermes/drivers/base.py`, implement `ClaudeDriver`, `GrokDriver`, `OllamaDriver`, `DeepSeekDriver` each as one file. Helm registers drivers at startup and routes through a `ProviderRegistry`.

---

## Pattern 2: Approval Card System (`server/auto-approve.ts` + `contracts.ts`)

### What it is

When an agent wants to run a command, the harness decides: auto-approve silently, or surface a "request card" that pauses the agent until a human responds. Two escalation paths exist in the contract:

```typescript
// From contracts.ts — emitted when agent requests permission
| {
    type: "request.opened";
    requestType: "permission" | "question";
    tool: string;
    summary: string;
    choices?: string[];
    approvalScope?: "local-computer";
  }
// Emitted when the human (or auto-mode) decides
| {
    type: "request.resolved";
    behavior: "allow" | "deny" | "answer";
    source: "user" | "auto" | "timeout" | "system" | "unavailable" | "peer";
    approvalScope?: "local-computer";
  }
```

### What triggers auto-approve vs. human card (from `server/auto-approve.ts`)

```typescript
// Auto-approve is BLOCKED by destructive patterns (checked before any silent approval)
const DESTRUCTIVE = [
  /\brm\s+(-[a-z]*\s+)*-[a-z]*[rf]/i,         // rm -rf, rm -fr
  /\bgit\s+push\s+[^|]*--force(-with-lease)?/i, // force push
  /\bDROP\s+(TABLE|DATABASE)\b/i,               // SQL drops
  /\bsudo\s+rm\b|\bchmod\s+-R\s+777\s+\//i,
];
const SENSITIVE = [
  /(^|[\s/"'])\\.env(\.|$|["'\s])/i,
  /\.ssh\/|id_rsa|id_ed25519/i,
  /\.aws\/credentials|\.netrc/i,
];
// If summary matches DESTRUCTIVE → always card, never auto
// If summary matches SENSITIVE → always card, never auto
// Otherwise in auto-mode → auto-approve with log entry

// "Always allow" is narrowed by program, not just tool name
const COMMAND_TOOLS = new Set(["bash", "shell", "execute", "run_command", "terminal"]);
function approvalKey(tool: string, summary: string, scope?: "local-computer"): string {
  const bare = tool.replace(/^mcp__[^_]+__/, "").toLowerCase();
  if (!COMMAND_TOOLS.has(bare)) return scope ? `${scope}:${tool}` : tool;
  // "Always allow bash" → too broad; key by program: "Bash:git", "Bash:npm"
  const words = summary.trim().split(/\s+/);
  // ... extract first program word
}
```

### How it waits for a response

The harness emits `request.opened` on the event stream. The UI renders a card and blocks. When the user clicks Allow/Deny, the UI calls `adapter.respondToRequest(threadId, requestId, { behavior: "allow" })`, which unblocks the agent. The `request.resolved` event is emitted with `source: "user"`.

The `RequestOutcome` type makes the result unambiguous: `"allowed-once" | "rejected" | "answered" | "unavailable"`. `unavailable` is the fail-closed default when no human is present.

### carrier_hermes mapping (Spec A)

Helm should emit approval requests to Discord before executing irreversible actions. The pattern:
1. Bot is about to run `git push`, `rm`, email send, or file delete → emit approval event
2. Helm posts a Discord embed with action summary, two buttons (✅ Allow / ❌ Deny)
3. Bot's thread is **paused** (kanban task stays `running`, Helm polls Discord for button response)
4. On Allow → resume; on Deny → abort with explanation; on timeout (5 min) → fail-closed (deny)

The DESTRUCTIVE regex list is directly portable to Python for Helm's pre-action guard.

---

## Pattern 3: Agent-as-Contact / Roster Model (`server/drivers/agents-proxy.ts`)

### What it is

Each bot is a "contact" in a Telegram-style sidebar. The harness maintains a roster of `{id, name, title, description, model, busy}` objects. Agents can call `list_bots()` to discover peers:

```typescript
// From agents-proxy.ts — the MCP tool that surfaces the roster to agents
const r = await api(`/api/internal/agents?self=${encodeURIComponent(BOT_ID)}`);
const bots = (r.bots as Array<Json>) ?? [];
// Each bot in the roster carries:
// { id, name, title, description, model, busy }

// Agents can also delegate to peers:
// ask_bot(bot_id, message)       → synchronous, waits for reply
// delegate_bot(bot_id, message)  → async, peer runs after current turn finishes
```

### State management

- `busy` flag is set by the harness when a bot has a running turn
- The sidebar reflects live status: `idle` / `working` / `waiting for approval`
- Depth guard: `OMB_TURN_DEPTH` env var prevents recursive agent chains from running unbounded
- Section-based organization: bots belong to sections; a Chief of Staff bot can `create_bot()` for their section (max 4/turn)

### carrier_hermes mapping

The fleet roster in `carrier_hermes` already has this structure (see `docs/DISCORD_BOT_IDENTITY_MATRIX.md`). Gaps to close:
- The carrier roster doesn't expose a `/api/internal/agents` endpoint that bots can query
- `busy` state is tracked per-kanban-task but not surfaced as a live API
- Discord sidebar doesn't reflect running state — bots just have presence, not "working on X"

**Adoption:** Add a lightweight Flask endpoint to each bot profile (or to Helm) that returns fleet roster JSON. Update `carrier_kanban_dispatch` to set a bot's Discord presence/status when a task starts/ends.

---

## Pattern 4: Webhook Trigger System (`server/webhooks.ts`)

### What it is

OpenMausBot runs a **dedicated, minimal HTTP server** on port 8800 (one port above the main API at 8799) that receives webhook events and triggers agent runs. It is isolated from the main API surface by design.

### The WebhookTrigger data model (from `server/webhooks.ts`)

```typescript
export interface WebhookTrigger {
  id: string;
  endpointId: string;    // the URL path fragment (/hooks/<endpointId>)
  name: string;
  prompt: string;        // pre-set prompt injected when the webhook fires
  botId: string;         // which bot handles this webhook
  runOn: RoutineRunOn;   // "local" | "cloud" runner
  enabled: boolean;
  createdAt: number;
  updatedAt: number;
  lastReceivedAt?: number;
  lastRunId?: string;
  deliveryCount: number;
  verificationPending?: boolean;  // NEW hooks must receive one request before running
  verifiedAt?: number;
  verificationSample?: WebhookVerificationSample;
  eventTypes?: string[];  // optional allowlist — empty = accept all event types
}

export interface WebhookAttempt {
  id: string;
  webhookId: string;
  receivedAt: number;
  outcome: "accepted" | "captured" | "duplicate" | "ignored" | "rejected";
  statusCode: number;
  eventName?: string;
  preview?: string;
  deliveryId?: string;
  runId?: string;
  reason?: string;
}
```

### Key behaviors

- **Deduplication:** `DeliveryReceipt` records prevent a retried webhook from triggering twice
- **Outcomes:** `captured` = webhook stored but bot not yet run; `accepted` = bot run queued; `duplicate` = already processed; `ignored` = event type not in allowlist; `rejected` = bad auth
- **Auth:** Bearer token (recommended) OR capability URL (secret in path, for senders that can't set headers)
- **Verification flow:** New hooks must receive one request before they can trigger a bot run (prevents typo misconfiguration)
- **Prompt injection:** If a static `prompt` is configured, it's prepended; otherwise the webhook payload is parsed for a task description

### Queue behavior

When multiple webhooks arrive concurrently, the queued task executor (shared with Routines) serializes them per-bot. A bot that's busy receives `captured` outcome — the run is queued, not dropped.

### carrier_hermes mapping (Spec C)

This is the exact pattern needed for the **peers broker** (Wave 1, PR #5) to trigger agent runs. Currently the broker handles peer registration and messaging but doesn't dispatch kanban tasks in response to external events. The webhook system would:
1. Expose `/hooks/<secret>` endpoints that map to specific bot assignments
2. On arrival: validate auth → check dedup → create kanban task with `status=ready` → return 202
3. Webhook events from GitHub CI, external services, or other carrier fleets trigger specific bots
4. The peers broker on port 9876 can forward peer announcements as webhook calls to the local fleet

The `eventTypes` allowlist maps cleanly to the peers broker's message types (`peer_registered`, `peer_message`, `peer_left`).

---

## Pattern 5: Multi-Provider Normalized Event Stream (`server/contracts.ts`)

### What it is

Every provider driver translates its native protocol into a **canonical `RuntimeEvent` union**. The harness, UI, and logging layer only see this normalized stream — never raw protocol bytes. The `raw` field optionally carries the original message for debugging.

### The canonical event types

```typescript
export type RuntimeEvent = RuntimeEventBase & (
  // Session lifecycle
  | { type: "session.started"; sessionId: string | null; model?: string | null }
  | { type: "session.exited"; reason?: string }
  // Turn lifecycle
  | { type: "turn.started" }
  | { type: "turn.retrying"; attempt: number; delayMs: number; reason: string }
  | { type: "turn.completed";
      ok: boolean;
      stopReason?: string | null;
      cost?: number | null;
      denials?: string[];
      usage?: { input: number; output: number };  // THIS turn's tokens only
    }
  // Tool execution
  | { type: "item.started"; itemType: "tool" | "reasoning"; title?: string }
  | { type: "item.updated"; itemType: "tool" | "reasoning"; tokens?: number | null }
  | { type: "item.completed"; itemType: "tool"; ok: boolean }
  | { type: "item.completed"; itemType: "assistant_text"; text: string }
  // Streaming text
  | { type: "content.delta"; streamKind: "assistant_text" | "reasoning_text"; delta: string }
  // Human-in-the-loop
  | { type: "request.opened"; requestType: "permission" | "question"; tool: string; summary: string; choices?: string[] }
  | { type: "request.resolved"; behavior: "allow" | "deny" | "answer"; source: "user" | "auto" | "timeout" | "system" | "unavailable" | "peer" }
  // Token accounting
  | { type: "thread.token-usage.updated"; input: number; output: number }
  // Errors
  | { type: "runtime.error"; message: string; setup?: boolean }
);

// Base fields on every event
export interface RuntimeEventBase {
  eventId: string;
  provider: DriverKind;
  providerInstanceId?: InstanceId;
  threadId: ThreadId;
  createdAt: string;
  turnId?: TurnId;
  itemId?: string;
  requestId?: string;
  raw?: { source: string; payload: unknown };  // original protocol message
}
```

### How streaming vs. non-streaming providers work

- **Streaming providers** (Claude, Grok): emit `content.delta` events in real time, then `item.completed` with the full text at turn end
- **Non-streaming providers** (Antigravity/Gemini in print mode): buffer output, emit a single `item.completed` with full text — no deltas
- The `ProviderAdapter.capabilities.queueing` flag tells the UI whether to keep the composer open mid-turn
- Token accounting: `turn.completed.usage` is the authoritative per-turn figure; `thread.token-usage.updated` is a live indicator that MUST NOT be summed (different drivers report it differently)

### Effort levels (reasoning control)

```typescript
export const EFFORT_LEVELS = ["none", "low", "medium", "high", "xhigh", "max"] as const;
// Each driver declares the subset it can pass to its CLI
// capabilities.effortLevels = ["low", "medium", "high"] for Claude
// Never offer a knob the driver cannot turn
```

### carrier_hermes mapping (Spec B)

Currently each bot in carrier_hermes has hardcoded provider logic in its prompt/config. A normalized event stream would:
- Let Helm observe any bot's execution in real-time (token usage, tool calls, errors) via a single listener
- Enable the billing guard to intercept `turn.completed.usage` events fleet-wide without provider-specific code
- Surface `runtime.error` with `setup: true` to automatically pause a bot and page the ops LT
- Allow the Discord bridge to render `content.delta` as streaming message edits (bot "typing")
- Make the routing fallback chain (Claude Max → Grok 4.5 → Ollama → DeepSeek) transparent: on `session.exited` with the right error code, Helm retries with the next provider

**Python implementation:** A `RuntimeEvent` dataclass union (use `typing.Literal` for `type` discriminator). Each driver's `run_turn()` yields `RuntimeEvent` instances. A `HelmEventBus` broadcasts to: billing guard, Discord bridge, approval card handler, activity logger.

---

## Implementation Priority Matrix

| Pattern | Value | Effort | Dependencies | Priority |
|---------|-------|--------|-------------|----------|
| Webhook trigger system (→ Spec C) | 🔴 High | 🟡 Medium | Wave 1 peers broker | **1st** |
| Approval cards via Discord (→ Spec A) | 🔴 High | 🟡 Medium | Discord webhook bot | **2nd** |
| Provider event stream (→ Spec B) | 🟠 Medium-High | 🔴 High | All provider drivers | **3rd** |
| Driver SPI | 🟠 Medium | 🟡 Medium | Spec B event types | **4th** |
| Agent roster live API | 🟡 Low-Medium | 🟢 Low | Fleet checkin already exists | **5th** |

---

## Reference Files

- `server/contracts.ts` — complete type definitions for all 5 patterns
- `server/drivers/claude.ts` — full Claude driver implementation (~400 lines)
- `server/drivers/antigravity.ts` — Gemini/Antigravity driver (per-turn process, no interactive broker)
- `server/drivers/agents-proxy.ts` — peer agent comms MCP proxy (list_bots, ask_bot, delegate_bot)
- `server/auto-approve.ts` — destructive/sensitive regex guards + approvalKey logic
- `server/webhooks.ts` — WebhookTrigger model, WebhookAttempt outcomes, dedup receipt
- `server/routines.ts` — shared queued task executor (routines + webhooks share this)
