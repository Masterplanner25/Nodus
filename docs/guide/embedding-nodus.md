# Embedding Nodus

`NodusRuntime` is the Python API for running Nodus scripts from a host
application. Use it to execute scripts, sandbox filesystem access, inject
host-side functions, and enforce resource limits.

For the full constructor and method reference, see
[EMBEDDING.md](../runtime/EMBEDDING.md).

---

## 1. Installation

```
pip install nodus-lang
```

```python
from nodus import NodusRuntime

rt = NodusRuntime()
result = rt.run_source('print("hello from nodus")')
print(result["stdout"])   # hello from nodus
```

---

## 2. run_source() and the result dict

Every `run_source()` call returns a plain dict. The keys are always present
regardless of whether the script succeeded or failed:

```python
# test_01_happy.py
from nodus import NodusRuntime

rt = NodusRuntime()
result = rt.run_source('print("hello from nodus")')
print("Keys:", sorted(result.keys()))
print("ok:", result["ok"])
print("stdout:", repr(result["stdout"]))
print("stderr:", repr(result["stderr"]))
print("stage:", result["stage"])
print("filename:", result["filename"])
print("result:", result["result"])
print("errors:", result["errors"])
print("error:", result["error"])
```

```
Keys: ['diagnostics', 'error', 'errors', 'filename', 'ok', 'result', 'stage', 'stderr', 'stdout']
ok: True
stdout: 'hello from nodus\n'
stderr: ''
stage: execute
filename: <memory>
result: None
errors: []
error: None
```

### Result dict fields

| Field | Type | Description |
|-------|------|-------------|
| `ok` | `bool` | `True` if the script completed without error |
| `stdout` | `str` | Everything printed by `print()` |
| `stderr` | `str` | Diagnostic output (usually empty) |
| `stage` | `str` | Last stage reached: `"parse"`, `"compile"`, or `"execute"` |
| `filename` | `str` | Source path (`"<memory>"` for `run_source`) |
| `result` | `any` | Return value of the top-level expression (usually `None`) |
| `errors` | `list` | Structured parse errors (populated for `stage="parse"`) |
| `diagnostics` | `list` | Warnings and hints (usually empty) |
| `error` | `dict\|None` | First fatal error; `None` on success (see below) |

The `ok` field is the primary success indicator. Always check `result["ok"]`
before accessing `result["stdout"]` — on failure, `stdout` captures whatever
the script printed before it died.

### Passing a filename

The `filename` keyword argument labels errors with a useful path instead of
`<memory>`:

```python
result = rt.run_source(source, filename="myscript.nd")
```

---

## 3. Handling errors

### Parse errors vs. runtime errors

```python
# test_02_errors.py
from nodus import NodusRuntime

rt = NodusRuntime()

r1 = rt.run_source('let x = @@@')
print("=== Syntax error ===")
print("ok:", r1["ok"])
print("stage:", r1["stage"])
print("error:", r1["error"])

r2 = rt.run_source('let x = nil\nprint(x["key"])')
print("\n=== Runtime error ===")
print("ok:", r2["ok"])
print("stage:", r2["stage"])
print("error:", r2["error"])

r3 = rt.run_source('print(1 / 0)')
print("\n=== Division by zero ===")
print("ok:", r3["ok"])
print("error:", r3["error"])
```

```
=== Syntax error ===
ok: False
stage: parse
error: {'type': 'syntax', 'message': "Unexpected character '@'", 'path': '<memory>', 'line': 1, 'column': 9}

=== Runtime error ===
ok: False
stage: execute
error: {'type': 'runtime', 'kind': 'type', 'message': 'Indexing is only supported on lists and maps', 'path': '<memory>', 'line': 2, 'column': 9, 'stack': ['at <main> (<memory>:2:9)']}

=== Division by zero ===
ok: False
error: {'type': 'runtime', 'kind': 'runtime', 'message': 'Division by zero', 'path': '<memory>', 'line': 1, 'column': 11, 'stack': ['at <main> (<memory>:1:11)']}
```

### The `error` dict

Two shapes depending on `type`:

**Parse errors** (`type: "syntax"`, `stage: "parse"`):

| Field | Description |
|-------|-------------|
| `type` | `"syntax"` |
| `message` | Human-readable description |
| `path` | Source filename |
| `line` | Line number |
| `column` | Column number |

**Runtime errors** (`type: "runtime"`, `stage: "execute"`):

| Field | Description |
|-------|-------------|
| `type` | `"runtime"` |
| `kind` | Error category: `"type"`, `"key"`, `"index"`, `"name"`, `"call"`, `"runtime"`, `"sandbox"`, `"thrown"` |
| `message` | Human-readable description |
| `path` | Source filename |
| `line` | Line number |
| `column` | Column number |
| `stack` | List of stack-trace strings |

The `kind` field mirrors `err.kind` in Nodus's own `catch` blocks. See
[error-handling.md §4](error-handling.md#4-errkind-reference).

**Import errors** (`type: "import"`, `stage: "execute"`) have `kind: "import"`
and are not catchable from inside the script.

### Standard error-check pattern

```python
def run_safe(rt, source, filename="<memory>"):
    result = rt.run_source(source, filename=filename)
    if not result["ok"]:
        e = result["error"]
        if e and e["type"] == "syntax":
            raise ValueError(f"Syntax error at {e['path']}:{e['line']}: {e['message']}")
        elif e:
            raise RuntimeError(f"[{e.get('kind', e['type'])}] {e['message']}")
    return result
```

---

## 4. Execution limits

`NodusRuntime` enforces three independent limits. All three can be set at
construction time and overridden per call.

| Limit | Constructor param | Default |
|-------|------------------|---------|
| CPU steps | `max_steps` | 10,000,000 |
| Wall-clock time | `timeout_ms` | **200 ms** |
| Output size | `max_stdout_chars` | 20,000 chars |

> **Watch the default timeout.** 200 ms is short enough to fire on legitimate
> computation-heavy scripts. For long-running tasks, pass `timeout_ms=0` to
> disable it or raise it explicitly at construction time.

```python
# test_04_limits.py
from nodus import NodusRuntime

# Step limit
rt = NodusRuntime(max_steps=1000)
r = rt.run_source("let i = 0\nwhile (true) { i = i + 1 }")
print("=== Step limit ===")
print("ok:", r["ok"])
print("error:", r["error"])

# Timeout
rt2 = NodusRuntime(timeout_ms=50)
r2 = rt2.run_source("let i = 0\nwhile (true) { i = i + 1 }")
print("\n=== Timeout ===")
print("ok:", r2["ok"])
print("error:", r2["error"])

# Stdout cap
rt3 = NodusRuntime(max_stdout_chars=100)
long_line = "x" * 80
r3 = rt3.run_source(f'let i = 0\nwhile (i < 1000) {{ print("{long_line}")\ni = i + 1 }}')
print("\n=== Stdout cap ===")
print("ok:", r3["ok"])
print("error:", r3["error"])
print("stdout length:", len(r3["stdout"]))
```

```
=== Step limit ===
ok: False
error: {'type': 'sandbox', 'kind': 'sandbox', 'message': 'Execution step limit exceeded', 'path': '<memory>', 'line': None, 'column': None, 'stack': []}

=== Timeout ===
ok: False
error: {'type': 'sandbox', 'kind': 'sandbox', 'message': 'Execution timed out', 'path': '<memory>', 'line': None, 'column': None, 'stack': []}

=== Stdout cap ===
ok: False
error: {'type': 'sandbox', 'kind': 'sandbox', 'message': 'stdout limit exceeded', 'path': '<memory>', 'line': None, 'column': None, 'stack': []}
stdout length: 81
```

All three produce `kind: "sandbox"`. The `stack` is empty because these errors
originate outside the Nodus VM. The `stdout` field captures whatever was
printed before the limit fired.

### Per-call overrides

Any limit can be overridden for a single call without changing the runtime's
defaults:

```python
# One-off expensive computation
result = rt.run_source(source, max_steps=50_000_000, timeout_ms=5000)
```

Per-call limits do not change the `NodusRuntime` object's defaults; the next
call uses the original construction-time values.

---

## 5. Sandboxing with allowed_paths

Pass `allowed_paths` to restrict which directories the script can access:

```python
rt = NodusRuntime(allowed_paths=["/data/safe"])
```

### What it blocks

Direct builtin calls — `read_file()`, `write_file()` — are blocked for paths
outside the allowed set:

```
error: {'type': 'sandbox', 'kind': 'sandbox',
        'message': "read_file(path) blocked for path: '/tmp/secret.txt'", ...}
```

### BUG-046: stdlib module calls bypass allowed_paths

> **Security note.** In v2.1.0, `allowed_paths` does **not** protect against
> filesystem access through the `std:fs` module. The `fs.read()` and
> `fs.write()` wrappers create a new internal VM that does not receive the
> `allowed_paths` restriction.

Demonstrated:

```python
# test_09_sandbox_direct.py
import os, tempfile
from nodus import NodusRuntime

with tempfile.TemporaryDirectory() as allowed_dir:
    forbidden_dir = tempfile.mkdtemp()
    forbidden_file = os.path.join(forbidden_dir, "secret.txt")
    with open(forbidden_file, "w") as f:
        f.write("classified")
    allowed_file = os.path.join(allowed_dir, "data.txt")
    with open(allowed_file, "w") as f:
        f.write("allowed data")

    forbidden_fwd = forbidden_file.replace("\\", "/")
    allowed_fwd = allowed_file.replace("\\", "/")

    rt = NodusRuntime(allowed_paths=[allowed_dir])

    # Direct builtin: forbidden file is blocked
    r2 = rt.run_source(f'print(read_file("{forbidden_fwd}"))')
    print("Forbidden, direct builtin — ok:", r2["ok"])
    print("error:", r2["error"])

    # Stdlib module: sandbox bypassed
    r3 = rt.run_source(f'import "std:fs" as fs\nprint(fs.read("{forbidden_fwd}"))')
    print("\nForbidden, fs.read (BUG-046) — ok:", r3["ok"])
    print("stdout:", repr(r3["stdout"]))
```

```
Forbidden, direct builtin — ok: False
error: {'type': 'sandbox', 'kind': 'sandbox',
        'message': "read_file(path) blocked for path: '...'", ...}

Forbidden, fs.read (BUG-046) — ok: True
stdout: 'classified\n'
```

Until BUG-046 ([#47](https://github.com/Masterplanner25/Nodus/issues/47)) is
fixed, do not use `allowed_paths` as the sole defense against untrusted scripts
that import `std:fs`. Consider also blocking stdlib imports at the host level
or running scripts in a process-level sandbox.

---

## 6. Injecting host functions with register_function

`register_function(name, fn, *, arity=None)` makes a Python callable available
to scripts as a first-class Nodus function.

```python
# test_05_register.py
from nodus import NodusRuntime

rt = NodusRuntime()

# Zero-arg
rt.register_function("get_version", lambda: "2.1.0", arity=0)
r = rt.run_source('print("version: " + get_version())')
print(r["stdout"])   # version: 2.1.0

# Two-arg
rt.register_function("add_prefix", lambda prefix, s: prefix + s, arity=2)
r2 = rt.run_source('print(add_prefix(">> ", "hello"))')
print(r2["stdout"])  # >> hello
```

```
version: 2.1.0
>> hello
```

### Returning structured data

A Python `dict` returned from a registered function becomes a Nodus `map`
(bracket access). A Python `list` becomes a Nodus `list`:

```python
rt.register_function("get_config", lambda: {"host": "localhost", "port": 5432}, arity=0)

r = rt.run_source("""
let cfg = get_config()
print(cfg["host"])
print(cfg["port"])
print(type(cfg))
""")
print(r["stdout"])
```

```
localhost
5432
map
```

### Python exceptions become Nodus errors

If a registered function raises a Python exception, the script catches it as a
Nodus error with `err.kind = "runtime"` and `err.message` equal to the
exception's string:

```python
def fail_always():
    raise ValueError("Python-side error")

rt.register_function("fail", fail_always, arity=0)

r = rt.run_source("""
try {
    fail()
} catch err {
    print(err.kind)
    print(err.message)
}
""")
print(r["stdout"])
```

```
runtime
Python-side error
```

### Injecting data via closure

`register_function` is the correct way to make Python data accessible to
scripts. `initial_globals` and `host_globals` parameters exist but do not inject
names into Nodus script scope (the module loader overwrites VM globals at load
time):

```python
data = {"user": "alice", "role": "admin"}
rt.register_function("get_user", lambda: data, arity=0)

r = rt.run_source("""
let u = get_user()
print(u["user"] + " is " + u["role"])
""")
print(r["stdout"])   # alice is admin
```

### Validation

`register_function` raises `ValueError` on misuse:

```python
try:
    rt.register_function("print", lambda x: None, arity=1)
except ValueError as e:
    print(e)   # Cannot override built-in function: print
```

Other checks: empty name, negative arity, invalid arity type.

---

## 7. Type marshaling

### Nodus → Python (return values from registered functions' perspective)

When a Nodus value is passed to a Python registered function as an argument, or
captured via a callback, it is converted as follows:

| Nodus type | Python type | Note |
|-----------|-------------|------|
| `string` | `str` | |
| `number` (whole) | `int` | `42` → `42` (int), not `42.0` |
| `number` (fractional) | `float` | `3.14` → `3.14` |
| `bool` | `bool` | `true` → `True` |
| `nil` | `None` | |
| `list` | `list` | Elements recursively converted |
| `map` / `record` | `dict` | Keys are strings |

```python
# test_06_marshaling.py
from nodus import NodusRuntime

results = {}
rt = NodusRuntime()
rt.register_function("capture", lambda k, v: results.update({k: v}), arity=2)

rt.run_source("""
capture("str",    "hello")
capture("int",    42)
capture("float",  3.14)
capture("bool_t", true)
capture("nil",    nil)
""")
for k, v in results.items():
    print(f"{k}: {v!r}  ({type(v).__name__})")
```

```
str: 'hello'  (str)
int: 42  (int)
float: 3.14  (float)
bool_t: True  (bool)
nil: None  (NoneType)
```

### Python → Nodus (return values from registered functions)

| Python type | Nodus type | Nodus `print()` output |
|------------|-----------|------------------------|
| `str` | `string` | the string |
| `int` | `number` | `42` |
| `float` | `number` | `3.14` |
| `True` / `False` | `bool` | `true` / `false` |
| `None` | `nil` | `nil` |
| `list` | `list` | accessible via `[i]` |
| `dict` | `map` | accessible via `[key]` |
| `bytes` | unknown | prints as `b'...'` — avoid |

---

## 8. State isolation

Each `run_source()` call creates a fresh VM. Variables from one call are not
visible in the next:

```python
# test_07_isolation.py
from nodus import NodusRuntime

rt = NodusRuntime()
rt.run_source("let counter = 100")
r2 = rt.run_source("""
try {
    print(counter)
} catch err {
    print(err.kind + ": " + err.message)
}
""")
print(r2["stdout"])   # name: Undefined variable: counter
```

```
name: Undefined variable: counter
```

Two `NodusRuntime` instances are fully independent — registered functions,
`allowed_paths`, and limits do not cross:

```python
rt_a = NodusRuntime()
rt_b = NodusRuntime()
rt_a.register_function("only_in_a", lambda: "from a", arity=0)

print(rt_a.run_source('print(only_in_a())')["stdout"])   # from a

r = rt_b.run_source("""
try {
    only_in_a()
} catch err {
    print(err.kind + ": " + err.message)
}
""")
print(r["stdout"])   # name: Undefined function: only_in_a
```

```
from a
name: Undefined function: only_in_a
```

---

## 9. run_file()

`run_file(path)` reads a `.nd` file from disk and executes it. The result dict
is identical to `run_source()` except `filename` contains the actual file path:

```python
# test_08_runfile.py
import os, tempfile
from nodus import NodusRuntime

script_dir = tempfile.mkdtemp()
script_path = os.path.join(script_dir, "greet.nd")
with open(script_path, "w") as f:
    f.write('let name = "world"\nprint("Hello, " + name + "!")\n')

rt = NodusRuntime()
r = rt.run_file(script_path)
print("ok:", r["ok"])
print("filename:", r["filename"])
print("stdout:", repr(r["stdout"]))
```

```
ok: True
filename: C:\Users\...\greet.nd
stdout: 'Hello, world!\n'
```

**Missing file raises `OSError`** (not a result dict). This is unlike
`run_source()`, which always returns a result dict:

```python
try:
    rt.run_file("/nonexistent/path/script.nd")
except OSError as e:
    print(type(e).__name__)   # FileNotFoundError
```

If the file exists but has a syntax error, `run_file` returns a normal result
dict with `ok=False, stage="parse"`.

---

## 10. Production patterns

### Reuse one runtime per logical tenant

`NodusRuntime` construction is cheap, but if you're running many scripts with
the same limits and registered functions, reuse one instance. Registered
functions persist across calls on the same instance; state does not.

```python
# One runtime per request handler (or per session, per user, etc.)
class ScriptEngine:
    def __init__(self, db_conn):
        self._rt = NodusRuntime(
            max_steps=2_000_000,
            timeout_ms=2000,
            max_stdout_chars=50_000,
            allowed_paths=["/data/scripts"],
        )
        self._rt.register_function(
            "query",
            lambda sql: db_conn.fetchall(sql),
            arity=1
        )

    def run(self, source: str, filename: str = "<script>") -> dict:
        return self._rt.run_source(source, filename=filename)
```

### Never trust `ok=True` alone for output

A script that prints nothing still returns `ok=True`. A script that prints
partway through before hitting a step limit returns `ok=False` with partial
`stdout`. Always check `ok` before acting on output.

### Normalize errors for display

The `error` dict is for internal logging. Expose a clean message to end users:

```python
def user_message(result: dict) -> str | None:
    if result["ok"]:
        return None
    e = result["error"]
    if not e:
        return "Script failed (unknown error)"
    if e["type"] == "syntax":
        return f"Syntax error on line {e['line']}: {e['message']}"
    kind = e.get("kind", e["type"])
    return f"Runtime error ({kind}): {e['message']}"
```

### Detect sandbox kills

All three limit types produce `kind: "sandbox"`. You can distinguish them by
message:

```python
def is_limit_exceeded(result: dict) -> bool:
    e = result.get("error")
    return e is not None and e.get("kind") == "sandbox"
```

---

## 11. See also

- [EMBEDDING.md](../runtime/EMBEDDING.md) — full constructor and method reference
- [error-handling.md](error-handling.md) — `err.kind` reference and throw patterns
- [standard-library.md](standard-library.md) — stdlib functions and their error behavior
- [BUG-046 #47](https://github.com/Masterplanner25/Nodus/issues/47) — `allowed_paths` bypass via `std:fs`

---

<!--
TESTED EXAMPLES (9 test files in C:\dev\Nd project\)

test_01_happy.py      — run_source happy path: result dict keys, ok/stdout/stage confirmed
test_02_errors.py     — syntax error (stage=parse), runtime type error, division by zero
test_03b_sandbox.py   — allowed_paths with fs.read: allowed file reads
test_03c_sandbox.py   — allowed_paths with fs.read: forbidden file readable (BUG-046)
test_04_limits.py     — step limit, timeout, stdout cap, per-call override
test_05_register.py   — register_function: zero-arg, two-arg, dict/list return, exception, shadow builtin, data injection
test_06_marshaling.py — Nodus->Python type mapping, Python->Nodus type mapping, whole-float->int
test_07_isolation.py  — state non-persistence, two-instance isolation
test_08_runfile.py    — run_file happy path, missing file raises OSError, syntax error returns result dict
test_09_sandbox_direct.py — allowed_paths: direct builtin blocked, fs.read bypass confirmed

VERBATIM ERROR MESSAGES:
- "Execution step limit exceeded"  (kind: sandbox)
- "Execution timed out"            (kind: sandbox)
- "stdout limit exceeded"          (kind: sandbox)
- "read_file(path) blocked for path: '...'"  (kind: sandbox)
- "Cannot override built-in function: print"  (ValueError from register_function)

BEHAVIORAL FINDINGS (documented, not yet fixed):
F29: initial_globals / host_globals parameters do NOT inject names into Nodus script scope.
     The module loader overwrites VM globals when loading the module.
     Use register_function for data injection instead. Not a bug per se, but undocumented.
F30: run_file() raises OSError for missing files (does not return ok=False result dict).
     Inconsistent with run_source() which always returns a dict.
     Not filed yet — may be intentional.
F31: Nodus whole-number floats (e.g., 42) marshal to Python int, not float.
     This can cause type confusion when writing Python-side code that consumes
     Nodus output and expects float for all numeric values.

BUG-046 (#47) filed this session:
     allowed_paths is bypassed when scripts call std:fs module functions.
     Root cause: NodusModule.invoke_function creates new VM without forwarding allowed_paths.
     Tracking: https://github.com/Masterplanner25/Nodus/issues/47
-->
