# Post-publish eval — v4.2.0 (Stage 5)

**Date:** 2026-08-15
**Artifact under test:** `pip install nodus-lang==4.2.0` **from PyPI**
**Environment:** fresh `.venv-postpublish`, nothing else installed, no `PYTHONPATH`

Distinct from Gate 10 (`CREATOR_VALIDATION.md`), which asked *"what can I make
fail?"* against a locally-built wheel. This stage asks **"does this work as a new
user would expect?"** against the published package.

## Result: clean. No findings.

### 1. Install and discovery

```
pip install nodus-lang==4.2.0        → installs, no errors
nodus --version                      → Nodus 4.2.0
pip show nodus-lang                  → Version: 4.2.0
nodus --help                         → usage + grouped command list
```

### 2. README quickstart, run verbatim

The README's first instruction block, executed exactly as written in an empty
directory:

```
pip install nodus-lang
nodus init      → Initialized Nodus project at <dir>/     (creates nodus.toml, src/, .nodus/)
nodus run       → Running project from: <dir>
                  Entry: src\main.nd
                  hello from nodus
```

A new user reaches a running program in three commands, with no editing.

### 3. The claims this release advertises

The README's "Recent" line and the CHANGELOG make four user-facing claims. Each
verified against the PyPI install:

| Claim | Check | Result |
|---|---|---|
| `finally` runs when `catch` re-throws (#361) | cleanup on a re-throw path | `cleanup_ran;propagated;` ✅ |
| `std:async` worker pools actually run their workers (#339) | `worker_pool` + `send` + `run_loop` | `worked:5;worked:6;` ✅ |
| `--help` no longer executes the command (#353) | `nodus logout --help` | `Usage: nodus logout [--registry URL]` — **token not deleted** ✅ |
| embedded runtime applies a call-depth cap by default (#350) | `NodusRuntime(max_steps=None, timeout_ms=None)` on runaway recursion | `ok: False`, `Call stack overflow` — not a hang ✅ |

The two remaining advertised items are not user-facing at runtime: the
`--opcodes` gate phase is a repo tool, and DAP locals surface through an editor.

## Known issues, as shipped

Both disclosed in the CHANGELOG's `[4.2.0]` known-issues section and filed before
publish. Neither is a regression; both fail at compile time.

- **#415** — `try { } finally { }` without `catch` is a syntax error.
- **#416** — a closure inside a loop body at module top level cannot capture that
  body's variables; the same loop inside a function works.

Neither was encountered on the new-user path above.

## Release record

| | |
|---|---|
| PyPI | https://pypi.org/project/nodus-lang/4.2.0/ |
| Tag | `v4.2.0` → `1ad1a66` |
| Gates | 1–7, 10 all pass — see `CREATOR_VALIDATION.md` |
| Gate 10 | 11 programs, 2 findings, both filed |
| Stage 5 | this document — no findings |
