# Nodus Language Spec (Working)

## Values
Stability: Mostly stable (record vs map semantics may evolve).
- number (float-based)
- bool (`true`, `false`)
- string (double-quoted with escapes: `\\`, `\"`, `\n`, `\t`)
- nil (`nil`)
- list (`[...]`)
- map (`{key: value, ...}`)
- record (`record { key: value, ... }`)
- record methods: `record { greet: fn(self) { ... } }`, called as `obj.greet()`

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
- Arithmetic: `+ - * /`
- Comparison: `== != < > <= >=`
- Logical: `&& || !`
- Truthiness: `nil` is falsey; booleans use natural value; others use Python-like truthiness.

## Control Flow
Stability: Mostly stable (missing `break`/`continue`).
- `if (...) { ... } else { ... }`
- `while (...) { ... }`
- `for (init; cond; inc) { ... }` lowered to while behavior.
- `for name in iterable { ... }`
- `try { ... } catch err { ... }`
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
- Close: `close(ch)` stops future sends. `recv(ch)` on a closed empty channel returns `nil`.

## Static Types
Stability: Experimental (tooling-only, likely to evolve).
- Type annotations are optional and do not change runtime behavior.
- Supported type names:
  - `int`
  - `float`
  - `string`
  - `bool`
  - `list`
  - `record`
  - `function`
  - `any`
- `nodus check` runs static analysis and reports type mismatches for annotated code.
- Programs without annotations continue to run as before.

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
- Relative paths (`./` or `../`) resolve from the importing file.
- Non-relative paths resolve from the project root, then fall back to `deps/`.
- If no extension is provided, `.nd` is preferred, then `.tl` as legacy fallback.

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
  - `nodus deps` lists declared dependencies and resolved lock entries

### Re-exports
- `export { name } from "./module.nd"`
- Re-exported names must already be exported by the target module.
- Re-exports do not grant access to private names.

### Package/Index Resolution
When importing a path without an extension, Nodus checks in this order:
1. `path.nd`
2. `path.tl`
3. `path/index.nd`
4. `path/index.tl`

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
- `type(x)`
- `str(x)`
- `len(x)` for list/map/string
- `print(x)`
- `input(prompt)`
- `keys(map)`
- `values(map)`
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
- `memory_get(key)` reads a shared runtime memory entry or `nil`
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
  - JSON objects decode to Nodus `record` values, so fields can be accessed with `obj.name`
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
  - `has(key)` returns `true` when `get(key) != nil`
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
- `action memory_put "key" expr` -> shared runtime memory write
- `action memory_get "key"` -> shared runtime memory read
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

## Agent, Tool, And Memory Primitives

Nodus keeps AI-native orchestration out of the language core syntax and exposes it through explicit built-ins plus standard-library modules.

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

Workflow state and memory stay distinct:
- Workflow state is durable per-workflow execution state managed by the workflow runtime.
- `memory_*` and `std:memory` are shared runtime lookup/storage primitives outside workflow state.

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
- CLI: `nodus run script.nd`, `nodus repl`, `nodus check script.nd`
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
  - `nodus memory-keys`
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
- Debug flags: `--dump-bytecode`, `--trace`
- Trace controls: `--trace-no-loc`, `--trace-filter <text>`, `--trace-limit <n>`
- Scheduler tracing: `--trace-scheduler`
- Scheduler summary: `--scheduler-stats`
- Runtime event tracing: `--trace-events`, `--trace-json`, `--trace-file <path>`
- Formatting: `nodus fmt script.nd` (see `FORMAT.md` for rules)

## Errors
- Parse errors: `LangSyntaxError` with line/col.
- Runtime errors: `LangRuntimeError` with kind + line/col + stack trace.
- `try/catch` can intercept runtime errors and bind the message to a variable.

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
