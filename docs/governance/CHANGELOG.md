# Changelog

All notable changes to Nodus are documented here.

## [1.0.0] — 2026-03-15

**The Nodus opcode set is frozen. This is the first stable release.**

### Changed (Breaking — bytecode cache invalidated)
- `BYTECODE_VERSION` bumped from 3 to 4. All existing `.ndsc` cache files are
  automatically invalidated and recompiled on next load.

### Added
- **`finally` block support** — `try { } catch e { } finally { }` syntax. All three
  normal-path execution paths handled: try-success, caught exception, return-inside-try.
  - `FINALLY_END` opcode added (signals end of finally block; completes deferred returns).
  - `SETUP_TRY` extended to two operands: `SETUP_TRY handler_ip [finally_ip]`.
  - `POP_TRY` updated: redirects to `finally_ip` on normal try exit when non-zero.
  - `_deferred_return` mechanism in `_op_return` for deferred returns through finally.
  - Handler stack extended from 3-tuple to 4-tuple: `(handler_ip, finally_ip, stack_depth, frame_depth)`.
  - `FINALLY` keyword added to lexer; `TryCatch` AST extended with `finally_block` field.
  - Formatter, diagnostics, analyzer, LSP server, and workflow lowering updated.
  - 15 new tests in `tests/test_finally.py`.

### Changed
- **Opcode freeze declared** — all 47 active opcodes promoted to stable.
  Zero provisional opcodes. `SETUP_TRY`, `POP_TRY`, `FINALLY_END`, `THROW` promoted
  at freeze declaration. See `docs/governance/FREEZE_PROPOSAL.md`.

### Previous v1.0 changes (accumulated from v0.9.x):
- **Iterator protocol cleanup** — `GET_ITER`/`ITER_NEXT` use first-class `Iterator`
  objects. `pending_get_iter`/`pending_iter_next` VM flags removed. Both promoted to stable.
- **`_op_throw` structured values** — non-string thrown values preserved as `err.payload`
  with `err.kind="thrown"`. Strings become `err.message` directly.
- **`LOAD_LOCAL` removed** — opcode removed from VM dispatch table; `_op_load_local`
  replaced with `RuntimeError` tombstone. Three compiler fallback paths confirmed
  unreachable via audit; replaced with `assert` guards. `BYTECODE_VERSION` bumped 2→3.
- **`NodusRuntime` added to `nodus.__all__`** — `from nodus import NodusRuntime` works.
- **`compile_source()` fully removed** — function body removed from `nodus.tooling.loader`.
  Last test caller migrated to `ModuleLoader`.
- **Module system frozen** — `BUILD_MODULE` promoted to stable. Module system
  (live bindings, re-exports, circular detection) is feature-complete.

## [0.9.1] — 2026-03-15

### Fixed
- `test_task_reassignment_after_worker_failure` timing sensitivity: replaced
  the 2-second polling loop (`poll()` every 10ms) with a new
  `WorkerManager.wait_for_job()` method that blocks on the existing `_cond`
  condition variable. `submit()` already calls `_cond.notify_all()` on
  enqueue, so the wakeup is immediate with no race window. Test runtime
  reduced from up to 2s to ~20ms. Passes consistently under full-suite
  concurrency.

## [0.9.0] — 2026-03-15

### Removed
- `compile_source()` public re-export removed from `nodus.__init__`. The function body
  in `nodus.tooling.loader` is retained for internal tooling use and will be removed
  at v1.0. Callers should migrate to `NodusRuntime` or `ModuleLoader`.
  Note: The `DeprecationWarning` emitted in v0.8.0 said "will be removed in v1.0" —
  removal happened one version early at v0.9.0.

### Added
- **Registry authentication**: `RegistryClient` now accepts a `token` parameter and
  injects `Authorization: Bearer <token>` headers into all registry requests.
- `NODUS_REGISTRY_TOKEN` environment variable for registry token configuration.
- `--registry-token <token>` and `--registry <url>` CLI flags wired to `nodus install`.
- User-level config file `~/.nodus/config.toml` for persistent token storage.
  New module: `src/nodus/tooling/user_config.py` (`UserConfig` class).
- Three-tier token resolution: `--registry-token` flag > `NODUS_REGISTRY_TOKEN` env var
  > `~/.nodus/config.toml` > unauthenticated.
- `nodus login [--registry <url>]` — interactive token entry (via `getpass`), stored in
  `~/.nodus/config.toml`.
- `nodus logout [--registry <url>]` — removes stored token from `~/.nodus/config.toml`.
- **Registry publish**: `nodus publish [--registry <url>] [--registry-token <token>]`
  command.
- `create_package_archive(source_dir, output_path, name, version)` in
  `registry_client.py` — creates a `.tar.gz` archive excluding `.nodus/`,
  `__pycache__/`, `.git/`, `*.pyc`, `nodus.lock`. Returns SHA-256 hex digest.
- `RegistryClient.publish_package(name, version, archive_path, sha256)` — POST to
  `{registry_url}/packages/{name}/{version}` with `Authorization` and `X-SHA256`
  headers. Maps 409 Conflict to a clear `RegistryError`.
- Registry publish protocol documented in `docs/tooling/PACKAGE_MANAGER.md`
  (GET fetch + POST publish endpoints, request/response formats, error codes).
- 20 new tests: 11 auth/token tests + 9 publish/archive tests.

### Documentation
- `GET_ITER` / `ITER_NEXT` pending flag behavior (`pending_get_iter`,
  `pending_iter_next`) fully documented in `docs/runtime/INSTRUCTION_SEMANTICS.md`.
- `docs/governance/FREEZE_PROPOSAL.md` updated with v0.9 decisions for all 7
  provisional opcodes: `GET_ITER`, `ITER_NEXT`, `SETUP_TRY`, `POP_TRY`, `THROW`,
  `BUILD_MODULE`, `YIELD` all remain provisional; cleanup/finally/send-value all
  deferred to v1.0. Summary counts corrected from "9 provisional" to "7 provisional".
- Exception model decision: `finally` blocks deferred to v1.0; `SETUP_TRY`/`POP_TRY`/
  `THROW` remain provisional.
- `YIELD` send-value decision: formalization of send-value path deferred to v1.0.

### Known Issues
- `test_task_reassignment_after_worker_failure` (`tests/test_task_graph.py`) has
  pre-existing timing sensitivity. The test polls a background VM thread within a
  2-second window; under full-suite concurrency it occasionally misses the window.
  Passes consistently when run in isolation. Not caused by v0.9 changes. Tracked
  for fix in v0.9.x.

---

## [0.8.0] — 2026-03-15

### Added
- Registry-backed package resolution: `RegistryClient` with semver, SHA-256 verification, archive extraction.
- `compile_source()` internal callers migrated to `ModuleLoader`; 0 DeprecationWarnings from `src/`.
- `LOAD_LOCAL_IDX` / `STORE_LOCAL_IDX` / `FRAME_SIZE` opcodes: slot-indexed local variable access.
- All 48 AST node types covered in the formatter; `format_pattern()` helper added.
- Opcode freeze proposal published: `docs/governance/FREEZE_PROPOSAL.md` (39 stable / 7 provisional / 1 deprecated).
- Bytecode cache version bumped to 0x02. LSP version field updated to 0.8.0.

---

## [0.7.0] — 2026-03-15

### Added
- Incremental module compilation with persistent dependency graph (`.nodus/deps.json`).
- Disk bytecode cache: `marshal` + `NDSC` magic + SHA-256 integrity, replacing `pickle`.
- DAP debug adapter (`nodus dap`) and LSP server (completion, hover, go-to-definition, diagnostics).
- Workflow persistence snapshots, checkpoint files, and workflow management CLI commands.
- Scheduler fairness: round-robin execution with `TASK_STEP_BUDGET` enforcement.
- VM dispatch table (`_build_dispatch_table()`): replaced `if/elif` chain — ~33% throughput improvement.
- `LOAD_LOCAL` opcode for confirmed function-local variables — ~21% additional loop improvement.
- Bytecode cache hardened: `pickle` → `marshal` + NDSC magic + SHA-256 integrity check.
- Channel queues converted to `collections.deque` (O(1) pop).
- Builtin registry (`BuiltinRegistry`) extracted from VM into `src/nodus/builtins/`.
- `compile_source()` deprecated; `ModuleLoader` is the canonical pipeline.
- AST `Base` dataclass with explicit `_tok` / `_module` fields.
- `NodeVisitor` base class (`src/nodus/frontend/visitor.py`).
