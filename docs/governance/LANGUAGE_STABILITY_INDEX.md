<!-- Authored by Codex during non coding session. Needs review before repo commit and push. -->

# Language Stability Index

**Version:** 3.0.2
**Status:** Governing document — supersedes `docs/governance/STABILITY.md`
**Maintainer:** Shawn Knight (Masterplanner25)

This is the surface-by-surface stability index for Nodus. Every public surface is
classified. Classifications apply to the current release only; experimental surfaces
may stabilize in future releases without notice in this document — changes are recorded
in CHANGELOG.md and the relevant eval reports.

---

## Stability tiers

| Tier | Meaning |
|------|---------|
| **Stable** | Frozen behavior. Breaking changes require a major version bump and a COMPATIBILITY_MODEL.md policy exception. |
| **Mostly Stable** | Minor refinements may occur in minor releases. Breakage is avoided but not guaranteed. |
| **Experimental** | Behavior may change in any release. Do not take production dependencies on experimental surfaces without tracking CHANGELOG.md. |
| **Internal** | Not part of the public API. May change without notice. Do not reference from application code or library code. |

---

## 1. Language syntax

| Surface | Tier | Notes |
|---------|------|-------|
| Core declarations: `let`, `fn` | Stable | Frozen since v1.0 |
| Literals: numbers, ints, strings, booleans, `nil` | Stable | String escapes `\x`, `\u` finalized in v3.0.1 |
| Integer suffix `i` (e.g. `42i`) | Stable | Added in v3.0 |
| Arithmetic operators `+ - * / %` | Stable | |
| Comparison operators `== != < > <= >=` | Stable | |
| Logical operators `&& \|\| !` | Stable | |
| Control flow: `if`, `while`, `for (init;cond;inc)` | Stable | |
| `for name in iterable` | Mostly Stable | Protocol stable; edge cases may be refined |
| `try / catch / finally` | Stable | `finally` finalized at v1.0 |
| `throw expr` | Stable | Structured payload preservation finalized at v1.0 |
| `return` | Stable | |
| List literals `[...]` | Stable | |
| Map literals `{"key": value}` | Stable | Quoted-string keys required |
| Record literals `{ key: value }` | Stable | Map/record disambiguation finalized in v3.0 |
| `record { ... }` explicit form | Stable | |
| Dot access on records | Stable | |
| Bracket access on maps | Stable | |
| Import syntax `import "path" as name` | Stable | |
| Export syntax | Mostly Stable | Visibility rules may be refined |
| `workflow`, `goal`, `step` | Experimental | Implemented; semantics may change |
| `action` expressions in steps | Experimental | |
| `yield expr` | Mostly Stable | Semantics frozen; `YIELD` opcode stable |
| `spawn`, `coroutine`, `channel` | Experimental | Implemented; API not frozen |
| String interpolation | Check V4_0_PLAN.md — planned for v4.0 | Not yet in 3.0.2 |
| Optional type annotations | Experimental | Syntax accepted; no enforcement |
| `break` / `continue` | Not implemented | Not in 3.0.2 |

---

## 2. Standard library modules

| Module | Tier | Notes |
|--------|------|-------|
| `std:json` | Stable | `json.parse` returns maps (v2.1.0); `json.stringify` stable |
| `std:math` | Mostly Stable | Extended in v4.0 with `is_numeric`, `is_nan`, etc. |
| `std:strings` | Mostly Stable | Core ops stable; further additions possible |
| `std:collections` | Mostly Stable | Map/list ops stable; additions possible |
| `std:fs` | Mostly Stable | Sandbox enforcement added in v2.1.1; API stable |
| `std:path` | Mostly Stable | |
| `std:http` | Experimental | Shipping in v4.0; async variants + SSE streaming |
| `std:env` | Experimental | Shipping in v4.0 |
| `std:time` | Experimental | Shipping in v4.0 |
| `std:hash` | Experimental | Shipping in v4.0; returns hash record with `.to_hex()` |
| `std:encoding` | Experimental | Shipping in v4.0; base64, URL encode/decode |
| `std:secrets` | Experimental | Shipping in v4.0; cryptographic random tokens |
| `std:subprocess` | Experimental | Shipping in v4.0; run, shell, spawn with async variants |
| `std:test` | Experimental | Shipping in v4.0; built-in assertion framework |
| `std:tool` | Experimental | Shipping in v4.0; MCP-compatible tool registry |
| `std:identity` | Experimental | Shipping in v4.0; trace_id, session_id propagation |
| `std:effects` | Experimental | Shipping in v4.0; EXACTLY_ONCE idempotency |
| `std:sys` | Experimental | Shipping in v4.0; versioned syscall dispatch |
| `std:memory` | Experimental | Shipping in v4.0; share/recall/forget across namespaces |
| `std:retry` | Experimental | Shipping in v4.0; configurable retry policies |
| `std:circuit_breaker` | Experimental | Shipping in v4.0; three-state breaker |
| Legacy `.tl` extension | Deprecated | Warned on use; no removal date set |

---

## 3. Embedding API (`NodusRuntime`)

| Surface | Tier | Notes |
|---------|------|-------|
| `from nodus import NodusRuntime` | Stable | Added to `nodus.__all__` in v1.0 |
| `NodusRuntime(...)` constructor params | Stable | Stable: `max_steps`, `timeout_ms`, `max_stdout_chars`, `project_root`, `allowed_paths`, `allow_input`, `max_frames`. Added v4.0: `on_error` (coroutine error hook) |
| `run_source(source, ...)` | Stable | Returns `{"ok", "stdout", "stderr", "error"}` |
| `run_file(path, ...)` | Stable | |
| `register_function(name, fn, arity)` | Stable | |
| `reset()` | Stable | |
| `shutdown()` | Stable | Added v4.0; clears last_vm, host functions, tools |
| `set_trace_id(id)` | Mostly Stable | Added v4.0 |
| `set_effect_store(store)` | Mostly Stable | Added v4.0 |
| `run_source()` result shape | Stable | `ok`, `stdout`, `stderr`, `error` keys |
| `run_file()` result shape | Stable | Now consistent with run_source (ok=False for missing files, v4.0) |
| Event subscription API | Experimental | Not yet implemented |
| Module loading hooks | Experimental | Not yet implemented |
| `host_globals` parameter | Mostly Stable | |
| `initial_globals` parameter | Mostly Stable | |
| `nodus.tooling.loader.run_source()` | Internal | Low-level; no sandbox controls; prefer `NodusRuntime` |

---

## 4. Bytecode format

| Surface | Tier | Notes |
|---------|------|-------|
| Opcode set (47 opcodes) | Stable | Frozen at v1.0 (2026-03-15) |
| `BYTECODE_VERSION = 4` | Stable | Bumped for `finally` support; frozen |
| Bytecode cache format | Mostly Stable | Uses `marshal` + SHA-256 + `NDSC` magic; invalidated on version change |
| `FunctionInfo` serialization | Internal | Cache format; may change without notice on `BYTECODE_VERSION` bump |
| Adding new opcodes | Requires major version bump | See RELEASE_CHECKLIST.md for opcode addition procedure |

---

## 5. VM and runtime internals

| Surface | Tier | Notes |
|---------|------|-------|
| `VM.execute()` dispatch model | Internal | Dict-based dispatch table; internal implementation |
| `BuiltinRegistry` | Internal | Internal structure; subject to change |
| `ModuleLoader` | Internal (but stable path) | `load_module_from_source()` / `load_module_from_path()` used internally; no public API contract |
| `TASK_STEP_BUDGET = 1000` | Mostly Stable | Scheduler fairness parameter; may be tunable in future |
| Workflow persistence format (`.nodus/graphs/`) | Experimental | JSON format; may change between releases |
| Module cache (`.nodus/cache/`) | Internal | Invalidated by `BYTECODE_VERSION` change |
| Dependency graph (`.nodus/deps.json`) | Internal | |

---

## 6. CLI

| Surface | Tier | Notes |
|---------|------|-------|
| `nodus run <file>` | Stable | |
| `nodus run` (project mode) | Stable | |
| `nodus check` | Stable | |
| `nodus fmt` | Stable | |
| `nodus repl` | Stable | |
| `nodus --version` | Stable | |
| `nodus init` | Stable | |
| `nodus install` | Mostly Stable | Package manager; registry auth added in v0.9 |
| `nodus publish` | Mostly Stable | |
| `nodus login` / `nodus logout` | Mostly Stable | |
| `nodus dis` | Internal | Bytecode disassembler; output format not guaranteed |
| `nodus ast` | Internal | AST printer; output format not guaranteed |
| REPL inspection commands (`:ast`, `:dis`, `:type`) | Internal | REPL-only; output format not guaranteed |

---

## 7. Tooling servers (LSP, DAP)

| Surface | Tier | Notes |
|---------|------|-------|
| LSP server (language server protocol) | Experimental | Implements LSP 3.17; feature coverage partial |
| DAP server (debug adapter protocol) | Experimental | Breakpoints, stepping, variable inspection; `evaluate` not implemented (GitHub #106) |
| Server mode (HTTP/FastAPI) | Experimental | Requires `nodus-lang[server]`; protocol not frozen |

**Tooling drift policy:** The formatter has a CI gate that catches formatting
regressions automatically. The LSP and DAP do not have equivalent gates —
both implement AST visitor patterns that must be manually updated when new
syntax constructs are added to the language.

**Rule:** Any PR that adds new AST node types (new syntax) must update the
following tooling surfaces in the same PR or explicitly defer with a filed issue:
1. `src/nodus/tooling/formatter.py` — new node types in `format_stmt`/`format_expr`
2. `src/nodus/lsp/server.py` — new node types in the analysis visitor
3. `src/nodus/dap/server.py` — new control flow nodes that affect stepping behavior

The formatter CI gate (`find . -name "*.nd" | xargs python nodus.py fmt --check`)
catches formatter drift on every commit. LSP and DAP have no equivalent gate.
Until gated tests exist for those, this rule is the process guard against drift.

---

## 8. Error types and shapes

| Surface | Tier | Notes |
|---------|------|-------|
| Err record shape `{kind, message, payload, path, line, column, stack}` | Stable | Standard error record shape |
| `kind="syntax"` | Stable | |
| `kind="runtime"` | Stable | |
| `kind="sandbox"` | Stable | |
| `kind="thrown"` | Stable | |
| `LangRuntimeError` Python exception | Internal | Python-level exception; internal detail |
| `LangSyntaxError` Python exception | Internal | |

---

## 9. Eval score and quality gates

| Surface | Tier | Notes |
|---------|------|-------|
| Eval score (composite weighted, 21 dimensions) | Informational | Current: 7.57/10 (v3.0.2); not a stability guarantee |
| Coverage gate (≥60%) | Internal quality gate | Not a public API commitment |
| Ruff lint gate | Internal quality gate | |
| Doc-vs-code gate (nodus_gate) | Internal quality gate | |

---

## 10. Graduation criteria for experimental surfaces

An experimental surface graduates to Mostly Stable or Stable when:

1. Two consecutive eval cycles show no regressions in that surface
2. The surface has test coverage ≥ 70% for its implementation
3. A design decision record exists and is not provisional
4. The surface has been in production use (embedded or CLI) without reported breakage

Coroutines, channels, and task graphs are the largest experimental surfaces. They are
implemented and tested but their API has not completed the graduation process.

---

## Related documents

- `docs/governance/STABILITY.md` — original stability summary (still valid; this doc supersedes it)
- `docs/governance/COMPATIBILITY_MODEL.md` — what breaks between versions
- `docs/governance/RELEASE_GATES.md` — release quality gates
- `docs/governance/VERSIONING.md` — versioning policy
- `docs/evals/` — eval reports that inform stability decisions
