# Nodus Runtime Profiler

The profiler is a lightweight, optional component that instruments the VM execution loop without altering language semantics. It provides quick, practical insight into runtime behavior.

## Architecture

- Implemented as `Profiler` in `src/nodus/runtime/profiler.py`.
- Stored on the VM (`VM.profiler`) and only used when `profiler.enabled` is `True`.
- Uses simple dictionaries for counts and timing to keep overhead low.
- Measures elapsed time with `time.perf_counter()` and reports in milliseconds.

## Opcode Counting

- Each VM instruction is recorded by opcode name.
- The VM execution loop checks `profiler.enabled` and calls `profiler.record_opcode(op)`.
- Counts are accumulated in `Profiler.opcode_counts`.

## Function Call Counting

- Each VM call site records a function call by name.
- Calls are aggregated in `Profiler.function_calls`.
- Names use the display-friendly name (e.g., nested function suffixes are stripped).

## Function Timing

- The profiler tracks a lightweight call stack of `(name, start_time)`.
- `enter_function(name)` pushes a timestamp.
- `exit_function(name)` pops and accumulates elapsed time in `Profiler.function_time`.
- Timing is inclusive (callee time is included in caller time).
- On exceptional unwinds, the VM exits profiler frames as call frames are discarded.

## CLI Usage

Human-readable report:

```bash
nodus profile examples/demo.nd
```

JSON output for automation:

```bash
nodus profile examples/demo.nd --json
```

Example JSON output:

```json
{
  "runtime_ms": 8.3,
  "functions": [
    { "name": "main", "calls": 1, "time_ms": 2.3 }
  ],
  "opcodes": {
    "LOAD_CONST": 120,
    "CALL": 40,
    "ADD": 25
  }
}
```

## Notes

- Profiling is opt-in. If `VM.profiler` is `None` or disabled, the VM runs without profiling overhead beyond a single guard.
- The profiler is per-VM and does not currently isolate coroutine timing.
