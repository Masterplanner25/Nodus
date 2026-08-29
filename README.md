# Nodus

[![CI](https://github.com/Masterplanner25/Nodus/actions/workflows/ci.yml/badge.svg)](https://github.com/Masterplanner25/Nodus/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/nodus-lang.svg)](https://pypi.org/project/nodus-lang/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](https://github.com/Masterplanner25/Nodus/blob/main/LICENSE)

> **Stable on PyPI** — `pip install nodus-lang` · Full 35-package companion ecosystem live: `pip install nodus-sdk[agent,sql,fastapi]`
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
> [the migration note](https://github.com/Masterplanner25/Nodus/blob/main/docs/migration/v5.0-deny-by-default.md) and
> [#405](https://github.com/Masterplanner25/Nodus/issues/405).

**Recent:** 5.7.0 is about declaring contracts at the boundaries a program cannot see across: the host functions it requires (`extern`), the types a host function takes, the shape a resume payload must have, and the undo path for work that already succeeded (`compensates`).

An installed Nodus could not tell you where its own documentation was. The wheel
shipped code and the stdlib; the guide, the machine-readable index and the agent
skills were repo-only, no command mentioned them, and PyPI silently drops the
relative links a README uses — so an agent working inside a virtualenv had no
next step at all. `nodus docs` answers that from the install itself, `llms.txt`
now ships in the package, and every link here is absolute. The skill that ships
for Claude Code and Codex had described 4.1.1 for nine releases: it taught a
200 ms embedding deadline that no longer exists and said nothing about the
capability defaults that inverted in 5.0.0, which made its advice backwards
rather than merely old.

The editor got the same treatment. Hover, go-to-definition and completions were
blind inside a workflow step body; a destructured `let [a, b]` was reported as
an *undefined variable* on correct code; and a typo inside a string
interpolation, a compound assignment or an `action` payload was accepted in
silence. The editor and the runtime also disagreed about what an import meant —
two resolvers, and the one the editor used could not see a pip-installed
companion, so `import "nodus-mcp"` ran fine and read as "Import not found" on
screen.

Underneath, three guarantees stopped being conditional. A workflow step body can
no longer be called out of order — `step B after A` is enforced at every door
into a step, not just the routed one. A step's `timeout_ms` now bounds an
`action agent` handler, which it had never done: the budget was read from
scheduler state the handler's own thread had already left behind, so whether the
bound applied was a race. And both halves of a run's state relocate together
under `NODUS_RUN_STATE_ROOT`, with the capability floor following them — the
supported way to move the store had been moving it out of the floor's reach.

5.4.0 is about a resume that tells the truth, and an inspection that
costs nothing.

A resume used to answer questions it had not been asked. It replayed the source
stored with the run — the right rule — but said nothing when the file had moved
on since, while a run persisted before source recording rebuilt from disk
instead: the opposite rule, equally silent. Both announce themselves now. A
rebuilt graph whose *shape* has drifted is refused with the real reason, in place
of a manufactured `Dependency cycle detected` in code that has no cycle. A resume
from a mid-step checkpoint no longer double-counts a folded `state` cell's
contributions, and a checkpoint resume of a run that is *waiting* — which could
only ever re-wait — is refused instead of reporting success. What a run persists
is also now written down: every run stores its whole program text as the rebuild
handle, `nodus workflow cleanup` bounds that by default, and an embedder can
decline it with `persist_workflow_source=False`.

`nodus graph` and `nodus graph show` no longer execute the file they are asked to
inspect. The plan is built from the workflow declarations alone, so pointing them
at an untrusted or generated `.nd` file runs none of its code — `--execute`
restores the old behaviour for graphs constructed at runtime. `nodus check` now
enters workflow step bodies, which had been invisible to both the type checker
and the editor diagnostics, and what it does and does not guarantee is stated in
its `--help`.

Three things that could not be said before, can be: `step … with { allow_failure:
true }` for a step whose failure is not the run's failure, `try { } finally { }`
without the `catch e { throw e }` boilerplate, and a bounded `channel(n)` that
makes a fast producer *wait* for its consumer rather than raise.

5.3.0 is about declarations that bind. A run of surfaces accepted
something that read as a decision and enforced none of it, and each is now either
enforced or refused where it is written.

A `CapabilityPolicy` that denied everything used to deny nothing outside the four
sandbox flags: tool invocation, syscalls, agent dispatch and the whole memory
store were invisible to it, and `DenyList("tool.invoke")` raised *unknown
capability*. Five capability names close that, `SyscallSpec.capability` is
enforced rather than merely published, and every builtin is now classified as
carrying authority or explicitly not — so a new one fails the suite until someone
decides which.

`allowed_paths` gains a write dimension: `writable_paths=["/repo/src"]` inside
`allowed_paths=["/repo"]` gives read-only context and an editable subtree, the
split an agent editing a repository actually wants. `nodus.toml` refuses tables
and keys it does not read instead of discarding them silently, and `entry` now
selects what `nodus run` starts. A `step … with { worker: "sandboxed" }` that
nothing can honour warns rather than running in-process and reporting success.
And a conditional workflow edge finally says so in the plan and the diagram —
`nodus graph show` labels an `on:` filter and dashes a `when` guard, where both
were plain arrows before.

5.2.0 closed the write-merge gap at a join. Two concurrent steps that
read a `state` cell, do something slow, and write it back used to lose one of the
writes silently. A cell can now declare how concurrent writes combine —
`state total = 0i with { merge: "sum" }`, or `"append"` / `"union"` for lists — and
under a fold `total += 1i` *contributes* a value applied at the join rather than
assigning into a slot another branch is halfway through reading. A plain
`total = ...` on a folded cell is a compile error, because a final value cannot be
combined with another branch's. Where no policy is declared the runtime warns, and
only when an update was genuinely lost.

It also adds three commands — `nodus graph show` renders a planned workflow as
Mermaid or DOT, `nodus doctor` reports which package and version your `nodus`
actually resolves to, and `nodus completion` emits shell completions — and makes
ordinary runs about twice as fast by no longer retaining a telemetry event for
every function call and return.

5.1.0 gave the workflow DSL the vocabulary it was missing at a join: a step can
carry a guard (`step ship after review when reached("approved")`) and declare which
dependency outcomes satisfy it (`with { on: ["failed"] }`). Every task in a run
reports a status — `completed`, `failed`, `upstream_failed`, `skipped`, `omitted`,
`cancelled` or `abandoned` — where before, anything that never got a turn was simply
absent from the result. A failed step no longer tears the scheduler down: the run
drains and then reports, so a timed-out step gets its `finally` blocks and siblings
finish.

**One behaviour change to know about, and it is worth a minute if you embed Nodus.**
`run_source(source, filename=...)` used to run the *file* named by `filename`
whenever one existed, discarding the `source` you passed and returning `ok=True`
with the other program's output — so which program ran depended on the process CWD
([#521](https://github.com/Masterplanner25/Nodus/issues/521), present since v0.4.0).
`filename` is now purely a label, as the guide always said it was; a real path still
resolves relative imports against its directory, and `run_file` is unchanged. If you
were relying on the old behaviour to run a file, call `run_file`.

5.0.4 repairs one thing 5.0.3 broke — constructing a
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
represent instead of corrupting it. See the [changelog](https://github.com/Masterplanner25/Nodus/blob/main/CHANGELOG.md).

```bash
pip install nodus-lang
nodus init
nodus run
nodus repl
```

Nodus is an **orchestration DSL and embedded runtime** for building agentic hosts, created by **Shawn Knight** as part of the **Masterplan Infinite Weave** ecosystem. Its execution model embodies the **Infinity Algorithm**'s feedback-loop structure at the runtime layer — a structural correspondence documented in [Infinity Pattern Mapping](https://github.com/Masterplanner25/Nodus/blob/main/docs/architecture/INFINITY_PATTERN_MAPPING.md), not a named construct in the grammar.

**There is no model in the core, and that is the design.** Nodus contains no LLM client, no agent loop and no tool-selection logic; `action agent "name" with {...}` hands a JSON-safe payload to a handler your host registers, and takes a result back. Because the runtime cannot perform inference, every semantic decision *must* cross that boundary — so deterministic structure never guesses, and the model never controls sequencing.

What the language contributes: `workflow`, `goal`, `step` and `after` are real keywords with real AST nodes, and dependency names are resolved and checked at parse time — `after typo` is a syntax error, which LangGraph, Prefect and Airflow all discover at run time. Coroutines are a hybrid: one `YIELD` opcode and a VM-level `Coroutine` that saves `ip`/`stack`/`frames`, with `spawn`/`channel`/`send`/`recv` as builtins. **Task graphs are a runtime library** (`orchestration/task_graph.py`) operating on data the compiler emits — genuine deterministic sequencing, but not language-level, and the README said otherwise until v4.2.0.

If you're building multi-step AI agents, embedding a scripting layer in a Python application, or wiring together tools via MCP or A2A (through the `nodus-mcp` and `nodus-a2a` companion packages — the core language ships neither protocol), Nodus is the execution layer.

For a machine-readable project index see [llms.txt](https://github.com/Masterplanner25/Nodus/blob/main/llms.txt).

Beyond the core language, the Nodus ecosystem spans **35 standalone companion packages**
published on PyPI (36 projects counting `nodus-lang` itself), all with source at
`github.com/Masterplanner25`. A unified SDK (`nodus-sdk`) provides a single installation
story: `pip install nodus-sdk[agent,sql,fastapi]`. See the
[ecosystem guide](https://github.com/Masterplanner25/Nodus/blob/main/docs/guide/ecosystem.md) for the package-by-package breakdown.

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
[Standard Library guide](https://github.com/Masterplanner25/Nodus/blob/main/docs/guide/standard-library.md).

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

## Where This Is Going

Nodus will bootstrap itself — compile itself in itself. The lexer, parser, AST
lowering, bytecode generation and VM evaluation get rewritten in Nodus.

It is a long-term goal rather than a near-term one, but it is a decided
direction, and it constrains design now: a feature that would make bootstrapping
impossible, or need a separate "systems" subset to work around, is treated as
evidence the abstraction level is wrong.

The proof-of-concept exists — [`examples/expr_compiler.nd`](https://github.com/Masterplanner25/Nodus/blob/main/examples/expr_compiler.nd)
is a lexer, recursive-descent parser and evaluator written entirely in Nodus. The
semantics are there and the 49-opcode instruction set has been frozen since v1.0.
Runtime throughput is the honest blocker: roughly **400K instructions/sec** on
CPython for a hot arithmetic loop, **~320K on a compiler workload**. Nodus runs on
**PyPy** unmodified, which is worth ~23× on that arithmetic loop but **~4–5× on the
compiler workload** — a JIT is at its best on a tight loop, so the larger number is
an upper bound rather than a promise. A further **1.5× is available with no new
runtime at all**: the VM retains an event per function call and return, unbounded
and unread ([#522](https://github.com/Masterplanner25/Nodus/issues/522)). See
[Language Vision §Bootstrapping](https://github.com/Masterplanner25/Nodus/blob/main/docs/language/LANGUAGE_VISION.md#bootstrapping-long-term-goal).

## Documentation

- [User Guide](https://github.com/Masterplanner25/Nodus/blob/main/docs/guide/getting-started.md) — task-oriented walkthroughs; index in §7
- [Language Specification](https://github.com/Masterplanner25/Nodus/blob/main/docs/language/LANGUAGE_SPEC.md) — full syntax, types, control flow, imports, coroutines
- [Embedding Nodus](https://github.com/Masterplanner25/Nodus/blob/main/docs/guide/embedding-nodus.md) — `NodusRuntime` from Python, sandboxing, limits
- [Ecosystem Specs](https://github.com/Masterplanner25/Nodus/blob/main/docs/ecosystem/README.md) - implementation specs for proposed Nodus libraries and frameworks
- [Architecture](https://github.com/Masterplanner25/Nodus/blob/main/docs/runtime/ARCHITECTURE.md) — runtime pipeline and module system
- [Changelog](https://github.com/Masterplanner25/Nodus/blob/main/CHANGELOG.md) — version history
- [Contributing](https://github.com/Masterplanner25/Nodus/blob/main/CONTRIBUTING.md) — development setup, code style, and contribution process
- [llms.txt](https://github.com/Masterplanner25/Nodus/blob/main/llms.txt) — machine-readable project index for AI tools
- [llms-full.txt](https://github.com/Masterplanner25/Nodus/blob/main/llms-full.txt) — full content summaries for AI indexers

## Using with Claude Code

If you write Nodus with [Claude Code](https://claude.ai/code), a language skill is available
that teaches Claude the idioms, gotchas, and workflow patterns specific to Nodus v4:

1. Download [`skills/nodus.skill`](https://github.com/Masterplanner25/Nodus/blob/main/skills/nodus.skill) and [`skills/project-CLAUDE.md`](https://github.com/Masterplanner25/Nodus/blob/main/skills/project-CLAUDE.md) from this repo.
2. Copy `project-CLAUDE.md` to your project root as `CLAUDE.md` (fill in your project name).
3. Drop `nodus.skill` in your project's `.claude/commands/` folder.
4. Claude will apply Nodus-specific rules automatically in every session.

The skill covers: record vs map distinction, the closure outer-let pattern, `spawn()` coroutine
wrapping, workflow result bracket notation, NodusRuntime embedding defaults (timeout_ms=None,
allowed_paths=CWD since v4.0.1), the stdlib module surface, and 15 verified complete example
programs.

## Using with Codex

If you write Nodus with Codex, a Codex-native skill and project template are available:

1. Copy [`skills/project-AGENTS.md`](https://github.com/Masterplanner25/Nodus/blob/main/skills/project-AGENTS.md) to your project root as `AGENTS.md` and fill in your project name if needed.
2. Copy the [`skills/nodus/`](https://github.com/Masterplanner25/Nodus/tree/main/skills/nodus/) folder to `$CODEX_HOME/skills/nodus` or `~/.codex/skills/nodus`.
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
[Infinity Pattern Mapping](https://github.com/Masterplanner25/Nodus/blob/main/docs/architecture/INFINITY_PATTERN_MAPPING.md)).

**From the creator's writing:**
- [Why I'm Building A.I.N.D.Y. (Or Any Tool, Really)](https://medium.com/masterplan-infinite-weave/2025-chatgpt-ai-the-duality-of-progress-why-im-building-a-i-n-d-y-or-any-tool-really-a138f7860fba) — the strategic context behind Nodus
- [Duality of Progress: Master Index](https://medium.com/masterplan-infinite-weave/2025-chatgpt-ai-the-duality-of-progress-master-index-strategic-manifesto-4c96cf98348a) — the Infinity Algorithm framework Nodus executes
- [AI Search Optimization](https://medium.com/masterplan-infinite-weave/2025-chatgpt-case-study-ai-search-optimization-0f8cd5e78d4f) — the discoverability philosophy this project embodies
