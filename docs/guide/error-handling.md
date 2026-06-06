# Error Handling

Nodus errors are values. When your code catches an error, you get a record
with fields describing what went wrong and where. Knowing which `err.kind`
values exist — and what each one means — is the core of productive error
handling in Nodus.

---

## 1. Three categories of error

**Parse errors** happen before your code runs. `nodus run` or `nodus check`
reports them. They are not catchable in code — `try/catch` cannot intercept
a syntax error.

**Runtime errors** happen during execution: missing keys, wrong types, out-of-
bounds indices. These are catchable with `try/catch`.

**Arithmetic errors** (integer division/modulo by zero) are returned as err
values, not thrown. `try/catch` cannot intercept them — use
`type(result) == "error"` to detect them. See [Section 6](#6-what-is-not-catchable).

**Thrown errors** are raised deliberately with `throw`. They are catchable
and carry whatever value you threw.

---

## 2. try / catch / finally

```nd
try {
    // code that might fail
} catch err {
    print(err.kind)
    print(err.message)
} finally {
    print("always runs")
}
```

`finally` requires `catch` — `try/catch/finally` is the only form; `try/finally`
alone is a syntax error.

### What err contains

Inside `catch`, `err` is a record with these fields:

| Field | Type | Always present | Description |
|-------|------|---------------|-------------|
| `err.kind` | string | yes | Error category (see Section 4) |
| `err.message` | string | yes | Human-readable description |
| `err.line` | int | yes | Source line where the error occurred |
| `err.column` | int | yes | Source column |
| `err.path` | string | yes | Source file path |
| `err.stack` | list | yes | Stack trace as a list of strings |
| `err.payload` | any | yes | Original thrown value; `nil` for runtime errors and string throws |

```nd
try {
    let m = {}
    m["missing"]
} catch err {
    print(err.kind)
    print(err.message)
    print(err.line)
    print(err.stack)
}
```

Output:

```
key
Missing map key: "missing"
3
["at <main> (script.nd:3:5)"]
```

**Stdlib-returned err records.** Some stdlib functions return err records as values
instead of throwing — for example `json.parse` returns an err record on invalid JSON,
and `math.sqrt(-1)` returns an err record for a domain error. These have the same shape
as caught errors. The `kind`, `message`, and `payload` fields are always reliable.
The `path`, `line`, and `column` fields are present but may point to stdlib internals
rather than your call site. Treat them as diagnostic hints rather than authoritative
locations. Use `type(result) == "error"` to detect returned err records.

```nd
import "std:json" as json

let result = json.parse("{bad")
if (type(result) == "error") {
    print(result.kind)    // "parse_error"
    print(result.message) // "invalid JSON at line 1 column 2: ..."
}
```

### finally semantics

`finally` runs after `try` completes (with or without an error) and after
`catch` completes. One known limitation: **`finally` does not run when the
`catch` block contains a `return`** (tracked as a v3.1 bug). In all other
exit paths the spec describes, `finally` runs correctly.

```nd
fn divide(a, b) {
    try {
        if (b == 0) { throw "divide by zero" }
        return a / b
    } catch err {
        print("caught: " + err.message)
        return -1
    } finally {
        print("cleanup")
    }
}

print(divide(10, 2))
print(divide(10, 0))
```

Output:

```
cleanup
5.0
caught: divide by zero
-1.0
```

Note that `cleanup` prints for the non-error case but not for the error case,
because `finally` is skipped when `catch` returns.

### Re-throwing

`throw err` inside a `catch` block re-throws the caught error to the next
handler up the call stack:

```nd
fn inner() { throw "inner error" }

fn outer() {
    try {
        inner()
    } catch err {
        print("outer caught: " + err.message)
        throw err
    }
}

try {
    outer()
} catch err {
    print("top caught: " + err.kind + " - " + err.message)
}
```

Output:

```
outer caught: inner error
top caught: thrown - inner error
```

---

## 3. Throwing your own errors

### String throw — simplest case

```nd
fn require_positive(n) {
    if (n <= 0) {
        throw "value must be positive"
    }
    return n
}

try {
    require_positive(-5)
} catch err {
    print(err.kind)
    print(err.message)
    print(err.payload)
}
```

Output:

```
thrown
value must be positive
nil
```

`err.kind` is always `"thrown"` for explicit throws. `err.payload` is `nil`
for string throws.

### Record throw — structured errors

Throw a record to carry structured data to the caller. `err.payload` contains
the original record:

```nd
try {
    throw record { code: 404, reason: "not found" }
} catch err {
    print(err.kind)
    print(err.payload.code)
    print(err.payload.reason)
}
```

Output:

```
thrown
404.0
not found
```

For non-string throws, `err.message` contains a stringified version of the
value, which is rarely useful. Prefer `err.payload` for structured errors.

---

## 4. err.kind reference

### Runtime error kinds (from the VM)

| `err.kind` | What triggers it | Example message |
|------------|-----------------|-----------------|
| `"type"` | Type mismatch in operation | `Cannot add number and string` |
| `"key"` | Missing map key | `Missing map key: "field"` |
| `"index"` | List index out of range | `List index out of range: 10` |
| `"name"` | Undefined variable | `Undefined variable: x` |
| `"call"` | Wrong arity, call a non-function | `add expected 2 args, got 1` |
| `"runtime"` | VM-level failures not covered by other kinds | `Execution limit exceeded` |
| `"sandbox"` | Call stack overflow, path traversal | `Call stack overflow` |
| `"thrown"` | Any `throw` statement | the thrown value as string |

### Stdlib error kinds (from wrapped stdlib functions)

| `err.kind` | What triggers it | Example message |
|------------|-----------------|-----------------|
| `"parse_error"` | Input string cannot be parsed in the expected format | `invalid JSON at line 1 column 2: expected property name` |
| `"type_error"` | Argument is the wrong type for the operation | `math.idiv requires int args, got float` |
| `"value_error"` | Argument is the right type but an invalid value | `math.sqrt requires a non-negative number, got -1` |
| `"math_error"` | Domain or arithmetic error in a math operation | `division by zero` |
| `"io_error"` | File or path operation failed for an I/O reason | `file not found: "/missing/file.txt"` |
| `"path_error"` | Path manipulation failed structurally | (path.relative mixing rel/abs) |
| `"internal_error"` | Unexpected Python exception inside a wrapped stdlib function | `unexpected internal error in fs.read` |

**Important distinctions:**

- `"runtime"` is the VM catch-all for failures not covered by a specific kind.
- **Integer division and modulo by zero** produce a `"math_error"` err record
  **returned as a value** (not thrown). `1i / 0i` does not raise — it returns an
  err record. Check with `type(result) == "error"`. Float division by zero
  returns `inf`/`nan` (not an error). See also
  [v3-to-v4 migration §4](../migration/v3-to-v4.md#4-float-division-by-zero-returns-infnan).
- `"type_error"` (from stdlib) is different from `"type"` (from the VM). Both
  describe type mismatches; the VM raises `"type"` for operators like `+`; stdlib
  functions return `"type_error"` err records.
- `"sandbox"` is also used for execution step-limit and time-limit exceeded, but
  those cannot be caught from inside the script — they terminate execution
  immediately.
- Import errors (`Import not found: ...`) have kind `"import"` but are NOT
  catchable. See [Section 6](#6-what-is-not-catchable).

### Stdlib errors are returned, not thrown

In v3.0, stdlib functions that fail at the I/O or parsing boundary **return**
an err record rather than throwing. This means your code can inspect the err
record without a try/catch:

```nd
import "std:fs" as fs

let content = fs.read("config.json")
if (type(content) == "error") {
    print("read failed: " + content.kind + " — " + content.message)
} else {
    print("read ok: " + str(len(content)) + " bytes")
}
```

The `type(x) == "error"` check is the idiomatic way to detect a returned err
record. Alternatively, branch on `err.kind`:

```nd
import "std:fs" as fs

let content = fs.read("config.json")
if (type(content) == "error" and content.kind == "io_error") {
    print("I/O failure: " + content.message)
}
```

You can still use `try/catch` for stdlib errors, but the returned-value pattern
is preferred for functions where errors are expected outcomes.

---

## 5. When to use try/catch vs. err-record checks

**Use `try/catch`** for:
- VM-level errors you cannot predict (type mismatches, index errors, name errors)
- Code that calls multiple operations and needs one handler for any failure
- Re-throwing with added context

**Use returned err-record checks** for:
- Stdlib I/O and parse functions where failure is a normal expected outcome
- When you need to branch on `err.kind` for different error types
- When you need to continue execution after a failure

**Use `has_key` guards** when failure is predictable from data you control:
- Accessing a map key that might be absent
- Checking parsed JSON for optional fields

### File read pattern (v3.0 style)

```nd
import "std:fs" as fs
import "std:json" as json

fn load_config(path) {
    let raw = fs.read(path)
    if (type(raw) == "error") {
        if (raw.kind == "io_error") {
            print("file error: " + raw.message)
        }
        return nil
    }
    let data = json.parse(raw)
    if (type(data) == "error") {
        print("parse error: " + data.message)
        return nil
    }
    return data
}

let cfg = load_config("config.json")
if (cfg == nil) {
    print("using defaults")
}
```

### Re-throw with context

Catch, add information, throw a new error to the caller:

```nd
fn parse_user(raw) {
    let result = json.parse(raw)
    if (type(result) == "error") {
        throw "parse_user failed: " + result.message
    }
    return result
}
```

---

## 6. What is not catchable

**Arithmetic err-values**: `1i / 0i` and `1i % 0i` return an err record as a
value — they do not throw. `try/catch` never fires for these. The idiomatic
check is:

```nd
let result = a / b
if (type(result) == "error") {
    print("division by zero: " + result.message)
}
```

**Parse errors**: Syntax errors, unterminated strings, invalid escape sequences.
These abort at load time before any `try` block can execute.

**Import errors**: `import "./missing_module"` inside a `try` block does not
raise a catchable error — the import silently fails, leaving the module name
undefined. Accessing the undefined name later raises `"name"`. This is a known
limitation: import errors inside try blocks are not catchable.

**Execution limits**: When `--step-limit` or `--time-limit` is exceeded, the
runtime terminates the script from the outside. The `catch` block never runs.
This is by design — the embedding host needs to be able to kill runaway scripts
regardless of what the script does with error handling.

---

## 7. Stdlib error messages in v3.0

Stdlib functions produce errors in Nodus voice. No Python error text appears
in `err.message`. Concrete examples:

```nd
import "std:fs" as fs

let r = fs.read("/missing/file.txt")
print(r.kind)     // io_error
print(r.message)  // file not found: "/missing/file.txt"
```

```nd
import "std:json" as json

let r = json.parse("{bad")
print(r.kind)     // parse_error
print(r.message)  // invalid JSON at line 1 column 2: expected property name
```

### Debugging stdlib errors

If you need to see the underlying Python exception detail (for debugging a
strange internal error), run with `--trace-errors`:

```sh
nodus run --trace-errors script.nd
```

Or set `NODUS_TRACE_ERRORS=1` in the environment. When set, Nodus prints the
original Python exception and traceback to stderr whenever a wrapped stdlib
function converts a Python exception into an err record. The script's behavior
is unchanged — `err.message` still contains only the Nodus message.

---

## 8. See also

- [working-with-maps.md — Reading from a map](working-with-maps.md#3-reading-from-a-map) — `has_key` guard patterns
- [working-with-json.md — Edge cases](working-with-json.md#6-edge-cases-and-gotchas) — json.parse error format
- [standard-library.md](standard-library.md) — each function's error behavior
- [../policy/error-surfaces.md](../policy/error-surfaces.md) — which stdlib surfaces are wrapped and what the wrapping contract guarantees
- [LANGUAGE_SPEC.md — Exception Handling](../language/LANGUAGE_SPEC.md) — formal spec

---

<!--
TESTED EXAMPLES (v3.0 — all code blocks verified)
1. try/catch/finally basic — confirmed
2. err.line, err.stack — confirmed (note: err.line is now "int" in v3.0, not "number")
3. finally semantics — confirmed (finally skipped when catch returns — known bug)
4. rethrow — confirmed
5. string throw — confirmed (payload is nil, not absent)
6. record throw — confirmed
7. type(content) == "error" pattern — confirmed
8. fs.read missing file: kind="io_error", message starts with "file not found" — confirmed
9. json.parse bad JSON: kind="parse_error", message starts with "invalid JSON" — confirmed
-->
