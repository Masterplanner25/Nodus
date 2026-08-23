# Debugging

Nodus provides several tools for finding and fixing problems. This guide
covers each one, what it tells you, and when to reach for it.

---

## 1. Error messages

When a script fails at runtime, Nodus prints the error to stderr before
exiting with code 1. The format is:

```
<kind> error at <file>:<line>:<col>: <message>
Stack trace:
  at <function> (<file>:<line>:<col>)
  called from <function> (<file>:<line>:<col>)
  ...
```

Example:

```nd
// runtime_err.nd
let x = 42
print(x)
let m = {}
print(m["missing"])
```

```
$ nodus run runtime_err.nd
Key error at /abs/path/runtime_err.nd:4:9: Missing map key: "missing"
Stack trace:
  at <main> (runtime_err.nd:4:9)
42.0
```

The output before the error (`42.0`) is printed — Nodus runs until the error
fires, not before. The exit code is 1.

**Error kinds and what they mean:**

| Kind | What triggers it |
|------|-----------------|
| `Syntax error` | Invalid syntax — caught before execution |
| `Name error` | Undefined variable or function |
| `Type error` | Wrong type for an operation |
| `Key error` | Missing map key or record field |
| `Index error` | List index out of range |
| `Call error` | Wrong argument count, or calling a non-function |
| `Runtime error` | Division by zero, stdlib failures |
| `Sandbox error` | Step limit, time limit, stdout limit, path restriction |
| `Import error` | Module not found or circular import |

---

## 2. Stack traces inside scripts

When you catch an error with `try/catch`, `err.stack` is a list of strings
with the same content as the printed stack trace. Use it to pinpoint where an
error originated across multiple call levels:

```nd
// err_fields.nd
fn outer() {
    inner()
}

fn inner() {
    let m = {}
    m["missing"]
}

try {
    outer()
} catch err {
    print(err.kind)
    print(err.message)
    print(err.line)
    print(err.stack[0])
    print(err.stack[1])
}
```

```
key
Missing map key: "missing"
7
at inner (err_fields.nd:7:7)
called from outer (err_fields.nd:2:10)
```

`err.line`, `err.column`, `err.path`, and `err.stack` are always present on
caught errors, even though they are not yet in the language spec. See
[error-handling.md §2](error-handling.md#2-try--catch--finally) for the full
field reference.

---

## 3. nodus check — syntax validation

`nodus check` parses and validates a script (or project) without executing it:

```
$ nodus check main.nd
main.nd: OK
```

On a syntax error, it prints the location and exits 1:

```
$ nodus check bad.nd
Syntax error at /abs/path/bad.nd:2:9: Unexpected character '@'
```

**`nodus check` is parse-only.** It validates syntax and catches import
resolution failures, but it does not detect:
- Undefined variable or function references (runtime, not parse-time)
- Type errors
- Missing map keys

This means a script can pass `nodus check` and still fail at runtime. Use
`nodus check` to catch typos and malformed syntax in CI; rely on `nodus run`
to catch logic errors.

### Checking an entire project

`nodus check` with no argument checks the project in the current directory
(requires a `nodus.toml`). With a directory argument it checks that project:

```
$ nodus check src/
```

---

## 4. Print-based debugging

`print()` is the fastest debugging tool for most problems. Use `str()` and
`type()` to inspect values:

```nd
fn process(items) {
    let i = 0
    let total = 0
    while (i < len(items)) {
        print("item " + str(i) + ": " + str(items[i]) + " (" + type(items[i]) + ")")
        total = total + items[i]
        i = i + 1
    }
    return total
}
```

```
item 0.0: 10.0 (number)
item 1.0: 20.0 (number)
item 2.0: 30.0 (number)
item 3.0: 40.0 (number)
```

`type()` returns one of: `"string"`, `"number"`, `"int"`, `"bool"`, `"nil"`,
`"list"`, `"map"`, `"record"`, `"function"`, `"error"`.

For map inspection, `keys(m)` and `values(m)` let you dump the structure of
an unknown map without accessing specific fields.

---

## 5. --trace — VM instruction trace

`--trace` prints every VM instruction to stderr as it executes. Use it to
understand evaluation order, see which branch runs, or confirm a function
is being called:

```
$ nodus run script.nd --trace
[trace] PUSH_CONST      line 4  val=3.0
[trace] PUSH_CONST      line 4  val=4.0
[trace] CALL            line 4  fn=add
[trace] FRAME_SIZE      line 1
[trace] STORE_ARG       line 1
[trace] STORE_ARG       line 1
[trace] LOAD_LOCAL_IDX  line 2
[trace] LOAD_LOCAL_IDX  line 2
[trace] ADD             line 2
[trace] RETURN          line 2
[trace] STORE           line 4  name=x
```

`--trace` is high-volume on any non-trivial script. Use the filtering flags:

| Flag | Effect |
|------|--------|
| `--trace-filter STR` | Only show trace lines containing `STR` |
| `--trace-limit N` | Stop tracing after `N` instructions |
| `--trace-no-loc` | Omit line annotations from each trace line |

```
$ nodus run script.nd --trace --trace-filter CALL
[trace] CALL            line 4  fn=add
[trace] CALL            line 5  fn=print
```

```
$ nodus run script.nd --trace --trace-limit 5
[trace] JUMP            line ?  target=10
[trace] PUSH_CONST      line 4  val=3.0
[trace] PUSH_CONST      line 4  val=4.0
[trace] CALL            line 4  fn=add
[trace] FRAME_SIZE      line 1
```

`--trace-imports` is a separate flag that shows import resolution at startup
time — it is not part of the instruction trace:

```
$ nodus run main.nd --trace-imports
[import] Resolved "./utils" -> /path/to/utils.nd
```

Once the on-disk bytecode cache is warm the paths come from the cached unit
rather than the resolver, and the line says so:

```
$ nodus run main.nd --trace-imports
[import] Resolved (from bytecode cache) "./utils" -> /path/to/utils.nd
```

Either way the whole graph is reported, transitive imports included. Through
v4.1.1 the flag printed **nothing at all** on a warm cache — it fired only on
the first run after `rm -rf .nodus`, which is the run you are least likely to
be debugging ([issue 348](https://github.com/Masterplanner25/Nodus/issues/348)).

---

## 6. --dump-bytecode and nodus dis

`--dump-bytecode` prints the compiled bytecode before executing. `nodus dis`
does the same without executing:

```
$ nodus dis script.nd --loc
Program init:
Function add:
Function main:
  0: JUMP 10
  0: FRAME_SIZE 2  [1:1]
  1: STORE_ARG b  [1:1]
  2: STORE_ARG a  [1:1]
  3: LOAD_LOCAL_IDX 0  [2:12]
  4: LOAD_LOCAL_IDX 1  [2:16]
  5: ADD  [2:16]
  6: RETURN  [2:16]
  0: PUSH_CONST 3.0  [4:13]
  1: PUSH_CONST 4.0  [4:16]
  2: CALL add 2  [4:16]
  3: STORE x  [4:16]
  4: LOAD x  [5:7]
  5: CALL print 1  [5:7]
  6: POP  [5:7]
  7: HALT  [5:7]
```

`--loc` adds `[line:col]` annotations. Without it, only instruction indices
and operands are printed.

`nodus dis` is useful for confirming the optimizer did what you expected,
checking function boundaries, and understanding why a value is on the stack
in an unexpected order.

---

## 7. --step-limit for infinite loop diagnosis

If a script hangs, use `--step-limit` to cut it short and see where it was:

```
$ nodus run loop.nd --step-limit 1000
Sandbox error at /abs/path/loop.nd: Execution step limit exceeded
```

The error message does not include the instruction pointer, but the `--trace`
flag combined with `--step-limit` shows the last instructions before the
limit fired:

```
$ nodus run loop.nd --trace --trace-limit 20 --step-limit 20
[trace] LOAD            line 2  name=i
[trace] PUSH_CONST      line 2  val=1.0
[trace] ADD             line 2
[trace] STORE           line 2  name=i
[trace] JUMP            line 2  target=...
...
Sandbox error at /abs/path/loop.nd: Execution step limit exceeded
```

---

## 8. Interactive debugger

`nodus debug` starts an interactive session paused before the first
instruction:

```
$ nodus debug script.nd
```

Supported commands at the debug prompt:

| Command | Effect |
|---------|--------|
| `step` | Execute one instruction |
| `next` | Step over — execute until next source line |
| `out` / `stepout` | Step out of the current function |
| `continue` / `run` | Run until next breakpoint or end |
| `break <line>` | Set breakpoint at line in current file |
| `break <file>:<line>` | Set breakpoint in a specific file |
| `print <variable>` | Print a variable's current value |
| `locals` | Print all locals in the current frame |
| `stack` | Print the current call stack |
| `quit` | Exit the debugger |

For IDE integration via the Debug Adapter Protocol, use `nodus dap`. See
[docs/tooling/DEBUGGING.md](../tooling/DEBUGGING.md) for DAP configuration.

---

## 9. Common diagnostic patterns

### The behaviour contradicts the code you are reading

Before debugging anything else, check *which* Nodus is running. An installed
`nodus-lang` in a virtualenv can shadow a newer working copy, and nothing in
normal output says which tree was loaded — so a fix you just made appears to
have no effect, or a bug you already fixed appears to come back.

`nodus doctor` answers it directly:

```
$ nodus doctor
[  ok  ] nodus package: 5.1.0 from source checkout at /path/to/src/nodus
[  ok  ] version sync: installed nodus-lang==5.1.0 matches the imported module
[  ok  ] interpreter: CPython 3.11.9 at /path/to/.venv/bin/python
[  ok  ] optional extras: nodus-retry is installed (@retry uses the durable effect store)
[  ok  ] project: no nodus.toml in /path/to/project (running in script mode)
[  ok  ] workflow store: 41 recorded run(s) under /path/to/project/.nodus/workflow_framework/runs

No problems found.
```

A mismatch is reported as a failure and the command exits 1:

```
[ FAIL ] version sync: imported module is 5.2.0 but installed nodus-lang is 5.1.0
```

Other checks worth knowing:

- **optional extras** — `@retry` falls back to an in-memory effect store when
  `nodus-lang[retry]` is absent, which is why a suite can pass locally and fail
  on a clean machine.
- **workflow store** — warns past ~500 accumulated runs, because listing them
  scans every record. `nodus workflow cleanup` prunes.

`nodus doctor --json` emits the same report for scripting. The command performs
no writes: it will not create `.nodus/`, touch the bytecode cache, or migrate
anything, so it is safe to run against an installation you suspect is broken.

### "Undefined variable" but the name looks right

The most common cause is an import placed inside a function or block. Imports
must be at the file's top level. An import inside a function body compiles
successfully but the alias is never bound at call time:

```nd
// WRONG
fn do_work() {
    import "./helpers" as h   // silently fails
    return h.ping()           // Name error: Undefined variable: h
}
```

Fix: move the import to the top of the file. See
[modules-and-imports.md §6](modules-and-imports.md#6-constraints).

### A caught error has no `payload` field

`err.payload` is only present when you `throw` a non-string value (a record
or list). On runtime errors and string throws, accessing `err.payload` raises
`Key error: Missing record field: payload`. Use `has_key(err, "payload")` to
check before accessing.

### Stack overflow error

Infinite recursion produces a stack trace capped at the innermost 20 frames,
followed by a count of the rest:

```
Sandbox error at /abs/path/deep.nd:1:36: Call stack overflow
Stack trace:
  at recurse (/abs/path/deep.nd:1:36)
  called from recurse (/abs/path/deep.nd:1:36)
  called from recurse (/abs/path/deep.nd:1:36)
  ... (9981 more frames)
```

(20 frame lines are printed; three are shown here.)

The call site in the trace is where the recursive call was made, not the
top of the function. The final count confirms unbounded recursion vs. expected
deep nesting — 9,981 elided frames is a runaway, 12 is not.

> **Through v4.1.1 this trace was not truncated** on the `nodus run` path — it
> printed one line per frame for all 10,000 frames, about **1.5 MB** of stderr
> ([#49](https://github.com/Masterplanner25/Nodus/issues/49)). Your terminal
> truncated it; Nodus did not. On 4.1.1 or earlier, redirect it with
> `nodus run deep.nd 2> trace.txt` and read the head of the file.
>
> With the default 200 ms deadline you usually get `Execution timed out`
> instead, because the run dies before recursion reaches the stack limit. Pass
> `--time-limit 10000` to see the actual overflow.
>
> **The error payload is deliberately not capped** — only the rendered text is.
> `result["errors"][0]["stack"]` from `NodusRuntime` carries every frame, so you
> can slice it your own way before logging:
>
> ```python
> stack = result["errors"][0]["stack"]
> print("\n".join(stack[:20]), f"\n... ({len(stack) - 20} more frames)")
> ```
>
> Setting `max_frames` on the runtime bounds recursion depth, and therefore the
> trace: `NodusRuntime(max_frames=200)` yields 201 entries instead of 10,001.

---

## 10. See also

- [error-handling.md](error-handling.md) — `err.kind` reference, `try/catch`, throw patterns
- [modules-and-imports.md §6](modules-and-imports.md#6-constraints) — import placement constraints and their error messages
- [DEBUGGING.md](../tooling/DEBUGGING.md) — interactive debugger and DAP reference
- [REPL.md](../tooling/REPL.md) — REPL inspection commands (`:dis`, `:trace`, `:modules`)

---

<!--
TESTED COMMANDS (originally run against nodus-lang v2.1.1; reviewed for v3.0):

01: nodus check hello.nd                 → "OK"
02: nodus check syntax_err.nd            → "Syntax error at <abs>/syntax_err.nd:2:9: Unexpected character '@'"  exit 1
03: nodus check runtime_err.nd           → "OK" (confirms parse-only)
04: nodus run runtime_err.nd             → "Key error at ...:4:9: Missing map key: "missing"", stack trace, exit 1
05: nodus run trace_demo.nd --trace      → [trace] lines, output at end
06: nodus run trace_demo.nd --trace --trace-filter CALL    → 2 CALL lines
07: nodus run trace_demo.nd --trace --trace-limit 5        → 5 trace lines
08: nodus run trace_demo.nd --dump-bytecode                → bytecode + output
09: nodus dis trace_demo.nd --loc        → bytecode with [line:col] annotations
10: nodus run step_limit.nd --step-limit 100  → "Execution step limit exceeded", exit 1
11: nodus run deep_stack.nd              → "Call stack overflow", full stack trace, exit 1
12: nodus run import_trace.nd --trace-imports → "[import] Resolved ..." line
13: nodus run err_fields.nd              → err.line=7, err.stack[0] shows at inner, err.stack[1] shows called from outer
14: nodus run print_debug.nd             → per-item debug output with type annotations
15: nodus doctor                         → six checks, "No problems found.", exit 0
    (run 2026-08-22 against v5.1.0 dev source; paths in §9 are generalized from
     the real output, which printed Windows paths under C:\dev\Coding Language)
16: nodus doctor --json                  → {"ok": true, "checks": [...]}, exit 0

BEHAVIORAL FINDINGS:
F32: `nodus debug --help` outputs "File not found: --help" instead of help text.
     BUG-001/002 fixed --help for check/ast/dis in v2.1.0; debug was missed.
     Filed as BUG-047 (#48). RESOLVED in v3.0.

F33: RESOLVED 2026-08-14 (#49) — for real this time. The earlier "RESOLVED in
     v3.0" note was wrong and the issue was reopened on 2026-08-05.
     Why it looked fixed the first time: the 20-frame cap existed in only ONE of
     two stack-trace formatters. diagnostics.py had it; errors.py joined every
     frame, and that is the path `nodus run` uses. Measured on 4.1.1: 10,003
     lines / 1,500,317 bytes of stderr, LARGER than the ~800 KB originally
     reported because stack entries now carry absolute paths (#342).
     Both formatters now call diagnostics.format_stack_section. The same program
     produces 23 lines / 3,195 bytes.
     When re-verifying, pass --time-limit 30: at the default 200 ms deadline the
     run dies with "Execution timed out" before recursion reaches the stack
     limit, which makes the bug look absent whether or not it is.
     The error PAYLOAD stays uncapped by design — result["errors"][0]["stack"]
     carries every frame. Only rendering is capped.

F27: STILL PRESENT — now filed as #348. --trace-imports emits nothing once the
     on-disk bytecode cache is warm. Not the same as #51 (closed/completed),
     which was the in-memory cache within a single run. See the
     modules-and-imports.md findings block for the mechanism.
-->
