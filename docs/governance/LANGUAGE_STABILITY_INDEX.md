# Language Stability Index

**Version:** 4.1.1
**Status:** Governing document — supersedes `docs/governance/STABILITY.md`
**Maintainer:** Shawn Knight (Masterplanner25)

This is the surface-by-surface stability index for Nodus. Every public surface is
classified. Classifications apply to the current release only; changes between
releases are recorded in CHANGELOG.md and the relevant eval reports.

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
| Compound assignment `+=, -=, *=, /=` | Mostly Stable | Added in v4.0.1 (#183); closures still require map-mutation pattern |
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
| String interpolation `"\(expr)"` | Stable | Implemented in v4.0; syntax frozen |
| `workflow`, `goal`, `step` | Mostly Stable | Graduated v4.0.5; WorkflowFrameworkRunner path unified; checkpoint API documented |
| `goal … over …` (stopping condition) | Experimental | New in this release (#409 Part A) and **additive** — the `goal g { step … }` form above is unchanged. `until` accepts `reached("literal")` composed with `&&`/`\|\|`/`!`; `budget` is mandatory. Not yet frozen: state-at-checkpoint predicates, ordered history (*reached A then B*), a cost bound, and pursuing a workflow declared in another module are all unimplemented and would extend the surface. |
| `action` expressions in steps | Experimental | Step modifier; API not yet frozen |
| `yield expr` | Stable | Promoted v4.0.5; `YIELD` opcode stable since v1.0; no further changes planned |
| `spawn`, `coroutine`, `channel` | Mostly Stable | Graduated v4.0.5; SCHED-001/002, CHAN-001, CIRC-001 all resolved |
| Optional type annotations | Experimental | Syntax accepted and preserved in AST; **no runtime enforcement** — `let x: int = "hello"` succeeds silently. Forward path: `nodus check --strict` (not yet implemented). |
| `break` / `continue` | Mostly Stable | Shipped v4.1.0 (#309) for `while`, C-style `for`, and `for … in`. Compile-time error outside a loop or across a `try`/`catch`/`finally` boundary. No new opcodes. |
| `match` expression | Mostly Stable | Shipped v4.1.0 (#308). Value-matching arms compared with `==`, first match wins, `_` catch-all must be last. **No destructuring or binding patterns** — those would extend the surface, so it is not yet Stable. |

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
| `std:http` | Experimental | Shipped in v4.0; async variants + SSE streaming |
| `std:env` | Experimental | Shipped in v4.0 |
| `std:time` | Experimental | Shipped in v4.0; `time.format()` strftime support added v4.0.3 |
| `std:hash` | Experimental | Shipped in v4.0; returns hash record with `.to_hex()` |
| `std:encoding` | Experimental | Shipped in v4.0; base64, URL encode/decode |
| `std:secrets` | Experimental | Shipped in v4.0; cryptographic random tokens |
| `std:subprocess` | Experimental | Shipped in v4.0; run, shell, spawn with async variants |
| `std:test` | Experimental | Shipped in v4.0; built-in assertion framework |
| `std:tool` | Experimental | Shipped in v4.0; MCP-compatible tool registry; dotted namespacing required |
| `std:identity` | Experimental | Shipped in v4.0; trace_id, session_id propagation; CLI propagation fixed v4.0.3 |
| `std:effects` | Experimental | Shipped in v4.0; EXACTLY_ONCE idempotency; `get_result()` added v4.0.3 |
| `std:sys` | Experimental | Shipped in v4.0; versioned syscall dispatch |
| `std:memory` | Experimental | Shipped in v4.0; share/recall/forget across namespaces; `tag`/`forget` added v4.0.3 |
| `std:retry` | Experimental | Shipped in v4.0; configurable retry policies |
| `std:circuit_breaker` | Experimental | Shipped in v4.0; three-state breaker; map-form `create` added v4.0.3 |
| `std:async` | Experimental | All of `sleep`, `queue`, `parallel`, `series`, `worker_pool`, `pipeline` work (`parallel`/`series` fixed v4.1.1; `worker_pool`/`pipeline` after 4.1.1 — both were non-functional through that release, spawning onto a scheduler nothing drove, #339). Workers and stages may suspend. `channel`/`send`/`recv`/`close`/`spawn`/`coroutine` are VM builtins, not exports of this module. |
| `std:runtime` | Experimental | Introspection — `typeof`, `fields`, `fn_arity`, `stack_depth`, `tasks`, `scheduler` |
| `std:utils` | Experimental | `clamp`, `coalesce`, `get` |
| `std:tools` / `std:agent` | Experimental | Adapters for tools/agents registered by the embedding host; `agent.call_async` added v4.1.0 (#294) |
| `std:bool` | Experimental | Single export `equal(value, bool_value)` |
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
| `agent_timeout_ms` constructor param | Mostly Stable | Added post-5.0.2 (#424). Default deadline for host agent handlers; `None` (unbounded) preserves prior behaviour. A step's `timeout_ms` wins when tighter. Bounds the *wait*, not the handler — an over-deadline handler keeps running on a daemon thread |
| `register_function` refusing builtin names | Stable | Raises `ValueError` for any builtin name. A security boundary for hosts installing fail-loud guards under a guest-reachable name; pinned by `tests/test_downstream_contracts.py`, not only documented |
| `active_vm()` | Mostly Stable | Added v5.0.1. The **accessor** is supported; the `VM` it returns is Internal and its attributes are not. `_get_active_vm()` retained as an alias for existing pinners |
| `NodusRuntime.__init__` taking no `**kwargs` | Stable | Deliberate: with a catch-all, a renamed confinement flag would be silently swallowed and the guest would run unconfined. A rename must raise `TypeError` so the embedder fails closed |
| Confinement flags keyword-only | Stable | `allow_subprocess`, `allow_network`, `allow_env`. Positional acceptance would let an argument reorder silently change which boundary is denied |
| `reset()` | Stable | |
| `shutdown()` | Stable | Added v4.0; clears last_vm, host functions, tools |
| `set_trace_id(id)` | Mostly Stable | Added v4.0 |
| `set_effect_store(store)` | Mostly Stable | Added v4.0 |
| `run_source()` result shape | Stable | `ok`, `stdout`, `stderr`, `error` keys |
| `run_file()` result shape | Stable | Consistent with run_source (ok=False for missing files, v4.0) |
| Event subscription API | Experimental | Not yet implemented |
| Module loading hooks | Experimental | Not yet implemented |
| `host_globals` parameter | Mostly Stable | |
| `initial_globals` parameter | Mostly Stable | |
| `nodus.tooling.loader.run_source()` | Internal | Low-level; no sandbox controls; prefer `NodusRuntime` |

### 3.1 Capability policy (`nodus.runtime.capability`)

Added in v5.0.0 (#405); this table added in v5.0.1, which is late — the surface
shipped a major release before it was indexed, and a downstream embedder scraped
our source for want of it.

| Surface | Tier | Notes |
|---------|------|-------|
| `SUBPROCESS`, `NETWORK`, `ENV`, `FS_READ`, `FS_WRITE` | Stable | Capability labels |
| `TOOL_INVOKE`, `SYSCALL`, `AGENT_CALL`, `MEMORY_READ`, `MEMORY_WRITE` | Stable | Added v5.3.0 (#473). Authority that is not a sandbox flag. Before these, a policy that denied everything could not see tool invocation, syscalls, agent dispatch or the memory store at all |
| `ALL_CAPABILITIES` | Stable | The closed set, as a frozenset. **Closed, not fixed** — it grew from 5 to 10 in v5.3.0. Membership changing is the list changing, not the contract; validate against it rather than against a copy |
| `NO_AUTHORITY_BUILTINS`, `NO_AUTHORITY_BUILTIN_NAMES` | Mostly Stable | Added v5.3.0. Every builtin that carries no authority, grouped by why. Exists so the classification is *total*: `BUILTIN_CAPABILITIES | NO_AUTHORITY_BUILTIN_NAMES == BUILTIN_NAMES` is pinned by test, so a new builtin cannot ship unclassified |
| `GATED_BUILTINS` | Mostly Stable | Added v5.0.1. Flag → `GatedBuiltinGroup(flag, capability, description, arity, names)`. The registry builds its refusing stubs from this, so the published list and the enforced gate cannot disagree. **Membership may change** as builtins are added — that is the list changing, not the contract |
| `GATED_BUILTIN_NAMES` | Mostly Stable | Added v5.0.1. All gated builtins, flattened |
| `BUILTIN_CAPABILITIES` | Mostly Stable | Which builtins consult the policy at call time. Distinct from `GATED_BUILTINS`; see the runbook §3.3.1 |
| `CapabilityRequest` fields | Mostly Stable | `capability`, `target`, `kind`, `args` |
| `CapabilityPolicy`, `DenyList`, `Floor` | Experimental | The three-valued cascade is stage 1–2 of the design; attenuation and layered rule sources are not implemented |
| `DEFAULT_FLOOR` | Mostly Stable | Unbypassable. Its one rule: a Nodus program cannot *write* into `.nodus/` |
| `inherit_authority()` | Experimental | |
| `capability_denied` event | Mostly Stable | Emitted at both chokepoints on refusal |
| Denial `error["kind"] == "sandbox"` | Stable | Classify on this |
| Denial message **naming the flag** | Stable | The flag name is contractual; the surrounding wording is not |

---

## 4. Bytecode format

| Surface | Tier | Notes |
|---------|------|-------|
| Opcode set (49 opcodes) | Stable | Frozen at v1.0 (2026-03-15) with 47; `MOD` and `RESET_LOCAL_IDX` added post-freeze — see [#366](https://github.com/Masterplanner25/Nodus/issues/366) |
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
| `nodus test` | Mostly Stable | Built-in test runner; added v4.0 |
| `nodus --version` | Stable | |
| `nodus init` | Stable | |
| `nodus install` | Mostly Stable | Package manager; registry auth added in v0.9 |
| `nodus publish` | Mostly Stable | |
| `nodus login` / `nodus logout` | Mostly Stable | |
| `nodus workflow` subcommands | Mostly Stable | `runs`, `inspect`, `dead-letters`, `replay`, `migrate-state`, `cleanup` |
| `nodus lsp` | Experimental | LSP server; hover, go-to-definition, completions |
| `nodus dap` | Experimental | DAP debug server; breakpoints, stepping, variable inspection, evaluate |
| `nodus dis` | Internal | Bytecode disassembler; output format not guaranteed |
| `nodus ast` | Internal | AST printer; output format not guaranteed |
| REPL inspection commands (`:ast`, `:dis`, `:type`) | Internal | REPL-only; output format not guaranteed |

---

## 7. Tooling servers (LSP, DAP) and companion tooling

| Surface | Tier | Notes |
|---------|------|-------|
| LSP server (`nodus lsp`) | Experimental | LSP 3.17; hover docs, go-to-definition, completions |
| DAP server (`nodus dap`) | Experimental | Breakpoints, stepping, variable inspection, evaluate (#106 closed v4.0.4) |
| Server mode (HTTP/FastAPI) | Experimental | Requires `nodus-lang[server]`; protocol not frozen |
| **nodus-vscode** extension | Experimental | VS Code Marketplace (`MasterplanInfiniteWeave`); v0.1.0 (2026-06-15) |
| **nodus-jupyter** kernel | Experimental | `pip install nodus-jupyter`; v0.1.0 (2026-06-15) |
| **nodus-mcp-server** | Experimental | Standalone MCP server; v0.1.0 on GitHub (2026-06-15) |

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
| Eval score (composite weighted, 21 dimensions) | Informational | v4.0.3: 6.3/10 (Stage 5 independent eval, 2026-06-13); not a stability guarantee |
| Coverage gate (≥70%) | Internal quality gate | Raised from 60% on 2026-05-31; not a public API commitment |
| Ruff lint gate | Internal quality gate | |
| Doc-vs-code gate (nodus_gate) | Internal quality gate | |

---

## 10. Graduation criteria for experimental surfaces

An experimental surface graduates to Mostly Stable or Stable when:

1. Two consecutive eval cycles show no regressions in that surface
2. The surface has test coverage ≥ 70% for its implementation
3. A design decision record exists and is not provisional
4. The surface has been in production use (embedded or CLI) without reported breakage

**Graduated in v4.0.5:** `spawn`/`coroutine`/`channel` and `workflow`/`goal`/`step`
completed all four criteria after the v4.0.3 and v4.0.4 eval cycles. The primary
remaining experimental surfaces are the v4.0 stdlib modules (`std:http`, `std:tool`,
`std:identity`, etc.) — these need one more eval cycle before graduation is considered.

---

## Related documents

- `docs/governance/STABILITY.md` — original stability summary (still valid; this doc supersedes it)
- `docs/governance/COMPATIBILITY_MODEL.md` — what breaks between versions
- `docs/governance/RELEASE_GATES.md` — release quality gates
- `docs/governance/VERSIONING.md` — versioning policy
- `docs/evals/` — eval reports that inform stability decisions
