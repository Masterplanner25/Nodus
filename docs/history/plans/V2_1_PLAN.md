# Nodus v2.1.0 — Plan
Source: 2026-05-23 independent evaluation
Eval composite score: 5.52/10
Eval verdict: not production-ready as v2.0.0; v2.1 closes the gap

## Scope summary
- **25 issues** in v2.1.0 milestone (GitHub milestone #1)
- **4 issues** deferred to v3.0 or unscheduled
- Target v2.1.0 release: TBD — decided separately based on capacity

---

## v2.1.0 milestone contents

### subsystem:parser
- #3 [CRITICAL] BUG-007: Python RecursionError on deeply nested expressions (no Nodus error, no location)
- #4 [HIGH] BUG-010: Modulo operator `%` is not implemented
- #5 [HIGH] BUG-011: Scientific notation float literals not parsed
- #20 [LOW] BUG-008: Unclosed string literal gives confusing "Unexpected character" error
- #23 [LOW] BUG-026: `while true` (without parens) gives confusing error; hint missing

### subsystem:runtime
- #2 [CRITICAL] BUG-017: CLI crashes with Python traceback when reading file with UTF-8 BOM
- #14 [MEDIUM] BUG-009: Non-ASCII characters in parser error messages render as `?` on Windows cp1252
- #17 [MEDIUM] BUG-015: Stack traces for stdlib errors point to stdlib internals, not the user call site
- #18 [MEDIUM] BUG-020: No builtin map key-existence check; requires importing std:collections
- #24 [LOW] BUG-027: `throw "string"` gives `err.kind = "runtime"` instead of `"thrown"`
- #25 [COSMETIC] BUG-023: Unicode arrow in NodusRuntime docstring causes `inspect.getsource` failure on Windows

### subsystem:stdlib
- #1 [CRITICAL] BUG-016: `fs.read` does not block path traversal
- #6 [HIGH] BUG-018: `json.parse` returns records, not maps — dynamic field access is impossible
- #7 [HIGH] BUG-019: `strings.replace` is missing from std:strings

### subsystem:embedded-api
- #9 [HIGH] BUG-005: `NodusRuntime.run_source` always raises on error, never returns `ok=False`

### subsystem:workflow
- #8 [HIGH] BUG-022: `print()` inside workflow steps produces no output

### subsystem:docs
- #10 [HIGH] BUG-014: `foreach` keyword documented but does not exist; correct syntax is `for item in list`

### subsystem:repl
- #19 [MEDIUM] BUG-021: REPL command list inconsistency between REPL.md and `nodus repl --help`

### subsystem:cli
- #11 [HIGH] BUG-001: `nodus ast --help` and `nodus dis --help` treat `--help` as a filename
- #12 [MEDIUM] BUG-002: `nodus check` produces no output on success
- #13 [MEDIUM] BUG-003: `nodus check` does not catch undefined variable/function references (fix help text at minimum)
- #21 [LOW] BUG-024: `nodus init` produces no success output
- #22 [LOW] BUG-025: `nodus fmt --check` false-negative on freshly written files before first format pass
- #26 [COSMETIC] BUG-028: `--trace-no-loc` output has trailing whitespace on alignment columns
- #29 [META] META: Downgrade Production/Stable classifier to Beta for v2.1.0

---

## Critical path (these block v2.1.0 release)

The three CRITICAL findings must be resolved before v2.1.0 ships:

- **#1** — `fs.read` path traversal (BUG-016): security issue; import system blocks `../` but fs builtins do not in CLI mode
- **#2** — BOM file `UnicodeEncodeError` crash (BUG-017): unhandled Python traceback on a legitimate file type
- **#3** — 100-level nested parens `RecursionError` leak (BUG-007): parser stack overflow with no Nodus error or source location

Plus the PyPI classifier downgrade:
- **#29** — Downgrade `Production/Stable` → `Beta` in `pyproject.toml` before v2.1.0 ships

---

## High-priority but not blocking

These are all in v2.1.0 but do not individually block release:

- **#4** — `%` modulo operator (BUG-010): fundamental arithmetic; one lexer token + one opcode
- **#6** — `json.parse` record/map clarification (BUG-018): code OR docs fix — decide during implementation
- **#9** — NodusRuntime error model doc fix (BUG-005): document that `run_source` always raises, remove misleading `ok=False` examples or add `try_run_source`
- **#8** — workflow `print()` suppression (BUG-022): breaks observability of the language's primary marketed feature
- **#7** — `strings.replace` implementation (BUG-019): most commonly expected string function, currently raises at runtime
- **#10** — `foreach` doc/reality mismatch (BUG-014): documented feature that doesn't exist; fix NODUS.md
- **#5** — scientific notation literals (BUG-011): language produces notation it cannot parse

---

## Deferred to v3.0 (require design work)

- **#15** [BUG-012] Integer type — all Nodus numbers are IEEE 754 doubles; large integers silently lose precision; `len()` returns `3.0` not `3`. Adding a first-class integer type is a language-level change that touches the lexer, compiler, VM, and all stdlib. Cannot be done in a patch.
- **#28** [DESIGN] Equality coercion semantics — `0 == false` is `true` but `"" == false` is `false`; inconsistent and undocumented. Fixing requires choosing strict equality (breaking change) or documenting as intentional (design commit). Punted to v3.0.

---

## Unscheduled / low priority

- **#16** [BUG-013] `0 == false` coercion — the behavior itself; tracked by #28 (DESIGN) for v3.0 design resolution
- **#27** [BUG-029] Flat `--help` command list — cosmetic; requires design effort to group 50+ commands; no cluster pull from other fixes

---

## Cross-cutting themes from the eval

From the "What v2.1 should prioritize" section of the evaluation report:

1. **Path traversal protection is inconsistent between subsystems.** The import system blocks `../`; fs builtins do not in CLI mode; NodusRuntime `allowed_paths` does. The fix for BUG-016 should audit all fs builtins, not just `read`.

2. **Several Python-leaked tracebacks should be Nodus errors.** BUG-007 (RecursionError), BUG-017 (UnicodeEncodeError), and BUG-023 (inspect UnicodeEncodeError) are all cases where Python's exception surfaces to the user. A defensive `except Exception` wrapper at the CLI boundary would catch future cases before they become CRITICALs.

3. **Non-ASCII characters in error output break on Windows consoles.** The v2.0.0 fix covered `--trace-imports` only. BUG-009 shows the same problem in parser error message strings. The fix pattern is established — apply it globally to all `LangError` message strings.

4. **Embedded API (NodusRuntime) is the strongest surface; the CLI lags.** NodusRuntime isolation, `allowed_paths` sandboxing, and the structured result dict all work correctly. The CLI is where the critical bugs live. v2.1 should bring CLI safety up to embedded API standards.

5. **Docs in several places describe behavior that doesn't match the runtime.** `foreach` doesn't exist; `nodus check` doesn't type-check; REPL command lists are inconsistent; `err.kind` for string throws is wrong. Each is individually small, but together they suggest docs and runtime have been diverging. A doc accuracy pass alongside the fix work would pay dividends.

---

## Out-of-scope: v2.0.x emergency patch

If a v2.0.1 patch is needed before v2.1.0 is ready, scope it to exactly:
- #1 BUG-016 — `fs.read` path traversal (security)
- #2 BUG-017 — BOM file crash (stability)
- #3 BUG-007 — RecursionError leak (stability)
- #29 META — `pyproject.toml` classifier downgrade

Do not include anything else in a v2.0.1 patch. Keep the diff minimal for fast review and release.
