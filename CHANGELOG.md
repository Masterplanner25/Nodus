# Changelog

## [Unreleased]

### Added

- **3D.2 — Equality coercion narrowing (Doc 11):** `==` now performs numeric-only
  coercion (int ↔ float) and rejects cross-family coercions. `0i == false` is
  `false` in v4.0 (was `true`). `1i == true`, `"" == false`, `"1" == 1i` are
  all `false`. Number-family coercion preserved: `1i == 1.0` is still `true`.
  `!=` updated for consistency. New builtins: `type_eq(a, b)` (strict same-type
  equality), `bool_equal(value, bool_value)`. New `std:bool` module exposing
  `bool.equal(x, bool_value)`. Breaking change for code relying on `0 == false`
  or `1 == true`.

- **3D.1 — type() naming reconciliation (Doc 10):** `type(1.0)` now returns
  `"float"` (was `"number"`). `type(42)` (unadorned literal) also returns
  `"float"`. `type(1i)` unchanged (`"int"`). New math helpers: `math.is_float(x)`,
  `math.is_numeric(x)` (joins existing `math.is_int`). Breaking change for code
  comparing `type(x) == "number"` — update to `math.is_float(x)` or `"float"`.

- **3C.4 — nodus_gate doc-vs-code reconciliation gate (Doc 12):** New
  `tools/nodus_gate/` Python tool implementing the three-phase verification gate.
  `python -m tools.nodus_gate.cli --static` verifies every `import "std:*"` and
  `nodus <cmd>` in docs exists in the codebase. `--runtime` executes all
  ` ```nodus ` and ` ```nodus-expect=output ` code blocks in documentation and
  verifies they run clean / produce expected output. `--closed-issues` parses
  `CHANGELOG.md [Unreleased]` for issue references, locates tests by file
  convention or `# closes: #N` marker, and runs them. `--all` runs all three.
  Supports `.nodusgate-allow` allowlist, `--verbose`/`--quiet`/`--format` flags.
  Mandatory pre-release step per the PLAYBOOK_MAJOR.md Phase 4 exit criterion.

- **3C.3 — std:test framework (Doc 07 + Doc 08):** New `std:test` namespace
  implementing a full pytest/jest-equivalent test framework. 11 assertions
  (`assert`, `assert_eq`, `assert_neq`, `assert_err`, `assert_ok`, `assert_kind`,
  `assert_throws`, `assert_close`, `assert_contains`, `assert_has_key`,
  `assert_in_range`). Suite/case API: `test.suite`, `test.case`, `test.case_async`,
  `test.skip`. Lifecycle hooks: `before_all`, `after_all`, `before_each`,
  `after_each`. Fixtures with test/suite scopes and `test.cleanup` teardown.
  Parameterized tests via `test.parameterize` (list and map row forms). Async
  tests with virtual clock: `test.advance_clock`, `test.flush_async`. Test
  isolation by default (env, cwd, tool registry reverted between tests).
  CLI: `nodus test [path] [--filter] [--format] [--coverage] [--bail]
  [--verbose] [--quiet]`. Output formats: pretty, plain, JSON, JUnit XML.
  Coverage: line-hit collection via event bus; JSON + HTML reports written
  to `./coverage/` with `--coverage` flag. Doc 08 coverage integration.

- **3C.2 — Tool registry library-side handlers (Doc 06):** New `std:tool`
  namespace for dynamic tool registration. `tool.register({name, handler,
  description, schema?, version?, tags?, deprecated?, metadata?})` — conflict
  on duplicate name returns err (`category: "registration_conflict"`). Schema
  supports simple flat map form (auto-normalized to JSON Schema) and full JSON
  Schema. `tool.unregister(name)`, `tool.invoke(name, args)`,
  `tool.lookup(name)`, `tool.list_tools(filter?)`, `tool.has(name)`. Deprecated
  tools emit a warning once per VM instance on first invocation.
  `NodusRuntime.tool_registry` property exposes a Python-side `ToolRegistry`
  wrapper with the same API; Python-registered tools persist across `run_source`
  calls and are pre-populated into each VM. Value translation (Nodus ↔ Python)
  for Python callable handlers. `threading.RLock` for concurrent host access.

- **3C.1 — String interpolation:** Swift-style `"\(expr)"` syntax for inline
  expression embedding in string literals. Lexer uses a character-by-character
  mode-stack (`_lex_string` / `_lex_interp`) replacing the prior regex-based
  string match; plain strings (no `\(`) still emit the classic `STR` token for
  full backward compatibility. Interpolated strings emit a token sequence:
  `STRING_START`, zero or more `STRING_LITERAL` / (`INTERP_START` expr-tokens
  `INTERP_END`) interleaved parts, `STRING_END`. Parser builds an
  `InterpolatedString(parts)` AST node where each part is `StringLiteralPart`
  or `InterpolationPart`. Compiler lowers to existing opcodes: each literal
  part becomes `PUSH_CONST`, each interpolated expression is compiled then
  coerced with `CALL str 1`; all parts are joined with N−1 `ADD` ops. No new
  bytecode opcodes (BYTECODE_VERSION stays at 4). Escape sequences (`\n`,
  `\t`, `\r`, `\0`, `\"`, `\\`, `\xHH`, `\uXXXX`) decoded inline in the lexer
  so they work correctly in both literal and interpolated segments. Literal
  `\(` is written `\\(` in source. Empty interpolations (`"\()"`) and format
  specifiers (`"\(x:.2f)"`) are parse errors with descriptive messages. Nesting
  depth capped at 32 levels. Formatter round-trips interpolated strings
  correctly. Analyzer treats `InterpolatedString` as `STRING` type. AST printer
  handles the new nodes. 39 new tests added (`tests/test_string_interpolation.py`).
  1227 total tests passing.

- **3B.5 — std:subprocess:** New `std:subprocess` namespace with 7 public
  functions: `run(argv, options?)`, `run_async(argv, options?)`,
  `shell(command, options?)`, `shell_async(command, options?)`,
  `spawn(argv, options?)`, `spawn_shell(command, options?)`,
  `shell_quote(string)`. `run`/`shell` block until process exit and
  return a result record (`stdout`, `stderr`, `exit_code`, `duration_ms`,
  `command`) or err record (`kind: "subprocess_error"`, five `category`
  values: `exit_code`, `timeout`, `signal`, `spawn_error`, `io_error`).
  `spawn`/`spawn_shell` return a process handle with `stdout`/`stderr`
  Channels (background-thread pumped, registered on root-VM scheduler's
  `_io_channels`), a `stdin` record with `send`/`close` BuiltinMethods,
  and lifecycle methods (`wait`, `wait_async`, `is_alive`, `terminate`,
  `kill`, `interrupt`, `signal`). Options: `output`, `stdout`, `stderr`
  (per-stream override including file-path redirect with `>>` prefix),
  `output_encoding` (`"utf-8"` or `"bytes"`), `stdin`, `env`/
  `env_inherit`/`env_passthrough` for environment merging, `cwd`,
  `timeout_ms`/`kill_grace_ms`, `check` (default true), `process_group`,
  `chunk_mode` (`"lines"` default or `"bytes"`) for spawn streams.
  `_async` variants are Phase 3B synchronous under the hood (true async
  bridging deferred to Phase 3C). `shell_quote` uses
  `subprocess.list2cmdline` on Windows and `shlex.quote` on Unix.
  No new dependencies (Python stdlib only). 48 new tests, 1186 total passing.

- **3B.4 — std:http:** New `std:http` namespace with 19 public functions:
  8 sync verbs (`get`, `post`, `put`, `delete`, `patch`, `head`, `options`,
  `request`), 8 `_async` counterparts (Phase 3B: synchronous at I/O level;
  parallelism via Nodus scheduler), `stream`, and `sse`. Buffered response
  records have `status`, `headers`, `body`, `url`, `method`, `ok`,
  `is_redirect`, `is_client_error`, `is_server_error` fields plus
  `json()`, `header(name)`, `headers_all(name)` method fields.
  Options: `json`, `form`, `text`, `bytes`, `multipart` body keys
  (mutually exclusive); `headers`, `query`, `auth_bearer`, `auth_basic`
  shortcuts; `timeout_ms`, `connect_timeout_ms`, `read_timeout_ms`;
  `follow_redirects`, `verify_tls`, `proxy`. Stream responses carry a
  `chunks` channel filled by a background thread; scheduler's new
  `_io_channels` list is polled by `run_loop` to wake blocked coroutines.
  SSE responses carry an `events` channel with parsed event dicts
  (`event`, `data`, `id`, `retry` fields). `r.as_sse()` converts a stream
  to an SSE channel. Err records use `kind: "http_error"` with six
  `category` values (`network`, `timeout`, `client_error`, `server_error`,
  `decode_error`, `redirect_error`). Requires `httpx>=0.27,<1` (already
  in `pyproject.toml`). Scheduler extended with `_io_channels` polling
  for thread-backed Channel wakeup.

- **3B.3 — std:hash, std:encoding, std:secrets:** Three new namespaces
  using Python stdlib only (no new dependencies).
  `std:hash`: 15 hash functions (5 algorithms × one-shot/builder/file),
  5 HMAC functions, constant-time `compare`. Hash records have `to_hex`,
  `to_hex_upper`, `to_base64`, `to_base64_url`, `to_bytes` method fields
  (via `BuiltinMethod`) plus `algorithm` and `length`. Builder pattern
  is single-use; reuse after `finalize` returns err
  (`kind: "state_error"`). `std:encoding`: base64 standard/URL-safe
  encode/decode, hex lower/upper encode, hex decode, URL RFC 3986
  percent-encode, URL form-encode/decode. `std:secrets`: `random_bytes`,
  `random_int` (rejection sampling), `token_hex/base64/urlsafe/
  alphanumeric`, `uuid_v4`, `uuid_v7` (RFC 9562 manual implementation).

- **3B.2 — std:time:** New `std:time` namespace with 7 datetime constructors
  (`now`, `now_in`, `at`, `from_epoch_ms`, `from_iso8601`, `from_http_date`,
  `parse`), 6 duration constructors plus `duration_between`, 12 calendar
  operations, chrono-style format engine, and serialization helpers
  (`to_iso8601`, `to_http_date`, `to_epoch_ms`). Datetimes store
  `epoch_ms + zone`; durations store `total_ms`. DST gap/fold detection
  with `on_invalid`/`on_ambiguous` options. Err records use
  `kind: "time_error"` with four categories. `datetime` and `duration`
  Records support comparison operators (`==`, `!=`, `<`, `>`, `<=`, `>=`).
  Requires `tzdata>=2024.1` (added to `pyproject.toml`).

- **3B.1 — std:env:** New `std:env` namespace with `get`, `set`, `unset`,
  `has`, `list`, `list_keys`. All values are strings; `env.get` accepts an
  optional default; `env.set` with an invalid name (contains `=` or null byte)
  returns an err record (`kind: "env_error"`, `category: "invalid_name"`).
  Modifications affect the current process only.

- **Doc 15:** Cyclic workflow dependency detection now returns an err record
  (`kind: "workflow_error"`, `origin: "stdlib"`) instead of a plain dict.
  The payload contains `category: "cyclic_workflow"`, `cycle` (ordered list
  of step names forming the cycle), and `workflow_name`. The DFS cycle
  detector extracts the actual cycle path; ambiguous "missing tasks" cases
  return `category: "missing_tasks"`. `run_workflow_code` runner translates
  err-record returns to `ok: false` for CLI/API consumers.

- **Doc 14:** `len()`, `count()`, `index_of()`, `last_index_of()`, and `range()`
  now return `int`. `math.floor()`, `math.ceil()`, and new `math.round()` return
  `int`. `index_of()` and `last_index_of()` return `nil` when not found (was
  `-1`). New top-level builtins `count`, `index_of`, `last_index_of`, `range`
  (1–3 args) added.

- **Doc 09:** Float division by zero now returns IEEE 754 `inf`/`nan` instead
  of throwing. `0.0 / 0.0` → `nan`; `1.0 / 0.0` → `inf`; `-1.0 / 0.0` →
  `-inf`. Float modulo by zero returns `nan`. Integer division or modulo by
  zero returns an err record (`kind: "math_error"`, `origin: "vm"`). New
  `math.is_nan(x)`, `math.is_inf(x)`, `math.is_finite(x)` functions and
  `math.nan`, `math.infinity`, `math.neg_infinity` constants added to
  `std:math`.

- **Doc 13 (#78):** All err records now carry five location fields: `path`,
  `line`, `column`, `stack`, and `origin`. Stdlib-returned errs are augmented
  in `call_builtin()` with `origin="stdlib"` and the call-site location.
  VM-thrown errs get `origin="vm"` via `build_runtime_error()`. User-thrown
  errs get `origin="user"` via `_op_throw()`.

### Breaking Changes

- **`type(float)` returns `"float"` not `"number"`** (Doc 10). Code checking
  `type(x) == "number"` will silently stop matching. Migrate: use
  `math.is_float(x)` or `type(x) == "float"`. Grep for `"number"` in type
  comparisons.

- **`==` no longer coerces across type families** (Doc 11). `0 == false`,
  `1 == true`, `"" == false`, `"1" == 1` are all `false` in v4.0. Number-family
  coercion (`1i == 1.0`) is preserved. Migrate: use `bool.equal(x, true/false)`,
  `type_eq(a, b)`, or explicit type-checked comparisons.

- **`index_of()` and `last_index_of()` return `nil` for not-found** (Doc 14,
  v4.0). Was `-1` in v3.x. Migrate: check `result == nil` instead of `== -1`.

- **Float division by zero returns `inf`/`nan`** instead of throwing (Doc 09).
  Code catching `RuntimeError: Division by zero` will silently get `inf`/`nan`.
  Migrate: use `math.is_nan(x)` or `math.is_inf(x)` to check results.

- **Cyclic workflow returns err record** instead of a plain dict (Doc 15).
  Migrate: check `type(result) == "error"` for cyclic workflow detection.

- **Err records now carry location fields** (`path`, `line`, `column`, `stack`,
  `origin`) in v4.0 (Doc 13). Code pattern-matching err record fields must
  allow for the new fields.

### Fixed

- **BUG-V31E-03 (#77):** `nodus workflow run --help` and `nodus graph run --help`
  now display help text instead of treating `--help` as a script filename and
  producing "File not found: --help".

## [3.0.2] - 2026-05-25

Patch release fixing two issues surfaced by the v3.0.1 independent stress-test
eval: a patch closure failure (BUG-V31E-01, #75) and a new HIGH bug introduced
by v3.0.1's `math.log` addition (BUG-V31E-02, #76).

### Fixed (undocumented in original release)

- `strings.split(x)` (wrong arity) now produces a Nodus-voice type error
  (`type error: split(x, delimiter) expects a string`) instead of leaking the
  internal "Stack underflow" message. This was an unintended side effect of
  the v3.0.2 work that was not captured in the original release notes.
  Identified by the v3.0.2 stress-test eval. The fix is real and shipped in
  the v3.0.2 wheel; this note is a retroactive disclosure.

### Fixed

- **BUG-V31E-01 (#75):** `1I` (uppercase integer suffix) now reliably produces
  a parse-time syntax error in all distribution artifacts. The lexer fix was
  committed in v3.0.1 but was absent from the v3.0.1 wheel due to a packaging
  gap (see `docs/governance/TECH_DEBT.md` § Patch closure verification gap).
- **BUG-V31E-02 (#76):** `math.log(value, base)` now correctly returns
  `log_base(value)`. The v3.0.1 implementation silently computed `ln(base)` and
  ignored `value` for all two-argument calls. The `log` and `log_base` wrappers
  in `std:math` have been unified into a single `fn log(n, base)` that passes
  `nil` for the base when called with one argument. The separate `log_base`
  export has been removed; callers should use `math.log(n, base)`.

## [3.0.1] - 2026-05-25

Patch release addressing 22 issues found during the v3.0.0 stress-test eval.
All issues filed as GitHub #53–#74 against the v3.0.1 milestone.

### Fixed

**Replace contract completeness (Commit 1)**

- **BUG-E01 (#53):** `json.parse` type-check now returns a `type_error` err
  record when the argument is not a string, instead of throwing a VM runtime
  error.
- **BUG-E02 (#54):** `math.sqrt(-1)` now returns a `value_error` err record
  instead of throwing. The Replace contract now covers all `std:math` domain
  errors.
- **BUG-E05 (#57):** `math.log(n)` and `math.log_base(n, base)` are now
  exposed in `std:math`. Previously `math_log` was wired as a builtin but
  never surfaced through the stdlib module.
- **BUG-E06 (#58):** `math.pow(base, exp)` is now exposed in `std:math`.
  Handles `OverflowError` and returns a `math_error` err record on overflow.
- **BUG-E07 (#59):** `fs.mkdir(path)` is now exposed in `std:fs`. Creates
  the directory; returns an `io_error` err record if the path already exists
  or is inaccessible.
- **BUG-E10 (#62):** `fs.delete(path)`, `path.relative(p, base)`, and
  `path.absolute(p)` are now exposed in `std:fs` and `std:path` respectively.
  All three are Replace-wrapped and return err records on failure.
- **BUG-E13 (#65):** The parser now accepts `catch (err)` with parentheses
  around the catch variable, in addition to the existing `catch err` form.

**Embedding API (Commit 2)**

- **BUG-E03 (#55):** `NodusRuntime.run_source(host_globals=...)` now correctly
  forwards `host_globals` to the `ModuleLoader`, so named variables injected
  from the host are accessible in Nodus scripts.
- **BUG-E04 (#56):** Python exceptions raised by host-registered functions
  (via `NodusRuntime.register_function`) now propagate to the Python caller
  as the original exception type. Previously they were silently absorbed by
  the VM's `except Exception` handler and converted to `LangRuntimeError`.
  A new `HostFunctionError` sentinel in `nodus.runtime.diagnostics` bypasses
  the VM wrapper.

**Documentation reconciliation (Commit 3)**

- **BUG-E08 (#60):** `docs/policy/error-surfaces.md` now documents that sandbox
  validation fires before stdlib error wrapping. Includes a code example showing
  that absolute paths produce sandbox errors, not `io_error` records.
- **BUG-E09 (#61):** `docs/policy/error-surfaces.md` §5 trace-errors example
  output updated to match the actual `print_trace()` format emitted at runtime.
- **BUG-E19 (#71):** `docs/migration/v2-to-v3.md` now includes an explicit
  breaking-change callout that `has_key(err, key)` **crashes** in v3.0 (throws
  a runtime type error) rather than silently returning a wrong value. Includes
  the error message, an audit call-to-action, and replacement patterns.
- **BUG-E20 (#72):** CHANGELOG v3.0.0 `path.join` entry corrected — removed
  the incorrect claim "in addition to the variadic form". The function accepts
  a single list argument only.

**Polish, deprecations, and design capture (Commit 4)**

- **BUG-E11 (#63):** The lexer now emits `"Identifiers must use ASCII letters
  only: '<char>'"` when a non-ASCII alphabetic character appears at identifier
  position, instead of the generic `"Unexpected character"` message.
- **BUG-E12 (#64):** `1I`, `42I`, and similar integer literals with an
  uppercase `I` suffix now produce a parse error (`"Integer suffix must be
  lowercase 'i'"`) instead of silently splitting into a number and a name that
  later causes a confusing runtime name-lookup failure.
- **BUG-E16 (#68):** Import error messages no longer double the `.nd` extension.
  `import "logparse.nd"` that fails now shows `"logparse.nd"` in the tried
  paths, not `"logparse.nd.nd"`. Fixed in both the local resolution path and
  the stdlib fallback path.

### Changed

- **BUG-E14 (#66):** `nodus.tooling.loader.run_source()` now emits
  `DeprecationWarning` on every call, directing callers to
  `NodusRuntime.run_source()` from `nodus.runtime.embedding`. Planned removal
  in v4.0. See `docs/governance/DEPRECATIONS.md`.

### Documentation

- **BUG-E15 (#67):** `docs/guide/standard-library.md` now notes that `len()`
  returns a float (e.g., `3.0`) in v3.x. Changing to `int` is a v3.1 design
  candidate; see `docs/governance/V3_1_PLAN.md §1`.
- **BUG-E17 (#69):** `docs/guide/standard-library.md` now notes the `type()`
  naming asymmetry (`"number"` for floats, `"int"` for integers). Renaming
  `"number"` to `"float"` is a v3.1 design candidate; see
  `docs/governance/V3_1_PLAN.md §2`.
- **BUG-E21 (#73):** `docs/guide/standard-library.md` now documents that
  `print(42i)` displays `42` (not `42i`). The `i` suffix is source syntax only;
  it is not part of the runtime string representation.
- **BUG-E22 (#74):** `docs/guide/standard-library.md` now notes that
  `json.stringify` accepts `int` values natively (e.g., `42i` serializes as
  `42` in JSON output).
- `docs/governance/V3_1_PLAN.md` created — captures deferred design items
  (BUG-E15, BUG-E17, the `finally`/`catch`-return bug) as v3.1 candidates
  with rationale and proposed resolution options.
- `docs/governance/DEPRECATIONS.md` updated with the `run_source()` entry.

## [3.0.0] - 2026-05-25

### Breaking changes

**v2.1.1 is the last v2.x release.** v3.0 folds the v2.2 bug-fix milestone
and all breaking language changes into a single release. Migration guide:
`docs/migration/v2-to-v3.md`.

- **`{foo: bar}` is now a record literal, not a map lookup.** In v2.x, bare
  (unquoted) identifier keys in a map literal context were evaluated as variable
  lookups. In v3.0, `{ host: "localhost" }` is a **record literal** — `host`
  is a field name, not a variable. To use a variable's value as a map key, wrap
  it in parentheses: `{ (mykey): value }`. To create a map with a literal string
  key, quote it: `{ "host": "localhost" }`.

- **Bare identifier as map key is now a parse error.** Using a bare identifier
  as a map key (e.g. `{ host: ... }` in a map context) was a silent runtime error
  in v2.x. In v3.0 it is a parse error with a helpful message naming the two
  correct forms.

- **`fs.*` and `json.*` errors are returned, not thrown.** `fs.read`, `fs.write`,
  `json.parse`, and similar stdlib functions now **return** an err record when
  they fail. They no longer throw a runtime error. `try/catch` still works for
  VM-level errors; returned err records are the preferred pattern for expected
  I/O and parse failures. Check with `type(result) == "error"`.

- **New err.kind values for stdlib failures.** Code that branched on
  `err.kind == "runtime"` to catch file or JSON errors will no longer match.
  The specific kinds are:

  | v2.x kind | v3.0 kind | What changed |
  |-----------|-----------|--------------|
  | `"runtime"` | `"io_error"` | `fs.read`, `fs.write`, `fs.listdir`, etc. |
  | `"runtime"` | `"parse_error"` | `json.parse` failures, `math.parse_int` failures |
  | `"runtime"` | `"type_error"` | `json.stringify` with non-serializable value, `math.idiv` with float args |
  | `"runtime"` | `"math_error"` | `math.idiv` division by zero |
  | (new) | `"value_error"` | Domain errors in math functions (`math.sqrt(-1)`) |
  | (new) | `"internal_error"` | Unexpected internal error in a wrapped stdlib function |

- **`err.payload` is always present.** In v2.x, `err.payload` was absent on
  runtime errors and string throws — accessing it raised `"Key error: Missing
  record field: payload"`. In v3.0, `err.payload` is always present and is `nil`
  for runtime errors and string throws. Existing guards (`has_key(err, "payload")`)
  are still safe; they return true where they previously returned false.

- **Integer type: `42i` literals, `type()` returns `"int"`.** v3.0 introduces
  the `int` type. Integer literals use the `i` suffix (`42i`, `0i`, `-1i`). Plain
  number literals (`42`) remain floats. `type(42i)` returns `"int"`; `type(42)`
  still returns `"number"`. Integer arithmetic (`int + int`) returns `int`;
  integer division always returns float. Code that checks `type(x) == "number"`
  for values that may now be integers should also check `type(x) == "int"`.

### Added

- **Integer type** (`42i` syntax, `"int"` type). New integer stdlib functions in
  `std:math`: `math.parse_int(s)`, `math.to_int(n)`, `math.to_float(n)`,
  `math.is_int(v)`, `math.idiv(a, b)`. Large integers maintain exact precision.
  Booleans continue to coerce to float in arithmetic.
- **`--trace-errors` CLI flag and `NODUS_TRACE_ERRORS=1` env var.** When set,
  prints the original Python exception to stderr whenever a stdlib function
  converts a Python exception to an err record. Script behavior is unchanged —
  `err.message` always contains only Nodus-voice text.
- **`docs/policy/error-surfaces.md`** — new policy doc describing the Replace
  contract, which stdlib surfaces are wrapped, and how to use `--trace-errors`.
- **`docs/migration/v2-to-v3.md`** — migration guide for all six breaking changes,
  "What does NOT break" section, and list of non-breaking v2.2 improvements.

### Fixed (v2.2 backlog, folded into v3.0)

- **`finally` now runs correctly in all cases** except the one known case where
  `catch` has a `return` (tracked as a v3.1 bug). Previously, `finally` was
  silently skipped in several exit paths.
- **Import errors inside function bodies and `if/else` blocks now work
  correctly.** Previously, a failed import inside a function body or `if/else`
  branch silently left the module name undefined instead of propagating the error.
- **Imports inside function bodies and `if`/`else` blocks now work correctly** —
  the module is loaded and the alias is defined in the enclosing scope, matching
  expected behavior. Note: import errors inside `try/catch` are still not catchable
  (the alias is left undefined and accessing it raises a `"name"` error); this
  is a known v3.1 bug, documented in error-handling.md §6.
- **`strings.is_blank` correctly returns `true` for whitespace-only strings.**
  Previously returned `false` for strings containing only spaces, tabs, or newlines.
- **`path.join` accepts a list of path segments.** `path.join(["a", "b", "c"])`
  joins a list of strings into a path. The function takes a single list argument,
  not variadic arguments.
- **`path.ext` now returns the leading dot.** `path.ext("file.nd")` returns
  `".nd"` (previously returned `"nd"`).
- **`utils.get(map, key, default)` added** — new function for safe map access
  with a default value when the key is absent.
- **Multi-line map literals work.** The value of a map entry can now start on
  the line after the `:` without a parse error.
- **`err.line`, `err.column`, `err.path`, `err.stack` are now documented fields.**
  These fields were always present but undocumented. `err.line` and `err.column`
  are `int` values in v3.0.
- **`type()` and `rt.typeof()` are now consistent and documented.** Previously
  the two functions returned different strings for the same value in some cases.
  `rt.typeof()` returns the runtime type name; `type()` returns the user-facing
  type name. See `docs/guide/types-and-values.md` for the complete comparison table.
- **`collections.has_key` O(n) shadow fixed.** The stdlib `has_key` function
  in `std:collections` was inadvertently shadowing the O(1) builtin `has_key`
  with an O(n) implementation.
- **`coalesce` now evaluates arguments lazily.** Previously `coalesce(a, b)`
  evaluated `b` even when `a` was non-nil.
- **Cyclic workflow dependency now errors correctly.** Previously, a workflow
  with a cyclic step dependency produced exit code 0 silently.
- **Stack overflow trace truncated.** Previously, a call stack overflow would
  print all 10,000 frames to stderr. Now truncated to a readable summary.
- **`nodus debug --help` no longer outputs "File not found".**
- **`nodus fmt --check` false-negative on fresh files fixed.**
- **`else if` is now valid syntax.** Previously required `else { if ... }` nesting.

### Documentation

- `docs/guide/types-and-values.md` — complete rewrite for v3.0: integer type
  section, `42i` syntax, arithmetic semantics, integer stdlib table, `{key: value}`
  disambiguation (record vs map), updated falsy values list, equality coercion
  documented as stable behavior.
- `docs/guide/error-handling.md` — major update: new stdlib err.kind table,
  err.payload always present, returned-not-thrown pattern documented, Section 5
  rewritten with guidance on try/catch vs. err-record checks, `--trace-errors`
  usage in Section 7.
- `docs/guide/standard-library.md` — v3.0 update: integer type additions,
  `json.parse_int`, updated fs error docs, rt.typeof comparison table corrected.

## [2.1.1] - 2026-05-24

### Security
- **BUG-046 — `allowed_paths` sandbox bypassed via `std:fs` module calls (CRITICAL):** `fs.read`, `fs.write`, `fs.append`, `fs.exists`, `fs.listdir`, and `fs.ensure_dir` now correctly enforce `NodusRuntime(allowed_paths=...)` restrictions. Previously, `NodusModule.invoke_function` created a new internal VM without forwarding `allowed_paths` or `fs_root` from the calling VM, allowing any embedded script to read or write arbitrary files by routing calls through the `std:fs` module. Direct builtin calls (`read_file`, `write_file`, etc.) were correctly sandboxed; stdlib wrappers were not. Also fixes the same bypass in CLI mode when `fs_root` enforcement is active. Path traversal via `std:fs` is now also blocked.

## [2.1.0] - 2026-05-24

### Added
- **BUG-020 — `has_key(map, key)` builtin:** New top-level builtin for O(1) map membership testing. No import required. Raises a `type` error when called on non-map values.
- **BUG-010 — Modulo operator `%`:** Integer and floating-point modulo now supported as a first-class arithmetic operator.
- **BUG-011 — Scientific notation literals:** Numeric literals in scientific notation (`1e3`, `2.5e-4`, `1E10`) are now parsed correctly by the lexer.
- **BUG-019 — `strings.replace(s, old, new)` / `str_replace` builtin:** New string replacement function available via `import "std:strings"` and as a raw builtin.

### Fixed
- **BUG-015 — Stdlib errors report user call site:** Runtime errors originating inside stdlib modules (e.g. `fs.read`, `math.sqrt`) now report the user's call site (file and line) instead of the internal stdlib file path. Implemented via `_is_stdlib_path()` helper and `_caller_vm` fallback in `build_runtime_error()`.
- **BUG-005 — `NodusRuntime.run_source` no longer raises on error:** The embedding API now catches all runtime and syntax errors and returns `{"ok": false, ...}` instead of propagating exceptions to the caller.
- **BUG-018 — `json.parse` returns maps, not records:** `json.parse` (and `json_parse` builtin) now returns plain maps, enabling `obj["key"]`, `keys(obj)`, `values(obj)`, and `has_key(obj, "key")`. Previously returned Record objects, which only supported dot notation.
- **BUG-022 — `print()` inside workflow/goal steps now visible:** Output from `print()` calls inside workflow and goal step functions is now captured and shown in CLI output.
- **BUG-027 — `throw` kind is `"thrown"` not `"runtime"`:** Throwing a string or primitive value (`throw "msg"`) now sets `err.kind = "thrown"`. Previously all throws reported `"runtime"`.
- **BUG-026 — `while` without parentheses gives helpful hint:** `while true { }` (missing parentheses) now produces: `while condition must be in parentheses: while (condition) { ... }` instead of a generic parse error.
- **BUG-008 — Unclosed string literal error message:** An unterminated string literal now reports `Unterminated string literal` instead of the misleading `Unexpected character`.
- **BUG-009 — Parser errors use ASCII hyphens:** Error messages in the parser used Unicode em-dashes (`—`). Replaced with ASCII hyphens (`-`) for terminal compatibility.
- **BUG-024 — `nodus init` prints success message:** `nodus init` now prints `Initialized Nodus project at <path>/` instead of silently succeeding.
- **BUG-028 — `--trace-no-loc` trailing whitespace removed:** Opcode lines emitted with `--trace-no-loc` no longer include trailing spaces when no context string is present.
- **BUG-001 / BUG-002 — `nodus check` / `nodus ast` / `nodus dis` `--help` handling:** `--help` after a subcommand is now handled correctly instead of being treated as a filename. `nodus check` now prints `OK` on success.
- **BUG-003 — `nodus check` help text accuracy:** Help text now correctly describes check as parse-only validation (does not detect undefined variable/function references).
- **BUG-023 — Unicode arrow in `NodusRuntime` docstring:** Replaced `→` with `->` in `embedding.py` docstrings, preventing `UnicodeEncodeError` on Windows CP1252 terminals.

### Documentation
- **BUG-014 — `foreach` removed from docs:** `foreach` does not exist in Nodus. All references in `LANGUAGE_VISION.md` and `docs/onboarding/NODUS.md` updated to `for item in list`.
- **BUG-021 — REPL.md lists `:modules` and `:reload`:** REPL command reference now matches the actual help text output by `nodus repl`.

## [2.0.1] - 2026-05-23

### Security
- **BUG-016 — path traversal in `fs.*` builtins (CRITICAL):** `read_file`, `write_file`, `append_file`, `mkdir`, `list_dir`, and `exists` now enforce a filesystem root in CLI mode. When no `allowed_paths` sandbox is active, scripts are restricted to the process working directory (or the `nodus.toml` project root when one is discovered). Paths that resolve outside this root raise a `sandbox` runtime error. Previously, any script could read or write arbitrary files on the host machine regardless of where `nodus run` was invoked.

### Fixed
- **BUG-017 — Python traceback on UTF-8 BOM files (CRITICAL):** Source files that begin with a UTF-8 BOM (`\xef\xbb\xbf`) — commonly produced by Windows editors — previously caused a raw Python `SyntaxError` or `UnicodeDecodeError` crash rather than a clean Nodus error. All file-read paths (`cli.py`, `module_loader.py`, `embedding.py`, `builtins/io.py`) now open files with `encoding="utf-8-sig"`, which transparently strips the BOM before parsing. `read_file()` also strips BOMs from data files read at runtime.
- **BUG-007 — `RecursionError` on 100+ nested parentheses (CRITICAL):** Deeply nested expressions (e.g. `((((…))))` with 100+ levels) caused Python's recursion limit to be exceeded, surfacing as an unhandled `RecursionError` traceback. The parser now tracks expression nesting depth and raises a `LangSyntaxError("Expression too deeply nested")` at depth 50, well before Python's stack limit is reached.

### Changed
- **PyPI classifier downgrade:** `Development Status :: 5 - Production/Stable` → `Development Status :: 4 - Beta`. The v2.0.0 stress-test evaluation revealed three CRITICAL bugs that disqualify a Production/Stable rating.

## [2.0.0] - 2026-05-23

### Fixed
- **CI lint regression (Phase 5A):** Two ruff errors introduced in Phase 6 test additions (commit `0568185`) caused the `ruff check .` CI gate to exit 1. Fixed `tests/test_run_trace.py:64` (E741: renamed ambiguous loop variable `l` -> `line`) and `tests/test_workflow_unification.py:56` (F841: removed unused `exit_code` assignment from `test_workflow_no_args_shows_usage`). `ruff check .` now exits 0.
- **`--trace-imports` Windows encoding crash (Phase 5B):** `src/nodus/runtime/module_loader.py` used the Unicode arrow `→` (U+2192) in the `[import] Resolved` output line and an em dash `—` (U+2014) in the `[import] Failed` line. Both characters are non-ASCII; the arrow is not encodable in Windows CP1252, causing `UnicodeEncodeError` when `--trace-imports` wrote to a CP1252 terminal. Replaced `→` with `->` and `—` with `--` (ASCII equivalents). Existing tests were unaffected because they redirect stderr to `io.StringIO()`.
- **CHANGELOG.md E402 count discrepancy (Phase 5B):** Corrected the E402 fix count in the Refactoring section from 8 to 11. The actual count resolved in commit `b9e6418` was 11, matching the git commit message and AUDIT_REPORT_2.md baseline.
- **TECH_DEBT.md vm.py line count stale (Phase 5B):** Updated from "2,418 lines as of v1.1.2" to "2,438 lines as of v1.1.2 (post-Phase 6)" to reflect the +20 lines added for `builtin_memory_has` in Phase 6.

### Documentation
- **README.md: JSON-LD structured metadata (Phase 5C):** Added a `<script type="application/ld+json">` block at the end of `README.md` with `schema.org/SoftwareApplication` metadata (name, description, author, category, language, OS, URLs, license, version, Python requirement). Improves discoverability by AI indexers and search engines.
- **LANGUAGE_SPEC.md: `--strict` flag and `nodus status` added (Phase 5B):** Added a "Run mode flags" entry documenting `--strict` (disables project auto-discovery, requires explicit file path) and `--trace-imports` (ASCII format). Added `nodus status` to the CLI commands section describing its three-field output and always-zero exit behavior.

### Added
- **AUTHORS file (Phase 5C):** Added `AUTHORS` at the project root listing Shawn Knight as the sole author with a GitHub profile link. Standard file for PyPI/GitHub attribution.
- **Cross-platform documentation (Task 7.2):** Audited `CONTRIBUTING.md` and `docs/onboarding/DEVELOPMENT.md` for shell commands that differ between bash and PowerShell. All three bash-only constructs in `CONTRIBUTING.md` now have adjacent PowerShell equivalents: `source .venv/bin/activate` ↔ `.venv\Scripts\Activate.ps1` (pre-existing), `pip install dist/*.whl` ↔ `pip install (Get-Item dist\*.whl).FullName` (added by Task 7.1), and `NODUS_RUN_DIST_SMOKE=1 python -m pytest ...` ↔ `$env:NODUS_RUN_DIST_SMOKE = "1"; python -m pytest ...` (added by Task 7.1). `DEVELOPMENT.md` contains no platform-diverging shell commands (all invocations use `nodus <tool> file.nd` or `python` forms that are identical across platforms); no changes required.
- **CI distribution validation (Task 7.1):** CI pipeline now has an explicit `Build wheel` step (`python -m build --wheel`) that runs after `Install build tooling` and before the smoke test, making the wheel build visible as its own CI step. The `Installed wheel smoke test` step was already gated by `NODUS_RUN_DIST_SMOKE: "1"` and creates an isolated venv for clean-install verification. Added `nodus --help` smoke check to `tests/test_distribution_smoke.py` (verifies exit 0 and "Usage" in stdout). Updated `_build_wheel` to reuse a pre-built wheel from `dist/` when available (avoids a redundant second build in CI). `CONTRIBUTING.md` updated with a new "Distribution Testing" section documenting the wheel build and smoke-test commands.
- **Execution trace format update (Task 6.2):** `nodus run --trace` now writes opcode trace lines to **stderr** (previously stdout) with the format `[trace] <OPCODE padded to 14 chars>  line N  <context>`. Opcode-specific context: `CALL` shows `fn=<name>`, `LOAD`/`STORE` show `name=<var>`, `LOAD_FIELD`/`STORE_FIELD` show `field=<name>`, `PUSH_CONST` shows `val=<repr>`, `JUMP` shows `target=<ip>`. `--trace-no-loc` omits the `line N` field. Existing `--trace-filter` and `--trace-limit` flags are unchanged. Three existing tests in `tests/test_nodus.py` updated to capture stderr; 6 new tests added in `tests/test_run_trace.py`. `_COMMAND_HELP["run"]` updated to note high-volume stderr output.
- **Memory API stabilization (Task 6.1):** Added `memory_has(key)` top-level builtin and `has(key)` method to `std:memory`. The previous `has` implementation incorrectly used `value != nil` and returned `false` when `nil` was stored under a key; it now calls `memory_has` which checks key existence directly. `memory_has` is registered in `BUILTIN_NAMES`, the VM builtin dispatch, and `memory_runtime.py`. All four stable methods (`put`, `get`, `delete`, `has`) and their top-level counterparts are now fully tested. Non-string keys raise a runtime `TypeError` across all methods. `LANGUAGE_SPEC.md` updated with a dedicated Memory API section. Tests added in `tests/test_memory_api.py` (19 tests).
- **Path traversal error message improvement (Task 5.1):** The error raised when a relative import would escape the project root now names the offending path: `Invalid import: path '../outside.nd' escapes the project root.` Previously the message did not include the path. The check continues to fire before any filesystem access, in both project mode (explicit `nodus.toml`) and single-file mode (no manifest, root defaults to entry file's directory). Tests added in `tests/test_path_traversal.py` (6 tests covering: project-mode rejection, error message names the path, in-tree relative import accepted, double-dot chain blocked, single-file-mode rejection, single-file in-tree accepted). `LANGUAGE_SPEC.md` and `docs/governance/TECH_DEBT.md` updated.
- **REPL import parity verified and tested (Task 5.2):** The REPL uses the same `ModuleLoader` and `resolve_import_path` code path as CLI execution. Automated tests in `tests/test_repl_import_parity.py` confirm: (1) bare project-root-relative imports resolve from project root in the REPL, (2) path traversal (`../outside.nd`) is blocked in the REPL with the same error as CLI, (3) `lib/index.nd` fallback resolution works in the REPL. No separate REPL import code path exists or was introduced.
- **CLI help system (Task 1.1):** Every primary subcommand now has a per-command `--help` that shows usage, a one-sentence description, all options with descriptions, and at least two examples. Commands covered: `run`, `repl`, `init`, `check`, `fmt`. Implemented via a `_COMMAND_HELP` dict in `src/nodus/cli/cli.py`; `--help` after a command no longer falls through to the global help.
- **Execution transparency (Task 1.3):** `nodus run` now prints two lines to stderr when auto-discovering a project (no file argument, or a directory argument): `Running project from: <absolute path>` and `Entry: <relative path>`. Single-file invocations (`nodus run script.nd`) are unchanged. Tests added in `tests/test_project_run_header.py`.
- **Project-root-relative imports (Task 3.1):** Bare import paths (no leading `./`) resolve against the project root first, then `.nodus/modules/`, then stdlib. When all fail, the error message now names all paths tried including stdlib candidates. Tests added in `tests/test_bare_imports.py`.
- **Index module support (Task 3.2):** When a bare or relative import path has no extension and no exact file match, Nodus now checks `<path>/index.nd` and `<path>/index.tl` as fallbacks. Resolution order: `path.nd` → `path.tl` → `path/index.nd` → `path/index.tl`. Tests added in `tests/test_bare_imports.py`.
- **`nodus run --trace-imports` flag (Task 3.3):** When set, prints one `[import] Resolved "path" → /abs/path` line to stderr for each import resolved at module-load time. Failed imports print `[import] Failed "path" — <reason>` before the error is raised. No effect on execution behavior. Tests added in `tests/test_trace_imports.py`.
- **Strict run mode (Task 2.2):** `nodus run --strict` disables project auto-discovery and requires an explicit file path. Without a file argument it prints `Error: --strict mode requires an explicit file path.` and exits non-zero. The flag is documented in `nodus run --help`. Tests added in `tests/test_strict_mode.py`.
- **`nodus status` command (Task 2.3):** New command that reports the project root, entry file, and working directory that would be used if `nodus run` were called from the current directory. Prints `No project found in current directory` when no `nodus.toml` is reachable; always exits 0. Appears in `nodus --help`. Help text available via `nodus status --help`. Tests added in `tests/test_status_command.py`.
- **Context-aware REPL prompt (Task 4.2):** `run_repl()` now calls `load_project_from(os.getcwd())` at startup. When a project is found the prompt becomes `nodus (<name>)> `; without a project it shows `nodus> `. The `ModuleLoader` is also initialised with the project root rather than raw cwd when a project is detected, so bare imports resolve correctly inside the REPL.
- **REPL error deduplication verified (Task 4.3):** Investigation confirmed the REPL prints exactly one error message per failed user action; `_execute_source` raises exceptions rather than printing them, and the `run_repl` loop prints exactly once via `format_error`. Two regression tests added to `tests/test_repl_commands.py` (`ReplErrorDeduplicationTests`) to lock this behaviour in place.
- **REPL `:modules` and `:reload` commands (Task 4.1):** `:modules` lists all modules imported in the current REPL session (paths from `import_state["loaded"]`), or prints `No modules imported.` when the session is clean. `:reload` clears session state and recreates the VM and loader, then prints `REPL session restarted.`. Unknown colon-commands now print `Unknown REPL command ':xyz'. Type :help for available commands.` instead of raising an exception. `:help` output updated to include all seven commands. `execute_repl_command` return type extended to a 4-tuple `(handled, output, should_exit, should_reload)`. Tests updated in `tests/test_repl_commands.py`; 5 new tests added.
- `llms.txt` at project root: machine-readable AI crawler index with project name, tagline, creator attribution, key concept definitions, and links to 8 key documents.

### Changed
- **CLI command visibility (Task 1.2):** `nodus --help` now shows `nodus init` instead of the internal `package-init` alias. `login`, `logout`, and `publish` added to the known-commands dispatch table (they were listed in help but silently failed at runtime). `nodus --help` now requires `--help` to be the first argument; `--help` after a command routes to per-command help.
- **Parser error messages (Task 1.4):** Parser errors no longer expose raw token kind names (`ID`, `COLON`, `RBRACE`, etc.). All error messages in `eat()`, `parse_pattern()`, and `parse_primary()` now use human-readable terms: `identifier` for `ID`, `end of file` for `EOF`, `end of statement` for `SEP`, `'{'`/`'}'` for brace tokens, etc. Context-specific hints added for `Unexpected '}'` and `Unexpected end of file` in expression position.

### Changed
- `pyproject.toml` `[server]` optional extras now pin `fastapi>=0.136.0,<1` and `uvicorn>=0.30.0,<1`; lower bound raised to the tested 0.136 series after a clean upgrade from 0.111.0.
- CI: `permissions: contents` downgraded from `write` to `read`; the job no longer requires write access now that the auto-format commit step has been removed.
- `pyproject.toml` `filterwarnings`: removed `ignore::PendingDeprecationWarning:starlette` suppression — starlette 1.0.1 no longer emits the python_multipart `PendingDeprecationWarning`.

### Security
- Updated `certifi` 2026.2.25 → 2026.5.20 (security certificate bundle; pinned in `requirements.txt`).
- Updated `idna` 3.11 → 3.16 (IDNA protocol library; pinned in `requirements.txt`).
- Updated `fastapi` 0.111.0 → 0.136.1 and `starlette` 0.37.2 → 1.0.1; both pinned in `requirements.txt`. The `services/server.py` FastAPI code (`FastAPI()`, `@app.middleware("http")`, `@app.get/post/delete` decorators, `Request`, `JSONResponse`, `request.json()`) is compatible with starlette 1.0 — no `on_startup`/`on_shutdown`, no bare `@app.route()`, no removed Starlette-level decorators are used. All 413 pytest tests pass against the upgraded versions.

### Fixed
- CI: `test_formatter_foreach.py` was silently excluded from the CI `unittest` runner. Added a `Pytest` step (`python -m pytest -q`) so pytest-style tests are covered.
- CI: Auto-format step that committed `.nd` changes directly to the branch on every push has been removed. Format enforcement is now check-only via the existing `nodus fmt --check` step.
- `nodus.py` shim: `main` was referenced in the `__main__` block without an explicit import (ruff F821). Added `from nodus.cli.cli import main` inside the block so the name is unconditionally resolved.
- `src/nodus/frontend/types.py`: replaced `exec(compile(...))` pattern with explicit `from types import ...` statements. No behavior change; removes exec() risk and makes the module statically analysable.
- `src/nodus/runtime/project.py`: removed 9 unused imports (`DependencySpec`, `create_project`, `find_project_root`, `load_manifest`, `load_project`, `load_project_from`, `parse_dependencies`, `read_lockfile`, `write_lockfile`). None were referenced in the file body or consumed via re-export from this module.

### Improved
- None.

### Documentation
- `README.md`: added Shawn Knight creator attribution and Masterplan Infinite Weave / Infinity Algorithm canonical definition in the opening paragraph; added CI, PyPI, and license badges; added Documentation section with links to language spec, architecture, changelog, contributing guide, and llms.txt.
- `CONTRIBUTING.md`: updated repository structure diagram from stale flat layout to current `src/nodus/` package structure; fixed `requirements-dev.txt` reference to `requirements.txt`; fixed `LANGUAGE_SPEC.md` bare reference to `docs/language/LANGUAGE_SPEC.md`.
- `docs/onboarding/DEVELOPMENT.md`: updated all core component file references from bare filenames to full `src/nodus/` paths (`src/nodus/frontend/lexer.py`, `src/nodus/frontend/parser.py`, `src/nodus/frontend/ast/ast_nodes.py`, `src/nodus/compiler/compiler.py`, `src/nodus/vm/vm.py`, `src/nodus/orchestration/task_graph.py`, `src/nodus/orchestration/workflow_lowering.py`).

### Tests
- **CI: Coverage gate added (Phase 5C):** Added a `Coverage` step to CI running `pytest --cov=src/nodus --cov-report=term-missing --cov-fail-under=60`. Three timing-sensitive tests are deselected from the coverage run (they pass in the regular `Pytest` step but fail under instrumentation overhead): `test_scheduler_fairness.py::test_multiple_tasks_progress`, `test_scheduler_fairness.py::test_long_running_task_rotates_with_budget`, `test_task_graph.py::TaskGraphTests::test_worker_death_detection`. Overall baseline: 77% (14,232 stmts). `pytest-cov==7.1.0` added to `requirements.txt`.
- **CI: GitHub Actions SHA pinning (Phase 5C):** Both `actions/checkout` and `actions/setup-python` are now pinned to 40-character commit SHAs with inline version comments. `actions/checkout v4.3.1` → `34e114876b0b11c390a56381ad16ebd13914f8d5`; `actions/setup-python v5.6.0` → `a26af69be951a213d495a4c3e4e4022e16d87065`. Prevents supply-chain attacks via tag mutation.
- **CI: mypy non-blocking baseline (Phase 5C):** Added a `Type check` step with `continue-on-error: true` running `mypy src/nodus/ --ignore-missing-imports --no-error-summary`. Current baseline: 208 errors across 29 modules (top offenders: `cli/cli.py` 49, `vm/vm.py` 24, `formatter.py` 18, `task_graph.py` 18). Baseline recorded in `TECH_DEBT.md`. `mypy==2.1.0` added to `requirements.txt`; `[tool.mypy]` section added to `pyproject.toml`.
- CI: Added `Lint` step (`ruff check .`) positioned immediately after `Set up Python`, before all test and format steps. The step fails the build on any lint error, surfacing the existing backlog of 77 errors.

### Refactoring
- **`BuiltinRegistry` extracted to `builtins/registry.py` (Phase 5C):** Moved `BuiltinRegistry` class from `src/nodus/builtins/__init__.py` to `src/nodus/builtins/registry.py`. `__init__.py` now re-exports it with `# noqa: F401`. `register_all()` moved to the class body; all four category-module registrations (`io`, `math`, `coroutine`, `collections`) are performed there. Only `vm.py` imported `BuiltinRegistry` from `nodus.builtins`; no consumer changes required.
- **`src/nodus/__init__.py` function-body imports removed (Phase 5C):** Three wrapper functions (`resolve_imports`, `run_source`, `main`) that existed only to provide lazy-import deferred loading were replaced with `__getattr__` handlers plus `globals()` caching. Startup cost unchanged (imports still deferred); module-body wrapper definitions eliminated. `if __name__ == "__main__"` updated to use `__getattr__("main")()`.
- **Lint cleanup — ruff error count 66 → 0** (Phase 4A): resolved all outstanding ruff errors so CI passes on every push.
  - F811: removed duplicate `import threading` at `services/server.py:48`; kept the import at line 12.
  - F401 (46): removed 45 unused imports across `builtins/collections.py`, `lsp/server.py`, `orchestration/workflow_lowering.py`, `runtime/errors.py`, `services/server.py`, `tooling/analyzer.py`, `tooling/loader.py`, `tooling/registry_client.py`, `tooling/runner.py`, `tooling/user_config.py`, `vm/vm.py`, and test files; `runtime/semver.py` re-exports protected with `# noqa: F401`.
  - E402 (11): moved `TASK_STEP_BUDGET` constant in `runtime/scheduler.py` to after imports; moved `from nodus.support.version import VERSION` in `services/server.py` to top-level import block; added `# noqa: E402` to `cli.py`, `language.py`, and `task_graph.py` shims where imports must follow `sys.path` manipulation.
  - E401 (2): split multi-import lines in `tmp_demo/` (auto-fixed).
  - F841 (6): removed `scheduler_hint` initial declaration and intermediate assignment in `orchestration/task_graph.py`; removed unused `by_id` dict in `orchestration/task_graph.py`; removed dead `else_header` in `tooling/formatter.py`; narrowed `except Exception as err:` to `except Exception:` in `lsp/server.py`; dropped unused assignment targets in `tests/test_incremental_compilation.py` and `tests/test_registry_client.py`.

## [1.1.2] - 2026-04-27

### Added
- `nodus repl` CLI command.

### Fixed
- duplicate execution when both `main.nd` and `src/main.nd` exist.
- circular import detection with full chain reporting.
- stdlib packaging issues.

### Changed
- clarified execution behavior for `nodus run`.

### Notes
- runtime behavior is now consistent between development and installed environments.

## 1.1.1 - 2026-04-26

### Added
- Optional `server` install extra for FastAPI/Uvicorn: `pip install "nodus-lang[server]"`.

### Changed
- `nodus check` now mirrors `nodus run` project resolution and can validate the default project entry file when invoked with no explicit file from a project directory.
- HTTP server docs now identify canonical route names and compatibility aliases for overlapping endpoint names.

### Improved
- Added installed-wheel smoke coverage for the packaged `nodus` CLI, including `run`, `init`, `repl`, `serve`, and stdlib import resolution.

### Documentation
- Clarified that `nodus serve` is the canonical user-facing HTTP API surface.
- Documented optional server dependency behavior for plain installs versus `nodus-lang[server]`.

### Tests
- Added installed-wheel distribution smoke validation.
- Added CLI coverage for `nodus check` project-root and project-directory resolution.

## 1.1.0

* Added automatic `main()` execution
* Introduced installable PyPI package (`nodus-lang`)
* Cleaned repository boundary (removed A.I.N.D.Y. concepts)
* Clarified execution model

## [0.9.0] - 2026-03-15 — Registry Auth, Publish & Ecosystem Completeness

### Added
- **Registry authentication**: Bearer token support via `--registry-token` flag, `NODUS_REGISTRY_TOKEN` env var, and `~/.nodus/config.toml` user config file. Three-tier resolution: flag > env > config.
- **`nodus login` / `nodus logout`** commands: write and clear the registry token in `~/.nodus/config.toml`.
- **`nodus publish`**: uploads a package archive to the registry via POST with SHA-256 digest sent as `X-SHA256` header. 409 Conflict returns a clear error. Implemented via `create_package_archive()` and `publish_package()`.

### Changed
- `compile_source()` public re-export removed from `nodus.__init__`; loader body retained in `nodus.tooling.loader` for internal use until v1.0.

### Fixed
- CI: `tests/test_formatter_coverage.py` was using `import pytest`, causing `ModuleNotFoundError` in the unittest-based CI runner. Converted to `unittest.TestCase`.

### Documentation
- `CONTRIBUTING.md`: replaced stale `pytest` commands in the Running Tests section with `python -m unittest` equivalents.
- `docs/tooling/TESTING.md`: added `test_formatter_coverage.py` entry to the Formatter Test Files section; updated Known Flaky Tests run command from `python -m pytest` to `python -m unittest`; removed stale `pytest` alternative from Running Tests.

### Tests
- 11 new tests covering registry authentication: token resolution priority (flag > env > config), `nodus login`/`nodus logout`, and Bearer token header injection.
- 9 new tests covering publish: archive creation, POST upload, `X-SHA256` header, and 409 Conflict handling.
- Converted `tests/test_formatter_coverage.py` from pytest to `unittest.TestCase` (CI fix).

### Provisional Opcodes
- `GET_ITER`/`ITER_NEXT` `pending_get_iter` cleanup deferred to v1.0 by design; behavior documented in `INSTRUCTION_SEMANTICS.md`.
- Exception model: `finally` blocks and typed catches deferred to v1.0. `SETUP_TRY`, `POP_TRY`, and `THROW` remain provisional.

## [0.8.0] - 2026-03-15 — Stability and Package Ecosystem

### Added
- **Registry-backed package resolution**: new `RegistryClient` (`src/nodus/tooling/registry_client.py`) fetches package index, resolves semver constraints, downloads archives with SHA-256 verification, and extracts to `.nodus/_staging/`. Registry URL resolved from `--registry` flag, `NODUS_REGISTRY_URL` env var, or `registry_url` in `nodus.toml`. 12 new tests in `tests/test_registry_client.py`.
- **FRAME_SIZE opcode**: pre-allocates `frame.locals_array` (list of N slots) at function entry. First instruction of every compiled function body. Bytecode version bumped to `BYTECODE_VERSION = 2`.
- **LOAD_LOCAL_IDX opcode**: slot-indexed read from `frame.locals_array[slot]`; replaces name-keyed `LOAD_LOCAL` for all function-scope locals. ~40%+ hot-loop improvement over name-keyed dict lookup.
- **STORE_LOCAL_IDX opcode**: slot-indexed write to `frame.locals_array[slot]`; handles Cell boxing in-place for closure capture. Emitted for all let-bindings, assignments, loop variables, catch variables, and destructuring targets.
- **Opcode freeze proposal**: `docs/governance/FREEZE_PROPOSAL.md` — formal stability table for all 47 opcodes (39 stable, 7 provisional, 1 deprecated), freeze prerequisites, post-freeze extension process, and version history.
- **Formatter coverage complete**: handlers added for `Yield`, `Throw`, `TryCatch`, `DestructureLet`, `VarPattern`, `ListPattern`, `RecordPattern`. New `format_pattern()` helper. All 48 AST node types now covered. See `tests/test_formatter_coverage.py`.

### Changed
- `Frame` dataclass extended with `locals_array: list | None` and `locals_name_to_slot: dict[str, int] | None`. `STORE_ARG` syncs to both `locals` dict and `locals_array`.
- `SymbolTable.define()` now assigns `Symbol.index` (local slot) for function-scope symbols. `Upvalue.index` carries the local slot when `is_local=True`.
- `FunctionInfo` gains `local_slots: dict[str, int]` field; serialized to/from bytecode cache.
- `capture_local()` prefers `locals_array` path when available; Cell boxing goes through array slot.
- `ProjectConfig` gains optional `registry_url` field; written to `nodus.toml` when set.
- LSP server `serverInfo.version` bumped to `0.8.0`.

### Fixed
- LSP `_uri_to_path` now uses `os.path.realpath` instead of `os.path.abspath`, normalising double-slash paths (`//tmp/…`) that arise from 4-slash `file:////…` URIs on Linux.
- LSP `_publish_diagnostics` echoes back the exact URI registered via `textDocument/didOpen` instead of reconstructing one, preventing URI mismatches on Linux.

### Deprecated / Removed
- `compile_source()` internal callers fully migrated to `ModuleLoader` in v0.8. Public stub in `nodus.__init__` retained with `DeprecationWarning` until v1.0. All 24 test files migrated to `ModuleLoader.compile_only()`.
- `LOAD_LOCAL` opcode classified **deprecated**; retained as fallback only. Removal target: v1.0 after full bytecode migration.

### Documentation
- `docs/governance/FREEZE_PROPOSAL.md`: new — opcode stability classifications and v1.0 freeze process.
- `docs/runtime/BYTECODE_REFERENCE.md`: added FRAME_SIZE, LOAD_LOCAL_IDX, STORE_LOCAL_IDX entries; opcode count updated to 47; reference to FREEZE_PROPOSAL.md added.
- `docs/governance/TECH_DEBT.md`: GET_ITER/pending_get_iter cleanup and Exception model finalization sections added; all v0.8 items marked complete.
- `docs/governance/ROADMAP.md`: all five v0.8 goals marked ✅.
- `docs/language/FORMAT.md`: formatting rules for Yield, Throw, TryCatch, DestructureLet.
- `docs/tooling/PACKAGE_MANAGER.md`: Registry Installation section added.
- `docs/tooling/TESTING.md`: corrected CI step description; updated formatter test authoring guidance.

### Tests
- `tests/test_formatter_coverage.py`: 7 new tests covering all previously-missing AST formatter nodes.
- `tests/test_registry_client.py`: 12 new tests covering HTTP fetch, semver resolution, checksum verification, install/extract, and full integration flow.
- Rewrote `tests/test_formatter_fnexpr.py` as a `unittest.TestCase` class.

## [0.7.0] - 2026-03-15 — Runtime Orchestration, Diagnostics, Debugging, and Sprint Fixes

### Added
- Incremental module compilation backed by a persistent dependency graph (`.nodus/deps.json`).
- Disk bytecode cache for compiled modules (`.nodus/cache/*.nbc`).
- DAP debug adapter over stdio with `nodus dap`.
- LSP server with completion, hover, go-to-definition, and diagnostics.
- Workflow persistence snapshots and checkpoint files under `.nodus/graphs/`.
- Workflow management CLI commands: `nodus workflow list`, `nodus workflow resume`, `nodus workflow cleanup`.
- `NodeVisitor` base class (`src/nodus/frontend/visitor.py`) — automatic `visit_<ClassName>` dispatch for all AST walkers.
- `BuiltinRegistry` class (`src/nodus/builtins/__init__.py`) — category modules (`io`, `math`, `coroutine`, `collections`) register builtins at VM construction time.
- String escape sequences: `\r`, `\0`, `\xHH`, `\uXXXX` now supported in the lexer.
- Import chain depth limit: configurable via `NODUS_MAX_IMPORT_DEPTH` env var (default 100); raises `LangSyntaxError` instead of `RecursionError`.
- Formatter handlers for `FnExpr` (anonymous functions), `FieldAssign` (`obj.field = val`), and `RecordLiteral` (`record { ... }`).
- CI auto-formats `examples/*.nd` before the format check and commits back with `[skip ci]`.

### Changed
- Runtime module loader now skips recompilation when dependency mtimes are unchanged.
- Workflow resume logic rehydrates persisted task state and scheduler order.
- `nodus deps` now reports the incremental compilation dependency graph.
- `compile_source()` marked deprecated since v0.5.0; `ModuleLoader(...).load_source(src)` is the canonical pipeline. Removal target: v1.0.
- AST `Base` dataclass carries explicit `_tok` and `_module` fields (excluded from `__repr__`/`__eq__`) on all node types.
- Bytecode cache format changed from `pickle` to `marshal` with `NDSC` magic header + format version byte + SHA-256 integrity check. Eliminates pickle's arbitrary-code-execution risk.
- Channel `waiting_receivers` / `waiting_senders` converted from `list` to `collections.deque`; `pop(0)` replaced with `popleft()` (O(1)).
- Optimizer `collect_jump_targets()` hoisted to once per outer fixed-point iteration; O(n) list-equality dirty-detection fallback removed in favour of a boolean `changed` flag.
- Legacy `.tl` files removed from `examples/`; `examples/` now contains only `.nd` files.

### Fixed
- `decode_string_literal` now raises `LangSyntaxError` directly with line/col rather than bare `SyntaxError`; tokenize() re-raise workaround removed.
- Optimizer bool constant folding normalised: arithmetic ops convert bool operands to int before folding to match VM runtime semantics.
- `builtin_close` now guards receiver wake-up with `state == "suspended"` check to prevent waking non-suspended coroutines.

### Improved
- VM `execute()` dispatch replaced `if/elif` chain with a dict dispatch table (`_build_dispatch_table()`). Benchmark: 388 ms → 260 ms (~33% throughput improvement).
- `LOAD_LOCAL` opcode: compiler emits `LOAD_LOCAL name` instead of `LOAD name` for confirmed function-local variables, bypassing the 4-scope probe in `load_name()`. Benchmark: ~21% additional improvement on tight loops.
- Scheduler fairness via round-robin execution and `TASK_STEP_BUDGET` enforcement.
- LSP diagnostics are dependency-aware with cross-module publishing and incremental refresh.
- Debugger integration reused by both interactive debugger and DAP server.
- Workflow checkpoint handling preserves upstream task outputs while rolling back downstream steps.

### Documentation
- Added/updated docs for LSP, DAP, debugging entrypoints, workflow persistence, and scheduler fairness.
- Documentation synchronisation pass: FORMAT.md, TESTING.md, BYTECODE_REFERENCE.md, RELEASE_CHECKLIST.md, TECH_DEBT.md, GETTING_STARTED.md updated to reflect Phases 1–4.

### Tests
- Added coverage for bytecode cache, incremental compilation, scheduler fairness, workflow persistence, LSP diagnostics, and DAP server behavior.
- Added/expanded tests for module isolation and runtime module objects.
- Added `tests/test_formatter_fnexpr.py` covering FnExpr, FieldAssign, RecordLiteral formatting.

### Refactoring
- `_StateRewriter` documented in `src/nodus/runtime/workflow_lowering.py`.

## [0.5.0] - 2026-03-14 — Interactive Shell and Inspection

### Added
- REPL multiline editing with `... ` continuation for brace-delimited blocks.
- Persistent REPL history via `~/.nodus_history` when Python `readline` is available.
- REPL inspection commands: `:ast <expr>`, `:dis <expr>`, `:type <expr>`, `:help`, and `:quit`.
- Dedicated REPL documentation in `docs/tooling/REPL.md`.
- Profiler documentation and runtime integration for the 0.5.0 tooling milestone.

### Changed
- REPL inspection output now supports compact expression AST views and expression bytecode inspection.
- Onboarding and runtime docs now describe the interactive shell workflow and inspection commands.
- Project metadata now aligns on version `0.5.0`.

### Fixed
- None.

### Removed
- None.

## [0.4.x Tracking]
- Module bytecode unit format and bytecode version headers.
- Minimal runtime module objects and debugger MVP.
- Semver parsing and lockfile format groundwork.

## [0.4.0] - 2026-03-14 — Runtime Architecture & Packaging

### Added
- Bytecode version headers in compiled modules.
- Runtime sandbox limits (steps/time/stdout).
- Embedding API for host execution and host function registration.
- Runtime module system with module objects and caching.
- Per-module bytecode units and per-module global namespaces.
- Project manifest parsing (`nodus.toml`) and dependency resolution.
- `nodus.lock` lockfile generation with resolved metadata.
- Debugger MVP with breakpoints, stepping, stack inspection, and variable inspection.
- Tooling-side package management modules for project parsing, semver, dependency resolution, installation, and registry metadata.
- Deterministic `[[package]]` lockfile entries with `name`, `version`, `source`, and `hash`.
- Test coverage for installer behavior, lockfile generation, runtime loading from `.nodus/modules`, and manifest/resolution flows.

### Changed
- Imports now resolve through the runtime module loader with dependency-first resolution.
- Module execution is isolated per module with cached module objects.
- Tooling execution flows updated for module-based runtime execution.
- CLI includes `nodus update` for dependency refresh.
- Refactored package management so runtime execution no longer performs manifest parsing, dependency resolution, registry access, or network operations.
- Installed dependencies now live under `.nodus/modules/` instead of `deps/`.
- Runtime module loading now resolves imports in the order: local project modules, `.nodus/modules/`, then standard library.
- `nodus install` and `nodus update` now route through tooling-side resolution and installation.

### Internal
- Module loader integrates project manifests, lockfile resolution, and dependency paths.
- VM supports module-bound function wrappers for module exports.
- Package manager routes through the runtime project system and lockfile format.

### Tests
- Added coverage for manifest parsing, semver ranges, and dependency resolution.
- Updated package tests for the new lockfile format and module execution behavior.

### Fixed
- Worker-required tasks always dispatch through the worker manager.

### Removed
- Package-management responsibilities from the runtime project/loading path.

## [0.3.0] - 2026-03-13

### Added
- Workflow and goal syntax with task graph planning, execution, resume, and checkpoints.
- Cooperative coroutines, scheduler, and channels (`coroutine`, `resume`, `spawn`, `run_loop`, `sleep`, `channel`, `send`, `recv`, `close`).
- Runtime event bus with human/JSON sinks and CLI flags `--trace-events`, `--trace-json`, `--trace-file`.
- Service mode `nodus serve`, session snapshots (`nodus snapshot`, `nodus snapshots`, `nodus restore`), and worker registration (`nodus worker`).
- Orchestration CLI commands: `nodus graph`, `workflow-*`, `goal-*`.
- Runtime service CLI commands: `tool-call`, `agent-call`, `memory-get`, `memory-put`, `memory-keys`.
- Package management commands: `nodus init`, `nodus install`, `nodus deps` with `nodus.toml`/`nodus.lock`.
- Stdlib modules: `std:json`, `std:math`, `std:runtime`, `std:tools`, `std:memory`, `std:agent`, `std:async`, `std:utils`.
- Editor support: TextMate grammar, VS Code config, and snippets under `tools/vscode/`.
- Inspection tooling: `nodus ast`, `nodus dis`, `nodus ast --compact`, `nodus dis --loc`.
- Debug command: `nodus debug`.
- Example smoke test command: `nodus test-examples`.
- Added `examples/project_layout_demo/` as a small multi-file onboarding example.

### Changed
- Formatter preserves integer-looking numeric literals and uses a dedicated unary minus AST node.
- Trailing comment behavior clarified and `--keep-trailing` option added.
- `nodus run` adds `--no-opt`, `--project-root`, scheduler tracing, and trace filters/limits.
- Bytecode reference updated to document the `NEG` opcode explicitly.

### Fixed
- Expire polling workers after heartbeat timeout to ensure dead workers are removed promptly.

### Removed
- None.

## [0.2.0] - 2026-03-11

### Added
- Module system (imports/exports, selective imports, re-exports, `std:` aliases).
- Deterministic import resolution with package/index support and project-root overrides.
- Standard library modules: `std:strings`, `std:collections`, `std:fs`, `std:path`.
- `nodus fmt` (formatter) with `--check` and comment handling controls.
- `nodus check` for syntax/import/compile validation without execution.
- Debug flags: `--dump-bytecode` and `--trace` with controls.
- CI workflow via GitHub Actions.
- Release discipline docs: `RELEASE_CHECKLIST.md`, `VERSIONING.md`, `COMPATIBILITY.md`.

### Changed
- Primary source extension is `.nd` (legacy `.tl` remains supported).
- Public CLI is `nodus` (legacy launchers still supported).
- Centralized version metadata in `version.py`.
- Compatibility: `.tl` extension still supported with warnings; legacy launchers remain available.

### Fixed
- None.

### Removed
- None.

## [0.1.0] - 2026-03-09

### Added
- Modular runtime architecture (lexer, parser/AST, compiler, VM, loader).
- Imports/exports with selective and namespaced imports.
- Deterministic import resolution with `std:` aliases.
- Stack traces with source mapping.
- Debugging flags: `--dump-bytecode` and `--trace`.
- Package/index resolution and project-root overrides.
- Re-export support (`export { name } from "./mod.nd"`).

### Changed
- Primary source extension is `.nd` (legacy `.tl` remains supported).
- Public CLI is `nodus` (legacy launchers still supported).

### Fixed
- None.

### Removed
- None.
