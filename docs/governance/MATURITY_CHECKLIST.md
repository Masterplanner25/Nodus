# Nodus 90-Day Maturity Checklist

Nodus is being matured as:

> A domain-specific execution language for orchestration, workflows, agents, and runtime automation.

**Baseline score:** `72.5 / 100`  
**90-day target:** `78-80 / 100`  
**Re-score date:** 2026-05-31  
**Re-score result:** `82-83 / 100` — target exceeded

---

## Success Criteria

- [x] Canonical product definition published and reflected across README/spec/architecture docs
- [x] Stable core language/runtime surface explicitly defined
- [x] Experimental features explicitly isolated and labeled
- [ ] Workflow/goal/checkpoint/resume semantics documented as invariants — partial (#111)
- [x] Security matrix added for CLI, embedded, and server contexts — partial (SECURITY_POSTURE.md; #112 #113 track gaps)
- [x] Core mypy debt reduced materially in `vm/`, `runtime/`, `compiler/`, and loaders — **260 → 0 errors**
- [x] Artifact verification and closure-verification release steps added
- [x] Overall maturity score improved to at least `78-80` — **scored 82-83**

---

## Phase 1: Days 1-30

### Product Identity
- [x] Write canonical product definition — "orchestration DSL and embedded runtime for agentic systems"
- [x] Update `README.md`
- [x] Update `docs/language/LANGUAGE_SPEC.md` — preamble added establishing DSL identity
- [x] Update `docs/runtime/ARCHITECTURE.md`
- [x] Align CLI/help text — `nodus stability` command + help section
- [x] De-emphasize general-purpose language framing

### Stable vs Experimental Boundary
- [x] Create stability doc — `docs/governance/LANGUAGE_STABILITY_INDEX.md`
- [x] Define Stable Core
- [x] Define Stable Platform — "Mostly Stable" tier
- [x] Define Experimental
- [x] Classify major features into buckets
- [x] Add stability labels in docs/specs — per-section labels in LANGUAGE_SPEC.md

### Semantic Surface Inventory
- [x] Inventory stable runtime/language contracts — LANGUAGE_STABILITY_INDEX.md
- [x] Include import resolution rules
- [x] Include workflow lowering semantics — ARCHITECTURE.md
- [ ] Include checkpoint/resume semantics — #111 (invariant doc); #110 (tests)
- [x] Include coroutine lifecycle semantics — EXECUTION_INVARIANTS.md
- [x] Include tool/agent runtime contracts — COMPANION_LIBRARY_CONTRACT.md
- [x] Include error model surface — LANGUAGE_STABILITY_INDEX.md §8

### Core Module Risk Review
- [x] Identify top 5 highest-risk core modules
- [x] Record current mypy burden — was 260, now 0
- [x] Prioritize refactor order — graduation phases B/C/D

---

## Phase 2: Days 31-60

### Semantic Invariants
- [x] Create semantic invariants doc — `docs/runtime/EXECUTION_INVARIANTS.md` (31 invariants)
- [x] Define workflow state invariants — I-WFLOW-01 through I-WFLOW-03
- [ ] Define dependency ordering invariants — #111
- [ ] Define checkpoint invariants — #111
- [ ] Define resume invariants — #111
- [x] Define coroutine lifecycle invariants — I-CORO-01/02
- [ ] Define module execution/cache invariants — #111

### Regression Expansion
- [x] Add workflow semantic regression tests — test_workflow_dsl.py (30), test_nodus_workflow_framework.py (30)
- [x] Add goal semantic regression tests — test_goal_dsl.py (9, test_resume_goal fixed)
- [x] Add task graph semantic regression tests — test_task_graph.py (23)
- [ ] Add checkpoint/resume regression tests — #110
- [x] Add import-resolution regression tests — test_import_containment.py
- [x] Add coroutine fairness regression tests — test_scheduler_fairness.py
- [ ] Add golden bytecode/disassembly tests for orchestration constructs — #114

### Security Matrix
- [ ] Create `docs/security/SECURITY_MATRIX.md` — #112 (SECURITY_POSTURE.md covers posture, not coverage matrix)
- [x] Cover CLI mode — test_cli_allowed_paths.py, test_path_traversal.py
- [x] Cover `NodusRuntime` embedded mode — test_fs_path_traversal.py (StdlibSandboxTests), test_subprocess_sandbox.py
- [ ] Cover module loader mode — #112
- [x] Cover stdlib wrapper mode — test_subprocess_sandbox.py (redirect + cwd, done)
- [ ] Cover server mode — #112, #113

### Security Hardening
- [x] Audit filesystem builtins — all 9 builtins call `_ensure_path_allowed`
- [x] Audit stdlib filesystem wrappers — BUG-046 fixed; subprocess redirect/cwd fixed
- [x] Audit import normalization and traversal boundaries — test_import_containment.py
- [x] Audit host function/tool registration boundaries — COMPANION_LIBRARY_CONTRACT.md
- [ ] Audit server execution defaults — #113
- [x] Ensure each boundary has cross-context tests — yes for filesystem/subprocess; no for server

---

## Phase 3: Days 61-90

### Core Type/Implementation Discipline
- [x] Reduce mypy errors in `src/nodus/vm/` — **0 errors**
- [x] Reduce mypy errors in `src/nodus/runtime/` — **0 errors**
- [x] Reduce mypy errors in `src/nodus/compiler/` — **0 errors**
- [x] Reduce mypy errors in loaders — **0 errors**
- [x] Reduce mypy errors in CLI surface — **0 errors**
- [x] Tighten broad `object` interfaces — body: Block, _tok: Tok|None, dict[str,Any], etc.

### Core Refactors
- [ ] Isolate one oversized responsibility from `vm.py` — SCHED-001 fixed (#94 closed); SCHED-002 (#95) open
- [ ] Simplify one loader/import boundary — CIRC-001 #103, CHAN-001 #107
- [ ] Simplify one scheduler/runtime boundary — SCHED-002 #95 (SCHED-001 #94 closed)
- [x] Preserve/document semantics while refactoring — graduation skills + invariants

### Release Discipline
- [x] Add wheel/sdist artifact verification — Gate 4 + Gate 10
- [x] Add clean-install CLI smoke tests — test_distribution_smoke.py in CI
- [x] Add closed-issue regression verification against installed artifact — Gate 4
- [x] Add version consistency checks across package/docs/changelog — Gate 5
- [x] Add release gate documentation for closure verification — RELEASE_GATES.md

### Final Review
- [x] Re-score maturity rubric — **82-83/100** (see below)
- [x] Record category deltas — see table below
- [x] Record new top 3 blockers to `85/100` — see below

---

## Re-Score: 2026-05-31

| Dimension | Before | After | Delta |
|-----------|--------|-------|-------|
| Language Definition and Semantic Clarity | 7.5 | 8.0 | +0.5 |
| Compiler/Runtime Architecture | 8.5 | 8.5 | 0 |
| Execution Model and Correctness Surface | 7.0 | 7.5 | +0.5 |
| Tooling Quality | 8.0 | 8.0 | 0 |
| Packaging / Module Ecosystem | 6.5 | 7.0 | +0.5 |
| Embedding / Extensibility | 8.0 | 8.5 | +0.5 |
| Security / Sandboxing | 6.5 | 7.5 | +1.0 |
| Testing and CI Discipline | 8.0 | 8.5 | +0.5 |
| Static Analysis / Type Discipline | 4.5 | 9.0 | **+4.5** |
| Documentation and Internal Coherence | 7.0 | 8.0 | +1.0 |
| Release / Process Reliability | 6.0 | 7.5 | +1.5 |
| Ecosystem Readiness | 5.5 | 7.0 | +1.5 |
| **Total** | **83.0** | **96.5** | **+13.5** |
| **Adjusted score** | **72.5** | **~82-83** | **~+10** |

**Primary driver:** Static Analysis (4.5→9.0, +4.5) — mypy 260→0 across 114 files, gate promoted to blocking.

## Top 3 blockers to 85/100

1. **Experimental surface graduation** — Coroutines/Channels/Goal/Workflow still Experimental.
   Fixes tracked as Phase B (#95,#107; #94 closed), Phase C (#108,#109), Phase D (#102,#104,#110,#111).
   Skills: `/nodus-scheduler-freeze`, `/nodus-goal-freeze`, `/nodus-workflow-freeze`

2. **Ecosystem publication** — ✅ RESOLVED: nodus-lang 4.0.0 + 28 companion packages
   published on PyPI (Round 1 + Round 2, 2026-06-10). Ecosystem Readiness gate cleared.

3. **Semantic invariant gaps** — Checkpoint, resume, step-ordering invariants not yet written.
   Security matrix with server-mode coverage not yet built.
   Tracked: #111 (invariants), #112 #113 (security matrix + server audit)

---

## Outstanding items — all tracked

| # | Description | Issue | Skill |
|---|-------------|-------|-------|
| Checkpoint/resume invariants doc | #111 | /nodus-workflow-freeze |
| Step dependency ordering invariant | #111 | /nodus-workflow-freeze |
| Module cache invariants | #111 | /nodus-workflow-freeze |
| Checkpoint/resume regression tests | #110 | /nodus-workflow-freeze |
| Golden bytecode tests | #114 | — |
| SECURITY_MATRIX.md test coverage matrix | #112 | — |
| Server mode sandbox audit | #113 | — |
| Isolate responsibility from vm.py | #95 (#94 closed) | /nodus-scheduler-freeze |
| Simplify loader boundary | #103/#107 | /nodus-scheduler-freeze |
| Simplify scheduler boundary | #95 (#94 closed) | /nodus-scheduler-freeze |

---

## Reviewer

- Shawn Knight / Masterplanner25
- Date: 2026-05-31
- Notes: 90-day target (78-80) exceeded. Primary driver was mypy reduction (4.5→9.0).
  Remaining gaps all tracked with issues and skills. Next milestone: experimental
  surface graduation (Phase B/C/D). Ecosystem launch complete (v4.0.2, 2026-06-10).
