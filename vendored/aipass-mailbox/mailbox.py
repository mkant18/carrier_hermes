# =================== carrier_ops ====================
# Name: mailbox.py
# Description: Minimal file-protocol mailbox — message naming, frontmatter,
#              inbox/outbox conventions, read/ack/fold semantics.
# Reimplemented from the AIPass mailbox protocol concepts, not copied.
#   See PROVENANCE.md in this directory for the full explanation.
# =====================================================
"""
A tiny, dependency-light implementation of a file-based agent mailbox.

Design goals (see PROVENANCE.md for why this is a reimplementation and not
a vendored subset of AIPass's ai_mail module):

  - One message = one Markdown file with a frontmatter block + body.
  - No daemons, no process spawning, no third-party chat integrations.
  - Pure standard library (re, pathlib, datetime) — no PyYAML.

Message filename convention:
    <utc-timestamp>-<from>-<slug>.md
    e.g. 20260823T211530Z-email-triage-inbox-sweep.md

Frontmatter fields:
    from:    agent name that authored the message
    to:      agent name (or "michael") the message is addressed to
    mission: short free-text description of the mission/thread
    status:  unread | read | folded

Body sections (Markdown headings, all optional but conventionally present):
    ## REPORT
    ## OPEN DECISIONS
    ## DIVERGENCES

This module only implements the protocol/format layer. It does not decide
where a given agent's mailbox lives on disk — callers pass in a directory.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

VALID_STATUSES = ("unread", "read", "folded")

_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n(.*)\Z", re.DOTALL)
_FIELD_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$")
_SLUG_STRIP_RE = re.compile(r"[^a-z0-9]+")


class MailboxError(ValueError):
    """Raised for malformed messages or invalid protocol usage."""


@dataclass
class Message:
    from_agent: str
    to_agent: str
    mission: str
    status: str
    body: str
    path: Optional[Path] = field(default=None)

    def frontmatter_text(self) -> str:
        return (
            "---\n"
            f"from: {self.from_agent}\n"
            f"to: {self.to_agent}\n"
            f"mission: {self.mission}\n"
            f"status: {self.status}\n"
            "---\n"
        )

    def render(self) -> str:
        return self.frontmatter_text() + self.body


def slugify(text: str, max_len: int = 40) -> str:
    """Lowercase, hyphenate, and truncate free text into a filename-safe slug."""
    slug = _SLUG_STRIP_RE.sub("-", text.strip().lower()).strip("-")
    return slug[:max_len].rstrip("-") or "message"


def utc_timestamp(now: Optional[datetime] = None) -> str:
    """Return a compact UTC timestamp: YYYYMMDDTHHMMSSZ."""
    dt = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return dt.strftime("%Y%m%dT%H%M%SZ")


def message_filename(from_agent: str, slug_source: str, now: Optional[datetime] = None) -> str:
    """Build the standard <utc-timestamp>-<from>-<slug>.md filename."""
    return f"{utc_timestamp(now)}-{slugify(from_agent)}-{slugify(slug_source)}.md"


def parse_message(text: str, path: Optional[Path] = None) -> Message:
    """Parse a message file's contents into a Message. Raises MailboxError on bad input."""
    match = _FRONTMATTER_RE.match(text)
    if not match:
        raise MailboxError("message is missing a --- frontmatter block")

    raw_fields, body = match.groups()
    fields: dict[str, str] = {}
    for line in raw_fields.splitlines():
        line = line.strip()
        if not line:
            continue
        field_match = _FIELD_RE.match(line)
        if not field_match:
            raise MailboxError(f"unparseable frontmatter line: {line!r}")
        key, value = field_match.groups()
        fields[key] = value.strip()

    for required in ("from", "to", "mission", "status"):
        if required not in fields:
            raise MailboxError(f"frontmatter missing required field: {required}")

    if fields["status"] not in VALID_STATUSES:
        raise MailboxError(f"invalid status {fields['status']!r}, must be one of {VALID_STATUSES}")

    return Message(
        from_agent=fields["from"],
        to_agent=fields["to"],
        mission=fields["mission"],
        status=fields["status"],
        body=body,
        path=path,
    )


def read_message(path: Path) -> Message:
    """Read and parse a message file from disk."""
    return parse_message(path.read_text(encoding="utf-8"), path=path)


def render_body(report: str = "", open_decisions: str = "", divergences: str = "") -> str:
    """Build the standard REPORT / OPEN DECISIONS / DIVERGENCES body."""
    return (
        "## REPORT\n\n"
        f"{report.strip()}\n\n"
        "## OPEN DECISIONS\n\n"
        f"{open_decisions.strip() or '(none)'}\n\n"
        "## DIVERGENCES\n\n"
        f"{divergences.strip() or '(none)'}\n"
    )


def write_message(
    directory: Path,
    from_agent: str,
    to_agent: str,
    mission: str,
    body: str,
    now: Optional[datetime] = None,
) -> Path:
    """Write a new unread message file into *directory* (an inbox or outbox).

    Returns the path of the written file. Caller is responsible for choosing
    the correct directory per the protocol's routing rule (see PROTOCOL.md).
    """
    directory.mkdir(parents=True, exist_ok=True)
    msg = Message(
        from_agent=from_agent,
        to_agent=to_agent,
        mission=mission,
        status="unread",
        body=body,
    )
    filename = message_filename(from_agent, mission, now=now)
    path = directory / filename
    path.write_text(msg.render(), encoding="utf-8")
    return path


def list_messages(directory: Path, status: Optional[str] = None) -> list[Message]:
    """List messages in *directory*, optionally filtered by status. Skips unparseable files."""
    if not directory.exists():
        return []
    messages: list[Message] = []
    for path in sorted(directory.glob("*.md")):
        try:
            msg = read_message(path)
        except MailboxError:
            continue
        if status is None or msg.status == status:
            messages.append(msg)
    return messages


def ack_message(path: Path) -> Message:
    """Flip a message's status from unread to read, in place. Idempotent if already read."""
    msg = read_message(path)
    if msg.status == "unread":
        msg.status = "read"
        path.write_text(msg.render(), encoding="utf-8")
    return msg


def fold_message(path: Path, folded_dir: Path) -> Path:
    """Move a message into *folded_dir* and set its status to folded.

    This is the chief-of-staff debrief step: after a message's contents have
    been folded into MEMORY.md, the file is archived out of the active
    inbox/outbox listing.
    """
    msg = read_message(path)
    msg.status = "folded"
    folded_dir.mkdir(parents=True, exist_ok=True)
    dest = folded_dir / path.name
    dest.write_text(msg.render(), encoding="utf-8")
    path.unlink()
    return dest
