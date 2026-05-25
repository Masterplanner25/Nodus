# Migrating from Nodus v2.x to v3.0

## v2.x end-of-life

**v2.1.1 is the last v2.x release.** With v3.0 published, the v2.x line is
end-of-life: no further patches, including security patches. `pip install
nodus-lang==2.1.1` continues to work — the version is not yanked — but it
receives no future updates.

**The migration path is v2.1.1 → v3.0.** There is no intermediate v2.2 release;
all v2.2 bug fixes were folded into v3.0.

---

## What breaks in v3.0

### 1. `{foo: bar}` is now a record literal, not a map lookup

**v2.x behavior:** `{ foo: bar }` in a map literal context evaluated `foo` and
`bar` as variable expressions — effectively `{ value_of_foo: value_of_bar }`.
This was confusing and undocumented.

**v3.0 behavior:** `{ foo: bar }` with bare (unquoted) identifiers is a
**record literal**. The keys are field names, not variable lookups.

```nd
// v2.x: { host: "localhost" } would look up the variable 'host'
// v3.0: { host: "localhost" } creates a record with a 'host' field

let cfg = { host: "localhost", port: 8080 }  // v3.0: record
print(type(cfg))   // "record"
print(cfg.host)    // "localhost"
```

**If you used `{ key: value }` to create a map:** replace with quoted keys.

```nd
// v2.x (fails silently or gives wrong result)
let m = { host: "localhost" }  // was looking up variable 'host'

// v3.0 equivalent as a map
let m = { "host": "localhost" }

// v3.0 equivalent as a record (if you want dot-access)
let m = { host: "localhost" }
```

**If you want a variable's value as a map key:** use parentheses.

```nd
let mykey = "host"
let m = { (mykey): "localhost" }  // map with dynamic key
```

### 2. Bare identifier as map key is now a parse error

In v2.x, using a bare identifier as a map key produced a runtime error
(variable lookup). In v3.0, it is a **parse error** with a helpful message:

```
bare identifier "host" cannot be a map key.
  - to use the variable's value as the key, write: {(host): ...}
  - to use the literal string "host" as the key, write: {"host": ...}
```

### 3. fs.* and json.* errors are returned, not thrown

**v2.x behavior:** `fs.read`, `json.parse`, and similar stdlib functions
threw a runtime error (kind `"runtime"`) when they failed. You caught them
with `try/catch`, and `err.message` contained Python error text.

**v3.0 behavior:** These functions **return** an err record when they fail.
They do not throw. The err record has Nodus-voice messages and specific kind
values.

**Migration: if you used try/catch:**

```nd
// v2.x
try {
    let content = fs.read("config.json")
    // use content
} catch err {
    if (strings.contains(err.message, "No such file")) {
        print("file missing")
    }
}

// v3.0 equivalent
import "std:fs" as fs

let content = fs.read("config.json")
if (type(content) == "error") {
    if (content.kind == "io_error") {
        print("file missing: " + content.message)
    }
} else {
    // use content
}
```

You can still use `try/catch` in v3.0 — VM-level errors (type mismatches,
index errors) still throw. But returned err records are the preferred pattern
for expected I/O and parse failures.

**If your code checks err.message for Python text:**

```nd
// v2.x (breaks in v3.0)
if (strings.contains(err.message, "No such file or directory")) { ... }

// v3.0 idiomatic
if (err.kind == "io_error" and strings.contains(err.message, "file not found")) { ... }
// or, even simpler
if (err.kind == "io_error") { ... }
```

### 4. New err.kind values

v3.0 introduces specific err.kind values for stdlib failures. If your code
branches on `err.kind == "runtime"` to catch file or JSON errors, it will
no longer match. Update to the specific kinds:

| v2.x kind | v3.0 kind | What changed |
|-----------|-----------|--------------|
| `"runtime"` | `"io_error"` | `fs.read`, `fs.write`, `fs.listdir`, etc. |
| `"runtime"` | `"parse_error"` | `json.parse` failures, `math.parse_int` failures |
| `"runtime"` | `"type_error"` | `json.stringify` with non-serializable value, `math.idiv` with float args |
| `"runtime"` | `"math_error"` | `math.idiv` division by zero |
| (new) | `"value_error"` | Domain errors in math functions (`math.sqrt(-1)`) |
| (new) | `"internal_error"` | Unexpected internal error in a wrapped stdlib function |

### 5. err.payload is always present

**v2.x behavior:** `err.payload` was absent on runtime errors and string throws.
Accessing `err.payload` on a runtime error raised `Key error: Missing record field: payload`.

**v3.0 behavior:** `err.payload` is always present. It is `nil` on runtime
errors and string throws. Accessing it never raises.

```nd
// v2.x: this would raise "Key error: Missing record field: payload"
// v3.0: this prints "nil"
try {
    let x = 1 / 0
} catch err {
    print(err.payload)  // nil
}
```

**If your code guards `err.payload` access:** no migration needed — the guard
is still safe (payload is nil, not absent). If your code avoids `err.payload`
on runtime errors, you can simplify that code.

### 6. Integer type: `type()` returns `"int"` for `42i` values

**v2.x behavior:** No integer type. All numbers were floats; `type(42)` returned
`"number"`.

**v3.0 behavior:** The `int` type exists. `42i` is an integer literal.
`type(42i)` returns `"int"`. `type(42)` still returns `"number"` (floats
are the default).

**If your code checks `type(x) == "number"` and processes values that might
now be integers:** consider whether you need to also check `type(x) == "int"`.
For most arithmetic code, this doesn't matter — integer and float values both
support `+ - * %` and comparison. Division always returns float.

---

## What does NOT break

Most v2.1.1 code works unchanged in v3.0:

- All float arithmetic, comparison, and output behavior is unchanged.
- Map literals `{ "key": value }` with quoted keys work exactly as before.
- `record { key: value }` with the `record` keyword works exactly as before.
- `json.parse` still returns maps for JSON objects and lists for JSON arrays.
- `try/catch` still works for any VM-level error.
- All `std:strings`, `std:collections`, `std:utils`, `std:path`, `std:memory`,
  `std:runtime` APIs are unchanged.
- The `fs.*` functions still perform the same operations — only error behavior
  changed (returned err records instead of thrown errors).
- Embedding API (`NodusRuntime`) is unchanged.

---

## Non-breaking improvements in v3.0 (from the v2.2 merge)

v3.0 includes all the v2.2 bug fixes:

- `finally` now runs correctly in all cases (except the one known case where
  catch has a `return` — still a v3.1 bug).
- Import errors inside function bodies and `if/else` blocks now work correctly.
- Import errors inside `try/catch` blocks now propagate correctly.
- `strings.is_blank` now correctly returns `true` for whitespace-only strings.
- `path.join` now accepts a list of segments: `path.join(["a", "b", "c"])`.
- `path.ext` now returns the leading dot: `path.ext("file.nd")` returns `".nd"`.
- `utils.get(map, key, default)` is a new function for safe map access with default.
- Multi-line map literals work: the value can start on the next line after `:`.
- `err.line`, `err.column`, `err.path`, `err.stack` are now documented fields.
- `type()` and `rt.typeof()` are now consistent and documented.

---

## See also

- [error-handling.md](../guide/error-handling.md) — updated err.kind reference
- [types-and-values.md](../guide/types-and-values.md) — integer type documentation
- [standard-library.md](../guide/standard-library.md) — full stdlib reference for v3.0
- [../policy/error-surfaces.md](../policy/error-surfaces.md) — which stdlib
  surfaces return err records and the wrapping contract
- [CHANGELOG.md](../../CHANGELOG.md) — complete change list with issue references
