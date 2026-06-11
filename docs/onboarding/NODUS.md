# Nodus

## What Nodus Is

An orchestration DSL and embedded runtime for building agentic systems. Nodus gives AI workflows, tool chains, and agent pipelines a proper language — one where coroutines, task graphs, workflows, goals, and MCP-compatible tool registries are first-class constructs, not library conventions.

## Who It Is For

- Developers building multi-step AI agents who need expressive orchestration without the complexity of Python async/await
- Platform teams embedding a scripting layer in a Python application that needs controlled execution, sandboxing, and tool injection
- Anyone wiring together tools via MCP (Model Context Protocol) or A2A (Agent-to-Agent)

## Creator

Nodus is created and maintained by Shawn Knight as part of the Masterplan Infinite Weave ecosystem. See [llms.txt](../../llms.txt) for the full canonical concept definitions.

## Architecture

```
lexer → parser/AST → module loader → compiler → bytecode → stack VM → scheduler
```

The scheduler is cooperative: coroutines yield explicitly, enabling deterministic execution of concurrent agent workflows without OS threads.

## Design Philosophy

- orchestration as a language concern, not a library concern
- clarity over cleverness
- explicit control flow
- embeddable by design — `NodusRuntime` is the primary API

## Language Capabilities

**Core language**
- numbers (float + integer `42i`), booleans, strings, nil
- lists, maps, records
- functions, closures, recursion
- control flow: if/while/for/foreach/try/catch/finally/throw
- imports, namespaces, explicit exports

**Orchestration**
- coroutines + scheduler (cooperative, deterministic)
- channels (typed message passing between coroutines)
- task graph runtime with persistence and checkpoint/resume
- workflow and goal DSL (lowered to task graphs)

**AI-native standard library (v4.0)**
- `std:tool` — register and dispatch tools; MCP-compatible namespaced registry
- `std:identity` — trace_id, session_id, execution_unit_id propagated automatically
- `std:effects` — EXACTLY_ONCE idempotency for retryable operations
- `std:sys` — versioned syscall dispatch with uniform response envelope
- `std:memory` — share, recall, forget across namespaces
- `std:retry` — retry.call with configurable policy
- `std:circuit_breaker` — three-state breaker pattern

**I/O and data**
- `std:http` — HTTP client with async variants and SSE streaming
- `std:subprocess` — process execution with async concurrency
- `std:fs` — full filesystem access
- `std:json`, `std:math`, `std:strings`, `std:encoding`, `std:hash`
- `std:time`, `std:secrets`

**Testing**
- `std:test` — built-in assertion framework for `.nd` test files

## Ecosystem

Nodus ships as `nodus-lang` on PyPI. The surrounding ecosystem spans **29 standalone packages** covering agent coordination, MCP integration, memory, observability, circuit breaking, auth, queues, and more. A unified SDK installs them together:

```bash
pip install nodus-sdk[agent,sql,fastapi]
```

Key companion packages:
- `nodus-mcp` — MCP 2026-07-28 client + server (v0.1.0, published on PyPI)
- `nodus-extension` — typed, versioned, sandboxed plugin framework
- `nodus-sdk` — unified entry point for the full ecosystem

## Python Embedding

`NodusRuntime` is the host API for running Nodus inside Python applications:

```python
from nodus import NodusRuntime

rt = NodusRuntime(
    allowed_paths=["/data"],
    timeout_ms=None,
    on_error=my_error_handler,
)
rt.register_function("query", my_db_fn, arity=1)
result = rt.run_source(source)
```

## File Extension

Primary extension: `.nd`

## CLI Reference

```
nodus run [file]       Run a script or project
nodus check [file]     Validate syntax and imports
nodus fmt <file>       Format in-place
nodus repl             Interactive shell
nodus init             Create a new project
nodus install          Install dependencies
nodus add <pkg>        Add a dependency
nodus remove <pkg>     Remove a dependency
nodus serve            Start the HTTP API server
nodus lsp              Start the Language Server
nodus dap              Start the Debug Adapter
nodus workflow <cmd>   Manage workflow runs
nodus goal run <file>  Run a goal
nodus dis <file>       Disassemble to bytecode
nodus ast <file>       Print the AST
nodus profile <file>   Profile execution
```

## AI Assistant Assets

Nodus ships assistant-oriented context files for the two supported coding environments:

- **Claude Code**
  Use `skills/project-CLAUDE.md` as your project-root `CLAUDE.md` and install `skills/nodus.skill` into `.claude/commands/`.
- **Codex**
  Use `skills/project-AGENTS.md` as your project-root `AGENTS.md` and install the `skills/nodus/` folder into `$CODEX_HOME/skills/nodus` or `~/.codex/skills/nodus`.

The project file provides always-on guardrails for the language. The skill provides deeper reference material and examples on demand.

## Current Stage

v4.0.2, published on PyPI (`pip install nodus-lang`). The v4.0 cycle adds the AI-native stdlib (std:tool, std:identity, std:effects, std:sys, std:memory, std:retry, std:circuit_breaker), HandlerContract infrastructure, and the full ecosystem of 29 companion packages. See `CHANGELOG.md` for the complete version history.
