# v5.2.0 — Creator Validation (Gate 10, pre-publish)

Adversarial validation of the built wheel **before** the PyPI upload.
Prompt: `docs/governance/EVAL_PREPUBLISH.md`. Template:
`docs/governance/EVAL_STAGE4_TEMPLATE.md`.

| | |
|---|---|
| Tag | `v5.2.0` → `90eea2f13a6c847f4dd0edc37720e495be291968` |
| Artifacts | `nodus_lang-5.2.0-py3-none-any.whl`, `nodus_lang-5.2.0.tar.gz` |
| Built from | the tagged tree (`HEAD == v5.2.0` verified before building) |
| Date | 2026-08-24 |
| Verdict | **PASS** — cleared for upload |

---

## 0. Dependent suites — run before the upload

Gate 10 step 0. This is the check added because **5.0.3 shipped a broken
`nodus-sdk`**: #185 assigned `self.memory_store` on `NodusRuntime`, which
`NodusSDKRuntime` subclasses with `memory_store` as a read-only property, and
every construction of that subclass raised. Gate 10 passed then with 32 green
probes, because it validates nodus-lang against *itself* and nothing in it
constructs a dependent.

```
companion                      verdict   detail
------------------------------------------------------------------------------
nodus-mcp                      PASS      363 passed in 37.07s
nodus-mcp-server               PASS      25 passed in 0.86s
nodus-extension                PASS      126 passed in 29.51s
nodus-sdk                      PASS      99 passed in 6.34s
nodus-native-memory-engine     PASS      76 passed in 1.41s
nodus-jupyter                  PASS      32 passed in 1.57s

All 6 dependent suites pass.
```

**721 tests, exit 0, green on the first run** — no re-runs, no recorded flakes
consulted. Run with nothing else going, which is what 5.1.0 had to learn: there,
`nodus-mcp` went red while a clean-venv install ran alongside it and needed three
serial re-runs to clear.

This release changed `NodusRuntime`-adjacent surfaces (the event bus, per-step
state records), so a dependent break was a live risk rather than a formality.

---

## 1. Adversarial probes against the wheel

`tests/eval/release_claims_probe.py`, run by the **clean venv's** interpreter with
no `PYTHONPATH`. New this cycle: the probes are a durable script rather than
ad-hoc, and they are written **before** the tag.

The header is the point — 5.0.3 passed 32 probes against a tree that was not the
one being shipped:

```
  package   ...\scratchpad\wheelvenv\Lib\site-packages\nodus
  version   5.2.0
  import    ...\scratchpad\wheelvenv\Lib\site-packages\nodus\__init__.py
```

**15/15 passed.**

| probe | result |
|---|---|
| `merge: "sum"` combines concurrent contributions | the #485 reproduction totals 2 |
| `append` and `union` land; `union` deduplicates | `LOG=2 SEEN=3` |
| `=` on a folded cell is refused at compile time | refused before the program runs |
| a record element in a `union` contribution is refused | names the workaround and #545 |
| conflict warning: silent on agreement, loud on read-modify-write | both directions |
| `graph show` renders Mermaid and DOT | levels pinned with `rank=same` |
| `doctor --json` parses, names the resolved package | 6 checks |
| `completion` emits four shells with LF endings | 4 shells |
| #532 `publish` parses `--project-root` | no longer publishes the CWD |
| #533 `graph`/`workflow --help` reach the real help | both |
| #522 a default run retains no VM bookkeeping | 0 retained, calls still counted |
| the stale-claim pattern is falsifiable both ways | 3 caught, 4 left alone |
| no artifact says a fold policy is unavailable | README, llms\*, guide, runtime |
| documented policy vocabulary matches the runtime | all 5 |
| every new command appears in `nodus --help` | doctor, completion, graph |

---

## 2. Standard eval scripts, through the wheel's own CLI

Run as `nodus run <script> --time-limit 120` using the venv's console script.

| script | exit | stderr | last line |
|---|---|---|---|
| `quirk_probe.nd` | 0 | empty | `ALL QUIRKS CONFIRMED` |
| `language_exerciser.nd` | 0 | empty | `ALL EXERCISES PASSED` |
| `framework_capabilities.nd` | 0 | empty | `ALL FRAMEWORK PROBES PASSED` |

---

## 3. Distribution metadata

```
Checking dist/nodus_lang-5.2.0-py3-none-any.whl: PASSED
Checking dist/nodus_lang-5.2.0.tar.gz: PASSED
```

- `nodus --version` → `Nodus 5.2.0`
- console scripts: `nodus`
- **Long description carries the 5.2.0 "Recent:" paragraph**, not 5.1.0's.
  `pyproject.toml` sets `readme = "README.md"`, so this is the permanent PyPI
  page — and release immutability means it cannot be corrected after upload.
  This was checked explicitly because 5.0.1 shipped a stale banner that
  <https://pypi.org/project/nodus-lang/5.0.1/> still displays.

---

## 4. `nodus doctor` from the installed console script

New command, and this is the first environment where it can do its job. #535
records that it could not diagnose the version gap it exists for until it
shipped:

```
[  ok  ] nodus package: 5.2.0 from installed package at ...\wheelvenv\Lib\site-packages\nodus
[  ok  ] version sync: installed nodus-lang==5.2.0 matches the imported module
[  ok  ] interpreter: CPython 3.11.9 at ...\wheelvenv\Scripts\python.exe
[ warn ] optional extras: nodus-retry is not installed (@retry falls back to the in-memory effect store)
[  ok  ] project: no nodus.toml (running in script mode)
[  ok  ] workflow store: 5 recorded run(s)
No problems. 1 warning(s).
```

It correctly reports `installed package` as the origin here, where against the dev
checkout it reports `source checkout` and — before this bump — a **failing**
`version sync` (module 5.2.0 vs installed 5.1.0). Both directions observed.

The `nodus-retry` warning is correct: a bare venv has no `[retry]` extra, and that
absence changes `@retry` behaviour, which is why it is surfaced rather than
silent.

---

## 5. Gates

| gate | result |
|---|---|
| Full suite | 2536 passed, 3 skipped |
| `ruff` / `mypy` | clean |
| `nodus_gate --all` | PASS, all seven phases |
| — static | 135/135 symbols |
| — runtime | 244/244 doc blocks |
| — closed-issues (`--section 5.2.0`) | 5/5 |
| — contracts | 6/6 |
| — opcodes | 26/26, BYTECODE_VERSION 4 |
| — consumers | 2/2 in step |
| — versions | 11/11 claims agree with 5.2.0 |

**BYTECODE_VERSION stays 4 and the 49-opcode set is untouched** — a minor with new
DSL semantics, but no recompilation implied.

One `test_async_concurrency_timing` failure in the local full run. It passes in
isolation, and a *different test in that file* failed than in the previous run —
the machine signature `CLAUDE.md` documents. CI on a clean runner was green on
both PR head commits.

---

## 6. What the pre-tag probe work caught

The probes ran **before** the tag, which is the ordering CLAUDE.md requires and
which paid for itself again.

**A stale prose claim.** `docs/guide/workflows-and-tasks.md` still asserted a fold
policy was unavailable. That is the same shape as 5.1.0's four stale artifacts:
`STATE_MERGE_POLICIES` grew across three PRs this cycle — `(any, once)` →
`+ sum, append` → `+ union` — and the guide kept a sentence written at the middle
step. No behaviour test covers prose; nothing else would have found it.

**Then a defect in the probe itself.** The tightened pattern flagged *correct*
prose — "under a fold policy, `+=` contributes and `=` is refused", where what is
refused is the assignment form, not the policy. The pattern is now a named
constant with a self-check probe holding it to both directions: it must catch the
three sentences it was written for and leave four correct ones alone.

A prose probe that cries wolf gets switched off; one that cannot fail is worse
than none.

**A convention broken five times.** `[Unreleased]` had 3× `### Changed` and 2×
`### Added`, because each of five PRs prepended its own block — the exact failure
`CLAUDE.md` records having already untangled by script once. Merged before the
cut, verified lossless: same 13 entry bullets, same 2,940 prose words.

**The `--versions` gate's first real use.** Built this cycle. Run after the bump it
named all **nine** stale version claims with file, line and both values. Run
before the bump it passes by construction, which is why release step 4b exists.

---

## 7. Known issues shipping

- **#536** — `zsh` and `fish` completion scripts are structure-checked only;
  neither shell is installed on the dev box or CI. `bash` is execution-tested in
  the suite; the PowerShell check was manual and is not in the suite, so a machine
  without bash verifies nothing executable.
- **#537** — `graph show` does not draw a step's `on: [...]` filter, because the
  plan does not record it. An edge means "B depends on A", not "B runs if A
  succeeded". Stated in the renderer, the guide and the help.
- **#545** — records compare by identity, not by value, and the rule exists only in
  a `__eq__` body. Filed this cycle; it is why `union` refuses record elements
  rather than silently not deduplicating them.
- **#547** — the lost-update warning becomes an **error at 6.0.0**. Recorded in
  `COMPATIBILITY.md` under *Deprecated*, with the checklist on the issue.
- **#475** — a step failure still kills independent fan-out branches, and a join
  has no declared failure semantics. The barrier policy moved here from #485.
- **#380** — `LocalWorkflowStore.list_runs()` remains linear in accumulated runs.

**#535 is resolved by this release** — `nodus doctor` is now in a published
artifact, verified above from the installed console script. Close it after upload.

---

## 8. Not covered

- **zsh / fish completion execution** — see #536.
- **Cross-platform**: validated on Windows 11 / CPython 3.11.9 only. CI covers
  Linux for the suite but not the wheel install.
- **PyPy**: not exercised this cycle.
- **Upgrade-in-place from 5.1.0**: the clean venv installs 5.2.0 fresh. Stage 5
  covers the published-package path; an in-place upgrade over 5.1.0 is untested.
- **The `[retry]` extra**: not installed in the validation venv, so `@retry`
  against the durable effect store is unexercised here.
