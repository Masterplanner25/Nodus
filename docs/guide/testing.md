# Testing Nodus Code

This guide covers `std:test` — Nodus's built-in test framework. It handles
everything from simple assertions to async tests with virtual clock control.
Read the async section carefully if you're testing code that uses coroutines,
`sleep`, or spawned tasks — MCP and A2A library tests will need it.

---

## Quick start

Create a file ending in `_test.nd` and run it with `nodus test`:

```nd
import "std:test" as test

test.suite("my first suite", fn() {
    test.case("addition works", fn() {
        test.assert_eq(1i + 1i, 2i)
    })

    test.case("strings work", fn() {
        test.assert_eq("hello " + "world", "hello world")
    })
})
```

```
nodus test tests/
```

---

## Assertions

All assertions follow **actual-first, expected-second** ordering. An optional
message is the last argument and appears in failure output.

### assert(condition, msg?)

Fails if `condition` is falsy (`false`, `nil`, `0`, `0.0`, `""`, `[]`, `{}`).

```nd
import "std:test" as test

test.suite("assert", fn() {
    test.case("truthy values pass", fn() {
        test.assert(true)
        test.assert(1i)
        test.assert("hello")
        test.assert([1i])
    })
})
```

### assert_eq / assert_neq

```nd
import "std:test" as test

test.suite("equality", fn() {
    test.case("numbers", fn() {
        test.assert_eq(2i + 2i, 4i)
        test.assert_neq(2i, 3i)
    })

    test.case("strings", fn() {
        test.assert_eq("hello", "hello")
        test.assert_neq("hello", "world")
    })

    test.case("lists (element-wise)", fn() {
        test.assert_eq([1i, 2i, 3i], [1i, 2i, 3i])
    })
})
```

### assert_err / assert_ok / assert_kind

For testing functions that return err records:

```nd
import "std:test" as test
import "std:tool" as tool

test.suite("err assertions", fn() {
    test.case("assert_ok passes on non-error", fn() {
        let result = test.assert_ok("hello")
        test.assert_eq(result, "hello")
    })

    test.case("assert_err passes on error", fn() {
        let e = tool.lookup("no.such.tool")
        test.assert_err(e)
    })

    test.case("assert_kind checks the kind field", fn() {
        let e = tool.lookup("no.such.tool")
        test.assert_kind(e, "tool_error")
    })
})
```

### assert_throws

Calls `thunk()` and passes only if it throws. Returns the thrown err for inspection:

```nd
import "std:test" as test

test.suite("assert_throws", fn() {
    test.case("function that throws", fn() {
        let e = test.assert_throws(fn() {
            throw "something went wrong"
        })
        test.assert_eq(e.kind, "thrown")
    })
})
```

### assert_close

Float comparison with explicit tolerance. The epsilon argument is required:

```nd
import "std:test" as test

test.suite("float comparison", fn() {
    test.case("close enough", fn() {
        test.assert_close(1.0 / 3.0, 0.333, 0.001)
    })
})
```

### assert_contains / assert_has_key / assert_in_range

```nd
import "std:test" as test

test.suite("structural assertions", fn() {
    test.case("list contains element", fn() {
        test.assert_contains([1i, 2i, 3i], 2i)
    })

    test.case("string contains substring", fn() {
        test.assert_contains("hello world", "world")
    })

    test.case("map has key", fn() {
        test.assert_has_key({name: "alice", age: 30i}, "name")
    })

    test.case("value in range (inclusive)", fn() {
        test.assert_in_range(5.0, 1.0, 10.0)
    })
})
```

---

## Suite structure

### Nested suites

```nd
import "std:test" as test

test.suite("user", fn() {
    test.suite("validation", fn() {
        test.case("rejects empty name", fn() {
            test.assert(len("") == 0i)
        })
    })

    test.suite("authentication", fn() {
        test.case("accepts valid token", fn() {
            test.assert(true)
        })
    })
})
```

### test.skip

```nd
import "std:test" as test

test.suite("work in progress", fn() {
    test.case("completed feature", fn() {
        test.assert_eq(1i + 1i, 2i)
    })

    test.case("not ready yet", fn() {
        test.skip("waiting for API to stabilize")
    })
})
```

---

## Lifecycle hooks

Hooks run around every test in the suite. Outer-suite hooks wrap inner-suite hooks.

```nd
import "std:test" as test

test.suite("with hooks", fn() {
    test.before_all(fn() {
        // runs once before any test in this suite
    })

    test.before_each(fn() {
        // runs before each test
    })

    test.after_each(fn() {
        // runs after each test, even on failure
    })

    test.after_all(fn() {
        // runs once after all tests in this suite
    })

    test.case("t1", fn() { test.assert(true) })
    test.case("t2", fn() { test.assert(true) })
})
```

**Note:** Closures cannot mutate outer `let` variables — use a map to share
state between hooks and test bodies:

```nd
import "std:test" as test

test.suite("shared state via map", fn() {
    let state = {setup_ran: false}

    test.before_all(fn() {
        state.setup_ran = true
    })

    test.case("sees setup result", fn() {
        test.assert(state.setup_ran)
    })
})
```

---

## Fixtures

Fixtures are lazily-evaluated values shared by tests. They run only when a
test actually requests them.

```nd
import "std:test" as test

test.suite("fixtures", fn() {
    test.fixture("greeting", fn() {
        return "hello, world"
    })

    test.case("uses greeting", fn(ctx) {
        let g = ctx.fixture("greeting")
        test.assert_eq(g, "hello, world")
    })
})
```

### Suite scope vs test scope

The default scope is `"test"` — each test gets a fresh value. Suite scope
runs the fixture once and shares it across all tests:

```nd
import "std:test" as test

test.suite("scoped fixtures", fn() {
    test.fixture("shared_value", fn() {
        return {id: "abc"}
    }, "suite")   // one instance for all tests in this suite

    test.case("t1", fn(ctx) {
        test.assert_eq(ctx.fixture("shared_value").id, "abc")
    })

    test.case("t2", fn(ctx) {
        test.assert_eq(ctx.fixture("shared_value").id, "abc")
    })
})
```

### Cleanup

Use `test.cleanup` inside the fixture body to register teardown logic:

```nd
import "std:test" as test
import "std:tool" as tool

test.suite("fixture with cleanup", fn() {
    test.fixture("registered_tool", fn() {
        tool.register({
            name: "test.mock",
            handler: fn(a){ return "mocked" },
            description: "Mock for this test"
        })
        test.cleanup(fn() {
            tool.unregister("test.mock")
        })
        return "test.mock"
    })

    test.case("tool is available", fn(ctx) {
        let name = ctx.fixture("registered_tool")
        test.assert(tool.has(name))
    })
})
```

---

## Parameterized tests

### List form

```nd
import "std:test" as test

test.suite("parameterized", fn() {
    test.parameterize([[1i, 1i, 2i], [2i, 3i, 5i], [10i, 5i, 15i]], fn(a, b, expected) {
        test.case("adds correctly", fn() {
            test.assert_eq(a + b, expected)
        })
    })
})
```

### Map form

```nd
import "std:test" as test

test.suite("map form", fn() {
    test.parameterize([{input: "alice", valid: true}, {input: "", valid: false}], fn(row) {
        test.case("validates name", fn() {
            test.assert_eq(len(row.input) > 0i, row.valid)
        })
    })
})
```

---

## Async tests

Use `test.case_async` for tests that involve coroutines, `sleep`, or spawned
background tasks.

### Basic async test

A `case_async` body runs as a coroutine. Any Nodus coroutine operations
are available:

```nd
import "std:test" as test

test.suite("async", fn() {
    test.case_async("simple background task", fn() {
        let state = {done: false}
        let task = coroutine(fn() {
            sleep(100)
            state.done = true
        })
        spawn(task)

        test.flush_async()        // task runs → calls sleep(100), suspends
        test.advance_clock(200)   // advance virtual clock 200ms → task is overdue
        test.flush_async()        // task wakes, sets state.done = true

        test.assert(state.done)
    })
})
```

### The two-flush pattern

Every test involving `sleep` needs two `flush_async` calls with an
`advance_clock` in between:

```
spawn(task)
   └─ task is queued but hasn't run yet

test.flush_async()          ← step 1
   └─ task runs its first step
   └─ task calls sleep(N), suspends
   └─ wakeup scheduled at virtual_time + N

test.advance_clock(M)       ← step 2  (M > N)
   └─ virtual clock moves forward
   └─ any task with wakeup ≤ new_time enters ready queue

test.flush_async()          ← step 3
   └─ woken tasks run their remaining steps
```

Skipping either flush or the advance produces a test that passes vacuously —
the task never ran.

### Ordering: deterministic by sleep time

When multiple tasks are sleeping, the one with the earlier wakeup runs first:

```nd
import "std:test" as test

test.suite("ordering", fn() {
    test.case_async("short sleep runs before long sleep", fn() {
        let log = []
        let slow = coroutine(fn() {
            sleep(200)
            list_push(log, "slow")
        })
        let fast = coroutine(fn() {
            sleep(50)
            list_push(log, "fast")
        })
        spawn(slow)
        spawn(fast)

        test.flush_async()
        test.advance_clock(300)
        test.flush_async()

        test.assert_eq(log, ["fast", "slow"])
    })
})
```

### Tasks with no sleep

Tasks that don't sleep run in spawn order during a single `flush_async`:

```nd
import "std:test" as test

test.suite("no-sleep ordering", fn() {
    test.case_async("spawn order is execution order", fn() {
        let log = []
        spawn(coroutine(fn() { list_push(log, "first") }))
        spawn(coroutine(fn() { list_push(log, "second") }))
        spawn(coroutine(fn() { list_push(log, "third") }))

        test.flush_async()   // one flush is enough: no sleeps

        test.assert_eq(log, ["first", "second", "third"])
    })
})
```

### State sharing between coroutines and test body

Closures cannot assign to outer `let` variables. Use a map and mutate
fields instead:

```nd
import "std:test" as test

test.suite("state sharing", fn() {
    test.case_async("counter incremented by coroutine", fn() {
        let state = {count: 0i}   // map; fields are mutable from closures

        let worker = coroutine(fn() {
            sleep(10)
            state.count = state.count + 1i   // mutates the map field ✓
        })
        spawn(worker)
        test.flush_async()
        test.advance_clock(50)
        test.flush_async()

        test.assert_eq(state.count, 1i)
    })
})
```

### Library test pattern: deferred response

This is the pattern for testing MCP tool calls, A2A message flows, or any
protocol where a request triggers an asynchronous response:

```nd
import "std:test" as test

test.suite("deferred response pattern", fn() {
    test.case_async("handler responds after delay", fn() {
        let state = {response: nil}

        // Simulate a handler that takes time to respond
        let handler = coroutine(fn() {
            sleep(100)
            state.response = {ok: true, result: "pong"}
        })
        spawn(handler)

        // Before flush: no response yet
        test.assert_eq(state.response, nil)

        test.flush_async()        // handler sleeps for 100ms
        test.advance_clock(200)   // advance past the sleep
        test.flush_async()        // handler responds

        test.assert_ok(state.response)
        test.assert_eq(state.response.ok, true)
    })
})
```

### Library test pattern: parallel tasks

For testing code that fans out to multiple concurrent operations:

```nd
import "std:test" as test

test.suite("parallel operations", fn() {
    test.case_async("all three complete", fn() {
        let state = {a: false, b: false, c: false}

        let ta = coroutine(fn() {
            sleep(100)
            state.a = true
        })
        let tb = coroutine(fn() {
            sleep(50)
            state.b = true
        })
        let tc = coroutine(fn() {
            sleep(200)
            state.c = true
        })
        spawn(ta)
        spawn(tb)
        spawn(tc)

        test.flush_async()         // all three sleep
        test.advance_clock(300)    // all three are overdue
        test.flush_async()         // all three complete

        test.assert(state.a)
        test.assert(state.b)
        test.assert(state.c)
    })
})
```

### Common mistake: single flush

This passes vacuously — the task never ran to completion:

```nd-no-run
// WRONG — task sleeps, but clock never advances so it never wakes
test.case_async("broken", fn() {
    let state = {done: false}
    let task = coroutine(fn() {
        sleep(100)
        state.done = true
    })
    spawn(task)
    test.flush_async()   // task sleeps, suspends
    // missing: advance_clock + second flush_async
    test.assert(state.done)   // fails — state.done is still false
})
```

---

## Test isolation

By default, each test case starts with a clean slate. The framework reverts:

- **Environment variables** — any `env.set` calls are undone after the test
- **Tool registry** — any `tool.register` calls are undone after the test
- **Working directory** — restored to the pre-test value

Example: verifying isolation works:

```nd
import "std:test" as test
import "std:env" as env

test.suite("isolation demo", fn() {
    test.case("sets an env var", fn() {
        env.set("MY_TEST_VAR", "hello")
        test.assert_eq(env.get("MY_TEST_VAR", ""), "hello")
    })

    test.case("env var is gone", fn() {
        test.assert_eq(env.get("MY_TEST_VAR", ""), "")
    })
})
```

### Opt out of isolation

For suites where shared state is intentional:

```nd
import "std:test" as test

test.suite("shared state", fn() {
    // ... tests that intentionally share env / tool state
}, {isolated: false})
```

---

## Running tests

```
nodus test                         # discover and run tests/ directory
nodus test tests/mymodule_test.nd  # run a specific file
nodus test --filter "*auth*"       # run cases matching a glob
nodus test --format json           # JSON Lines output
nodus test --coverage              # collect coverage; writes coverage/
nodus test --bail                  # stop on first failure
nodus test --verbose               # show passing tests too
```

Exit codes: `0` = all pass, `1` = failures, `2` = no tests found.

---

<!-- TESTED 2026-05-28 against Nodus v4.0 dev source
All code blocks verified runnable except:
- The "WRONG — single flush" example is intentionally failing (illustrative)
Key implementation notes confirmed:
- flush_async() is synchronous (no await keyword in Nodus)
- spawn() requires coroutine value, not fn literal
- Closures cannot mutate outer let variables; use map fields
- sleep(N) takes ms as plain number
- advance_clock(N) takes ms as plain number
-->
