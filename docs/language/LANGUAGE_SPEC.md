# Nodus Language Spec

## Language Identity

Nodus is an **orchestration DSL**. Every feature in this spec exists to serve one
primary use case: expressing workflows, goals, coroutines, and tool chains as
first-class language constructs.

The core language — types, functions, control flow, closures — is deliberately
minimal and conventional. It is not trying to be novel. Its job is to be a
familiar, reliable host for the orchestration primitives (coroutines, channels,
task graphs, workflows, goals, tools) that are the actual reason Nodus exists.

A Nodus script that does nothing but print strings and do arithmetic is valid
Nodus but not idiomatic Nodus. Idiomatic Nodus uses coroutines, spawns tasks,
wires tool calls, and expresses business logic as workflow steps with checkpoints.

**Design positions that will not change without a major version:**
- No implicit returns. All functions return nil unless `return expr` is used.
- No operator overloading.
- `{key: value}` is a record; `{"key": value}` is a map. This is intentional and
  unambiguous (disambiguated by key syntax, not value content).
- `42i` is an integer; `42` is a float. No automatic promotion from integer context.
- Type annotations are hints for tooling and documentation. They do not change
  runtime behavior. This is a deliberate design position — Nodus is dynamically
  typed at runtime, and a `--strict` type-checking mode is the forward direction
  for static analysis, not enforcement baked into the language.

---

## Values
Stability: Stable (v3.0).
- number (float; scientific notation `1e3`, `2.5e-4`, `1E10` supported; `type()` returns `"float"`)
- int (integer literal suffix `i`: `42i`, `0i`, `-1i`; `type()` returns `"int"`; large integers stay exact)
- bool (`true`, `false`)
- string (double-quoted with escapes: `\\`, `\"`, `\n`, `\t`, `\r`, `\0`, `\xHH`, `\uXXXX`)
  - `\xHH` — hex byte (two hex digits, e.g. `\x41` → `A`)
  - `\uXXXX` — Unicode code point (four hex digits, e.g. `\u03B1` → `α`)
  - All escape errors (unterminated, unsupported, or malformed `\x`/`\u`) are reported as `LangSyntaxError` with source line and column.
- nil (`nil`)
- list (`[...]`)
- map (`{"key": value, ...}`) — keys must be **quoted strings**
- record (`record { key: value, ... }` or `{ key: value }` with bare-identifier keys)
- record methods: `record { greet: fn(self) { ... } }`, called as `obj.greet()`

**Record vs map literal disambiguation (v3.0):**
- `{ "key": value }` — **map** (quoted string key)
- `{ key: value }` — **record** (bare identifier key; shorthand for `record { key: value }`)
- `{ (expr): value }` — **map** with the runtime value of `expr` as the key
- Using a bare identifier as a map key is a **parse error** naming both correct forms.

**Record vs map access:**
- **record** — dot-access only: `r.name`, `r.field = value`. Methods called as `obj.method()`.
- **map** — bracket access: `m["key"]`, `m["key"] = value`. `has_key(m, "key")`, `keys(m)`, `values(m)` available. Returned by `json.parse` and certain stdlib calls.

## Variables and Assignment
Stability: Stable.
- Declare: `let x = expr`
- Optional annotation: `let x: int = expr`
- Destructuring list: `let [a, b] = expr`
- Destructuring record: `let {name, age} = expr`
- Reassign variable: `x = expr`
- Index assignment:
  - list: `xs[0] = value`
  - map: `m["key"] = value`
- Record assignment:
  - `rec.field = value`

## Operators
Stability: Stable.
- Arithmetic: `+ - * / %` (`%` is modulo; works for integer and float values)
- Comparison: `== != < > <= >=`
- Logical: `&& || !`
- Compound assignment: `+=`, `-=`, `*=`, `/=` (lower to expanded form at compile time)
- Truthiness: `nil` is falsey; booleans use natural value; others use Python-like truthiness.

## Control Flow
Stability: Mostly stable (missing `break`/`continue`).
- `if (...) { ... } else { ... }`
- `while (...) { ... }`
- `for (init; cond; inc) { ... }` lowered to while behavior.
- `for name in iterable { ... }`
- `try { ... } catch err { ... }`
- `try { ... } catch err { ... } finally { ... }`
- `throw expr`
- `yield expr` suspends the current coroutine and returns the yielded value to `resume(...)`

## Functions
Stability: Stable.
- Define: `fn name(args...) { ... }`
- Typed define: `fn add(a: int, b: int) -> int { ... }`
- Anonymous: `fn(args...) { ... }` (returns a function value)
- `return expr` or bare `return` (`nil`)
- Recursion supported.

## Coroutines
Stability: Experimental.
- Create: `let c = coroutine(fn_name)`
- Resume: `resume(c)`
- Status: `coroutine_status(c)` returns `created`, `running`, `suspended`, or `finished`
- Coroutines are cooperative, single-threaded, and preserve their own call stack between yields.
- Resuming a `running` or `finished` coroutine is a runtime error.
- `spawn(coroutine)` schedules a coroutine to run on the event loop.
- `run_loop()` runs the scheduler until there are no runnable coroutines or timers.

## Channels
Stability: Experimental.
- Create: `let ch = channel()`
- Send: `send(ch, value)` enqueues a value or wakes a waiting receiver.
- Receive: `recv(ch)` returns the next value, or blocks if none are available.
- Close: `close(ch)` stops future sends. `recv(ch)` on a closed empty channel returns `nil`. Any coroutines blocked in `recv(ch)` at the time of the close are woken and receive `nil`; only coroutines in `suspended` state are eligible to be woken.

## Static Types
Stability: Experimental (syntax accepted; enforcement not yet implemented).

Type annotations are optional hints for tooling and human readers. They do not
change runtime behavior — this is intentional. Nodus is dynamically typed at
runtime. The type system is designed to add value progressively:

- **Today:** Annotations are parsed and preserved in the AST. `nodus check`
  validates syntax but not types. The LSP can use annotations for hover and
  completion hints.
- **Forward direction:** `nodus check --strict` will enable type inference and
  flag assignments that violate declared types. This is tooling-layer enforcement,
  not language-layer enforcement — the same model as TypeScript or Python `mypy`.

Supported type names:
- `int`, `float`, `string`, `bool`, `list`, `record`, `function`, `any`

```nd
fn greet(name: string) -> string {
    return "Hello, " + name
}
```

Programs without annotations are fully valid and run identically to annotated
programs. The annotation syntax is stable; the enforcement semantics will be
specified in a design doc before `--strict` ships.

## Iteration Protocol
Stability: Mostly stable (protocol details may evolve).
- `for name in iterable { ... }` uses a simple protocol:
  - Lists are iterable by default.
  - Records can implement `__iter__(self)` and `__next__(self)`.
  - `__iter__` should return a list or a record that provides `__next__`.
  - `__next__` returns the next value or `nil` to signal completion.

## Imports
Stability: Syntax stable; runtime module semantics mostly stable.
- `import "path/file.nd"`
- `import { name, add } from "path/file.nd"`
- `import "path/file.nd" as mod`
- `import "std:strings"`
- `import "utils:strings"`
- Namespaced member access: `mod.name`, `mod.fn(...)`
- Namespace imports produce runtime module objects, so aliases can be passed to reflection helpers and retain live exported state.
- Named imports are live bindings to the exporting module rather than copied values.
- Imported modules execute once per run and are cached by resolved module path.
- Each module maintains its own isolated global namespace.

Import behavior:
- `import "mod.nd" as mod` binds `mod` to a runtime module object.
- `mod.name` reads the current exported value from the module.
- `mod.name = expr` writes back to the exported binding when `name` is exported.
- `import { name } from "mod.nd"` binds `name` as a live import. Reassigning `name` updates the exported binding in the source module.

Import resolution:
- `std:` prefix resolves to built-in `std/` modules (e.g. `std:strings`).
- `package:module` resolves under `.nodus/modules/<package>/...` (e.g. `utils:strings` -> `.nodus/modules/utils/strings.nd`).
- Relative paths (`./` or `../`) resolve from the importing file's directory. A relative path that would resolve outside the project root (or, in single-file execution, outside the entry file's directory) is always rejected **before any filesystem access** with: `Invalid import: path '<path>' escapes the project root.` This rule applies equally in the CLI and the REPL.
- Bare paths (no leading `.`, no `:` prefix) resolve in this order:
  1. `<project_root>/<path>` (project-root-relative)
  2. `<project_root>/.nodus/modules/<path>` (installed packages)
  3. `<stdlib>/<path>` (built-in stdlib modules)
  - If none found: error naming all candidates tried.
  - If no project manifest is found, `<project_root>` falls back to the importing file's directory.
- If no extension is provided, resolution checks in order: `.nd`, `.tl`, `<path>/index.nd`, `<path>/index.tl`.
- Cyclic imports are detected and reported as `LangSyntaxError`.
- The import chain depth is limited to 100 levels by default (override with the `NODUS_MAX_IMPORT_DEPTH` environment variable). Exceeding the limit raises a `LangSyntaxError` with a clear message rather than a Python `RecursionError`.
- `nodus run --trace-imports` prints one `[import] Resolved "path" → /abs/path` line to stderr per resolved import. Failed imports print `[import] Failed "path" — <reason>` before the error.

## Projects And Packages
Stability: Experimental (git-only, may change).
- Manifest file: `nodus.toml`
- Lock file: `nodus.lock`
- Installed dependencies live under `.nodus/modules/`
- Minimal manifest example:
  
  ```
  [package]
  name = "example"
  version = "0.1.0"
  
  [dependencies]
  utils = "1.0.0"
  ```
  
- CLI:
  - `nodus init` creates `nodus.toml`, `src/main.nd`, and `.nodus/modules/`
  - `nodus install` installs manifest dependencies into `.nodus/modules/` and writes `nodus.lock`
  - `nodus deps` prints the runtime module dependency graph from `.nodus/deps.json`
  - `nodus package-list` lists declared dependencies and resolved lock entries

### Re-exports
- `export { name } from "./module.nd"`
- Re-exported names must already be exported by the target module.
- Re-exports do not grant access to private names.

## Exports
Stability: Syntax stable; visibility semantics mostly stable.
- `export let name = expr`
- `export fn add(a, b) { ... }`
- `export { name, add }`

Module visibility rules:
- If a module uses any `export` declaration, **only** explicitly exported names are visible to importers.
- Modules without any `export` declarations export all top-level `let`/`fn`/assignment names (legacy compatibility).
- Accessing a non-exported name from another module is an error.
- Exported bindings remain live after import, so later writes are visible through namespace aliases and named imports.

## Built-ins
Stability: Mixed. Core built-ins stable; orchestration/tooling built-ins experimental.
- `clock()`
- `type(x)` — returns `"float"` for floats, `"int"` for integer values (`42i`), `"bool"`, `"string"`, `"nil"`, `"list"`, `"map"`, `"record"`, `"function"`, `"error"`. Use `rt.typeof(x)` from `std:runtime` for the internal runtime type name.
- `str(x)`
- `len(x)` for list/map/string
- `print(x)`
- `input(prompt)`
- `keys(map)`
- `values(map)`
- `has_key(map, key)` — O(1) map membership test; returns `true` if `key` exists in `map`
- `read_file(path)`
- `write_file(path, content)`
- `append_file(path, content)`
- `exists(path)`
- `mkdir(path)`
- `path_join(a, b)`
- `path_dirname(path)`
- `path_basename(path)`
- `path_ext(path)`
- `path_stem(path)`
- `coroutine(fn)` for zero-argument function values
- `resume(coroutine)`
- `coroutine_status(coroutine)`
- `spawn(coroutine)`
- `run_loop()`
- `sleep(ms)`
- `channel()`
- `send(channel, value)`
- `recv(channel)`
- `close(channel)`
- `task(fn, deps)` creates a task node (deps can be a task, list, or a map like `{ deps: [...], timeout_ms: 50, worker: "gpu", worker_timeout_ms: 1000 }`)
- `graph(tasks)` builds a task graph
- `run_graph(graph_or_tasks)` executes a task graph
- `run_workflow(workflow)`
- `plan_workflow(workflow)`
- `resume_workflow(graph_id, checkpoint=nil)`
- `run_goal(goal)`
- `plan_goal(goal)`
- `resume_goal(graph_id, checkpoint=nil)`
- `workflow_state()` returns the current workflow state map or `nil`
- `workflow_checkpoints(graph_id)` returns checkpoint metadata for a workflow run
- `current_workflow_id()` returns the active workflow graph id or `nil`
- `emit(name, payload={})` emits a runtime event and returns the payload
- `tool_call(name, args)` dispatches a registered runtime tool and returns a structured result
- `tool_available()` returns registered tool names
- `tool_describe(name)` returns tool metadata or `nil`
- `memory_get(key)` reads a local runtime memory entry or `nil`
- `memory_put(key, value)` stores a JSON-safe value and returns it
- `memory_delete(key)` removes a memory entry and returns `true` if it existed
- `memory_keys()` returns memory keys
- `agent_call(name, payload)` dispatches a registered agent handler and returns a structured result
- `agent_available()` returns registered agent names
- `agent_describe(name)` returns agent metadata or `nil`
- `runtime_tasks()`
- `runtime_task(id)`
- `runtime_scheduler_stats()`
- `runtime_time()`
- `runtime_events()`
- `runtime_clear_events()`
- `runtime_event_count()`

## Standard Library Modules
- `std:strings`
  - `upper(string)`
  - `lower(string)`
  - `trim(string)`
  - `split(string, delimiter)`
  - `join(list, delimiter)`
  - `contains(string, substring)`
  - `repeat(string, count)`
  - `replace(s, old, new)` — returns a new string with all occurrences of `old` replaced by `new`
- `std:collections`
  - `len(collection)`
  - `map(list, fn)`
  - `filter(list, fn)`
  - `reduce(list, fn, initial)`
  - `push(list, value)` mutates the list and returns it
  - `pop(list)` mutates the list and returns the removed value
- `std:json`
  - `parse(string)` decodes JSON values
  - `stringify(value)` encodes lists, maps, records, strings, booleans, numbers, and `nil`
  - **JSON objects decode to Nodus `map` values** (breaking change from v2.0.0, which returned `record`). Use `[]` for field access, not dot-notation.
  - `map["key"]` — field access
  - `has_key(map, "key")` — membership test (top-level builtin, no import required)
  - `keys(map)` — list of keys
  - `values(map)` — list of values

  ```nd
  import "std:json" as json
  let obj = json.parse("{\"name\": \"ada\"}")
  print(obj["name"])          // "ada"
  print(has_key(obj, "name")) // true
  print(keys(obj))            // ["name"]
  ```

  > **Migration note:** Code using `obj.name` on `json.parse` results will break. Replace dot access with `obj["name"]`.
- `std:math`
  - `abs(x)`
  - `min(a, b)`
  - `max(a, b)`
  - `floor(x)`
  - `ceil(x)`
  - `sqrt(x)`
  - `random()`
- `std:fs`
  - `read(path)`
  - `write(path, content)`
  - `exists(path)`
  - `listdir(path)`
  - `append(path, content)`
  - `ensure_dir(path)`
- `std:runtime`
  - `fn_name(fn)`
  - `fn_arity(fn)`
  - `fn_module(fn)` returns the defining module path
  - `fields(record)`
  - `has(record_or_module, name)`
  - `module_fields(module)`
  - `stack_depth()` returns the current function call depth
  - `stack_frame(index)` returns a record with `name`, `module`, `path`, `line`, and `column`
  - `typeof(value)` returns `int`, `float`, `string`, `bool`, `list`, `record`, `module`, `function`, `nil`, or `map`
  - `tasks()` returns a list of tracked coroutine tasks
  - `task(id)` returns task metadata or `nil`
  - `scheduler()` returns scheduler counters and queue sizes
  - `time_ms()` returns the runtime clock in milliseconds
  - `events()` returns collected runtime events
  - `clear_events()` clears the event buffer
- `std:tools`
  - `execute(name, args)` wraps `tool_call(...)`
  - `available()` returns registered tool names
  - `describe(name)` returns tool metadata or `nil`
- `std:memory`
  - `get(key)`
  - `put(key, value)`
  - `delete(key)`
  - `keys()`
  - `has(key)` — returns true if key exists in memory store (key-existence check, not value check)
- `std:agent`
  - `call(name, payload)` wraps `agent_call(...)`
  - `available()` returns registered agent names
  - `describe(name)` returns agent metadata or `nil`
- `std:async`
  - `sleep(ms)` suspends the current coroutine for the given milliseconds
  - `parallel(tasks)` spawns all tasks (functions or coroutines) and runs the event loop
  - `series(tasks)` runs tasks sequentially via the event loop
  - `queue()` returns a new channel
  - `worker_pool(worker, count)` returns a jobs channel serviced by `count` workers
  - `pipeline(stages)` returns `{input, output}` channels connected by stage functions

## Task Retry Policies

Task graphs support retries via the options map:

```
let A = task(fn() {
    throw "fail"
}, { "retries": 3, "retry_delay_ms": 5 })
```

- `retries` is the maximum retry attempts after the first failure.
- `retry_delay_ms` delays each retry using the scheduler timer.
- Failures propagate once retries are exhausted.

## Task Result Caching

Tasks can cache results by enabling `cache` in the options map:

```
let A = task(fn() { return 5 }, { "cache": true })
```

Optional custom cache key:

```
let A = task(fn() { return 5 }, { "cache": true, "cache_key": "custom" })
```

- Cached results are reused on subsequent `run_graph` calls within the same process.
- Cache keys default to a stable hash of the function identity and dependency results.
- Cache hits skip execution and emit `task_cache_hit`.

## Task Graph Planning

`plan_graph(tasks)` analyzes task dependencies without executing tasks.

It returns:

- `nodes`: task ids
- `edges`: dependency edges `[from, to]`
- `levels`: dependency levels
- `parallel_groups`: tasks runnable in parallel per stage

## Workflow DSL

Nodus workflows are syntax sugar over the existing task graph runtime.

```
workflow publish_article {
    step research {
        return 2
    }

    step outline after research {
        return research + 1
    }

    step draft after outline {
        return outline * 3
    }
}
```

- `workflow <name> { ... }` defines a reusable workflow value.
- `step <name> { ... }` defines a task node.
- `after` declares symbolic dependencies by step name.
- Dependency names become function parameters inside the step body.
- Step names must be unique within a workflow.

Run and plan workflows with:

- `run_workflow(workflow)`
- `plan_workflow(workflow)`
- `resume_workflow(graph_id, checkpoint=nil)`

Workflow execution returns the usual graph result plus a `steps` map:

```
{
  "graph_id": "...",
  "tasks": { "task_1": 2, "task_2": 3 },
  "steps": { "research": 2, "outline": 3 },
  "state": { "topic": "AI SEO" },
  "checkpoints": [{ "label": "after_research", "step": "research" }],
  "failed": []
}
```

Workflows can declare durable workflow state and checkpoints:

```
workflow publish_article {
    state topic = "AI SEO"
    state draft = nil

    step research {
        checkpoint "after_research"
        return topic
    }

    step write after research {
        draft = research + " draft"
        checkpoint "after_write"
        return draft
    }
}
```

- `state <name> = <expr>` declares a workflow-scoped, durable state variable.
- `checkpoint "label"` records a durable checkpoint inside a step.
- State variables are readable/writable inside steps and persist across resume.
- Checkpoints record label, step, timestamp, and a snapshot of workflow state.

Step options use the compact `with` form and lower directly into task options:

```
workflow demo {
    step research with { timeout_ms: 1000, retries: 2, worker: "gpu" } {
        return 2
    }
}
```

Supported step options:

- `timeout_ms`
- `retries`
- `retry_delay_ms`
- `cache`
- `cache_key`
- `worker`
- `worker_timeout_ms`

## Goal DSL

Goals are a semantic wrapper over the same durable workflow/task graph runtime.

```nd
goal publish_article {
    state topic = "AI SEO"

    step research {
        action tool "nodus_check" with {
            code: "print(1 + 1)",
            filename: "inline.nd"
        }
    }

    step summarize after research {
        action agent "summarize" with {
            input: research
        }
    }

    step store after summarize {
        action memory_put "article_summary" summarize
    }
}
```

- `goal <name> { ... }` defines a reusable goal value.
- `step <name> { ... }` and `step <name> after a, b { ... }` build the dependency graph.
- Goal step names must be unique within the goal.
- Goal state uses the same durable state/checkpoint behavior as workflows.
- `run_goal(goal)`, `plan_goal(goal)`, and `resume_goal(graph_id, checkpoint=nil)` are goal-oriented wrappers over workflow/task graph execution.

Goal execution returns the usual graph result plus goal metadata:

```
{
  "goal": "publish_article",
  "graph_id": "...",
  "steps": { "research": {...}, "summarize": {...}, "store": null },
  "state": { "topic": "AI SEO" },
  "checkpoints": [],
  "failed": []
}
```

### Action Primitives

Actions are only valid inside workflow/goal steps and lower into existing runtime builtins.

- `action tool "name" with { ... }` -> tool dispatch
- `action agent "name" with { ... }` -> agent dispatch
- `action memory_put "key" expr` -> local runtime memory write
- `action memory_get "key"` -> local runtime memory read
- `action emit "event" with { ... }` -> runtime event emission

Action rules:
- Actions return values when appropriate, so a step can `return action memory_get "notes"` or bind `let x = action memory_get "notes"`.
- If a step ends with an action expression and does not explicitly `return`, the action result becomes the step result.
- Tool and agent actions preserve structured result objects unless later transformed by normal code.
- Goal/workflow state and runtime memory remain distinct.

## Persistent Workflows

Task graphs persist state to `.nodus/graphs/<graph_id>.json` during execution.
Workflow graphs also persist workflow metadata, including workflow name, workflow state,
checkpoint entries, and enough workflow source metadata for `resume_workflow(...)` to
rebuild the workflow graph after process restart.

Use `resume_graph(graph_id)` to resume pending tasks after interruption.

Workflow checkpoints can be queried with `workflow_checkpoints(graph_id)`.
`resume_workflow(graph_id, checkpoint)` restores workflow state from the latest matching checkpoint label and rolls back the checkpointed step plus downstream steps to `pending` before resuming. Completed tasks upstream of the checkpoint are preserved.

## Memory API

Nodus exposes an in-process key/value memory store through both top-level builtins and the `std:memory` module.

### Top-level builtins

```nd
memory_put("key", value)   // store a JSON-safe value; returns the stored value
memory_get("key")          // retrieve value; returns nil if key not found
memory_delete("key")       // remove key; returns true if existed, false otherwise
memory_has("key")          // returns true if key exists regardless of stored value
memory_keys()              // returns sorted list of all keys
```

### `std:memory` module (recommended)

```nd
import "std:memory" as memory

memory.put("key", value)   // store value
memory.get("key")          // retrieve; nil if not found
memory.delete("key")       // remove; no-op if absent
memory.has("key")          // boolean existence check
memory.keys()              // sorted key list
```

### Rules

- Keys must be non-empty strings. Passing any other type raises a runtime `TypeError`.
- Values must be JSON-safe (strings, numbers, booleans, nil, lists, maps of the above).
- `memory.get` on a missing key returns `nil` — it is not an error.
- `memory.has` checks key existence; it returns `true` even when `nil` is stored under the key.
- `memory.delete` on a missing key is a no-op (returns `false`).
- Memory is process-local by default. In server sessions it is session-local and snapshot-aware.
- Workflow state and runtime memory are distinct: `memory_*` / `std:memory` are ephemeral per-process; workflow state is durable per-workflow-execution.

## Agent, Tool, And Memory Primitives

Nodus keeps integration behavior out of the language core syntax and exposes it through explicit built-ins plus standard-library modules.

Example:

```nd
import "std:agent" as agent
import "std:memory" as memory
import "std:tools" as tools

let checked = tools.execute("nodus_check", {
    "code": "print(1 + 1)",
    "filename": "inline.nd"
})
memory.put("notes", checked)
let result = agent.call("summarize", {
    "input": memory.get("notes")
})
```

Phase 1 semantics:
- Tools dispatch through the local runtime registry and currently expose `nodus_execute`, `nodus_check`, `nodus_ast`, and `nodus_dis`.
- Agents dispatch through a local handler registry. Unregistered agents return a structured `agent_call` failure.
- Memory stores JSON-safe values. Outside sessions it is process-local. In server sessions it is session-local and snapshot-aware.
- Advanced memory systems, including A.I.N.D.Y., may be connected by the host as external integrations. They are not core runtime memory primitives.

Workflow state and memory stay distinct:
- Workflow state is durable per-workflow execution state managed by the workflow runtime.
- `memory_*` and `std:memory` are local runtime lookup/storage primitives outside workflow state.

Runtime events are emitted for:
- `tool_call_start`, `tool_call_complete`, `tool_call_fail`
- `memory_put`, `memory_get`, `memory_delete`
- `agent_call_start`, `agent_call_complete`, `agent_call_fail`
- `goal_start`, `goal_complete`, `goal_fail`
- `goal_step_start`, `goal_step_complete`, `goal_step_fail`
- `goal_action_start`, `goal_action_complete`, `goal_action_fail`

Task states:

- `pending`
- `running`
- `completed`
- `failed`
- `retrying`

## Distributed Workers

Workers can register and execute task graph work via HTTP:

- `POST /worker/register` with `{ "capabilities": ["cpu", "gpu", "io"] }`
- `POST /worker/poll`
- `POST /worker/heartbeat` with `{ "worker_id": "worker_1" }`
- `POST /worker/result`

The runtime assigns runnable tasks to available workers and requeues on failure.
Tasks can target specific worker capabilities using the `worker` option on `task(...)`.
If no worker is specified, the task can be dispatched to any available worker.
If no worker with the required capability registers within the timeout, the graph fails with a diagnostic error.
Workers are considered dead if they stop heartbeating for longer than the heartbeat timeout, and their in-flight tasks are requeued.

## Files and CLI
- Primary source extension: `.nd`
- Legacy `.tl` is still supported for compatibility.
- CLI: `nodus run script.nd`, `nodus run`, `nodus repl`, `nodus check script.nd`
- Dependency graph inspection: `nodus deps`
- Cache maintenance: `nodus cache clear`
- Bytecode optimization runs automatically during compilation.
- `nodus run --no-opt script.nd` disables the optimizer for debugging or comparison.
- Service mode: `nodus serve [--port <n>] [--trace]` exposes HTTP endpoints for executing code.
  - `--worker-sweep-interval-ms <ms>` sets the background worker expiry sweep interval.
  - `POST /session` -> `{ "session": "id" }`
  - `POST /execute` with `{ "session": "id", "code": "..." }` for stateful execution
  - `POST /graph` with `{ "session": "id", "code": "..." }` for task graph runs
  - `POST /tool/call` with `{ "name": "nodus_check", "args": { ... } }`
  - `POST /agent/call` with `{ "name": "summarize", "payload": { ... } }`
  - `GET /memory` returns memory keys; `GET /memory?key=topic` returns one value
  - `POST /memory` with `{ "key": "topic", "value": "AI SEO" }`
  - `DELETE /memory/<key>`
- `POST /workflow/run` with `{ "code": "...", "filename": "inline.nd", "workflow": "optional_name" }`
- `POST /workflow/plan` with `{ "code": "...", "filename": "inline.nd", "workflow": "optional_name" }`
- `POST /workflow/resume` with `{ "graph_id": "g_...", "checkpoint": "optional_label" }`
- `GET /workflow/checkpoints/<graph_id>`
- `POST /goal/run` with `{ "code": "...", "filename": "inline.nd", "goal": "optional_name" }`
- `POST /goal/plan` with `{ "code": "...", "filename": "inline.nd", "goal": "optional_name" }`
- `POST /goal/resume` with `{ "graph_id": "g_...", "checkpoint": "optional_label" }`
  - `GET /sessions` for active session metadata
  - `POST /snapshot` -> `{ "snapshot": "id" }`
  - `POST /restore` -> `{ "session": "id" }`
  - `GET /snapshots` list stored snapshots
  - `DELETE /snapshot/<id>` delete a snapshot
- Workflow CLI: `nodus workflow-run script.nd`, `nodus workflow-plan script.nd`, `nodus workflow-resume <graph_id> [--checkpoint <label>]`, `nodus workflow-checkpoints <graph_id>`
- Goal CLI: `nodus goal-run script.nd [--goal <name>]`, `nodus goal-plan script.nd [--goal <name>]`, `nodus goal-resume <graph_id> [--checkpoint <label>]`
- Agent/tool/memory CLI:
- `nodus tool-call <tool> --json <payload>`
- `nodus agent-call <agent> --json <payload>`
- `nodus memory-get <key>`
- `nodus memory-put <key> --json <value>`
- `nodus memory-delete <key>`
- `nodus memory-keys`
- Project inspection: `nodus status` — prints the project root, entry file, and working directory that `nodus run` would use from the current directory; prints `No project found in current directory` when no `nodus.toml` is reachable; always exits 0.
- Debugger: `nodus debug script.nd`
  - Commands: `break <line>`, `step`, `next`, `continue`, `locals`, `stack`, `quit`
  - Breakpoints pause on source lines using compiler-provided location metadata
  - `step` pauses after the next instruction
  - `next` steps over function calls and pauses when control returns to the current frame
  - `locals` shows current frame locals, or top-level globals when paused in main
  - `stack` shows the current call stack with line information
- AST inspection: `nodus ast script.nd` (parse only, no execution)
  - `--compact` prints a denser tree for large files.
- Bytecode disassembly: `nodus dis script.nd` (compile only, no execution)
  - `--loc` includes source locations when available.
- Run mode flags: `--strict` (disables project auto-discovery; requires an explicit file path — exits non-zero with an error if no file argument is provided), `--trace-imports` (prints one `[import] Resolved "path" -> /abs/path` line to stderr per resolved import; failed imports print `[import] Failed "path" -- <reason>`)
- Debug flags: `--dump-bytecode`, `--trace`
- Trace controls: `--trace-no-loc`, `--trace-filter <text>`, `--trace-limit <n>`
- Scheduler tracing: `--trace-scheduler`
- Runtime event tracing: `--trace-events`, `--trace-json`, `--trace-file <path>`
- Formatting: `nodus fmt script.nd` (see `FORMAT.md` for rules)

## Exception Handling
Stability: Stable.

`try/catch/finally` provides structured error handling.

```nd
try {
    risky()
} catch err {
    print(err.message)
} finally {
    print("always runs")
}
```

### Exit paths

All five exit paths are handled correctly:

1. **Normal (no exception):** try body completes, finally (if present) runs, execution continues after.
2. **Caught exception:** exception raised in try, catch binds `err`, catch block runs, finally runs.
3. **Uncaught exception:** exception raised in try with no matching handler, finally runs, exception propagates.
4. **`return` inside try:** finally runs before the function returns; the return value is preserved.
5. **`return` inside catch:** finally runs before the function returns; the return value is preserved.

### The error object

Inside a `catch` block, the caught error record has these fields:

| Field | Type | Description |
|-------|------|-------------|
| `err.message` | string | Human-readable error description (always present). |
| `err.kind` | string | Error category. VM kinds: `"type"`, `"key"`, `"index"`, `"name"`, `"call"`, `"runtime"`, `"sandbox"`, `"thrown"`. Stdlib kinds (v3.0): `"io_error"`, `"parse_error"`, `"type_error"`, `"value_error"`, `"math_error"`, `"path_error"`, `"internal_error"`. |
| `err.payload` | any | Original thrown value for non-string throws; `nil` for runtime errors and string throws. **Always present** (never absent). |
| `err.path` | string | Source file path where the error occurred; empty string if unavailable. |
| `err.line` | int | Source line number; `0` if unavailable. |
| `err.column` | int | Source column number; `0` if unavailable. |
| `err.stack` | list | Stack trace as a list of strings (one entry per frame). |

All explicit `throw` statements set `err.kind = "thrown"`, regardless of value type.
The difference is in `err.payload`:
- String throw (`throw "msg"`): `err.message` contains the string; `err.payload` is `nil`.
- Non-string throw (`throw record { ... }`): `err.message` is a generic description; `err.payload` contains the original value.

**Stdlib-returned vs VM-thrown err records.** The table above describes err records
caught inside a `try/catch` block (VM-thrown errors). Stdlib functions like
`json.parse`, `math.sqrt`, and `fs.read` can also *return* err records as values
rather than throwing them — these can be inspected without `try/catch`. Returned err
records have the same `kind`, `message`, and `payload` fields and are always reliable.
The `path`, `line`, `column`, and `stack` fields are also present on returned err
records, but they may point to stdlib internals rather than the user call site. Use
`err.kind` and `err.message` as the primary error-handling signal; treat `path`/`line`
on returned err records as best-effort diagnostic information.

```nd
try {
    throw record { code: 404, reason: "not found" }
} catch err {
    print(err.kind)        // "thrown"
    print(err.payload.code)  // 404
}
```

### `finally` without `catch`

A `finally` clause is only valid after a `catch` clause. The `catch` block is always required.

## Errors
- Lex errors (unexpected characters, malformed string escapes): `LangSyntaxError` with line/col, raised directly from the lexer.
- Parse errors: `LangSyntaxError` with line/col.
- Runtime errors: `LangRuntimeError` with kind + line/col + stack trace.
- `try/catch/finally` can intercept runtime errors; the caught error record exposes `message`, `kind`, `payload`, `path`, `line`, `column`, and `stack` fields.

## Stack Traces
Runtime errors include a compact stack trace with function name, file path, line, and column:

```
Index error at examples/data.nd:42:9: List index out of range: 9
Stack trace:
  at process_data (examples/data.nd:42:9)
  called from main (scripts/run.nd:10:5)
```

## Bytecode Dump
Use `--dump-bytecode` to print the compiled bytecode before execution:

```
nodus run script.nd --dump-bytecode
```

## Trace Mode
Use `--trace` to print each executed instruction:

```
nodus run script.nd --trace
```
