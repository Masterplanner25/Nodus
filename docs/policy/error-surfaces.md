# Error Surfaces Policy

**Last reviewed:** 2026-09-07, against 5.12.0

This document defines which Nodus stdlib surfaces produce Nodus-voice err records,
what the err record contract guarantees, and how to access the underlying Python
exception detail when debugging.

**Design rationale:** `docs/design/v3/02-python-error-replacement.md`

---

## 1. The Replace contract

When a stdlib function fails **at an I/O or parsing boundary**, it *returns* an
err record rather than throwing. The err record's `err.message` field contains
only Nodus-voice text — no Python exception class names, no Python stack traces,
no `[Errno N]` prefixes.

This contract has three guarantees:

1. **No Python text in err.message.** Every message follows the style `"<what
   failed>: <specific detail>"` — e.g. `"file not found: \"data/missing.json\""`.
2. **Specific err.kind values.** Each failure category has a dedicated kind value
   (see Section 3). User code can branch on `err.kind` without parsing message text.
3. **Catchall coverage.** Any unexpected Python exception in a wrapped surface
   produces an `internal_error` err record instead of leaking an exception. The
   original Python detail is available via `--trace-errors` (see Section 5).

**"At an I/O or parsing boundary" is load-bearing.** The contract is about
failures the *world* causes — a missing file, malformed input, a domain error.
It is not about calling a function wrongly. See Section 2.1.

---

## 2. In-scope surfaces

The following stdlib namespaces are Replace-wrapped: when the operation itself
fails, they return an err record.

### `std:json`

| Function | Returns on success | err.kind on failure |
|----------|---------------------------|---------------------|
| `json.parse(s)` | map or list | `parse_error`, `type_error` |
| `json.parse_int(s)` | int | `parse_error` |
| `json.stringify(v)` | string | `type_error` |

`std:json` is the one namespace here that returns an err record for a
wrong-typed argument too — `json.parse(5i)` gives `type_error` rather than
throwing.

### `std:fs`

All eleven functions, not the seven an earlier revision listed.

| Function | Returns on success | err.kind on failure |
|----------|---------------------------|---------------------|
| `fs.read(path)` | string | `io_error` |
| `fs.read_bytes(path)` | list of ints | `io_error` |
| `fs.write(path, content)` | nil | `io_error` |
| `fs.write_bytes(path, bytes)` | nil | `io_error` |
| `fs.append(path, content)` | nil | `io_error` |
| `fs.exists(path)` | bool | `io_error` |
| `fs.exists_path(path)` | bool | — (returns `false`, does not fail) |
| `fs.listdir(path)` | list of strings | `io_error` |
| `fs.mkdir(path)` | nil | `io_error` |
| `fs.ensure_dir(path)` | the path | `io_error` |
| `fs.delete(path)` | nil | `io_error` |

The function is `fs.listdir`, not `fs.list_dir`; the latter is not exported and
gives *"Missing module export: list_dir"*.

`fs.ensure_dir` is the idempotent one: an existing **directory** succeeds and
returns the path, missing parents are created, and an existing **file** at the
target is `io_error: path exists and is not a directory`. `fs.mkdir` is the
non-idempotent form and returns `io_error: path already exists` for either.

> **It reported success for every failure until
> [#845](https://github.com/Masterplanner25/Nodus/issues/845).** It was written
> as `mkdir(path); return path` with the result discarded, so a file at the
> target produced the path, no directory, and a later write failing at an
> unrelated call site. The repair that looks obvious — propagate `mkdir`'s error
> — is wrong: `fs.mkdir` fails on an existing directory too, which is the case
> `ensure_dir` exists to absorb.

### `std:math` (error-returning functions only)

| Function | err.kind on failure |
|----------|---------------------|
| `math.parse_int(s)` | `parse_error` |
| `math.idiv(a, b)` | `math_error`, `type_error` |
| `math.sqrt(n)` | `value_error` |
| `math.log(n)` | `value_error` |
| `math.pow(a, b)` | `math_error` |

`std:math` exports 26 functions. The other 21 are pure — `abs`, `ceil`, `floor`,
`min`, `max`, `round`, the bit operations, the `is_*` predicates — and have no
failure mode of their own; given a wrong-typed argument they throw (Section 2.1),
they do not return err records.

### `std:path` (error-returning functions only)

| Function | err.kind on failure |
|----------|---------------------|
| `path.relative(p, base)` | `path_error` |
| `path.absolute(p)` | `path_error` |

The other five (`join`, `basename`, `dirname`, `ext`, `stem`) are string
manipulation with no failure mode.

---

## 2.1 Two ways an in-scope surface still throws

An earlier revision said these namespaces *"do not throw"* and called the sandbox
*"the one case"*. There are two, and knowing which is which decides whether you
write `type(r) == "error"` or `try`/`catch`.

**A. A wrong-typed argument throws `kind="type"`.** This is a programmer error,
caught by argument validation before the I/O boundary is reached, so Replace
never sees it:

```
fs.read(5i)       -> throws  type: read_file(path) expects a string path
fs.mkdir(5i)      -> throws  type: fs.mkdir(path) expects a string path
math.sqrt("a")    -> throws  type: math_sqrt(x) expects a number
```

`std:json` is the exception, as noted above.

**B. A sandbox violation throws `kind="sandbox"`.** Sandbox validation fires
*before* stdlib error wrapping, so a blocked path produces a sandbox error
regardless of whether the file exists or what I/O error would have occurred. The
throw aborts the line, so nothing is assigned and the `type(r) == "error"`
pattern never gets a chance to run.

```nd-no-run
import "std:fs" as fs

// Absolute paths escape the sandbox:
let r = fs.read("/etc/passwd")
// throws -> Sandbox error: read_file(path) blocked ...
// (NOT io_error, whether or not the file exists; nothing is assigned to r)

// Relative paths within the root exercise the io_error path:
let r2 = fs.read("data/missing.json")
// -> err{kind: "io_error", message: "file not found: \"data/missing.json\""}
```

The sandbox *message* differs by how the jail was configured — *"escapes the
project root"* when falling back to the project root, *"blocked for path"* when
an explicit `allowed_paths` was given. `err.kind` is `"sandbox"` either way,
which is the reason Section 6 says to branch on kind rather than message.

Catch either class with `try`/`catch` if it should be recoverable rather than
fatal. Use relative paths in examples meant to demonstrate `io_error`.

---

## 3. err.kind values for stdlib errors

These kinds are produced by Replace-wrapped surfaces. They are distinct from
the VM-level runtime error kinds (`"type"`, `"key"`, `"index"`, `"sandbox"`, …).

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

### The embedding boundary does not raise

An earlier revision said host Python code *"calling `NodusRuntime.run()`
continues to receive Python exceptions"*. There is no `run()` method — the
surface is `run_source()` and `run_file()` — and neither raises for a program
error. Both **return a result dict**, and have since v2.1.0 (BUG-005):

```python
rt = NodusRuntime()
res = rt.run_source("fn main() { let x = 1i / 0i }\nmain()")
# res["ok"] is False, res["error"]["kind"] == "math"   -- no exception raised

res = rt.run_source("fn main( {")
# res["ok"] is False, res["stage"] == "parse"          -- no exception raised
```

So a host checks `res["ok"]` rather than wrapping the call in `try`/`except`.
The parameter *validation* on the constructor still raises — `max_memory_mb=0`
gives a `ValueError` — because that is the host calling Nodus wrongly, which is
the same distinction Section 2.1 draws for guest code.

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
normal output still goes to stdout. Both forms were verified to produce identical
output.

Example, when `fs.read` fails on a missing file:

```
[trace-errors] in fs.read
  underlying Python exception: FileNotFoundError
  [Errno 2] No such file or directory: 'missing.txt'
  Traceback:
    Traceback (most recent call last):
      File ".../nodus/builtins/io.py", in builtin_read_file
        with open(path, "r", encoding="utf-8-sig") as f:
    FileNotFoundError: [Errno 2] No such file or directory: 'missing.txt'
```

The output includes the exception type, the exception message, and the full
Python traceback. `err.message` in the Nodus script still contains only the
Nodus-voice text.

---

## 6. Idiomatic error handling

Check returned err records with `type(x) == "error"`, then branch on `err.kind`:

```nd-expect=output
import "std:fs" as fs

fn load_config() {
    let content = fs.read("config.json")
    if (type(content) == "error") {
        if (content.kind == "io_error") {
            print("file error: " + content.message)
        }
        return nil
    }
    return content
}
load_config()
```

```
file error: file not found: "config.json"
```

Prefer `err.kind` branching over `err.message` string matching — kind values are
stable across versions; message wording may be refined, and Section 2.1 gives a
worked example of the same condition carrying two different messages.

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
