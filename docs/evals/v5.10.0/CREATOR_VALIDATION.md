# v5.10.0 — Gate 10 creator validation

**Verdict: ship.** Both halves pass against the built wheel — but only after the
gate stopped the release once and the tag was moved. That is the part of this
record worth reading.

| | |
|---|---|
| Tag | `v5.10.0` → `d2c00c3` (**moved** from `a1d65c2`; see below) |
| Artifacts | `nodus_lang-5.10.0-py3-none-any.whl`, `nodus_lang-5.10.0.tar.gz`, `twine check` PASSED |
| Gate 10a | **6/6 dependent suites**, 721 tests — after one exit-3 and three serial re-runs |
| Gate 10b | **94/94 probes** against the installed wheel (93/94 on the first build) |
| Suite | 3,625 passed, 8 skipped |
| `nodus_gate --all` | 8 phases green; `--closed-issues --section 5.10.0` 25/25 |

---

## Gate 10b found a real defect, and the release stopped

The first build scored **93/94**. The failure:

```
[FAIL] #167: extensions= withholds a domain surface, None carries it
       a misspelled extension was accepted
```

Reduced against the wheel:

```python
VM(extensions=["workfow"])            # refused immediately
NodusRuntime(extensions=["workfow"])  # accepted at construction
```

A `NodusRuntime` does not build a VM until it runs something, so the misspelled
surface was accepted and then raised a **bare `ValueError` out of the first
`run_source`** — which breaks that method's documented contract of *always*
returning a result dict (`embedding-nodus.md` §2: *"Every `run_source()` call
returns a plain dict"*).

It also falsified a claim made in two places, both illustrated with a
`NodusRuntime` example:

> **An unknown extension name is refused at construction**, listing the known ones.

**The documentation was right and the code was wrong.** The fix (#765) makes the
claim true rather than softening it to match the behaviour — the rarer and better
direction to resolve that kind of mismatch.

### Three things this cost, and what each teaches

**1. The duplication was in *timing*, not content.** The two validation sites
agreed completely about *what* was a valid extension name. They disagreed about
*when* they would say so, and only one of those moments is the one a host
experiences. Every previous instance of this codebase's signature shape has been
two sites giving different *answers*; this is the first where they gave the same
answer at different *times*. Worth adding to the mental catalogue: "one question,
two places" includes "one question, two moments".

Fixed as one `capability.validate_extensions`, called from both, with a source
assertion that neither re-implements it.

**2. The suite could not have caught it.** Every test in
`tests/test_domain_extensions.py` constructs a `VM` directly. Nothing exercised
`NodusRuntime`, which is the *documented* embedding entry point — so **the tested
path and the documented path were different ones**, and a full green suite said
nothing about the interface users actually touch.

This is #691's lesson recurring: there, every test and probe for `retry.until`
ran inside `fn main()`, so a step-body-only defect was invisible to the suite,
nine gate phases and 83 probes. The rule generalises past both: **test the
construct where its documentation says to use it**, not where it is convenient to
construct.

**3. The probes had to be written before the tag to find it.** They were, per the
rule added at 5.1.0. Had they been written after tagging, the choice would have
been shipping a false claim or a `5.10.1`.

### The tag moved, and that was safe — checked, not assumed

Before deleting it, both were verified:

```
gh release view v5.10.0   -> release not found
pypi.org/pypi/nodus-lang/5.10.0/json -> 404
```

Release immutability attaches to a *published release*, not to a tag, so with
neither existing the tag could be repointed at the fix. This is the whole reason
Gate 10 sits between the tag and the upload rather than after it.

---

## Gate 10a — dependent suites, before the upload

Run with nothing else going, per the rule added after 5.1.0 reported a spurious
`nodus-mcp FAIL` while a clean-venv probe ran alongside it.

| companion | result |
|---|---|
| nodus-mcp | 363 passed |
| nodus-mcp-server | 25 passed |
| nodus-extension | 126 passed |
| nodus-sdk | 99 passed |
| nodus-native-memory-engine | 76 passed |
| nodus-jupyter | 32 passed |

**The first run after the fix exited 3, not 0** —
`nodus-mcp::test_m2_bearer_wrong_returns_401`, matching a recorded flake. The
tool says exactly what to do with that, and it is not "proceed":

> Not a pass. Re-run those suites serially… a recorded flake is a reason to look
> again, never a reason to skip looking.

Re-run serially: the file green twice (15 passed each), the full suite green
twice (363 passed each). Only then treated as satisfied.

One reading trap worth recording: the shell reported `exit: 0` because the
command was piped through `tail`, which reports *its own* status. The tool's
verdict was in its text, not its exit code as observed. Read the words.

---

## Gate 10b — 94 probes against the installed wheel

The header confirms the tree before anything runs, which is the check that exists
because 5.0.3 shipped past 32 green probes run against the source tree, and it
recurred at 5.5.0 and 5.6.0:

```
package   C:\dev\Coding Language\.venv-validation\Lib\site-packages\nodus
version   5.10.0
```

**It fired again this cycle**, during setup: an interactive check run with the
working directory inside the repo resolved `nodus` to `src/nodus` despite the
wheel being installed. Not a probe run — but the same trap, on the same day,
which is why `--require-installed` exists rather than a paragraph asking people to
read a header.

Six probes are new for 5.10.0:

| probe | what it pins |
|---|---|
| `#754` serve confinement | submitted code refused, granted explicitly, **and a control that must run** |
| `#167` extensions | `None` carries every surface, `[]` withholds, a typo is refused |
| `#181` deliver | found by event type, run carried forward, matching nothing is not an error |
| `#174` store warning | quiet when empty, one actionable warning when runs are at risk |
| prose | no artifact still calls 5.9.0 current |
| prose | the README banner names `serve` and how to grant what it now denies |

The `#754` probe's control is load-bearing. The very first reproduction attempt
for that issue wrapped its code in `fn main()` and read the resulting empty
stdout as a refusal, when the program had never executed. Every refusal probe
here is paired with a program that must succeed.

---

## Supporting gates

- **Suite** — 3,625 passed, 8 skipped. Its one failure was the README's
  `**Recent:**` claim, deliberately moved to 5.10.0 ahead of the bump.
- **`--versions` after the bump** — named **10 stale claims across 8 files**,
  including the skill an agent installs and two project templates users copy
  into their own repos. All updated; 13/13 after.
- **`--closed-issues --section 5.10.0`** — 25/25. Run against the cut section
  because `--all` scans an empty `[Unreleased]` after the cut and reports
  `0 passed, 0 failed, 0 missing` — a pass that checked nothing.
- **`--consumers`** — `nodus-run-action` stale, tracking `nodus_version` at
  `5.9.0`. Deferred to Stage 6, which is where it is cleared.
- **ruff, mypy, `.nd` format, keyword coverage** — clean; 61 `.nd` files formatted.

---

## Verdict

**Ship.** The one defect Gate 10 found is fixed in the artifact being uploaded,
its test gap is closed, and the claim it falsified is now true. The gate did the
job it exists for: it caught, before anything immutable was created, a runtime
that did not do what its own documentation promised.
