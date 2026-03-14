# Nodus

Nodus is a lightweight, practical scripting language implemented in Python. It targets small scripts and automation tasks with a clean module system, a compact standard library, and predictable tooling.

Architecture:
`tokenizer -> parser/AST -> compiler -> bytecode -> stack VM`

Quick links:
- `GETTING_STARTED.md`
- `FORMAT.md`
- `EDITOR_SUPPORT.md`
- `STABILITY.md`
- `TESTING.md`
- `TASK_GRAPHS.md`
- `WORKFLOWS.md`
- `RUNTIME_EVENTS.md`
- `DEBUGGER.md`
- `PACKAGE_MANAGER.md`
- `SERVER_MODE.md`
- `VERSIONING.md`
- `RELEASE_NOTES_0.2.0.md`

## Example

```nd
import { repeat } from "std:strings"
import "std:collections" as c

fn greet(name) {
    return "hello " + name
}

let nums = [1, 2, 3]
print(greet("Nodus"))
print(repeat("ha", 2))
print(c.list_sum(nums))
```

Run it:

```bash
nodus run examples/hello.nd
```

## Getting Started

- REPL: `python nodus.py` or `nodus repl`
- Run script: `nodus run script.nd`
- Check script (no execution): `nodus check script.nd`
- Format script: `nodus fmt script.nd`
- Run examples: `nodus test-examples`
- Service mode: `nodus serve` (HTTP runtime server)
- Session snapshots: `nodus snapshot <session>`, `nodus snapshots`, `nodus restore <snapshot>`
- Version: `nodus --version`

Project setup and dependencies:
- Initialize project: `nodus init`
- Install dependencies: `nodus install`
- List deps: `nodus deps`

Backward compatible invocations are still supported:
- `python language.py script.nd`
- `python tiny_vm_lang_functions.py script.nd`

## Common Commands

- `nodus fmt script.nd` (format to canonical style)
- `nodus fmt script.nd --check` (CI-friendly formatting check)
- `nodus fmt script.nd --keep-trailing` (keep trailing comments inline when possible)
- `nodus check script.nd` (fast validation without running)
- `nodus ast script.nd` (print parsed AST)
- `nodus ast script.nd --compact` (compact AST view)
- `nodus dis script.nd` (print compiled bytecode without running)
- `nodus dis script.nd --loc` (include source locations in bytecode)
- `nodus run script.nd` (execute)
- `nodus run script.nd --trace --trace-limit 50` (short trace)
- `nodus run script.nd --trace-events` (runtime event stream)
- `nodus run script.nd --trace-json --trace-file trace.json` (machine-readable events)
- `nodus run script.nd --trace-scheduler --scheduler-stats` (scheduler tracing)
- `nodus run script.nd --no-opt` (disable bytecode optimization)
- `nodus debug script.nd` (interactive debugger)
- `nodus test-examples` (quick smoke test)
- `nodus serve --port 7331` (HTTP runtime server)
- `nodus snapshot <session>` (save session snapshot)
- `nodus snapshots` (list snapshots)
- `nodus restore <snapshot>` (restore snapshot to new session)
- `nodus worker --host <host> --port <n>` (register a worker with a server)

Orchestration commands:
- `nodus graph <script.nd>` (plan a task graph from a script)
- `nodus workflow-run <script.nd> [--workflow <name>]`
- `nodus workflow-plan <script.nd> [--workflow <name>]`
- `nodus workflow-resume <graph_id> [--checkpoint <label>]`
- `nodus workflow-checkpoints <graph_id>`
- `nodus goal-run <script.nd> [--goal <name>]`
- `nodus goal-plan <script.nd> [--goal <name>]`
- `nodus goal-resume <graph_id> [--checkpoint <label>]`

Runtime service commands:
- `nodus tool-call <tool> --json <payload>`
- `nodus agent-call <agent> --json <payload>`
- `nodus memory-get <key>`
- `nodus memory-put <key> --json <value>`
- `nodus memory-keys`

## Language Files

- Primary extension: `.nd`
- Legacy extension supported: `.tl`

## Core Features

- numbers, booleans, strings, nil
- lists, maps, and records
- functions and recursion
- if / else, while, for
- imports and namespaced imports
- explicit exports and selective imports
- stdlib scripts in `std/`
- builtins including file I/O
- coroutines and channels
- workflow/goal syntax and task graphs
- REPL
- line/column errors + stack traces
- bytecode dump and trace mode for debugging

## Imports

- `import "lib/math.nd"`
- `import { add, sub } from "lib/math.nd"`
- `import "lib/math.nd" as math`
- `import "std:strings"`
- `import { repeat } from "std:strings"`
- `export { add } from "./math.nd"`

Import resolution rules:
- `std:` prefix resolves to the built-in `std/` directory (e.g. `std:strings`).
- Relative paths start with `./` or `../` and resolve from the importing file.
- Non-relative paths resolve from the project root (the entry script directory by default).
- Project root override precedence: `--project-root <path>` > `NODUS_PROJECT_ROOT` > entry script directory.
- Extension handling: if no extension is provided, `.nd` is preferred, then `.tl` as legacy fallback, then `index.nd` / `index.tl`.

Resolution order examples:
- `import "std:strings"` -> `std/strings.nd` (fallback `std/strings.tl`)
- `import "./utils"` from `src/main.nd` -> `src/utils.nd` (fallback `src/utils.tl`)
- `import "lib/math"` from `src/main.nd` -> `<project_root>/lib/math.nd` (fallback `.tl`)
- `import "./utils"` from `src/main.nd` -> `src/utils.nd`, then `src/utils.tl`, then `src/utils/index.nd`, then `src/utils/index.tl`

## Exports

- `export let pi = 3.14159`
- `export fn add(a, b) { return a + b }`
- `export { add, sub }`

Notes:
- If a module uses any `export` declaration, only those names are visible to importers.
- Legacy modules with no `export` declarations export all top-level `let`/`fn`/assignment names.

Example (private names are not visible):

```nd
// math.nd
let secret = 10
export fn add(a, b) { return a + b }

// main.nd
import { add } from "math.nd"
print(add(1, 2))
print(secret) // error: not exported
```

Re-exports:

```nd
// api.nd
export { add } from "./math.nd"
```

## Built-ins

Core: `clock`, `type`, `str`, `len`, `print`, `input`, `keys`, `values`

File utilities: `read_file`, `write_file`, `append_file`, `exists`, `mkdir`

AI/runtime adapters: `tool_call`, `tool_available`, `tool_describe`, `memory_get`, `memory_put`, `memory_delete`, `memory_keys`, `agent_call`, `agent_available`, `agent_describe`, `emit`, `run_goal`, `plan_goal`, `resume_goal`

## Standard Library

Modules (import with `std:` prefix):
- `std:strings` - `upper`, `lower`, `trim`, `split`, `contains`, `repeat`, `is_blank`, `join`
- `std:collections` - collection helpers and list mutation helpers
- `std:json` - `parse`, `stringify`
- `std:math` - numeric helpers
- `std:fs` - filesystem helpers
- `std:path` - path helpers
- `std:runtime` - reflection, scheduler stats, runtime events
- `std:tools` - `execute`, `available`, `describe`
- `std:memory` - `get`, `put`, `delete`, `keys`, `has`
- `std:agent` - `call`, `available`, `describe`
- `std:async` - coroutine and channel helpers
- `std:utils` - small utility helpers

Notes:
- Tools currently dispatch to local adapters for `nodus_execute`, `nodus_check`, `nodus_ast`, and `nodus_dis`.
- Agents are local handler adapters in phase 1. Unregistered agents return a structured error instead of invoking an external provider.
- Memory stores JSON-safe values. Without a session it is process-local; in server sessions it is session-local.

## AI-Native Workflow Pattern

Nodus keeps the language core small and adds agent, tool, and memory behavior through explicit built-ins and stdlib modules:

```nd
import "std:agent" as agent
import "std:memory" as memory
import "std:tools" as tools

workflow ai_pipeline {
    state topic = "AI SEO"

    step research {
        let notes = tools.execute("nodus_check", {
            "code": "print(1 + 1)",
            "filename": "inline.nd"
        })
        memory.put("notes", notes)
        return notes
    }

    step summarize after research {
        return agent.call("summarize", {
            "input": memory.get("notes")
        })
    }
}
```

Keep these semantics distinct:
- Workflow `state` is durable per-workflow execution state.
- `memory.*` is shared runtime memory outside workflow state.
