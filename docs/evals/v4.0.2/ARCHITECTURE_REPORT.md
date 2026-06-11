# Architecture Report — Sentinel on Nodus 4.0.2

**Project:** Sentinel — incident triage and digest-publishing orchestrator  
**Eval context:** Built during the v4.0.2 independent eval to stress-test real-world
orchestration, AI-native features, and the tool registry under production-shaped load.  
**Source:** `Nodusv4.0.2 fable5/sentinel/`

---

## What was built

Sentinel ingests 13 raw alerts (including malformed records and duplicates),
classifies them through a registered tool via a coroutine worker pool, fans out
into parallel dedupe/stats steps, enriches through a flaky upstream guarded by
retry annotations, pages on-call exactly once per team, runs a dynamically
constructed per-host remediation task graph, and publishes a digest idempotently —
with an identity-stamped audit trail of every event.

~430 lines total: 205 in `src/main.nd`, ~160 across five `lib/` modules, 70 of
tests. Zero application Python — the only Python is the Nodus runtime itself.

---

## Why this project

The brief was to determine whether Nodus's abstractions pay for themselves. A
hello-world workflow exercises syntax; Sentinel was designed so that every
Nodus-native concept carries real load:

- The parallel dedupe/stats level only works if the scheduler actually levels the DAG.
- Exactly-once publishing is only meaningful if a replay is actually suppressed.
- The flaky geo service is only survivable if `@retry` actually re-executes.
- The dead pager only proves the circuit breaker if state visibly transitions.
- Handing triage results to the publishing goal only works if memory namespaces
  actually cross workflow boundaries.

All five behaviors were verified in the final run: exit 0, `failed=[]` in both
phases, breaker `closed → open`, replay `duplicate-suppressed`, audit log showing
exactly 2 `page.sent` events for 3 paging calls.

---

## Nodus capabilities exercised

| Concept | Where | Verdict |
|---|---|---|
| `workflow` DSL, `after` deps, parallel levels | `triage` in main.nd | **Works well.** Declarative, readable, `plan_workflow()` shows levels. |
| `goal` DSL | `publish_digest` | Works (identical to workflow; the two names add little). |
| `state` variables | both phases | Work, with a serious interpolation blind spot (B3). |
| `checkpoint` | ingest/dedupe/finalize | Records labeled snapshots in the result; resume untested. |
| Dynamic task graphs `task()`/`run_graph()` | lib/remediate.nd | Works, incl. `{"deps": [...]}` fan-in. Result shape is undocumented. |
| Coroutines + channels | lib/stream.nd | Work, even nested inside a workflow step. Errors are swallowed (B5). |
| `std:tool` registry + invoke | lib/tools.nd + main.nd | Works **only** when registration is in the entry module (B1) and only with undocumented simple-form schema (B6). |
| `@retry` annotation | geo enrichment | **Works as advertised** — 2 failures then success, verified. |
| `@exactly_once` annotation | on-call paging | **Works as advertised** — body ran once per distinct args. |
| `std:effects` manual protocol | lib/publish.nd | Works once you read the runtime source; the documented API does not exist (B15). |
| `std:circuit_breaker` | notify step | Works (`closed → open` after 3 failures); real signature differs from docs (B10/B11). |
| `std:memory` (kv + namespaces) | stats/finalize → assemble | Works; clean way to hand data between a workflow and a goal. |
| `std:identity` | lib/audit.nd | `execution_unit_id()` works; `trace_id()` is nil under CLI (B12). |
| Step-level `with { retries }` | attempted on gate step | **Unusable from the CLI** (B2); replaced with an in-body sync loop. |
| `std:test` | sentinel_test.nd | Good assertion library, 12/12 passing; runner has Windows + import-rooting defects (B8/B9). |
| stdlib | fs, json, strings, hash, collections, time | Mostly solid; `time.format` broken (B7). |

---

## What was hard

1. **The debugging cliff.** Authoring took ~30 minutes; making it run took several
   hours, nearly all spent bisecting B1 — a re-execution storm whose visible symptoms
   (recursion errors, wrong-file stack traces, stdout limits, hundreds of orphaned
   graph snapshots) all pointed away from the actual cause (where `tool.register` was
   called). A language whose value proposition is orchestration cannot afford failure
   modes that destroy the causal chain between mistake and symptom.

2. **Docs that describe a different language.** `std:effects`, `std:circuit_breaker`,
   `std:memory.tag`, and the tool schema format are all documented with APIs that do
   not exist in the shipped runtime. Every AI-primitive module except `std:tool`
   required reading the installed Python/`.nd` source to use.

3. **Closure semantics.** Three separate rules (outer `let` silently shadows, no
   per-iteration loop bindings, state vars invisible in interpolation) each produce
   silent wrong behavior or late runtime errors rather than compile-time feedback.

4. **Retry duality.** Annotation `@retry` works; step option `retries:` doesn't
   (in CLI context). The two features share a name and a concept but not a runtime path.

---

## What was genuinely good

- The **workflow result map** (`steps`, `state`, `failed`, `timings`, `attempts`,
  `cache_hits`, `checkpoints`, `graph_id`) makes a run fully observable with zero setup.
- **Annotations** (`@exactly_once`, `@retry`) are the best idea in the language:
  one line buys correct idempotency/retry semantics that take real care in Python.
- The **import error messages** (full list of attempted paths) and `nodus check`'s
  precise locations are excellent.
- `pip install` worked first time; the missing-extra error for retry support gave
  the exact install command.
- The **shipped skill file** teaches the quirks honestly; AI-authorability of the
  syntax is high.
