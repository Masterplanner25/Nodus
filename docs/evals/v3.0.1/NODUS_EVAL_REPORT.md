# Nodus v3.0.1 — Independent Evaluation

**Evaluator:** Claude Code (researcher mode, stress test)
**Date:** 2026-05-25
**Time invested:** ~3 hours (research pass + full test battery + real task + deliverables)
**Baseline for comparison:** v3.0.0 eval scored 6.45/10 composite, v2.0.0 eval scored 5.52/10 composite

---

## TL;DR

Nodus v3.0.1 is a meaningful step forward from v3.0.0: the embedding API (previously critically broken) now works correctly, the stdlib is substantially more complete, and most of the 22 v3.0.0 bugs are genuinely fixed. For pure scripting use cases, v3.0.1 is ready to use with known sharp corners around `len()` returning float and the absence of string interpolation. For Python embedding, v3.0.1 is now a viable choice where v3.0.0 was not. **However, one patch closure failure stands out:** BUG-E12 (`1I` uppercase suffix) was claimed fixed in the v3.0.1 CHANGELOG but is absent from the distributed wheel — still giving a cryptic name error at runtime. A new HIGH bug also arrived in the patch: `math.log(n, base)` computes `ln(base)` instead of `log_base(n)`, silently returning wrong results for all two-argument calls. The composite score is **7.36/10** (+14% from v3.0.0's 6.45, +33% from v2.0.0's 5.52).

---

## What Nodus v3.0.1 is

Nodus is a bytecode-compiled scripting language with a stack-based virtual machine, designed for automation and orchestration workloads. Source passes through lexing → parsing → AST → bytecode compilation → optimization → VM execution. The canonical one-sentence definition is consistent across README, LANGUAGE_SPEC, and PyPI: a language implementing coroutines, task graphs, workflows, and goals on a deterministic stack-based VM, for Python ≥3.10. v3.0.1 is a patch release on top of the major v3.0.0 release (released the same day, 2026-05-25). v3.0.0 introduced four headline features: an opt-in integer type (`42i`), Python error text replacement for stdlib errors, a consistent `err.payload` shape, and parse-time enforcement of map-vs-record literal syntax. v3.0.1 completes the error-replacement contract, fixes the broken embedding API, and closes 21 of 22 filed v3.0.0 issues.

---

## What changed from v3.0.0

v3.0.1 addressed 22 issues (#53–#74) in four areas. **Replace contract completion:** `json.parse(non-string)` now returns `err{kind: "type_error"}` (was throwing); `math.sqrt(-1)` returns `err{kind: "value_error"}` (was throwing); `math.log`, `math.pow`, `path.relative`, `path.absolute`, `fs.mkdir`, and `fs.delete` were added to the wrapped namespaces. **Embedding API fixes:** `NodusRuntime.run_source(host_globals={...})` now correctly forwards host variables into the script (was silently ignored in v3.0.0); Python exceptions from registered host functions now propagate to the Python caller (were being swallowed). **Documentation reconciliation:** migration guide now explicitly warns that `has_key(err, key)` throws a type error (was understated as "requires rewriting"); `docs/governance/V3_1_PLAN.md` added to capture deferred design items; `--trace-errors` format documentation updated; CHANGELOG v3.0.0 entry now has a release date. **Polish:** `catch (e)` syntax now accepted alongside `catch e`; non-ASCII identifier error now says "Identifiers must use ASCII letters only"; import with `.nd` extension no longer doubles the extension; top-level `run_source` now emits a `DeprecationWarning`.

---

## What works well

- **Install and first run:** `pip install nodus-lang==3.0.1` installs in seconds. `nodus --version` immediately returns 3.0.1. Zero configuration required. ✓
- **Embedding API (critical fix):** `NodusRuntime.run_source(source, host_globals={"x": 5})` correctly delivers `x` to the script as Nodus int type. Host Python exceptions (ValueError, KeyError, custom subclasses) all propagate correctly. Two runtime instances are properly isolated. Previously CRITICAL-broken; now reliable. ✓
- **Error replacement completeness:** All four wrapped namespaces (json, fs, math, path) now have full coverage. Every `fs.read`, `json.parse`, `math.sqrt`, `math.log`, `math.pow`, `path.relative`, `path.absolute` call returns a Nodus-voice err record. Zero Python text observed in any `err.message`. ✓
- **Integer type arithmetic:** All arithmetic rules correct and precise. Large integers like `9007199254740993i` preserve precision. `math.idiv`, `math.parse_int`, `math.to_int/to_float/is_int`, `json.parse_int` all correct. ✓
- **catch (e) syntax:** Both `catch e` and `catch (e)` now accepted identically. Makes Nodus syntax consistent with its own control structure patterns. ✓
- **Module system:** Import with `.nd` extension works. Circular imports detected. Path traversal blocked. Import inside function gives clear "move to top" message. ✓
- **Map/record disambiguation:** Parse-time enforcement with excellent dual-suggestion error messages unchanged from v3.0.0. ✓
- **--trace-errors and NODUS_TRACE_ERRORS:** Both work; stderr shows full Python traceback while stdout stays clean. ✓
- **DeprecationWarning on top-level run_source:** Fires correctly with "will be removed in v4.0" message. ✓
- **fs.mkdir, fs.delete now exported:** `fs.mkdir("existing")` returns `io_error`. `fs.delete("missing")` returns `io_error`. ✓
- **migration guide has_key crash warning:** Now prominently flagged as CRITICAL with crash description and safe alternative (`err.payload != nil`). ✓
- **V3_1_PLAN.md:** Deferred items (len() float, type() naming, finally behavior) explicitly documented, correctly framed as design items not bugs. ✓

---

## Where v3.0.1 still hits sharp corners

Each item linked to NODUS_EVAL_BUGS.md.

- **BUG-01 (CRITICAL):** `1I` uppercase suffix still gives runtime name error "Undefined variable: I" — NOT a parse error with a helpful message. The CHANGELOG claimed this was fixed in v3.0.1; the fix is absent from the distributed 3.0.1 wheel. One of the 22 patch closures did not land.
- **BUG-02 (HIGH):** `math.log(value, base)` computes `ln(base)` and ignores `value`. Returns wrong results for all two-argument calls without erroring. Example: `math.log(100, 10)` = 2.302 instead of 2.0. This is a new defect introduced when math.log was added in the v3.0.1 patch.
- **BUG-03 (MEDIUM):** `nodus workflow run --help` and `nodus graph run --help` output "File not found: --help" instead of help text. Multi-level subcommand help is broken.
- **BUG-04 (MEDIUM):** Stdlib err records (json.parse, fs.read, math.sqrt, etc.) do not have `path`, `line`, `column`, or `stack` fields. LANGUAGE_SPEC says all err records have these fields. User code checking `err.path` after a stdlib call will get a key error crash.
- **BUG-05 (MEDIUM):** Cyclic workflows return a result map with an `"error"` string key and exit code 0, rather than returning an err record or exiting non-zero. The standard Nodus error-checking pattern (`type(result) == "error"`) cannot detect this failure.
- **BUG-06 (LOW):** `strings.split("hello")` (wrong arity) produces "Stack underflow" — an internal VM error with no user value.
- **BUG-07 (LOW):** `1.0 / 0.0` throws a runtime error instead of returning IEEE 754 infinity. The LANGUAGE_SPEC describes numbers as IEEE 754 floats.
- **Design gap (not a bug):** `json.parse` returns floats for all numbers. There is no way to recover precise large integer IDs from JSON once parsed — `json.parse_int` operates on a raw JSON string, not on already-parsed float values. This limits the integer type's practical value for JSON-sourced data.
- **Pre-existing / deferred:** `len()` returns float (V3_1_PLAN), no string interpolation, REPL not testable non-interactively.

---

## Patch closure verification (v3.0.1)

21 of 22 v3.0.1 patch closures verified as working. The one failure is BUG-E12 (#64): `1I` uppercase suffix still produces a runtime name error (`Undefined variable: I`) rather than a parse error with an explicit "integer literal suffix must be lowercase i" message. This was the stated fix in the CHANGELOG and the GitHub issue, but the fix is absent from the distributed wheel.

All other closures verified:
- BUG-E01 (json.parse type-check), BUG-E02 (math.sqrt wrapping), BUG-E03 (host_globals), BUG-E04 (host exceptions), BUG-E05 (math.log/pow added), BUG-E06 (path.relative/absolute), BUG-E07/E13 (fs.mkdir, fs.delete), BUG-E08 (migration guide warning), BUG-E09 (path.join list-arg docs), BUG-E10 (catch (e) syntax), BUG-E11 (Unicode identifier message), BUG-E14 (DeprecationWarning), BUG-E15 (len() in V3_1_PLAN), BUG-E16 (.nd extension import), BUG-E17 (type() in V3_1_PLAN), BUG-E18 (sandbox precedence documented), BUG-E19 (trace-errors format), BUG-E20 (CHANGELOG date), BUG-E21/E22 (int display and json.stringify documented).

One new bug was introduced by the patch itself: BUG-02 (`math.log` two-arg form with arguments swapped). This is a defect in the implementation of the BUG-E05 fix (adding math.log), not a regression of existing functionality.

---

## The build-something-real experience

Built a JSON-to-JSON order report transformer in two files (`scratch/real_task/transformer.nd` + `scratch/real_task/main.nd`, ~110 lines total). Uses std:fs, std:json, std:math, std:strings, std:path (5 stdlib modules). Integer type used for cent-amount arithmetic. Module import system splits transformer logic. Time to working output: ~20 minutes.

**What improved over v3.0.0 real-task experience:**
- `catch (e)` syntax available (v3.0.0 required looking up the no-paren form)
- fs.mkdir, fs.delete, path.relative available when needed (v3.0.0 was missing these)
- No embedding API stumbling (if calling from Python, v3.0.0 host_globals was broken)

**Friction points unchanged from v3.0.0:**
- `len()` returns float — `str(len(orders))` prints "6.0 orders", not "6 orders"
- No string interpolation — all formatting requires `str()` + concatenation chains
- `import "std:json"` inside a function body gives a parse error (had to restructure on first attempt)

**New friction discovered:**
- **json.parse precision loss for large integer IDs.** Input JSON had IDs like `9007199254740993` (above float precision). `json.parse` returned floats — precision lost immediately. `json.parse_int` operates on raw JSON strings, not on already-parsed map values. No recovery path without writing a custom parser. The output report contained ID collisions (e.g., two orders with ID 9007199254740996). The integer type exists but there is no practical path from `json.parse` → exact integer for values already parsed as float. This is a design gap, not a regression.

Overall, v3.0.1 is noticeably smoother than v3.0.0 for scripting tasks. The improvement is incremental (one less sharp corner from catch syntax) but the embedding improvements matter greatly for the Python-integration use case.

---

## Verdict by audience

**For language designers / hobbyists:**
v3.0.1 is interesting and shows disciplined design-doc-driven development. The integer type, err record pattern, and map/record disambiguation are thoughtful solutions to real problems. The V3_1_PLAN.md shows honest acknowledgment of trade-offs. The gap between documented and implemented behavior (math.log two-arg, LANGUAGE_SPEC err fields) is correctable. Score: **7.5/10** — substantive improvement, still a hobby-level tool.

**For real production scripting needs:**
Cautiously usable for file and JSON processing pipelines. The core language is reliable. Error messages are good. The embedding API is now viable. **Blockers:** no string interpolation makes output formatting verbose; `len()` float requires explicit conversion; math.log two-arg is silently wrong. If your use case fits the strengths (orchestration, workflows, typed error values), it's viable today. Score: **6/10** — usable with workarounds, but not yet ergonomic.

**For Python/Lua/Starlark evaluators:**
Improved from v3.0.0 but still not competitive with mature alternatives. Starlark has more complete stdlib, better tooling, and wider adoption. Python's subprocess and yaml/json libraries require less learning surface. Nodus's unique value prop (workflow primitives, typed error records, integer type) is real but niche. Score: **5/10** — worth watching, not worth switching today.

**For v2.x or v3.0.0 migrators:**
- **From v2.x:** Migration guide is more complete than v3.0.0. The has_key crash warning is now prominent. Most v2.x scripting code runs unchanged. Audit for has_key(err, ...) patterns before migrating. Score: **6/10** — migration is real work, guide is honest.
- **From v3.0.0:** No migration required. v3.0.1 is fully backward-compatible with v3.0.0 code. All tested v3.0.0 patterns work without changes. The embedding API improvements are automatically available. Score: **9/10** — upgrade freely.

---

## What v3.0.2 or v3.1 should prioritize

**v3.0.2 patch (urgent):**
1. **Fix BUG-E12:** Make `1I` emit a parse error with "integer literal suffix must be lowercase i" message. The lexer needs to recognize `\d+I` as a two-token sequence and flag it at lex/parse time, not leave it to runtime name resolution.
2. **Fix math.log two-arg form:** `math.log(value, base)` should compute `ln(value) / ln(base)`, not `ln(base)`. Argument order in the Python implementation appears swapped.

**v3.1 (high priority):**
3. **len() → int:** Already in V3_1_PLAN with breaking-change label. The float return is the single most common friction point in every day of scripting.
4. **Fix workflow/graph run --help:** Multi-level subcommand help routing should propagate `--help` correctly.
5. **Reconcile LANGUAGE_SPEC err record table:** Either document that stdlib err records omit location fields, or add them. The spec promising path/line/column/stack and delivering none of them on the most common err records is a documentation contract failure.

**v3.1 (design work):**
6. **String interpolation:** Absence is the largest ergonomic gap vs. peer languages. `"Order \(id) total: \(total)"` would eliminate significant verbosity.
7. **json.parse integer detection:** Add a way to parse JSON numbers as Nodus int when they are whole and large, or provide `json.parse_ints(str)` that upgrades all numbers to int — without breaking the default float behavior.
