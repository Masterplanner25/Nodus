# v5.14.0 — Stage 5 post-publish evaluation

**Date:** 2026-09-18
**Package:** `nodus-lang==5.14.0` from PyPI, `pip install "nodus-lang[http]==5.14.0"`
into a fresh venv, run from a neutral directory (never the checkout)
**Verdict:** **PASS.** 10/10, every fix in the release exercised through the
published binary.

Stage 5 asks *"does this work as a new user would expect?"* — against the
artifact on the index, not the wheel on disk. Gate 10b answered the same
question about a local file; the index can serve something else (it served
zero files for 5.6.0 for a while), so nothing here reuses anything from Gate 10.

---

## Install

`pip install "nodus-lang[http]==5.14.0"` resolved on the **first attempt**,
about a minute after the upload. The index lagged nine minutes at 5.13.0, so the
install loop was written to retry; it did not need to.

```
Name: nodus-lang
Version: 5.14.0
Nodus 5.14.0
resolved from: …\stage5\Lib\site-packages\nodus\__init__.py
```

---

## What a new user would do

One session, in a scratch directory, the way the examples and the README tell
them to. Numbered as run.

| # | claim | how | result |
|---|---|---|---|
| 1 | #856 — a nested cross-module fan-out returns every inner result | three files (`a.nd` fan-out, `b.nd` calling it through a closure, `main.nd`), `nodus run main.nd` | `[[10, 20], [20, 40], [30, 60]]` — the judge-panel shape that had never run |
| 2 | #857 — `nodus workflow run --time-limit 30` raises the budget | a step looping 300k times, ~3 s | exit 0, `steps={"a": 300000}` |
| 2 | #858 — the CLI reports the program's own run | the same file calls `run_workflow` itself | the JSON payload's `graph_id` equals the one the program printed |
| 3 | control — the default budget still times that step out | same file, no flag | `Execution timed out`, exit 1 |
| 4 | #857 — legacy `workflow-run --time-limit 30` means seconds | same file | ran to completion (was a 30 ms budget) |
| 5 | #858 — `POST /workflow/run` runs a self-running program once | `nodus serve --time-limit 5 …`, then the program | step ran **1×**, response `graph_id` == the program's |
| 6 | #862 — a `while (true)` step under `serve` returns | same server | `ok: false`, `Execution timed out`, **5025 ms** — the ceiling, not forever |
| 7 | #857 — a request may ask for less | `timeout_ms: 50` on the slow step | `ok: false`, `Execution timed out` |
| 8 | #857 — a request cannot ask for more | `timeout_ms: 60000` on a 5 s server | accepted and capped; the step happened to fit (2.7 s) |
| 9 | #857 — a malformed `timeout_ms` is refused, not ignored | `"timeout_ms": "soon"` on `/execute` | `ok: false`, `timeout_ms must be a positive number of milliseconds, got 'soon'`, and the program did **not** run |
| 10 | #855 — the trust store is built once per process | three `/execute` requests each doing one 300 ms `http_get` | **758 / 341 / 310 ms** — the first pays the bundle, the rest are the request |

Server log: zero tracebacks.

Row 8 is honest about what it shows: the cap held the request to 5 s, and the
step fit inside that, so the row proves the request was *accepted* with an
over-ceiling ask rather than refused — the cap itself is pinned by
`test_serve_execution_budget.py` with a 100 ms server.

---

## What did not go wrong

- No index lag, no wrong-tree resolution (checked before the first probe), no
  optional-extra gap — the `[http]` extra was installed deliberately because
  row 10 needs it, and 5.13.0's cycle taught that a bare install leaves `http`
  refusing rather than failing.
- Nothing here needed Postgres, ngrok or a companion package; every row is
  nodus-lang alone.

---

## Findings

None new. The one thing worth noting for the next reader is in row 10: the
first request of a `nodus serve` process still pays ~450 ms for the CA bundle.
That is once per process now rather than once per request; it is not zero, and
the changelog says so.
