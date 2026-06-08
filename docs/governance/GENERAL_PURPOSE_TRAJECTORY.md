# General-Purpose Language Trajectory

**Status:** Strategic direction document — v4.0.0 baseline assessment  
**Date:** 2026-06-08

---

## The shift being proposed

Nodus should evolve from being good at orchestration to being able to express most
normal programs without escape hatches — while orchestration remains the killer use
case. Not "Nodus competes with Python at everything." The stronger identity:

> **Nodus is a general-purpose programming language for execution-native systems.**

Orchestration, agents, workflows, and runtime automation are where it is architecturally
strongest. But a developer should be able to reach for Nodus for any automation task,
tooling problem, or service without hitting the wall of "I can't express that cleanly."

This document maps the 8-step ladder to current reality so the gaps are named precisely.

---

## The ladder

```
DSL
  → scripting language
    → orchestration language       ← Nodus is here today
      → runtime programming language
        → general-purpose language with a dominant execution niche  ← target
```

---

## Step-by-step gap analysis

### Step 1 — Stabilize the core language

**Target:** boring, dependable semantics that do not keep shifting.

| Capability | Status | Notes |
|-----------|--------|-------|
| Variables, functions, modules, errors, closures | ✅ Stable | BYTECODE_VERSION=4, frozen |
| Async / coroutines / channels | ✅ Stable | Marked Experimental in stability index — the semantics are stable, the surface name isn't |
| Loops — C-style `for(;;)` | ✅ Complete | Parser: `for_stmt()` |
| Loops — `for x in iterable` | ✅ Complete | Parser: `for_each_stmt()`, ForEach AST node |
| Destructuring `let` | ✅ Complete | List and record pattern destructuring |
| Optional type hints on `let` | ✅ Complete | `let x: int = 5` parses; not enforced at runtime |
| Bytecode stability | ✅ Frozen | All 47 opcodes stable since v1.0 |
| Closure upvalue mutation | ❌ Missing | DESIGN-006, deferred to v5. Can't assign outer `let` from closure — workaround: map |
| String interpolation | ✅ Complete | `"\(expr)"` works |
| Pattern matching (beyond destructuring) | ❌ Missing | No `match/case`, no exhaustiveness checking |
| Error propagation shorthand | ❌ Missing | No `?` operator or equivalent — try/catch required everywhere |

**Assessment:** The core language is 90% of what "stable" requires. The two real gaps are
closure mutation and the absence of a propagation shorthand. Neither blocks most programs,
but both force workarounds that a general-purpose language shouldn't require.

---

### Step 2 — Expand the standard library

**Target:** batteries that let a developer write a real program without reaching outside the language.

| Module | Status | Notes |
|--------|--------|-------|
| `std:strings` | ✅ Complete | split, join, trim, replace, contains, starts/ends with, etc. |
| `std:math` | ✅ Complete | floor, ceil, round, sqrt, abs, pow, min, max, trig |
| `std:json` | ✅ Complete | parse, stringify, full round-trip |
| `std:http` | ✅ Complete | All verbs, streaming, SSE, async, custom headers/auth/timeout |
| `std:fs` | ✅ Complete | read, write, append, delete, listdir, mkdir, exists |
| `std:path` | ✅ Complete | join, dirname, basename, ext, normalize |
| `std:env` | ✅ Complete | get, has, all — gated by `allow_env` sandbox flag |
| `std:subprocess` | ✅ Complete | sync, async, streaming, shell mode, stdin/stdout/stderr |
| `std:hash` | ✅ Complete | SHA-256, SHA-512, HMAC, MD5, Blake2, `.to_hex()` |
| `std:encoding` | ✅ Complete | base64, base64url, hex, URL encode/decode, form encode/decode |
| `std:collections` | ✅ Complete | map, filter, reduce, push/pop, sort, group, flatten |
| `std:test` | ✅ Complete | assert, expect, flush_async, advance_clock |
| `std:time` | ✅ Partial | sleep, now (ms timestamp) — no datetime parsing/formatting |
| `std:secrets` | ✅ Complete | constant-time compare |
| `std:tool` | ✅ Complete | register, invoke, lookup, list, has |
| `std:agent` | ✅ Complete | call, available, describe |
| `std:memory` | ✅ Complete | get, put, delete, keys, has, recall_from, recall_all |
| `std:async` | ✅ Complete | sleep, parallel, series, worker_pool, pipeline, queue |
| `std:runtime` | ✅ Complete | typeof, fields, stack_depth, tasks, scheduler stats, time_ms |
| `std:identity` | ✅ Complete | Phase 6 AI primitives |
| `std:effects` | ✅ Complete | Effect tracking |
| `std:circuit_breaker` | ✅ Complete | Call-site resilience |
| `std:retry` | ✅ Complete | Retry with backoff |
| **`std:log`** | **❌ Missing** | No structured logging; `print()` is the only output |
| **`std:regex`** | **❌ Missing** | No pattern matching on strings |
| **`std:datetime`** | **❌ Missing** | `std:time` gives `now()` in ms; no parse/format/timezone |
| **`std:csv`** | **❌ Missing** | No delimiter-separated parsing |
| **`std:toml`** | **❌ Missing** | No TOML parser (ironic given nodus.toml) |

**Assessment:** The stdlib is strong for I/O, HTTP, files, and data manipulation. The four
notable missing modules are `std:log`, `std:regex`, `std:datetime`, and `std:csv`. These
are not exotic — they are what every automation and CLI script reaches for. `std:log` and
`std:regex` in particular block the "write any general program" goal.

---

### Step 3 — Make app building possible

**Target:** support common application shapes without requiring Python interop.

| App type | Status | Notes |
|----------|--------|-------|
| CLI tools | ✅ Ready | subprocess + fs + HTTP + JSON + stdlib |
| Automation scripts | ✅ Ready | The primary use case |
| Workflow services | ✅ Ready | Full workflow engine with persistence |
| Background jobs | ✅ Ready | Coroutines + workflow + WorkerManager |
| Agent plugins | ✅ Ready | nodus-extension with subprocess sandbox |
| SDK integrations | ✅ Ready | NodusRuntime with host function registration |
| HTTP APIs | ⚠️ Near-term | nodus serve + nodus-router/gateway — needs hardening |
| Small web backends | ❌ Not yet | No template engine, no session middleware in-language |
| Frontend | ❌ Not realistic | No browser runtime, no UI model |

**Assessment:** CLI tools, automation, workflows, and agents are ready. HTTP APIs are
buildable but not hardened. Web backends are not a realistic near-term target.

---

### Step 4 — Package and library infrastructure

**Target:** an ecosystem where others can extend Nodus with libraries.

| Capability | Status | Notes |
|-----------|--------|-------|
| Package manifest (`nodus.toml`) | ✅ Complete | name, version, dependencies, entry points |
| Lockfile (`nodus.lock`) | ✅ Complete | Pinned versions + SHA-256 |
| Semver resolution | ✅ Complete | `~=`, `>=`, `==`, `^` |
| `nodus install / update / add / remove / deps` | ✅ Complete | Full package lifecycle |
| `nodus publish / login / logout` | ✅ Complete | Registry auth + archive upload with SHA-256 |
| Registry client (HTTP) | ✅ Complete | Bearer token, `NODUS_REGISTRY_TOKEN`, `~/.nodus/config.toml` |
| **Public registry** | **❌ Missing** | No PyPI-equivalent for Nodus packages. Current packages publish to PyPI as Python packages with `nodus.nd` entry points |
| **Docs generation** | **❌ Missing** | No `nodus doc` command |
| **Pure Nodus packages** | **❌ Missing** | Current library packages are Python-backed. A `.nd`-only package with no Python shim doesn't have a full story |

**Assessment:** The package tooling is substantially complete and more mature than expected
(package manager has been in since v0.9.0). The gap that matters most is the absence of a
public registry. `nodus install foo` has nowhere canonical to install *from* yet. The
ecosystem currently runs on PyPI as Python packages — which works but is not the natural
package story for a language runtime.

---

### Step 5 — Strengthen tooling

**Target:** developer ergonomics that make people stay.

| Tool | Status | Notes |
|------|--------|-------|
| Formatter (`nodus fmt`) | ✅ Complete | Deterministic, all 48 AST node types covered |
| Syntax checker (`nodus check`) | ✅ Complete | Validates syntax + imports |
| Profiler (`nodus profile`) | ✅ Complete | Opcode counts, function times, hot spots |
| REPL (`nodus repl`) | ✅ Complete | Multiline, history, `:ast`, `:dis`, `:type`, `:help` |
| Debugger (`nodus dap`, `nodus debug`) | ✅ Complete | Full DAP server: breakpoints, step/next/continue, stack frames, variable scopes |
| LSP (`nodus lsp`) | ✅ Complete | Diagnostics, completion, hover, go-to-definition |
| `nodus init` | ⚠️ Minimal | Creates `nodus.toml` + `src/main.nd`; no project templates |
| **Semantic linter** | **❌ Missing** | `nodus check` validates syntax; no unused variable detection, no type-aware linting |
| **Docs generator** | **❌ Missing** | No `nodus doc` |
| **VS Code extension** | **⚠️ Partial** | TextMate grammar + LSP wiring exists in `tools/vscode/`; not published to VS Code Marketplace |
| **Error explanations** | **⚠️ Partial** | Error messages are good; limited "did you mean" |

**Assessment:** The tooling foundation is stronger than it appears. LSP and DAP are
implemented. The formatter is complete. What's missing is surface area: the VS Code
extension needs to be published, the linter needs semantic rules, and `nodus init`
needs project templates. None of these require architectural work — they require
completing what's already started.

---

### Step 6 — Define interop

**Target:** Nodus can be useful before it has a giant native ecosystem, by calling into other systems safely.

| Interop | Status | Notes |
|---------|--------|-------|
| Python interop (embedding) | ✅ Complete | `NodusRuntime` from Python; full host function injection |
| HTTP/service interop | ✅ Complete | `std:http` — any service with an HTTP API is reachable |
| Subprocess interop | ✅ Complete | `std:subprocess` — any installed binary |
| Plugin ABI | ✅ Complete | `nodus-extension` subprocess sandbox |
| MCP protocol | ✅ Complete | `nodus-mcp` v0.1.0 |
| A2A agent coordination | ✅ Complete | `nodus-a2a` v0.1.0 |
| WASM | ❌ Missing | No WASM compilation target or host |
| Native FFI | ❌ Missing | No direct C/Rust FFI (subprocess is the current path) |

**Assessment:** Interop is the strongest part of the general-purpose story. Any Python
library is accessible via `NodusRuntime.register_function()`. Any CLI tool is accessible
via `std:subprocess`. Any HTTP service is accessible via `std:http`. Any MCP-compatible
tool is accessible via `nodus-mcp`. The gaps (WASM, FFI) are long-term and not blockers
for the target use cases.

---

### Step 7 — Write real software in it

**Target:** non-demo, daily-use tools written in Nodus that validate the language maturity.

| Project | Status |
|---------|--------|
| Nodus package manager written in Nodus | ❌ Not started |
| Agent tools written in Nodus | ❌ Not started |
| Workflow runners written in Nodus | ❌ Not started |
| Test harnesses written in Nodus | ❌ Not started |
| Deployment scripts written in Nodus | ❌ Not started |

**Assessment:** This step is entirely undone. It is also the most credible proof that
the language is real. The package manager itself is the obvious first target — it is
already implemented in Python, has clear semantics, and would demonstrate that Nodus
can write systems-level tooling. Even a partial port would be meaningful.

This is the step that closes the gap between "language you can use" and "language people do use."

---

### Step 8 — Decide what general-purpose means for Nodus

The ROADMAP.md currently states:

> "Nodus is primarily an automation scripting and orchestration runtime, not a
> general-purpose application language."

This is stale. The capability set is already general-purpose for execution-native
domains. The decision to make is not "should we become general-purpose?" — it is
"what does general-purpose mean *for us*?"

**The right framing:**

Nodus should be able to express general programs, but is especially powerful for
orchestration, agents, workflows, runtime automation, and distributed execution.

This is different from "compete with Python at everything." It means:
- A Nodus developer writing an automation tool should not need to reach for Python
- A Nodus developer writing a workflow service should not need to escape to subprocess
- A Nodus developer writing an agent plugin should not need to implement it in a different language

The escape hatches should be for performance-sensitive or platform-specific code — not
for ordinary programming tasks.

---

## Priority ordering

The gaps that most block "write a real program without escape hatches" today, in order:

### Priority 1 — Fix the obvious stdlib holes (1–2 weeks)

`std:log`, `std:regex`, and `std:datetime` are the modules most likely to force a
developer to reach for subprocess or Python. These are isolated additions with no
architectural dependencies.

**`std:log`** — structured log output with levels (debug, info, warn, error), optional
timestamp, optional JSON format. The single most common thing missing from every script.

**`std:regex`** — match, search, replace, split against a pattern. The second most
common missing capability in string processing scripts.

**`std:datetime`** — parse from string, format to string, add/subtract intervals,
timezone-aware comparison. `std:time.now()` gives a millisecond timestamp; everything
else requires the host.

### Priority 2 — Fix closure upvalue mutation (2–4 weeks)

DESIGN-006 is the most ergonomically painful language limitation for general-purpose
programming. The workaround (map with quoted keys) is functional but alien. Closures
that can't mutate outer variables are a constant source of surprise for anyone who
has written in any mainstream language.

This is a v5.0 item per the roadmap. Given the general-purpose trajectory, it deserves
earlier attention.

### Priority 3 — Complete the tooling surface (2–3 weeks)

The VS Code extension needs to be published. The LSP exists but developers who don't
know to run `nodus lsp` won't find it. Publish the extension and it becomes discoverable.

Semantic linting rules (unused variables, unreachable code, type-inconsistent arguments
where inferable) would be a meaningful step beyond what `nodus check` does today.

### Priority 4 — Write the first real Nodus program (4–8 weeks)

A Nodus tool written in Nodus is the credibility test. The package manager is the
natural first candidate: it has well-defined semantics, uses HTTP, JSON, filesystem,
subprocess (for archive extraction), and cryptography — exactly the stdlib modules that
Nodus has covered. Writing even the `nodus install` command in Nodus would be meaningful.

### Priority 5 — Public registry (medium-term)

The package tooling is complete but has nowhere canonical to point `nodus install` at.
A public registry (even a minimal one running nodus serve + a simple index) would make
the package story real for third-party developers.

---

## What does NOT need to change

- The orchestration semantics. Workflow, goal, checkpoint, step/after — these stay as
  first-class language primitives. They are the architectural advantage.
- The embedding model. NodusRuntime with capability gating is a strong story.
- The coroutine + channel concurrency model. It works and is clean.
- The tool registration model. First-class tool registration is an AI/agent superpower.
- PyPI as the current distribution channel. This works for the Python-embedding story.

---

## What the ROADMAP.md needs

ROADMAP.md currently reflects v1.0/v2.x planning and names v2.1.0 as the current
release. It needs a v4.0.0 section and an updated "Strategic Identity" section that
reflects the general-purpose trajectory described here. That update is deferred until
this direction is validated — updating the roadmap should follow a decision to commit
to the trajectory, not precede it.
