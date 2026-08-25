# Provenance — vendored/aipass-mailbox

**Upstream repository:** https://github.com/AIOSAI/AIPass.git
**Commit reviewed:** 1a8d66ca4ecc94ab18ea582dea7b8225bd640d99 (Sat Aug 22 09:35:07 2026 -0700)
**Review date:** 2026-08-23
**License:** MIT (upstream `LICENSE`, copied unmodified into this directory as attribution
for the protocol design this module draws on — no upstream source lines were copied,
so no code-license obligation is triggered, but the attribution is kept anyway).

## Route taken: reimplementation, not a vendored subset

Per the dispatch instructions, a clean protocol-only subset was attempted first and
found infeasible. This directory contains an **original, from-scratch implementation**
of a file-based mailbox protocol, written after reviewing upstream's design — no
upstream source files are copied here. Only `mailbox.py` (original code) and this
document, plus the upstream `LICENSE`, live in this directory.

## Why a subset wasn't possible

Two candidate locations were reviewed in the upstream clone:

1. `src/aipass/aipass/apps/handlers/handoff_platform/__init__.py` — reviewed in full.
   This module contains **no message-format or inbox/outbox logic at all**. It is
   entirely an OS-dispatched interactive terminal-session launcher (picks a terminal
   emulator or a multiplexer tool, or shells out to a Windows terminal host, to open
   a new CLI session). Every function in it either builds a shell command string or
   calls a process-spawning API. There is nothing here to subset — it is 100%
   launcher, 0% protocol.

2. `src/aipass/ai_mail/apps/handlers/email/*.py`, `.../dispatch/*.py`,
   `.../paths.py`, `.../registry/read.py` — this is where the actual message
   read/write/ack logic lives, but it is a single-`inbox.json`-array-per-mailbox
   model (not one-file-per-message), and every handler file is welded to:
   - a proprietary logging/instrumentation layer (`aipass.prax.apps.modules.logger`,
     `json_handler.log_operation` calls on nearly every function),
   - a proprietary console/presentation layer (`aipass.cli.apps.modules.console`),
   - repo-registry discovery (`AIPASS_REGISTRY.json` / `*_REGISTRY.json` walk-up),
   - a ~2,600-line dispatch/daemon/wake/monitor subsystem that starts and
     supervises long-running background processes and a session multiplexer,
   - an outbound notification integration for a consumer chat-bot platform,
   - a CLI permissions-bypass flag variant (present upstream in the launcher
     module above, not present anywhere in this directory).

   Extracting "just the format logic" would have meant either dragging the
   proprietary logger/console/registry dependencies into this repo, or rewriting
   nearly every line to remove them — at which point it is a reimplementation,
   not a subset. So: reimplementation, done honestly as one from the start.

## What was kept (as design concepts, not code)

Ideas borrowed from reading upstream's `inbox_ops.py` / `inbox_lock.py` / `create.py`
and reimplemented independently in `mailbox.py`:
- a message has an author-assigned id/filename and a status field driving
  read/unread bookkeeping (upstream: `status` on a JSON record; here: `status`
  in a Markdown frontmatter block, one file per message instead of one JSON
  array per mailbox),
- write-then-rename-in-place semantics for status transitions (no external
  index to keep in sync),
- per-mailbox directory as the unit of ownership (upstream: one `inbox.json`
  per agent; here: one directory of `.md` files per agent per inbox/outbox).

## What was deliberately excluded from the reimplementation

- Nothing here starts, supervises, or communicates with another process —
  `mailbox.py` only reads and writes plain files.
- No outbound integration to any third-party chat platform.
- No interactive terminal/session-launcher code of any kind.
- No CLI permissions-bypass flag or flag-variant handling.
- No background daemon, watcher, or scheduler.

## Files in this directory

| File | Origin |
|---|---|
| `mailbox.py` | Original code, written for carrier_ops, protocol concepts only |
| `LICENSE` | Copied verbatim from upstream, attribution only |
| `PROVENANCE.md` | This file |

The adapted protocol's practical documentation (filename convention, frontmatter fields,
ack/fold semantics as actually used in this repo) lives outside this directory, in the vault
at `_agent/mailbox/PROTOCOL.md` — not copied here since it documents the vault-side runtime,
not this vendored module.

## Verification

`scripts/vendored-guard.sh` was run against this directory after writing the above
and must pass with zero matches before this directory is considered complete.
