# Nodus Showcase Projects

Four projects built by the language's author using the Nodus ecosystem. They range
from a fully-running 430-line example to a production platform:

- exercises real Nodus language features end-to-end in a domain that makes sense outside of a tutorial
- tests the Claude/Codex skills that ship with the language against a live coding session
- serves as reference material and practice ground for a future Nodus coding agent

These are not toy scripts. Each project was started with nothing but the installed
Nodus ecosystem and the skill files, then pushed until something real was built or
a concrete design was produced. Bugs found during construction were filed as GitHub
issues and fixed in subsequent releases.

---

## Sentinel — Incident Triage & Digest Orchestrator

**Location:** `C:\dev\nodus-sentinel`
**Status:** Complete and runnable

~430 lines of Nodus, zero application Python. Built as an independent evaluation
of Nodus v4.0.2 by Claude Fable 5 (code name: the "Sentinel eval"). Bugs found
during construction drove the fixes in v4.0.3–4.0.6.

### What it does

Two-phase incident pipeline:

```
workflow triage:
  ingest → classify → { dedupe, stats } → enrich → finalize

goal publish_digest:
  assemble → { gate, notify, remediate } → publish → report
```

Alerts from `data/alerts.json` flow through classification (tool-based, coroutine
fan-out), deduplication (`std:hash` sha256 fingerprinting), geo-enrichment (`@retry`
recovers a deliberately flaky service), circuit-breaker-wrapped paging, a dynamic
remediation task graph built at runtime, and an `std:effects` exactly-once digest
write. Every event is audit-logged with `std:identity.execution_unit_id()`.

### Language features exercised

`workflow` + `goal`, parallel `step after` deps, channels + coroutine fan-out,
`@retry` with backoff, `@exactly_once`, `std:effects` exactly-once protocol,
`std:circuit_breaker`, `std:memory` cross-workflow namespace handoff, `std:identity`
audit trail, `std:hash` fingerprinting, dynamic `task()` / `run_graph()`, checkpoints,
synchronous in-step retry via `while + try/catch`. 12 unit tests using `std:test`.

### Run it

```powershell
pip install "nodus-lang[retry]" nodus-circuit-breaker
cd C:\dev\nodus-sentinel
nodus run --time-limit 30000 src/main.nd
nodus test .
```

### Key files

| File | Role |
|---|---|
| `src/main.nd` | workflow + goal, tool registration, entry point |
| `lib/tools.nd` | classify/geo/notify handlers, `@retry` wrapper |
| `lib/stream.nd` | channel producer/consumer fan-out |
| `lib/publish.nd` | `std:effects` publish + `@exactly_once` paging |
| `lib/remediate.nd` | runtime task graph, closure-factory workaround |
| `lib/audit.nd` | identity-stamped audit trail |
| `sentinel_test.nd` | std:test suite |
| `history/EVALUATION.md` | full language evaluation report (scored 1–10 per axis) |
| `history/BUGS.md` | 18-bug inventory with repros; most fixed in v4.0.3+ |

---

## claudecodenodus — Autonomous Research Agent

**Location:** `C:\dev\claudecodenodus`
**Status:** Design complete · Implementation not started

Designed by Claude Sonnet during an independent evaluation session where the full
Nodus ecosystem was installed and the skills were the primary reference. Design
docs live at `docs/plan.md`.

### What it will do

An agent that takes a research question, fans out across web/code/data sources in
parallel, synthesizes findings with an LLM, and gates every write action on human
approval before publishing.

```
workflow research_task:
  init → { gather_web, gather_code, gather_data } → analyze → produce_draft → publish

  produce_draft delegates to:

goal draft_approval_goal:
  draft → review (yield → human approval) → loop back if rejected → exit when approved
```

The LLM reasons within individual steps but does not control the workflow shape.
The DAG is fixed and auditable at definition time.

### Architecture

Three layers: **LLM driver** (via `nodus-llm`) → **Nodus orchestration** (fixed
workflow DAG, `@exactly_once` per fetch, approval gate) → **extension tools**
(Docker-sandboxed `research.web_search`, `research.fetch_doc`, `research.run_code`,
`research.write_file`, `research.notify`).

The approval gate is wired to `effects` declarations — any tool declaring
`fs.write` or `network.write` automatically requires human approval. No allowlist
to maintain.

### Memory schema

All memory nodes are path-addressed within a session, with tags for cross-session
recall:

```
research/{session_id}/sources/{content_hash}   ← content_hash = @exactly_once action_id
research/{session_id}/analysis/{content_hash}
research/{session_id}/revisions/{n}/draft
research/{session_id}/final
```

### Open questions before implementation

1. **`yield` return value** — does `yield` inside a goal step return the
   `resume_workflow()` payload as its expression value? The draft-review feedback
   loop depends on this. Needs a targeted runtime test.
2. **Goal loop termination** — exact mechanism for a goal to exit when its success
   condition is met. Not confirmed from source reading alone.

### Next steps

1. Answer the two open questions with targeted `.nd` tests against the live runtime.
2. Add `require_for_effects()` to `nodus-approvals` (straightforward extension of
   `require_for()`).
3. Implement: `src/runtime.py` → `extensions/` (manifests + handlers) →
   `workflows/research_task.nd` → `tests/research_task.test.nd`.

---

## codexnodus — Workflow-Native Agent Service

**Location:** `C:\dev\codexnodus`
**Status:** High-level plan complete · No concrete workflow spec yet

Designed by OpenAI Codex during an independent planning session with the Nodus
ecosystem installed and the Codex skill as the primary reference. Design docs live
at `docs/workflow-native-agent-service-plan.md`.

### What it will do

A production-ready agent service where Nodus is the durable execution layer. Any
long-running task that needs retries, approval gates, memory, resumability, and
an inspectable run history submits here.

V1 scope is intentionally narrow: one service, one workflow family, one complete
run through the full lifecycle.

### Canonical run lifecycle

```
received → planned → executing → waiting_for_approval → resuming → completed
                                                       ↓
                                               failed_retryable → retry
                                               failed_terminal
                                               cancelled
```

### Responsibility split

**Nodus owns:** workflow definition, step sequencing, wait/checkpoint behavior,
resume continuation, retry behavior inside a run, tool call orchestration,
memory access from workflow code.

**Host service owns:** HTTP/API surface, auth and tenancy, persistent storage,
approval persistence and identity, worker lifecycle, monitoring/export, policy
enforcement around sensitive tools.

### V1 workflow shape

```
intake → classify/route → recall memory → execute tool steps →
request approval if needed → wait → resume on decision →
finalize result → persist outcome and memory
```

### Core contracts defined

- **Tool contract** — every tool declares `name`, `timeout_ms`, `retry_class`,
  `side_effect_class` (`read_only` / `reversible_write` / `irreversible_write` /
  `external_communication` / `privileged_system`), `approval_policy`,
  `idempotency_expectation`.
- **Memory scopes** — `run`, `agent`, `subject`, `tenant`. All reads/writes
  visible in run history.
- **Approval contract** — every request includes plain-language summary, exact
  action, reason, deadline, and consequences of reject.
- **Retry classes** — only idempotent or explicitly retry-safe steps auto-retry;
  approval waits never auto-retry; irreversible effects need stronger replay
  protection.

### Control plane API (designed, not implemented)

`POST /tasks` · `GET /runs/{run_id}` · `GET /runs` · `GET /runs/{run_id}/events` ·
`POST /runs/{run_id}/approve` · `POST /runs/{run_id}/reject` · `POST /runs/{run_id}/resume`

### Next steps

1. Pick the first concrete use case (candidate: change-request preparation with
   approval before execution — a natural fit for the run lifecycle).
2. Write the workflow spec: step graph, step inputs/outputs, tool calls, approval
   trigger points, memory reads/writes, failure and retry behavior.
3. Draft the full API contract around that specific workflow.

---

## Infinity Claw — Self-Hosted Multi-Channel AI Workspace

**Location:** `C:\dev\claw`
**Status:** Active development · Python implementation substantial · Nodus workflows stubbed, expanding

The largest of the four projects and the broadest in scope. Infinity Claw is the
**first company application built on infrastructure that Masterplan Infinite Weave
itself created** — making it the first application to fully exercise the underlying
substrate of the Infinity Algorithm. It does this by running on Nodus (the language
ecosystem built in-house) and AINDY (the execution kernel built in-house) at the
same time. The name is deliberate: Infinity Claw is the Infinity Algorithm expressed
as a working application. The OpenClaw rewrite was designed around Nodus first, then
wired into AINDY.

### What it is

A production-grade, self-hosted personal AI assistant platform:

- **Multi-channel** — WebChat, Telegram, Discord, Slack, Matrix, Signal, each as
  a separate `nodus_adapter_base.Adapter` package (`claw_telegram`, `claw_discord`, etc.)
- **Persistent memory** — SQLite-backed hybrid BM25+vector search; daily Markdown
  memory logs; `std:memory` KV for runtime state
- **Multi-agent** — multiple named agents against a single workspace, each with
  their own session, credential store, and skill set
- **Self-hosted** — single `claw start` from a `claw.toml` + API key; no cloud dependency

### Where Nodus fits

Nodus is the workflow and infrastructure layer. The Python `claw/` package is a
thin orchestration shell; almost every subsystem delegates to a Nodus package:

| OpenClaw concept | Nodus replacement in Claw |
|---|---|
| TypeScript event handlers | `.nd` workflows (`boot.nd`, `session_reset.nd`, `heartbeat.nd`, `bootstrap.nd`) |
| Custom retry / failover | `nodus_retry`, `nodus_circuit_breaker`, `nodus_llm.FailoverClient` |
| Custom queue/lane system | `nodus_queue` (session, main, cron, subagent lanes) |
| mcporter MCP bridge | `nodus_mcp` — first-class, bidirectional; every `std:tool` registration auto-exposed |
| Custom observability | `nodus_observability_framework` (OTel, Prometheus, health endpoints) |
| Idempotency keys | `std:effects` EXACTLY_ONCE (`@exactly_once` on sends and agent methods) |
| Execution trace correlation | `std:identity` (`trace_id`, `session_id`, `execution_unit_id`) |
| Agent-to-agent delegation | `nodus_a2a` (opt-in) |
| Approvals + risk policy | `nodus_approvals`, `nodus_governance` |

The Nodus `.nd` workflows replace TypeScript `setTimeout` / cron handlers. Recurring
platform logic — memory flush before compaction, daily session reset, startup checklist,
heartbeat turn — is expressed as named workflow steps with `@exactly_once` idempotency,
not imperative event handlers.

### System diagram (abbreviated)

```
[Telegram] [Discord] [Slack] [Signal] [Matrix] [WebChat]
      │          nodus_adapter_base.Adapter
      ▼
[Claw Gateway — FastAPI + WebSocket]
      │
      ▼
[Agent Runtime — nodus_agent.AgentExecutor]
  nodus_llm.FailoverClient  |  nodus_queue (lanes)  |  nodus_events
      │
      ▼
[Tool Layer — std:tool (MCP-compatible registry)]
  std:fs, std:http, std:subprocess, memory_search, sessions_*, cron
  └── nodus_mcp.server (exposes all tools over MCP to Claude Code, etc.)
      │
      ▼
[Infrastructure — full Nodus package stack]
  Sessions: nodus_session + nodus_state + nodus_store_sql
  Memory:   nodus_memory (embeddings) + std:memory (KV)
  Auth:     nodus_auth + nodus_llm.CredentialStore
  A2A:      nodus_a2a  |  Approvals: nodus_approvals
  Obs:      nodus_observability_framework (OTel, Prometheus)
```

### AINDY integration

AINDY (runtime v1.4.0) is the execution kernel underneath Claw. Claw is the
first Masterplan Infinite Weave application: Nodus handles workflow orchestration,
AINDY handles turn lifecycle events, syscall dispatch, MAS memory, and the Redis
event bus. The two are connected at the platform boundary — Claw calls into AINDY
for lifecycle events and memory; AINDY knows nothing about Claw's channel adapters
or skill files.

### Implementation status

- `claw/` Python package — gateway, agents, sessions, memory, channels, routing,
  skills, cron, workspace, tools, auth, weave modules all implemented
- Channel adapters — `claw_discord`, `claw_telegram`, `claw_slack`, `claw_signal`,
  `claw_matrix`, `claw_webchat` all scaffolded
- Test suite — 14 phase test files (`test_aindy_phase2.py` through `test_aindy_phase14.py`)
- Nodus workflows — `boot.nd`, `session_reset.nd`, `heartbeat.nd`, `bootstrap.nd`
  exist; currently stubs being expanded as each phase completes
- `claw start` — gateway starts; WebChat reachable at `http://127.0.0.1:18789/`

### Key files

| File | Contents |
|---|---|
| `PROJECT_BRIEF.md` | Vision, problem statement, success criteria |
| `OPENCLAW_NODUS_ARCHITECTURE.md` | Full system diagram, package responsibilities, boundary contracts |
| `OPENCLAW_TO_NODUS_ANALYSIS.md` | Migration analysis: what moves to Nodus vs. stays Python |
| `CLAW_AINDY_INTEGRATION_PLAN.md` | AINDY integration points and phase plan |
| `workflows/*.nd` | Nodus workflow files for recurring platform logic |
| `claw/` | Core Python orchestration package |
| `claw_*/` | Per-channel adapter packages |
| `tests/` | Phase test suite (phases 2–14) |

---

## Relationship to the Nodus coding agent

These four projects are the early sketch of what a **Nodus-specific AI coding
agent** would need to handle autonomously: read the skill files, understand the
language quirks, plan an implementation, write correct `.nd` code on the first
pass, debug using `nodus check` / `nodus ast`, and produce a runnable project
without external help.

**Sentinel** is the benchmark — built by an LLM from scratch, it runs end-to-end
and exercises the full AI-native surface. **claudecodenodus** and **codexnodus**
push further into multi-agent and durable-service territory. **Infinity Claw** is the production target: the first company application to run
on the infrastructure Masterplan Infinite Weave built itself, exercising the Infinity
Algorithm through Nodus + AINDY in a real deployed system. A future Nodus coding
agent will be evaluated against tasks drawn from all four.
