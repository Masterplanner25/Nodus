# NODUS v4.0.0 — Filable Findings

Independent post-publish stress test. Every entry cites `EVAL_LOG.md`. Ordered by severity, then subsystem.
No CRITICAL findings. All evidence is from the PyPI install (`nodus-lang==4.0.0`, verified `Nodus 4.0.0`).

---

### BUG-001: Embedded `NodusRuntime()` has no filesystem sandbox by default
**Severity:** HIGH
**Subsystem:** embedding / runtime
**Affects:** v4.0.0
**Repro:**
```python
from nodus import NodusRuntime
rt = NodusRuntime(timeout_ms=None, max_steps=None)
res = rt.run_source('import "std:fs" as fs\nprint(fs.read("../../../../../../Windows/System32/drivers/etc/hosts"))')
print(res["ok"], res["stdout"][:40])   # True, file contents leak
```
**Expected:** Parity with the CLI, which jails to the project root by default and blocks `../` escapes
("escapes the project root"). An embedded host that does not opt into `allowed_paths` should not grant
unrestricted disk read.
**Actual:** The default embedded runtime read `C:\Windows\System32\drivers\etc\hosts` in full. The CLI
blocks the identical path with a sandbox error; the embedded default does not. `allowed_paths=[...]`
DOES block it correctly when passed — so the mitigation exists but is opt-in.
**Fix direction:** Either (a) default the embedded runtime to a project-root jail like the CLI, or
(b) make the open-by-default behavior unmissable at the top of `embedding-nodus.md` with a security
callout. This matters most because the stated primary audience is AI agents running generated code
in an embedded host. (EVAL_LOG #10)

---

### BUG-002: `base64_decode` returns bytes (hex display), contradicting its documented string round-trip
**Severity:** HIGH
**Subsystem:** stdlib / docs
**Affects:** v4.0.0
**Repro:**
```nd
import "std:encoding" as enc
let r = enc.base64_decode(enc.base64_encode("hello world"))
print(r == "hello world")   // false
print(str(r))               // 68656c6c6f20776f726c64  (hex, not "hello world")
```
**Expected:** `docs/guide/standard-library.md` §std:encoding states
`enc.base64_decode(b64)  // "hello world"` — i.e. a string round-trip.
**Actual:** `base64_decode` returns a `bytes` value that prints and compares as hex. The documented
round-trip is impossible as written; `str(bytes)` yields hex, and `== "hello world"` is `false`. No
obvious bytes→string conversion is shown in the doc.
**Fix direction:** Either return a string (matching the doc), or add and document a `bytes.to_string()` /
`decode_utf8()` path and correct the doc comment. (EVAL_LOG #13)

---

### BUG-003: `error-handling.md` claims division by zero is catchable; it is an uncatchable err-as-value
**Severity:** MEDIUM
**Subsystem:** docs / runtime
**Affects:** v4.0.0
**Repro:**
```nd
let caught = false
try { let x = 1i / 0i } catch err { caught = true }
print(caught)   // false — catch never fires
```
**Expected:** `docs/guide/error-handling.md` line 17 lists "division by zero" among errors "catchable
with try/catch", and line 233 documents a catchable `kind:"runtime"` / message `"Division by zero"`.
**Actual:** Integer `1i / 0i` returns an err record *as a value* (`kind:"math_error"`, `origin:"vm"`,
message `"Integer division by zero"`) and never throws, so `try/catch` cannot intercept it. This is the
INTENDED v4 behavior per CHANGELOG ("Doc 09") and the migration guide — the defect is the stale
error-handling.md claim, which directly contradicts shipped behavior.
**Fix direction:** Update error-handling.md: int div/mod by zero is an err-as-value (check
`type(x) == "error"`), not a throw; float div by zero is `inf`/`nan`. Remove the "catchable" claim.
(EVAL_LOG #15, #22)

---

### BUG-004: A workflow step that divides by zero reports success and runs downstream steps
**Severity:** MEDIUM
**Subsystem:** workflow / runtime
**Affects:** v4.0.0
**Repro:**
```nd
workflow wf {
    step good { print("good") }
    step will_fail after good { let x = 1i / 0i }
    step downstream after will_fail { print("downstream ran") }
}
let r = run_workflow(wf)
print(r["failed"])   // []  — failure not recorded; "downstream ran" prints
```
**Expected:** A step that hits an arithmetic error should mark the step failed and skip dependents,
the way an explicit `throw` does (verified: `throw` correctly yields `failed:["task_2"]` and skips
downstream).
**Actual:** Because `1i/0i` is an err-VALUE (not thrown — see BUG-003), the step "succeeds",
`r["failed"]` is empty, and `downstream` runs. `docs/guide/workflows-and-tasks.md` §5 even uses
`1 / 0` as its canonical failing-step example and claims `r["error"]="Division by zero"` and
`r["failed"]=["task_2"]` — neither happens (the result map has no `"error"` key at all).
**Fix direction:** Either treat an err-value returned from a step body as a step failure, or fix the
doc example to use `throw` and document that bare arithmetic errors do not fail a step. (EVAL_LOG #14, #15)

---

### BUG-005: `std:strings` has no `starts_with` / `ends_with` (only `contains`)
**Severity:** MEDIUM
**Subsystem:** stdlib
**Affects:** v4.0.0
**Repro:**
```nd
import "std:strings" as strings
print(strings.ends_with("file.json", ".json"))   // Missing module export: ends_with
```
**Expected:** Prefix/suffix tests are among the most common string operations; a model or human filtering
files by extension reaches for `ends_with` immediately.
**Actual:** No `starts_with`/`ends_with`/`has_prefix`/`has_suffix`. Only `contains` exists, which is a
weaker, less correct substitute (`contains(name, ".json")` matches `.jsonx`, `a.json.bak`, etc.).
**Fix direction:** Add `starts_with`/`ends_with` to `std:strings`. (EVAL_LOG #23)

---

### BUG-006: `break` / `continue` unsupported, and the error is the misleading "Undefined variable: break"
**Severity:** MEDIUM
**Subsystem:** parser / runtime
**Affects:** v4.0.0
**Repro:**
```nd
let i = 0i
while (i < 10i) { if (i == 3i) { break }  print(i)  i = i + 1i }
// Name error: Undefined variable: break
```
**Expected:** Either support `break`/`continue`, or emit "break is not supported in this version of Nodus"
so a reader knows it is a missing feature, not a typo.
**Actual:** `break` parses as an identifier and fails at runtime with `Name error: Undefined variable:
break`. The absence is documented (`LANGUAGE_SPEC.md` line 77: "Mostly stable (missing break/continue)"),
but the runtime message gives no hint that it is an unimplemented keyword.
**Fix direction:** Add a dedicated parser/checker diagnostic for `break`/`continue` keywords. Ideally
implement them. This is a notable AI-authorability gap — idiomatic loop code uses `break`. (EVAL_LOG #17)

---

### BUG-007: Migration guide does not cover the most common v3→v4 break — bare integer literals become floats
**Severity:** MEDIUM
**Subsystem:** docs
**Affects:** v4.0.0
**Repro:**
```nd
print(type(3))   // float  (was effectively int-like in v3)
print(3 / 2)     // 1.5
```
**Expected:** `docs/migration/v3-to-v4.md` to flag that bare numeric literals (`3`, `0`) are now floats,
since virtually every v3 program uses plain integer literals and the change is silent (no error).
**Actual:** The guide covers `type=="number"`, `==` coercion, `index_of`, float div-by-zero, cyclic
workflows, and err fields — all accurate and verified — but never mentions the literal-defaults-to-float
change or the `json.parse` dot→bracket break. A v3 program "half-runs": float arithmetic silently
differs, and `json.parse(...).field` throws "Field access is only supported on records".
**Fix direction:** Add a top-of-guide section: "Integer literals now need the `i` suffix; bare numbers
are floats" and a prominent `json.parse` returns-a-map note. (EVAL_LOG #22)

---

### BUG-008: Doc concurrency example is not Windows-portable (`sys.executable` backslashes break the source)
**Severity:** LOW
**Subsystem:** docs
**Affects:** v4.0.0
**Repro:** Copy the `embedding-nodus.md` "Concurrent async I/O" example verbatim on Windows:
```python
PY = sys.executable          # C:\...\python.exe
rt.run_source(f'... subprocess_run_async(["{PY}", ...]) ...')
# SyntaxError: Unsupported escape sequence: \d   (backslash in path)
```
**Expected:** A copy-paste example should run on the platform a reader is on.
**Actual:** The Windows path's backslashes are injected into Nodus source and parsed as escape
sequences. Replacing with forward slashes fixes it; with that fix the example confirms true concurrency
(3×1s subprocesses in ~1.3s). (EVAL_LOG #18)
**Fix direction:** Use `sys.executable.replace("\\", "/")` or `repr()`-safe injection in the doc example.

---

### BUG-009: Bare `import "std:json"` (no `as`) silently binds nothing
**Severity:** LOW
**Subsystem:** runtime / docs
**Affects:** v4.0.0
**Repro:**
```nd
import "std:json"
let e = json.parse("{}")   // Name error: Undefined variable: json
```
**Expected:** This is documented ("an import without `as` … does not bind any name"), but the failure
mode for a beginner who omits `as` is a confusing "Undefined variable: json" several lines later.
**Actual:** As documented, but easy to trip. A model that writes `import "std:json"` then `json.parse`
gets a name error with no connection to the missing `as`.
**Fix direction:** Consider a checker hint: "module 'std:json' imported without `as`; add `as json`
to use it." (EVAL_LOG #7)

---

### BUG-010: `list` append has two names — `list_push` (builtin) vs `push` (std:collections)
**Severity:** LOW
**Subsystem:** stdlib / docs
**Affects:** v4.0.0
**Repro:**
```nd
let xs = []
xs = push(xs, 1i)        // Undefined function: push   (push is col.push, needs std:collections)
xs = list_push(xs, 1i)   // works (top-level builtin)
```
**Expected:** One obvious way to append to a list.
**Actual:** `list_push` is the no-import builtin; `push` only exists as `col.push` after importing
`std:collections`. Both are documented in the same table region, so reaching for the wrong one is easy.
**Fix direction:** Alias `push` as a top-level builtin too, or clearly separate the two in the docs.
(EVAL_LOG #23)

---

### BUG-011: `for k in m` (iterate a map directly) errors without hinting at `keys(m)`
**Severity:** LOW
**Subsystem:** runtime
**Affects:** v4.0.0
**Repro:**
```nd
let m = {"a": 1i}
for k in m { print(k) }   // Type error: Value is not iterable
```
**Expected:** Maps are iterated via `for k in keys(m)` (documented and works). The error could point there.
**Actual:** "Value is not iterable" — accurate but unhelpful; a reader does not learn that `keys(m)` is
the path. (EVAL_LOG #25)
**Fix direction:** Special-case maps in the for-in type error: "maps are not directly iterable; use
`keys(m)` or `values(m)`".

---

### BUG-012: `await` produces a generic "Undefined variable" rather than a "not supported" hint
**Severity:** LOW
**Subsystem:** parser
**Affects:** v4.0.0
**Repro:**
```nd
let x = await foo()   // Name error: Undefined variable: await
```
**Expected:** Nodus has no `await` keyword (intentional — async is synchronous-looking). A reader
coming from JS/Python benefits from "Nodus has no `await`; async builtins return directly."
**Actual:** `await` is parsed as an identifier → "Undefined variable: await". (EVAL_LOG #5)
**Fix direction:** Recognize `await` (and similar foreign keywords) in the parser and emit a targeted hint.

---

### BUG-013: Em-dash renders as mojibake in `--help` and `stability` output on Windows
**Severity:** COSMETIC
**Subsystem:** cli
**Affects:** v4.0.0
**Repro:** `nodus --help` and `nodus stability` — the em-dash separator prints as `�` on the Windows console.
**Expected:** Correct glyph or an ASCII `-` / `--` fallback.
**Actual:** `STABLE � frozen behavior...` etc. — a UTF-8/cp1252 mismatch on the default Windows console.
**Fix direction:** Emit ASCII separators in CLI help, or force UTF-8 stdout encoding. (EVAL_LOG #2, #25)
