# Nodus v3.0.0 — Evaluation Rubric

Evaluator: Claude Code (researcher mode, stress test)
Date: 2026-05-25
Reference: v2.0.0 baseline composite score: 5.52/10

---

## Scoring Table

| Dimension | Score | Rationale |
|-----------|-------|-----------|
| Install and first-run UX | 9/10 | `pip install nodus-lang==3.0.0` clean, 205 kB wheel, `nodus --version` works immediately, no setup friction |
| CLI ergonomics | 8/10 | Grouped --help is excellent (BUG-029 #27 confirmed); `nodus run`, `nodus check`, `nodus debug`, `nodus dis`, `nodus ast` all work; `debug --help` shows help not "file not found" (BUG-047); minor: import path convention not intuitive |
| Error message quality | 7/10 | Most runtime errors are clear with file/line/col; `catch (e)` gives cryptic "Expected identifier, got '('"; unclosed string gives helpful message; mixed map keys give excellent dual-fix suggestions; `has_key(err, key)` gives "expects a map" with no hint to use `.payload` |
| Parser robustness | 8/10 | Deep nesting, empty files, whitespace-only, comment-only all handle cleanly; multi-line map values work (BUG-039); unicode identifiers crash without a clear error; `1I` gives name error instead of parse error |
| Type system behavior | 7/10 | Equality coercion documented and stable; `0 == false` true, `nil == false` false — consistent; type names "number" vs "int" is inconsistent; `len()` returns float rather than int despite int type existing; `has_key` on Record throws |
| Integer type (new in v3.0.0) | 8/10 | Core arithmetic correct (int+int=int, int+float=float, int/int=float), precision-preserving for large values, `json.parse_int` exact, `math.idiv` correct with truncation-toward-zero; `1I` not a parse error (spec says it should be); int display as bare `2` vs `2i` confusing |
| Standard library completeness | 5/10 | Good coverage of strings/json/math core; `math.log` and `math.pow` missing despite being in error-surfaces.md; `path.relative` and `path.absolute` missing; `fs.mkdir` and `fs.delete` not exported; `len()` returns float |
| Standard library correctness | 6/10 | `strings.is_blank` (BUG-035), `utils.get`, `path.ext` (BUG-037), `json.parse_int` all correct; `math.sqrt(-1)` THROWS instead of returning err (critical correctness failure); `fs.mkdir` silently ignores existing paths instead of erroring |
| Python error replacement (v3) | 6/10 | Excellent for json parse/stringify and fs.read — Nodus-voice messages, zero Python text leak; `--trace-errors` and env var work; BUT `math.sqrt(-1)` still throws (not wrapped), `json.parse(123)` throws instead of returning err, three math functions missing entirely |
| err record shape (v3) | 8/10 | `err.payload` always nil (not absent) when no data — design doc 3 confirmed; `err.kind` consistent; mixed keys parse error has excellent suggestions; FAIL: `has_key(err, key)` throws type error — migration guide understates as "requires rewriting" when actual result is crash |
| Map/record disambiguation (v3) | 9/10 | `{foo: "bar"}` = record, `{"foo": "bar"}` = map — clean; mixed keys give parse error with two fix suggestions; dynamic keys `{(k): v}` work; multi-line map value works (BUG-039); near-perfect execution |
| Module system | 7/10 | Import with `std:` prefix works cleanly; user module imports work without extension; circular import detected; import inside fn gives good error; path traversal blocked; FAIL: import with explicit `.nd` extension doubles the extension confusingly |
| REPL | 5/10 | Starts and identifies as 3.0.0 REPL; banner clear; piping commands in non-interactive mode fails; :help and other commands not testable in automated fashion; incomplete evaluation due to interactive-only nature |
| Workflow / graph runner | 4/10 | `nodus workflow --help` shows proper subcommands; basic structure present; BUG-050 cycle detection not confirmed; no actual workflow tested — insufficient to score higher |
| Tracing / observability | 8/10 | `--trace` exists; `--trace-errors` fully functional with env var; `--trace-imports` works with `[import] Resolved` and `[import] Cache hit` messages; `--step-limit` fires with clear error; `--time-limit` present; `nodus dis` readable |
| Embedded / programmatic API | 3/10 | `NodusRuntime` class exists and is well-documented; `run_source` returns proper dict with ok/stdout/stderr; step limit in embedded mode works; BUT `host_globals` and `initial_globals` BROKEN (CRITICAL BUG-E03); host Python exceptions swallowed (CRITICAL BUG-E04); top-level `run_source` returns VM object (confusing) |
| Documentation accuracy | 5/10 | Design docs match implementation for map/record, integer arithmetic, Phase 0 decisions; FAIL: error-surfaces.md documents math.log, math.pow, path.relative, path.absolute, fs.mkdir, fs.delete as existing — they don't; math.sqrt documented as err-returning but throws |
| Documentation completeness | 6/10 | error-surfaces.md well-structured; migration guide covers main cases; REPL.md not retrieved in full; catch syntax (no parens) likely underdocumented; import path convention (no extension) needs clearer note |
| Migration guide quality | 5/10 | Covers: record/map disambiguation, err.payload, integer type, err.kind changes; MISS: `has_key(err, key)` CRASH not "silent change"; MISS: embedding API host_globals behavior; MISS: math.log/pow/path.relative/absolute entirely absent (new v3 APIs that don't exist) |
| Stability under stress | 7/10 | Parser survives deep nesting, empty/comment-only files, malformed syntax; step limit works; path traversal blocked; no crashes from valid programs; FAIL: math.sqrt(-1) crashes uncaught if not in try/catch; unicode identifiers crash with cryptic error |
| Overall first-week usability | 6/10 | A competent engineer CAN build things in Nodus v3.0.0 (log parser built in ~15 min); the integer type, error replacement, and map/record disambiguation all add genuine value; but the broken embedding API and missing stdlib functions mean any non-trivial use case requires workarounds |

---

## Composite Weighted Score

| Category | Weight | Score | Weighted |
|----------|--------|-------|---------|
| Core language (parser, type system, control flow) | 15% | 7.3 | 1.10 |
| New v3.0.0 features (int type, err replacement, err shape, map/record) | 20% | 7.6 | 1.52 |
| Standard library (completeness + correctness) | 15% | 5.5 | 0.83 |
| CLI and tooling | 10% | 8.0 | 0.80 |
| Embedding API | 10% | 3.0 | 0.30 |
| Documentation (accuracy + completeness + migration) | 15% | 5.3 | 0.80 |
| Error quality and observability | 10% | 7.5 | 0.75 |
| Stability under stress | 5% | 7.0 | 0.35 |

**Composite score: 6.45/10**

---

## Comparison to v2.0.0 baseline (5.52/10)

**Overall improvement: +0.93 points (+17%)**

### Dimensions where v3.0.0 clearly improved:
- **Integer type** (new): Addresses the real BUG-012 precision problem cleanly; design is sound; most arithmetic cases correct
- **Map/record disambiguation**: The parse-time enforcement with helpful suggestions is a genuine UX win
- **err.payload consistency**: Always-nil payload (never absent) removes a real source of key-lookup errors
- **CLI ergonomics**: Grouped --help, `debug --help` fix, `else if` parsing — polish visible
- **Error messages**: Nodus-voice errors for json.parse, fs.read are clean; `--trace-errors` well-implemented

### Dimensions where v3.0.0 shows design-doc discipline paying off:
- Phase 0 decision 3 (equality coercion unchanged) — correctly kept backwards compat
- Phase 0 decision 2 (opt-in integer type) — doesn't break existing code
- Design doc 3 decisions: err.payload nil not absent ✓, mixed key parse error ✓

### Dimensions where v3.0.0 did NOT improve meaningfully:
- **Embedded API**: Was limited in v2, is still limited AND has critical new bugs (BUG-E03, BUG-E04)
- **Standard library completeness**: Missing functions actually increased from docs promises
- **Migration guide**: Covers some cases but misses critical breakages
- **Documentation accuracy**: Design docs made specific promises (math.log, path.relative, etc.) not kept

### Where the design-doc-driven v3.0.0 cycle helped:
The explicit design documents (docs/design/v3/) served as falsifiable claims. Because they existed, this evaluation could definitively say "doc says X, implementation does Y" rather than "behavior seems inconsistent." This is a process improvement that makes bugs findable.

---

## Scoring rationale footnotes

**Weights:**
- New v3.0.0 features weighted highest (20%) because the evaluation mandate is specifically to assess whether the breaking changes delivered value
- Embedding API weighted at 10% because Nodus's primary use case appears to be scripting (CLI), not embedding
- Documentation weighted 15% because the design-doc-driven process creates testable promises
- Stability at 5% because basic stability was already good in v2.0.0

**Score interpretation:**
- 9-10: Excellent, production-ready for this dimension
- 7-8: Good, usable with minor rough edges
- 5-6: Functional but with notable gaps or bugs
- 3-4: Broken in important ways
- 1-2: Does not function for this dimension
