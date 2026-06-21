# Nodus

[![CI](https://github.com/Masterplanner25/Nodus/actions/workflows/ci.yml/badge.svg)](https://github.com/Masterplanner25/Nodus/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/nodus-lang.svg)](https://pypi.org/project/nodus-lang/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

> **v4.0.7 stable on PyPI** — `pip install nodus-lang` · Full 33-package companion ecosystem live: `pip install nodus-sdk[agent,sql,fastapi]`

```bash
pip install nodus-lang
nodus init
nodus run
nodus repl
```

Nodus is an **orchestration DSL and embedded runtime** for building agentic systems, created by **Shawn Knight** as part of the **Masterplan Infinite Weave** ecosystem. It implements the **Infinity Algorithm**'s execution model as a first-class language construct. It gives AI workflows, tool chains, and agent pipelines a proper language — one where coroutines, task graphs, workflows, and goals are first-class constructs rather than library conventions layered over Python.

If you're building multi-step AI agents, embedding a scripting layer in a Python application, or wiring together tools via MCP or A2A, Nodus is the execution layer.

For a machine-readable project index see [llms.txt](llms.txt).

The Nodus ecosystem spans **33 standalone packages**, all available at
`github.com/Masterplanner25`. A unified SDK (`nodus-sdk`) provides a single installation
story: `pip install nodus-sdk[agent,sql,fastapi]`.

## Install

Requires **Python 3.10+**.

```bash
pip install nodus-lang
```

For the optional FastAPI/Uvicorn server stack:

```bash
pip install "nodus-lang[server]"
```

## Quick Start

Create a project:

```bash
mkdir my-app
cd my-app
nodus init
nodus run
```

`nodus init` creates `nodus.toml` and `src/main.nd`.

`nodus run` executes the current project's `src/main.nd` when run inside a project root.

Start the REPL:

```bash
nodus repl
```

Useful REPL commands:

- `:help` shows REPL commands.
- `:quit` exits the REPL.

## Run A File

Create `hello.nd`:

```nd
print("hello")
```

Run it explicitly:

```bash
nodus run hello.nd
```

When you provide a file path, Nodus runs only that file. When you run `nodus run` with no file inside a project, Nodus runs only `src/main.nd`.

## Common Commands

- `nodus --version`
- `nodus run hello.nd`
- `nodus run`
- `nodus repl`
- `nodus check hello.nd`
- `nodus check`
- `nodus fmt hello.nd`

## Standard Library

Import standard library modules with the `std:` prefix:

```nd
import "std:http" as http
let r = http.get("https://api.example.com/data")
print(r.body)
```

The full standard library ships with Nodus — no extra installs required for core modules:

**Networking and I/O**

| Module | What it does |
|---|---|
| `std:http` | HTTP client — GET, POST, PUT, DELETE, PATCH; async variants; SSE streaming |
| `std:subprocess` | Run processes — `sp.run(argv)`, `sp.spawn(argv)` for async + channel output |
| `std:fs` | Filesystem — read, write, append, exists, listdir, mkdir |

**Data and encoding**

| Module | What it does |
|---|---|
| `std:json` | `json.parse(str)` / `json.stringify(val)` |
| `std:math` | Arithmetic, trig, rounding, min/max |
| `std:string` | Split, join, trim, replace, starts_with, ends_with, case conversion |
| `std:encoding` | Base64 encode/decode, URL encode/decode |
| `std:hash` | SHA-256 / SHA-512 for data and files — returns record with `.to_hex()` |

**Time and system**

| Module | What it does |
|---|---|
| `std:time` | `now_ms()`, `sleep(ms)`, UTC offset, format/parse timestamps |
| `std:secrets` | Cryptographic random tokens and bytes |

**AI-native orchestration (v4.0)**

| Module | What it does |
|---|---|
| `std:tool` | Register and dispatch tools — MCP-compatible namespaced registry |
| `std:identity` | `trace_id()`, `session_id()`, `execution_unit_id()` — propagated automatically |
| `std:effects` | EXACTLY_ONCE idempotency — `resolve`, `pending`, `complete`, `action_id` |
| `std:sys` | Versioned syscall dispatch — uniform `{status, data, error, trace_id}` response shape |
| `std:memory` | `share(ns, key, val)`, `recall_from(ns, key)`, `recall_all(ns)`, `forget(ns, key)` |
| `std:retry` | `retry.call(func, policy)` — exponential backoff, jitter, max attempts |
| `std:circuit_breaker` | `cb.create(name, cfg)` / `cb.call(name, func)` — three-state breaker |

**Testing**

| Module | What it does |
|---|---|
| `std:test` | `test.assert_eq`, `test.assert_err`, `test.flush_async` — built-in test framework |

## Documentation

- [Language Specification](docs/language/LANGUAGE_SPEC.md) — full syntax, types, control flow, imports, coroutines
- [Ecosystem Specs](docs/ecosystem/README.md) - implementation specs for proposed Nodus libraries and frameworks
- [Architecture](docs/runtime/ARCHITECTURE.md) — runtime pipeline and module system
- [Changelog](CHANGELOG.md) — version history
- [Contributing](CONTRIBUTING.md) — development setup, code style, and contribution process
- [llms.txt](llms.txt) — machine-readable project index for AI tools
- [llms-full.txt](llms-full.txt) — full content summaries for AI indexers

## Using with Claude Code

If you write Nodus with [Claude Code](https://claude.ai/code), a language skill is available
that teaches Claude the idioms, gotchas, and workflow patterns specific to Nodus v4:

1. Download [`skills/nodus.skill`](skills/nodus.skill) and [`skills/project-CLAUDE.md`](skills/project-CLAUDE.md) from this repo.
2. Copy `project-CLAUDE.md` to your project root as `CLAUDE.md` (fill in your project name).
3. Drop `nodus.skill` in your project's `.claude/commands/` folder.
4. Claude will apply Nodus-specific rules automatically in every session.

The skill covers: record vs map distinction, the closure outer-let pattern, `spawn()` coroutine
wrapping, workflow result bracket notation, NodusRuntime embedding defaults (timeout_ms=None,
allowed_paths=CWD since v4.0.1), all 19 stdlib modules, and 15 verified complete example programs.

## Using with Codex

If you write Nodus with Codex, a Codex-native skill and project template are available:

1. Copy [`skills/project-AGENTS.md`](skills/project-AGENTS.md) to your project root as `AGENTS.md` and fill in your project name if needed.
2. Copy the [`skills/nodus/`](skills/nodus/) folder to `$CODEX_HOME/skills/nodus` or `~/.codex/skills/nodus`.
3. Start a Codex session in your Nodus project. Codex can auto-trigger the skill, or you can invoke `$nodus` explicitly.

The Codex skill covers the same core language hazards: record vs map distinction, closure outer-`let`
mutation, `spawn()` coroutine wrapping, workflow result bracket notation, import rules, and
NodusRuntime embedding defaults (timeout_ms=None, allowed_paths=CWD since v4.0.1), while keeping
deeper material in reference files for on-demand loading.

---

## Creator & Ecosystem

Nodus is created and maintained by **Shawn Knight** as part of the
[Masterplan Infinite Weave](https://www.the-master-plan.com/) — an AI-native execution
framework built on the Infinity Algorithm. Nodus is the runtime layer that makes the
Infinity Algorithm's orchestration constructs executable as a first-class language.

**From the creator's writing:**
- [Why I'm Building A.I.N.D.Y. (Or Any Tool, Really)](https://medium.com/masterplan-infinite-weave/2025-chatgpt-ai-the-duality-of-progress-why-im-building-a-i-n-d-y-or-any-tool-really-a138f7860fba) — the strategic context behind Nodus
- [Duality of Progress: Master Index](https://medium.com/masterplan-infinite-weave/2025-chatgpt-ai-the-duality-of-progress-master-index-strategic-manifesto-4c96cf98348a) — the Infinity Algorithm framework Nodus executes
- [AI Search Optimization](https://medium.com/masterplan-infinite-weave/2025-chatgpt-case-study-ai-search-optimization-0f8cd5e78d4f) — the discoverability philosophy this project embodies
