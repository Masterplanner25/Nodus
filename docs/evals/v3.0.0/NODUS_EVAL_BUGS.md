# Nodus v3.0.0 — Evaluation Bug Report

Evaluator: Claude Code (researcher mode, stress test)
Date: 2026-05-25

---

## CRITICAL

### BUG-E01: json.parse(non-string) throws VM error instead of returning err record
**Severity:** CRITICAL
**Subsystem:** stdlib
**Affects:** v3.0.0
**Repro:**
```nodus
import "std:json" as json
let r = json.parse(123)
print(r.kind)  // never reached — throws instead
```
**Expected:** `err{kind: "type_error", message: "json.parse expects a string"}` returned
**Actual:** VM throws "Type error at ...: json_parse(text) expects a string" — uncatchable without try/catch
**Notes:** `builtin_json_parse` calls `vm.ensure_string(text, ...)` which THROWS, not returns. Design doc 2 §5.1 and error-surfaces.md §2 explicitly say `json.parse` returns `err{kind: "type_error"}` for wrong-type args. This is a design-vs-shipped drift.
- **Blocks v3.0.1 patch:** YES
- **v3.0.0 regression:** YES (design doc specifies this behavior as new)
- **Design doc:** docs/design/v3/02-python-error-replacement.md, docs/policy/error-surfaces.md

---

### BUG-E02: math.sqrt(-1) throws runtime error instead of returning err record
**Severity:** CRITICAL
**Subsystem:** stdlib
**Affects:** v3.0.0
**Repro:**
```nodus
import "std:math" as math
let r = math.sqrt(-1)
print(r.kind)  // never reached — throws instead
```
**Expected:** `err{kind: "value_error", message: "..."}` returned
**Actual:** VM throws "Runtime error at ...: math_sqrt(x) expects a non-negative number"
**Notes:** `builtin_math_sqrt` calls `vm.runtime_error("runtime", ...)` — uses the OLD pre-Replace pattern. error-surfaces.md §2 lists `math.sqrt` as a Replace-wrapped function returning `err.kind="value_error"`. The error kind should be "value_error" not "runtime".
- **Blocks v3.0.1 patch:** YES
- **v3.0.0 regression:** YES (claimed as fixed in v3.0.0)
- **Design doc:** docs/policy/error-surfaces.md

---

### BUG-E03: NodusRuntime host_globals and initial_globals parameters have no effect
**Severity:** CRITICAL
**Subsystem:** embedded-api
**Affects:** v3.0.0
**Repro:**
```python
from nodus import NodusRuntime
rt = NodusRuntime()
result = rt.run_source('print(type(x))', host_globals={"x": 5})
# result: ok=False, error="Undefined variable: x"
```
**Expected:** Script receives `x = 5` (Nodus int), prints "int"
**Actual:** "Undefined variable: x" — variables passed via host_globals are silently ignored
**Notes:** Root cause: `NodusRuntime.run_source()` creates a VM with `host_globals=host_globals`, then passes this VM to `ModuleLoader`. When `ModuleLoader._execute_module()` runs, it calls `vm.reset_program(..., host_globals=self.host_globals)` where `self.host_globals` is `{}` (empty — the loader was never given the host_globals). This OVERWRITES the host_globals set on the VM. The entire documented way to pass data into scripts from the embedding layer is broken. `initial_globals` has the same wiring bug.
- **Blocks v3.0.1 patch:** YES
- **v3.0.0 regression:** Unknown if worked in v2.1.1 (API may be new)
- **Design doc:** docs/design/v3/01-integer-type.md §2.6

---

### BUG-E04: Host Python exceptions swallowed by NodusRuntime.run_source
**Severity:** CRITICAL
**Subsystem:** embedded-api
**Affects:** v3.0.0
**Repro:**
```python
from nodus import NodusRuntime
def throws():
    raise ValueError("host error")
rt = NodusRuntime()
rt.register_function("throws", throws, arity=0)
result = rt.run_source('throws()')
# result: ok=False, error={'kind': 'runtime', 'message': 'host error'}
# NO Python ValueError raised to the host
```
**Expected:** Python `ValueError` re-raised to the host caller; OR behavior clearly documented as "wrapped into error dict"
**Actual:** Host Python exceptions are caught by `run_source`'s generic `except Exception`, formatted as a Nodus error dict, and returned. The Python exception is not re-raised.
**Notes:** Phase 0 decision 4 scope clarification says: "embedding API continues to surface Python exceptions to the Python host. The policy boundary is the Nodus-language/Python-host boundary." This is violated — `_invoke_host_function` does not protect host exception propagation.
- **Blocks v3.0.1 patch:** YES
- **v3.0.0 regression:** May be new embedding API behavior
- **Design doc:** docs/design/v3/00-phase-0-decisions.md, Decision 4

---

## HIGH

### BUG-E05: math.log and math.pow not implemented
**Severity:** HIGH
**Subsystem:** stdlib
**Affects:** v3.0.0
**Repro:**
```nodus
import "std:math" as math
math.log(1.0)  // Key error: Missing module export: log
```
**Expected:** `math.log(0)` → `err{kind: "value_error"}`, `math.log(-1)` → same, `math.pow(0, -1)` → err
**Actual:** Functions do not exist in std:math
**Notes:** docs/policy/error-surfaces.md §2 explicitly lists `math.log(n)` and `math.pow(a, b)` as Replace-wrapped functions with documented err.kind returns. Neither the stdlib module (math.nd) nor the builtins (builtins/math.py) contain these functions.
- **Blocks v3.0.1 patch:** YES
- **v3.0.0 regression:** Functions never existed if not in v2.x; HIGH because docs claim they exist

---

### BUG-E06: path.relative and path.absolute not implemented
**Severity:** HIGH
**Subsystem:** stdlib
**Affects:** v3.0.0
**Repro:**
```nodus
import "std:path" as path
path.relative("foo", "/abs/bar")  // Key error: Missing module export: relative
```
**Expected:** Functions exist and return `err{kind: "path_error"}` on failure
**Actual:** Functions do not exist in std:path
**Notes:** docs/policy/error-surfaces.md §2 lists both functions as Replace-wrapped with `err.kind="path_error"`. stdlib/path.nd only has join, dirname, basename, ext, stem.
- **Blocks v3.0.1 patch:** YES
- **v3.0.0 regression:** HIGH if these functions were promised for v3.0.0

---

### BUG-E07: fs.mkdir and fs.delete not exported by std:fs
**Severity:** HIGH
**Subsystem:** stdlib
**Affects:** v3.0.0
**Repro:**
```nodus
import "std:fs" as fs
fs.mkdir("mydir")   // Key error: Missing module export: mkdir
fs.delete("file")   // Key error: Missing module export: delete
```
**Expected:** `fs.mkdir(path)` and `fs.delete(path)` available per error-surfaces.md
**Actual:** stdlib/fs.nd exports `ensure_dir` (which calls mkdir) and has no `delete`. `ensure_dir` uses `exist_ok=True` which silently succeeds on existing paths instead of returning an error.
**Notes:** docs/policy/error-surfaces.md §2 explicitly lists `fs.mkdir(path)` and `fs.delete(path)`. `ensure_dir` is a helper that calls mkdir but has different semantics (returns the path, not nil; never errors on existing).
- **Blocks v3.0.1 patch:** YES

---

### BUG-E08: has_key(err_record, key) throws type error — migration guide understates impact
**Severity:** HIGH
**Subsystem:** migration
**Affects:** v3.0.0
**Repro:**
```nodus
import "std:json" as json
let e = json.parse("{bad")
let r = has_key(e, "payload")  // throws: has_key(map, key) expects a map
```
**Expected (per migration guide):** Migration guide says "code using `has_key(err, 'payload')` requires rewriting to `err.payload != nil`"
**Actual:** `has_key` THROWS a type error when called on an err Record, not just "returns wrong value"
**Notes:** Migration guide design doc 3 §7.1 notes this as a "silent semantic change." The actual behavior is a CRASH (runtime exception), which is worse than "silent" and affects any v2.x code that used `has_key` on err records without a surrounding try/catch.
- **Blocks v3.0.1 patch:** Docs fix needed at minimum
- **v3.0.0 regression:** YES — v2.x code calling has_key on err records CRASHES in v3.0

---

### BUG-E09: path.join takes a list argument, not variadic args
**Severity:** HIGH
**Subsystem:** stdlib / docs
**Affects:** v3.0.0
**Repro:**
```nodus
import "std:path" as path
// Correct: path.join(["a", "b", "c"])  → "a\b\c" on Windows
// Wrong: path.join("a", "b", "c", "d")  → arity error
```
**Expected (per CHANGELOG claim about BUG-036):** `path.join` should be variadic (accept multiple string args)
**Actual:** `path.join` takes a single LIST argument and iterates over it internally
**Notes:** The CHANGELOG says BUG-036 fix provides variadic `path.join`. The implementation in stdlib/path.nd takes `fn join(parts)` — a single list. While functional, this is NOT variadic in the conventional sense and contradicts the BUG-036 description.
- **Blocks v3.0.1 patch:** Clarification needed at minimum

---

## MEDIUM

### BUG-E10: catch syntax requires no parens — docs may show wrong syntax
**Severity:** MEDIUM
**Subsystem:** parser / docs
**Affects:** v3.0.0
**Repro:**
```nodus
try { let x = 1 / 0 } catch (e) { print(e.kind) }
// Syntax error: Expected identifier, got '('
```
**Expected:** Parser accepts `catch (e)` OR documentation shows `catch e` (no parens)
**Actual:** Parser requires `catch e` (identifier directly after "catch", no parens). `catch (e)` is a parse error.
**Notes:** Common Nodus patterns use parens for conditions (`if (x)`, `while (x)`), so users naturally try `catch (e)`. If the LANGUAGE_SPEC shows `catch (e)`, that's a doc error.
- **Blocks v3.0.1 patch:** No (workaround: remove parens)

---

### BUG-E11: Unicode non-ASCII characters in identifiers cause "Unexpected character" error
**Severity:** MEDIUM
**Subsystem:** parser
**Affects:** v3.0.0
**Repro:**
```nodus
let café = "coffee"  // Syntax error: Unexpected character '?'
```
**Expected:** Either works (per "Unicode in identifiers" documentation) OR fails with a clear error explaining ASCII-only restriction
**Actual:** "Unexpected character '?'" — the `é` in `café` is not in the lexer's token regex (`[A-Za-z_][A-Za-z0-9_]*`), treated as an unknown character
**Notes:** The lexer's TOKEN_RE regex only matches ASCII identifiers. No documentation found explicitly saying identifiers are ASCII-only. The error message doesn't explain the restriction.

---

### BUG-E12: 1I (uppercase i) gives name error instead of parse error
**Severity:** MEDIUM
**Subsystem:** parser
**Affects:** v3.0.0
**Repro:**
```nodus
let x = 1I
// Name error: Undefined variable: I
```
**Expected:** Parse error — spec says "1I is a syntax error"
**Actual:** `1I` lexes as `NUM(1)` followed by `ID(I)`, then parser tries to evaluate `I` as a variable — name error at runtime
**Notes:** Design doc 01-integer-type.md §2.1: "The i suffix must be lowercase. 1I, 1Int, 1_i are syntax errors." The implementation doesn't enforce this at parse time — `1I` silently becomes two tokens.

---

### BUG-E13: fs.mkdir with exist_ok=True never errors on existing paths
**Severity:** MEDIUM
**Subsystem:** stdlib
**Affects:** v3.0.0
**Repro:**
```nodus
import "std:fs" as fs
let r = fs.ensure_dir("scratch")  // returns "scratch" (nil expected? path returned)
print(r)  // "scratch" — not nil, not an error
```
**Expected:** Per error-surfaces.md: `fs.mkdir` on existing path → `err{kind: "io_error", message: "path already exists"}`
**Actual:** `os.makedirs(path, exist_ok=True)` — SILENTLY SUCCEEDS on existing paths. `ensure_dir` returns the path string (not nil). No error returned.
**Notes:** The builtin `mkdir` has a `FileExistsError` catch, but `os.makedirs(..., exist_ok=True)` never raises `FileExistsError`. The error case documented in error-surfaces.md is unreachable.

---

### BUG-E14: NodusRuntime top-level run_source returns VM object, not a usable value
**Severity:** MEDIUM
**Subsystem:** embedded-api
**Affects:** v3.0.0
**Repro:**
```python
from nodus import run_source
result = run_source('print(1+1)')
# prints 2.0 to stdout
# result is a VM object, not a return value or output dict
print(result)  # <nodus.vm.vm.VM object at 0x...>
```
**Expected:** Either returns a useful result (output string, return value) OR the docs clearly say "use NodusRuntime.run_source instead"
**Actual:** Top-level `run_source` returns the raw VM object; `NodusRuntime.run_source` returns the proper dict. There are two functions with the same name, different behaviors, different return types.
**Notes:** Confusing API duality. The top-level `run_source` appears to be a legacy/internal function exposed in the public API.

---

### BUG-E15: len() returns float, not int
**Severity:** MEDIUM
**Subsystem:** stdlib
**Affects:** v3.0.0
**Repro:**
```nodus
print(len("hello"))  // 5.0 not 5
print(type(len([1,2])))  // "number" not "int"
```
**Expected:** With the new integer type, `len()` should return int (`5i`) since lengths are always whole numbers
**Actual:** `builtin_len` returns `float(len(value))` — always a float
**Notes:** This makes mixing `len()` with integer arithmetic awkward: `let i = 0i; while (i < len(list))` requires comparison between int (i) and float (len). Works due to coercion but is semantically inconsistent.

---

### BUG-E16: Import path resolution adds .nd extension, breaking imports with explicit .nd suffix
**Severity:** MEDIUM
**Subsystem:** module system
**Affects:** v3.0.0
**Repro:**
```nodus
import "scratch/modA.nd" as mod  // tried: scratch/modA.nd.nd (double .nd!)
// Import not found: 'scratch/modA.nd'
```
**Expected:** Either `import "modA.nd"` works OR the error says "don't include the extension"
**Actual:** Resolution adds `.nd` suffix to the import path, so `"modA.nd"` becomes `"modA.nd.nd"`. Users must import as `"modA"` (no extension) which is not discoverable without docs or errors.
**Notes:** The error message shows the tried paths, so a knowledgeable user can figure it out — but the fix isn't obvious from the error.

---

## LOW

### BUG-E17: type() returns "number" for floats, not "float"
**Severity:** LOW
**Subsystem:** runtime
**Affects:** v3.0.0
**Repro:**
```nodus
print(type(1.0))   // "number"
print(type(1i))    // "int"
```
**Expected:** More consistent naming: either "float"/"int" or "number"/"int"
**Actual:** Float type is "number", int type is "int" — inconsistent naming convention
**Notes:** This is documented per the migration guide ("type(42i) returns 'int' while type(42) returns 'number'"). Not a bug per se, but the inconsistency (using "number" for one and "int" for another) is a design smell.

---

### BUG-E18: Absolute paths to missing files produce sandbox errors, not io_errors
**Severity:** LOW
**Subsystem:** stdlib
**Affects:** v3.0.0
**Repro:**
```nodus
import "std:fs" as fs
let r = fs.read("/missing/file.txt")
// Sandbox error: read_file(path) blocked: path '/missing/file.txt' escapes the project root
```
**Expected:** Per error-surfaces.md: `err{kind: "io_error", message: "file not found: ..."}`
**Actual:** Sandbox check fires before the actual file read — produces sandbox error instead of io_error
**Notes:** This is correct security behavior, but means the error-surfaces.md documentation scenario (testing with an absolute path) doesn't produce the documented io_error. Tests must use relative paths within the project root.

---

### BUG-E19: --trace-errors output format differs from documentation
**Severity:** LOW
**Subsystem:** docs
**Affects:** v3.0.0
**Repro:**
```sh
nodus run --trace-errors script.nd
```
**Expected (per error-surfaces.md §5):**
```
[trace-errors] in fs.read: FileNotFoundError
  [Errno 2] No such file or directory: '/missing/file.txt'
```
**Actual:**
```
[trace-errors] in fs.read
  underlying Python exception: FileNotFoundError
  [Errno 2] No such file or directory: ...
  Traceback:
    ...
```
**Notes:** The actual output is MORE informative than the docs, which is a positive finding. But the format differs. LOW severity because the format improvement is beneficial.

---

### BUG-E20: CHANGELOG summary returned by GitHub API says v3.0.0 is "unreleased"
**Severity:** LOW
**Subsystem:** docs
**Affects:** v3.0.0
**Repro:** GitHub CHANGELOG shows "v3.0.0 (unreleased)" in the summary text visible from the API
**Expected:** "v3.0.0" with a release date since it's on PyPI
**Actual:** "(unreleased)" label in the returned document
**Notes:** May be a stale document or summarization artifact. The package IS on PyPI as 3.0.0.

---

## COSMETIC

### BUG-E21: int arithmetic display shows bare numbers not `Ni` form
**Severity:** COSMETIC
**Subsystem:** runtime
**Affects:** v3.0.0
**Repro:**
```nodus
print(1i + 1i)  // outputs: 2 (not 2i or 2 (int))
print(type(1i + 1i))  // "int" — confirms it IS an int
```
**Expected:** Either `2i` (reinforces the type) or the docs clarify that ints display without suffix
**Actual:** `2` — same display as if it were a float `2.0` would give `2.0`, but `2i+2i` gives `2`. Visually indistinguishable from `2.0` in truncated cases.
**Notes:** Not a functionality bug, but a UX confusion point. Mentioned in CHANGELOG as "whole numbers no longer displaying with trailing zeros" — but the int `2` looks identical to if float `2.0` lost its `.0`.

---

### BUG-E22: json.stringify handles Nodus int without needing math.to_float
**Severity:** COSMETIC
**Subsystem:** docs
**Affects:** v3.0.0
**Notes:** Positive finding — `json.stringify({"count": 5i})` → `{"count": 5}` works directly. The real-task log parser unnecessarily called `math.to_float()` before serialization. Documentation should clarify that Nodus int values serialize as JSON integers natively.

---

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 4 |
| HIGH | 5 |
| MEDIUM | 7 |
| LOW | 4 |
| COSMETIC | 2 |
| **Total** | **22** |

### v3.0.1 patch priorities (CRITICAL + HIGH)
BUG-E01, BUG-E02, BUG-E03, BUG-E04 — embedding API and stdlib Replace violations
BUG-E05, BUG-E06, BUG-E07 — missing documented stdlib functions
BUG-E08 — migration guide understates has_key crash
BUG-E09 — path.join variadic claim vs list impl

### v3.0.0 regressions from v2.1.1
- BUG-E08: has_key(err, key) CRASHES (was presumably functional in v2 where err wasn't a Record type)
- BUG-E01: json.parse(non-string) — if v2 also threw here, not a regression; if v2 returned err, it is
