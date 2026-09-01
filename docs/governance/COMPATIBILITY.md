# Nodus Compatibility & Deprecation Timeline

> **This document is a deprecation timeline record, not a compatibility policy.**
> For the compatibility policy (what counts as breaking, semver rules, bytecode
> compatibility, embedding API commitment), see:
> **`docs/governance/COMPATIBILITY_MODEL.md`**



Nodus keeps legacy compatibility for now, but the following items are deprecated and will be revisited in future releases.

## Deprecated (Still Supported)
- `.tl` legacy extension (CLI emits warnings on use).
- `tiny_vm_lang_functions.py` compatibility shim.
- `language.py` / `language.bat` legacy launchers (CLI emits warnings on use).
- **Undeclared workflow `state` written concurrently with a lost update**
  (#485). Two steps the graph does not order both writing one cell, where either
  read it before writing or they wrote different values, currently *warns* and
  keeps last-write-wins. **Scheduled to become an error in 6.0.0.** The warning
  names both fixes: declare `with { merge: "sum" }` / `"append"` to combine the
  writes, or `with { merge: "any" }` to keep last-write-wins deliberately.

  Concurrent writes that lose nothing — same value, neither branch reading first
  — are silent and are not affected.

## Timeline

- v0.9.x: continued support with warnings.
- **v1.0.0 (2026-03-15):** `compile_source()` loader body removed.
  Legacy launchers (`.tl`, `language.py`, `language.bat`) are still supported with
  warnings pending migration verification. Re-evaluation deferred to v1.1.x.
- **v2.1.0 (2026-05-24):** `json.parse` now returns maps (BREAKING from v2.0.0).
  Legacy `.tl` extension and `language.py` / `language.bat` launchers remain supported with warnings; no removal date set.
- **v2.1.1 (2026-05-24):** `allowed_paths` sandbox now enforced for `std:fs` module calls (security fix, BUG-046). No deprecation or compatibility impact — scripts relying on the bypass were relying on a bug.
- **v3.0.2 (2026-05-25):** `math.log_base` export removed; use `math.log(n, base)` instead. Patch release fixing BUG-V31E-01 (1I parse error) and BUG-V31E-02 (math.log argument order).
- **v4.0.0 (2026-06-04):** Major release. BYTECODE_VERSION 4. New opcodes, annotation syntax, compound assignment, multiline expressions, AI-native primitives, full security sandbox, coroutine scheduler, goals/workflows DSL. See CHANGELOG for full scope.
- **v4.0.1 (2026-06-10):** Patch release. `@exactly_once`/`@retry` decorators, `+=`/`-=`/`*=`/`/=` operators, multiline expressions, `std:math` bit ops, `allowed_commands`/`allowed_hosts` sandbox allowlists, `event_sinks`/`coroutine_timeout_ms`/`get_execution_stats` embedding API additions, `clear_shared_state()`, bounded channels. No bytecode break.
- **v4.0.2 (2026-06-10):** Patch release. Bug fixes: `@exactly_once` idempotency and nil-return (#207/#208), `allowed_commands` not enforced via module import (#209), `@retry` silent skip when dependency missing (#210), `event_sinks` callable support (#212). Trailing comma in list/call syntax (#211). No bytecode break.
- **v4.0.3 (2026-06-11):** Patch release. All 18 Sentinel evaluation bugs from v4.0.2 fixed (#214, #225–#242): tool.register re-execution storm, step-level retries under `nodus run`, state vars in string interpolation, per-iteration `let` bindings in `for` loops, `run_loop()` error reporting, tool JSON-Schema form, `time.format()` strftime tokens, `nodus test` Windows encoding, `nodus test` project-root resolution, and P3 API surface gaps across circuit-breaker, identity, memory, tool, effects, and workflow. Stdlib contract test suite added (87 tests, `NODUS_RUN_CONTRACTS=1`). No bytecode break.
- **v4.0.4 (2026-06-13):** Patch release. `identity.session_id()` nil in child VMs fixed (#254); retry stderr noise suppressed on eventual workflow success (#255). No bytecode break.
- **v4.0.5 (2026-06-15):** Stability graduation release. `spawn`/`coroutine`/`channel` and `workflow`/`goal`/`step` promoted to Mostly Stable; `yield` promoted to Stable. Companion tooling: nodus-vscode v0.1.0, nodus-jupyter v0.1.0, nodus-mcp-server, nodus-adapter-base. No bytecode break.
- **v4.0.6 (2026-06-20):** Patch release. `@retry` annotation no-op fixed (COMPILER-001, #267); spurious "spawned task never executed" warning fixed (WARN-001, #268); `nodus serve --help` and `nodus worker --help` now print usage instead of starting. No bytecode break.
- **v4.0.7 (2026-06-21):** Patch release. Cross-process workflow resume re-binds module imports (REHYDRATE-001, #285): a waiting workflow rehydrated in a fresh VM no longer runs with `tool`/`mem`/`json` unbound. No bytecode break.
- **v4.0.8 (2026-06-25):** Patch release. Stdlib async wrappers (`http.get_async`, `subprocess.run_async`) called from a scheduler coroutine now genuinely overlap instead of silently falling back to synchronous execution (ASYNC-MOD-001, #105). No bytecode break.
- **v4.1.0 (2026-07-10):** Minor release. New language features: `match` expression for value dispatch (#308) and `break`/`continue` loop control (#309). New `agent_call_async` / `agent.call_async` builtin so agent fan-out overlaps (#294). Fixes: workflow/goal `after` cycles rejected at build time (#323); resume no longer re-executes the workflow or clobbers the caller (#322, #328); async fan-out shares one HTTP client (#295). Doc-vs-code gate now runs in CI (#302). Backward-compatible; no bytecode break.
- **v4.1.1 (2026-08-05):** Patch release. A closure passed to a module function **inside a list, map, or record** was never wrapped in a `_ClosureProxy`, so it executed the caller's instruction address against the module's bytecode — `Stack underflow` under the CLI, a silent no-op under `NodusRuntime` (ASYNC-MOD-003, #339). This affected every `.nd` library taking callbacks in a container, not only the stdlib. `std:async.parallel` and `std:async.series` work as a result; `worker_pool` and `pipeline` remain broken and are documented as such (#339 stays open). CI now pins `ruff`, which was unpinned and began failing on untouched files when 0.16.1 changed its default rule selection. No bytecode break.
- **v4.2.0 (2026-08-15):** Minor release. Correctness: `finally` runs when `catch` re-throws (#361); `std:async` worker pools actually run their workers (#339); `--help` no longer executes the command it documents (#353/#345); the embedded runtime applies a call-depth cap by default (#350). Adds an opcode-freeze gate phase (#366) and DAP locals (#106). **Breaking for stderr consumers:** every error now reports a resolved absolute path (#342). No bytecode break. *(Entry added retroactively during the 5.0.0 cut — the 4.2.0 release did not update this file.)*
- **v5.0.0 (2026-08-17, current):** **Major release — breaking.** `NodusRuntime` denies `allow_subprocess`, `allow_network` and `allow_env` by default (#405); grant them explicitly. `nodus run` is unaffected. A Nodus program can no longer write into `.nodus/`. Adds a capability policy at both host chokepoints with per-call, argument-aware decisions, `capability_denied` events and an unbypassable floor (#405), and `goal … over …` — a goal that declares a stopping condition over a workflow (#409, Experimental). Fixes: step retries honoured on every entry point (#392); `goal`/`workflow` retry unified (#393); concurrent agent steps actually overlap (#398); cross-process resume works when the script reads the result (#399); derived VMs no longer shed the sandbox (#405); `nodus fmt` no longer writes files that stop parsing (#427). No bytecode break — BYTECODE_VERSION stays 4. Migration: `docs/migration/v5.0-deny-by-default.md`.

- **Unreleased:** The concurrent-write warning became precise (#485). It now
  fires only when an update was actually lost -- the writers disagreed, or one
  read the cell before writing it -- and is silent when concurrent branches wrote
  the same value without reading first. Not breaking: nothing that ran now fails,
  and a class of false-positive warnings stopped. The warning announces that the
  remaining case becomes an **error in 6.0.0**; see *Deprecated* above.

  `merge: "sum"` and `merge: "append"` also ship, so there is now a way to say
  "combine these" rather than only "I know they agree".

## Migration Path
- Use `.nd` files for new code.
- Use the `nodus` CLI (`nodus run`, `nodus check`, `nodus fmt`, `nodus repl`).
- Keep legacy `.tl` only for compatibility; the stdlib still ships `.tl` mirrors for now.
