# Nodus v3.0.0 Evaluation Log

Evaluator: Claude Code (researcher mode, stress test)
Start: 2026-05-25

---

## [07:53] SETUP

### Environment
- Working directory: `C:\dev\nd testing` — confirmed empty at start
- Platform: Windows 11, PowerShell
- Python: venv created with `python -m venv .venv`
- Install: `pip install nodus-lang==3.0.0` — SUCCESS, 205 kB wheel
- Version confirm: `nodus --version` → `Nodus 3.0.0` ✓
- Directories created: `scratch/`, `migration/`

---

## [07:53] RESEARCH PASS — BEGIN

Reading PyPI page, GitHub docs, CHANGELOG, design docs.

---

## [07:55] RESEARCH FINDINGS

### PyPI page (https://pypi.org/project/nodus-lang/3.0.0/)
- Not directly accessed; metadata obtained via pip install and package inspection
- Package size: 205 kB wheel, installs cleanly

### README.md
- One-sentence definition: "Nodus is a scripting language and runtime created by Shawn Knight, designed as part of the Masterplan Infinite Weave ecosystem."
- Features: bytecode-compiled, stack-based VM, coroutines, task graphs, workflows
- Consistent with llms.txt and LANGUAGE_SPEC high-level summary

### CHANGELOG.md
- The CHANGELOG returned by GitHub API was a SUMMARY, not the full version-by-version detailed CHANGELOG
- Key v3.0.0 items visible: record literals, integer type (`42i`), returned errors, new err.kind values
- Notably: the summary did not list all individual BUG-0xx fixes that were tested in Section 3
- The CHANGELOG says v3.0.0 is "unreleased" in the summary text — contradicts the fact that it's on PyPI as 3.0.0

### LANGUAGE_SPEC.md
- Full text not returned (too large); structural summary was provided
- Notes the integer type, try/catch, import system, workflow/goal DSLs

### Migration guide (docs/migration/v2-to-v3.md)
- Covers: record vs map syntax, error kinds, err.payload consistency, integer type
- Missing explicit call-out that `has_key(err, "payload")` CRASHES in v3.0 (it throws type error, not just returns wrong value)
- Missing: math.log/math.pow don't exist (they were listed in error-surfaces.md as wrapped, but the stdlib doesn't have them)
- Missing: NodusRuntime host_globals/initial_globals broken
- Misleading: `{key: "value"}` with bare keys was ALWAYS a record in v2 (not a map); this wasn't a real breaking change for most code

### error-surfaces.md
- Lists math.log(n), math.pow(a, b), math.sqrt(n) as Replace-wrapped returning err
- Lists fs.delete(path), fs.mkdir(path) as stdlib functions
- Lists path.relative(p, base), path.absolute(p) as stdlib functions
- ALL FOUR of these either don't exist or don't return err records as documented

### Design docs (docs/design/v3/)
- doc 01: integer type — very detailed, matches implementation closely
- doc 02: Python error replacement — wrapping confirmed for json/fs, NOT for math.sqrt (still throws)
- doc 03: err record shape — err.payload always nil when absent confirmed ✓; mixed key parse error confirmed ✓
- doc 00: phase 0 decisions — equality coercion unchanged confirmed ✓

---

## [08:00] BASELINE TESTS

### nodus run scratch/hello.nd
- Output: `Hello, Nodus v3.0.0!` and `2.0` ✓
- Note: 1+1 = 2.0 (float), not 2 (int). Expected.

### nodus check scratch/hello.nd
- Output: `scratch\hello.nd: OK` ✓

### nodus --help
- Commands grouped into sections: Execution, Project, Inspection, Orchestration, Server, Tooling, Runtime API, Registry ✓
- BUG-029 #27 fix confirmed

### nodus run --help
- `--trace-errors` flag present ✓

### Programmatic API (top-level run_source)
- `from nodus import run_source; run_source('print(1+1)')` → prints 2.0, returns VM object
- API PROBLEM: top-level `run_source` returns the VM object, not a clean result value

### NodusRuntime embedding API
- `NodusRuntime.run_source()` returns a dict with ok/stdout/stderr ✓
- `host_globals` and `initial_globals` DON'T WORK — variables are "Undefined" in scripts
- Root cause: ModuleLoader created without host_globals, then overwrites VM's host_globals in _execute_module
- CRITICAL: host Python exceptions from registered functions are swallowed (not re-raised)

---

## [08:05] SECTION 3.2 — INTEGER TYPE TESTS

### Results:
- `type(1i)` → "int" ✓
- `type(1)` → "number" (not "float") — consistent with BUG-032 reconciliation
- `9007199254740993i` → prints correctly without precision loss ✓
- `1i + 1i` → 2 (displayed as int, no trailing .0) ✓
- `1i + 1` → 2.0 (float promotion) ✓
- `1i / 2i` → 0.5 (float, division always float) ✓
- `1i % 2i` → 1 (int, modulo stays int) ✓
- `1i == 1` → true (coercion) ✓
- `math.parse_int("42")` → 42 (int) ✓
- `math.parse_int("42.0")` → err{kind: "parse_error"} ✓
- `math.parse_int("foo")` → err{kind: "parse_error"} ✓
- `math.to_int(3.7)` → 3, `math.to_int(-3.7)` → -3 ✓
- `math.to_float(3i)` → 3.0 ✓
- `math.is_int(3i)` → true, `math.is_int(3.0)` → false ✓
- `math.idiv(7i, 2i)` → 3 (int) ✓
- `math.idiv(7i, 0i)` → err{kind: "math_error", message: "division by zero"} ✓
- `math.idiv(7, 2)` → err{kind: "type_error"} ✓
- `json.parse_int("9007199254740993")` → 9007199254740993 (int, exact) ✓
- `json.parse("1")` → 1.0 (float, unchanged) ✓
- `json.stringify({"count": 5i})` → `{"count": 5}` (no .0) ✓

### Rejected forms:
- `1I` → Name error "Undefined variable: I" (NOT a parse error as spec claims — LOW severity)
- Hex/oct/bin int literals: not tested explicitly but TOKEN_RE regex shows no hex/oct support
- `1_000i`: would give "Undefined variable: _" or similar
- These are runtime errors, not parse errors as the spec says

---

## [08:10] SECTION 3.3 — TYPE SYSTEM

- `0 == false` → true ✓ (Phase 0 decision 3)
- `nil == false` → false (nil is NOT equal to false)
- `[] == false` → false (empty list is NOT equal to false)
- `"5" == 5` → false (no string-number coercion)
- `0i == false` → true (boolean coercion of int works)
- Boolean coercion: 0, 0i, "", nil, [] are all falsy ✓

---

## [08:12] SECTION 3.4 — MAP AND RECORD LITERALS

- `{foo: "bar"}` → type "record", access via `r.foo` ✓
- `{"foo": "bar"}` → type "map", access via `m["foo"]` ✓
- Mixed keys `{foo: 1, "bar": 2}` → PARSE ERROR with two fix suggestions ✓
- Multi-line map with value on next line works (BUG-039) ✓
- Dynamic key `{(k): "hello"}` works ✓
- err.payload is nil when no data, but still present as field ✓

---

## [08:15] SECTION 3.5 — ERR RECORD SHAPE

- `err.payload` always nil for errors without structured data ✓
- `has_key(err, "payload")` → TYPE ERROR (throws) — has_key only works on maps, not Records
- CRITICAL: Migration guide says "requires rewriting" but actual behavior is a throw, not a silent wrong result
- err.kind confirmed working for json.parse and fs.read errors ✓

---

## [08:17] SECTION 3.6 — CONTROL FLOW

- `try {} catch e {}` (no parens on catch variable) is correct syntax
- `try {} catch (e) {}` → PARSE ERROR "Expected identifier, got '('"
- NOTE: If any docs show `catch (e)` syntax, that's a documentation bug
- BUG-041 fix: finally runs even when catch has a return ✓
- else if works ✓ (BUG-029 fix)
- --step-limit fires correctly ✓
- 0, 0i, "", nil, [] all falsy ✓

---

## [08:20] SECTION 3.7 — MODULE SYSTEM

- import "std:nonexistent" → clear import error with tried paths ✓
- import "modA" (no extension, relative to script dir) → works ✓
- import "scratch/modA.nd" (with extension and subdir prefix from scratch/) → FAILS (adds .nd to .nd suffix)
- import inside function → syntax error with actionable message ✓
- Path traversal `../../etc/passwd` → blocked ✓
- Circular imports: not explicitly tested but code shows detection

---

## [08:22] SECTION 3.8 — PYTHON ERROR REPLACEMENT

### Confirmed working:
- json.parse("{bad") → err{kind: "parse_error", message: "invalid JSON at line 1 column 2: expected property name"} — Nodus voice ✓
- json.stringify(function) → err{kind: "type_error", message: "cannot serialize to JSON: ..."} — Nodus voice ✓
- json.parse_int("abc") → err{kind: "parse_error"} ✓
- json.parse_int("1e9") → err{kind: "parse_error", message: "not an integer (scientific notation): ..."} ✓
- fs.read("missing/file") → err{kind: "io_error", message: "file not found: ..."} — Nodus voice ✓
- fs.read("scratch/") → err{kind: "io_error", message: "expected a file, got a directory: ..."} ✓
- fs.listdir("file.nd") → err{kind: "io_error", message: "expected a directory, got a file: ..."} ✓
- --trace-errors: stderr shows Python traceback, stdout clean ✓
- NODUS_TRACE_ERRORS=1: same ✓

### CRITICAL failures:
- json.parse(123) → THROWS VM type error, does NOT return err record — violates design doc 2
- math.sqrt(-1) → THROWS runtime error "math_sqrt(x) expects a non-negative number", NOT err{kind: "value_error"}
- math.log(n) → function does NOT EXIST in std:math or builtins
- math.pow(a, b) → function does NOT EXIST
- path.relative(p, base) → function does NOT EXIST in std:path
- path.absolute(p) → function does NOT EXIST in std:path

### Absolute path sandbox:
- fs.read("/missing/file.txt") → SANDBOX ERROR (blocked) — NOT an io_error as documented
- This is correct security behavior, but means the documented io_error test case doesn't apply for absolute paths

### Stdlib not Replace-wrapped (intentional):
- strings.* functions use vm.runtime_error for type checks — leaks VM-level errors, not Python text
- collections.* same — OK per error-surfaces.md §4

---

## [08:30] SECTION 3.9 — STANDARD LIBRARY

- strings.is_blank("   ") → true ✓ (BUG-035 confirmed)
- strings.split, upper, lower, trim, contains, replace, join, repeat all present ✓
- json.parse, json.stringify, json.parse_int all present ✓
- math.abs, min, max, floor, ceil, sqrt, random, parse_int, to_int, to_float, is_int, idiv all present ✓
- math.log, math.pow → MISSING
- fs.read, write, append, exists, listdir, ensure_dir present ✓
- fs.mkdir, fs.delete → MISSING (ensure_dir is present but mkdir is not exported)
- path.join (list arg), dirname, basename, ext, stem ✓
- path.relative, path.absolute → MISSING
- utils.get, coalesce, clamp ✓
- len() returns float, not int — minor inconsistency
- path.join takes a LIST, not variadic args

---

## [08:35] SECTION 3.10 — MIGRATION TESTS

- has_key(err, "payload") → throws type error — migration guide underestimates the impact (says "requires rewriting" but actual result is a crash)
- {name: value} → record literal (same as v2, not actually changed behavior for most code)
- Equality coercion unchanged ✓
- Python error text gone from err.message ✓
- String matching on error messages would break (intentional breaking change) ✓
- NodusRuntime host_globals: Python int→ Nodus int marshaling works at function-call boundary (confirmed via register_function); host_globals parameter to run_source is broken

---

## [08:40] SECTION 3.11 — REPL

- REPL starts ✓ (`nodus repl` works)
- Piping commands to REPL caused "Unexpected character" error (non-interactive use is awkward)
- Could not fully test :help, :ast, :type, :modules — interactive-only commands
- REPL survives after reading it shows "3.0.0 REPL" banner ✓

---

## [08:42] SECTION 3.13 — TRACING

- --trace-errors ✓ (confirms Python traceback on stderr)
- NODUS_TRACE_ERRORS=1 ✓
- --trace-imports ✓ (confirmed working on fresh files)
- nodus debug --help → shows help ✓ (BUG-047 fix confirmed)
- --step-limit fires ✓

---

## [08:48] SECTION 3.14 — ERROR MESSAGE QUALITY SUMMARY

| Error type | WHAT | WHERE | FIX HINT | Nodus voice |
|-----------|------|-------|----------|------------|
| Unclosed string | ✓ | ✓ | - | ✓ |
| Operator with no operand | ✓ | ✓ | ✓ | ✓ |
| Import not found | ✓ | ✓ | ✓ (shows tried paths) | ✓ |
| Import in function | ✓ | ✓ | ✓ ("move to top level") | ✓ |
| Mixed map keys | ✓ | ✓ | ✓ (two fix suggestions) | ✓ |
| json.parse error | ✓ | ✓ (line/col) | - | ✓ |
| fs.read missing | ✓ | ✓ (line/col in script) | - | ✓ |
| math.idiv zero | ✓ | - | - | ✓ |
| math.sqrt(-1) | ✓ | ✓ | - | ✗ (throws, not err record) |
| has_key(err,...) | ✓ | ✓ | ✗ (no suggestion to use .payload) | ✓ |
| Undefined variable | ✓ | ✓ | - | ✓ |
| Wrong arity | ✓ | ✓ | - | ✓ |

---

## [08:52] SECTION 4 — REAL TASK

- Built log parser in 2 files: logparse.nd + main.nd
- Used: std:fs, std:strings, std:json, std:math (4 stdlib modules)
- Integer type used for line/error/warning counts
- Output confirmed correct: 15 lines, 3 errors, 2 warnings, 10 info
- Friction points:
  1. Had to convert int counts to float for JSON (turned out unnecessary — json.stringify handles ints)
  2. len() returns float — confusing when doing `i < len(items)` with int `i`
  3. `lines[math.to_int(i)]` needed explicit conversion (or maybe int index works natively — not tested)
  4. No string format/interpolation — had to concatenate with `+` and `str()`
  5. The module import path convention (`import "modA"` not `import "modA.nd"`) is not obvious
  6. No way to pass data from Python to Nodus via NodusRuntime kwargs
- Time: approximately 15 minutes to design and get working

---

## [08:57] FINAL NOTES

- `nodus init` creates project structure ✓
- `nodus ast`, `nodus dis` work ✓
- `nodus fmt --check` exists ✓
- `nodus workflow --help` shows subcommands ✓
- `nodus graph run --help` not tested
- BUG-050 (workflow cycle detection) not tested
- REPL commands :ast, :dis, :type, :modules not tested interactively



