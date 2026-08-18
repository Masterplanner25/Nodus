# Nodus

[![CI](https://github.com/Masterplanner25/Nodus/actions/workflows/ci.yml/badge.svg)](https://github.com/Masterplanner25/Nodus/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/nodus-lang.svg)](https://pypi.org/project/nodus-lang/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

> **Stable on PyPI** — `pip install nodus-lang` · Full 32-package companion ecosystem live: `pip install nodus-sdk[agent,sql,fastapi]`
>
> <sub>The badge above carries the current version. This line deliberately does not: it named a
> stale release through three consecutive cycles, most recently advertising 4.2.0 for the whole
> of the 5.0.0 cycle. A doc that cannot go stale beats a gate that catches it going stale.</sub>

> [!IMPORTANT]
> ### Breaking in v5.0.0: `NodusRuntime` denies capabilities by default
>
> **Embedding only.** A `NodusRuntime()` can no longer run subprocesses, open
> sockets, or read the process environment unless you say so:
>
> ```python
> # before — worked
> NodusRuntime().run_source(script)
>
> # now — grant what the script actually needs
> NodusRuntime(allow_subprocess=True, allow_network=True).run_source(script)
> ```
>
> The error names the flag:
> `Blocked: subprocess execution is not granted; pass allow_subprocess=True to NodusRuntime to allow it`
>
> **`nodus run` is unaffected.** A script you wrote and chose to run is not the
> threat model; hosting code you did not author is. The CLI never constructs a
> `NodusRuntime`.
>
> Also: a Nodus program can no longer write into `.nodus/` — the workflow store
> and graph state — because it could previously forge run records.
>
> Why: all three external architecture audits found the same thing — the
> capability chokepoint was built and unused, with *"the door propped open by
> registering subprocess and http by default."* See
> [the migration note](docs/migration/v5.0-deny-by-default.md) and
> [#405](https://github.com/Masterplanner25/Nodus/issues/405).

**Recent:** 5.0.4 repairs one thing 5.0.3 broke — constructing a
`nodus_sdk.NodusSDKRuntime` raised, because 5.0.3 assigned a `memory_store`
attribute that subclass already defines as a read-only property. **If you use
`nodus-sdk`, skip 5.0.3.**

5.0.3 is seven fixes with a common shape — a guarantee that held on one
path and not its sibling. A script ending in `main()` ran it **twice** on every run
after the first, because the guard against that read the AST and a cached module has
none. A directly constructed `VM()` had **no call-depth cap**, so runaway recursion
grew until the OS killed the process instead of raising. A host **agent handler had
no timeout at all** — every other bound in the runtime is a property of the
instruction stream, and a host handler is not in it. And two runtimes in one process
**shared memory**, so one request's script could read another's.

Also: `nodus check` now reports a workflow dependency cycle, resuming a run that does
not exist says so instead of blaming a claim, and workflow runs have an owner rather
than a process-global one.

**Multi-tenant hosts should upgrade** — the shared-memory fix is the one with a
security edge. One behaviour change to know about: each `NodusRuntime` now gets its
own memory store; pass `share_process_state=True` if you were relying on the old
sharing. No new syntax, no bytecode change.

5.0.1 is additive — it publishes the capability surfaces embedders were previously
reaching by scraping our source (`GATED_BUILTINS`, `active_vm()`, and a stated
denial contract), and it is the release that makes the companion ecosystem
installable alongside 5.0.0.

5.0.0 is the first major. It carries exactly one breaking change —
the deny-by-default above — and the bytecode format is untouched
(`BYTECODE_VERSION` is still 4, the 49-opcode set unchanged), so the major bump
does not imply recompilation. Alongside it: `goal … over …` gives a goal a real
stopping condition, so it is a workflow *plus a predicate and a budget* rather
than a workflow with different event names; `retries: N` now means the same thing
for goals and workflows; and `nodus fmt` refuses to write a file it cannot fully
represent instead of corrupting it. See the [changelog](CHANGELOG.md).

```bash
pip install nodus-lang
nodus init
nodus run
nodus repl
```

Nodus is an **orchestration DSL and embedded runtime** for *hosting* agentic systems, created by **Shawn Knight** as part of the **Masterplan Infinite Weave** ecosystem. Its execution model embodies the **Infinity Algorithm**'s feedback-loop structure at the runtime layer — a structural correspondence documented in [Infinity Pattern Mapping](docs/architecture/INFINITY_PATTERN_MAPPING.md), not a named construct in the grammar.

**There is no model in the core, and that is the design.** Nodus contains no LLM client, no agent loop and no tool-selection logic; `action agent "name" with {...}` hands a JSON-safe payload to a handler your host registers, and takes a result back. Because the runtime cannot perform inference, every semantic decision *must* cross that boundary — so deterministic structure never guesses, and the model never controls sequencing.

What the language contributes: `workflow`, `goal`, `step` and `after` are real keywords with real AST nodes, and dependency names are resolved and checked at parse time — `after typo` is a syntax error, which LangGraph, Prefect and Airflow all discover at run time. Coroutines are a hybrid: one `YIELD` opcode and a VM-level `Coroutine` that saves `ip`/`stack`/`frames`, with `spawn`/`channel`/`send`/`recv` as builtins. **Task graphs are a runtime library** (`orchestration/task_graph.py`) operating on data the compiler emits — genuine deterministic sequencing, but not language-level, and the README said otherwise until v4.2.0.

If you're building multi-step AI agents, embedding a scripting layer in a Python application, or wiring together tools via MCP or A2A (through the `nodus-mcp` and `nodus-a2a` companion packages — the core language ships neither protocol), Nodus is the execution layer.

For a machine-readable project index see [llms.txt](llms.txt).

Beyond the core language, the Nodus ecosystem spans **32 standalone companion packages**
published on PyPI (33 projects counting `nodus-lang` itself), all with source at
`github.com/Masterplanner25`. A unified SDK (`nodus-sdk`) provides a single installation
story: `pip install nodus-sdk[agent,sql,fastapi]`. See the
[ecosystem guide](docs/guide/ecosystem.md) for the package-by-package breakdown.

Editor and CI integrations ship separately: the
[VS Code extension](https://marketplace.visualstudio.com/items?itemName=MasterplanInfiniteWeave.nodus-lang)
(syntax, LSP, debugger), the [Jupyter kernel](https://pypi.org/project/nodus-jupyter/),
and the [`nodus-run` GitHub Action](https://github.com/Masterplanner25/nodus-run-action).

## Install

Requires **Python 3.10+**.

```bash
pip install nodus-lang
```

Optional extras:

```bash
pip install "nodus-lang[server]"   # FastAPI + Uvicorn — nodus serve
pip install "nodus-lang[http]"     # httpx — std:http
pip install "nodus-lang[schema]"   # pydantic — syscall/extension schema validation
pip install "nodus-lang[retry]"    # nodus-retry — durable effect store for std:retry
```

Without `[retry]`, `std:retry` falls back to the built-in in-memory effect store.

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
- `nodus run hello.nd` / `nodus run` — run a file, or the current project's entry point
- `nodus check hello.nd` / `nodus check` — validate syntax and imports without executing
- `nodus fmt hello.nd` — format in place
- `nodus test` — run `*_test.nd` / `test_*.nd` files
- `nodus repl` — interactive shell
- `nodus status` — show the project and entry point for the current directory
- `nodus stability` — show which language surfaces are stable vs experimental

`nodus --help` lists the rest: project and dependency management (`init`, `add`,
`install`, `deps`), inspection (`ast`, `dis`, `debug`, `profile`), orchestration
(`workflow`, `goal-run`, `graph run`), the HTTP server (`serve`, `worker`), and the
LSP/DAP servers (`lsp`, `dap`) used by the editor integrations.

## Standard Library

Import standard library modules with the `std:` prefix:

```nd
import "std:http" as http
let r = http.get("https://api.example.com/data")
print(r.body)
```

The standard library ships with Nodus — no extra installs for core modules (`std:http` is
the one exception; it needs the `[http]` extra above). Full reference:
[Standard Library guide](docs/guide/standard-library.md).

**Networking, processes, and the filesystem**

| Module | What it does |
|---|---|
| `std:http` | HTTP client — GET, POST, PUT, DELETE, PATCH; async variants; SSE streaming (requires `nodus-lang[http]`) |
| `std:subprocess` | Run processes — `sp.run(argv)`, `sp.spawn(argv)` for async + channel output |
| `std:fs` | Filesystem — read, write, append, exists, listdir, ensure_dir |
| `std:path` | Path manipulation — `join`, `dirname`, `basename`, `ext`, `stem`, `relative`, `absolute` |
| `std:env` | Environment variables — `get`, `get_or`, `set`, `unset`, `has`, `list_keys` |

**Data and encoding**

| Module | What it does |
|---|---|
| `std:json` | `json.parse(str)` / `json.stringify(val)` |
| `std:math` | Arithmetic, rounding, min/max, `random`, numeric parsing |
| `std:strings` | Split, join, trim, replace, contains, repeat, case conversion |
| `std:collections` | `map`, `filter`, `reduce`, `push`, `pop`, `first`, `last`, `has_key` |
| `std:encoding` | Base64, hex, and URL encode/decode |
| `std:hash` | SHA-256 / SHA-512 / BLAKE2b, HMAC — returns a record; call `.to_hex()` |
| `std:utils` | `clamp`, `coalesce`, `get` — small helpers |

**Time and system**

| Module | What it does |
|---|---|
| `std:time` | `now()`, `from_epoch_ms(ms)`, format/parse timestamps, duration helpers |
| `std:secrets` | Cryptographic random tokens and bytes |
| `std:runtime` | Introspection — `typeof`, `fields`, `fn_arity`, `stack_depth`, `tasks`, `scheduler` |

**Concurrency (experimental)**

| Module | What it does |
|---|---|
| `std:async` | `sleep(ms)`, `parallel(tasks)`, `series(tasks)`, `worker_pool(worker, count)`, `pipeline(stages)` |

`channel()`, `send()`, `recv()`, `close()`, `spawn()`, and `coroutine()` are VM
built-ins — always available, no import needed.

**AI-native orchestration (v4.0)**

| Module | What it does |
|---|---|
| `std:tool` | Register and dispatch tools in a namespaced local registry; MCP-shaped, bridged to the wire protocol by the `nodus-mcp` companion package |
| `std:tools` / `std:agent` | Call tools and agents registered by the embedding host — `execute`/`call`, `available`, `describe` |
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

- [User Guide](docs/guide/getting-started.md) — task-oriented walkthroughs; index in §7
- [Language Specification](docs/language/LANGUAGE_SPEC.md) — full syntax, types, control flow, imports, coroutines
- [Embedding Nodus](docs/guide/embedding-nodus.md) — `NodusRuntime` from Python, sandboxing, limits
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
allowed_paths=CWD since v4.0.1), the stdlib module surface, and 15 verified complete example
programs.

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
framework built on the Infinity Algorithm. Nodus is the runtime layer whose execution
model embodies the Infinity Algorithm's orchestration structure (see
[Infinity Pattern Mapping](docs/architecture/INFINITY_PATTERN_MAPPING.md)).

**From the creator's writing:**
- [Why I'm Building A.I.N.D.Y. (Or Any Tool, Really)](https://medium.com/masterplan-infinite-weave/2025-chatgpt-ai-the-duality-of-progress-why-im-building-a-i-n-d-y-or-any-tool-really-a138f7860fba) — the strategic context behind Nodus
- [Duality of Progress: Master Index](https://medium.com/masterplan-infinite-weave/2025-chatgpt-ai-the-duality-of-progress-master-index-strategic-manifesto-4c96cf98348a) — the Infinity Algorithm framework Nodus executes
- [AI Search Optimization](https://medium.com/masterplan-infinite-weave/2025-chatgpt-case-study-ai-search-optimization-0f8cd5e78d4f) — the discoverability philosophy this project embodies
