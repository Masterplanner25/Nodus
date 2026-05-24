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
bounds indices, division by zero. These are catchable with `try/catch`.

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
| `err.line` | number | yes | Source line where the error occurred |
| `err.column` | number | yes | Source column |
| `err.path` | string | yes | Source file path |
| `err.stack` | list | yes | Stack trace as a list of strings |
| `err.payload` | any | **only for non-string throws** | Original thrown value |

> **Spec note:** LANGUAGE_SPEC only documents `message`, `kind`, and `payload`.
> The `line`, `column`, `path`, and `stack` fields are real, usable, and tested
> but not yet in the spec. `err.payload` is absent (not `nil`) on runtime errors
> and string throws — accessing it on a runtime error raises
> `Key error: Missing record field: payload`.

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

### finally semantics

`finally` runs after `try` completes (with or without an error) and after
`catch` completes. One known limitation: **`finally` does not run when the
`catch` block contains a `return`** (tracked as a v2.2 bug). In all other
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
}
```

Output:

```
thrown
value must be positive
```

`err.kind` is always `"thrown"` for explicit throws. `err.payload` is absent
for string throws — do not access it.

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

| `err.kind` | What triggers it | Example message |
|------------|-----------------|-----------------|
| `"type"` | Type mismatch in operation | `Cannot add number and string` |
| `"key"` | Missing map key | `Missing map key: "field"` |
| `"index"` | List index out of range | `List index out of range: 10` |
| `"name"` | Undefined variable | `Undefined variable: x` |
| `"call"` | Wrong arity, call a non-function | `add expected 2 args, got 1` |
| `"runtime"` | Division by zero, stdlib failures | `Division by zero` |
| `"sandbox"` | Call stack overflow, path traversal | `Call stack overflow` |
| `"thrown"` | Any `throw` statement | the thrown value as string |

**Notes:**

- `"runtime"` is a catch-all for VM-level errors that don't fit a more specific
  kind. Division by zero, `json.parse` failures, and `fs.read` failures all
  surface as `"runtime"`.
- `"sandbox"` is also used for execution step-limit and time-limit exceeded, but
  those cannot be caught from inside the script — they terminate execution
  immediately.
- Import errors (`Import not found: ...`) have kind `"import"` but are NOT
  catchable. See [Section 6](#6-what-is-not-catchable).
- BUG-027 (v2.1.0): `throw "string"` now correctly sets `err.kind = "thrown"`.
  In v2.0.0 all throws produced `"runtime"`.

---

## 5. When to use try/catch vs. defensive checks

**Use `try/catch`** when failure is a normal, expected outcome at a trust
boundary:
- Reading a file that might not exist
- Parsing JSON from external input that might be malformed
- Calling an operation whose failure you need to respond to gracefully

**Use `has_key` guards** when failure is predictable from data you control:
- Accessing a map key that might be absent
- Checking parsed JSON for optional fields

Using `try/catch` to handle a missing key you could have checked is wasteful
and obscures intent. The `has_key` pattern is faster and clearer. See
[working-with-maps.md](working-with-maps.md#3-reading-from-a-map) and
[working-with-json.md](working-with-json.md#2-inspecting-parsed-data).

### File read pattern

```nd
import "std:fs" as fs
import "std:json" as json

fn load_config(path) {
    try {
        let raw = fs.read(path)
        return json.parse(raw)
    } catch err {
        print("config load failed: " + err.message)
        return nil
    }
}

let cfg = load_config("config.json")
if (cfg == nil) {
    print("using defaults")
}
```

This catches both `fs.read` failures (`"runtime"`, file not found) and
`json.parse` failures (`"runtime"`, malformed JSON) in one handler.

### Re-throw with context

Catch, add information, throw a new error to the caller:

```nd
fn parse_user(raw) {
    try {
        return json.parse(raw)
    } catch err {
        throw "parse_user failed: " + err.message
    }
}
```

---

## 6. What is not catchable

**Parse errors**: Syntax errors, unterminated strings, invalid escape sequences.
These abort at load time before any `try` block can execute.

**Import errors**: `import "./missing_module"` inside a `try` block does not
raise a catchable error — the import silently fails, leaving the module name
undefined. Accessing the undefined name later raises `"name"`. This is a known
v2.2 bug: import errors inside try blocks should be catchable.

**Execution limits**: When `--step-limit` or `--time-limit` is exceeded, the
runtime terminates the script from the outside. The `catch` block never runs.
This is by design — the embedding host needs to be able to kill runaway scripts
regardless of what the script does with error handling.

---

## 7. Stdlib error quality

**BUG-015 (v2.1.0):** Stdlib errors now report your call site, not the
stdlib's internal path. When `fs.read` fails, the error location points to
the line in your script that called `fs.read`, not to a line inside
`std/fs.nd`. This makes stack traces useful.

**Known Python text leaks:** Two stdlib functions pass Python error text
through verbatim:
- `json.parse` failures: `"json_parse failed: Expecting property name enclosed in double quotes"` — Python `json` module wording. Filed as [BUG-038](https://github.com/Masterplanner25/Nodus/issues/39).
- `fs.read` failures: `"read_file failed for 'path': [Errno 2] No such file or directory: 'path'"` — Python `OSError` wording. Similar pattern, not yet filed.

These errors are informative but break the "Nodus error voice" consistency.
The `err.kind` is `"runtime"` for both, so you can catch them; the
`err.message` text you display to users will look Python-flavored until these
are resolved.

---

## 8. See also

- [working-with-maps.md — Reading from a map](working-with-maps.md#3-reading-from-a-map) — `has_key` guard patterns
- [working-with-json.md — Edge cases](working-with-json.md#6-edge-cases-and-gotchas) — json.parse error format
- [standard-library.md](standard-library.md) — each function's error behavior
- [LANGUAGE_SPEC.md — Exception Handling](../language/LANGUAGE_SPEC.md) — formal spec

---

<!--
TESTED EXAMPLES (17 total — files in /tmp/error-tests/)
1.  err_location_fields.nd — err.line, err.column, err.stack confirmed
2.  err_fields.nd — full field list per error category confirmed
3.  kind_type.nd — kind="type", message="Cannot add number and string" confirmed
4.  kind_key.nd — kind="key", message="Missing map key: "missing"" confirmed
5.  kind_index.nd — kind="index", message="List index out of range: 10" confirmed
6.  kind_name.nd — kind="name", message="Undefined variable: undefined_var" confirmed
7.  kind_call.nd — kind="call", arity and non-function cases confirmed
8.  division_zero.nd — kind="runtime", message="Division by zero" confirmed
9.  kind_stdlib_json.nd — kind="runtime", json_parse failed text confirmed
10. kind_stdlib_fs_missing.nd — kind="runtime", read_file failed Python text confirmed
11. stack_overflow.nd — kind="sandbox", message="Call stack overflow" confirmed
12. step_limit.nd — step limit NOT catchable, exits externally confirmed
13. kind_thrown_string.nd — kind="thrown", message=thrown string confirmed
14. kind_thrown_record.nd — kind="thrown", payload.field accessible confirmed
15. kind_thrown_number.nd — kind="thrown", message=str(number) confirmed
16. finally_basic.nd — finally runs on normal exit confirmed
17. finally_catch_return.nd — finally does NOT run when catch returns (BUG)
18. rethrow.nd — throw err re-throws to outer handler confirmed
19. import_in_try_use_m.nd — import in try silently fails; m undefined confirmed
20. import_what_is_m.nd — import at top level fails with Import error confirmed

VERBATIM ERROR MESSAGES CAPTURED:
- "Missing map key: "missing""
- "List index out of range: 10"
- "Undefined variable: undefined_var"
- "Cannot add number and string"
- "Division by zero"
- "json_parse failed: Expecting property name enclosed in double quotes"
- "read_file failed for '...': [Errno 2] No such file or directory: '...'"
- "Call stack overflow"
- "add expected 2 args, got 1"
- "Cannot call non-function: 42.0"

BEHAVIORAL FINDINGS (new — to file as v2.2 bugs):
F21: finally block does NOT run when catch block has a return statement.
     LANGUAGE_SPEC exit path 5 says "return inside catch: finally runs before
     the function returns; the return value is preserved." This is not the case.
     Confirmed: finally_catch_return.nd shows "in catch", "from catch" but no
     "finally ran".
F22: import errors inside try/catch are silently swallowed — the import fails,
     m is undefined, and no error is raised to the catch block. The import
     statement appears to succeed (no exception), but using m later raises
     "name: Undefined variable: m". Not catchable, not propagated.
F23: err.payload is absent (not nil) on string throws. LANGUAGE_SPEC says
     "String throw: err.payload is nil." Actual: the payload field doesn't
     exist on the record for string throws — accessing it raises
     "Key error: Missing record field: payload".
F24: err record has 4 undocumented fields: path, line, column, stack. These
     are usable (e.g. err.line, err.stack[0]) but absent from LANGUAGE_SPEC.
     Not a bug (more fields is better), but a spec gap.
F25: fs.read failure leaks Python OSError text verbatim, parallel to BUG-038
     (json.parse leaks Python json module text). Same architectural pattern.
-->
