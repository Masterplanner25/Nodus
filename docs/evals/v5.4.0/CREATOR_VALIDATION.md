# Gate 10 — Creator validation, v5.4.0

**Pre-publish.** Run against the built wheel in a clean venv, before the PyPI
upload. Answers *"what can I make fail?"* — as distinct from Stage 5, which asks
*"does this work as a new user would expect?"* against the published package.

| | |
|---|---|
| Tag | `v5.4.0` at `3649c2a` |
| Artifact | `dist/nodus_lang-5.4.0-py3-none-any.whl` (452 KB), built from the tagged tree |
| Clean venv | `C:\dev\nodus-540-clean\cv` — resolved `…\cv\Lib\site-packages\nodus`, version `5.4.0` |
| Verdict | **Pass.** 35/35 release-claim probes, 9/9 adversarial boundaries, 6/6 dependent suites |

The resolved package path and version are printed by both probe scripts before
any result, because validating the wrong tree is the failure this gate has
already had once (5.0.3 shipped past 32 green probes run against a tree that was
not the one being released).

---

## Gate 10a — dependent suites, before the upload

`python -m tools.check_dependent_suites`, run with nothing else going.

| Companion | Result |
|---|---|
| nodus-mcp | 363 passed (see below) |
| nodus-mcp-server | 25 passed |
| nodus-extension | 126 passed |
| nodus-sdk | 99 passed |
| nodus-native-memory-engine | 76 passed |
| nodus-jupyter | 32 passed |

**721 companion tests green.** The first run exited **3** — one red suite whose
only failure matched a recorded flake — which the gate states plainly is *not* a
pass: *"Re-run those suites serially… a recorded flake is a reason to look again,
never a reason to skip looking."* So it was looked at:

`nodus-mcp` `test_phase_m.py::test_m2_bearer_wrong_returns_401`, failing with
`httpx.ReadError`. Twelve runs against the 5.4.0 source: **two full serial suite
runs green (363/363 each)**, the file alone 6/7, the single test 3/3. Three runs
of the same file against the *installed* 5.0.0 were also green. So the failure is
the documented port-binding race, not a 5.4.0 regression — 5.4.0's scheduler
changes touch Nodus channels, and this test is a Python `ThreadingHTTPServer`
binding a port, which shares nothing with them.

**One correction to record**, since a flake entry's `why` is supposed to say what
was actually established: `tools/dependent_flakes.json` states these tests *"pass
individually and in serial full-suite runs"*. The second half held (2/2). The
first did not — running the file alone failed once in seven. Filed as a
follow-up rather than edited during the release; the entry's classification is
right, only its evidence sentence is over-stated.

---

## Gate 10b — release-claim probes

`tests/eval/release_claims_probe.py`, the durable script from 5.2.0, extended
with 11 probes for 5.4.0. **35/35 pass** against the wheel.

**Written before the tag**, per the rule that has now paid for itself three
cycles running — and it paid again. Three findings, all caught while a fix was
still possible:

1. **`docs/governance/TECH_DEBT.md` still listed #400, #401 and #402 as open
   debt** — all three fixed in this release. A live debt register describing
   fixed work is the exact staleness class this probe exists for. Rewritten as
   RESOLVED entries naming what shipped.
2. **One of my own probes cried wolf on correct prose.** `probe_topology_validation`
   asserted `"Dependency cycle"` did not appear in the validator's *source* — and
   failed, because the docstring explains the false diagnosis the validator
   exists to prevent. A probe that flags true sentences gets switched off, so it
   was rewritten to assert on the raised message and to exercise the validator
   directly (drifted shape refused, matching shape accepted).
3. **Two artifacts were flagged that should not have been**, and the exemption
   list is now argued rather than globbed: `EXTERNAL_AUDIT_LEDGER.md` records
   what an outside audit claimed *at a named commit*, and `Session Handoff
   Summary.md` is untracked working scratch that never reaches a user. Both are
   records of what *was*, the same class as evals and the CHANGELOG.

The stale-claim pattern is held to both directions by
`probe_5_4_pattern_selfcheck`: **7 stale forms it must catch, 5 true sentences it
must ignore.** A prose probe that cannot fail is worse than none.

---

## Gate 10b — adversarial boundaries

`adversarial.py` in the clean venv. **9/9 held.** Every probe carries a positive
control, per the 5.3.0 lesson: *a refusal that reports "it did not happen" proves
nothing unless the permitted case is shown to succeed.*

| # | Boundary attacked | Verdict |
|---|---|---|
| A1 | A step's `with { }` option executing code during a static plan | **held** — option not evaluated; control wrote the marker under `--execute` |
| A1b | A `state` initializer executing during a static plan | **held** — not run; `nodus run` control fired it |
| A1c | An imported module's top-level effect firing during a static plan | **held** — import dropped before compilation, plan still produced |
| A2 | `allow_failure` leaking into downstream readiness | **held** — dependent still `upstream_failed`; undeclared failure still fails the run |
| A3 | A hand-edited topology smuggling a different graph through resume | **held** — 4/4 drifts refused (added, removed, rewired, legacy name-only); matching shape passes |
| A4 | A `durable: false` cell's live value reaching a persisted artifact | **held** — 6 snapshots hold the durable cell, none hold the non-durable one |
| A5 | `try`/`finally` swallowing an error or skipping cleanup | **held** — propagates on throw, runs on success, inner-before-outer ordering |
| A6 | Deny-by-default eroding on the wheel | **held** — 2/2 refused; granted subprocess runs (control) |
| A7 | A bounded channel losing a value or hanging silently | **held** — 3 values through a size-1 channel in order; stuck sender still detected |

**Two probes failed their first run, and both failures were the probe's fault —
which is the guard working.**

- **A1b was vacuous.** Its control used `--execute` over a script calling
  `plan_workflow`, and `plan_workflow` deliberately does not initialise state —
  so *neither* mode could fire the marker and a HELD verdict would have proved
  nothing. Corrected to use `nodus run`, which does run the initializer.
- **A4 was a false positive.** It matched the raw text `"ch"`, which appears in
  `metadata.state_policies` as `{"ch": {"durable": false}}` — the cell's
  *declaration*, which is how the runtime knows it is non-durable, not its value.
  Inspecting the artifacts directly showed every state snapshot holding only the
  durable cell. Corrected to assert on the snapshots.

Recording both is the point: the first was the vacuity guard catching me, the
second was me nearly reporting a defect that did not exist. The 5.3.0 cycle
produced one of each; so did this one.

---

## What this gate did not cover

- **Stage 5** — the published package, installed as a new user would. Separate
  document.
- **Stage 6** — downstream ranges, publish drift, non-PyPI consumers. Separate
  document. `nodus_gate --consumers` already reports `nodus-run-action` as needing
  republishing (its README pins `5.3.0`), which is Stage 6 work by design: the pin
  should name a version that is actually on PyPI.
- **Throughput.** Unmeasured this cycle. 5.2.0's event-retention change was the
  last deliberate performance move; 5.4.0's scheduler additions are a set
  membership test per loop iteration and were not expected to be measurable, but
  "not expected to be" is not a measurement.
