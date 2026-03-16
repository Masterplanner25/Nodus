# Nodus

## What Nodus Is
A lightweight scripting language built around a bytecode compiler and stack-based VM, optimized for automation and orchestration workflows.

## Purpose
Nodus is designed for readable logic, modular scripting, and runtime orchestration with task graphs, workflows, and event tracing.

## Architecture
`lexer -> parser/AST -> module loader -> compiler -> bytecode -> stack VM -> scheduler`

## Design Philosophy
- clarity over cleverness
- simplicity over complexity
- explicit control flow
- practical scripting first

## Current Capabilities
- numbers, booleans, strings, nil
- lists, maps, and records
- functions, closures, and recursion
- control flow (if/while/for/foreach/try/catch/finally/throw)
- imports and namespaces with explicit exports
- stdlib modules (`std:`)
- file I/O builtins
- coroutines, scheduler, and channels
- task graph runtime with persistence/resume
- workflows/goals lowered to task graphs
- runtime events and trace tooling
- deterministic formatter and static validation
- REPL with multiline editing, history, and inspection commands
- AST viewer and bytecode disassembler

## File Extension
Primary extension: `.nd`

## CLI
- `nodus run script.nd`
- `python -m nodus.tooling.repl`
- REPL commands: `:help`, `:ast <expr>`, `:dis <expr>`, `:type <expr>`
- `nodus fmt script.nd`
- `nodus check script.nd`
- `nodus ast script.nd`
- `nodus dis script.nd`
- `nodus serve`
- `nodus workflow-run script.nd`
- `nodus goal-run script.nd`
- `nodus install [--registry <url>] [--registry-token <token>]`
- `nodus login [--registry <url>]`
- `nodus logout [--registry <url>]`
- `nodus publish [--registry <url>] [--registry-token <token>]`

## Current Stage
v1.0.0 (2026-03-15) — stable release. Opcode set frozen at 47 stable opcodes
(`BYTECODE_VERSION = 4`). `try/catch/finally` supported. `NodusRuntime` embedding
API stable. Registry publish/auth ecosystem complete.
