# Phase 0 Decisions

**Doc ID:** `docs/design/v3/00-phase-0-decisions.md`
**Status:** Locked
**Author:** Shawn Knight
**Decision date:** 2026-05-24
**Cross-reference:** V3_0_PLAN.md §0a

---

## Purpose

This document is the audit trail for the five Phase 0 decisions that gated v3.0 design work. Each decision was resolved during the v3.0 planning conversation on 2026-05-24, before any Phase 1 design docs were drafted.

Phase 1 design docs (01, 02, 03) treat these decisions as locked inputs. This doc exists separately so the decision history survives independent of the V3_0_PLAN.md working document.

For each decision, this doc records: the question, the options considered, the chosen option, the reasoning, and the rejected alternatives with their costs.

---

## Decision 1: Migration window

**Question:** Is v2.1.1 maintained for security patches after v3.0 ships, or end-of-life immediately at v3.0 release?

**Options considered:**

- **EOL at v3.0 release.** v2.1.1 receives no further patches. Users on v2 must migrate to v3 to receive any fixes, including security fixes.
- **Maintained v2.1.x branch.** Critical security patches backported to v2.1.x for some defined window (6 months, 1 year, indefinite).

**Decision: EOL at v3.0 release.**

**Reasoning:**

1. Solo maintainer capacity. Backporting fixes to a v2.1.x branch doubles the work for every security finding — write the patch, port the patch, test both releases, publish both releases. Sustainable only with sustained maintainer time that does not exist for this project.
2. Small user base. v2.x deployment is minimal; the migration burden for existing users is real but small in aggregate.
3. v2.1.1 remains installable. `pip install nodus-lang==2.1.1` continues to work even after EOL — the version is not yanked, just no longer patched. Users who cannot migrate sit on known-state code with no future patches, but they retain a working pin.
4. Honest signaling. EOL is a clearer message than "maintained but probably not actually maintained" — it tells users that v3.0 is the supported line.

**Rejected alternative cost:** maintaining v2.1.x for a defined window would cost roughly 50% additional time per security patch (one fix becomes two ports plus two releases). For a release like the BUG-046 sandbox fix, that's an extra day of work that the project cannot reliably allocate.

**Migration consequence:** CHANGELOG and PyPI metadata must state v2.x EOL explicitly. Migration guide (`docs/migration/v2-to-v3.md`) must include the EOL notice prominently.

---

## Decision 2: Integer type model

**Question:** How does Nodus introduce an integer type to solve BUG-012 (large integer precision loss)?

**Options considered:**

- **Model A: Integer as default.** All numeric literals without a decimal point parse as int. `1` is int, `1.0` is float. Mixed arithmetic promotes. Breaks JSON round-trip, every existing numeric literal has changed type, silently breaks `1 / 2 == 0.5` style code.
- **Model B: Integer opt-in via literal suffix.** Float remains the default. New suffix (`1i`) plus stdlib parse functions for explicit int values. Non-breaking for existing code.
- **Model C: Integer internal-only.** No user-facing int type. Stdlib functions like `math.big_int` provide arbitrary-precision integer arithmetic for users who need it. The language continues to claim no integer type.

**Decision: Model B.** Literal syntax `1i` (lowercase suffix, no whitespace, no digit separators in v3.0).

**Reasoning:**

1. Model B actually solves BUG-012 for users who need it, without forcing the cost on users who don't.
2. Model A's blast radius is 3-5 weeks of focused work for a solo maintainer. The VM arithmetic paths, test suite, JSON round-trip, stdlib audit, embedding marshaling, and guide rewrites compound. Model B is 1-2 weeks of bounded work.
3. Model A silently breaks `1 / 2 == 0.5` code, which violates the v3.0 principle that breaking changes must be explicit in the CHANGELOG. Model B is non-breaking by definition.
4. Model A entangles with the equality coercion decision — `1 == 1.0` semantics force a decision before integer type can ship. Model B keeps them independent.
5. Model C is the cowardly option. It ships fast but doesn't earn the v3 banner. The complaint "the language can't represent integers without precision loss" remains technically true; users get a workaround library rather than a language fix.
6. Model A remains available for v4.0 if Model B's opt-in proves insufficient. The reverse — shipping Model A and walking it back — is much harder.

**Rejected alternative costs:**
- Model A: 3-5 weeks implementation, silent user code breakage, mandatory equality coercion decision.
- Model C: ships fast but doesn't solve the underlying complaint; permanent rough edge.

**Implementation specification:** see `01-integer-type.md`.

---

## Decision 3: Equality coercion semantics

**Question:** Does v3.0 change how `==` handles type coercion (e.g., `0 == false` evaluating to `true`)?

**Options considered:**

- **Keep coercing.** `==` continues to coerce across types. No breaking change. Document the existing behavior as a stable contract.
- **Strict equality.** `==` becomes type-strict. `0 == false` becomes `false`. Breaking change to existing behavior.
- **Staged.** Keep `==` coercing, introduce `===` for strict equality. Both available. Users opt into strict semantics where they want them.

**Decision: Keep `==` coercing. No breaking change in v3.0.**

**Reasoning:**

1. Coercion is the documented contract today, and users have built code around it. Silently flipping the semantics is the worst possible kind of breaking change — code continues to parse and run, but produces different results.
2. The staged option (adding `===`) is its own design question — what's the operator syntax, how does it interact with `!=`, how do hash maps handle key equality, etc. Worth doing properly in v4.0 if user feedback demands strict equality; not worth rushing into v3.0.
3. Decision 2 (Model B integer type) makes equality coercion independent of integer work. Without Model A, there's no forcing function to revisit `==` semantics in v3.0.
4. Issue #28 (DESIGN equality) and issue #16 (BUG-013 `0 == false`) close as documentation work in Phase 4. The behavior is locked; the docs explain it.

**Rejected alternative costs:**
- Strict equality: silent breakage of existing code, conservative estimate 1-2 weeks of design + implementation, plus uncountable user code audit.
- Staged: requires `===` design (syntax, hash semantics, !== negation), 2-3 weeks of design + implementation, ongoing dual-operator documentation burden.

**Implementation consequence:** `error-handling.md` and `types-and-values.md` document the coercion contract explicitly. No code changes in Phase 3 for equality.

**Deferred to v4.0:** strict equality operator `===`, if user feedback demands it.

---

## Decision 4: Python error wrapping policy

**Question:** When Nodus stdlib functions wrap Python operations that raise exceptions, how do Python error messages appear in the resulting Nodus err record?

**Options considered:**

- **Document.** Keep current leak-through behavior. Python error text continues to appear verbatim in `err.message`. Document this as policy.
- **Annotate.** Wrap Python errors in Nodus-shaped err records, but preserve the Python text in a new `err.caused_by` field. Best of both worlds — clean Nodus voice in `err.message`, debuggable Python detail in `err.caused_by`.
- **Replace.** Nodus catches Python exceptions at every stdlib boundary and rewraps them in Nodus-shaped err records. Users never see Python text in `err.message`. Debug escape hatch via CLI flag.

**Decision: Replace, stdlib only.** Embedding API surface is unchanged — host Python callers continue to receive Python exceptions.

**Reasoning:**

1. Document is the weakest option. It says "the leak is fine, we'll just tell users to expect it." Bakes inconsistency into the language permanently — Python errors look like Python, parser errors look like Nodus, runtime errors look like Nodus. Pushes cleanup work onto every user instead of doing it once in the language.
2. Annotate is the middle path. Same wrapping work as Replace, but with an extra `caused_by` field. Marginally friendlier for debugging, but adds a new field to the err record contract (interacts with decision in design doc 3), and users who want clean errors still see Python text reachable from `err.caused_by`.
3. Replace establishes the pattern. Every future Python-backed stdlib function ships with proper error wrapping from day one — there's a pattern to follow. Annotate or Document create a permanent rough edge that costs more to fix later than to do right now.
4. Replace matches the language's character. Nodus already has its own voice in parser errors, runtime errors, the err record. Python errors leaking through breaks that voice. Replace is the only option that makes Nodus sound like Nodus all the way down.
5. The debuggability concern (Replace loses Python detail) is addressed by the `--trace-errors` CLI flag specified in `02-python-error-replacement.md`. Maintainers and advanced users can still see Python tracebacks when needed; the err record stays clean.

**Scope clarification:** Replace covers the stdlib surfaces that wrap Python (json, fs, path, math per design doc 2). The embedding API surface — host Python code calling `runtime.run()` — continues to raise Python exceptions, not Nodus errs. Replace is about what Nodus *user code* sees; the embedding boundary is about what Python *host code* sees.

**Rejected alternative costs:**
- Document: zero implementation cost, permanent quality ceiling, BUG-038 and BUG-045 become "won't fix" rather than "fixed."
- Annotate: same implementation cost as Replace, adds `err.caused_by` field complexity, only marginal user value over Replace.

**Implementation specification:** see `02-python-error-replacement.md`.

---

## Decision 5: Eval timing

**Question:** Run a baseline rubric eval against v2.1.1 before starting v3.0 work, or run a single rubric eval against v3.0 after release?

**Options considered:**

- **Baseline now.** Run the formal rubric eval against v2.1.1 before v3.0 work starts. Provides a comparison point between guide-writing work (v2.0.0 → v2.1.1) and v3.0 work (v2.1.1 → v3.0).
- **Single eval at v3.0 release.** Skip the v2.1.1 baseline. Run one formal rubric eval against v3.0 after PyPI publish, compared against the v2.0.0 score (5.52).

**Decision: Single eval at v3.0 release.** Scored against the v2.0.0 rubric for comparability with the 5.52 baseline.

**Reasoning:**

1. v2.1.0 shipped without a formal rubric eval — the "eval" between v2.0.0 and v2.1.0 was the guide-writing exercise, which surfaced 23 issues but did not produce a composite score. There is no v2.1.x rubric data point to baseline against.
2. Running a fresh v2.1.1 rubric eval now would consume time better spent on v3.0 design and implementation. The data point would be useful for the playbook capture but is not necessary for v3.0 to ship.
3. The v3.0 eval comparison point is v2.0.0 (5.52). Two release cycles of work (v2.1.0 guide writing + v2.1.1 security patch + v3.0 features and breaking changes) compress into one composite score change. The data is noisier than ideal but it's the data that exists.
4. The methodology gap (v2.1.0 had no rubric eval) gets captured as a refinement in the Phase 5 playbook: future major releases run the formal rubric eval, not just guide-writing-as-eval, so every release has a comparable score.

**Rejected alternative cost:** running a v2.1.1 baseline eval would take 1-2 days of focused time, displace Phase 1 work, and produce a data point useful primarily for the playbook capture rather than for v3.0 decisions.

**Implementation consequence:** Phase 5 release procedure (V3_0_PLAN.md §2) runs one eval against v3.0. Phase 5 playbook capture (`docs/governance/RELEASE_PLAYBOOK.md`) includes the methodology refinement.

---

## Summary table

| # | Decision | Locked value | Implementation doc |
|---|----------|--------------|--------------------|
| 1 | Migration window | EOL at v3.0 release | Phase 4 docs |
| 2 | Integer type | Model B opt-in, `1i` syntax | `01-integer-type.md` |
| 3 | Equality coercion | Keep `==` coercing, document | Phase 4 docs |
| 4 | Python error wrapping | Replace, stdlib only | `02-python-error-replacement.md` |
| 5 | Eval timing | Single eval at v3.0 release | Phase 5 release procedure |

---

## Phase 1 design questions remaining after Phase 0

Phase 0 closed two of the original five design questions without requiring design docs (decisions 3 and 5 became documentation/procedure rather than implementation). Three design questions remained for Phase 1:

1. Integer type implementation spec — `01-integer-type.md`
2. Python error replacement taxonomy — `02-python-error-replacement.md`
3. err record shape (`err.payload` semantics, bare identifier map keys) — `03-err-record-shape.md`

All three design docs are drafted as of 2026-05-24. Phase 1 exits when each design doc's exit checklist completes.