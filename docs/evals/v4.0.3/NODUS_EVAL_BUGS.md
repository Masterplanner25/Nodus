# Nodus v4.0.3 — Eval Bug Report

**Eval date:** 2026-06-13
**Evaluator:** Claude Sonnet 4.6 (independent)
**Total findings:** 2 (1 LOW, 1 COSMETIC)

---

## EVAL-403-001 — `identity.session_id()` still nil under CLI after #236 fix

**Subsystem:** `std:identity`, module loader, VM propagation
**Severity:** LOW (same as original #236)
**Milestone routing:** v4.0.4 patch
**Status:** New residual from incomplete #236 fix

### Repro

```nodus
import "std:identity" as identity
print(identity.session_id())   # → nil   (BUG: should be a UUID)
print(identity.trace_id())     # → UUID  (OK — this part was fixed)
```

```
nodus run test_identity.nd
# trace_id: 6858d615-fd36-4a5d-86d6-9eef9863e71a
# session_id: nil
# exec_id: be1631c6a9cfb9f2
```

### Expected behavior

`session_id()` returns a UUID under `nodus run`, matching the documented
"auto-generated trace_id and session_id" behaviour.

### Actual behavior

`session_id()` returns nil. `trace_id()` returns a UUID.

### Root cause

`runner.py` sets both `vm.trace_id` and `vm.session_id` on the top-level VM.
However, `module.py` propagates only `trace_id` to child VMs created by the ModuleLoader:

```python
# module.py ~line 214
vm.trace_id = getattr(caller_vm, "trace_id", None)
# session_id is NOT propagated here
```

`std:identity` executes in a child VM. The child VM's `runtime_session_id()` builtin
closes over the child VM (not the parent), so it returns `child_vm.session_id = None`.

### Fix direction

Add one line to `module.py` immediately after the `trace_id` propagation:

```python
vm.session_id = getattr(caller_vm, "session_id", None)
```

This is a one-line fix in the same block where `trace_id` is propagated.

### Affected versions

v4.0.3 (current stable). v4.0.2 and earlier had the same symptom as a known issue.
The fix was applied in v4.0.3 for `trace_id` only.

---

## EVAL-403-C1 — Retry error trace bleeds to stderr on workflow success

**Subsystem:** `nodus workflow-run`, inline retry loop
**Severity:** COSMETIC
**Milestone routing:** v4.0.4 or backlog
**Status:** New cosmetic regression introduced by #226 fix

### Repro

```nodus
let state = { "count": 0 }
workflow demo {
    step flaky with { retries: 2, retry_delay_ms: 50 } {
        if (state["count"] == 0) {
            state["count"] = 1
            throw "fail on first attempt"
        }
        return "success on attempt 2"
    }
}
```

```
nodus workflow-run wf_retry.nd
# STDERR (unexpected):
#   Thrown error at wf_retry.nd:7:19: fail on first attempt
#   Stack trace:
#     at __anon_1 (wf_retry.nd:7:19)
#     called from <main> (wf_retry.nd:4:51)
# STDOUT (correct):
#   {"steps": {"flaky": "success on attempt 2"}, "failed": [], "attempts": {"task_1": 2.0}, ...}
# EXIT CODE: 0 (correct)
```

### Expected behavior

Stderr is silent when a workflow ultimately succeeds, even if a retried step
threw on the first attempt. The caller sees exit 0 and clean JSON output.

### Actual behavior

The error from the first (retried) attempt is printed to stderr unconditionally,
even though the inline retry loop successfully recovered and the final exit code is 0.

### Fix direction

In the inline retry loop in `runner.py` (or wherever the first-attempt error is
being emitted), either:
- Suppress the error trace for attempts that are retried and eventually succeed, OR
- Downgrade to DEBUG level (not printed unless `--trace-errors` is active)

The error should only be emitted at the retry-exhausted-failure point.

### Affected versions

v4.0.3 (introduced by #226 fix). Not present in v4.0.2 (retries were no-ops).
