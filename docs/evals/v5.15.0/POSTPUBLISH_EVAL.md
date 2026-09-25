# v5.15.0 — Stage 5 post-publish eval

**Date:** 2026-09-25
**Artifact:** `nodus-lang==5.15.0` installed from **PyPI** into a fresh venv
**Verdict:** **PASS — 8/8.**

Stage 5 asks a different question from Gate 10: not *"what can I make fail?"*
against a local wheel, but *"does this work as a new user would expect?"* against
the published package. It is the stage that caught #662 at 5.7.0 — by using two
new features in one program, where neither was broken alone.

---

## Install

```
pip install nodus-lang==5.15.0
```

Resolved from `site-packages`, not a checkout:

```
installed from PyPI: 5.15.0
resolved           : …\venv-pub\Lib\site-packages\nodus\__init__.py
```

**Index lag this cycle: none.** The install succeeded on the first attempt. That
is worth recording because it varies — 5.13.0's took nine minutes, and after
5.6.0's upload the JSON API reported *zero files* for the version that had just
landed. Only `pip install <name>==<version>` is authoritative; the JSON API and
the simple index both lag, and `Cache-Control: no-cache` does not prevent it.

---

## Checks

Each exercises something this release claims, through the surface a user would
touch rather than the internals the tests reach for.

| # | Check | Result |
|---|---|---|
| 1 | the CLI reports 5.15.0 | `Nodus 5.15.0` |
| 2 | a resumed step reaches a host tool (#868) | handler called once; the step got a record |
| 3 | a 40-day parked run is still listed (#869) | listed and sweepable at 40 days |
| 4 | reject-and-revise works (#870) | replays with the feedback, re-parks, `publish` does not fire |
| 5 | rehydrated data keeps its key order (#871) | `{"web": 1, "code": 2, "data": 3}` |
| 6 | a resume inherits the caller's bounds (#873) | all four bounds carried; steps are the remainder |
| 7 | the terminal cap holds (#875) | a cap of 2 leaves 2 files, aged records included |
| 8 | a plain script still runs (the control) | `hello from 2` |

**8/8 passed.**

Check 8 is the control and is not decoration: every other check exercises the
park-and-resume boundary, and without it the set would pass on a build where
ordinary `nodus run` was broken. Checks 4 and 6 each assert a *negative* as well
as a positive — that `publish` does **not** fire on a rejection, and that the
child's step budget is the remainder rather than a fresh allowance — because
both are the difference between the fix and a plausible wrong version of it.

---

## What this stage did not do

Stage 5 did not construct a dependent, which is Gate 10a's job and was done
before the upload (8 suites, 953 tests). It did not re-run the full nodus-lang
suite; CI did that on the release PR, on a clean runner, in both `unittest` and
`pytest` form.

No new issues were filed from this stage.
