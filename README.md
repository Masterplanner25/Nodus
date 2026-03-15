# Nodus

Nodus is a lightweight, practical scripting language implemented in Python. It targets small scripts and automation tasks with a clean module system, a compact standard library, and predictable tooling.

Architecture:
`source -> lexer -> parser -> AST -> compiler -> bytecode -> VM -> runtime services`

Quick links:
- `docs/onboarding/GETTING_STARTED.md`
- `docs/language/FORMAT.md`
- `docs/tooling/EDITOR_SUPPORT.md`
- `docs/tooling/LSP.md`
- `docs/tooling/DAP.md`
- `docs/governance/STABILITY.md`
- `docs/tooling/TESTING.md`
- `docs/runtime/TASK_GRAPHS.md`
- `docs/runtime/WORKFLOWS.md`
- `docs/runtime/RUNTIME_EVENTS.md`
- `docs/runtime/PROFILER.md`
- `docs/tooling/DEBUGGER.md`
- `docs/tooling/REPL.md`
- `docs/tooling/PROJECTS.md`
- `docs/tooling/PACKAGE_MANAGER.md`
- `docs/runtime/SERVER_MODE.md`
- `docs/governance/VERSIONING.md`
- `docs/governance/RELEASE_NOTES_0.2.0.md`
- `docs/governance/TECH_DEBT.md`
- `docs/governance/DEPRECATIONS.md`

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

- Install (editable):
  - `pip install -e .`
- REPL: `python nodus.py` or `nodus repl`
- Run script: `nodus run script.nd`
- Profile script: `nodus profile examples/demo.nd`
- Check script (no execution): `nodus check script.nd`
- Format script: `nodus fmt script.nd`
- Run examples: `nodus test-examples`
- Service mode: `nodus serve` (HTTP runtime server)
- Language server: `nodus lsp`
- Debug adapter: `nodus dap`
- Session snapshots: `nodus snapshot <session>`, `nodus snapshots`, `nodus restore <snapshot>`
- Version: `nodus --version`

Project setup and dependencies:
- Initialize project: `nodus init`
- Install dependencies: `nodus install`
- Update dependencies: `nodus update`
- Show module dependency graph: `nodus deps`
- List installed package dependencies: `nodus package-list`

Project manifests:
- `nodus.toml` defines project metadata and dependencies.
- `src/main.nd` is the default project entrypoint created by `nodus init`.
- `nodus.lock` pins resolved dependency sources and hashes.

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
- `nodus repl` (interactive REPL)
- `:help`, `:ast <expr>`, `:dis <expr>`, `:type <expr>` (inside the REPL)
- `nodus run script.nd --trace --trace-limit 50` (short trace)
- `nodus run script.nd --trace-events` (runtime event stream)
- `nodus run script.nd --trace-json --trace-file trace.json` (machine-readable events)
- `nodus run script.nd --trace-scheduler --scheduler-stats` (scheduler tracing)
- `nodus run script.nd --no-opt` (disable bytecode optimization)
- `nodus run script.nd --step-limit 100000 --time-limit 5 --output-limit 20000` (sandbox limits)
- `nodus run script.nd --allow-paths <paths>` (filesystem allowlist)
- `nodus profile examples/demo.nd` (runtime profiler report)
- `nodus debug script.nd` (interactive debugger)
- `nodus dap` (Debug Adapter Protocol over stdio)
- `nodus install` (install project dependencies)
- `nodus update` (refresh dependencies and lockfile)
- `nodus deps` (print the incremental compilation dependency graph)
- `nodus package-list` (list package manifest/lockfile dependencies)
- `nodus cache clear` (remove cached compiled modules from `.nodus/cache/`)
- `nodus test-examples` (quick smoke test)
- `nodus serve --port 7331` (HTTP runtime server)
- `nodus lsp` (Language Server Protocol over stdio)
- `nodus serve --allow-paths <paths>` (restrict filesystem builtins in server mode)
- `nodus serve --auth-token <token>` (require Authorization header)
- `nodus snapshot <session>` (save session snapshot)
- `nodus snapshots` (list snapshots)
- `nodus restore <snapshot>` (restore snapshot to new session)
- `nodus worker --host <host> --port <n>` (register a worker with a server)
- `nodus install` (install project dependencies to `deps/`)
- `nodus update` (refresh dependencies and lockfile)

Orchestration commands:
- `nodus graph <script.nd>` (plan a task graph from a script)
- `nodus workflow-run <script.nd> [--workflow <name>]`
- `nodus workflow-plan <script.nd> [--workflow <name>]`
- `nodus workflow-resume <graph_id> [--checkpoint <label>]`
- `nodus workflow-checkpoints <graph_id>`
- `nodus goal-run <script.nd> [--goal <name>]`
- `nodus goal-plan <script.nd> [--goal <name>]`
- `nodus goal-resume <graph_id> [--checkpoint <label>]`

Debug example:
```
$ nodus debug workflow.nd
(nodusdb) break workflow.nd:12
(nodusdb) run
(nodusdb) step
(nodusdb) print user_id
```

Runtime service commands:
- `nodus tool-call <tool> --json <payload>`
- `nodus agent-call <agent> --json <payload>`
- `nodus memory-get <key>`
- `nodus memory-put <key> --json <value>`
- `nodus memory-keys`

## Language Files

- Primary extension: `.nd`
- Legacy extension supported: `.tl`

## IDE Support

Nodus ships baseline editor support for syntax highlighting and snippets, plus a minimal Language Server Protocol implementation for diagnostics, completion, hover, and go-to-definition.

- Syntax highlighting and snippets: `docs/tooling/EDITOR_SUPPORT.md`
- Language server documentation: `docs/tooling/LSP.md`
- Debug adapter documentation: `docs/tooling/DAP.md`
- Start the language server with `nodus lsp`
- Start the debug adapter with `nodus dap`

## Debugging

Nodus exposes two debugger entrypoints:

- `nodus debug script.nd` for the built-in interactive debugger
- `nodus dap` for IDE clients that speak the Debug Adapter Protocol

The DAP adapter reuses the existing runtime debugger, supports source-line breakpoints, continue/pause/step controls, stack traces, and variable inspection for arguments and locals.

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
- bytecode version headers for forward compatibility
- embeddable Python runtime with host function registration
- sandbox limits for steps, time, and stdout output
- runtime module loader with per-module bytecode units
- on-disk bytecode cache for compiled modules in `.nodus/cache/`
- scheduler fairness with round-robin queueing and per-task instruction budgets
- persisted dependency graph for incremental compilation in `.nodus/deps.json`
- per-module global namespace isolation
- project manifests (`nodus.toml`) with dependency resolution and `nodus.lock`

## REPL

The REPL now supports multiline editing for brace-delimited blocks, persistent history via `~/.nodus_history`, and interactive inspection commands.

```text
> fn add(a, b) {
...   return a + b
... }
> :ast 1 + 2 * 3
Binary(+)
  Number(1)
  Binary(*)
    Number(2)
    Number(3)
> :dis 1 + 2
PUSH_CONST 1.0
PUSH_CONST 2.0
ADD
RETURN
> :type [1, 2, 3]
List<number>
```

## Imports

- `import "lib/math.nd"`
- `import { add, sub } from "lib/math.nd"`
- `import "lib/math.nd" as math`
- `import "std:strings"`
- `import { repeat } from "std:strings"`
- `export { add } from "./math.nd"`

Import resolution rules:
- Project dependencies resolve first (entries in `nodus.toml` / `nodus.lock` and the `deps/` directory).
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

## Bytecode Versioning

Compiled bytecode includes a version header:

```json
{
  "bytecode_version": 1,
  "module_name": "<module>",
  "instructions": [...],
  "constants": [],
  "exports": [],
  "metadata": {}
}
```

The VM validates the version when loading and raises `BytecodeVersionError` for unsupported versions.

## Embedding In Python

Nodus can be embedded in Python applications:

```python
from nodus.runtime.embedding import NodusRuntime

rt = NodusRuntime()

def send_email(addr, body):
    return True

rt.register_function("send_email", send_email, arity=2)
rt.run_file("workflow.nd")
```

Host functions are callable from Nodus scripts and runtime errors propagate back to the host.

## Sandbox Runtime Limits

Runtime execution can be constrained by:

- step limit (instruction count)
- time limit (seconds via CLI, milliseconds in the API)
- output limit (stdout character cap)

When a limit is exceeded, the runtime raises `RuntimeLimitExceeded` (surfaced as a sandbox error in CLI results).

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
