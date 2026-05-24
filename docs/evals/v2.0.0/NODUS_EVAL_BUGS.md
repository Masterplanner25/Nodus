# Nodus v2.0.0 — Bug Report
Evaluator: Claude Code (researcher mode, stress test)
Date: 2026-05-23
Evidence base: EVAL_LOG.md

Bugs are ordered by severity (CRITICAL → COSMETIC), then subsystem.

---

## CRITICAL

### BUG-016: fs.read does not block path traversal
**Severity:** CRITICAL
**Subsystem:** stdlib
**Affects:** v2.0.0
**Repro:**
```nodus
import "std:fs" as fs
let x = fs.read("../../Windows/System32/cmd.exe")
print(x)
```
Run with `nodus run scratch/traversal_fs.nd` (no --allow-paths flag).
**Expected:** Error: path escapes the project root (same as import path protection).
**Actual:** The runtime attempts to open the file. Fails only because `cmd.exe` is binary and cannot be decoded as UTF-8. A text file at any reachable path would be read successfully.
**Notes:** The import system correctly blocks `../` traversal with "Invalid import: path escapes the project root." The same protection is absent from `read_file`, `write_file`, `append_file`, `mkdir`, `list_dir`, and `exists` builtins when running under `nodus run` (CLI mode, no sandbox). NodusRuntime with `allowed_paths` set does correctly block this — the gap is CLI mode only.

---

### BUG-017: CLI crashes with Python traceback when printing file content that contains UTF-8 BOM
**Severity:** CRITICAL
**Subsystem:** runtime
**Affects:** v2.0.0
**Repro:**
```python
# Write a file with UTF-8 BOM
import codecs
with open("bom_test.nd", "w", encoding="utf-8-sig") as f:
    f.write('print("hello")\n')
```
Then read it from within Nodus and run on a cp1252 console:
```nodus
import "std:fs" as fs
let x = fs.read("bom_test.nd")
print(x)
```
**Expected:** Either the BOM is stripped and content is printed, or a clear Nodus error is raised.
**Actual:**
```
Traceback (most recent call last):
  File "...\cli.py", line 329, in _print_result_output
    print(stdout, end="")
  File "...\cp1252.py", line 19, in encode
    return codecs.charmap_encode(input,self.errors,encoding_table)[0]
UnicodeEncodeError: 'charmap' codec can't encode character '﻿' in position 0
```
**Notes:** The Python traceback leaks to the user. The root cause is that `cli.py` calls bare `print()` on captured stdout without forcing a UTF-8 output encoding. Mitigation: `sys.stdout.reconfigure(encoding='utf-8', errors='replace')` at CLI startup.

---

### BUG-007: Python RecursionError on deeply nested expressions (no Nodus error, no location)
**Severity:** CRITICAL
**Subsystem:** parser
**Affects:** v2.0.0
**Repro:**
```
# Generate a file with 100 levels of nested parens
python -c "print('print(' + '(' * 100 + '1' + ')' * 100 + ')')" > deep.nd
nodus run deep.nd
```
**Expected:** `Syntax error: expression too deeply nested (max depth: N)` with file and line.
**Actual:**
```
Error at deep.nd: maximum recursion depth exceeded
```
This is a Python RecursionError propagated from the recursive-descent parser with no source location.
**Notes:** Python's default recursion limit is ~1000 frames. The recursive-descent parser exhausts the stack before Nodus can report a structured error. Fix: add a depth counter in the parser and raise `LangSyntaxError` at a reasonable nesting limit (e.g., 200).

---

## HIGH

### BUG-010: Modulo operator `%` is not implemented
**Severity:** HIGH
**Subsystem:** parser
**Affects:** v2.0.0
**Repro:**
```nodus
print(10 % 3)
```
**Expected:** `1.0`
**Actual:** `Syntax error at file:1:10: Unexpected character '%'`
**Notes:** `%` is not in the lexer's token set. This is a fundamental arithmetic operator expected by every programmer. Workarounds require manual implementation (e.g., `a - math.floor(a/b) * b`) which is not documented anywhere. Confirmed by reading `strings.nd` which implements `repeat` with a counter loop rather than modulo.

---

### BUG-011: Scientific notation float literals not parsed
**Severity:** HIGH
**Subsystem:** parser
**Affects:** v2.0.0
**Repro:**
```nodus
let x = 1.5e10
print(x)
```
**Expected:** `15000000000.0`
**Actual:** `Syntax error: Expected ')', got identifier ('e')`
**Notes:** The lexer tokenizes `1.5e10` as number `1.5`, then identifier `e`, then number `10`. Scientific notation is standard in JSON, Python, JavaScript, and most scientific computing. Nodus already prints large numbers in scientific notation (`999999999999999999` → `1e+18`) but cannot parse the same notation it produces.

---

### BUG-018: json.parse returns records, not maps — dynamic field access is impossible
**Severity:** HIGH
**Subsystem:** stdlib
**Affects:** v2.0.0
**Repro:**
```nodus
import "std:json" as json
let data = json.parse("{\"name\": \"test\"}")
print(data["name"])  // fails
print(keys(data))    // fails
```
**Expected:** `"test"` / `["name"]`
**Actual:**
- `data["name"]` → `Type error: Indexing is only supported on lists and maps`
- `keys(data)` → `Type error: keys(x) expects a map`
**Notes:** Nodus records and maps are distinct types. Records support only dot-notation field access; maps support `[]` indexing and `keys()`. `json.parse` converts JSON objects to records, not maps. This makes generic JSON processing (iterate over keys, access fields by variable name) impossible without rewriting code to use hardcoded dot-access for every field. Workaround: use function extractors (`fn(e) { return e.field_name }`), which works but is not discoverable.

---

### BUG-019: strings.replace is missing from std:strings
**Severity:** HIGH
**Subsystem:** stdlib
**Affects:** v2.0.0
**Repro:**
```nodus
import "std:strings" as strings
print(strings.replace("hello world", "world", "nodus"))
```
**Expected:** `"hello nodus"`
**Actual:** `Key error: Missing module export: replace`
**Notes:** `replace` is one of the most commonly needed string operations. `strings.nd` exports: `upper`, `lower`, `trim`, `split`, `contains`, `repeat`, `is_blank`, `join`. No `replace`, `starts_with`, `ends_with`, `index`, `find`, or `pad`. The str_replace builtin may exist internally but is not exposed.

---

### BUG-022: print() inside workflow steps produces no output
**Severity:** HIGH
**Subsystem:** workflow
**Affects:** v2.0.0
**Repro:**
```nodus
workflow demo {
  step greet {
    print("hello from step")
    return "done"
  }
}
```
Run: `nodus workflow run demo.nd`
**Expected:** `hello from step` printed to stdout.
**Actual:** Only the JSON result summary is printed. All stdout from step bodies is silently discarded.
**Notes:** Debugging workflow steps is impossible without print output. The JSON summary shows task results but not intermediate output. This is undocumented behavior.

---

### BUG-005: NodusRuntime.run_source always raises on error, never returns ok=False
**Severity:** HIGH
**Subsystem:** runtime
**Affects:** v2.0.0
**Repro:**
```python
from nodus import NodusRuntime
rt = NodusRuntime(max_steps=100)
result = rt.run_source('while (true) { let x = 1 }')
# Expect: result["ok"] == False
# Actual: raises NodusSandboxError before this line is reached
```
**Expected:** Returns `{"ok": False, "error": "Execution step limit exceeded", ...}` (consistent with the success dict shape).
**Actual:** Raises `NodusSandboxError`. The `ok` key in the returned dict is always `True` — it is impossible for a call to `run_source` to return `ok=False`.
**Notes:** The docstring shows usage patterns implying `result["ok"]` checks make sense, but they can never be False. Callers must wrap every call in try/except to handle errors. The NodusRuntime docstring contains the Unicode arrow `→` in its pipeline description, which causes `inspect.getsource` to fail on Windows (cp1252 console) — a secondary bug (BUG-023).

---

### BUG-014: `foreach` keyword documented but does not exist; correct syntax is `for item in list`
**Severity:** HIGH
**Subsystem:** docs
**Affects:** v2.0.0
**Repro:**
```nodus
let items = [1, 2, 3]
foreach item in items {
  print(item)
}
```
**Expected:** Iterates, prints each item.
**Actual:** `Syntax error: Unexpected 'in' in expression`
**Notes:** NODUS.md lists `foreach` as a supported control structure. The correct syntax is `for item in items { }` (no `foreach` keyword). The C-style `for (init; cond; inc) { }` form is also valid. Any user reading the docs and writing `foreach` will waste time debugging the parse error.

---

### BUG-001: `nodus ast --help` and `nodus dis --help` treat `--help` as a filename
**Severity:** HIGH
**Subsystem:** other (CLI)
**Affects:** v2.0.0
**Repro:**
```
nodus ast --help
nodus dis --help
```
**Expected:** Usage information for the `ast` and `dis` subcommands.
**Actual:** `File not found: --help` (runtime error, exit code 1).
**Notes:** All other documented subcommands (`run`, `check`, `fmt`, `repl`, `init`, `graph`, `workflow`) correctly handle `--help`. The `ast` and `dis` commands parse `--help` as a positional file argument before checking for the flag.

---

## MEDIUM

### BUG-002: `nodus check` produces no output on success
**Severity:** MEDIUM
**Subsystem:** other (CLI)
**Affects:** v2.0.0
**Repro:**
```
nodus check scratch/hello.nd
```
**Expected:** `scratch/hello.nd: OK` or similar (exit 0).
**Actual:** No output whatsoever (exit 0). In a CI pipeline, this looks indistinguishable from a hung or skipped step.
**Notes:** Related: `nodus init` also produces no output on success (BUG-003). A consistent success-confirmation convention would improve the CLI.

---

### BUG-003: `nodus check` does not catch undefined variable/function references
**Severity:** MEDIUM
**Subsystem:** other (CLI)
**Affects:** v2.0.0
**Repro:**
```nodus
let x = undefined_func()
```
Run `nodus check` on this file → exit 0, no error.
**Expected:** `Name error: undefined_func is not defined` (or similar static warning).
**Actual:** Check passes silently. `nodus run` on the same file raises at runtime.
**Notes:** The `--help` for `check` says "parse and type-check a Nodus script." In practice it only parses — it does not resolve names or check type consistency. The word "type-check" in the description overstates the analysis performed.

---

### BUG-009: Non-ASCII characters in parser error messages render as `?` on Windows cp1252
**Severity:** MEDIUM
**Subsystem:** runtime
**Affects:** v2.0.0
**Repro:**
```
nodus run scratch/bad_op.nd
# file contains: let x = 1 +
```
**Expected:** `Syntax error at file:1:12: Unexpected end of statement — expression is incomplete`
**Actual:** `Syntax error at file:1:12: Unexpected end of statement ? expression is incomplete`
The em-dash `—` (U+2014) renders as `?` on the Windows console (cp1252 encoding).
**Notes:** The v2.0.0 changelog states Windows encoding was fixed for `--trace-imports`. That fix replaced `→` and `—` in import trace output only. The same characters appear in parser error message strings and were not covered by the fix. Affected messages include at least the "incomplete expression" parser error.

---

### BUG-012: No integer type; large integers silently lose precision; whole numbers display with `.0`
**Severity:** MEDIUM
**Subsystem:** runtime
**Affects:** v2.0.0
**Repro:**
```nodus
print(999999999999999999)
print(10 / 2)
print(len([1, 2, 3]))
```
**Expected:** `999999999999999999`, `5`, `3`
**Actual:** `1e+18`, `5.0`, `3.0`
**Notes:** All Nodus numbers are IEEE 754 doubles. Integers larger than 2^53 lose precision silently. Every integer operation (including `len()`) returns a float displayed with `.0`. This affects readability of any output containing counts, indices, or whole-number results. No integer arithmetic operators or integer literals exist.

---

### BUG-013: `0 == false` evaluates to `true` (undocumented numeric-boolean coercion)
**Severity:** MEDIUM
**Subsystem:** runtime
**Affects:** v2.0.0
**Repro:**
```nodus
print(0 == false)   // prints: true
print("" == false)  // prints: false
print(nil == false) // prints: false
print([] == false)  // prints: false
```
**Expected:** `false` for all (strict equality; 0 and false are different types).
**Actual:** `0 == false` is `true`; all others are `false`.
**Notes:** The inconsistency is sharp: numeric zero is coerced to false, but empty string, nil, and empty list are not. The LANGUAGE_SPEC.md does not document equality coercion rules. A user writing `if (result == false)` where `result` could be `0` will get unexpected behavior.

---

### BUG-015: Stack traces for stdlib errors point to stdlib internals, not the user call site
**Severity:** MEDIUM
**Subsystem:** runtime
**Affects:** v2.0.0
**Repro:**
```nodus
import "std:fs" as fs
let x = fs.read("nonexistent.txt")
```
**Expected:**
```
Runtime error at user_script.nd:2:9: file not found: nonexistent.txt
Stack trace:
  at <main> (user_script.nd:2:9)
```
**Actual:**
```
Runtime error at .../stdlib/fs.nd:2:22: read_file failed for 'nonexistent.txt': ...
Stack trace:
  at read (.../stdlib/fs.nd:2:22)
```
**Notes:** The error location shown is inside the stdlib wrapper, not the user's code. A user seeing `fs.nd:2:22` will not immediately know which line of their own script caused the problem. Same behavior seen for `json.nd` errors. The user call site should be the first (or only) frame in the stack trace.

---

### BUG-020: No builtin map key-existence check; requires importing std:collections
**Severity:** MEDIUM
**Subsystem:** runtime
**Affects:** v2.0.0
**Repro:**
```nodus
let m = {}
m["key"] = "value"
print(m["missing"])  // throws: Missing map key: "missing"
```
**Expected:** Either returns `nil` for missing keys, or a builtin `has_key(m, k)` function exists.
**Actual:** Accessing a missing map key throws `Key error: Missing map key: "missing"`. No `has_key`, `map_get`, or `.get(k, default)` builtin exists. The function is available as `std:collections.has_key(m, k)` but this is not documented in the language reference and requires an import.
**Notes:** This breaks a common idiom (accumulating counts in a map) and forces every map-building operation to either pre-populate all keys or import std:collections. The implementation of `has_key` in collections.nd uses O(n) linear search via `keys()`.

---

### BUG-021: REPL command list inconsistency between REPL.md and `nodus repl --help`
**Severity:** MEDIUM
**Subsystem:** repl
**Affects:** v2.0.0
**Repro:**
1. Read `docs/tooling/REPL.md` — documents `:ast`, `:dis`, `:type`, `:help`, `:quit`
2. Run `nodus repl --help` — lists `:help`, `:quit`, `:clear`, `:reset`
**Expected:** Consistent list in both places.
**Actual:** REPL.md documents `:ast`, `:dis`, `:type` (absent from --help); `--help` documents `:clear`, `:reset` (absent from REPL.md).
**Notes:** Cannot test interactively to determine ground truth. One of these sources is out of date. If `:ast`/`:dis`/`:type` are implemented, they are not surfaced in --help. If `:clear`/`:reset` are implemented, they are not documented in REPL.md.

---

## LOW

### BUG-008: Unclosed string literal gives confusing "Unexpected character" error
**Severity:** LOW
**Subsystem:** parser
**Affects:** v2.0.0
**Repro:**
```nodus
print("hello
```
**Expected:** `Syntax error at file:1:7: Unterminated string literal`
**Actual:** `Syntax error at file:1:7: Unexpected character '"'`
**Notes:** The lexer reports the start of the string as an "unexpected character" rather than reporting that the string was never closed. A developer will be confused by the error pointing to the opening quote. This is a minor usability issue since the line/column is correct; only the message is misleading.

---

### BUG-024: `nodus init` produces no success output
**Severity:** LOW
**Subsystem:** other (CLI)
**Affects:** v2.0.0
**Repro:** `nodus init --path myproject`
**Expected:** `Initialized Nodus project at myproject/` or similar.
**Actual:** Silent exit 0. The directory was created but the user has no confirmation.
**Notes:** Related to BUG-002 (check silence). A `--quiet` flag would make silence opt-in; current behavior makes it mandatory.

---

### BUG-025: `nodus fmt --check` false-negative on freshly written files before first format pass
**Severity:** LOW
**Subsystem:** other (CLI)
**Affects:** v2.0.0
**Repro:**
```powershell
# Write a correctly formatted file with LF line endings
[System.IO.File]::WriteAllText("good.nd", "let x = 1 + 2`nprint(x)`n", [Text.Encoding]::UTF8)
nodus fmt --check good.nd
# Exit code 1: "File not formatted: good.nd"
nodus fmt good.nd  # run formatter
nodus fmt --check good.nd
# Exit code 0 -- now passes
```
**Expected:** `fmt --check` should pass on any file that `fmt` would leave unchanged.
**Actual:** Files written with specific line-ending conventions fail `fmt --check` until `fmt` runs once. This makes `fmt --check` unusable in CI without a prior `nodus fmt` pass (defeating the purpose of --check).
**Notes:** Root cause appears to be that `nodus fmt` enforces a specific line-ending normalization. On Windows, files written by editors/tools with Windows-native or pure-LF endings both fail until `fmt` normalizes them. The formatter must either document its expected line ending, or `--check` must normalize before comparing.

---

### BUG-026: `while true` (without parens) gives confusing error; `while` always requires parens
**Severity:** LOW
**Subsystem:** parser
**Affects:** v2.0.0
**Repro:**
```nodus
while true {
  let x = 1
}
```
**Expected:** Either works (Python/Ruby style) or gives: `while condition requires parentheses: while (true) { ... }`
**Actual:** `Syntax error: Expected '(', got 'true'`
**Notes:** The error is technically accurate but not immediately helpful. A user coming from JavaScript or Python might try `while true` and not know what "Expected '('" means. A one-line "Hint: while requires parentheses: while (cond) { }" would be a significant improvement.

---

### BUG-027: `throw "string"` gives err.kind = "runtime" instead of "thrown"
**Severity:** LOW
**Subsystem:** runtime
**Affects:** v2.0.0
**Repro:**
```nodus
try {
  throw "explicit error"
} catch err {
  print(err.kind)   // prints: "runtime" (expected: "thrown")
}

try {
  throw record { code: 404 }
} catch err {
  print(err.kind)   // prints: "thrown" (correct)
}
```
**Expected:** `"thrown"` for all explicit `throw` statements, regardless of value type.
**Actual:** `throw <string>` gives `err.kind = "runtime"`; `throw <record>` gives `err.kind = "thrown"`.
**Notes:** The LANGUAGE_SPEC.md implies `"thrown"` for any explicit throw. This inconsistency means error-handling code that branches on `err.kind == "thrown"` will not match string-typed throws.

---

## COSMETIC

### BUG-023: Unicode `→` in NodusRuntime docstring causes `inspect.getsource` failure on Windows
**Severity:** COSMETIC
**Subsystem:** runtime
**Affects:** v2.0.0
**Repro:**
```python
from nodus import NodusRuntime
import inspect
print(inspect.getsource(NodusRuntime.run_source))
```
**Expected:** Source code printed to console.
**Actual:** `UnicodeEncodeError: 'charmap' codec can't encode character '→'`
**Notes:** The docstring for `NodusRuntime.run_source` contains `→` (U+2192) in its pipeline description. The v2.0.0 changelog fixed the same character in `--trace-imports` output but missed this docstring. Python's inspect module reads the source and prints to stdout, which on Windows uses cp1252. Only affects developers inspecting the source; not a user-facing bug.

---

### BUG-028: `--trace-no-loc` output has trailing whitespace on alignment columns
**Severity:** COSMETIC
**Subsystem:** other (CLI)
**Affects:** v2.0.0
**Repro:**
```
nodus run --trace --trace-no-loc scratch/small.nd
```
**Expected:** `[trace] ADD` (no trailing spaces)
**Actual:** `[trace] ADD           ` (padded to column width even without any content after)
**Notes:** The trace formatter pads all opcode lines to the same width for alignment. When `--trace-no-loc` removes the `line N` suffix, the padding still fills the column with spaces. Purely cosmetic; does not affect functionality.

---

### BUG-029: Large CLI command list in `--help` with no grouping or documentation tier labels
**Severity:** COSMETIC
**Subsystem:** other (CLI)
**Affects:** v2.0.0
**Repro:** `nodus --help`
**Expected:** Commands grouped (e.g., "Core", "Workflow", "Package management", "Service / cluster") with stable vs experimental labels.
**Actual:** 50+ commands in a flat list. Most (serve, lsp, dap, snapshot, worker, agent-call, tool-call, login, publish, etc.) are undocumented in any public doc.
**Notes:** Not a functional bug, but a discoverability issue that makes the project look more mature than it is. A new user sees 50 commands and has no signal about which ones to start with.
