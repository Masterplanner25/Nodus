# v6.0.0 — Stage 5 post-publish eval

**Package:** `nodus-lang==6.0.0` from PyPI (https://pypi.org/project/nodus-lang/6.0.0/),
installed into `.venv-postpublish`, upgraded in place from 5.21.0. The first
`pip install` after the upload still resolved 5.21.0 (index lag); the second got
6.0.0.

**Date:** 2026-11-28. Everything below ran from fresh directories under `%TEMP%`,
outside the repo, against
`C:\dev\Coding Language\.venv-postpublish\Lib\site-packages\nodus`.

The question this stage answers: does the published package work as a new user
expects, and does an upgrading 5.x user meet each 6.0.0 change the way the
README box and the migration guide say they will?

## As a new user (the README's Quick Start)

| step | result |
|---|---|
| `nodus --version` | `Nodus 6.0.0` |
| `nodus init` then `nodus run` | `hello from nodus`, exit 0 |
| `nodus run hello.nd` | `hello` |
| `nodus check hello.nd` | `hello.nd: OK`, exit 0 |
| `nodus status` | project root, entry and working dir |
| `nodus check hello.nd --staged` | `No behaviour changes are staged for 6.0.0. Plain \`nodus check\` reports what the landed ones find.` |

## As an upgrading user: each change

| change | what happened | exit |
|---|---|---|
| #545 record `==` | `record {x: 1i} == record {x: 1i}` printed `true` | 0 |
| #609 type names | `Syntax error at ty.nd:1:9: Unknown type name 'itn' -- did you mean 'int'? Known types: ...` | 1 |
| #547 lost update | `steps a and b both wrote state 'total' while running concurrently and with different values, so one was lost ... Declare \`with { merge: "sum" }\` ...`; `nodus check` warned on the same pair first | 1 |
| #798 `worker:` | `a step declares worker 'gpu', but no worker dispatcher is registered ...` | 1 |
| #1021 library `run_loop()` | `run_loop() was called from library code at lib.nd:2:5 ...` | 1 |
| D2 `.tl` | `Error: .tl source files are no longer supported. Rename old.tl to old.nd.` | 1 |
| D3 `_last_vm` | absent; `active_vm()` returns the last run's VM | — |

### #797, the one about state, end to end

A project that parked a run on 5.x behaviour (`NODUS_WORKFLOW_STORE_BACKEND=local`,
a `workflow_wait`), then used under the 6.0.0 default:

1. `nodus workflow runs` → `Error: the default workflow store is SQLite (...), and 1
   run record(s) in the file-backed JSON store ... are not in it ...`, exit 1. The
   parked run is named, not hidden.
2. `nodus workflow migrate-store --to sqlite --dry-run` → `migrated_count: 1`,
   `waiting_count: 1`.
3. `nodus workflow migrate-store --to sqlite` → `migrated_count: 1`,
   `failed_count: 0`, target `.nodus/workflow_framework.sqlite3`.
4. `nodus workflow runs` → `waiting: 1`.
5. `nodus workflow deliver approval.granted --payload '{"ok": true}'` → matched the
   run; `nodus workflow runs` then reports `completed: 1`.

**The parked run survived the upgrade and resumed.** That is the harm the flip was
staged for, checked on the published package rather than assumed.

### Durable coroutines need no setup

`durable_spawn("k1", w, [3i])` with one checkpoint, no store configured: printed
`done 3`, exit 0. Through 5.x this needed `NODUS_WORKFLOW_STORE_BACKEND=sqlite`.

### Embedding

With `-W error::DeprecationWarning`: `NodusRuntime().run_source(...)` compared two
records `true`; `active_vm()` returned the VM; `hasattr(rt, "_last_vm")` is
`False`; a bare runtime still denies `std:subprocess` with `kind: "sandbox"`
(5.0.0's deny-by-default is unchanged).

## Findings

None blocks the release, and none is a defect in a 6.0.0 claim.

1. **`nodus check --staged` on 6.0.0 says "Staged for 6.0.0".** The register's
   `target` is still `6.0.0`, so on the release itself the header names the
   version you are running as the next major. The body is right ("No behaviour
   changes are staged"). Moving `target` to `7.0.0` is the first step of the next
   cycle; the landed entries keep `landed_in: 6.0.0`.
2. **An error kind is rendered as `Workflow_error error at ...`.** Cosmetic and
   not new in 6.0.0 (`kind.capitalize()` + " error"), but 6.0.0 makes users meet
   it more often, since #547 and #798 now refuse with `workflow_error`.
3. Carried from Gate 10: a server sweeper thread dies if its SQLite file is
   deleted under it (#1035, see `CREATOR_VALIDATION.md`).

## Verdict

**Works as published.** Every README Quick Start step works, each 6.0.0 change
reads as the migration guide says, and the stored-run upgrade path was walked
end to end on the published package.
