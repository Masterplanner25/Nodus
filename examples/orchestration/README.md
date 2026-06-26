# Orchestration examples — concurrent agent fan-out

These examples show how to write **concurrent, schema-validated agent
orchestration** in Nodus: fan work out across coroutines, force each agent's
output to satisfy a required-key "schema" (with retry), and compose the results
(a judge panel). They are the patterns that drove the ASYNC-MOD-001 fix (#105 /
#290) — the reason `http.get_async` / `subprocess.run_async` fan-out now
genuinely overlaps instead of silently running serially.

## Files

| File | What it is |
|---|---|
| `agent_typed.nd` | The reusable core: `fan_out(items, worker)` (ordered concurrent fan-out), `typed(name, payload, required_keys, max_attempts)` (schema-forced agent call with retry), and `invoke(name, payload)` — the single agent-execution **seam** where you choose the transport. |
| `judge_panel.nd` | A judge-panel pattern built on `agent_typed`: generate N angled solutions concurrently, score each with a panel of judges (nested fan-out), then synthesize the winner while grafting in the best runner-up ideas. |
| `fanout_walltime_test.nd` | A wall-clock regression test (uses `std:test`) that asserts fanned-out I/O actually **overlaps**, measured against a *real concurrent server* — not an instant in-process mock. |

## Concurrency status (important)

- **`http.get_async` / `subprocess.run_async` fan-out OVERLAPS** as of nodus-lang
  **v4.0.8** (ASYNC-MOD-001, #105 / #290). The idiomatic stdlib-wrapper path is
  the fast path.
- **`agent.call` is still synchronous** (ASYNC-MOD-002, #294). So fanning out over
  the default `invoke()` (which calls `agent.call`) produces **correct results but
  runs serially**. To overlap agent work *today*, point `invoke()` at an async
  transport — `http.post_async(AGENT_HOST + "/run", {...})` or
  `subprocess.run_async([...])`. That choice lives in exactly one place:
  `invoke()` in `agent_typed.nd`. The orchestration (`typed`, `fan_out`,
  `run_panel`) is transport-agnostic and does not change.
- The **raw direct-builtin** path is concurrency-capped short of N× (ASYNC-CAP-001,
  #295) — prefer the stdlib wrapper, which scales.

## Running

`agent_typed.nd` / `judge_panel.nd` are library modules — the **host must register
the agents** they call (`solver`, `judge`, `synthesizer`, etc.) via the embedding
API before running an orchestration that imports them. Example shape:

```
let out = run_panel("Design a rate limiter", ANGLES, JUDGES)
```

`fanout_walltime_test.nd` needs a **local concurrent server** that delays each
response; the header comment has a one-liner Python `ThreadingHTTPServer` to copy.
Then:

```
nodus test examples/orchestration/fanout_walltime_test.nd
```

See `tests/test_async_concurrency_timing.py` for the Python-side equivalent of the
timing test that ships in the nodus-lang test suite.
