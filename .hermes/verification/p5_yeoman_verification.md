# Yeoman AIPass Intake Verification Report
**Task:** t_9c315547  
**Author:** Mate ⚙️ (firstmate)  
**Date:** 2026-08-26  
**Status:** ✅ COMPLETE

---

## 1. Yeoman AIPass Intake Format (from SOUL.md)

Yeoman's SOUL.md declares its AIPass configuration:

```
AIPass: _agent/mailbox/git_yeoman/{inbox,outbox}/ via scripts/aipass_send.py
```

**Resolved inbox path:**
```
C:/Users/micha/AppData/Local/hermes/profiles/git_yeoman/home/_agent/mailbox/git_yeoman/inbox/
```

Yeoman is configured to receive messages via the `aipass` toolset (listed as ON in SOUL.md). The bot reads from its own inbox and writes to recipient inboxes. No explicit YAML schema is enforced by SOUL.md — format is implicitly defined by what senders write.

---

## 2. Caulker → Yeoman: open_pr Packet (patch_writer.md)

**Inbox path used by Caulker:**
```
C:/Users/micha/AppData/Local/hermes/profiles/git_yeoman/home/_agent/mailbox/git_yeoman/inbox/
```
✅ Path matches Yeoman's expected inbox path.

**Filename convention:** `aipass-caulker-<timestamp>.md`

**YAML frontmatter schema:**
```yaml
---
from: patch_writer
to: git_yeoman
type: open_pr
branch: maint/<YYYY-MM-DD>/fixes
base: main
pr_title: "🛠 Maintenance: <N> fixes, <YYYY-MM-DD>"
pr_body: |
  Automated maintenance pass by Shipwright Wing — <YYYY-MM-DD>.
  ## Fixes Applied
  - [SEVERITY] `<file>`: <description>
  ## Blocked Fixes (if any)
  - Fix N: <reason> — requires human review
  ## Process
  Each fix is an atomic commit. All changed files passed `ruff check`. Tests run per fix.
  /cc Surveyor 🧭 for review.
---
```

**Key constraint noted in Caulker's prompt:**
> Use the exact Unicode wrench: `🛠` (not `🛠️` — Yeoman's parser is sensitive)

⚠️ **Potential issue:** The PR title uses `🛠` (U+1F6E0, no variation selector) rather than `🛠️` (with VS-16). This is Caulker's explicit constraint — Yeoman's parsing is described as sensitive to this. However, Yeoman's SOUL.md has no matching parser rule documented. This should be verified against Yeoman's actual PR creation logic.

---

## 3. Surveyor → Yeoman: merge_pr Packet (pr_reviewer.md)

**Inbox path used by Surveyor:**
```
$OBSIDIAN_VAULT_PATH/_agent/mailbox/git_yeoman/inbox/<utc>-pr_reviewer-merge_pr<N>.md
```

⚠️ **FORMAT MISMATCH FOUND:**

Surveyor's prompt uses `$OBSIDIAN_VAULT_PATH` as the base path, NOT the resolved Hermes profile path. This is an **unresolved variable reference** in Surveyor's configuration.

The correct path should be:
```
C:/Users/micha/AppData/Local/hermes/profiles/git_yeoman/home/_agent/mailbox/git_yeoman/inbox/
```

**Surveyor's merge_pr YAML schema:**
```yaml
---
from: pr_reviewer
to: git_yeoman
mission: merge_pr
status: unread
---
## REPORT

**Surveyor 🧭** — PR #<N> approved. Please merge.

merge PR #<N> — approved by Surveyor 🧭

PR Title: <exact PR title>
PR URL: https://github.com/owner/repo/pull/<N>
Branch: maint/<date>/fixes
Description excerpt:
> <first 3-4 lines of PR body>

Merge method: squash (or merge commit — per your standing config)
After merge: please reply via AIPass with the merge SHA.
```

**Filename convention:** `<UTC_timestamp>-pr_reviewer-merge_pr<N>.md`

---

## 4. Format Comparison: Caulker vs. Surveyor

| Field | Caulker (open_pr) | Surveyor (merge_pr) |
|---|---|---|
| `from` | `patch_writer` | `pr_reviewer` |
| `to` | `git_yeoman` | `git_yeoman` |
| `type`/`mission` | `type: open_pr` | `mission: merge_pr` |
| `status` field | Not included | `status: unread` |
| Body format | YAML multiline `pr_body:` | Markdown REPORT section |
| Path variable | Hardcoded absolute path | `$OBSIDIAN_VAULT_PATH` (unresolved) |

**Schema inconsistency:** Caulker uses `type:` key; Surveyor uses `mission:` key. Yeoman's SOUL.md does not specify which field name it expects — both should work if Yeoman inspects either key, but this could cause parsing confusion if Yeoman strictly parses only one field name.

**Missing `status: unread` in Caulker packets:** Surveyor includes `status: unread` in its frontmatter; Caulker does not. If Yeoman uses `status` to gate processing, Caulker's messages may not be picked up correctly.

---

## 5. Inbox Path Verification

**Path checked:**
```
C:/Users/micha/AppData/Local/hermes/profiles/git_yeoman/home/_agent/mailbox/git_yeoman/inbox/
```

**Result:** ❌ Did NOT exist prior to this verification run.  
**Action taken:** ✅ Directory created by Mate during this task.

**Write test:** ✅ Successfully wrote `message-test-shipwright.md` to the inbox.

---

## 6. Issues and Recommendations

### 🔴 ISSUE 1 — Surveyor uses unresolved `$OBSIDIAN_VAULT_PATH`
**Severity:** HIGH  
**File:** `C:/Users/micha/carrier_hermes/prompts/pr_reviewer.md`  
**Finding:** Surveyor's AIPass mailbox table uses `$OBSIDIAN_VAULT_PATH/_agent/mailbox/git_yeoman/inbox/` — this env var is not defined in Yeoman's profile or Surveyor's config. Messages will be written to the wrong path or fail entirely.  
**Recommendation:** Replace `$OBSIDIAN_VAULT_PATH` with the hardcoded Hermes profile path, or define the env var in Surveyor's launch configuration. Preferred fix: align with Caulker's pattern using the explicit path `C:/Users/micha/AppData/Local/hermes/profiles/git_yeoman/home/_agent/mailbox/git_yeoman/inbox/`.

### 🟡 ISSUE 2 — `type:` vs `mission:` field name inconsistency
**Severity:** MEDIUM  
**Finding:** Caulker uses `type: open_pr`; Surveyor uses `mission: merge_pr`. If Yeoman's session prompt or aipass handler looks for a specific key, one sender's messages will be misrouted.  
**Recommendation:** Standardize on one key name across all senders. Suggest adopting `type:` (Caulker's pattern) and updating Surveyor's prompt.

### 🟡 ISSUE 3 — Missing `status: unread` in Caulker packets
**Severity:** LOW  
**Finding:** Surveyor includes `status: unread` in its frontmatter; Caulker does not.  
**Recommendation:** Add `status: unread` to Caulker's packet template for consistency, in case Yeoman's aipass processor uses this field to gate processing.

### 🟢 ISSUE 4 — Yeoman inbox path did not exist
**Severity:** LOW (resolved)  
**Finding:** The inbox path `home/_agent/mailbox/git_yeoman/inbox/` did not exist under Yeoman's profile home directory.  
**Action:** Created during this verification run. No further action needed unless the aipass system is expected to create it on first run.

### 🟢 NOTE — `🛠` vs `🛠️` Unicode wrench in PR title
**Severity:** INFO  
**Finding:** Caulker's prompt explicitly says to use `🛠` (U+1F6E0, no variation selector), calling Yeoman's parser "sensitive." This is defined intent in Caulker's instructions, not a bug — but Yeoman's SOUL.md does not document this constraint. Worth noting for maintainability.

---

## 7. Summary

| Check | Result |
|---|---|
| Yeoman SOUL.md read | ✅ |
| Caulker packet format verified | ✅ |
| Surveyor packet format verified | ✅ with issues |
| Inbox path exists | ✅ (created) |
| Test message written | ✅ |
| Format mismatches documented | ✅ 3 issues found |

**Critical blocker:** Surveyor's `$OBSIDIAN_VAULT_PATH` path reference will cause message delivery failure unless the env var is defined or the prompt is updated.
