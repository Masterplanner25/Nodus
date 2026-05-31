# Issue Response Policy

**Maintainer:** Shawn Knight (Masterplanner25)  
**Status:** Governing — applies to all issues filed against Nodus and its companion libraries

---

## Core commitment

Every filed bug gets a response. Not eventually — promptly.

The standard concern about solo-maintained language projects is that issues
languish. That concern is valid for projects where the maintainer has to
understand the bug, reproduce it, trace through the code, write the fix, write
the test, and ship it — all manually, all from scratch. That is not this project.

With AI-assisted development, most bug fixes that would have taken a week take
a session (1–3 hours). A clear repro, a well-described expected vs actual, and
a clean codebase means the fix goes from "filed" to "committed" fast. The test
suite catches regressions. The process is documented. The sessions compound.

This does not mean every filed issue is a 5-minute fix. Some bugs are design
decisions that require Phase 0 thinking before code work begins. Some are
interactions between features that take time to isolate. But the expected
timeline for a filed bug is days to weeks, not months to years.

---

## What happens when you file a bug

1. **Triage** — within one week, the issue gets a severity label
   (`severity:critical`, `severity:high`, `severity:medium`, `severity:low`),
   a subsystem label, and a milestone assignment. If it can't be triaged,
   it gets the `needs-repro` label and a clarifying comment.

2. **Fix or defer decision** — CRITICAL and HIGH bugs get a fix started
   immediately or in the next release cycle. MEDIUM bugs are batched into
   the next planned release. LOW bugs are batched or deferred to a quality
   sweep.

3. **Transparency** — if a bug is deferred, the issue says so, with a milestone.
   No ghost triage (no label + no comment = not triaged).

---

## How bugs found during creator validation are handled

Before every release (Gate 10 / Playbook A Stage 3), the maintainer runs an
adversarial validation session with the explicit goal of finding bugs. Bugs
found during this window are handled under the most favorable possible terms:

- **Fixable before publish:** fixed in the same session, shipped in the version
  being released. The user never sees the bug. A regression test is added.

- **Not fixable before publish:** filed as a GitHub issue with full repro,
  explicitly called out in the release notes as a known issue, and targeted for
  the next patch release. The user sees the bug in the notes before they see
  it in practice.

The release notes for any version that shipped with known-unfixed bugs from
creator validation will say so, plainly, with a link to the issue.

---

## What "quickly" means

| Severity | Target response | Target fix |
|----------|----------------|------------|
| CRITICAL (blocks use) | 24 hours | 1–3 days |
| HIGH (feature broken as documented) | 1 week | 1–2 weeks |
| MEDIUM (workaround exists) | 2 weeks | Next planned release |
| LOW / COSMETIC | 1 month | Batched with quality sweep |

These are targets, not guarantees. Solo maintenance means occasional delays
during busy periods. But the targets are honest — they reflect what AI-assisted
development actually makes possible, not what would be typical for a solo
maintainer without it.

---

## What this policy does NOT promise

- **Zero bugs in any release.** The creator validation gate reduces the number
  of bugs that ship; it does not guarantee zero. A language with a scheduler,
  VM, coroutines, module system, and 40+ stdlib modules will have edge cases
  that no amount of pre-release testing fully covers.

- **Backwards compatibility for experimental surfaces.** Workflows, goals, and
  coroutines are marked experimental. They can change between releases without
  a deprecation cycle. Stable surfaces have the compatibility commitment in
  `docs/governance/COMPATIBILITY_MODEL.md`.

- **Immediate response on duplicate or won't-fix.** Issues that are clearly
  duplicates or design decisions (not bugs) get a brief explanation and close.
  That's still a response, just not a fix.

---

## Filing a good bug report

The faster the repro, the faster the fix. A good bug report has:

1. **Exact repro** — a `.nd` file or a Python snippet that triggers the bug
   consistently. If it's intermittent, say so and describe the conditions.
2. **Expected vs actual** — what you expected to happen, what happened instead.
   Include the exact error message if there is one.
3. **Version** — `nodus --version` output. Bugs that aren't reproducible on
   the current version need to be re-verified first.
4. **Context** — CLI mode, embedded `NodusRuntime`, or inside a test. The same
   bug can present differently across contexts.

Use the `file-bug` skill (`.claude/commands/file-bug.md`) for consistent issue
shape if filing via Claude Code.

---

## Related documents

- `docs/governance/RELEASE_GATES.md §Gate 10` — pre-publish creator validation
- `docs/governance/PLAYBOOK_PATCH_MINOR.md §Stage 3` — validation protocol
- `docs/governance/COMPATIBILITY_MODEL.md` — what's stable vs experimental
- `CHANGELOG.md` — known issues are noted in each version's entry
