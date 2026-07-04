# Nodus v3.0.0 — Independent Evaluation

Evaluator: Claude Code (researcher mode, stress test)
Date: 2026-05-25
Time invested: ~2 hours (research pass + full test battery + real task + report)
Baseline for comparison: v2.0.0 eval scored 5.52/10 composite

---

## TL;DR

Nodus v3.0.0 delivers three of its four headline features well: the integer type works correctly for its designed use case, the map/record disambiguation is clean, and the Python error replacement produces genuinely Nodus-voice errors for the json and fs namespaces. However, the v3.0.0 embedding API is critically broken — `host_globals` and `initial_globals` silently have no effect, making the documented way to pass data from Python into Nodus scripts non-functional. The standard library also makes promises it doesn't keep: `math.log`, `math.pow`, `path.relative`, `path.absolute`, `fs.mkdir`, and `fs.delete` are all listed in the Replace contract documentation but don't exist. The composite score of 6.45/10 (+17% from v2.0.0's 5.52) reflects real improvement in the language core while leaving the embedding story and stdlib completeness in a degraded state. **For a CLI scripting use case: cautiously usable with workarounds. For Python embedding: not production-ready.**

---

## What Nodus v3.0.0 is

Nodus is a bytecode-compiled scripting language with a stack-based virtual machine, designed for automation and orchestration workloads. The canonical definition, consistent across README.md, llms.txt, and LANGUAGE_SPEC.md, is: a language implementing "coroutines, task graphs, workflows, and goals on a deterministic stack-based VM." It compiles `.nd` source through a lexer → parser → AST → compiler → optimizer → VM pipeline. v3.0.0 is the first major version with declared breaking changes from the v2.x line, centered on four changes: an opt-in integer type (`1i`), Python error text replacement for stdlib error messages, a consistent `err.payload` field shape on all err records, and a parse-time enforcement of map-vs-record literal syntax.

---

## What changed from v2.x

The CHANGELOG summary (returned verbatim from GitHub) describes v3.0.0 as introducing: record literals (`{foo: bar}`), integer type (`42i`), returned errors instead of thrown ones for stdlib calls, and new `err.kind` values (`io_error`, `parse_error`, `type_error`, `math_error`, `value_error`, `internal_error`). The migration guide at `docs/migration/v2-to-v3.md` covers the four breaking areas. Most v2.1.1 code runs unchanged — the breaks are targeted. The Phase 0 decisions (docs/design/v3/00-phase-0-decisions.md) deliberately kept `==` coercion unchanged and made the integer type opt-in, limiting the migration surface to embedding callers and code that string-matched Python error text.

---

## What works well in v3.0.0

- **Install and first run:** `pip install nodus-lang==3.0.0` installs cleanly in seconds. `nodus --version` immediately returns `Nodus 3.0.0`. No configuration required.

- **Grouped CLI help:** `nodus --help` organizes 30+ commands into labeled sections (Execution, Project, Inspection, Orchestration, Server, etc.) instead of the prior flat wall. A clear UX win. BUG-029 #27 confirmed fixed.

- **Integer type arithmetic:** `1i + 1i = 2` (int), `1i + 1 = 2.0` (float), `1i / 2i = 0.5` (float), `1i % 2i = 1` (int) — exactly per design doc 01. Large integers like `9007199254740993i` preserve precision. `json.parse_int("9007199254740993")` returns the exact integer. The precision problem (BUG-012) is solved for opt-in usage.

- **Map/record disambiguation parse errors:** `{foo: 1, "bar": 2}` produces a parse error with two concrete suggestions: "quote all keys" or "use bare identifiers." This is excellent error-message design.

- **Python error replacement for json and fs:** `json.parse("{bad")` returns `err{kind: "parse_error", message: "invalid JSON at line 1 column 2: expected property name"}` — zero Python text. `fs.read("missing.txt")` returns `err{kind: "io_error", message: "file not found: ..."}`. The Nodus-voice framing is consistent and professional.

- **`--trace-errors` flag:** When active, prints `[trace-errors] in fs.read` with the Python exception and full traceback to stderr, while stdout output stays clean. The `NODUS_TRACE_ERRORS=1` env var is a good alternative for CI pipelines.

- **err.payload always present:** Every err record has a `payload` field. When there's no structured data, `err.payload` is `nil` (never absent). `e.payload == nil` is reliable. Design doc 3 confirmed implemented.

- **try/catch/finally with return in catch (BUG-041):** `finally` block runs even when `catch` contains a `return` statement. Confirmed working.

- **else if parsing (BUG-029):** `else if (cond)` is valid syntax. Confirmed working.

- **`nodus debug --help` (BUG-047):** Shows help content instead of "file not found." Confirmed working.

- **Security: path traversal blocked:** `fs.read("../../etc/passwd")` produces a sandbox error. BUG-016 and BUG-046 fixes confirmed still holding.

- **Import inside function gives actionable error:** "import statements must be at the top level of a module; move this import to the top of the file." Clear and actionable.

- **`strings.is_blank` (BUG-035):** `strings.is_blank("   ")` correctly returns `true`. Was broken in v2.x.

- **`path.ext("file.tar.gz")` (BUG-037):** Returns `.gz` not `.gz.tar`. Confirmed fixed.

---

## Where v3.0.0 hits sharp corners

All items linked to NODUS_EVAL_BUGS.md.

- **BUG-E01:** `json.parse(123)` throws a VM error instead of returning `err{kind: "type_error"}`. The Replace contract claims this is fixed.
- **BUG-E02:** `math.sqrt(-1)` throws a runtime error instead of returning `err{kind: "value_error"}`. Direct design doc violation.
- **BUG-E03 (CRITICAL):** `NodusRuntime.run_source(host_globals={"x": 5})` — the variable `x` is undefined in the script. The documented mechanism for passing Python data into Nodus scripts is silently broken.
- **BUG-E04 (CRITICAL):** Host Python exceptions from registered functions are swallowed and returned as error dicts, not re-raised to Python. Phase 0 decision 4 is violated.
- **BUG-E05:** `math.log` and `math.pow` don't exist despite being listed in error-surfaces.md.
- **BUG-E06:** `path.relative` and `path.absolute` don't exist despite being listed.
- **BUG-E07:** `fs.mkdir` and `fs.delete` not exported from std:fs.
- **BUG-E08:** `has_key(err, "payload")` CRASHES with a type error — the migration guide says "requires rewriting" but understates this as a complete program crash.
- **BUG-E10:** `catch (e)` causes a parse error — correct syntax is `catch e` (no parens), which conflicts with every other control structure in Nodus that uses parens.
- **BUG-E11:** Unicode characters in identifiers cause "Unexpected character" error with no guidance.

---

## Migration honesty

The migration guide (`docs/migration/v2-to-v3.md`) is accurate about the changes it covers but misses several real breakages.

**Correctly documented:**
- `{foo: bar}` is now always a record literal (not ambiguous with map). ✓
- `err.payload` is always present. ✓
- err.kind values changed from generic "runtime" to specific kinds. ✓
- Python error text is gone from err.message. ✓

**Understated or missing:**
1. **`has_key(err, "payload")` crashes, not "requires rewriting."** The guide says "code using `has_key(err, 'payload')` requires rewriting to `err.payload != nil`." The actual behavior is a thrown type error — "has_key(map, key) expects a map." Any v2.x code that used `has_key` on err records without a surrounding `try/catch` will CRASH in v3.0.0. The migration guide describes this as a semantic change (always returns true) — it is actually a breakage.

2. **`{key: value}` was never a "map with variable key" in v2.x.** The guide implies bare-identifier keys were previously evaluated as variable references. In reality, they were record literals in v2.x too. The real breakage is for any user who *thought* they were using a map and was actually using a record — this is a conceptual clarity fix, but calling it a "parse error for bare map keys" is misleading if the code already worked as a record.

3. **Embedding API `host_globals` marshaling change is broken.** The guide says "embedding code that relies on v2.x marshaling must convert explicitly." But the mechanism to pass ANY data into scripts via `host_globals` doesn't work at all in v3.0.0 (BUG-E03).

4. **`math.log`, `math.pow`, `path.relative`, `path.absolute` are entirely absent.** If any v2.x code called these functions (if they existed then), it would now get "Missing module export" errors.

**Migration verdict:** The guide is honest about the changes it mentions, but the omissions matter. A v2.x developer reading the guide would not be warned about the `has_key` crash or the broken embedding API.

---

## The build-something-real experience

Built a log parser in two files: `scratch/real_task/logparse.nd` (parser module) and `scratch/real_task/main.nd` (driver). Total ~100 lines. Uses std:fs, std:strings, std:json, std:math (four stdlib modules). Integer type used for line/error/warning counts. Module import system used to split parser logic.

**Time to working:** ~15 minutes from blank slate to correct output.

**What worked smoothly:**
- The module system is ergonomic once you know to omit the file extension
- Integer type arithmetic for counting was natural (`0i`, `error_count + 1i`)
- `json.stringify` handles Nodus int values natively (outputs `5` not `5.0`)
- Error handling pattern (`if (type(result) == "error") { ... }`) is readable

**Where I got stuck:**
1. `len()` returns float — I initially tried to use `i < len(lines)` with int `i`. This works due to coercion but required checking; the type inconsistency is surprising.
2. `import "logparse.nd"` fails (doubles the extension). The correct `import "logparse"` is non-obvious.
3. No string interpolation — had to write `"Total lines: " + str(total_lines)` everywhere.
4. Had to look up whether `json.stringify` handles int values (it does — underdocumented).
5. `catch e {}` syntax (no parens) is different from every other control structure.

**Where v3.0.0 specifically helped:** Integer arithmetic is genuinely cleaner than storing line counts as floats (which was the v2 situation). The err-record pattern `if (type(result) == "error")` read naturally and didn't require wrapping in try/catch.

**Where v3.0.0 hurt vs v2.x for this use case:** Nothing major — the breaking changes didn't affect this scripting use case at all. The embedding limitations would have hurt if I were calling from Python.

---

## Verdict by audience

**For language designers / language hobbyists:** Worth evaluating. The integer type design (opt-in via suffix, clean mixed-arithmetic rules) is a thoughtful solution to a real problem. The design docs in docs/design/v3/ show disciplined thinking. The gap between design and implementation is visible and correctable. Score: 7/10 — interesting, honest about trade-offs.

**For someone with a real production scripting need:** Cautiously usable for CLI scripting of file/JSON processing tasks. The core language works. Error messages are good. But you'll hit missing stdlib functions (`math.log`, `path.relative`, `fs.delete`) and the catch-variable syntax friction. If your use case doesn't touch the gaps, it's viable today. Score: 5/10 — usable with sharp edges.

**For someone evaluating against Python/Lua/Starlark:** Not yet competitive for general-purpose scripting. Missing stdlib coverage, no string interpolation, the broken embedding API, and no documentation on how to use catch-variable syntax (vs common other languages). Starlark in particular has a much more complete ecosystem. Score: 4/10 — Nodus needs another release cycle.

**For someone migrating from Nodus v2.x:** Possible but requires care. The migration guide covers the main cases but understates the `has_key` crash. Run your test suite — if you don't have one, start with the four documented breaking changes and manually audit for `has_key(err, ...)` patterns. Score: 5/10 — migration is real work, guide is incomplete.

---

## What v3.0.1 or v3.1 should prioritize

**v3.0.1 patches (CRITICAL/HIGH):**
1. **BUG-E03:** Fix `NodusRuntime.run_source` to pass `host_globals` through to the `ModuleLoader` instead of the VM constructor. One-line fix: add `host_globals=host_globals` to the `ModuleLoader(...)` call.
2. **BUG-E04:** Protect `_invoke_host_function` so that Python exceptions from host functions propagate out of `run_source` instead of being caught by the outer `except Exception`.
3. **BUG-E01/E02:** Fix `json.parse` and `math.sqrt` to return err records instead of throwing for invalid inputs.
4. **BUG-E08:** Update the migration guide to say "`has_key(err, key)` will throw a type error in v3.0 — replace with `err.payload != nil`."
5. **BUG-E07:** Export `fs.mkdir(path)` and `fs.delete(path)` from std:fs, or update error-surfaces.md to remove them.

**v3.1 design work:**
1. **BUG-E05/E06:** Implement `math.log`, `math.pow`, `path.relative`, `path.absolute` — or remove them from error-surfaces.md.
2. **BUG-E10:** Make `catch (e)` valid syntax (accept the parenthesized form), matching the pattern of other Nodus control structures.
3. **BUG-E15:** Consider making `len()` return int instead of float, now that the int type exists.
4. **BUG-E11:** Improve the unicode identifier error message to say "Nodus identifiers are ASCII-only" with a clear explanation.
5. **String interpolation:** The absence of string interpolation (`${}` or similar) is a significant scripting friction point not addressed in v3.0.0.
