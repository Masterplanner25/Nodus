# Nodus v4.0.2 — Post-Publish Eval Report

**Eval date:** 2026-06-10  
**Version:** v4.0.2 (PyPI, POST-PUBLISH)  
**Evaluator:** Claude Fable 5 (independent — not the maintainer)  
**Method:** Autonomous build of a complete project (Sentinel — see `ARCHITECTURE_REPORT.md`) against `nodus-lang 4.0.2` freshly installed from PyPI, Python 3.11.9, Windows 11.  
**Composite score:** 5.2 / 10

---

## TL;DR

v4.0.2 is a functionally real language with a genuine value proposition in the
orchestration/agent niche — and a runtime that cannot yet be trusted for production
work. The headline AI-native features (`@exactly_once`, `@retry`, effects, memory,
circuit breaker) are real and work. One P0 bug (B1: entry-script re-execution storm
triggered by cross-module tool registration) corrupts execution itself and produces
symptoms that destroy the causal chain needed to debug it. A second P0 bug (B2: step
`retries:` is a silent no-op from the CLI) makes the flagship retry syntax unusable.
The documentation for AI-native modules describes APIs that do not exist in the
shipped runtime. Each of these issues alone would block recommendation; together they
place v4.0.2 in "promising experimental" territory, consistent with the `nodus
stability` output itself.

---

## Scores (1–10)

| Axis | Score | Justification |
|---|---|---|
| Language Design | **6** | Small, consistent, easy to hold in your head; closure/scoping semantics undermine it. |
| Runtime Design | **4** | The right primitives, genuinely first-class — sabotaged by one critical bug and silent failure modes. |
| Documentation | **5** | Enormous, well-organized, and partly fictional. |
| Tooling | **6** | check/fmt/repl/ast/dis/lsp/dap/test/package-manager is a huge surface for a young language; the test runner has three defects. |
| AI-Native Features | **7** | The standout. Effects, tools, memory, identity, retry, breaker as stdlib — and annotations that actually work. |
| Production Readiness | **3** | One P0 bug corrupts execution itself; step retries don't work from the CLI; state stores poison themselves. |

---

## Findings by severity

### P0 — Critical

**B1: Tool registered in an imported module + invoked inside a workflow step → entry-script re-execution storm**

A script whose workflow step calls `tool.invoke()` on a tool whose `tool.register()`
executed inside an imported module re-executes the entire entry script in a loop
(~35 times before limits kill it). Top-level side effects re-run each time. Secondary
symptoms: `maximum recursion depth exceeded` inside `tool.invoke`, error locations
attributed to the wrong file/function, `Sandbox error: stdout limit exceeded`, and
hundreds of orphaned graph snapshots in `.nodus/graphs/` (210 after two failed runs).

Registering from the entry module with an imported handler function is clean, so the
workaround is cheap — but nothing in the error output diagnoses this. The failure is
a storm of unrelated-looking errors. This is a correctness catastrophe for a language
whose value proposition is "orchestration."

**B2: Step-level `with { retries: N }` never completes under `nodus run`**

A step that throws with `retries: 2` returns immediately: `failed=[]`, `attempts=1`,
no retry ever executes, and an incomplete run is persisted to the `.nodus` store. The
documented behavior (workflows guide §5) is wrong; the skill reference admits retries
are async and need a "sweep loop", but `nodus run` has no sweeper. The flagship retry
syntax is unusable from the CLI and silently reports success.

---

### P1 — High

**B3: Workflow state variables invisible inside string interpolation**

`state x = 0i; step a { x = 5i; print("\(x)") }` → runtime `Undefined variable: x`.
Bare reads and cross-step reads work fine. Interpolation lowers into a scope where
state rewriting isn't applied. Insidious because interpolation is the recommended way
to print (single-arg `print`).

**B4: `let` in a `for` loop body does not create per-iteration bindings**

Closures created inside a loop all capture the final iteration's value (Sentinel's
remediation tasks all targeted the last host until a factory-function workaround was
added). Combined with the documented silent-shadow closure rule, closures over
anything mutable are a minefield.

**B5: Coroutine errors are swallowed by `run_loop()`**

A worker coroutine that throws prints to stderr and dies; `run_loop()` returns normally
and the calling step continues with partial results. No flag, no result status, nothing
on the channel. Silent data loss in fan-out pipelines.

---

### P2 — Medium

**B6: `tool.register` accepts JSON-Schema-style schemas that explode at invoke time**

`schema: {type: "object", properties: {...}, required: [...]}` (the form shown in
`docs/guide/ai-primitives.md`) registers fine, then every `tool.invoke` fails with
`argument of type 'Record' is not iterable`. The undocumented "simple form"
(`{"param": "string"}`) works. Docs are actively misleading.

**B7: `time.format()` produces garbage**

`time.format(time.now(), "%Y-%m-%d %H:%M:%S")` → `%Y-%54-%10 %22:%6:%S`
(minute substituted for `%m`, month for `%M`, `%Y`/`%S` untouched).

**B8: `nodus test` crashes on Windows consoles**

`UnicodeEncodeError: 'charmap' codec can't encode character '✗'` — raw traceback.
Workaround: `PYTHONIOENCODING=utf-8`.

**B9: `nodus test` cannot import project code from a `tests/` subdirectory**

Imports resolve relative to the test file's directory, ignoring the `nodus.toml`
project root that `nodus run` honors; `../lib/x` is rejected as "escapes the project
root" even when it doesn't.

---

### P3 — Low / paper cuts

See `NODUS_EVAL_BUGS.md` for B10–B18 with full detail. Summary:

| Bug | Description |
|---|---|
| B10 | `cb.create(name, config_map)` → raw Python error; real signature is positional (seconds, not ms) |
| B11 | `cb.call` never throws; failures return a plain map indistinguishable from success |
| B12 | `identity.trace_id()` / `identity.session_id()` return nil under the CLI |
| B13 | `mem.tag` / `mem.forget` documented in ai-primitives.md but not implemented |
| B14 | `tool.execute` / `tool.available` documented; real API is `invoke`/`call`/`has` |
| B15 | `std:effects` docs describe a different API than ships (wrong arg count, wrong return type, undocumented silent no-op) |
| B16 | Failed-step reporting inconsistent: workflow results list task IDs, goal results list step names |
| B17 | `nodus test` not listed in `nodus --help` |
| B18 | Workflow run snapshots pile up forever in `.nodus/`; no automatic cleanup |

---

## Positive findings

- **Workflow result map** (`steps`, `state`, `failed`, `timings`, `attempts`,
  `cache_hits`, `checkpoints`, `graph_id`) makes a run fully observable with zero setup.
- **`@exactly_once` and `@retry` annotations** deliver verified idempotency and retry —
  the audit log shows duplicate page suppressed and flaky service recovered.
- **`std:memory` namespace KV** cleanly hands data between a workflow and a goal.
- **`pip install` worked first try**; missing-extra error for retry support gave the
  exact install command.
- **Import error messages** (full list of attempted paths) and `nodus check`'s precise
  locations are excellent.
- The **shipped skill file** teaches the quirks honestly; AI-authorability of the
  syntax is high.

---

## Improvement recommendations

**Fix first (correctness):**
1. **B1 storm.** Make cross-module tool registration either work or fail loudly at
   `register` time. Nothing may ever re-execute the entry module implicitly.
2. **B2 step retries.** `with { retries: N }` under `nodus run` should retry
   synchronously (or block on the scheduled retry). Silently reporting success is worse
   than no retry.
3. **B3/B4 scoping.** Make interpolation see state vars; give `for`-loop `let` a fresh
   binding per iteration; make assignment to a captured outer `let` a compile-time error
   instead of a silent shadow.
4. **B5.** Surface coroutine failures: `run_loop()` should return or raise them.
5. Validate tool schemas at registration; reject or normalize nested records (B6).

**Documentation:**
6. Run every snippet in `ai-primitives.md` through the existing `nodus_gate`
   doc-testing machinery — the infrastructure exists; this file bypassed it.
7. Document the real effects protocol including the pending-before-complete requirement;
   document the simple-form tool schema; fix the circuit-breaker signature.
8. Document the result shape of `run_graph()` and the workflow-vs-goal failed-step
   naming inconsistency (B16).

**Runtime/UX:**
9. Auto-expire or cap `.nodus` run snapshots; add `nodus workflow cleanup` to the
   getting-started path (B18).
10. `time.format` rewrite with real strftime semantics (B7).
11. UTF-8-safe output on Windows (B8); honor `nodus.toml` project root in `nodus test`
    (B9); list `test` in `--help` (B17).
12. Set a default `trace_id` under the CLI so audit trails work without embedding (B12).
13. Step-level tracing (`--trace-steps`): task start/finish/retry events instead of
    bytecode.

**Language:**
14. Either give `goal` distinct semantics (success criteria, invariants) or fold it
    into `workflow`; today it is a synonym that costs a keyword.
15. Multi-line call/list literals. The single-line rule is the #1 ergonomic complaint an
    LLM has writing non-trivial handlers. *(Fixed in v4.0.1 — note for completeness.)*

---

## Final verdict

**Would I choose Nodus over building Sentinel directly in Python? Today: no.**

The honest ledger: authoring Sentinel in Nodus was *faster* than Python would have
been — the workflow DSL, the annotations, and the effects/memory/tool primitives
replaced several hundred lines of Python scaffolding with language features that mostly
worked on the first try. The 430-line result is more legible than the equivalent Python,
and an LLM can both write and read it easily.

But the time saved authoring was repaid threefold debugging B1, a runtime bug whose
symptoms (recursion errors, wrong-file stack traces, re-executed side effects, poisoned
state stores) gave no path back to the cause. In Python, every one of Sentinel's
behaviors would be more verbose — and every failure would have a stack trace pointing
at the truth.

**What kind of software becomes easier when Nodus exists?** Small, durable,
tool-dispatching agent pipelines — ingest→classify→enrich→act flows with idempotent
side effects, retries, and audit trails. Nodus's bet — make orchestration, effects,
and tools *language constructs* so programs are short enough for LLMs to write and
verify whole — is the right bet, and `@exactly_once` proves the concept.

The gap is not vision or design; it is runtime trustworthiness. If B1/B2-class bugs are
fixed and docs are brought under the project's own doc-testing gate, Nodus becomes a
defensible choice for its niche. At 4.0.2, it is a promising experimental DSL whose
own `nodus stability` output gives the correct guidance: the core language is stable;
the orchestration layer is experimental, and behaves like it.
