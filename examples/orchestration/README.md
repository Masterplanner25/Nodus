# Orchestration examples — concurrent agent fan-out

These examples show how to write **concurrent, schema-validated agent
orchestration** in Nodus: fan work out across coroutines, force each agent's
output to satisfy a required-key "schema" (with retry), and compose the results
(a judge panel). They are the patterns that drove the ASYNC-MOD-001 fix (#105 /
#290) — the reason `http.get_async` / `subprocess.run_async` fan-out genuinely
overlaps instead of silently running serially.

Re-verified 2026-09-17 against nodus-lang 5.13.0; every number below was
measured on that day.

## Files

| File | What it is |
|---|---|
| `agent_typed.nd` | The reusable core: `fan_out(items, worker)` (ordered concurrent fan-out), `typed(name, payload, required_keys, max_attempts)` (schema-forced agent call with retry), and `invoke(name, payload)` — the single agent-execution **seam** where you choose the transport. |
| `judge_panel.nd` | A judge-panel pattern built on `agent_typed`: generate N angled solutions concurrently, score each with a panel of judges (nested fan-out), then synthesize the winner while grafting in the best runner-up ideas. |
| `judge_panel_demo.nd` | Drives `run_panel()` with three angles and two judges, and prints the outcome. |
| `run_judge_panel.py` | **How to run the panel.** Registers stub `solver` / `judge` / `synthesizer` agents (each sleeps 200 ms, standing in for a model) on a `NodusRuntime`, runs `judge_panel_demo.nd`, and prints the wall time. |
| `fanout_walltime_test.nd` | A wall-clock regression test (uses `std:test`) that asserts fanned-out I/O actually **overlaps**, measured against a *real concurrent server* — not an instant in-process mock. |

## Running the judge panel

```bash
cd examples/orchestration
python run_judge_panel.py
```

```
winner: fairness
final:  a rate limiter that optimises for fairness, grafting 4 runner-up ideas
  throughput avg=7.0
  fairness avg=9.0
  simplicity avg=6.0
wall time: 715 ms  (10 agent calls; serial would be 2000 ms)
```

Ten agent calls of 200 ms each — 3 solvers, then 3 × 2 judges, then 1
synthesizer — in 715 ms: each of the three fan-out levels runs its calls
concurrently, and the wall time is the sum of the levels, not of the calls.

`nodus run judge_panel_demo.nd` on its own fails, as it should: nothing has
registered the agents, and the panel stops at the first one with
`agent 'solver' did not validate: No handler registered for agent 'solver'`.
Agent registration is host-only by design (`docs/guide/agent-host-boundary.md`).

## Running the wall-time test

It needs a local server that delays each response ~300 ms and serves requests
concurrently; the header comment has a one-liner `ThreadingHTTPServer` to copy.
Then:

```bash
nodus test examples/orchestration/fanout_walltime_test.nd
```

```
raw builtin fan-out: 324ms (serial would be 1800.0ms)
wrapper fan-out: 312ms (serial would be 1800.0ms)
Tests: 2 total, 2 passed
```

## Concurrency status

- **`agent.call_async` overlaps** (4.1.0, #294). `invoke()` uses it, so a
  `fan_out()` over agent calls is concurrent — that is what the 715 ms above
  measures. Earlier revisions of these files said agent calls were serial;
  they were when written and have not been for nine releases.
- **`http.get_async` / `subprocess.run_async` fan-out overlaps** (4.0.8,
  #105 / #290), and so does the raw `http_get_async` builtin — fully, since
  #295 (closed 2026-07-10). Both cases in the wall-time test assert the same
  bar now; the raw case used to be allowed partial overlap.
- **The first HTTP request of a process is slow** (#855, open): building the
  shared `httpx` client loads the CA bundle, ~0.4–1 s here, and every worker
  thread in a cold fan-out waits on it. The wall-time test issues one
  synchronous request before timing anything for that reason. If your first
  fan-out looks serial and the second does not, that is what you are seeing.

## What #856 was

`judge_panel.nd` had never actually run. Its inner `fan_out` — the judges,
inside a candidate's worker — silently returned nothing: a coroutine spawned by
a module function that was reached *through a foreign closure* was owned by
the wrong VM and dropped without an error. Fixed in the same change that made
these examples runnable; `tests/test_foreign_ctx_keeps_own_builtins.py` pins
it with a three-file repro.

See `tests/test_async_concurrency_timing.py` for the Python-side equivalent of
the timing test that ships in the nodus-lang test suite.
