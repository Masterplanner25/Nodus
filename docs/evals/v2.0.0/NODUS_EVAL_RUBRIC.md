# Nodus v2.0.0 — Evaluation Rubric
Evaluator: Claude Code (researcher mode, stress test)
Date: 2026-05-23

All scores are supported by evidence in EVAL_LOG.md.

---

| Dimension                       | Score | Rationale |
|---------------------------------|-------|-----------|
| Install and first-run UX        | 8/10  | `pip install nodus-lang==2.0.0` + `nodus run hello.nd` works first try; no dependencies; clean version output. Deducted for `nodus init` and `nodus check` producing zero output on success. |
| CLI ergonomics                  | 5/10  | Global `--help` is comprehensive. Per-command help mostly works but `nodus ast --help` and `nodus dis --help` treat `--help` as a filename. 50+ undocumented commands in the help screen dilute signal for new users. |
| Error message quality           | 6/10  | Import errors (all tried paths shown) and type errors (clear, located) are genuinely good. Offset by: Python traceback leaks on deep nesting and BOM reads; non-ASCII characters in parser error messages render as `?` on Windows; unclosed string gives "Unexpected character" not "Unterminated string". |
| Parser robustness               | 4/10  | Empty/whitespace/comment-only files: fine. Long identifiers: fine. Deep nesting (100 parens): Python RecursionError crash. Missing modulo (`%`). Scientific notation literals not supported. Mixed line endings not tested to crash but CRLF affects `fmt --check`. |
| Type system behavior            | 5/10  | Types are well-defined and errors are clear. Float-only numbers lose precision on large integers and display poorly (`5.0` for `5`). `0 == false` is surprising. No integer division, no modulo. Record vs map distinction is sharp and underdocumented. |
| Standard library completeness   | 4/10  | Modules present: strings, fs, json, math, memory, collections, async, runtime, path, utils. Missing in strings: `replace`, `starts_with`, `ends_with`, `index`. Missing in math: pow, log, trig, constants. No network, no datetime. Very thin for a "production scripting" claim. |
| Standard library correctness    | 7/10  | All present functions work correctly. `memory.has` fix from v2.0.0 works. json round-trip is correct (number display differs but stringify is right). Stack traces on stdlib errors point to stdlib, not caller. |
| Module system                   | 8/10  | Circular import detection works. Path traversal blocked on imports. Error messages when modules are not found are the best in the language. Named exports work. Bare-path resolution against project root is a good default. |
| REPL                            | 4/10  | Cannot test interactively. `nodus repl --help` lists `:clear, :reset` but REPL.md documents `:ast, :dis, :type, :modules, :reload` — unknown which is the ground truth. `nodus ast` and `nodus dis` as standalone CLI commands work correctly (proxy test). |
| Workflow / graph runner         | 5/10  | Basic workflow execution works; JSON result output is clean; failure propagation is clean; cycle detection works. Significant issue: `print()` inside steps is silently discarded. Wrong dependency syntax in early testing (`depends:` vs `after`) wasted time. |
| Tracing / observability         | 7/10  | `--trace` output is readable and structured. `--trace-no-loc` works. `--trace-imports` uses ASCII `->` (Windows-compatible). `--trace` with `--step-limit` interaction is clean. Minor: `JUMP` at top of every script has `line ?` (no source location for boilerplate). |
| Embedded / programmatic API     | 6/10  | NodusRuntime is well-documented and `allowed_paths` sandboxing works. Default 200ms timeout is too low for general use. Error model (always raises, never returns ok=False) is internally consistent but differs from what the docstring examples imply. Module-level `run_source` returns a VM object (useless for callers) and is confusing alongside NodusRuntime.run_source. |
| Documentation accuracy         | 5/10  | Core language docs (types, control flow, imports) are accurate. `foreach` keyword documented but syntax is `for...in`. REPL commands inconsistent between REPL.md and --help. `err.kind` for `throw "string"` is `"runtime"` not `"thrown"` per spec. `nodus check` described as type-checker but only parses. |
| Documentation completeness      | 4/10  | Language spec is thorough for the core. 50+ CLI commands are undocumented. No docs for map vs record behavioral differences. No `has_key` in the language reference. Standard library reference is implicit (read the .nd files). |
| Stability under stress          | 3/10  | Two CRITICAL bugs found in a single evaluation day (path traversal, BOM crash). Python traceback leaks on deep nesting. `nodus fmt --check` false-negatives on freshly written files. `strings.replace` missing. For a "Production/Stable" PyPI classifier, this is not the right score. |
| Overall first-week usability    | 5/10  | An experienced developer will be productive on light automation tasks within a day, but will hit 4-5 unexpected walls (records vs maps, no modulo, no scientific notation, workflow print silencing, float display). The language is not hostile, but it is not finished. |

---

## Composite Weighted Score

| Dimension                       | Score | Weight | Weighted |
|---------------------------------|-------|--------|----------|
| Install and first-run UX        | 8     | 0.05   | 0.40     |
| CLI ergonomics                  | 5     | 0.07   | 0.35     |
| Error message quality           | 6     | 0.08   | 0.48     |
| Parser robustness               | 4     | 0.07   | 0.28     |
| Type system behavior            | 5     | 0.07   | 0.35     |
| Standard library completeness   | 4     | 0.06   | 0.24     |
| Standard library correctness    | 7     | 0.06   | 0.42     |
| Module system                   | 8     | 0.07   | 0.56     |
| REPL                            | 4     | 0.04   | 0.16     |
| Workflow / graph runner         | 5     | 0.06   | 0.30     |
| Tracing / observability         | 7     | 0.05   | 0.35     |
| Embedded / programmatic API     | 6     | 0.07   | 0.42     |
| Documentation accuracy         | 5     | 0.07   | 0.35     |
| Documentation completeness      | 4     | 0.06   | 0.24     |
| Stability under stress          | 3     | 0.09   | 0.27     |
| Overall first-week usability    | 5     | 0.07   | 0.35     |
| **Total**                       |       | **1.00** | **5.52 / 10** |

---

## Weight Rationale

Stability under stress (0.09) and error message quality (0.08) are weighted highest because for an embedded runtime these are the properties that cause production incidents. CLI ergonomics, type system, module system, embedded API, and documentation accuracy are each weighted 0.07 — equal weight for core user-facing capabilities. Install/REPL/tracing are weighted lower (0.04–0.05) because they are either trivially good or not interactive-testable in this evaluation. The composite score of **5.5/10** aligns with the narrative verdict: functional, promising, not production-ready.
