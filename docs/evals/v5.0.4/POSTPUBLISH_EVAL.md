# Stage 5 — post-publish eval, v5.0.4

**Date:** 2026-08-17 · **Verdict: clean, no new findings.**

Run against the **published** package from PyPI, in a fresh venv, outside any
Nodus project.

---

## 0. What this release is

5.0.4 repairs one thing 5.0.3 broke and closes the gate gap that let it ship.
So this eval's load-bearing question is narrow: **does the combination that was
broken now work, installed from PyPI?**

## 1. Install

```
$ pip install nodus-lang==5.0.4
$ nodus --version
Nodus 5.0.4
```

The index lag recurred — the first install in a fresh venv did not produce a
console script, and a moment later the same venv resolved 5.0.4 cleanly as a
dependency of nodus-sdk. This is the third publish of four where the first check
after upload disagreed with the index. Treat it as normal: **check the simple
index, never re-upload on a first check.**

## 2. The 5.0.3 break, from PyPI

```
nodus-lang 5.0.4 + nodus-sdk 0.1.2
NodusSDKRuntime() constructs : True
memory still isolated (#185) : nil
```

Both halves matter. The first is the regression: under 5.0.3 this raised
`AttributeError: property 'memory_store' ... has no setter` and nodus-sdk went
from 99 passed to 29 failed and 10 errors. The second is the control — the #185
isolation the rename could plausibly have undone is intact, so the repair did not
buy compatibility by reverting the fix.

## 3. New-user flow

```
$ nodus init
$ nodus run src/main.nd
hello from nodus
```

## 4. Cross-checks against the release claims

| Claim | Verified how |
|---|---|
| "5.0.3 broke nodus-sdk at construction" | reproduced before the fix; `NodusSDKRuntime()` now constructs against the published 5.0.4 |
| "no change needed on nodus-sdk's side" | published nodus-sdk **0.1.2**, unmodified since the cap float, passes |
| "the #185 isolation is unchanged" | a second runtime still reads `nil`, not the first's secret |
| "dependent suites now run before the upload" | Gate 10 step 0, 6/6 pass — recorded in `CREATOR_VALIDATION.md` §0 |
| README banner is current | "Recent: 5.0.4" written before the tag, so the PyPI page is correct |

## 5. Findings

**None.** The one thing worth carrying is not a defect in 5.0.4 but the lesson
that produced it, now recorded in `RELEASE_GATES.md`: Gate 10 validated
nodus-lang against itself and passed 5.0.3 with 32 green probes, because nothing
in it constructed a dependent. A gate that only tests a project against itself
cannot see a break it causes in its consumers.

## 6. Not covered

- **Windows only.** `py3-none-any` wheel, so platform risk is low.
- **The other five companions** were exercised by Gate 10 step 0 against the
  checkout, not re-installed from PyPI alongside 5.0.4 here; only nodus-sdk was,
  because it is the one 5.0.3 broke.
- **Coverage** not re-measured; the baseline is over 300 tests stale.
