# v5.5.0 — Stage 6 downstream sweep

After publish. Four questions, three of them tooled, and the fourth done by hand because
nothing can automate "is there work left in a checkout".

---

## 1. Do published ranges still admit the new version?

`python -m tools.check_downstream_constraints` — resolves **published** PyPI metadata, not
the local checkouts, because a floated cap sitting unreleased in a companion's `main`
helps nobody.

| companion | published | range | verdict |
|---|---|---|---|
| nodus-mcp | 0.1.3 | `>=4.0.0` | ok |
| nodus-mcp-server | 0.1.12 | `>=4.0.5` | ok |
| nodus-extension | 0.1.2 | `>=4.0.0` | ok |
| nodus-sdk | 0.1.2 | `>=4.0.0` | ok |
| nodus-native-memory-engine | 0.1.1 | `>=4.0.0` | ok |
| nodus-jupyter | 0.1.0 | `>=4.0.0` | ok |

**All 6 admit 5.5.0.** None caps, per the policy set on 2026-08-17.

### A downstream report this cycle proved the tool's worth

A user upgrading a project venv hit `nodus-extension 0.1.0 requires nodus-lang <5.0.0` and
concluded — reasonably — that the fix was an upstream release. It was not: the published
`nodus-extension` is **0.1.2** and has floated since #445 on 2026-08-17. Their venv held a
stale **0.1.0**; `pip install -U nodus-extension` was the whole fix.

The distinction matters because the two look identical from inside a venv and lead to
opposite actions — wait for a release, or update a package. The rule that settles it is the
one CLAUDE.md already states: do not read a range by eye, run the script, and note that it
resolves *published* metadata.

---

## 2. Has any companion drifted from what it published?

`python -m tools.check_publish_drift` — downloads each published sdist and compares file
contents. Not a git heuristic: counting commits since the version bump gave four false
positives at v4.2.0, because a commit can touch only docs, only CI, or only tests.

**9/9 identical, exit 0.** nodus-a2a, nodus-extension, nodus-jupyter, nodus-mcp,
nodus-mcp-server, nodus-memory, nodus-native-memory-engine, nodus-sdk, nodus-store-sql.

Exit 0 and not 2 — no companion was skipped, and a skip is not a pass.

---

## 3. Which non-PyPI consumers has the release left behind?

`nodus_gate --consumers`. Both are invisible to the content-hash sweep above because
neither is on PyPI, which is the whole reason this phase exists.

| consumer | before | after |
|---|---|---|
| nodus-vscode (0.1.3) | ok — keywords unchanged | ok |
| nodus-run-action (v1.0.5) | **NEEDS REPUBLISH** — `nodus_version` 5.4.0 → 5.5.0 | ok (v1.0.6) |

**nodus-vscode needed nothing.** No keyword was added or removed in 5.5.0, and the gate
fingerprints the keyword set rather than the release number, so it correctly stayed quiet.

**nodus-run-action was republished.** Its README pins a `nodus-lang` version in the CI
examples new users copy, so a stale pin hands them an old runtime. The pins moved 5.4.0 →
5.5.0, tagged **v1.0.6**, and the floating `v1` tag was moved to match:

```
209f478  refs/tags/v1
209f478  refs/tags/v1.0.6
```

Verified by resolving both refs rather than by `rev-parse` on the tag name, which returns
the tag object rather than the commit for an annotated tag and has misled this check before.

`tools/consumers.json` was updated **after** the republish, with `fingerprint` and
`published` moved in the same edit. A flag cleared before the work is done is worse than no
flag.

---

## 4. Is there work left behind in any checkout?

By hand, because nothing automates it.

All **12** sibling checkouts clean, no uncommitted work:

nodus-mcp · nodus-a2a · nodus-memory · nodus-native-memory-engine · nodus-extension ·
nodus-mcp-server · nodus-jupyter · nodus-vscode · nodus-run-action · nodus-workflow ·
nodus-sdk · nodus-store-sql

(nodus-jupyter and nodus-store-sql are on `master` rather than `main` — long-standing,
recorded in the 2026-07-05 sweep, not drift.)

---

## Verdict

**Clean.** 6/6 ranges admit 5.5.0, 9/9 companions match what they published, 2/2 non-PyPI
consumers in step after one republish, 12/12 checkouts clean.

### Not measured this cycle

**Throughput.** 5.5.0's runtime changes are a guard on closure entry and a deadline read
moved earlier on the same thread; neither was expected to be measurable. But "not expected
to be" is not a measurement, and it is stated that way here rather than implied — the same
note 5.4.0 carried.
