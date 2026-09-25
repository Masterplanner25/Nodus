# v5.15.0 — Stage 6 downstream republish sweep

**Date:** 2026-09-25
**Verdict:** **Ranges and drift clean. Two non-PyPI consumers still owed.**

Four questions, three of them tooled. Stage 6 exists because the first three are
invisible to everything earlier in the sequence: Gate 10 validates nodus-lang
against itself and against companion *suites*, neither of which can see a
published range that no longer resolves or a wiki page nobody has read since
v4.1.1.

---

## 1. Do published ranges still admit the new version?

```
python -m tools.check_downstream_constraints
```

| companion | published | nodus-lang range | verdict |
|---|---|---|---|
| nodus-a2a-wire | 0.1.0 | `>=4.0.0` | ok |
| nodus-extension | 0.1.2 | `>=4.0.0` | ok |
| nodus-jupyter | 0.1.0 | `>=4.0.0` | ok |
| nodus-mcp | 0.1.4 | `>=4.0.0` | ok |
| nodus-mcp-server | 0.1.14 | `>=4.0.5` | ok |
| nodus-native-memory-engine | 0.1.1 | `>=4.0.0` | ok |
| nodus-sdk | 0.1.3 | `>=4.0.0` | ok |
| nodus-workflow-ai | 0.1.0 | `>=5.8.0` | ok |

**All 8 admit 5.15.0.** Resolved with `packaging` against *published* metadata,
never read by eye: `>=4.0.0,<5.0.0` reads as "admits 4.x", which is what the eye
checks for, and the clause that forbids the new version sits at the far end of
the string. Five of six companions once published that cap, which made 5.0.0
`ResolutionImpossible` for anyone with the ecosystem installed — found by the
aindy-runtime team, not by us (#445).

## 2. Has any companion drifted from what it published?

```
python -m tools.check_publish_drift
```

**First run: one SKIP and one DRIFT.**

```
nodus-a2a-wire   SKIP    no checkout at C:\codev\a2a-wire-pub
nodus-mcp        DRIFT   differs: src/nodus_mcp/__init__.py
```

### The SKIP was a second copy of a path I had already fixed

`nodus-a2a-wire` moved from `C:\codev` to `C:\dev`. Gate 10a had already exited
**2** on the stale path in `tools/nodus_lang_dependents.json`, and that was
corrected before the publish — but `check_publish_drift.py` carries its **own**
hardcoded path table, so the same move broke it twice and fixing one left the
other skipping.

That is the recurring shape at the tooling layer. #810 unified the *membership*
lists — which companions declare a nodus-lang dependency — and left the
**paths** duplicated, so a checkout that moves still has to be corrected in two
places. Both are now correct and the comment at the second site says so rather
than leaving the next reader to rediscover it.

A skip is not a pass — *a companion that could not be checked is not a companion
that passed* — which is why the tool exits 2 on one.

**Second run: `nodus-a2a-wire` ok, 9 files identical to 0.1.0.** Every other
companion identical to its published release.

### The DRIFT is intended, and is the fix for a defect the gate found

`src/nodus_mcp/__init__.py` differs from published 0.1.4 because Gate 10a caught
nodus-mcp's two version sources disagreeing — `__init__.py` at `0.1.3`,
`pyproject.toml` at `0.1.4` — and it was corrected (`51cb91d`).

So **the published nodus-mcp 0.1.4 reports the wrong version**: `nodus-mcp
--version` and both serve banners print 0.1.3. PyPI is immutable, so 0.1.4 keeps
it. The drift is the correction sitting unpublished.

**Owed: a nodus-mcp 0.1.5**, or an explicit decision to leave 0.1.4's banner
wrong until its next release for another reason. Not taken unilaterally here —
it is a second package's publish, and irreversible.

## 3. Non-PyPI consumers left stale

```
python -m tools.nodus_gate.cli --consumers
```

| consumer | tracks | state |
|---|---|---|
| nodus-vscode (0.1.5) | `keywords` | **in step** — this release adds no keyword |
| nodus-run-action (**v1.0.16**) | `nodus_version` | **republished** |
| nodus-wiki (**b9550c2**) | `nodus_version` | **republished** |

Both stale consumers track `nodus_version`, so they go stale at *every* bump by
construction. That is the design and not a nuisance: a wiki nobody has looked at
since the last release is exactly the thing to be told about. The wiki documented
v4.1.1 for twelve minors — across the 5.0.0 major, whose deny-by-default change
breaks embedders — with 1 of its 26 pages mentioning 5.x at all.

`nodus-vscode` is genuinely in step: it tracks the keyword set, and 5.15.0 adds
no keyword. Its fingerprint is unchanged, so no VSIX is owed.

**Both are republished, and the flags were cleared only afterwards** —
`fingerprint` and `published` move in this same commit, because a flag cleared
before the work is done is worse than no flag. `--consumers --strict` now reports
**3/3 in step**.

### nodus-run-action v1.0.16

The two pinned `version:` examples moved to 5.15.0 — the pin is what a new user
copies, so a stale one hands them an old runtime.

It also surfaced something the fingerprint does not track: **the floating `v1`
tag had not moved since the 5.9.0 cycle**, six releases, while the README tells
everyone to use `@v1`. Checked before moving it rather than assumed —
`git diff v1 HEAD` touches `README.md` only and `action.yml` is byte-identical,
so no consumer's behaviour changes and what `@v1` was shipping was a README
pinning 5.9.0. Moved to the new commit.

### nodus-wiki b9550c2

Four currency banners, plus two the version fingerprint caught only indirectly:

- **`_Sidebar.md` said `## Nodus v5.12`** — stale by three releases, and
  invisible to a grep for the *current* version, which is exactly why the gate
  tracks a fingerprint rather than scanning for a string.
- **`Security.md`'s supported-versions table named v5.13.x as latest** — stale by
  two. On a security page that is the kind of staleness that actively misinforms.

Content, per the convention that each release's wiki commit carries the thing a
production reader needs: a Security paragraph on #873 (a resume inheriting no
bounds) and #868 (the cross-tenant agent-registry leak through module
functions), and the **reject-and-revise recipe** on the Workflows page, which had
documented `resume_workflow(id, "checkpoint")` as though #482 had never refused
the payload form.

**The two `Since v5.14.0 …` sentences on Security were deliberately left alone.**
They are *as of* claims — they say when something arrived and stay true — and
bumping them would make the page lie about which release introduced the serve
budget. Same distinction `tools/version_claims.json` encodes upstream.

`Embedding-API.md` was checked against the real constructor rather than trusted:
**27 documented, 27 in the signature**, all three capability flags present. No
change needed.

Every claim and the code example on the Workflows page were run against the
**published** 5.15.0 before the push. That wiki has no PR and no CI — a push goes
straight to the reader — so nothing else would have checked them.

## 4. Work left behind in a checkout

`git status` across the registered checkouts: clean, except `nodus-mcp`, whose
one-line version fix is committed and pushed (`51cb91d`) and awaits the release
decision above.

---

## Summary

| Question | Answer |
|---|---|
| ranges admit 5.15.0 | **8/8 yes** |
| companions drifted | **1 — nodus-mcp, intended, needs 0.1.5** |
| non-PyPI consumers stale | **0 — both republished, 3/3 in step** |
| work left in a checkout | none uncommitted |

Two tooling fixes landed as part of this sweep: the `nodus-a2a-wire` path in
both registries. Neither is a nodus-lang defect; both would have silently
degraded the next release's gates.
