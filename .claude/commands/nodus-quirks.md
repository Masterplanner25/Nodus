---
description: "Nodus language quirks that burn time: maps vs records, syntax traps, aliasing, task statuses, the nodus run budget. Read before writing or debugging .nd code."
---

# Nodus language quirks

> Moved out of the root `CLAUDE.md` on 2026-11-05 so it loads on demand. "This file" in the text
> below may mean the root file as it was. A section it names may now be in another file:
> release rules in `.claude/commands/release-sequence.md`, the bug shape in
> `.claude/commands/recurring-bug-shape.md`, embedding in `.claude/commands/nodus-embedding.md`.

## Nodus language quirks (relevant when writing test .nd code)

These burn time when forgotten:

- **No `await` keyword.** `test.flush_async()` is synchronous — no `await`.
- **`+=`, `-=`, `*=`, `/=` work** (added in 4.0.1 pre-release, PR #183), including inside
  closures.
- **Closures CAN mutate an outer `let`**, including a module-top-level one (#671,
  fixed in 5.8.0). Verified by running each case: `fn make_counter() { let n = 0i;
  return fn() { n = n + 1i; return n } }` returns 1 then 2; so do two closures
  sharing one captured variable, two-level nesting, mutation from inside a
  spawned coroutine, and `n += 5i`.

  **This entry asserted the opposite for a long time** and sent every session to
  an unnecessary quoted-key-map workaround. That is the reason it names its
  evidence: a quirk entry nobody re-runs becomes a quirk of the file. #671's
  mechanism is in the recurring-bug-shape table.
- **Maps vs Records — dot vs bracket notation:**
  - `{"key": val}` (quoted keys) → **map** → access with `state["key"]`
  - `{key: val}` (unquoted keys) → **record** → access with `state.key`
  - Mixing them causes "Field access is only supported on records" or
    "Indexing is only supported on lists and maps". Never use dot on a map.
- **`run_workflow()` and `run_goal()` return maps** — use bracket notation:
  `result["steps"]`, `result["failed"]`, `result["goal"]`. NOT `result.steps`.
- **Channels are built-in functions, NOT a stdlib module.** `import "std:channel"`
  fails with "Import not found". Use built-ins directly: `channel()`, `send(ch, val)`,
  `recv(ch)`, `close(ch)`. No import needed.
- **Workflow step dependencies use `after` keyword:**
  `step b after a { ... }` — not `depends_on`, not any other syntax.
- **Cross-module closures work in both directions** (#691, #696, fixed in 5.9.0).
  The lesson they left is the part to carry: every test and probe for
  `retry.until` ran inside `fn main()`, so the full suite, nine gate phases and 83
  release probes were green on a feature that did not work where it is meant to be
  used — inside a step body, which is where its own documentation points. **A
  construct documented for use inside a step body must be tested inside a step
  body.** Mechanism in the recurring-bug-shape section.

- **`checkpoint` is valid INSIDE step bodies only**, not at workflow-body level.
  `step a { checkpoint "mid"; return "done" }` — correct.
  `workflow w { checkpoint "mid"; step a { ... } }` — syntax error.
  **And it is a re-entry label for its whole step, not a position marker** (#486):
  a resume re-enters the step from the top, so effects before the checkpoint run
  again on every resume. Split the step at the checkpoint to skip completed work.
  State re-derives deterministically — including folded cells since the #486 fix
  (`resume_state` on the engine checkpoint; before it, `merge: "sum"` counted
  pre-checkpoint contributions once per resume).
- **Async test two-flush pattern:** `spawn → flush (task sleeps) → advance_clock(N) → flush (task wakes)`.
  Skipping either flush or the advance causes the test to pass vacuously.
- **`spawn()` accepts a zero-argument function directly** (#718) —
  `spawn(fn() { ... })` wraps and spawns, returning the handle; `spawn(c)` after
  `let c = coroutine(fn() {...})` is unchanged. #336 proposed a `spawn { }`
  keyword for the same footgun and was rejected: the grammar position it needs is
  the one `match` occupies (#717). Widening the builtin delegates to
  `coroutine()`'s own path, so the zero-arity check and the ASYNC-MOD-003/#691
  origin pinning are not duplicated.
- **`fn` is a reserved keyword** — can't use as a parameter name in `.nd` files.
- **`if` conditions with function calls require parentheses.** `if (module.fn(a, b))` works;
  `if module.fn(a, b)` gives "Expected '(', got identifier". Simple field access works without
  parens (`if record.field`), but call expressions need `if (expr)`.
  **A bare `state` variable also needs them** inside a step body: `if approve { ... }` gives
  "Expected '(', got identifier ('approve')"; `if (approve) { ... }` works.
- **`sleep_until(deadline_ms)` waits to an instant; `sleep(ms)` waits for a
  duration** (#182, 5.11.0). Both are global builtins. Reach for the absolute
  form in any loop with a period, because a relative sleep adds whatever the body
  cost to every iteration — measured, five iterations of 30 ms of work: 650 ms
  with `sleep`, 500 ms against fixed instants.

  **The deadline is on the scheduler's clock, which `runtime.time_ms()` reads.**
  Not `clock()`, which is epoch *seconds*, and not `std:time`, which is wall
  clock. Mixing them is not approximate, it is meaningless (#778). A deadline
  already past yields once rather than returning, so an overdue loop cannot
  starve its siblings.

  `spawn_after(ms, fn)` defers a spawn. `std:loop` wraps both — `now`, `deadline`,
  `at`, `run_after`, `every`, `until` — and is written in Nodus with no host code.
  **`run_after`, not `after`**: `after` is a reserved word, so `loop.after(...)`
  does not parse. Every *contextual* keyword tried (`each`, `over`, `when`,
  `state`, `until`) is a legal field name; only the reserved one is out.
- **A `state` cell can declare its own join: `with { barrier: true }`** (#578).
  Every step that *reads* the cell waits for every step that *writes* it,
  inferred — `step d after b, c` says the same thing but goes stale when a
  fourth writer is added. Composes with `merge:`. Its writers must write
  **unconditionally**: a write inside an `if`, a loop or a `match` arm, or a
  step carrying `when`, is refused at declaration, because a reader waiting for
  a writer that may not write waits forever. The inferred edges are *ordering*,
  not data — a barrier reader's body stays zero-parameter, unlike `after`, which
  binds one parameter per dependency.
- **Containers alias; assignment binds, it does not copy.** `let b = a` gives a second
  name for one list, map or record — mutating through either is visible through both, at
  any depth and across a call boundary, and from inside a coroutine or a step body. There
  is **no copy or clone builtin**, so "hand this container to a step without letting it
  mutate mine" is currently inexpressible. Pinned by `tests/test_container_aliasing.py`
  (#818); **#814 is open** on stating the rule in the guide and deciding whether a copy
  surface is owed, so treat the test as *what the VM does*, not as a ratified contract.

  **`copy(value)` is the deep copy** (#814, 5.13.0) — a global, no import. It preserves
  shared structure rather than expanding it, terminates on a cycle, and **refuses** a
  value holding a function, method, channel, coroutine or task, naming where it is.

  **A workflow `state` cell is the one exception: it owns its value** (#822). Writing a
  container into a cell stores a copy and reading one hands back a copy, so a step cannot
  change a cell by mutating what it read or what it assigned from. `cell[i] = v` is still
  a write and is recorded as one — that is the fix, not a side effect.

  Two things that mislead in opposite directions. `list_push` **mutates in place** and
  returns the same list; `xs = list_push(xs, v)` reads functional and is not, so use the
  bare form — `tests/test_list_push_idiom.py` fails on the reassignment now (#816), and
  chaining is what the return value is for. And record `==` becomes **structural** at
  6.0.0 (#545) while binding stays by reference — so "records became value types" is the wrong reading of that flip;
  lists and maps have had that same shape (structural `==`, reference mutation) all along.
- **A `state` cell cannot hold a record.** The run aborts at persist time with
  `Object of type Record is not JSON serializable`, blamed on the `run_workflow(...)` call
  site rather than the assignment. Records are ordinary data with an obvious JSON shape, so
  this reads as a plain gap rather than the live-handle case — but it is the same
  undeclared serializability requirement as a closure or a channel (#498). Use a map.
- **Seven task statuses, and `on:` admits three of them.** `statuses` reports `completed`,
  `failed`, `upstream_failed`, `skipped`, `omitted`, `cancelled`, `abandoned`;
  `with { on: [...] }` accepts only `completed`, `failed`, `skipped` — the three a dependency
  can reach *while the run is going*. The rest are end-of-run conclusions, so a step waiting
  on one could never become ready, and they are refused at declaration. The vocabulary is
  named once in `TASK_STATUSES` / `JOIN_ON_STATES` and pinned by
  `tests/test_status_vocabulary.py`; do not re-enumerate it in prose without checking those.
- **Multiline list literals and function calls cannot span newlines.** Both
  `[1,\n2]` and `len(\n"hi"\n)` give "Unexpected end of statement". Keep on one line.
- **`print()` is single-argument.** `print("label:", value)` → syntax error.
  Use string interpolation: `print("\(label): \(value)")`.
- **`std:hash` returns a hash record, not a string.** `hash.sha256(data)` returns
  a record with methods; call `.to_hex()` to get hex: `hash.sha256(data).to_hex()`.
- **`std:tool` names must be dotted.** `tool.register({name:"greet",...})` silently
  returns an error. Use `"myapp.greet"`. Error message says "must use dotted namespacing".
- **`http.get()` and `subprocess.run()` return records** — use dot notation:
  `result.status`, `result.body`, `result.ok` (http); `result.stdout`, `result.exit_code` (subprocess).
- **CLI sandbox flag is `--allow-paths`** (not `--allowed-paths`). Relative paths
  resolve against CWD. To block a specific subdir, pass an explicit absolute path.
- **`goal … over …` is the v5.0.0 stopping-condition form** (#409). A goal now wraps a workflow
  and re-runs it until a predicate holds:
  ```
  goal reach_quality over tune {
      until reached("good_enough")
      budget { max_iterations: 5, deadline_ms: 30000 }
  }
  ```
  `reached("label")` refers to a `checkpoint "label"` inside a step body. **A label that no step
  emits is a compile error**, not a silent never-satisfied loop (`frontend/goal_validation.py`) —
  so `nodus check` catches the typo. Result map adds `goal_satisfied` and `iterations`.
  Five new **contextual** keywords: `over`, `until`, `budget`, `reached`, `retry` — contextual, so
  they remain usable as identifiers.
- **`nodus run` bounds the WHOLE program at 200ms of wall clock**
  (`EXECUTION_TIMEOUT_MS`), not just a coroutine. Cooperative sleep counts, so a
  coroutine sleeping 4 × 100ms is killed having consumed no CPU — but so is any
  script that simply does 200ms of work. Fix: `nodus run --time-limit N`, in
  **seconds**. SCHED-001, deferred to 4.0.1.

  **The reason nobody reads this off the CLI is a `None` that round-trips back to
  the default.** `cli.py`'s `run` branch passes `timeout_ms=None if time_limit is
  None else ...`, which looks like "unbounded unless asked"; two frames later
  `cli.run_file` does `timeout_ms=EXECUTION_TIMEOUT_MS if timeout_ms is None else
  timeout_ms` and puts the 200ms back. Reading either site alone tells you the
  opposite of what happens.

  **An `import` is charged to that budget**, because the import compiles the
  imported module *during* the run. So a two-file script can time out having
  executed almost nothing of its own. This is what took
  `test_cross_module_closure.py` down on CI (fixed in #711): measured, the case
  spent ~78ms of the 200ms warm and failed outright below 40ms — a 2.5x margin
  where the rule here is 5-10x, and CI is colder still, since a fresh process pays
  the compiler's own lazy imports inside the window.

  **A CLI subprocess test that imports a module needs `--time-limit`.** Put it on
  the harness, not the one test that happened to go red — every case in the file
  shares the exposure. And check the embedded half of any both-ways harness:
  `NodusRuntime(timeout_ms=None)` is genuinely unbounded, so the two halves were
  bounded differently while claiming to run the same program.
