# Error Surfaces Policy

This document defines which Nodus stdlib surfaces produce Nodus-voice err records,
what the err record contract guarantees, and how to access the underlying Python
exception detail when debugging.

**Design rationale:** `docs/design/v3/02-python-error-replacement.md`

---

## 1. The Replace contract

When a stdlib function fails at an I/O or parsing boundary, it **returns** an
err record rather than throwing. The err record's `err.message` field contains
only Nodus-voice text — no Python exception class names, no Python stack traces,
no `[Errno N]` prefixes.

This contract has three guarantees:

1. **No Python text in err.message.** Every message follows the style `"<what
   failed>: <specific detail>"` — e.g. `"file not found: \"/missing/file\""`.
2. **Specific err.kind values.** Each failure category has a dedicated kind value
   (see Section 3). User code can branch on `err.kind` without parsing message text.
3. **Catchall coverage.** Any unexpected Python exception in a wrapped surface
   produces an `internal_error` err record instead of leaking an exception. The
   original Python detail is available via `--trace-errors` (see Section 5).

---

## 2. In-scope surfaces

The following stdlib namespaces are Replace-wrapped. Every function in these
namespaces either returns data on success or returns an err record on failure —
it does not throw.

### `std:json`

| Function | What it returns on success | err.kind on failure |
|----------|---------------------------|---------------------|
| `json.parse(s)` | map or list | `parse_error`, `type_error` |
| `json.parse_int(s)` | int | `parse_error` |
| `json.stringify(v)` | string | `type_error` |

### `std:fs`

| Function | What it returns on success | err.kind on failure |
|----------|---------------------------|---------------------|
| `fs.read(path)` | string | `io_error` |
| `fs.write(path, content)` | nil | `io_error` |
| `fs.append(path, content)` | nil | `io_error` |
| `fs.exists(path)` | bool | `io_error` |
| `fs.listdir(path)` | list of strings | `io_error` |
| `fs.mkdir(path)` | nil | `io_error` |
| `fs.delete(path)` | nil | `io_error` |

### `std:math` (error-returning functions)

| Function | err.kind on failure |
|----------|---------------------|
| `math.parse_int(s)` | `parse_error` |
| `math.idiv(a, b)` | `math_error`, `type_error` |
| `math.sqrt(n)` | `value_error` |
| `math.log(n)` | `value_error` |
| `math.pow(a, b)` | `math_error` |

### `std:path` (error-returning functions)

| Function | err.kind on failure |
|----------|---------------------|
| `path.relative(p, base)` | `path_error` |
| `path.absolute(p)` | `path_error` |

### Sandbox checks take precedence

Sandbox validation fires **before** stdlib error wrapping. If a path argument
fails the sandbox check (e.g., it escapes the project root or is outside
`allowed_paths`), the function produces a sandbox error regardless of whether
the underlying file exists or what kind of I/O error would have occurred.

```nd
import "std:fs" as fs

// Absolute paths escape the project root sandbox:
let r = fs.read("/etc/passwd")
// -> Sandbox error: read_file blocked: path escapes project root
// (NOT io_error, even though the file exists or doesn't)

// Relative paths within the project root exercise the io_error path:
let r2 = fs.read("data/missing.json")
// -> err{kind: "io_error", message: "file not found: \"data/missing.json\""}
```

Use relative paths in examples that demonstrate io_error behavior. Absolute
paths will hit the sandbox before reaching the Replace-wrapped I/O layer.

---

## 3. err.kind values for stdlib errors

These kinds are produced by Replace-wrapped surfaces. They are distinct from
the VM-level runtime error kinds (`"type"`, `"key"`, `"index"`, etc.).

| err.kind | When it fires |
|----------|---------------|
| `"parse_error"` | Input string cannot be parsed in the expected format |
| `"type_error"` | Argument is the wrong type for the operation |
| `"value_error"` | Argument is the right type but an invalid value |
| `"math_error"` | Domain or arithmetic error (division by zero, overflow) |
| `"io_error"` | File or path operation failed for an I/O reason |
| `"path_error"` | Path manipulation failed structurally |
| `"internal_error"` | Unexpected Python exception inside a wrapped function |

---

## 4. Out-of-scope surfaces

These surfaces are NOT Replace-wrapped. Python exceptions from them propagate
as-is (as VM-level runtime errors) if they occur. In practice they rarely raise
because they operate on already-validated Nodus values.

- **`std:strings`** — pure string operations; Python `str` methods rarely raise.
- **`std:collections`** — dict/list operations; already covered by VM key/index
  error handling.
- **`std:memory`, `std:runtime`, `std:path` (pure ops)** — operate on internal
  Nodus state; no I/O boundary to wrap.
- **Parser and VM** — already produce Nodus-voice errors; not affected by this
  policy.
- **Embedding boundary** — host Python code calling `NodusRuntime.run()` continues
  to receive Python exceptions. This policy applies to Nodus scripts, not Python
  host code.

---

## 5. Debugging stdlib errors: `--trace-errors`

Replace removes Python text from `err.message`. To recover the underlying Python
exception for debugging:

```sh
nodus run --trace-errors script.nd
```

Or set the environment variable:

```sh
NODUS_TRACE_ERRORS=1 nodus run script.nd
```

When set, every err record produced by a Replace-wrapped surface causes Nodus
to print the original Python exception and traceback to **stderr**. The script's
behavior is unchanged — `err.message` still contains only the Nodus message, and
normal output still goes to stdout.

Example output when `--trace-errors` is active and `fs.read` fails:

```
[trace-errors] in fs.read
  underlying Python exception: FileNotFoundError
  [Errno 2] No such file or directory: 'data/missing.txt'
  Traceback:
    Traceback (most recent call last):
      File ".../nodus/builtins/io.py", line 31, in builtin_read_file
        with open(path, "r", encoding="utf-8-sig") as f:
    FileNotFoundError: [Errno 2] No such file or directory: 'data/missing.txt'
```

The output includes the exception type, the exception message, and the full
Python traceback. `err.message` in the Nodus script still contains only the
Nodus-voice text.

---

## 6. Idiomatic error handling

Check returned err records with `type(x) == "error"`, then branch on `err.kind`:

```nd
import "std:fs" as fs

let content = fs.read("config.json")
if (type(content) == "error") {
    if (content.kind == "io_error") {
        print("file error: " + content.message)
    }
    return nil
}
// use content
```

Prefer `err.kind` branching over `err.message` string matching — kind values are
stable across versions; message wording may be refined.

---

## 7. See also

- [error-handling.md](../guide/error-handling.md) — full err.kind reference and
  try/catch vs. returned-err-record guidance
- [standard-library.md](../guide/standard-library.md) — per-function error
  behavior
- [docs/design/v3/02-python-error-replacement.md](../design/v3/02-python-error-replacement.md)
  — design rationale, message style guide, per-surface exception mapping tables
- [migration/v2-to-v3.md](../migration/v2-to-v3.md) — how to migrate code that
  catches or inspects Python-style error messages
