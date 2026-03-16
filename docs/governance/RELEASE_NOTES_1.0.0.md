# Nodus 1.0.0 Release Notes

**Released: 2026-03-15**

Nodus 1.0.0 is the first stable release. The bytecode instruction set is frozen, the
embedding API is stable, and the language feature set for v1.0 is complete.

---

## Headline Changes

### Opcode Freeze

The Nodus VM instruction set is now frozen at **47 stable opcodes**, `BYTECODE_VERSION = 4`.
No provisional opcodes remain. Post-freeze additions require a formal extension proposal
and a `BYTECODE_VERSION` bump (see `docs/governance/FREEZE_PROPOSAL.md`).

The full opcode reference is in `docs/runtime/BYTECODE_REFERENCE.md`.

### `try / catch / finally`

Full `finally` block support is shipped. All five exit paths are handled:

```nd
fn transfer(amount) {
    try {
        debit(amount)
        credit(amount)
    } catch err {
        log("transfer failed: " + err.message)
    } finally {
        audit_log("transfer attempted")
    }
}
```

- `finally` always runs — whether the try body succeeds, an exception is caught, or
  `return` executes inside the try block.
- Return values are preserved across the finally block (`_deferred_return` mechanism).
- Nested finally blocks work correctly.
- New `FINALLY_END` opcode marks the end of every finally block.
- `SETUP_TRY` extended to two operands: `SETUP_TRY handler_ip [finally_ip]`.

### Structured Throw Values

`throw` now preserves non-string values as a structured payload:

```nd
try {
    throw record { code: 404, reason: "not found" }
} catch err {
    print(err.kind)          // "thrown"
    print(err.payload.code)  // 404
}
```

String throws still populate `err.message` directly. The catch variable always exposes:
- `err.message` — human-readable description
- `err.kind` — error category (`"thrown"`, `"name"`, `"type"`, `"index"`, ...)
- `err.payload` — original thrown value when a non-string was thrown; `nil` otherwise

### Iterator Protocol Cleanup

`GET_ITER` and `ITER_NEXT` now use a first-class `Iterator` class. The previous
`pending_get_iter` / `pending_iter_next` VM flags are fully removed. All iterator
paths (list, `__iter__`, `__next__`) resolve synchronously via `run_closure()`.
Both opcodes are promoted to stable.

### `LOAD_LOCAL` Removed

`LOAD_LOCAL` (the name-keyed local variable opcode, deprecated in v0.8.0) has been
removed from the VM dispatch table. The compiler now exclusively emits `LOAD_LOCAL_IDX`
(slot-indexed) for all function-local variable reads. Cached bytecode from
`BYTECODE_VERSION = 2` is automatically recompiled on next load.

### Stable Embedding API

`NodusRuntime` is now exported from `nodus.__all__`:

```python
from nodus import NodusRuntime   # stable as of v1.0

runtime = NodusRuntime(max_steps=500_000, timeout_ms=5000)
result = runtime.run_source(source_code)
```

Constructor parameters, `run_source()`, `run_file()`, `register_function()`, and
`reset()` are all stable. See `docs/runtime/EMBEDDING.md`.

### `compile_source()` Fully Removed

The `compile_source()` function body in `nodus.tooling.loader` has been removed (the
public re-export from `nodus.__init__` was already removed in v0.9.0). All callers
have been migrated to `ModuleLoader` or `NodusRuntime`.

---

## Breaking Changes

| Change | Impact | Migration |
|--------|--------|-----------|
| `BYTECODE_VERSION` bumped 3 → 4 | All `.ndsc` cache files invalidated | Automatic — stale caches are recompiled on next load |
| `LOAD_LOCAL` removed from dispatch | Any bytecode compiled with version 2 raises a tombstone `RuntimeError` | Recompile source; version bump invalidates caches automatically |
| `compile_source()` removed | Call sites break | Use `ModuleLoader(...).load_module_from_source(src)` or `NodusRuntime(...).run_source(src)` |
| Handler stack extended to 4-tuple | Internal change only | No user action required |

---

## What Shipped in the v1.0 Cycle

These changes accumulated across the v0.9.x → v1.0 development cycle:

- **Registry auth & publish** (v0.9.0) — `nodus login`, `nodus logout`, `nodus publish`.
  Three-tier token resolution: `--registry-token` flag → `NODUS_REGISTRY_TOKEN` env var →
  `~/.nodus/config.toml`. Bearer token injection into all registry requests.
- **Module system frozen** — `BUILD_MODULE` promoted to stable. Live bindings, re-exports,
  and circular import detection are feature-complete.
- **Slot-indexed locals** (v0.8.0) — `FRAME_SIZE` / `LOAD_LOCAL_IDX` / `STORE_LOCAL_IDX`
  give O(1) local variable access with no dict hashing.
- **Dict dispatch table** (v0.7.0) — `_build_dispatch_table()` replaced the O(n) if/elif
  chain (~33% throughput improvement on compute-heavy benchmarks).
- **Bytecode cache hardened** (v0.7.0) — `marshal` + NDSC magic + SHA-256 integrity check
  replaced `pickle`.
- **Incremental compilation** — `.nodus/deps.json` dependency graph skips unchanged modules.
- **LSP + DAP** — diagnostics, completion, hover, go-to-definition; breakpoints, stepping,
  variable inspection.
- **Workflow / goal DSL** — durable state, checkpoints, resume, distributed workers.
- **`_op_throw` fixed v0.9.x** — structured thrown values preserved as `err.payload`.
- **Flaky test fixed** (v0.9.1) — `test_task_reassignment_after_worker_failure` converted
  from a polling loop to a condition-variable wait; test runtime 2s → 20ms.

---

## Test Coverage

404 tests pass. New tests added in this release:
- `tests/test_finally.py` — 15 tests covering normal path, caught exception,
  return-inside-try, nested finally, and regression cases.

---

## Stability Guarantees

| Area | Status |
|------|--------|
| Core language syntax (`let`, `fn`, `if`, `while`, `for`, `try/catch/finally`, `throw`) | **Stable** |
| VM execution model and bytecode format | **Frozen** (BYTECODE_VERSION = 4) |
| 47 active opcodes | **Stable** |
| `NodusRuntime` embedding API | **Stable** |
| Module system (imports, exports, live bindings, re-exports) | **Stable** |
| Package manager (`nodus install`, `nodus publish`, registry auth) | **Stable** |
| Coroutines, scheduler, channels | Experimental |
| Workflows, goals, task graphs | Experimental |
| Runtime service APIs (tools/agents/memory/events) | Experimental |
| Optional type annotations and static analysis | Experimental |

---

## Upgrading

From v0.9.x:

1. Delete `.nodus/cache/` or let the runtime invalidate it automatically on next run
   (the `BYTECODE_VERSION` bump handles this).
2. Replace any remaining `compile_source()` calls with `ModuleLoader` or `NodusRuntime`.
3. No `.nd` source changes required.

From v0.8.x or earlier: see the v0.9.0 and v0.9.1 changelog entries in `CHANGELOG.md`
for intermediate migration steps.

---

If you're new to Nodus, start with `docs/onboarding/GETTING_STARTED.md` and run
`nodus run examples/hello.nd`.
