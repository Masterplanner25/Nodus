Nodus Architecture

Nodus is a bytecode-compiled scripting runtime implemented in Python designed for automation and orchestration workloads.

The system combines:

a traditional compiler + VM pipeline

a task/workflow orchestration runtime

developer tooling for inspection and debugging

Nodus sits between a simple interpreter and a full programming ecosystem. It provides a compact runtime capable of executing structured scripts while supporting higher-level automation primitives.

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
  → resolve_imports
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

File:

project.py
package_manager.py
symbol_table.py

The resolver:

loads imported modules

enforces explicit exports

constructs module alias mappings

rewrites identifiers to module-qualified names

Currently, imports are flattened into a single compilation unit.

This simplifies compilation but creates scaling limitations.

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

When a limit is exceeded, the runtime raises RuntimeLimitExceeded (surfaced as a sandbox error in tooling outputs).
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

Imports are currently compile-time operations and do not appear as runtime opcodes.

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

Imports currently operate as compile-time transformations.

Process:

source.nd
  → parse AST
  → resolve_imports
     → build ModuleInfo
     → flatten imported AST
  → rewrite identifiers
  → compile

Modules are represented as snapshot records rather than runtime objects.

This simplifies compilation but introduces limitations.

8. Architectural Risks

The current architecture has several constraints.

Module Flattening

Flattening modules into a single compile unit:

limits isolation

prevents incremental compilation

complicates large projects

Runtime Coupling

Orchestration components share runtime state with the VM.

Without a clear boundary, this may complicate future extensions.

Python Runtime Constraints

Because the VM is implemented in Python:

performance ceilings exist

CPU-heavy workloads may be constrained

Embedding Boundary

Current embedding points (runner, server) are practical but informal.

A stable API for embedding Nodus into other systems is not yet defined.

9. Recommended Architectural Evolution

The highest-impact improvement is a runtime module system.

Future architecture:

Module Source
   ↓
Compile per module
   ↓
Bytecode Unit
   ↓
Runtime Module Object
   ↓
VM Loader

Benefits:

module isolation

incremental compilation

better tooling

improved embedding support

Additional improvements:

Bytecode Versioning

Introduce a bytecode version identifier to ensure compatibility across releases.

Embedding APIs

Formal APIs for:

executing code

loading modules

registering builtins

handling runtime events

Runtime Service Interfaces

Define structured interfaces for:

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
