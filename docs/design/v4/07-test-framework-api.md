# Nodus v4.0 — Design Doc 07: Test Framework API

**Phase:** 1 (design docs)
**Status:** Locked
**Implements:** Decisions 4 and 13 (Test framework comprehensive scope; API specifics) from `00-phase-0-decisions.md`
**Date:** 2026-05-26
**Maintainer:** Shawn Knight (Masterplanner25)

---

## Problem statement

v4.0 ships a comprehensive test framework (`std:test`) — full pytest/
jest-equivalent capability. Decision 4 (Phase 0) locked the scope and
Decision 13 (Phase 0) locked the API shape with concrete examples. This
doc fills in the remaining specifics: assertion signatures, fixture
lifecycle and teardown, parameterized test specifics, async test
scheduling, isolation mechanism, failure reporting, CLI flags, and
output formats.

The test framework is the largest single language-side feature in v4.0
outside the protocol libraries. It exists because v4.0's "production-
ready orchestration DSL" theme requires real testing capability — users
writing production orchestration scripts need to verify their code's
behavior, not just hope it works.

This doc and `08-test-framework-coverage.md` are designed as a pair.
The coverage doc extends the test framework with line-level coverage
instrumentation; the two are designed together to avoid drift.

---

## What Phase 0 already settled

From Decision 4 (comprehensive scope):

- Assertions (basic and structural)
- Suites and cases (block-based via `test.suite` and `test.case`)
- Lifecycle hooks (`before_all`, `after_all`, `before_each`, `after_each`)
- Fixtures with test/suite scopes
- Parameterized tests
- Async tests with deterministic scheduling
- Test isolation by default
- Coverage reporting (source-line in v4.0; bytecode-level deferred)
- Test discovery (`*_test.nd` files under `tests/`)
- CLI: `nodus test` with filter, parallel, watch, coverage, format flags

From Decision 13 (API specifics):

- 11 assertions: `assert`, `assert_eq`, `assert_neq`, `assert_err`,
  `assert_ok`, `assert_kind`, `assert_throws`, `assert_close`,
  `assert_contains`, `assert_has_key`, `assert_in_range`
- `test.suite(name, fn)` for grouping
- `test.case(name, fn)` and `test.case_async(name, fn)`
- Block-based, no new language syntax
- Lifecycle hooks named per Decision 4
- `test.fixture(name, fn)` with `"test"` and `"suite"` scopes
- `test.parameterize(rows, fn)`
- Output formats: pretty TTY, plain text, JSON, JUnit XML

This doc resolves:

- Assertion signatures (actual-first ordering with optional message)
- Fixture teardown mechanism (`test.cleanup`)
- Parameterized test row formats (list or map)
- Async test deterministic scheduling specifics
- Isolation mechanism details
- Failure reporting shape (five parts + diff rendering)
- CLI flag complete specification
- Output format auto-detection

---

## Bytecode impact

**No new opcodes required. `BYTECODE_VERSION` stays at 4.**

The test framework is implemented entirely as Nodus stdlib functions
plus a test-runner CLI. Test functions, suites, fixtures, and
assertions are all registered through the existing builtin registry
and invoked via `CALL_BUILTIN`. The deterministic async scheduler is
an alternative asyncio loop implementation switched in only during
test execution — no VM changes.

Coverage instrumentation (specified in `08-test-framework-coverage.md`)
uses the existing source-position event infrastructure rather than
new opcodes. No bytecode shape changes.

The frozen-bytecode contract from v1.0 is preserved.

---

## Test file structure

Test files live under `tests/` and use the `*_test.nd` naming
convention. Each file contains one or more `test.suite` blocks
containing `test.case` blocks. The runner discovers and executes them.

Example complete test file:

```nodus
import "std:test" as test
import "../src/validator.nd" as validator

test.suite("user validation", fn() {
    test.before_all(fn() {
        // Setup that runs once before any test in this suite
    })

    test.before_each(fn() {
        // Setup that runs before each test
    })

    test.after_each(fn() {
        // Cleanup that runs after each test
    })

    test.fixture("authenticated_user", fn() {
        let user = create_user_with_token()
        test.cleanup(fn() { delete_user(user) })
        return user
    })

    test.case("rejects empty name", fn() {
        let result = validator.validate({name: "", age: 30})
        test.assert_eq(result.valid, false)
        test.assert_eq(result.error, "name required")
    })

    test.case("accepts valid input", fn(ctx) {
        let user = ctx.fixture("authenticated_user")
        let result = validator.validate({name: user.name, age: user.age})
        test.assert_ok(result)
    })

    test.parameterize([
        ["alice", 30, true],
        ["bob", 25, true],
        ["", 30, false]
    ], fn(name, age, expected) {
        test.case("validates: \(name)", fn() {
            test.assert_eq(validator.validate({name, age}).valid, expected)
        })
    })
})
```

---

## Assertion API

### Signature convention

All assertions follow the pattern: **actual first, expected second,
optional message last.** This reads naturally as "I got X, expecting
Y" and matches user mental models for failure diagnosis.

```nodus
test.assert(condition, msg?)
test.assert_eq(actual, expected, msg?)
test.assert_neq(actual, expected, msg?)
test.assert_err(value, msg?)
test.assert_ok(value, msg?)
test.assert_kind(err, kind_string, msg?)
test.assert_throws(fn, msg?)
test.assert_close(actual, expected, epsilon, msg?)
test.assert_contains(collection, item, msg?)
test.assert_has_key(map_or_record, key, msg?)
test.assert_in_range(actual, min, max, msg?)
```

The optional `msg` parameter is the second or third argument depending
on assertion arity. It is included in failure output to help locate
the failure.

### Individual assertion behavior

**`test.assert(condition, msg?)`** — generic truthiness check. The
condition is anything that evaluates to a truthy or falsy value.
Failure if condition is falsy (false, 0, 0.0, "", [], {}, nil).

**`test.assert_eq(actual, expected, msg?)`** — equality check using
v4.0's `==` operator (numeric-only coercion per `11-equality-
coercion.md`). For complex values (lists, maps, records), deep
equality is used.

**`test.assert_neq(actual, expected, msg?)`** — inequality check via
`!=` operator.

**`test.assert_err(value, msg?)`** — passes if value is an err record
(has `kind` field per `13-err-record-location-fields.md`). Returns the
err record for further inspection in subsequent assertions.

```nodus
let e = test.assert_err(http.get("https://invalid-url-here"))
test.assert_kind(e, "http_error")
```

**`test.assert_ok(value, msg?)`** — passes if value is NOT an err
record. Returns the value for inspection.

```nodus
let r = test.assert_ok(http.get("https://example.com"))
test.assert_eq(r.status, 200)
```

**`test.assert_kind(err, kind_string, msg?)`** — passes if err is an
err record with the specified kind. Combined with `assert_err`, this
is the standard pattern for checking specific error categories.

**`test.assert_throws(fn, msg?)`** — calls `fn()` (zero arguments),
passes if it throws (raises an err via the `throw` keyword), fails if
it returns normally or returns an err record (returning an err is
NOT throwing). Returns the thrown err for inspection.

```nodus
let e = test.assert_throws(fn() {
    throw {kind: "my_error", message: "boom"}
})
test.assert_eq(e.kind, "my_error")
```

**`test.assert_close(actual, expected, epsilon, msg?)`** — float
comparison with explicit tolerance. Passes if `abs(actual - expected)
< epsilon`. The epsilon argument is REQUIRED (no default) to prevent
silent passes when comparing floats with too-loose tolerance.

```nodus
test.assert_close(math.pi, 3.14159, 0.001)    // passes
test.assert_close(1.0 / 3.0, 0.33333, 0.001)  // passes
test.assert_close(math.nan, 0.0, 1.0)          // fails (nan never equals)
```

**`test.assert_contains(collection, item, msg?)`** — passes if
collection contains item. Works for:

- Lists: item is in the list (using `==` semantics)
- Strings: item is a substring
- Maps: item is among the map's keys

**`test.assert_has_key(map_or_record, key, msg?)`** — passes if the
map/record has the specified key/field. Lighter than
`assert_contains` — doesn't check value, only presence.

**`test.assert_in_range(actual, min, max, msg?)`** — passes if
`min <= actual <= max` (inclusive both ends). For numeric values.

### Failure behavior

All assertions raise an err on failure (via the `throw` keyword
internally). The test runner catches assertion failures, records them
as failed tests, and continues with remaining tests in the suite.

Assertions are NOT designed to be caught by user code. If a test
needs conditional assertion logic, use `if`/`else` in the test body
to choose which assertion to call, not try-catch around the assertion.

---

## Suite and case API

### `test.suite(name, fn)`

Defines a test suite. The `fn` is called once at suite registration
time; it registers cases, fixtures, and hooks. Tests don't run inside
`fn` — they're collected, then run by the test runner.

```nodus
test.suite("user authentication", fn() {
    // This body runs at registration time
    // test.case calls inside here register the cases
    test.case("login succeeds", fn() {
        // This body runs at test execution time
    })
})
```

Suites can be nested:

```nodus
test.suite("outer", fn() {
    test.suite("inner", fn() {
        test.case("nested test", fn() { ... })
    })
})
```

Nested suites share `before_each`/`after_each` hooks (inner hooks run
inside outer ones). Nested fixture scopes are scoped to the suite that
defines them.

### `test.case(name, fn)` and `test.case_async(name, fn)`

Define a single test case. The `fn` is the test body; it runs when
the test executes. For sync tests, `fn` returns nothing (or returns
to indicate success); assertions inside it determine pass/fail.

`test.case_async(name, fn)` defines an async test. The `fn` is a
coroutine; the test runner awaits it.

Both forms accept an optional `ctx` parameter:

```nodus
test.case("uses fixture", fn(ctx) {
    let value = ctx.fixture("my_fixture")
    test.assert_ok(value)
})
```

The `ctx` provides access to fixtures and test metadata.

### Lifecycle hooks

```nodus
test.before_all(fn)    // runs once before any test in the suite
test.after_all(fn)     // runs once after all tests in the suite
test.before_each(fn)   // runs before each test in the suite
test.after_each(fn)    // runs after each test in the suite
```

Hooks are scoped to the containing suite. They do NOT run for nested
suites' tests unless those nested suites are children of the suite
where the hook is registered (in which case the parent's hooks run
around the child's tests).

Hook execution order for a test in suite `B` (nested in suite `A`):

```
A.before_all (if first test in A)
B.before_all (if first test in B)
A.before_each
B.before_each
[test body]
B.after_each
A.after_each
B.after_all (if last test in B)
A.after_all (if last test in A)
```

If a hook throws or fails, subsequent hooks at the same level still
run (cleanup must always execute), but the test is marked as failed
with the hook error.

---

## Fixture API

### `test.fixture(name, fn, scope?)`

Defines a fixture — a value that can be requested by tests. The fixture
function runs lazily (only when a test requests it) and the result is
cached per the scope.

```nodus
test.fixture("name", fn, scope?)
```

- `scope: "test"` (default): the fixture function runs once per test
  case that requests it. Each test gets a fresh value.
- `scope: "suite"`: the fixture function runs once per suite. All tests
  in the suite share the same value.

### Fixture access

Tests access fixtures via the optional `ctx` parameter:

```nodus
test.case("uses authenticated user", fn(ctx) {
    let user = ctx.fixture("authenticated_user")
    // user is the value returned by the fixture function
})
```

If a test doesn't take a `ctx` parameter, it can't access fixtures.

Fixtures can access other fixtures:

```nodus
test.fixture("database", fn() {
    return connect_db()
})

test.fixture("user", fn(ctx) {
    let db = ctx.fixture("database")
    return db.create_user()
})
```

A fixture function receiving a `ctx` parameter can request other
fixtures from the same suite.

### Fixture teardown via `test.cleanup`

Fixtures that need cleanup (close connections, delete temp files,
unregister tools) register a cleanup function via `test.cleanup` from
within the fixture body:

```nodus
test.fixture("temp_file", fn() {
    let path = fs.create_temp()
    test.cleanup(fn() {
        fs.delete(path)
    })
    return path
})
```

Cleanup functions:

- Run after the fixture's scope ends (after each test for `"test"`
  scope; after the suite for `"suite"` scope)
- Run in reverse order of registration (LIFO)
- Run even if the test fails
- Errors in cleanup are logged but don't fail the test (the test's
  pass/fail status is determined by the test body)

Multiple `test.cleanup` calls can be made from within one fixture
(for example, to clean up multiple resources). All run on scope end.

### Async fixtures

Fixtures can be async. If the fixture function uses `await` or is a
coroutine, the test runner awaits it before passing the value to the
test:

```nodus
test.fixture("authenticated_user", fn() {
    let user = await create_user_async()
    test.cleanup(fn() { await delete_user_async(user) })
    return user
})
```

Async fixtures work with both `test.case` and `test.case_async`.

---

## Parameterized tests

### `test.parameterize(rows, fn)`

Runs a test body multiple times with different input data. Each row
becomes a separate test case.

```nodus
test.parameterize([
    ["alice", 30, true],
    ["bob", 25, true],
    ["", 30, false]
], fn(name, age, expected_valid) {
    test.case("validates: \(name)", fn() {
        test.assert_eq(validate({name, age}).valid, expected_valid)
    })
})
```

### Row format

Two forms supported:

**List form (positional):**

```nodus
test.parameterize([
    ["alice", 30, true],
    ["bob", 25, false]
], fn(name, age, expected) {
    test.case("...", fn() { ... })
})
```

**Map form (named):**

```nodus
test.parameterize([
    {name: "alice", age: 30, expected: true},
    {name: "bob", age: 25, expected: false}
], fn(row) {
    test.case("validates: \(row.name)", fn() {
        test.assert_eq(validate({name: row.name, age: row.age}).valid, row.expected)
    })
})
```

The library detects the form by inspecting the first row's type. If
it's a list, all rows must be lists (and the inner `fn` is called with
unpacked positional arguments). If it's a map, all rows must be maps
(and the inner `fn` is called with a single map argument).

Mixed-form rows produce err at parameterize time:

```nodus
err {
    kind: "test_error",
    payload: {
        category: "invalid_parameterize",
        message: "All rows must be the same form (all lists or all maps)"
    }
}
```

### Test naming

If the test name inside the parameterized fn uses string interpolation
referencing the row data, that's the per-iteration name.

If the test name doesn't interpolate, the library appends a row index:

```nodus
test.parameterize([
    ["alice", 30, true],
    ["bob", 25, false]
], fn(name, age, expected) {
    test.case("validates input", fn() { ... })
})

// Results in test cases named:
// "validates input [0]"
// "validates input [1]"
```

For map-form rows, the library generates a name suffix from the keys
(truncated if too long):

```nodus
test.parameterize([
    {name: "alice", expected: true},
    {name: "bob", expected: false}
], fn(row) {
    test.case("validates", fn() { ... })
})

// Results in:
// "validates [name=alice, expected=true]"
// "validates [name=bob, expected=false]"
```

---

## Async test scheduling

### Deterministic execution

In test mode, the asyncio loop is replaced with a deterministic
scheduler. This is essential for testing workflows that fan out async
operations (HTTP calls, subprocess spawns) where ordering would
otherwise vary.

**Scheduler behavior:**

- Tasks are ordered by registration ID (monotonic integer per spawn)
- When multiple tasks are ready, the lowest-ID task runs first
- Sleep and timeout values use a virtual clock; tests can advance the
  clock without actually waiting

**Virtual clock control:**

```nodus
test.case_async("retry logic", fn() {
    let state = {attempt_count: 0i}
    let task = coroutine(fn() {
        sleep(5000)   // virtual 5 seconds (5000ms)
        state.attempt_count = state.attempt_count + 1i
    })
    spawn(task)

    test.flush_async()        // step 1: runs task's first step → sleep(5000)
    test.advance_clock(10000) // step 2: advance clock 10s; task is now overdue
    test.flush_async()        // step 3: task wakes, increments attempt_count

    test.assert_eq(state.attempt_count, 1i)
})
```

**Important implementation notes (deviations from this doc's original design):**

1. `flush_async()` is **synchronous** — there is no `await` keyword in Nodus.
   Call it as a plain statement: `test.flush_async()`.
2. The first argument to `spawn` must be a **coroutine value**, not a function
   literal. Use `coroutine(fn() {...})` to create one first, then `spawn(coro)`.
3. Closures cannot mutate outer local variables declared with `let` — use a
   **map field** (`state.count = state.count + 1i`) to share mutable state
   between the coroutine and the test body.
4. `sleep(N)` takes **milliseconds** as a plain number. `advance_clock(N)` also
   takes milliseconds.

**The two-flush pattern** is always required when testing code that sleeps:

1. First `flush_async()` — runs each spawned coroutine one step. A coroutine
   that immediately calls `sleep(N)` suspends here and schedules its wakeup at
   `current_virtual_time + N`.
2. `advance_clock(M)` — moves the virtual clock forward by M ms. Any coroutine
   whose wakeup time is now in the past is moved to the ready queue.
3. Second `flush_async()` — runs the newly-woken coroutines.

The `test.advance_clock(duration)` and `test.flush_async()` functions
control the virtual clock and scheduler. They're test-mode-only; using
them in production code is a no-op.

### Mixing sync and async tests

A suite can contain both `test.case` and `test.case_async`. The
runner handles both forms. Sync tests don't engage the async
scheduler; async tests do. Hooks (`before_each`, etc.) can be either
sync or async.

---

## Test isolation

### What gets isolated

By default, each test case runs as if no other test has run. The
framework tracks and reverts the following between tests:

- **Tool registry registrations.** Any `tool.register` calls made
  during the test are followed by automatic `tool.unregister` after
  the test ends.
- **Environment variables.** Any `env.set` calls are reverted to the
  pre-test value (or unset if the variable didn't exist).
- **Working directory.** Restored to the pre-test value.
- **Open channels and coroutines.** Channels opened by the test are
  closed; coroutines spawned by the test are cancelled.

### What's NOT isolated

Some state is not tracked because tracking is impractical or
expensive:

- **File system state outside known temp directories.** Tests that
  write to `/tmp/` should clean up via `test.cleanup`. Tests that
  write elsewhere are the author's responsibility.
- **External services.** HTTP calls to live servers, database writes
  to real databases. Use mocks or test doubles.
- **The Python interpreter's global state.** When Nodus is embedded
  in a Python host, Python-side state changes are not tracked.

### Opt-out from isolation

For suites where shared state is intentional (testing connection
pooling, validating that tool registrations persist correctly):

```nodus
test.suite("connection pool tests", fn() {
    // tests share state across runs
}, {isolated: false})
```

The optional third argument to `test.suite` accepts `{isolated:
false}`. Tests in the suite skip isolation steps.

Default is `{isolated: true}`; opt-out is explicit.

---

## Failure reporting

### Failure shape

When an assertion fails or a test throws unexpectedly:

```
FAIL: validates: alice (tests/validator_test.nd:42)
  assert_eq failed
  actual:   31
  expected: 42
  message:  (none)

  Backtrace:
    at fn anonymous (tests/validator_test.nd:42)
    at test.case "validates: alice" (tests/validator_test.nd:38)
    at test.suite "user tests" (tests/validator_test.nd:30)
```

Five parts:

1. **Test identifier:** suite name(s) + case name + source location
2. **Failure type:** assertion name or "uncaught error"
3. **Failure shape:** actual vs expected (for assertions); err details
   (for thrown errors)
4. **Optional user message:** the `msg?` parameter if provided
5. **Backtrace:** through the test structure

### Diff rendering for complex values

For `assert_eq` failures on multi-line or structurally complex values,
the framework renders a diff:

```
FAIL: matches expected user (tests/user_test.nd:18)
  assert_eq failed
  actual:
    {
      name: "alice",
      age: 30,
      email: "alice@example.com",
      role: "user"
    }
  expected:
    {
      name: "alice",
      age: 30,
      email: "alice@example.com",
      role: "admin"
    }
  diff:
      role: "user"      <- actual
      role: "admin"     <- expected
```

For lists:

```
FAIL: expected items list (tests/list_test.nd:25)
  assert_eq failed
  diff:
    [
      "a",
      "b",
    - "c",          <- present in actual
    + "d",          <- present in expected
      "e",
    ]
```

The diff algorithm uses standard line-by-line diff (similar to git
diff format) with structural awareness for records, maps, and lists.

### Output to different formats

The five-part failure shape is rendered differently per format:

- **pretty:** the human-readable rendering above, with colors
- **plain:** same without colors
- **json:** one JSON object per test result, including failure details
  as structured fields
- **junit:** XML in JUnit format with failure details in the
  `<failure>` element

---

## CLI specification

### Command and arguments

```
nodus test [path] [flags]
```

- **path** (optional, default `tests/`): directory or specific file
  to run. Tests are discovered recursively in directories.

### Flags

| Flag | Default | Description |
|---|---|---|
| `--filter <pattern>` | (none) | Run only tests matching pattern (glob or regex) |
| `--parallel <N>` | 1 | Run up to N test cases concurrently |
| `--watch` | off | Re-run tests when source files change |
| `--coverage` | off | Collect coverage data (see `08-test-framework-coverage.md`) |
| `--format <fmt>` | auto | Output format: pretty, plain, json, junit |
| `--bail` | off | Stop on first failure |
| `--seed <N>` | (random) | Random seed for reproducible randomization |
| `--verbose` | off | Show passing tests as well as failures |
| `--quiet` | off | Show only summary, no per-test output |

### Filter syntax

Glob form:

```bash
nodus test --filter "user_*"            # matches suite/case names starting with "user_"
nodus test --filter "*auth*"            # contains "auth"
nodus test --filter "validates: alice"  # exact case name
```

Regex form (prefix with `re:`):

```bash
nodus test --filter "re:.*async.*"   # any case containing "async"
```

Filter matches against the full hierarchical name: `suite_name >
nested_suite_name > case_name`.

### Parallel execution

`--parallel N` runs up to N test cases concurrently. Defaults to 1
(sequential) because:

1. Most orchestration tests are I/O-bound; parallelism helps
2. But many tests have implicit ordering dependencies users haven't
   realized; sequential execution is safer default
3. Users explicitly opt into parallelism when they're confident their
   tests are independent

Parallel execution uses the deterministic scheduler — tests are
assigned to worker contexts in registration order, and each worker
runs its tests sequentially. Output is collected and reported in
deterministic order.

### Watch mode

`--watch` monitors the source tree for file changes and re-runs
affected tests. Watch mode:

- Detects changes to `*.nd` files in the project
- Re-runs tests that depend on changed files (best effort; falls back
  to running all tests if dependency tracking is uncertain)
- Outputs incremental results
- Exits on Ctrl+C

### Format auto-detection

If `--format` is not specified, the format is auto-selected:

- **pretty** if stdout is a TTY (interactive use)
- **plain** if stdout is not a TTY (CI, log capture)

Explicit `--format` always overrides auto-detection.

### Exit codes

| Exit code | Meaning |
|---|---|
| 0 | All tests passed |
| 1 | One or more tests failed |
| 2 | Test discovery error (no tests found, invalid test file syntax) |
| 3 | Runtime error in the test runner itself |

---

## Output format specifications

### Pretty (TTY) format

```
 RUN  validator_test.nd
  ✓ validates non-empty input (12ms)
  ✓ validates: alice (3ms)
  ✓ validates: bob (3ms)
  ✗ validates: empty (5ms)
    assert_eq failed
    actual:   true
    expected: false

 RUN  http_client_test.nd
  ✓ gets a URL (245ms)
  ✓ handles 404 (140ms)

Suites: 2 total
Tests:  6 total, 5 passed, 1 failed
Time:   0.4s
```

### Plain format

Same content without colors or animations. Used in CI or when stdout
isn't a TTY.

### JSON format

One JSON object per test result on its own line (JSON Lines format):

```json
{"type": "test", "suite": "validator", "case": "validates non-empty input", "status": "pass", "duration_ms": 12}
{"type": "test", "suite": "validator", "case": "validates: empty", "status": "fail", "duration_ms": 5, "failure": {"assertion": "assert_eq", "actual": true, "expected": false}}
{"type": "summary", "suites_total": 2, "tests_total": 6, "tests_passed": 5, "tests_failed": 1, "duration_ms": 400}
```

### JUnit XML format

Standard JUnit XML for CI integration with Jenkins, GitHub Actions,
GitLab CI, etc.

---

## Err record shape

Test framework errs use this shape:

```nodus
err {
    kind: "test_error",
    message: string,
    path: ..., line: ..., column: ..., stack: ...,
    origin: "stdlib",
    payload: {
        category: string,
        details: ...
    }
}
```

### Category enumeration

| Category | When emitted |
|---|---|
| `"assertion_failure"` | Internal — assertions throw with this category |
| `"fixture_not_found"` | `ctx.fixture(name)` for unregistered name |
| `"fixture_error"` | Fixture function itself threw |
| `"invalid_parameterize"` | Mixed-form rows or other parameterize input errors |
| `"hook_error"` | Lifecycle hook (`before_each` etc.) threw |
| `"discovery_error"` | Test discovery failed (file not found, syntax error) |

---

## MCP and A2A consumer validation

The test framework is library-agnostic; `nodus-mcp` and `nodus-a2a`
use it for their own internal testing. The interaction that matters:
tests for orchestration code that uses both libraries can use:

- `test.assert_ok(mcp.call_tool(...))` to verify a remote MCP call
- `test.assert_kind(error, "a2a_error")` to verify expected A2A errors
- Async tests with `test.case_async` to test workflows that fan out
  to multiple protocols in parallel
- Fixtures to set up MCP server connections or A2A agent registrations

The deterministic async scheduling is especially valuable for testing
multi-protocol workflows — without it, tests would be flaky depending
on which protocol's response arrived first.

---

## Migration impact

The test framework is new in v4.0. No migration from v3.x (there was
no `std:test` before). Existing v3.x test code using ad-hoc assertion
patterns can migrate to `std:test` opt-in.

---

## Implementation outline

### Module structure

- `test_runner.py` — orchestrates suite/case execution, hook ordering,
  fixture caching, isolation tracking
- `test_assertions.py` — assertion implementations with failure
  formatting
- `test_scheduler.py` — deterministic async scheduler (test-mode only)
- `test_discovery.py` — finds test files matching `*_test.nd`
- `test_cli.py` — CLI flag parsing and orchestration
- `test_format_*.py` — one per output format (pretty, plain, json,
  junit)

### Isolation tracking

The runner uses a context-manager-style approach:

```python
class IsolationContext:
    def __enter__(self):
        self._snapshot = capture_state()  # env, cwd, registry, etc.

    def __exit__(self, ...):
        restore_state(self._snapshot)
        unregister_added_tools()
        close_opened_channels()
        cancel_spawned_coroutines()
```

### Failure formatting

The diff algorithm uses `difflib` (Python stdlib) for line-by-line
diffing. Structural diffing for records, maps, and lists wraps
`difflib` with a structure-aware renderer.

### Test surface (Phase 3B)

- All 11 assertions: pass and fail cases, message inclusion
- Lifecycle hook ordering (parent before child)
- Fixture scopes (test vs suite), teardown via `test.cleanup`
- Async fixtures, parameterized tests (list and map row forms)
- Async test scheduling (virtual clock, flush, ordering determinism)
- Isolation (state changes reverted), isolation opt-out
- Failure rendering in all four formats, diff rendering
- CLI flag parsing, watch mode, parallel execution, filter patterns
- Exit codes for all scenarios

---

## Open implementation questions for Phase 3B

1. **Virtual clock semantics for nested async operations.** Tests
   that spawn coroutines that themselves spawn coroutines can have
   complex timing. Tentative: depth-first virtual time advancement
   when `test.advance_clock` is called.

2. **Filesystem watcher implementation.** Use `watchdog` Python
   package or implement minimal polling-based watcher? Tentative:
   `watchdog` for production; falls back to polling if not installed.

3. **Diff algorithm performance on very large values.** Records or
   lists with thousands of elements could produce huge diffs.
   Tentative: truncate diff to ~100 lines; show "N more changes
   omitted" indicator.

4. **Parallel execution thread safety.** Each worker runs in its own
   context, but shared resources (tool registry, env vars) need
   synchronization. Tentative: workers get independent VM instances;
   tests in parallel can't easily share state by design.

5. **Test discovery for nested suite-only files.** Files with
   `test.suite` but no `test.case` at top level (suites that group
   children). Tentative: recurse into nested suites; warn on
   suites with no test cases at all (likely a bug).

6. **Coverage integration point.** Connects to
   `08-test-framework-coverage.md`. Tentative: `--coverage` enables
   the line-execution event stream; the coverage collector subscribes
   and aggregates.

---

## Capability surface ceiling

Per the capabilities-not-orchestration principle, the test framework
does NOT include:

- **Mocking / stubbing primitives.** A `nodus-mock` registry library
  could provide this in v5.x if real demand emerges.
- **Property-based testing.** Hypothesis-style generators. Out of
  scope; possibly `nodus-property-test` registry library later.
- **Snapshot testing.** Out of scope; possibly `nodus-snapshot` if
  demand emerges.
- **Benchmark / performance testing.** Out of scope; `nodus benchmark`
  CLI or separate tooling.
- **Code coverage rendering beyond basic HTML.** Coverage doc
  covers basic HTML; fancier rendering belongs to external tooling.

---

## Cross-references

- `docs/design/v4/00-phase-0-decisions.md` Decisions 4 and 13 (test
  framework scope and API)
- `docs/design/v4/08-test-framework-coverage.md` (sibling; coverage
  extension)
- `docs/design/v4/11-equality-coercion.md` (sibling; `assert_eq` uses
  v4.0 equality semantics)
- `docs/design/v4/13-err-record-location-fields.md` (sibling;
  assertion failures use the full err record shape)
- `docs/governance/LIBRARY_ECOSYSTEM.md` § Tier 3 (`nodus-mock`,
  `nodus-property-test`, `nodus-snapshot` as deferred libraries)
- `docs/governance/TECH_DEBT.md` (Phase 3B open questions appended)

---

**Phase 1 doc 07-test-framework-api.md: COMPLETE.**
