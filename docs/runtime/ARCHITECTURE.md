Nodus Architecture

Nodus is a bytecode-compiled scripting runtime implemented in Python for automation and orchestration workloads.

The architecture is split into two layers:

runtime

- execution engine
- module namespaces
- per-module bytecode loading
- VM execution

tooling

- project manifest parsing
- dependency resolution
- installation into `.nodus/modules/`
- lockfile generation

This split keeps the runtime small, embeddable, and deterministic. Runtime code never performs dependency resolution, manifest parsing, registry access, or network activity.

1. System Overview

Nodus follows a structured compilation and execution pipeline:

Source
  ↓
Lexer (tokenize)
  ↓
Parser
  ↓
AST
  ↓
Import Resolution
  ↓
Bytecode Compiler
  ↓
Optimizer
  ↓
Virtual Machine

The runtime executes bytecode instructions on a stack-based virtual machine.

In addition to core execution, the runtime includes orchestration components such as:

module loader and module objects

coroutines

channels

task graphs

workflows/goals

runtime event tracing

These components enable Nodus scripts to coordinate asynchronous or multi-step automation tasks.

2. Execution Pipeline

The current pipeline is implemented as:

tokenize
  → Parser.parse
  → ModuleLoader.resolve_import
  → Compiler.compile_program
  → optimize
  → VM.run
Stage Breakdown
Tokenization

File:

lexer.py

Responsibilities:

Convert source text into tokens

Track token location for diagnostics

Identify keywords, literals, operators, identifiers

Parsing

File:

parser.py

The parser is a recursive-descent implementation.

Responsibilities:

Build AST dataclasses

Enforce grammar rules

Produce a structured representation of the program

AST definitions live in:

ast_nodes.py
Import Resolution

Files:

runtime/module_loader.py
runtime/module.py

The runtime module loader:

- resolves local project modules from the project root
- resolves installed packages from `.nodus/modules/`
- resolves standard library modules
- compiles modules into bytecode units
- executes modules once and caches module objects

Import order is:

1. local project modules
2. `.nodus/modules/`
3. standard library

Compilation

File:

compiler.py

Responsibilities:

convert AST nodes into bytecode instructions

construct constant tables

generate function objects and closures

maintain source location mappings for diagnostics

Optimization

File:

optimizer.py

Current optimizations include:

constant folding

dead code elimination

jump simplification

These optimizations are intentionally lightweight.

Virtual Machine Execution

File:

vm.py

The Nodus VM is a stack-based interpreter.

Runtime components include:

value stack

call frames

global scope

closures and upvalues

builtin function registry

The VM executes bytecode instructions emitted by the compiler.

Debugger Architecture

The debugger is an optional runtime component that hooks into the VM execution loop.

Core mechanics:

- The VM invokes debugger hooks before and after each instruction when debugging is enabled.
- Breakpoints are stored by module name and line number, using code location metadata from the compiler.
- Step modes include STEP_IN, STEP_OVER, and CONTINUE.
- When a pause is triggered, the debugger exposes current module, line, function, and locals, along with stack helpers.

Runtime Subsystems

Core runtime subsystems are:

VM (vm.py)
module loader (runtime/module_loader.py)
module objects (runtime/module.py)
scheduler (runtime/scheduler.py)
debugger (runtime/debugger.py)
runtime services (tools/agents/memory/event bus)

3. Bytecode Model

The instruction set is organized into several opcode families.

Stack Operations
PUSH_CONST
POP
Variable Access
LOAD
STORE
STORE_ARG
LOAD_UPVALUE
STORE_UPVALUE
Arithmetic / Logic
ADD SUB MUL DIV
EQ NE LT GT LE GE
NOT NEG
TO_BOOL
Control Flow
JUMP
JUMP_IF_FALSE
JUMP_IF_TRUE
HALT
Iteration
GET_ITER
ITER_NEXT
Exceptions
SETUP_TRY
POP_TRY
THROW

4. Bytecode Versioning

Compiled bytecode is packaged with a version header:

{
  "bytecode_version": 1,
  "instructions": [...],
  "constants": [],
  "metadata": {}
}

The VM validates the bytecode version on load and raises BytecodeVersionError if the version is unsupported. This keeps the runtime forward-compatible as opcodes evolve.

5. Embedding API

The runtime can be embedded in external Python applications via nodus.runtime.embedding.NodusRuntime. Embedding supports:

initializing an isolated runtime
registering host functions callable from Nodus scripts
running source strings or script files
propagating runtime errors back to the host

6. Sandbox Limits

The runtime enforces optional execution limits:

step limit (instruction count)
time limit (wall-clock deadline)
output limit (stdout character cap)
call stack depth (maximum number of frames)

When a limit is exceeded, the runtime raises RuntimeLimitExceeded (surfaced as a sandbox error in tooling outputs).

7. Runtime Module System

Nodus now executes modules as isolated runtime units. Each module has its own global namespace and is executed once per process. Imports resolve through the module loader, which caches module objects and reuses them for repeated imports.

Module Qualification

To avoid name collisions across modules, the loader assigns each module a unique prefix (`__modN__`). The compiler qualifies imported symbols with this prefix while preserving display names for diagnostics. The VM strips module prefixes when presenting user-facing names.

Modules are represented at runtime by a NodusModule object that stores:

module bytecode
module globals
exported symbols

8. Module Bytecode Units

Each compiled module produces a standalone bytecode unit:

{
  "bytecode_version": 1,
  "module_name": "<module>",
  "constants": [...],
  "instructions": [...],
  "exports": [...],
  "metadata": {...}
}

These units can be cached independently and linked at runtime.

9. Module Loader

The module loader is responsible for:

- resolving module paths
- compiling modules to bytecode units
- executing modules once
- caching module objects
- linking import bindings into module globals

The loader only works with filesystem paths. It never reads `nodus.toml`, never reads `nodus.lock`, and never performs package resolution.

10. Project Tooling

Project and package management live under `src/nodus/tooling/`:

- `project.py` locates the project root, parses `nodus.toml`, and reads or writes `nodus.lock`
- `semver.py` evaluates version ranges
- `resolver.py` constructs dependency graphs from manifests and registry metadata
- `installer.py` installs resolved packages into `.nodus/modules/`
- `registry.py` exposes registry metadata to the resolver

`nodus.lock` uses deterministic `[[package]]` entries:

```toml
[[package]]
name = "json"
version = "1.2.0"
source = "registry"
hash = "sha256:abc123..."
```

Tooling runs during `nodus install` and `nodus update`. Script execution does not invoke the resolver or installer.
Functions and Closures
CALL
CALL_VALUE
CALL_METHOD
MAKE_CLOSURE
RETURN
YIELD
Collections / Records
BUILD_LIST
BUILD_MAP
BUILD_RECORD
BUILD_MODULE
INDEX
INDEX_SET
LOAD_FIELD
STORE_FIELD

Imports are resolved by the runtime module loader rather than being flattened at compile time.

4. Runtime Orchestration Layer

Beyond traditional scripting, Nodus includes orchestration capabilities.

Key modules:

coroutine.py
scheduler.py
channel.py
task_graph.py
workflow_lowering.py
workflow_state.py
runtime_events.py

These components support:

asynchronous execution

message passing

workflow definitions

goal-driven task execution

event tracing

Workflow syntax is lowered into task graph execution plans during compilation.

5. Tooling and Developer Interfaces

Nodus includes extensive developer tooling.

Key components:

cli.py
repl.py
formatter.py
debugger.py
runner.py
server.py

Capabilities include:

interactive REPL

- multiline brace-aware input
- persistent command history via `~/.nodus_history` when `readline` is available
- shell commands `:ast`, `:dis`, `:type`, `:help`, and `:quit`

deterministic formatting

AST inspection

bytecode disassembly

runtime tracing

server-mode execution

These tools support both script development and runtime debugging.

6. Standard Library

The Nodus standard library is organized under the std: namespace.

Examples include:

std:strings
std:collections
std:fs
std:path
std:json
std:math
std:runtime
std:async
std:tools
std:memory
std:agent

The stdlib provides common utilities while avoiding large external dependencies.

7. Current Module Model

Imports are runtime operations executed through the module loader. Each module is compiled into its own bytecode unit, executed once, and cached for subsequent imports. Module exports are surfaced as module records, while module functions are invoked through module-bound call wrappers.

8. Architectural Risks

The current architecture has several constraints.

Runtime Coupling

Orchestration components share runtime state with the VM.

Without a clear boundary, this may complicate future extensions.

Python Runtime Constraints

Because the VM is implemented in Python:

performance ceilings exist

CPU-heavy workloads may be constrained

Embedding Boundary

The embedding API is available, but host integrations remain sensitive to VM performance characteristics.

9. Recommended Architectural Evolution

The next high-impact improvements are incremental compilation and bytecode caching.

Planned architecture:

Module Source
   ↓
Compile per module
   ↓
Bytecode Unit (cached by hash)
   ↓
Runtime Module Object
   ↓
VM Loader

Benefits:

faster rebuilds

repeatable builds with caching

better tooling integration

Additional improvements completed:

Bytecode Versioning

Bytecode headers are versioned and validated at load time.

Embedding APIs

The NodusRuntime embedding API supports:

executing code

loading modules

registering host functions

propagating runtime errors

Runtime Service Interfaces

Service interfaces remain an evolution area for:

agents

tools

memory

orchestration services

10. Lifecycle Stage

Nodus currently sits in the early practical runtime stage.

Evidence:

functioning compiler and VM

module system

CLI and REPL

standard library

workflow orchestration runtime

debugging and formatting tools

However, ecosystem-level infrastructure such as:

module isolation

stable embedding APIs

package distribution

is still evolving.

11. Design Philosophy

Nodus prioritizes:

clarity of implementation

inspectable runtime behavior

deterministic tooling

disciplined language evolution

The goal is to build a scripting runtime that remains understandable while supporting complex automation workflows.

Final Note

The most important architectural principle of Nodus is maintainable clarity.

If a subsystem becomes difficult to explain, the design should be reconsidered.
