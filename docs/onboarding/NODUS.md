# Nodus

## What Nodus Is
A lightweight scripting language built around a bytecode compiler and stack-based VM, optimized for automation and orchestration workflows.

## Purpose
Nodus is designed for readable logic, modular scripting, and runtime orchestration with task graphs, workflows, and event tracing.

## Architecture
`tokenizer -> parser/AST -> compiler -> bytecode -> stack VM`

## Design Philosophy
- clarity over cleverness
- simplicity over complexity
- explicit control flow
- practical scripting first

## Current Capabilities
- numbers, booleans, strings, nil
- lists, maps, and records
- functions, closures, and recursion
- control flow (if/while/for/foreach)
- imports and namespaces with explicit exports
- stdlib modules (`std:`)
- file I/O builtins
- coroutines, scheduler, and channels
- task graph runtime with persistence/resume
- workflows/goals lowered to task graphs
- runtime events and trace tooling
- deterministic formatter and static validation
- REPL, AST viewer, and bytecode disassembler

## File Extension
Primary extension: `.nd`

## CLI
- `nodus run script.nd`
- `nodus repl`
- `nodus fmt script.nd`
- `nodus check script.nd`
- `nodus ast script.nd`
- `nodus dis script.nd`
- `nodus serve`
- `nodus workflow-run script.nd`
- `nodus goal-run script.nd`

## Current Stage
Early practical scripting runtime focused on automation and orchestration.
