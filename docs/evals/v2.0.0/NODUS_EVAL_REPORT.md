# Nodus v2.0.0 — Independent Evaluation
Evaluator: Claude Code (researcher mode, stress test)
Date: 2026-05-23
Time invested: ~3 hours (research, testing, reporting)

---

## TL;DR

Nodus v2.0.0 is a working, installable scripting language with a clean install story and a surprisingly solid module system and error messaging — but it is not ready for production adoption today. Two critical security/stability issues (fs path traversal not blocked in CLI mode; Python traceback crash on BOM files), one missing fundamental operator (`%` modulo), and a "Production/Stable" PyPI classifier that overstates the reality are the blockers. A competent developer building light automation workflows will be mostly productive but will hit rough edges within the first hour. The embedded API (NodusRuntime) is the language's strongest asset and is already worth using with an explicit `allowed_paths` sandbox; the CLI is several patches behind.

---

## What Nodus Is

Nodus is a bytecode-compiled, stack-VM scripting language designed primarily as a sandboxable orchestration runtime. The closest canonical definition, consistent across README, NODUS.md, and LANGUAGE_SPEC.md, is: "a lightweight scripting language built around a bytecode compiler and stack-based VM, optimized for automation and orchestration workflows" (NODUS.md). The README overlays this with "the Infinity Algorithm's execution model" framing that is aspirational rather than descriptive and does not appear in the spec or architecture docs — a slight identity inconsistency. In practice, Nodus is most accurately described as a Python-embedded scripting engine with a workflow/task-graph DSL bolted on top.

---

## What Works Well

- **Install and first run:** `pip install nodus-lang==2.0.0` + `nodus run hello.nd` works first try with no friction.
- **Import error messages:** When a module is not found, the error lists every path that was tried (relative, project-local, stdlib). Exemplary UX.
- **Circular import detection:** Two-file circular import detected with full chain shown (a → b → a).
- **Path traversal protection for imports:** `import "../../etc/passwd"` is blocked with a clear "path escapes the project root" message.
- **Step and time limits:** `--step-limit` and `--time-limit` both fire cleanly with a `Sandbox error: Execution step limit exceeded` message — no Python traceback, no hang.
- **memory.has() after v2.0.0 fix:** `memory.put("k", nil)` followed by `memory.has("k")` correctly returns `true`. The fix works.
- **--trace-imports ASCII format:** Uses `->` not `→`, confirmed working on Windows cp1252 console.
- **NodusRuntime isolation:** Two NodusRuntime instances in the same process do not share memory state.
- **NodusRuntime allowed_paths sandbox:** Path violations outside `allowed_paths` raise `NodusSandboxError` in embedded mode.
- **AST and disassembly tools:** `nodus ast` and `nodus dis` produce clean, readable output.
- **Formatter:** `nodus fmt` normalizes whitespace consistently; the output is clear idiomatic Nodus.
- **try/catch/finally:** Syntax is clean; error object provides `.message`, `.kind`, `.payload` fields.

---

## Where v2.0.0 Hits Sharp Corners

Each item below is linked to a filed defect in NODUS_EVAL_BUGS.md.

- **BUG-016 (CRITICAL):** `fs.read` does not block `../` path traversal. A script can read arbitrary filesystem files (binary decode errors aside). Import path protection does not extend to stdlib fs operations.
- **BUG-017 (CRITICAL):** Reading a file with a UTF-8 BOM via `fs.read` crashes the CLI with an unhandled Python `UnicodeEncodeError` traceback.
- **BUG-007 (CRITICAL):** 100 levels of nested parentheses crashes with a Python `RecursionError: maximum recursion depth exceeded` — a raw Python traceback, no Nodus error, no line number.
- **BUG-010 (HIGH):** The `%` modulo operator is not implemented. `print(10 % 3)` → `Syntax error: Unexpected character '%'`.
- **BUG-011 (HIGH):** Scientific notation literals (`1e+18`, `3.14e-2`) are not parsed. `1.7976931348623157e+308` → parse error.
- **BUG-018 (HIGH):** `json.parse` returns Nodus records for JSON objects. Records support dot-notation only — no `["key"]` access, no `keys()` call. Generic JSON processing requires redesigning code around function extractors.
- **BUG-019 (HIGH):** `strings.replace` is not implemented; calling it raises a runtime error.
- **BUG-022 (HIGH):** `print()` inside workflow steps produces no output. Step stdout is silently discarded.
- **BUG-005 (HIGH):** `NodusRuntime.run_source` always raises on error; it never returns a dict with `ok=False`. The API doc shows `result["ok"]` checks that can never be False.
- **BUG-014 (HIGH):** `foreach item in list` is documented as valid syntax in NODUS.md but raises a parse error. Correct syntax is `for item in list`.
- **BUG-001 (MEDIUM):** `nodus ast --help` and `nodus dis --help` interpret `--help` as a filename and error.
- **BUG-002 (MEDIUM):** `nodus check` produces no output on success; silent exit 0 is ambiguous in CI.
- **BUG-003 (MEDIUM):** `nodus check` does not catch undefined variable/function references — it only parses.
- **BUG-009 (MEDIUM):** Error messages contain non-ASCII bullet characters that render as `?` on Windows cp1252 consoles (partially fixed in v2.0.0 for --trace-imports, not for parser error messages).
- **BUG-012 (MEDIUM):** All numbers are floats; `print(10 / 2)` → `5.0`. Large integers silently lose precision (`999999999999999999` → `1e+18`).
- **BUG-013 (MEDIUM):** `0 == false` evaluates to `true` (numeric-boolean coercion). Undocumented; likely surprising.

---

## The Build-Something-Real Experience

**Task built:** JSON log transformer. Reads a JSON array of log entries, computes per-level and per-service counts, total and average duration, writes a summary JSON. Split into `main.nd` (orchestration) and `stats.nd` (generic aggregation helpers). Uses std:fs, std:json, std:math, std:strings (for context), std:collections. ~100 lines across two files.

**Time:** ~40 minutes from blank files to working output.

**Where it was pleasant:**
- The module system worked immediately. `import "./stats" as stats` resolved and `export fn` was clean.
- Function literals as arguments work well: `stats.count_by(entries, fn(e) { return e.level })` reads naturally.
- Error messages during development were usually helpful — "Missing module export: replace" told me exactly what was missing.

**Where it was painful:**

*The `json.parse` → record type problem cost 15 minutes.* My first instinct was to write a generic `count_by_key(entries, key)` function that does `entry[key]`. This failed with "Indexing is only supported on lists and maps" because `json.parse` returns records. I then tried `keys(entry)` which failed with "keys(x) expects a map". The workaround — passing a function extractor instead of a field name — is actually idiomatic Python, but the issue is undocumented and the error message doesn't hint at the distinction between records and maps.

*The missing `has_key` builtin cost 10 minutes.* Map access on a missing key throws; there's no `nil`-returning fallback and no builtin to check existence. The function is in `std:collections` but is not documented in the main language spec or LANGUAGE_SPEC.md. Once I found it the problem was solved, but discovery required reading stdlib source directly.

*All numbers are floats* means output like `Total entries: 10.0` which looks wrong to end users. No workaround except string post-processing.

**What would have made the experience smoother:** A table of record vs map differences in the docs (they look similar, behave differently). A `has_key` or `map_get(m, k, default)` builtin. A `str_int(n)` function or integer display that omits `.0` for whole numbers.

---

## Verdict by Audience

**For language designers / language hobbyists:** Interesting project with a clean architecture (lexer → parser → AST → compiler → VM is textbook-tidy). The workflow lowering and coroutine model are worth studying. The v2.0.0 changelog shows the author is responsive to real issues. Recommended for study or tinkering.

**For someone with a real production scripting need:** Not yet. The missing modulo operator, float-only numbers, and path traversal gap in fs.read are disqualifying. Come back for v2.1. If embedded use with `NodusRuntime` and `allowed_paths` is the target, the API is closer to usable today.

**For someone evaluating against Python/Lua/Starlark:** Nodus loses on breadth (no modulo, no integers, thin stdlib), but wins on the embedded safety story if you configure `allowed_paths` and execution limits. Against Starlark specifically: Nodus has coroutines and a more expressive syntax; Starlark has broader adoption and better-defined determinism guarantees. Against Lua: Lua has a dramatically richer ecosystem and C FFI; Nodus has a friendlier Python host API. Neither comparison is close yet.

---

## What v2.1 or v2.0.1 Should Prioritize

1. **Fix fs path traversal (CRITICAL):** The import system blocks `../`; `fs.read` must too. This is a security issue in any multi-tenant deployment.
2. **Implement `%` modulo operator (HIGH):** It is absent from the lexer. One line in the lexer, one opcode. Without it, basic arithmetic (hour/minute calculations, pagination, hash bucketing) requires workarounds.
3. **Audit non-ASCII characters in error messages (MEDIUM):** The v2.0.0 fix for `--trace-imports` shows this is solvable. Apply the same audit to all `LangError` message strings and CLI print paths so Windows users get coherent errors.
4. **Clarify NodusRuntime error model in docs (HIGH):** Document that `run_source` always raises on failure. Remove or caveat any `result["ok"]` example that implies it can be False. Alternatively, add a `try_run_source` method that returns an error-result dict.
5. **Address `foreach` doc/reality mismatch and add `strings.replace` (MEDIUM/HIGH):** Two documented features that don't work as documented — both fixable in under a day.
