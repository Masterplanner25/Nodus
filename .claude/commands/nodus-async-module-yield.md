Fix ASYNC-MOD-001: enable yield propagation when async builtins are called via
std: module wrappers (std:subprocess, std:http). Currently subprocess.run_async()
and http.get_async() called through `import "std:subprocess" as sp` / `import
"std:http" as h` fall back to synchronous execution because invoke_function →
run_closure → execute() cannot propagate ChannelRecvRequest yield across code
segment boundaries. Direct builtin calls already work.

GitHub: https://github.com/Masterplanner25/Nodus/issues/105

Arguments: $ARGUMENTS
(Omit to run the full implementation. Pass "design" to read and confirm the
plan without making changes.)

## Pre-flight checks

1. Run tests to confirm baseline:
   ```powershell
   cd "C:\dev\Coding Language"
   PYTHONPATH="C:/dev/Coding Language/src" `
     "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/ -q --tb=no `
     --ignore=tests/test_scheduler_fairness.py 2>&1 | tail -3
   ```
2. Read `src/nodus/vm/vm.py` around `_op_call_method` (search for "NodusModule branch").
3. Read `src/nodus/runtime/module.py` — understand `NodusModule`, `invoke_function`,
   and `ModuleFunction`.
4. Read `src/nodus/builtins/http_module.py` `_do_async_request` and
   `src/nodus/builtins/subprocess_module.py` `_do_async_run` — find the
   `current_task` guard that was added as the fallback workaround.

## Root cause (confirmed)

`NodusModule` exports are called via:
```
_op_call_method → invoke_function → run_closure(fn_info, args) → vm.execute()
```

`run_closure` creates a temporary coroutine and calls `execute()` with the
**module's own code** (because `fn_info.addr` is an address in the module's
bytecode, and `run_closure` sets `self.ip = fn_info.addr`). When the async
builtin inside returns `ChannelRecvRequest`, `execute()` returns `("yield", ...)`
and `run_closure` raises `"Task yielded during graph execution"`.

The `current_task` guard in `_do_async_request` / `_do_async_run` detects this
path and falls back to sync to avoid the crash.

The fix: **don't use `invoke_function` for module functions called from a
scheduler-managed coroutine**. Instead, swap `vm.code` temporarily and use
`call_closure`, which stays in the same `execute()` loop and propagates yield.

## Implementation — Option A: `_code_stack`

### Step 1 — VM: add `_code_stack`

In `VM.__init__` (after the other instance variables):
```python
self._code_stack: list[Any] = []
```

Type: `list[Any]` (stores the code list + return-to-module-code bookkeeping).

### Step 2 — VM: update `_op_return` to restore code on cross-module return

When a cross-module call frame returns, the VM must restore `vm.code` to the
caller's code segment. The cleanest approach: mark the cross-module call frame
with a `code_on_entry` attribute, and pop `_code_stack` when that frame pops.

In `_op_return`:
```python
frame = self.frames.pop()
# Restore code segment if this frame was a cross-module call
if getattr(frame, "cross_module_code", None) is not None:
    self.code = frame.cross_module_code
    if self._code_stack:
        self._code_stack.pop()
```

### Step 3 — VM: update `_op_call_method` for module function dispatch

Find the NodusModule branch in `_op_call_method`. The current code:
```python
if isinstance(method, ModuleFunction):
    self.stack.append(method.module.invoke_function(method.name, args, caller_vm=self))
    self.ip += 1
    return None
```

Replace with the conditional dispatch:
```python
if isinstance(method, ModuleFunction):
    scheduler_task = getattr(self.scheduler, "current_task", None)
    if (self.current_coroutine is not None and
            self.current_coroutine is scheduler_task and
            method.name in method.module.functions):
        fn_info = method.module.functions[method.name]
        # Pad missing args with nil (same as invoke_function does)
        expected = len(fn_info.params)
        padded = list(args) + [None] * max(0, expected - len(args))
        # Swap to module's code segment for the duration of this call
        caller_code = self.code
        self.code = method.module.bytecode  # the module's compiled bytecode
        self._code_stack.append(caller_code)
        closure = Closure(fn_info, [])
        frame = Frame(
            return_ip=self.ip + 1,
            locals={},
            fn_name=fn_info.name,
            call_line=None,
            call_col=None,
            call_path=None,
            closure=closure,
        )
        frame.cross_module_code = caller_code  # marker for _op_return
        if fn_info.local_slots:
            frame.locals_name_to_slot = fn_info.local_slots
        if self.max_frames is not None and len(self.frames) + 1 > self.max_frames:
            self.runtime_error("sandbox", "Call stack overflow")
        self.frames.append(frame)
        for arg in padded:
            self.stack.append(arg)
        self.ip = fn_info.addr
        return None
    # Fallback: invoke_function (outside scheduler context)
    self.stack.append(method.module.invoke_function(method.name, args, caller_vm=self))
    self.ip += 1
    return None
```

**Critical:** `method.module.bytecode` must be the `list[tuple]` bytecode for
the module, not the dict form. Verify that `NodusModule.bytecode` holds the
correct form (it's typed `Any` after the mypy fixes). If it's a dict (cached
form), read the `instructions` key.

### Step 4 — Remove `current_task` guards

In `src/nodus/builtins/http_module.py` `_do_async_request`:
```python
# Remove this guard:
# if (scheduler is None or coroutine is None or
#         coroutine is not getattr(scheduler, "current_task", None)):
# Replace with:
if scheduler is None or coroutine is None:
```

Same in `src/nodus/builtins/subprocess_module.py` `_do_async_run`.

### Step 5 — Tests

Add to `tests/test_subprocess.py` class `AsyncSyncTests`:
```python
def test_run_async_via_module_wrapper_is_concurrent(self):
    """subprocess.run_async via std:subprocess module wrapper runs concurrently."""
    src = (
        f'let co1 = coroutine(fn() {{ '
        f'let r = subprocess.run_async([{_PY}, "-c", "import time; time.sleep(0.5)"])\n'
        f' print(r.exit_code) }})\n'
        f'let co2 = coroutine(fn() {{ '
        f'let r = subprocess.run_async([{_PY}, "-c", "import time; time.sleep(0.5)"])\n'
        f' print(r.exit_code) }})\n'
        f'spawn(co1)\nspawn(co2)\nrun_loop()'
    )
    import time
    t0 = time.monotonic()
    out = _run_src(src)
    elapsed = time.monotonic() - t0
    self.assertLess(elapsed, 0.8, "two 0.5s concurrent subprocesses should finish in < 0.8s")
    self.assertEqual(len(out), 2)
```

Add similar test for `http.get_async` in `tests/test_http.py`.

### Step 6 — Update TECH_DEBT.md

Change the ASYNC-MOD-001 entry from open to fixed. Remove the workaround note.
Update the `current_task` guard documentation in the code comments.

## Key constraints

- `NodusModule.bytecode` — confirm at runtime that it holds a `list[tuple]` (the
  actual instructions). If it's a `dict` (the serialized cache payload), use
  `method.module.bytecode.get("instructions", [])`.
- The `cross_module_code` frame attribute must be cleaned up in ALL frame-pop paths:
  `_op_return`, `handle_exception` (frame unwinding), `run_closure`. Search for every
  `frames.pop()` call and add the restoration check.
- Nested module calls (module A calling a function from module B): the `_code_stack`
  must handle arbitrary depth. Each cross-module frame push saves the current code;
  each cross-module frame pop restores it. Test with 2-level nesting.
- `max_frames` check: apply it to the cross-module call_closure path too.
- Ruff and mypy must pass after the change.

## Dev environment

```powershell
cd "C:\dev\Coding Language"

# Run tests
PYTHONPATH="C:/dev/Coding Language/src" `
  "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/ -q --tb=no `
  --ignore=tests/test_scheduler_fairness.py

# Type check
"C:/dev/Coding Language/.venv/Scripts/python.exe" -m mypy src/nodus/ --ignore-missing-imports

# Lint
"C:/dev/Coding Language/.venv/Scripts/python.exe" -m ruff check src/nodus/
```

## Commit and push

```powershell
git commit -m @'
fix(async): enable yield propagation through std: module function calls (ASYNC-MOD-001)

Adds _code_stack to VM. _op_call_method swaps vm.code to the module's
code segment and uses call_closure instead of invoke_function when
dispatching module functions from a scheduler-managed coroutine. This
keeps the call in the same execute() loop so ChannelRecvRequest yield
propagates correctly.

subprocess.run_async() and http.get_async() via module wrappers now
achieve genuine concurrency matching the direct builtin path.

Removes current_task guard from _do_async_request/_do_async_run.
Closes #105 (ASYNC-MOD-001).

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
'@
```

Push to `github.com/Masterplanner25/Nodus`.
