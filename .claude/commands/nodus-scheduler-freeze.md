Graduate coroutines and channels from Experimental to Mostly Stable.

Covers Phase A (CIRC-001 quick fix) and Phase B (scheduler/channel correctness).
Phase B is the prerequisite for all later graduation phases.

Phases:
  Phase A — CIRC-001 lazy import (no deps, run first, ~30 min)
  Phase B — SCHED-001, SCHED-002, CHAN-001 (depends on Phase A)

GitHub issues: #94 (SCHED-001), #95 (SCHED-002), #103 (CIRC-001), #107 (CHAN-001)

Arguments: $ARGUMENTS
(Pass "A" for CIRC-001 only. Pass "B" for the scheduler/channel fixes.
Omit to run all phases in order.)

---

## Phase A — CIRC-001: lazy import fix

**File:** `src/nodus/vm/vm.py`
**GitHub:** #103

`nodus.vm.vm` imports `get_default_workflow_runner` from `nodus_workflow.runner`
at module level. Embedders who import `nodus_workflow` before `nodus` hit a
circular import.

**Fix:** Find the top-level `from nodus_workflow.runner import get_default_workflow_runner`
and move it to a lazy import inside the function body that uses it
(`builtin_run_workflow`, `builtin_resume_workflow`, or wherever it's called).

```python
# Before (top-level):
from nodus_workflow.runner import get_default_workflow_runner

# After (lazy, inside the function):
def builtin_run_workflow(self, ...):
    from nodus_workflow.runner import get_default_workflow_runner
    ...
```

**Test:** Confirm `import nodus_workflow; import nodus` works without circular import.

---

## Phase B — Scheduler and channel correctness

### B1: SCHED-001 — execution deadline must not count cooperative sleep

**File:** `src/nodus/runtime/scheduler.py`
**GitHub:** #94

The `timeout_ms` deadline counts wall-clock time including time a coroutine
spends suspended in the scheduler timer heap (sleeping). A coroutine that calls
`sleep(1000)` four times is killed after 200ms total wall time even though it
consumed no CPU.

**Root cause:** The deadline is checked against wall-clock time elapsed since
`run_source()` was called, not against actual execution time.

**Fix direction:**
1. Track `active_ms` per coroutine: time the VM actively runs it (not sleeping).
2. Only count `active_ms` against `timeout_ms`.
3. Alternatively: make `timeout_ms` apply only to total execution instructions
   (`max_steps`) and separate the wall-clock deadline (`deadline`) so sleeping
   doesn't consume the execution budget.

The cleanest separation: `timeout_ms` = wall-clock deadline for the WHOLE
`run_source()` call (prevents infinite hangs), but sleeping coroutines don't
count toward per-coroutine step limits. See how `TASK_STEP_BUDGET` already
handles per-coroutine fairness for steps — the wall-clock deadline is the
session-level guard, not the per-coroutine execution limit.

**Tests:** A coroutine that calls `sleep(100)` three times should NOT be killed
by a `timeout_ms=200` deadline if it has only executed for 50ms of CPU time.

### B2: SCHED-002 — limit breach must terminate the full session

**File:** `src/nodus/runtime/scheduler.py`
**GitHub:** #95

A `RuntimeLimitExceeded` breach currently kills only the coroutine that tripped
it; other coroutines continue draining. The host sees `ok=False` but the session
is not fully terminated.

**Fix:** When `RuntimeLimitExceeded` propagates out of `builtin_coroutine_resume`,
set a session-abort flag that causes `run_loop()` to exit after the current
iteration without processing further coroutines.

```python
# In run_loop():
except RuntimeLimitExceeded:
    raise  # already done — but also set self._session_aborted = True
           # and check it at the top of the while loop
```

**Tests:** After a limit breach, coroutines that were already queued should NOT
execute. Their output should NOT appear in stdout.

### B3: CHAN-001 — recv() must register channel in _io_channels to prevent orphan

**File:** `src/nodus/builtins/coroutine.py`
**GitHub:** #107

`recv()` on an empty channel adds the coroutine to `ch.waiting_receivers` but
does NOT add `ch` to `scheduler._io_channels`. The scheduler's exit condition is
`while self.ready_queue or self.timers or self._io_channels` — since the channel
is not in `_io_channels`, the scheduler exits and the blocked coroutine is
orphaned.

**Fix:** In `builtin_recv` when `recv()` blocks (the channel is empty and not
closed), also register the channel in `scheduler._io_channels`:

```python
# In the blocking path of builtin_recv:
scheduler = _get_scheduler(vm)  # or vm.scheduler if accessible
if scheduler is not None and ch not in scheduler._io_channels:
    scheduler._io_channels.append(ch)
```

`_drain_io_channels` already handles waking coroutines from `_io_channels` when
data arrives. The only change is ensuring the channel is registered there when
a receiver blocks on it.

When the channel is closed (all waiting receivers woken), `_drain_io_channels`
already calls `self._io_channels.remove(ch)` — so cleanup is handled.

**Tests:**
```nodus
let ch = channel()
spawn(coroutine(fn() {
    let v = recv(ch)
    print(v)
}))
// External feed after run_loop starts — e.g. via Python send in a thread
run_loop()
```
The scheduler should remain alive until the channel has data or is closed.

---

## Graduation criteria

After Phase A + B are complete, coroutines and channels qualify for
**Mostly Stable**:
- ✅ API frozen (`coroutine`, `spawn`, `resume`, `run_loop`, `channel`, `send`, `recv`, `close`)
- ✅ All Phase B correctness bugs fixed
- ✅ Edge cases tested (existing 9 coroutine + 10 channel tests)
- ✅ Semantics documented

Update `docs/governance/LANGUAGE_STABILITY_INDEX.md` after all tests pass:
- `spawn`, `coroutine`, `channel` tier: Experimental → Mostly Stable
- `yield expr` tier: Mostly Stable → Stable (already frozen semantics)

## Dev environment

```powershell
cd "C:\dev\Coding Language"
PYTHONPATH="C:/dev/Coding Language/src" `
  "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest `
  tests/test_coroutines.py tests/test_channels.py tests/test_scheduler.py `
  tests/test_scheduler_fairness.py -v

# Full suite
PYTHONPATH="C:/dev/Coding Language/src" `
  "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/ -q --tb=no
```

## Commit format

```powershell
git commit -m @'
fix(scheduler): <Phase A/B description>

Closes #94 / #95 / #103 / #107 as applicable.
Phase A/B of experimental surface graduation.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
'@
```
