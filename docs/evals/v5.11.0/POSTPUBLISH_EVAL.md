# v5.11.0 — Stage 5 post-publish eval

**Verdict: the published package works as a new user would expect.** 6 of 7
checks passed on the first run; the seventh was my own test being wrong, and
chasing it produced the one finding worth having.

| | |
|---|---|
| Installed | `pip install nodus-lang==5.11.0` into a fresh venv, from PyPI |
| Resolved | `…/.venv-stage5/Lib/site-packages/nodus`, version **5.11.0** |
| Checks | **6/7** — see §3 for the seventh |
| Finding | one, pre-existing, coverage rather than behaviour (§4) |
| Release action | **none** — nothing here supersedes 5.11.0 |

---

## 1. Publication is confirmed by installing it, not by asking

```
pip install nodus-lang==5.11.0
resolved: …\.venv-stage5\Lib\site-packages\nodus
version:  5.11.0
```

PyPI's JSON API serves stale data after an upload — it has reported the previous
release as latest, and at 5.6.0 reported **zero files** for the version that had
just landed. Only an install is authoritative, and that is what this records.

## 2. The checks, and why they are shaped this way

They deliberately **combine** features rather than probing each alone. 5.7.1
shipped a defect that every single-feature probe passed: three features touched
one vocabulary, landed in sequence, and the last silently falsified prose written
for the first two. Only a program using two features together found it.

The program used here is one a new user might plausibly write — a workflow whose
steps share a `barrier` state cell, a local module handed a closure, and a
`std:loop` poll — rather than a feature checklist:

| check | result |
|---|---|
| `nodus --version` reports 5.11.0 | PASS — `Nodus 5.11.0` |
| startup is not paying for a web server (#173) | PASS — best of 3: **816 ms** |
| importing the CLI pulls in no web framework | PASS — `[]` for fastapi/uvicorn/starlette |
| module + closure + barrier + `std:loop`, together | PASS — `published 2 pages for acme`, poll **156 ms** for 3×50 ms |
| the barrier reader saw both writers with no `after` | PASS |
| `nodus check` accepts it | PASS — `site.nd: OK` |
| `nodus fmt --check` is clean | **FAIL** — see §3 |

The fourth is the one that matters: a root-program closure passed into a module
and spawned there (#783), a `barrier` cell joined without an `after` clause
(#578), and `std:loop` timers (#182), in one program. Each is new or newly fixed
this release; none of them is exercised by the others' tests.

## 3. The seventh check was wrong, not the release

`fmt --check` reported `File not formatted: site.nd`. That is **correct** — the
program was hand-written and not in canonical form. The check asserted a property
of my test file, not of the release.

Worth chasing anyway, because the failure mode it *could* have been is #657:
`fmt` silently dropping a **new field** on an existing node, which is precisely
what `barrier: true` is this cycle. Formatted and diffed:

```
state pages_done = 0i with { barrier: true, merge: "sum" }   # unchanged
```

Every other difference was cosmetic (one-line step bodies expanded, blank lines
normalised), and the formatted program produced identical output. So `fmt`
round-trips the new field.

## 4. The finding: correct behaviour, no guard

**`barrier` had no case in `tests/test_formatter_round_trip.py`.**

That file exists because the node-level completeness guard cannot see a new
*field* — #656/#657, where `each` and `budget { limits }` were dropped silently
by a released `fmt`. Its corpus is **hand-maintained**, and #578 added `barrier`
without adding a case. Its docstring claimed any new field was covered "by
construction", which is the more dangerous half: it is covered once a case
exercises it, and not before.

Nothing was broken — `fmt` renders `barrier` correctly today. But this is exactly
the state #656 was in the day before it broke, and a green run looks identical
either way.

**Fixed in the same pass**: two cases added (`barrier` alone, and `barrier` with
a fold), and the docstring corrected to say the corpus is hand-maintained. Both
cases were falsified — a formatter neutered to drop `barrier` turns them red.

**This does not supersede the release.** The defect is in test coverage, not in
5.11.0's behaviour, and the coverage gap predates it by a release. 5.7.0's rule —
stop between PyPI and the GitHub release when a fix will supersede the version —
is explicitly about a defective release, and this is not one.

## 5. What this stage did not check

Companion compatibility and downstream staleness — those are Stage 6, recorded in
`STAGE6_DOWNSTREAM_SWEEP.md`. Gate 10's local-wheel adversarial run is in
`CREATOR_VALIDATION.md`. The three answer different questions on purpose.
