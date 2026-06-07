# Nodus Error Guide

Match the error text, then apply the fix class.

## Parse and syntax failures

- `Expected ')', got ','`
  Fix: `print()` is single-argument. Use interpolation.
- `Unexpected '=' in expression`
  Fix: remove `+=` or similar compound assignment.
- `Unexpected end of statement - expression is incomplete`
  Fix: keep calls and literals on one line.
- `Expected identifier, got 'fn'`
  Fix: rename a parameter or binding that uses a reserved keyword.
- `import statements must be at the top level of a module`
  Fix: hoist imports to file scope.
- `workflow body must contain state declarations or steps`
  Fix: move `checkpoint` or other stray statements inside a step body.
- `[import] Import not found: std:channel`
  Fix: use built-in channels directly.

## Runtime failures

- `Field access is only supported on records`
  Fix: switch from dot access to bracket access on a map.
- `Indexing is only supported on lists and maps`
  Fix: switch from bracket access to dot access on a record.
- `Missing map key: "name"`
  Fix: guard with `has_key()` or inspect the actual result shape.
- `Cannot add nil and int`
  Fix: replace outer-`let` closure mutation with the map pattern.
- `spawn(coroutine) expects a coroutine`
  Fix: create the coroutine value first, then pass it to `spawn()`.
- `Cannot resume finished coroutine`
  Fix: check `coroutine_status(c)` before resuming.

## Workflow and execution traps

- Script exits early with no obvious language error
  Fix: raise the time limit with `nodus run --time-limit 5000 script.nd` or disable it in embedding.
- Workflow result lookup fails for a step name
  Fix: inspect `r["failed"]` and `r["steps"]`; failed steps are not present in `r["steps"]`.
- Retry with `retry_delay_ms > 0` never completes synchronously
  Fix: understand that retry is async, or implement synchronous retry with `try/catch` inside the step.

## Python embedding traps

- Long-running embedded script times out
  Fix: use `NodusRuntime(timeout_ms=None, max_steps=None)` for server-like hosts.
- `run_source()` returns an error object instead of raising
  Fix: always inspect `result["ok"]` before consuming output.
