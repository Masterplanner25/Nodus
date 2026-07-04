# Nodus v3.0.1 — Evaluation Log

**Evaluator:** Claude Code (researcher mode, stress test)
**Date:** 2026-05-25
**Version under test:** nodus-lang 3.0.1 (PyPI)
**Working directory:** C:\dev\Testing Enviroment

---

## SECTION 0 — SETUP

### [00:00] Working directory check
Directory was empty. Created scratch/, migration/, patch-verification/.

### [00:01] Python virtual environment
```
python -m venv .venv
```
Created successfully.

### [00:02] Install nodus-lang==3.0.1
```
pip install nodus-lang==3.0.1
```
Successfully installed nodus-lang-3.0.1 (206 kB wheel). No dependency errors. pip 24.0 notice (non-blocking).

### [00:03] Version confirm
```
nodus --version  →  Nodus 3.0.1
```
PASS.

### [00:04] Working directories created
scratch/, migration/, patch-verification/ all present.

---

## SECTION 1 — RESEARCH PASS

### [01:00] PyPI metadata fetch
- **Package:** nodus-lang 3.0.1
- **Author:** Shawn Knight (Masterplanner25)
- **Release date:** 2026-05-25
- **License:** MIT
- **Python:** ≥3.10 (tested on 3.11/3.12)
- **Dependencies:** Optional FastAPI + uvicorn for server mode
- **Homepage:** https://github.com/Masterplanner25/Nodus

### [01:01] Canonical one-sentence definition
- **README.md:** "A bytecode-compiled scripting language created by Shawn Knight, implementing the Infinity Algorithm's execution model as a first-class language construct, expressed through coroutines, task graphs, workflows, and goals on a deterministic stack-based VM."
- **PyPI JSON API:** "A bytecode-compiled scripting language and distributed workflow runtime implementing the Infinity Algorithm as a first-class language construct."
- **GitHub description:** "Stack-VM scripting language and distributed workflow runtime"
- **LANGUAGE_SPEC:** "a compiled language designed for orchestration, workflows, and task graphs with experimental support for coroutines and channels"

**Assessment:** Consistent in broad strokes (bytecode VM, orchestration focus). Minor phrasing variations. "Infinity Algorithm" named in PyPI/README but absent from LANGUAGE_SPEC — minor identity ambiguity.

### [01:02] CHANGELOG entries

#### [3.0.1] - 2026-05-25
22 issues fixed (#53-#74):
- **Replace contract completion**: json.parse type-checks input, math.sqrt/log/pow wrap errors, fs.mkdir/delete added, path.relative/absolute added
- **Embedding API**: host_globals forwarded correctly, host Python exceptions propagate
- **Docs**: migration guide crash warning for has_key, BUG-E19 trace format docs updated, CHANGELOG date corrected, V3_1_PLAN.md added
- **Polish**: catch (e) syntax, ASCII-only error message, 1I parse error, .nd extension import

#### [3.0.0] - 2026-05-25
Major release. Six breaking changes: record literals, error handling redesign, integer type, import-in-blocks error, finally behavior, string/path changes.

### [01:03] v3.0.0 eval baseline
v3.0.0 eval scored 6.45/10 composite. 22 bugs filed (BUG-E01 to BUG-E22). 4 CRITICAL (embedding API, json.parse throw, math.sqrt throw). All 22 targeted for v3.0.1 closure.

### [01:04] Features flagged for stress testing
- Integer type: large values, mixed arithmetic, json.parse_int
- Embedding API: host_globals, exception propagation
- math.log, math.pow (new in v3.0.1)
- path.relative, path.absolute (new in v3.0.1)
- fs.mkdir (new), fs.delete (new)
- catch (e) syntax (new)
- Import with .nd extension fix
- DeprecationWarning on top-level run_source

### [01:05] Design doc coverage
- docs/design/v3/01-integer-type.md: Retrieved. Specifies 1I as parse error, math.to_float/to_int/etc.
- docs/design/v3/02-python-error-replacement.md: Retrieved. Specifies 4 wrapped namespaces.
- docs/design/v3/03-map-record-disambiguation.md: 404 (not found in main branch)
- docs/design/v3/04-err-record-shape.md: 404 (not found in main branch)
- docs/governance/V3_1_PLAN.md: Retrieved. len() float, type() naming, finally-in-catch-return deferred to v3.1.
- docs/evals/v3.0.0/: Available locally. Used as baseline.
- docs/policy/error-surfaces.md: Retrieved. Sandbox precedence before error wrapping confirmed.
- docs/migration/v2-to-v3.md: Retrieved. has_key crash warning present.

**Ambiguity flagged:** Design docs 03 and 04 returned 404. Either renamed or not committed to main branch. Content inferred from CHANGELOG and test results.

---

## SECTION 2 — BASELINE

### [02:00] nodus run hello.nd
```nodus
print("Hello from Nodus v3.0.1!")
```
Output: `Hello from Nodus v3.0.1!`. Exit 0. PASS.

### [02:01] nodus check hello.nd
Output: `scratch\hello.nd: OK`. Exit 0. PASS.

### [02:02] nodus --help
Shows grouped sections: Execution, Project, Inspection, Orchestration, Server, Tooling, Runtime API, Registry. PASS. BUG-029 #27 still fixed.

### [02:03] nodus run --help
Shows all documented flags including --trace-errors. PASS.

### [02:04] nodus check --help
Shows usage and options. PASS.

### [02:05] nodus workflow --help
Shows subcommands: run, list, resume, cleanup. PASS.

### [02:06] nodus workflow run --help (FINDING)
Output: `File not found: --help`. Exit 1. **FAIL** — treats --help as script filename. Same for `nodus graph run --help`. Subcommands of subcommands do not support --help flag. New finding, not in v3.0.0 eval.

### [02:07] nodus debug --help
Shows debugger commands with step, next, continue, break, print, locals, stack, quit. PASS. BUG-047 fix still holds.

### [02:08] Programmatic API — top-level run_source DeprecationWarning (BUG-E14)
```python
import nodus; nodus.run_source('print(42)')
```
DeprecationWarning fires: "nodus.tooling.loader.run_source() is deprecated and will be removed in v4.0. Use NodusRuntime from nodus.runtime.embedding instead." PASS. Return value is still a VM object (not dict).

### [02:09] NodusRuntime.run_source return shape
Keys: `['ok', 'stage', 'filename', 'stdout', 'stderr', 'result', 'errors', 'diagnostics', 'error']`. ok=True, stdout='2.0\n'. PASS.

### [02:10] NODUS_TRACE_ERRORS env var
```
NODUS_TRACE_ERRORS=1 nodus run script.nd
```
Outputs trace to stderr with `[trace-errors] in fs.read` header, `underlying Python exception: FileNotFoundError`, full traceback. PASS. Format consistent with --trace-errors flag.

---

## SECTION 3 — STRESS TEST

### [03.1] Parser and lexer

**Empty file:** Exit 0, no output. PASS.
**Whitespace-only file:** PASS.
**Comment-only file:** Exit 0, no output. PASS.
**Unicode in strings/comments:** Not tested in isolation (assumed fine per BOM test passing).
**Unicode in identifiers (BUG-E11):** `let café = "coffee"` → `Syntax error: Identifiers must use ASCII letters only: '?'`. Message improved from v3.0.0 "Unexpected character". PASS.
**BOM at file start:** `print("BOM file works")` in UTF-8-BOM file runs correctly. PASS.
**Long identifier (1000 chars):** `let aaa...a = 42` runs without error. PASS.
**1I uppercase suffix (BUG-E12):** `let x = 1I` → `Name error: Undefined variable: I`. NOT a parse error. **FAIL** — patch claimed closure but fix not in 3.0.1.
**Hex int literals (0x10i):** `let x = 0x10i` → `Name error: Undefined variable: x10i`. Not a parse error with a helpful message; internally parsed as `0` then identifier `x10i`. Expected behavior (not supported), message not ideal.
**CRLF mixed:** CRLF file runs correctly. PASS.
**Malformed syntax (unclosed string):** Parser gives syntax error. PASS.
**Mixed CRLF/LF same file:** Not tested separately; CRLF test passed.

### [03.2] Integer type

**Core literals:**
- `type(0i)` → "int" ✓
- `type(1i)` → "int" ✓
- `type(9007199254740993i)` → "int" ✓ (precision preserved)

**Arithmetic:**
- `1i + 1i` → `2` (int) ✓
- `1i + 1` → `2.0` (number) ✓
- `1i + 1.5` → `2.5` (number) ✓
- `1i / 2i` → `0.5` (number, always float) ✓
- `1i % 2i` → `1` (int) ✓

**Comparison:**
- `1i == 1` → true ✓ (coercion preserved per Phase 0 decision 3)
- `1i == 1.0` → true ✓
- `0i == false` → true ✓

**Math functions:**
- `math.parse_int("42")` → 42 (int) ✓
- `math.parse_int("42.0")` → error kind=parse_error ✓
- `math.parse_int("foo")` → error kind=parse_error ✓
- `math.to_int(3.7)` → 3 ✓, `math.to_int(-3.7)` → -3 ✓
- `math.to_float(3i)` → 3.0 ✓
- `math.is_int(3i)` → true ✓, `math.is_int(3.0)` → false ✓
- `math.idiv(7i, 2i)` → 3 ✓
- `math.idiv(7i, 0i)` → error kind=math_error ✓
- `math.idiv(7, 2)` → error kind=type_error ✓

**JSON:**
- `json.parse_int("9007199254740993")` → exact integer ✓
- `json.parse("1")` → 1.0 (float) ✓

**Display:** `1i + 1i` prints as `2` (bare number, no suffix). BUG-E21: documented in V3_1_PLAN as low-risk polish item. PASS (documented).

**Rejected forms:**
- `1I` → name error (NOT parse error) — BUG-E12 NOT FIXED

### [03.3] Type system and values

**Float precision/division:**
- `1.0 / 0.0` → THROWS "Runtime error: Division by zero". Not IEEE 754 infinity. VM-level throw, expected behavior per LANGUAGE_SPEC, but surprising for float division.

**Type names:**
- `type(1)` → "number" ✓
- `type(1i)` → "int" ✓
- `type("hi")` → "string" ✓
- `type(nil)` → "nil" ✓
- `type(true)` → "bool" ✓
- `type([])` → "list" ✓
- `type({"a": 1})` → "map" ✓
- `type({a: 1})` → "record" ✓

**Coercion (Phase 0 decision 3):**
- `0 == false` → true ✓
- `0i == false` → true ✓
- `"" == false` → false (not true — Nodus does not coerce empty string to false in equality)
- `nil == false` → false ✓
- `[] == false` → false
- `"5" == 5` → false ✓

**len() (BUG-E15):**
- `len("hello")` → 5.0 (float). `type(len("hello"))` → "number". Documented in V3_1_PLAN as deferred design item. PASS (documented deferred).

**nil field access:**
- `nil.foo` → type error "Field access is only supported on records". Slightly misleading message (says "on records" not "on nil"), but functional.

**String + number:**
- `5 + "hello"` → type error kind=type ✓

### [03.4] Map and record literals

- `{"foo": "bar"}` → type="map" ✓
- `{foo: "bar"}` → type="record" ✓
- `{(k): "value"}` → type="map" with variable key ✓
- `{foo: 1, "bar": 2}` → parse error with two suggestions ("quote all keys" or "bare identifiers") ✓
- Multi-line map with value on next line → works ✓ (BUG-039 still fixed)

### [03.5] err record shape

**Stdlib err records (json.parse, fs.read, math.sqrt):**
- `err.kind` present ✓
- `err.message` present ✓
- `err.payload` present, nil when no structured data ✓ (BUG-E08 design)
- `err.path` → **MISSING** ("Missing record field: path")
- `err.line` → **MISSING**
- `err.column` → **MISSING**
- `err.stack` → **MISSING**

**VM thrown/runtime errors:**
- All fields present: path, line, column, stack ✓

**Finding:** LANGUAGE_SPEC says all err records have path/line/column/stack. Stdlib err records do NOT. This is a documentation accuracy failure — the spec overstates what stdlib err records contain. VM errors do have the fields; stdlib return-errors don't.

**has_key on err record (BUG-E08):**
- `has_key(e, "payload")` → throws type error "has_key(map, key) expects a map" ✓
- Migration guide now explicitly warns this crashes ✓
- BUG-E08 docs fix: PASS

**err.payload immutability:** Not directly tested (record fields are generally mutable in Nodus).

### [03.6] Control flow

- `else if` → works ✓ (BUG-029 still fixed)
- Deeply recursive function: hits stack limit (sandbox error), e.stack has 10001 frames. BUG-048 cap (20 frames) does NOT apply to `e.stack` list length — only to stderr display. Stack list can be very large.
- `catch e` syntax → works ✓
- `catch (e)` syntax (BUG-E10) → works ✓ PASS
- try/catch/finally with return in catch: `finally` DID run. Contrary to CHANGELOG v3.0.0 note that says "except when catch contains a return statement." Behavior in v3.0.1 is correct (finally always runs). V3_1_PLAN defers this but the fix may already be in place.
- `--step-limit 1000` → fires "Execution step limit exceeded" sandbox error ✓

### [03.7] Module system

- Import nonexistent module → clear error with tried paths ✓
- Circular import detected → "Circular import detected: path → path" ✓
- Path traversal blocked → sandbox error "escapes the project root" ✓
- Import inside function body → clear error "import statements must be at the top level" ✓
- Import with .nd extension (BUG-E16) → works when extension is relative to importing file location ✓ PASS
- Import without .nd extension → also works ✓

### [03.8] Python error replacement

**json:**
- `json.parse("{bad")` → parse_error ✓ (message has no Python text)
- `json.parse("[1, 2,")` → parse_error ✓
- `json.parse(123)` (BUG-E01) → error kind=type_error ✓ PASS
- `json.stringify(some_function)` → not tested directly
- `json.parse_int("abc")` → parse_error ✓
- `json.parse_int("1e9")` → parse_error ✓

**fs:**
- `fs.read("missing.txt")` → io_error ✓
- `fs.read("scratch")` (directory) → io_error ✓ 
- `fs.mkdir("scratch")` (existing) → io_error "path already exists" ✓ (BUG-E07/E13 PASS)
- `fs.mkdir("scratch/newdir_test")` (new) → nil ✓
- `fs.delete("file.txt")` (existing) → nil ✓ (BUG-E07 PASS)
- `fs.delete("nonexistent.txt")` → io_error ✓
- `fs.listdir("scratch/hello.nd")` (file) → io_error ✓

**math:**
- `math.sqrt(-1)` (BUG-E02) → error kind=value_error ✓ PASS. Message: "math.sqrt requires a non-negative number, got -1.0".
- `math.log(0)` → error kind=value_error ✓ (BUG-E05 PASS)
- `math.log(-1)` → error kind=value_error ✓
- `math.log(n, base)` with invalid base (−1) → error kind=value_error ✓
- **`math.log(n, base)` with VALID base (FINDING):** `math.log(100, 10)` = 2.302... (wrong — returns `ln(base)` not `log_base(value)`). `math.log(8, 2)` = 0.693... = `ln(2)`. Arguments appear internally swapped for the two-argument form. HIGH severity new bug.
- `math.pow(0, -1)` → error kind=math_error ✓ (BUG-E05 PASS)
- `math.pow(2, 1000)` → float 1.07e+301 (not error; Python float handles it; not actually overflow for Python floats)

**path:**
- `path.relative("foo", "/abs/bar")` → error kind=path_error ✓ (BUG-E06 PASS)
- `path.absolute("foo")` → resolved string path ✓ (BUG-E06 PASS)
- `path.join([123, "foo"])` → THROWS type error (not Replace-wrapped; expected per error-surfaces.md)

**Trace-errors:**
- `--trace-errors` flag → produces `[trace-errors] in fs.read` with full Python traceback on stderr ✓
- `NODUS_TRACE_ERRORS=1` → same output ✓
- Script stdout unchanged ✓
- math.sqrt(-1) with --trace-errors → no trace output (function doesn't catch Python exception; returns err directly) — EXPECTED, not a bug

**Intentionally unwrapped:**
- `strings.upper(123)` → type error "upper(x) expects a string" (Nodus-voice, no Python text)
- `strings.split("hello")` (wrong arity) → "Stack underflow" (INTERNAL VM error leaking). LOW severity.
- Both consistent with error-surfaces.md "out of scope" designation.

### [03.9] Standard library

**strings:**
- `strings.is_blank("   ")` → true ✓ (BUG-035 still fixed)
- `strings.upper/lower/trim/contains/repeat/replace` → all correct ✓
- `strings.split/join` → work correctly ✓

**collections:**
- `col.map/filter/reduce` → all work ✓
- `has_key(map, key)` → true/false correctly ✓

**utils:**
- `utils.get(map, key, default)` → works ✓

**math:**
- `math.abs/min/max/floor/ceil/sqrt/random` → not exhaustively tested
- `math.parse_int/to_int/to_float/is_int/idiv/log/pow` → tested above

**path:**
- `path.join(["a", "b", "c"])` → "a\b\c" ✓ (list-only, no variadic)
- `path.ext("file.tar.gz")` → ".gz" ✓ (leading dot)
- `path.relative/path.absolute` → work per BUG-E06 ✓

**len():**
- Returns float. BUG-E15 documented in V3_1_PLAN ✓

**path.join variadic test:**
- `path.join("a", "b", "c")` → throws "Indexing is only supported on lists and maps" — confusing error message for wrong-arity call. Expected behavior (variadic not supported per BUG-E09 resolution), message quality MEDIUM.

### [03.10] Migration

**v2 → v3.0.1:**
- `has_key(err, "payload")` crash warning: PRESENT in migration guide ✓ (BUG-E08 PASS)
- Python error text gone from err.message ✓
- Record vs map syntax change documented ✓

**v3.0.0 → v3.0.1:**
- Running v3.0.0 idioms on v3.0.1: all tested patterns work without changes ✓
- No silent behavior changes detected

### [03.11] REPL

Not testable in non-interactive mode. `nodus repl` starts and shows v3.0.1 banner. `:help` and other commands not verified via automation. Documented as limitation.

### [03.12] Workflow / graph runner

**Workflow basic execution:**
```nodus
workflow test_workflow { step A { return 1 } step B after A { return A + 1 } }
run_workflow(test_workflow)
```
Runs silently (no output). Exit 0. PASS.

**Cyclic dependency (FINDING):**
```nodus
workflow cyclic { step A after B { return 1 } step B after A { return 2 } }
run_workflow(cyclic)
```
Returns map `{"error": "Dependency cycle or missing tasks", "tasks": {}, "steps": {}, ...}`. Exit code 0. **The error is embedded in the return map, not raised as an err record or non-zero exit.** BUG-050 was supposed to make cyclic workflows error. They do report an error but not in a user-catchable form and not as a non-zero exit. MEDIUM severity.

**`nodus workflow run --help` / `nodus graph run --help`:**
Both fail with "File not found: --help". MEDIUM severity.

### [03.13] Tracing and observability

- `--trace` → produces instruction-level trace to stderr ✓
- `--trace-imports` → not tested separately
- `--trace-no-loc` → not tested separately
- `--trace-errors` → works ✓ (tested in 3.8)
- `--step-limit` → works ✓
- `nodus debug --help` → shows help ✓ (BUG-047 still fixed)

### [03.14] Error message quality

| Error scenario | WHAT | WHERE | FIX HINT | Nodus voice |
|---|---|---|---|---|
| Invalid JSON | ✓ ("invalid JSON at line 1 column 2: expected property name") | ✓ | — | ✓ |
| File not found | ✓ ("file not found: path") | ✓ | — | ✓ |
| Unicode identifier | ✓ ("Identifiers must use ASCII letters only") | ✓ | — | ✓ |
| Mixed map/record keys | ✓ | ✓ | ✓ (two options) | ✓ |
| Import not found | ✓ (shows tried paths) | ✓ | partial | ✓ |
| Import inside fn | ✓ | ✓ | ✓ ("move to top") | ✓ |
| Circular import | ✓ | ✓ | — | ✓ |
| Path traversal | ✓ | ✓ | — | ✓ |
| Undefined variable | ✓ | ✓ | — | ✓ |
| math.sqrt(-1) | ✓ | ✓ | — | ✓ |
| has_key on record | ✓ ("expects a map") | ✓ | NO (no hint to use .payload) | partial |
| 1I uppercase suffix | NO (name error, not parse) | ✓ | NO | ✗ |
| strings.split arity | ✗ ("Stack underflow") | ✗ | ✗ | ✗ |
| nil field access | partial ("only on records") | ✓ | — | partial |

Overall error message quality: GOOD for wrapped stdlib, GOOD for parser errors, POOR for arity/internal VM errors.

### [03.15] Embedding API

- `NodusRuntime.run_source(source, host_globals={...})` → variables reach script ✓ (BUG-E03 PASS)
  - str → Nodus string ✓
  - Python int → Nodus int ✓ (type shows "int")
  - Python float → Nodus number ✓
  - Python list → Nodus list ✓
  - Python None → Nodus nil ✓
- Host Python exceptions propagate (BUG-E04 PASS):
  - ValueError propagates ✓
  - KeyError propagates ✓
- Two NodusRuntime instances isolated: ✓ (variable set in rt1 not visible in rt2)
- top-level `run_source` DeprecationWarning: ✓ (BUG-E14 PASS)
- Return dict shape: ok, stage, filename, stdout, stderr, result, errors, diagnostics, error ✓

### [03.X] v3.0.1 Patch Closure Verification

| Bug | Claim | Result | Evidence |
|---|---|---|---|
| BUG-E01 (#53) | json.parse(123) returns err | **PASS** | err kind=type_error |
| BUG-E02 (#54) | math.sqrt(-1) returns err | **PASS** | err kind=value_error |
| BUG-E03 (#55) | host_globals reaches script | **PASS** | type(x)="int" for int arg |
| BUG-E04 (#56) | host Python exceptions propagate | **PASS** | ValueError + KeyError both propagate |
| BUG-E05 (#57) | math.log and math.pow exist | **PASS** | Both present; return err on invalid |
| BUG-E06 (#58) | path.relative and path.absolute | **PASS** | Both present; path.relative returns path_error |
| BUG-E07 (#59) | fs.mkdir errors on existing | **PASS** | Returns io_error |
| BUG-E08 (#60) | Migration guide warns has_key crash | **PASS** | "CRITICAL: has_key() Crashes on Error Records" |
| BUG-E09 (#61) | path.join variadic/list docs match | **PASS** | List-arg only; CHANGELOG corrected |
| BUG-E10 (#62) | catch (e) syntax accepted | **PASS** | Works alongside catch e |
| BUG-E11 (#63) | Non-ASCII error message improved | **PASS** | "Identifiers must use ASCII letters only" |
| BUG-E12 (#64) | 1I gives parse error with message | **FAIL** | Still "Name error: Undefined variable: I" |
| BUG-E13 (#65) | fs.mkdir errors on existing | **PASS** | Same as E07 |
| BUG-E14 (#66) | run_source DeprecationWarning | **PASS** | Warning fires with v4.0 removal date |
| BUG-E15 (#67) | len() float documented as v3.1 item | **PASS** | V3_1_PLAN.md present with breaking-change label |
| BUG-E16 (#68) | import with .nd extension works | **PASS** | import "./modA.nd" works |
| BUG-E17 (#69) | type() naming documented as v3.1 item | **PASS** | V3_1_PLAN.md lists three resolution options |
| BUG-E18 (#71) | error-surfaces.md sandbox precedence | **PASS** | "Sandbox validation fires before error wrapping" |
| BUG-E19 (#72) | trace-errors format docs match | **PASS** | Format description updated |
| BUG-E20 (#70) | CHANGELOG v3.0.0 has release date | **PASS** | "## [3.0.0] - 2026-05-25" |
| BUG-E21 (#73) | Int display convention documented | **PASS** | V3_1_PLAN notes as low-risk polish |
| BUG-E22 (#74) | json.stringify handles int documented | **PASS** | Tested: json.stringify({"count": 5i}) → {"count": 5} |

**Score: 21/22 PASS. BUG-E12 is the single patch closure failure.**

---

## SECTION 4 — BUILD SOMETHING REAL

### [04:00] Task: JSON-to-JSON order report transformer

**Files created:**
- `scratch/real_task/orders.json` — input (6 orders with large integer IDs and cent amounts)
- `scratch/real_task/transformer.nd` — transformer module (filter_by_status, summarize, enrich_order)
- `scratch/real_task/main.nd` — driver (load, filter, summarize, enrich, write report)

**Stdlib modules used:** std:fs, std:json, std:math, std:strings, std:path (5 modules)

**Integer type usage:** `math.to_int(amount_cents)` for exact cent arithmetic, `0i` counters, integer accumulation with `+1i`.

**Time to working:** ~20 minutes from blank slate to correct output.

### [04:01] Friction points encountered

1. **Import inside function body** (first version had `import "std:json"` inside `enrich_order()`). Clear error message fixed this quickly.

2. **len() returns float** — `str(len(orders))` prints "6.0 orders" instead of "6 orders". Workaround: none without explicit conversion. Friction present.

3. **json.parse_int unusable for JSON-parsed values** — Tried to use `json.parse_int(str(order["id"]))` to recover precise large integer IDs. Failed because `str(9007199254740993.0)` in Python gives "9007199254740993.0" — `json.parse_int` on a decimal string fails. Large integer IDs in JSON lose precision at `json.parse` time; there is no recovery path. Had to abandon precise ID handling and use floats throughout (with 2-unit precision loss on IDs 9007199254740993-9007199254740996).

4. **No string interpolation** — All string formatting required `str()` + concatenation. Tedious but functional.

5. **math.to_float(int_val) in return map** — Had to convert ints to floats before putting in maps destined for JSON serialization. Some inconsistency in when this is needed.

### [04:02] Output

Generated `scratch/real_task/report.json`. Confirmed: json.stringify handles Nodus floats as JSON numbers without trailing ".0" when they are whole numbers. Amounts computed correctly with integer cent arithmetic ($287.49 total for 3 completed orders).

**Precision loss confirmed:** IDs 9007199254740993 and 9007199254740994 and 9007199254740995 all appear as 9007199254740992 or 9007199254740996 in output (float precision ceiling effect).

### [04:03] Comparison to v3.0.0 real-task experience

v3.0.0 real task: log parser, ~15 min, same friction points. v3.0.1 real task: JSON transformer, ~20 min.

**Better in v3.0.1:**
- `catch (e)` syntax available (used once; no need to look up the no-paren form)
- fs.mkdir and fs.delete available (not needed for this task but no longer missing)
- math.log and math.pow available (not needed here)
- Embedding API fixed (not used here but no longer blocking Python integration)

**Same in v3.0.1:**
- len() → float friction identical
- No string interpolation friction identical
- Import inside function caught early by parser (same as v3.0.0)
- json.stringify int behavior documented but underdocumented still

**Worse in v3.0.1:**
- None specifically. The precision loss on large integer IDs via json.parse was present in both versions (it's a design limitation, not regression).

---

## SECTION 5 — META-OBSERVATIONS

### [05:01] Identity
Nodus has a clear identity: it's a scripting language for automation and orchestration where the primary data types (maps, records, errors) and control structures (workflows, goals) are designed for that domain. v3.0.1 is cohesive and internally consistent on its core features. The "Infinity Algorithm" branding is mentioned in PyPI metadata but not explained anywhere accessible — minor identity clarity gap.

### [05:02] Audience
**Is for:** Developers building orchestration pipelines in Python-adjacent ecosystems who want a typed, readable scripting layer with first-class error values and workflow primitives. **Not yet for:** General-purpose scripting (no string interpolation, incomplete stdlib), teams that need Python embedding as a primary integration path (embedding works but still has rough edges in error surfacing and observability).

### [05:03] Stability
Core language is stable. Integer arithmetic, error records, map/record disambiguation, module system — all consistent across stress tests. Less stable: workflow CLI subcommands (--help broken), math.log two-arg form (wrong results), cyclic workflow detection (returns error in map, not as err record).

### [05:04] v3.0.0 → v3.0.1 patch quality
The patch meaningfully improved the language. The two CRITICAL embedding bugs (E03, E04) were the most important fixes and they landed correctly. The stdlib completions (math.log, math.pow, path.relative, path.absolute, fs.mkdir, fs.delete) close real gaps. The catch (e) syntax is a genuine UX improvement. One patch closure failure (BUG-E12) and one new HIGH bug (math.log two-arg form) reduce confidence in the patch's test coverage.

### [05:05] Documentation truth
Better than v3.0.0 but still gaps: LANGUAGE_SPEC says all err records have path/line/column/stack — false for stdlib err records. V3_1_PLAN.md correctly categorizes deferred items. Design docs 03 and 04 not accessible from main branch (404).

### [05:06] Sharp corners count
Roughly 8-10 "had to figure this out" moments: import placement, len() float, catch syntax (now both forms), json.parse precision loss, math.log two-arg wrong result, workflow cyclic detection semantics, stdlib err record missing fields, has_key crash on records.

### [05:07] Comparison to v3.0.0
Better on: embedding API (now works), stdlib completeness (math/fs/path additions), error message quality (unicode identifiers improved), documentation warning for has_key crash.
Same on: len() float, no string interpolation, REPL non-automatable, workflow observability gaps.
New problems: math.log two-arg, workflow --help broken, stdlib err records missing location fields.

---

## FINDINGS SUMMARY

| ID | Severity | Title |
|---|---|---|
| BUG-E12-3.0.1 | CRITICAL | 1I still gives name error not parse error (patch closure failure) |
| NEW-01 | HIGH | math.log(n, base) computes ln(base) not log_base(n) |
| NEW-02 | MEDIUM | workflow run --help / graph run --help fail with "File not found" |
| NEW-03 | MEDIUM | Stdlib err records missing path/line/column/stack fields |
| NEW-04 | MEDIUM | Cyclic workflow returns error in map, exit code 0 (BUG-050 partial fix) |
| NEW-05 | LOW | strings.split wrong arity gives "Stack underflow" (VM internal) |
| NEW-06 | LOW | 1.0 / 0.0 throws instead of returning infinity (IEEE 754 surprise) |
| NEW-07 | COSMETIC | len() float produces "6.0 orders" in print strings |
