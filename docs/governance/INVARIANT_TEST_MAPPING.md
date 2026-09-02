# Invariant Test Mapping

**Last reviewed:** 2026-09-01, against 5.9.0
**Status:** Superseded by `tools/invariant_coverage.json`
**Maintainer:** Shawn Knight (Masterplanner25)

> **The invariant-to-test mapping is `tools/invariant_coverage.json`, and it is the
> only copy.** `nodus_gate --invariants` checks it. Do not restore a prose table
> here — this document *was* that table, and the section below is what it had
> become.

---

## Where to look

| Question | Where |
|---|---|
| What are the runtime invariants? | `docs/runtime/EXECUTION_INVARIANTS.md` — **29** of them |
| Which test covers invariant X? | `tools/invariant_coverage.json` |
| Is the mapping honest? | `nodus_gate --invariants` — four checks, all failing the gate |
| What test gaps are open? | `docs/governance/TEST_GAP_BACKLOG.md` |
| What are the test standards? | `docs/governance/TEST_STRATEGY.md` |

The gate fails on: an invariant with no entry, an entry naming an invariant the
document no longer has, a named test file that does not exist, and an entry with no
tests and no stated reason. Citation drift is advisory.

**`unrecorded` is not `uncovered`.** Six of the 29 name a covering test; the other 23
are `unrecorded`, meaning the behaviour may well be tested but nothing ties a test to
the invariant. Do not "improve" that count by guessing a mapping — an invented one is
worse than a recorded gap, and is precisely how this document failed.

---

## Why this document was superseded

#179 is the issue: which test checks which invariant was recorded **in prose, in two
different places, by hand**, so a renamed test left the document pointing at nothing
and a new invariant arrived uncovered — with no CI signal for either. This file was
one of those two places. Reviewed against the tree on 2026-09-01, both failure modes
had happened here, and neither had ever surfaced:

- **Six of the thirteen test files it named do not exist** — `test_functions.py`,
  `test_recursion.py`, `test_try_catch.py`, `test_imports.py`, `test_sandbox.py`,
  `test_workflows.py`. Four of those sat under a **✅**, whose legend in this very
  document read *"Covered — test(s) exist that would fail on violation."* One of the
  four was **I-SAND-01**, the `allowed_paths` filesystem boundary.
- **It had never learned four invariants.** It mapped 25; `EXECUTION_INVARIANTS.md`
  documents 29. `I-WFLOW-04` through `I-WFLOW-07` were simply absent — no row, no
  gap entry, nothing to notice.
- **The gate does not read this file**, deliberately. So nothing could have caught
  either.

The lesson generalises past invariants, and it is the reason the ledger is JSON
rather than a nicer table: **a coverage claim that names a file has to be checked
against the filesystem, and prose cannot be.** A ✅ next to a filename that does not
exist is worse than no document, because it answers "is this covered?" with a
confident yes.

The `🔍 Needs verification` rows are the second half of the same problem — a hedge
recorded on 2026-05-29 and never resolved across the nine releases since. Where the
ledger cannot say, it says `unrecorded`, and the gate prints that state on every run
rather than leaving it as a symbol nobody sweeps.
