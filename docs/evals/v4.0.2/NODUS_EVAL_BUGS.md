# Nodus v4.0.2 — Eval Bug Report

**Eval date:** 2026-06-10  
**Version:** v4.0.2 (PyPI, POST-PUBLISH)  
**Evaluator:** Claude Fable 5 (independent)  
**Environment:** Python 3.11.9, Windows 11, fresh `pip install --no-cache-dir nodus-lang`  
**Repro project:** `Nodusv4.0.2 fable5/probes/` — minimal repros for all bugs  

Total bugs found: 18 (P0: 2, P1: 3, P2: 4, P3: 9)

---

## P0 — Critical

### B1. Tool registered in an imported module + invoked inside a workflow step ⇒ entry-script re-execution storm

**Severity:** P0 — correctness catastrophe  
**Subsystem:** runtime / module loader / tool registry  
**Affects:** v4.0.2

**Repro:**
- `probes/repro_storm_imported_register.nd` — storms (~35 re-executions before limits kill it)
- `probes/repro_storm_inline_register_CLEAN.nd` — identical except registration site; clean

**Behavior:** A script whose workflow step calls `tool.invoke()` on a tool registered
inside an *imported* module re-executes the entire entry script in a loop. Top-level
side effects re-run each time. Secondary symptoms: `maximum recursion depth exceeded`
inside `tool.invoke`, error locations attributed to the wrong file/function,
`Sandbox error: stdout limit exceeded`, and hundreds of orphaned graph snapshots in
`.nodus/graphs/` (210 after two failed runs).

**Workaround:** Register from the entry module (using an imported handler function is
fine); only the registration *call-site* matters. Clean but fragile — nothing in the
language or docs warns about this.

**Fix direction:** Identify why `tool.invoke` in a workflow step triggers re-execution
of the module that called `tool.register`. Likely a module loader re-entry triggered
by the tool dispatch path.

---

### B2. Step-level `with { retries: N }` never completes under `nodus run`

**Severity:** P0 — advertised feature is a silent no-op  
**Subsystem:** workflow runtime / CLI  
**Affects:** v4.0.2

**Repro:** `probes/repro_retry_step.nd` — step with `retries: 2` that always throws.

**Behavior:** Returns immediately: `failed=[]`, `attempts=1`, no retry ever executes.
An incomplete run is persisted to `.nodus`. The workflows guide §5 shows a synchronous
"succeeded on attempt 3.0"; the skill reference admits retries are async and need a
"sweep loop", but `nodus run` has no sweeper.

**Fix direction:** `nodus run` should either (a) run the sweep loop inline until the
workflow reaches a terminal state, or (b) document prominently that `retries:` requires
the server mode and `nodus run` is not the right CLI entry point for retry workflows.

---

## P1 — High

### B3. Workflow state variables invisible inside string interpolation

**Severity:** P1  
**Subsystem:** compiler / workflow lowering  
**Affects:** v4.0.2

**Repro:** `probes/repro_state.nd` case t2.

```nd
workflow w {
    state x = 0i
    step a {
        x = 5i
        print("\(x)")   // runtime: Undefined variable: x
        print(x)        // works fine
    }
}
```

State rewriting does not apply inside interpolation expressions. Insidious because
interpolation is the recommended way to print (single-arg `print` rule).

---

### B4. `let` in a `for` loop body does not create per-iteration bindings

**Severity:** P1  
**Subsystem:** compiler / scoping  
**Affects:** v4.0.2

Closures created inside a loop all capture the final iteration's value. Combined with
the documented silent-shadow closure rule, closures over anything mutable in loops are
a minefield. Sentinel required a factory-function workaround.

---

### B5. Coroutine errors are swallowed by `run_loop()`

**Severity:** P1  
**Subsystem:** scheduler  
**Affects:** v4.0.2

A worker coroutine that throws prints to stderr and dies; `run_loop()` returns normally.
No flag, no result status, nothing on the channel. Silent data loss in fan-out pipelines.

---

## P2 — Medium

### B6. `tool.register` accepts JSON-Schema-style schemas that explode at invoke time

**Severity:** P2  
**Subsystem:** std:tool  
**Affects:** v4.0.2

`schema: {type: "object", properties: {...}, required: [...]}` (the form shown in
`docs/guide/ai-primitives.md`) registers fine, then every `tool.invoke` fails with:

```
argument of type 'Record' is not iterable
```

The undocumented "simple form" (`{"param": "string"}`) works. Docs are actively
misleading. Fix: validate schema format at `register` time and reject or normalize
nested Records.

---

### B7. `time.format()` produces garbage on common patterns

**Severity:** P2  
**Subsystem:** std:time  
**Affects:** v4.0.2

```nd
time.format(time.now(), "%Y-%m-%d %H:%M:%S")
// → "%Y-%54-%10 %22:%6:%S"
// minute substituted for %m, month for %M, %Y/%S untouched, % left in
```

---

### B8. `nodus test` crashes on default Windows consoles

**Severity:** P2  
**Subsystem:** tooling / test runner  
**Affects:** v4.0.2, Windows

```
UnicodeEncodeError: 'charmap' codec can't encode character '✗'
```

Raw traceback, no helpful message. Workaround: `PYTHONIOENCODING=utf-8`.

---

### B9. `nodus test` cannot import project code from a `tests/` subdirectory

**Severity:** P2  
**Subsystem:** tooling / test runner  
**Affects:** v4.0.2

Imports resolve relative to the test file's directory, ignoring the `nodus.toml`
project root that `nodus run` honors. `../lib/x` is rejected as "escapes the project
root" even when it doesn't. Tests must live in the project root to import project code.

---

## P3 — Low / paper cuts

### B10. `cb.create` config map form fails at runtime

**Severity:** P3  
**Subsystem:** std:circuit_breaker  
**Affects:** v4.0.2

`cb.create(name, config_map)` (documented form) → `int() argument must be ... not 'Record'`.
Real signature: `cb.create(name, failure_threshold, recovery_timeout_secs)` — positional,
timeout in seconds not ms.

---

### B11. `cb.call` never throws; failures indistinguishable from success

**Severity:** P3  
**Subsystem:** std:circuit_breaker  
**Affects:** v4.0.2

`cb.call` failures return a plain map `{"kind": ..., "message": ...}`. This is
type-identical to a legitimate map-shaped success value, making error detection
impossible without knowing the success shape in advance.

---

### B12. `identity.trace_id()` / `identity.session_id()` return nil under the CLI

**Severity:** P3  
**Subsystem:** std:identity  
**Affects:** v4.0.2

Docs say auto-generated when unset. Under `nodus run`, both return `nil`. Identity
propagation only fully works in embedded mode (`NodusRuntime.set_trace_id()`).

---

### B13. `mem.tag` / `mem.forget` documented but not implemented

**Severity:** P3  
**Subsystem:** std:memory  
**Affects:** v4.0.2

Both functions are documented in `docs/guide/ai-primitives.md` but calling either
raises `Missing module export`. They do not exist in the installed runtime.

---

### B14. `tool.execute` / `tool.available` documented but not the real API

**Severity:** P3  
**Subsystem:** std:tool  
**Affects:** v4.0.2

The skill's modules reference lists `tool.execute` and `tool.available`. The real API
is `tool.invoke`/`tool.call`/`tool.has`. Builtin `tool_available()` exists but takes
0 arguments (undocumented behavior).

---

### B15. `std:effects` docs describe a different API than ships

**Severity:** P3 (doc gap)  
**Subsystem:** std:effects  
**Affects:** v4.0.2

Documented vs real API divergence:

| Item | Docs say | Reality |
|---|---|---|
| `action_id` signature | `fx.action_id(name, params)` | `action_id(action_type, payload, scope)` — 3 positional args |
| `resolve` return | status string `"pending"` / `"complete"` | record `{done, cached}` |
| `complete` status arg | not mentioned | must be `"success"` to count; wrong value silently no-ops |
| `pending` requirement | not mentioned | `complete` silently no-ops without a prior `pending` call |
| `fx.get_result()` | documented | does not exist |

The pending-before-complete silent no-op is particularly dangerous: an idempotency
primitive that fails open is worse than no idempotency primitive.

---

### B16. Failed-step reporting inconsistent between workflow and goal

**Severity:** P3  
**Subsystem:** runtime / result map  
**Affects:** v4.0.2

Workflow results list task IDs in `failed` (`["task_8"]`); goal results list step names
(`["assemble"]`). Same field, different semantics.

---

### B17. `nodus test` not listed in `nodus --help`

**Severity:** P3  
**Subsystem:** tooling / CLI  
**Affects:** v4.0.2

`nodus --help` does not include the `test` subcommand. First-time users have no
discoverability path.

---

### B18. Workflow run snapshots pile up forever in `.nodus/`

**Severity:** P3  
**Subsystem:** workflow runtime  
**Affects:** v4.0.2

Runs returning `retry_scheduled` or incomplete are persisted to `.nodus/graphs/` with
no automatic cleanup. 210 snapshots accumulated after two failed B1 runs. Stale runs
amplified the B1 storm (B1 re-executes each run in the store). No `nodus workflow
cleanup` command exists; no docs mention this operational concern.
