# Working under tests/

> Moved out of the root `CLAUDE.md` on 2026-11-05 so it loads on demand. "This file" in the text
> below may mean the root file as it was. A section it names may now be in another file:
> release rules in `.claude/commands/release-sequence.md`, the bug shape in
> `.claude/commands/recurring-bug-shape.md`, embedding in `.claude/commands/nodus-embedding.md`.

## Test suite: flakes, host memory, timing

**Three tests were known-flaky here; all are fixed. The reproduction method is the
part worth keeping.** Neither ever failed from repetition — only under *load* — so
"it passed when I ran it again" was never evidence about either, and an idle box
passes indefinitely.

- **`test_scheduler_fairness.py` (#631) — fixed 2026-08-28.** Never a fairness
  failure: the run was killed by the 200 ms wall-clock `EXECUTION_TIMEOUT_MS`
  before the ordering assertion was reached, so the test asserted the box could
  run 8000 iterations in 200 ms. The harness sets its own generous deadline now,
  in one helper so a test added later cannot forget it; `EXECUTION_TIMEOUT_MS`
  is untouched. **Both** tests in the file were affected, not the one an earlier
  note named.
- **`test_server.py::SQLiteWorkflowServerTests::test_workflow_run_uses_sqlite_store_when_configured`
  (#632) — fixed in 5.6.0.** Read as a tempdir race and was not one: the store
  was still open when the directory was removed, and `SQLiteWorkflowStore` had
  no `close()`. `RuntimeService.close()` waits for its sweeper now.
- **`test_task_graph.py::test_task_reassignment_after_worker_failure` (#728) —
  fixed 2026-09-06.** The tightest budget in the tree: `_worker_heartbeat_timeout_ms`
  was **20 ms**, and it had to cover a thread starting, compiling and reaching
  `submit()` — which calls `_expire_workers` first. `wait_for_job` marks the
  worker *seen*, which cancels the 250 ms `_startup_grace_ms` that would
  otherwise have covered it, so the worker was evicted and the first assertion
  saw `{"job_id": None}`. **The death the test simulates is the backdating, not
  this timeout**, so the timeout is large now (2 s) and the backdate far past it
  (60 s) — the margin runs on the side load stretches. Diagnosed by forcing the
  delay rather than by loading the box: 20 ms fails with the VM thread 200 ms
  late, 2 s survives 1 s late. Its three siblings in the same file were checked
  and left alone — two assert a worker *is* expired, which load only makes safer.

**To reproduce this class of failure, load the machine; do not re-run the test.**
Burn every core but one in a background process, then run the file.

**And keep the control inside the same load window.** Comparing "before" and
"after" is worthless if the load generator expires partway: a first attempt at
#631 showed the unfixed tests passing 5 of 6 with run times falling from 1.75 s
to 0.49 s — the box had gone idle, so the comparison measured nothing. Re-run
inside one window, both variants, and check the durations stayed up. Matched that
way, #631 was 3 of 5 runs red before and 5 of 5 green after.

**Do not fix #334's three flakes twice.** `test_async_concurrency_timing.py`,
`test_ieee754_division.py` and `test_workflow_dsl.py` were hardened in PR #581 and are
not on this list.

**The cause is established as of 2026-09-08: this host runs out of physical memory,
and process creation stalls on hard page faults.** It was recorded as unexplained
for months; it is not a mystery any more, though it is also not fixed — the
condition is the machine, not the tree.

Measured on the box during the 5.13.0 cut:

```
Physical RAM   : 7.7 GB total, 0.6 GB free (92.2% used)
Commit charge  : 23.61 GB used / 30.23 GB limit      -> ~16 GB paged to disk
Page Reads/sec : 142, 311, 253, 1061, 3283           -> climbing, while idle
Page file      : 4.6 GB in use, 7.5 GB peak
```

**The mechanism, and why it produces exactly the symptoms above.** A page read is
a *blocking disk fault*. Spawning a subprocess touches a lot of cold pages, so
under this pressure a spawn that normally costs 40 ms can cost seconds — which is
why the tests that break are **the ones with subprocess timeouts**, why a
different one breaks each run (whichever happened to fault at the wrong moment),
why they pass in isolation (one test has a small working set and does not
thrash), and why wall-clock drifts 7 → 19 minutes with "nothing else running".
Nothing else *has* to be running; the pages are already out.

Confirmed rather than inferred, on 2026-09-08:

- The four `test_cli_completion.py::BashExecutionTests` failed with
  `TimeoutExpired` in the full suite **and again in isolation** — then passed
  **4/4 in 3.62 s** an hour later with no code change. Their code is unchanged
  since v5.12.0.
- `bash --version` timed out at 15 s during that window. Later, 40 consecutive
  runs: **0 hangs, median 44 ms, max 76 ms.** The binary is fine; the machine was
  not.
- Two background tasks in that session were killed by the OS with *"the system is
  running low on memory"*.

**What is consuming it, measured the same day.** WSL2 is *not* the culprit any
more — `~/.wslconfig` caps it at 3 GB with `autoMemoryReclaim=gradual`, which was
an earlier fix for this same class on this host, and it was holding. The rest is
ordinary development: VS Code (11 processes, 1.15 GB), the agent itself
(3 processes, 1.96 GB), Chrome, two `node` processes at ~1.9 GB combined, and a
terminal at 0.76 GB. Together they commit roughly the whole of physical RAM
before a test suite starts.

One outlier worth knowing: **`explorer.exe` had leaked to 1.1 GB private across
11,941 handles and 15 days of uptime** — roughly ten times normal. Restarting
Explorer is the cheapest gigabyte available, and Defender real-time protection is
on with no exclusion for the checkout or the venv, which adds a scan to every file
the suite touches.

**None of this makes a local full-suite run a gate.** It explains why it never
was one. The guidance below is unchanged and now has a reason behind it rather
than a shrug.

**It still comes and goes within a single day. Do not record it as "fixed."** An
earlier revision of this section declared it "environmental and gone" on the
strength of one clean 7:46 run — hours before the same box produced a 15-minute
run with 13 failures and then stopped finishing at all. **One clean measurement
does not clear this.** A good run is not evidence of a good machine, which is the
whole reason CI arbitrates. What has changed is that a *bad* run can now be
attributed instead of puzzled over.

If you see failures that move between runs and a suite that is suddenly 2× slower,
check free memory, then re-run the failing test alone, then push.

**Flaky test fix pattern — timing headroom:**
Tests that race a sleep against a timeout need **5–10x headroom**, not 2x. Under full-suite parallel
load, a 20ms sleep takes longer than 20ms wall-clock. Rule: if the test sleeps N ms and the code
times out at M ms, ensure M ≥ 5N.

**And the test does not have to sleep to be racing something.** A test that shells
out to `nodus run` is racing the runtime's own 200ms default budget, which nothing
in the test mentions — `test_cross_module_closure.py` failed on CI that way with
`Execution timed out` and nothing else wrong (#711). Ask what deadline the code
under test carries by default, not only what the test itself waits for. Details in
the SCHED-001 entry under language quirks.

Two classes can't share incompatible timeout requirements. If a test needs `session_timeout_ms=50`
(to observe expiry quickly) and another needs `session_timeout_ms=2000` (to survive load without
expiring), split them into two classes with separate server instances — one per `setUpClass`.

**The runtime clock cannot order two events — it ticks at ~15.6 ms.** `runtime_time_ms()`
is `(time.monotonic() - _START) * 1000.0` (`runtime/runtime_stats.py`), and on this box
`time.monotonic()` advances in ~15.6 ms steps — measured deltas between consecutive
distinct readings: `[16.0, 16.0, 15.0, 16.0, 15.0, 16.0]`. So **any two things that happen
without I/O between them get the same timestamp.** A task's `started_at` and `finished_at`
are routinely equal, and a strict causal chain `a→b→c→d→e` stamped `265, 265, 281, 297, 297`
— two ties in a sequence with no ambiguity at all.

Consequences, in order of how much they cost:

- **Never derive an ordering from a timestamp.** Sorting completed tasks by `finished_at`
  puts them in an arbitrary order, not a wrong-but-close one. This is what #577's
  compensation spec had to solve (`docs/design/workflow-dsl/01-compensation.md`): the
  order exists — tasks settle one at a time on one scheduler — it is simply never
  recorded, so the fix is a counter incremented where completion is already serialized,
  not a finer clock.
- **A duration measured across a fast operation is `0.0` and means nothing.** Do not
  assert on one, and do not read it as "instant".
- **This is platform-specific, which makes it worse.** `time.monotonic()` is
  nanosecond-resolution on Linux, so a timestamp-ordering rule is *mostly* right on a CI
  runner and wrong here — correct on the test platform, broken on the developer's. CI
  cannot catch it; only a causal chain of trivial steps run locally can.

**Sweeper startup race:** `RuntimeService` starts the sweeper thread in `__init__` with the default
interval. If you set `_worker_heartbeat_timeout_ms` after construction, the sweeper sleeps the
default interval (500ms) before adopting the new value. Fix: pass `worker_sweep_interval_ms=N`
directly to the constructor.

## Test-related files

| What | Where |
|------|-------|
| Scheduler time source | `src/nodus/runtime/time_source.py` — `TimeSource`, `HostTimeSource`, `VirtualTimeSource` (#182). Reading time and waiting for it are **one** seam; injecting only a clock makes `run_loop()` hang |
| Eval test scripts | `tests/eval/` — quirk_probe.nd, language_exerciser.nd, framework_capabilities.nd. **Run by the suite as of #817** (`tests/test_eval_probes.py`), not only by `/release-prep`; a fourth `.nd` added here that nothing runs fails the suite. The runner reads each probe's `// SUCCESS CONTRACT:` header rather than restating the sentinel |
