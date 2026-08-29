# v5.7.0 — Gate 10 creator validation

**Date:** 2026-08-29
**Wheel:** `nodus_lang-5.7.0-py3-none-any.whl`, built from the tagged tree
**Tag:** `v5.7.0` → `5ea926da0a94ed43197c371d9ade8f674afbdd85` (equal to `HEAD` at build time)
**Verdict:** pass — cleared for upload

Gate 10 has two parts and the first is not optional. Both ran before any upload.

---

## Gate 10a — dependent suites, before the upload

```
PYTHONPATH="src;." python -m tools.check_dependent_suites
```

```
companion                      verdict   detail
------------------------------------------------------------------------------
nodus-mcp                      PASS      363 passed in 40.93s
nodus-mcp-server               PASS       25 passed in  1.13s
nodus-extension                PASS      126 passed in 31.58s
nodus-sdk                      PASS       99 passed in 13.76s
nodus-native-memory-engine     PASS       76 passed in  1.37s
nodus-jupyter                  PASS       32 passed in  2.96s

All 6 dependent suites pass.        exit 0
```

**721 companion tests, exit 0.** Exit 0 is the only clearing verdict: 1 is a new
failure, 2 is a missing checkout or a timeout — an unrun suite covers nothing —
and 3 means every failure matched a recorded flake, which changes the advice and
never the verdict.

This gate exists because 5.0.3 shipped past **32 green probes** and broke
`nodus-sdk` at construction: the probes validate nodus-lang against itself, and
nothing in them constructs a dependent. Two surfaces this release touches are
exactly the shape that caused it — `register_function` gained parameters (#493)
and `NodusRuntime.run_source` gained a pre-flight refusal (#489) — so a
dependent constructing a runtime or registering a host function is the case that
matters. `nodus-sdk` (99 tests) does both.

Run with nothing else going, per the standing note after 5.1.0's false red.

---

## Gate 10b — adversarial validation against the wheel

Clean venv, wheel installed, **run from a neutral CWD** with `--require-installed`.

### The wrong-tree check earned its place again

Running the same command with the repo as CWD first:

```
resolved from: C:\dev\Coding Language\nodus.py
```

That is the repo-root shim, not the wheel — the 5.0.3 failure mode exactly, and
the third release running in which it has appeared. Both version numbers agree
either way; only the path line reveals it. From outside the repo:

```
  package   ...\.venv-validation\Lib\site-packages\nodus
  version   5.7.0
  import    ...\.venv-validation\Lib\site-packages\nodus\__init__.py
```

### Result

```
71/71 probes passed
```

Twelve of those are new for this release, written **before** the tag — which is
the rule, because at 5.1.0 writing them early caught four artifacts describing a
vocabulary the release did not have, one of them `README.md`, which
`readme = "README.md"` makes the permanent PyPI page.

| Probe | Claim it holds to |
|---|---|
| `extern_declares_host_surface` | a file declaring an extern rejects an unknown call; a declared name is accepted |
| `extern_preflight` | an unregistered extern is refused **before running**; registering it makes the program run |
| `undeclared_file_unchanged` | a file with no `extern` still accepts unknown free calls — strictness is per file |
| `host_function_schema` | wrong argument types are refused; a registration without a schema is unchanged |
| `wait_payload_schema` | a payload violating the declared shape is refused at the resume call |
| `compensation_unwind_order` | `refund` (later) unwinds before `release` (earlier) |
| `compensated_run_is_terminal` | resuming a compensated run is refused, naming the reason |
| `failed_pass_does_not_satisfy` | a checkpoint recorded before a `throw` no longer satisfies `until` |
| `fmt_keeps_each` | a mapped step round-trips through `fmt` |
| `fmt_keeps_budget_limits` | single-dimension budgets format; `limits` survives |
| `new_keywords_named` | `extern` and `compensates` are in `ALL_KEYWORDS` (42 words) |
| `no_stale_5_6_current` | no artifact still calls 5.6.0 the current release |

The last is a **prose** probe, and prose probes are the half that has caught
things. It was checked against a deliberately stale line and observed to fail —
an absence assertion that cannot fail is worth nothing.

---

## Pre-tag gates

| Gate | Result |
|---|---|
| 1 — suite | pytest **2921 passed**, 8 skipped; `unittest` **2670 OK** |
| 2 — ruff / mypy | clean |
| 3 — `nodus_gate --all` | Static 136/136 · Runtime 263/263 · Contracts 6/6 · Opcodes 26/26 · Shapes 0 new |
| 3c — consumers | `nodus-vscode` **0.1.5 in step**; `nodus-run-action` stale (expected — Stage 6) |
| 3d — versions | **15/15 claims agree with 5.7.0**, re-run *after* the bump |
| 4 — closed issues | `--section 5.7.0` → **12/12**, not against the emptied `[Unreleased]` |
| 5 — version sync | `version.py` and `pyproject.toml` both 5.7.0 |

### One gate failure, and what it taught

The release PR went red on `test_llms_txt_shipped`. `llms.txt` ships **inside the
wheel** (#605) and its packaged copy at `src/nodus/llms.txt` is byte-compared
against the root; the version-claim edit updated the root only.

Gate 1 had been green — because it ran at step 1, **before** steps 2–4 made those
edits. That is the same lesson as "re-run `--versions` after the bump", one step
wider, and the sequence did not state it. Now recorded as **step 4c**, and both
harnesses were re-run after every release edit: only `unittest` caught it, while
`pytest` stayed green.

---

## Known and accepted

- **`nodus-run-action` is stale.** Its README pins the nodus-lang version and
  every release moves it. Stage 6 work, after the upload.
- **Throughput was not measured.** This release adds declarations and a
  compensation pass on the failure path; nothing was expected to be measurable —
  but that is not a measurement, and this says so rather than implying otherwise.
- **`BUILD_MODULE` remains unemitted** (#412 phase 1). Documented in
  `BYTECODE_REFERENCE.md`; the instruction set is frozen, so it stays.
