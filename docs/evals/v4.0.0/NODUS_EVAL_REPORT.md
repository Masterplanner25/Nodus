# NODUS v4.0.0 — Independent Post-Publish Evaluation Report

**Evaluator:** independent (no participation in building or releasing v4.0.0)
**Install source:** PyPI, `pip install nodus-lang==4.0.0`, verified `Nodus 4.0.0`
**Method:** shipped-behavior only; public docs consulted, source not read for behavior
**Evidence base:** `EVAL_LOG.md` (25 entries). Composite rubric: **7.3 / 10**.

---

## TL;DR verdict

Nodus v4.0.0 is a coherent, honestly-scoped release that does the hard things well — typed errors
with file:line:col and zero leaked Python tracebacks, a clean embedding API with real runtime
isolation, genuinely-concurrent async builtins, and a `stability` index that openly labels its
experimental surfaces. It is held back by one security default (the embedded runtime grants
unrestricted filesystem access unless you opt into `allowed_paths`) and a cluster of doc-vs-runtime
contradictions (base64 decode, division-by-zero "catchability", and the workflow failing-step example)
that would each burn a real adopter who trusted the docs. None are CRITICAL; the language core is
solid enough to adopt, provided you embed with `allowed_paths` set and treat the workflow/goal/channel
DSLs as the experimental features they are advertised to be.

---

## Findings ordered by severity then leverage

### HIGH

**1. Embedded `NodusRuntime()` has no filesystem sandbox by default (BUG-001).**
The CLI jails to the project root and blocks `../` escapes out of the box. The default embedded
runtime does not: `fs.read("../../.../etc/hosts")` returned the full file. The mitigation
(`allowed_paths=[...]`) exists and works, but it is opt-in. For a runtime whose headline use case is
executing AI-generated code inside a host process, an open-by-default disk is the highest-leverage
finding here. (LOG #10)

**2. `base64_decode` returns bytes-as-hex, not the documented string (BUG-002).**
`standard-library.md` shows `base64_decode(b64) // "hello world"`. The actual return is a `bytes`
value; `== "hello world"` is `false` and `str(...)` yields hex. The documented round-trip cannot be
reproduced, and there is no obvious bytes→string path in the doc. (LOG #13)

### MEDIUM

**3. Division-by-zero docs contradict the runtime (BUG-003).** `error-handling.md` lists div-by-zero
as catchable via `try/catch` (kind `"runtime"`). Reality (and the CHANGELOG): integer `1i/0i` returns
an **err-value** (`kind:"math_error"`, `origin:"vm"`) and never throws, so `catch` never fires. The
runtime behavior is intentional and documented in the CHANGELOG/migration guide; the error-handling
guide is simply stale. (LOG #15, #22)

**4. A workflow step that divides by zero reports success and runs downstream (BUG-004).** Because the
arithmetic error is a value, not a throw, the step "succeeds", `r["failed"]` is empty, and dependents
run. The workflow guide's own canonical failing-step example uses `1/0` and claims the opposite. An
explicit `throw` propagates correctly — so the workflow engine is fine; the trap is the silent
err-value. (LOG #14, #15)

**5. `std:strings` lacks `starts_with`/`ends_with` (BUG-005).** Only `contains` exists — a weaker and
incorrect substitute for extension filtering. This was the first thing I hit building a real task. (LOG #23)

**6. `break`/`continue` unsupported, reported as "Undefined variable: break" (BUG-006).** The absence
is documented in LANGUAGE_SPEC, but the runtime message reads like a typo, not a missing feature.
Idiomatic loop code uses `break`; this is a real AI-authorability gap. (LOG #17)

**7. Migration guide omits the most common v3→v4 break (BUG-007).** Bare integer literals are now
floats, and `json.parse(...).field` now throws — yet the guide (which is otherwise accurate and
verifiable) covers neither. A v3 program silently "half-runs" with float semantics. (LOG #22)

### LOW / COSMETIC

Non-portable Windows doc example (BUG-008), bare `import` binds nothing (BUG-009), `list_push` vs
`push` split (BUG-010), `for k in m` lacks a `keys()` hint (BUG-011), `await` generic error (BUG-012),
help mojibake on Windows console (BUG-013). Details in `NODUS_EVAL_BUGS.md`.

---

## Migration audit (v3.0.2 → v4.0.0)

A real migration guide exists at `docs/migration/v3-to-v4.md`, and it is **accurate where it speaks**:
I ran every documented helper (`math.is_float`/`is_int`/`is_numeric`, `type_eq`, `bool.equal`,
`index_of`→nil), string interpolation, and the cyclic-workflow err payload — all matched the guide
exactly (LOG #22). The CHANGELOG's breaking-change list (`type=="float"`, no cross-family `==`
coercion, float div→inf/nan, int div→err-value, cyclic→err record) also matched reality.

The gap is what the guide leaves out. A representative v3 program (`let count = 3`, plain-int loop,
`json.parse(...).name`) run unmodified on v4 did **not** cleanly fail — it executed with everything
silently promoted to float (`total` printed `3.0`) until the `json.parse` dot-access finally threw
"Field access is only supported on records". Neither the float-literal change nor the json.parse
dot→bracket break is in the migration guide. Because these are silent (no error at the literal site),
they are the changes most likely to ship subtle bugs into "migrated" code. The guide produces working
code for everything it covers; it just doesn't cover the two most common patterns.

---

## "Build something real" experience

I built a JSON-directory → report tool: `main.nd` (entry) plus a `stats.nd` export-module, reading
four order JSON files, aggregating totals/status-counts/spend-by-customer, and writing `report.json`.
Four stdlib modules (fs, json, strings, math) plus the local module; ~75 lines. Final output was
correct and `nodus check`/`fmt` both passed (LOG #23).

It took ~15 minutes, with two stops, both stdlib-discoverability:
1. `strings.ends_with` doesn't exist → "Missing module export: ends_with" → switched to `contains`.
2. `push(...)` isn't a builtin → "Undefined function: push" → the builtin is `list_push`; `push`
   is `std:collections`-only.

Everything else — `export fn` / `import "./stats" as stats`, `has_key`, `math.round`, bracket-mutation
on maps, string interpolation in `print` — worked first try. The error messages were precise enough
that each fix took seconds, which is the system working as intended even when the stdlib surface
surprised me. What would have made it smoother: `starts_with`/`ends_with`, and one canonical
list-append name.

---

## Per-audience verdicts

**The AI agent author (the primary audience).** Mostly strong. The surface is enumerable, errors are
uniform and positioned with no Python leakage, and `nodus stability` gives a model a machine-readable
map of what's safe to use. Two things undercut it: (a) misleading messages on common foreign keywords
(`break`, `await`, `+=` are at least good) — a model that emits `break` gets "Undefined variable", not
"unsupported"; and (b) doc/runtime contradictions (base64, div-by-zero) that a model would read from the
docs and get wrong. The single most important fix for this audience is BUG-001: a model generating code
against a default `NodusRuntime` can read the host's entire filesystem.

**The human adopter.** Good on-ramp, legible errors, honest stability labeling. They will trust the
docs and get bitten exactly three times (base64, div-by-zero catchability, the workflow failing-step
example). Each is a "the doc said X, the runtime did Y" moment that erodes trust disproportionately.

**The embedder / library author.** The API is clean (`run_source` → structured dict), runtimes are
isolated, `register_function` works, and the 200ms deadline trap is real but documented with a working
fix (`timeout_ms=None`). They must know to pass `allowed_paths` — without it the sandbox they assume is
present is absent (BUG-001).

**The migrating v3 user.** A real, accurate guide eases the explicit breaks, but the silent ones
(integer literals → float; json.parse dot→bracket) aren't signposted, so "it ran" does not mean "it's
correct." They should grep for bare integer literals and `json.parse(...).` access themselves.

---

## Comparison to v3.0.2 baseline

v3.0.2 was not formally scored, so this is qualitative. v4.0.0 is a deliberate, well-documented major
release: it tightens the type model (strict `==`, explicit `int` via `i`, float-by-default literals),
overhauls the error model with five location fields and an errors-as-values stance for arithmetic, and
adds the experimental coroutine/channel/workflow/goal surface plus async builtins. The engineering
quality of the *disclosed* changes is high — the migration guide and CHANGELOG verify against reality
almost everywhere I checked. The regressions relative to that quality bar are the doc contradictions
where the new errors-as-values model wasn't propagated into `error-handling.md` and the workflow guide,
and the unchanged open-by-default embedded sandbox. The release is an improvement in rigor over what a
v3.x user would expect; the remaining sharp corners are concentrated, identifiable, and fixable without
further breaking changes.

---

## Note on prompt vs. shipped reality

The evaluation prompt's Section 4.3 describes a Goal DSL with `success_when {}` / `fail_when {}` blocks.
That form does not exist in shipped v4.0.0 (`Syntax error: goal body must contain state declarations or
steps`). The public docs say `goal` and `workflow` are the same feature with `step`/`after` syntax, and
that is what ships. I evaluated the shipped (documented) goal surface. (LOG #16)
