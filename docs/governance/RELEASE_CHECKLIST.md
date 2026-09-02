# Nodus Release Checklist

**Last reviewed:** 2026-09-01, against 5.9.0
**Status:** Pointer — the release sequence is authoritative in `CLAUDE.md`
**Maintainer:** Shawn Knight (Masterplanner25)

> **This document no longer restates the release sequence.** It restated a
> twelve-step process in four steps and drifted; see *Why the sequence that used
> to be here is gone* below. The only content still original to this file is the
> **new-opcode procedure** at the bottom.

---

## The release sequence

| What you need | Where it is |
|---|---|
| **The sequence itself**, in order, with the traps | `CLAUDE.md § "Version sync — must keep in step"` — the authority |
| Which playbook a given release follows | `docs/governance/RELEASE_PLAYBOOK.md` |
| Gate definitions and passing criteria | `docs/governance/RELEASE_GATES.md` |
| Build and runtime validation detail | `docs/release.md` |
| Pre-publish eval prompt (Gate 10) | `docs/governance/EVAL_PREPUBLISH.md` |
| Post-publish eval prompt (Stage 5) | `docs/governance/EVAL_POSTPUBLISH.md` |
| Semver policy | `docs/release.md#semantic-versioning` |

`/release-prep` (`.claude/commands/release-prep.md`) walks the sequence, but it is
older than the sequence and its Step 5 pushes to `main`, which `enforce_admins`
rejects. Use it as a prompt, not a script.

---

## Why the sequence that used to be here is gone

Reviewed against the tree on 2026-09-01. The version written 2026-05-29 was not
merely incomplete — it was wrong in the one place a release cannot recover from:

- **It said "Tag the release → Publish release notes."** The actual order is tag →
  build from the tagged tree → Gate 10 → **PyPI** → *then* the GitHub release.
  A GitHub release marks its tag immutable **permanently**; deleting the release
  does not clear it, and `gh release create` on that tag afterwards is refused
  forever. Cutting the release before PyPI is the one sequencing mistake with no
  recovery, and this checklist prescribed it.
- **It ran ruff on "changed files" and never mentioned mypy.** CI runs both, and
  both block merges. `ruff check src/ tests/` is clean tree-wide, so scoping it
  now only hides regressions.
- **It had no Gate 10 step 0.** The dependent-suite gate
  (`tools/check_dependent_suites.py`) runs *before* the upload because
  nodus-lang validated against itself cannot see what it breaks in a companion —
  that is how 5.0.3 shipped broken to `nodus-sdk` and cost a 5.0.4.
- **It had no Stage 5, no Stage 6, and no eval documents.** Three documents per
  release under `docs/evals/vX.Y.Z/` are part of the release, not a write-up, and
  `nodus_gate --versions` fails without `CREATOR_VALIDATION.md`.
- **It missed every gate re-run the bump invalidates**: `--closed-issues --section
  X.Y.Z`, `--versions` after the version files move, `python -m tools.sync_llms_txt`,
  and the suite itself.
- **It told you to update `ROADMAP.md` milestone status.** Milestones were
  abandoned 2026-08-26 and all eleven are closed; release scope is tracked by
  `CHANGELOG.md`'s `[Unreleased]` section. (The file is also at
  `docs/governance/ROADMAP.md`, not the repo root.)

`DOCSET_CHANGELOG.md` flagged this file on **2026-05-29** — *"`RELEASE_CHECKLIST.md`
uses pre-v1.0 CLI commands — fix before next release"* — and nine releases went out
without it being fixed. A second copy of a sequence nobody reconciles is how a
checklist ends up prescribing the unrecoverable step.

---

## Adding a new opcode (post-v1.0 freeze)

The opcode set is frozen at v1.0 — **49 active opcodes**, `BYTECODE_VERSION = 4`.
To add one:

1. Open `docs/governance/FREEZE_PROPOSAL.md` and add an "Extension Proposal" entry
   with the opcode name, motivation, and provisional/stable classification.
2. Add `_op_<name>` to `src/nodus/vm/vm.py` and register it in `_build_dispatch_table()`.
3. Emit it from `src/nodus/compiler/compiler.py`.
4. Bump `BYTECODE_VERSION` in `compiler.py` and `NODUS_BYTECODE_VERSION` in
   `src/nodus/runtime/module.py`.
5. Document it in `docs/runtime/BYTECODE_REFERENCE.md` (**both** §3 and the
   appendix table), `docs/runtime/BYTECODE.md`, and
   `docs/runtime/INSTRUCTION_SEMANTICS.md`. Add a version-history entry to
   `BYTECODE.md`.
6. **Write a semantic spec** in `tests/test_opcode_semantics*.py`. Execute the one
   instruction against a hand-built VM state — not a program whose output you
   check, which is what the golden tests already do and is why #370 survived them.
   Then prove the spec can fail by breaking the opcode and watching it go red.
7. Update `CHANGELOG.md` with the version bump reason.

**Steps 5 and 6 are enforced, not advisory.** `nodus_gate --opcodes` requires
`BYTECODE_REFERENCE.md §3`, its appendix table, and the `FREEZE_PROPOSAL.md`
stability tables to name the same set with matching counts and `BYTECODE_VERSION`
([#366](https://github.com/Masterplanner25/Nodus/issues/366)), and requires every
dispatched opcode to carry a semantic spec and a `- Category:` line
([#412](https://github.com/Masterplanner25/Nodus/issues/412) phase 4). The
relation is an equality in both directions: an opcode with no spec and a spec
naming nothing dispatched are both failures. The gate will fail until you have
done both — that is the point of it.
