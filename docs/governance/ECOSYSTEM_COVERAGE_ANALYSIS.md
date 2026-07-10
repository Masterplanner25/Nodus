# Strict Nodus Ecosystem Coverage Analysis — Nodus (core + `nodus-*` companions) vs. 12 Reference Systems

**Date:** 2026-06-24 (verified against `nodus-lang` v4.0.7; re-confirmed accurate at v4.0.8).
**Sources:** internal source-code architectural audits of 12 reference AI agent/workflow systems for the concern taxonomy; coverage re-verified at file level against the Nodus core (`nodus-lang`) and the `nodus-*` companion packages.
**Purpose:** Answer one question honestly — *of the capability surface the 12 systems collectively demonstrate, how much does **Nodus itself** cover today?*

> **Note (v4.0.8):** one capability has improved since this snapshot — idiomatic
> async fan-out (`http.get_async` / `subprocess.run_async` under `fan_out`/`parallel`)
> now genuinely overlaps rather than silently serializing (ASYNC-MOD-001, #105/#290).
> Agent-call fan-out now overlaps too, via the `agent_call_async` / `agent.call_async`
> builtin added for #294 (ASYNC-MOD-002).

> **This document deliberately supersedes `Ecosystem_Coverage_Analysis.md` for the Nodus-only question.** That earlier doc rated **"AINDY Runtime + Nodus" as one stack** and assigned most of the strong coverage (syscall dispatch, WAIT/RESUME, multi-tenancy, pgvector memory, hosting, leader election, dead-letter) to **`aindy-runtime`**. This one strips every aindy-owned capability and re-scores strictly.

---

## 0. The strict boundary (read this first)

`aindy-runtime` is the **governed execution substrate that embeds Nodus**; Nodus is the execution substrate underneath. They are **two separate systems**, not one stack. The prior analysis conflated them and credited "the stack" with capabilities that live only in `C:\dev\aindy-runtime`.

**What counts as Nodus here:**

| Layer | What | Repos |
|---|---|---|
| **core** | The language, bytecode VM, workflow/goal DSL, coroutine/channel scheduler, stdlib (`std:*`), sandbox, `NodusRuntime` embedding API | `C:\dev\Coding Language` (`src/nodus/`) |
| **in-tree companion** | Framework modules shipped inside `nodus-lang` | `src/nodus_lang_workflow/`, `src/nodus_lang_schema/` |
| **companion** | The published `nodus-*` ecosystem packages | `C:\dev\nodus-*` (workflow, store-sql, memory, mcp, a2a, llm, observability, extension, auth, retry, circuit-breaker, queue, approvals, context, …) |

**What does NOT count:** anything in `C:\dev\aindy-runtime`. If a capability exists only there, **Nodus does not have it.**

### The single most important honest caveat

The companions are **~25 independently-versioned v0.1.0 pip packages, not an integrated runtime.** There is no single import that wires them together; a host application must compose them by hand (or via the thin `nodus-sdk` bridges). Almost everything real is **in-memory / single-process** and gated behind optional extras + external SDKs/keys. So "Nodus covers X" usually means *"a Nodus package provides a primitive for X that you must install and wire yourself,"* not *"the runtime guarantees X."* The integration layer that would turn these into a coordinated stack is precisely what `aindy-runtime` was — and it is excluded.

### Rating legend

| Rating | Meaning |
|---|---|
| ✅ **Full** | Implemented and reasonably complete *as a primitive* in Nodus today |
| 🟡 **Partial** | Exists but thin, in-memory-only, experimental, requires host wiring/keys, or covers only part of the concern |
| 🔴 **None** | Not implemented in Nodus core or any `nodus-*` companion |
| ⚪ **Hosted** | An application-layer concern Nodus is designed to *host*, not provide (correctly absent) |

---

## 1. Master strict coverage matrix

Layer column: **C** = core, **iC** = in-tree companion, **P** = `nodus-*` companion package, **—** = none.

### Tier 1 — Substrate / runtime capabilities

| # | Capability | Strict rating | Layer | Exemplar systems | Strict evidence note |
|---|---|---|---|---|---|
| 1 | Syscall / capability-gated dispatch | 🟡 | iC + P | (no peer; closest = SWE-agent liveness guard) | `services/syscall_runtime.py` dispatches versioned `sys.v1.*` syscalls and **schema-validates**, but the `SyscallSpec.capability` field is **declarative metadata, never enforced** (only 4 syscalls registered). `nodus-extension` `CapabilityGate.require()` *does* enforce, but host-side only. **Strictly: schema-gated dispatch, not capability-gated.** |
| 2 | Tool registry + dispatch | ✅ | C | MS-AF, ADK, CrewAI, SWE-agent | `builtins/tool_module.py` + `std:tool`: dotted-namespace enforcement, arg/return schema validation, effect declarations, sub-runtime invocation carrying parent sandbox limits. Genuinely complete (in-process only). |
| 3 | DAG / flow orchestration engine | ✅ | C | LangGraph, MS-AF `_workflows`, ADK | `orchestration/task_graph.py` (`TaskGraph`, topological dispatch, per-task retry/cache/timeout); workflow DSL lowers via `workflow_lowering.py`. `after`/`step`/`checkpoint` are language syntax. Single-process cooperative; "workers" are labels. |
| 4 | WAIT/RESUME + HITL / approval gates | 🟡 | C + P | Temporal signals, ADK, OpenHands, MS-AF | Core `workflow_wait`/`resume_workflow` is a generic event-wait primitive. `nodus-approvals` adds a **real** verdict model (approver_id, reason, expiry, fail-closed default). **But:** in-memory store only (no crash-durability), and `ApprovalGate.approve()` does **not** verify the approver against the rule's allow-list. Strong primitives, not a durable HITL service. |
| 5 | Scheduling / cron / timers | 🟡 | C + P | Temporal | `runtime/scheduler.py` heap timer queue + cooperative `sleep`; `nodus-queue` delayed jobs (Redis sorted-set); workflow runner `next_attempt_at` due-polling. **No cron / recurring / scheduled-at-wall-clock** anywhere. One-shot delays + due-polling only. |
| 6 | Idempotency / exactly-once effects | 🟡 | C | Temporal (outbox) | `std:effects` ships a deterministic `compute_action_id` (sha256) **with a built-in fallback** (works without external pkg). **But** the backing store is `InMemoryEffectStore` by default — exactly-once holds only within a process/store lifetime; no durable store shipped, and execution isn't re-driven from it. A contract surface, not an enforced durable guarantee. |
| 7 | Retries / circuit breakers / backoff | ✅ | P | SWE-agent, Aider, MetaGPT | `nodus-retry` (exponential + jitter + cap, named policies) and `nodus-circuit-breaker` (full 3-state CLOSED/OPEN/HALF_OPEN, thread-safe). **Caveat:** core `std:retry`/`std:circuit_breaker` are thin shims that **raise ImportError without these packages** (no fallback). All breaker/retry state is in-process memory (no shared/distributed state). |
| 8 | Dead-letter / orphan recovery / rehydration | 🟡 | iC + P | Temporal | `nodus_lang_workflow` dead-letter status + `rehydrate_run`/`revive_dead_lettered_run`; `nodus-queue` DLQ + `requeue_stale_jobs` (visibility timeout); `nodus-a2a` `StuckRunWatchdog`. **Durable only on Redis or a host-supplied persistent store**; the standalone `nodus-workflow` ships only `InMemoryRunStore`, so its rehydration is vacuous without host wiring. |
| 9 | **Durable execution (event-sourced crash continuation)** | 🟡 | C + iC | **Temporal** (gold), LangGraph (state), Open Interpreter | **Verified across all repos: NO event-sourcing anywhere.** `task_graph.py:_persist_graph_state` overwrites a full JSON **snapshot** each sweep (atomic `os.replace`+fsync); `nodus_lang_workflow` resumes from the last snapshot/checkpoint, not a replayed event log. `nodus-store-sql` has an append-only `EventStore` but **nothing consumes it for replay**. Crash recovery = last-snapshot granularity; in-flight work since last save is lost. This is the headline structural gap, same as in the aindy-era doc. |
| 10 | Workflow-as-data (serializable graph) | 🟡 | C + iC | Temporal (CHASM), MS-AF, ADK | `task_graph.py` serializes full graph *state* to deterministic JSON, but task functions reference in-process VM closures (`_GRAPH_VMS`) — resume needs the original source/VM. Companions serialize *run-state*, not graph topology. So "run-state-as-data," not portable graph-of-code. |
| 11 | Single-writer fencing / leader election | 🟡 | iC + P | Temporal (RangeID) | Per-record fencing exists: `nodus_lang_workflow` TTL claim tokens (`claim_run` → `claim_<uuid>`, `BEGIN IMMEDIATE`), `nodus-store-sql` optimistic `version` column + atomic CAS job-claim, Redis BRPOP single-consumer. **No leader election anywhere** (verified: zero `leader`/`election`/`redlock`/`FOR UPDATE`). Adequate for single-node, not distributed fencing. |
| 12 | Durable queue / worker / dispatch | 🟡 | P | Temporal (matching) | `nodus-queue` Redis backend is genuinely durable (LPUSH/BRPOP, in-flight hash, delayed set, DLQ, visibility-timeout recovery). **But** default/no-`REDIS_URL` path falls back to `InMemoryQueueBackend` (lost on restart); **requires a live Redis** for real durability (redis tests skipped in dev). `nodus-store-sql` JobStore is durable but has no worker loop — claim primitives only. |
| 13 | Multi-tenancy / isolation | 🟡 | C | (most peers single-tenant) | `runtime/sessions.py` `SessionManager` + independent `NodusRuntime` instances give **session/instance isolation only**. **No tenant identity, no per-tenant quota / data partitioning / RBAC.** *(Downgrade from the aindy-era ✅: `TenantContext` + 27 tenant tables were aindy's, not Nodus's.)* |
| 14 | Identity / trace propagation | ✅ | C + P | ADK, MS-AF, OpenHands | Core `std:identity` propagates `trace_id` to child VMs and stamps every emitted event; `nodus-observability` adds ContextVar trace-id + OTLP export; `nodus-sdk` `NodusTraceMiddleware` reads `X-Trace-ID`. Solid. (No W3C span hierarchy in core; that comes from the OTel companion.) |

### Tier 2 — Memory & state

| # | Capability | Strict rating | Layer | Exemplar systems | Strict evidence note |
|---|---|---|---|---|---|
| 15 | Long-term / vector / semantic memory (RAG) | 🟡 | P | CrewAI (LanceDB), ADK (Vertex RAG), LangGraph | `nodus-memory` has **real cosine similarity** (`scoring.py:_cosine_similarity`) and `nodus-native-memory-engine` has Rust-accelerated ranking — **but brute-force linear scan over an in-process dict, no vector index/ANN, no pgvector** in the installed Tier-2 layout. **No bundled embedder:** out of the box you get zero-vectors (semantic score → 0); real embeddings need an OpenAI key + optional dep. "RAG-shaped scoring," not a turnkey RAG store. *(Downgrade: aindy's pgvector `Vector(1536)` is excluded.)* |
| 16 | Short-term memory / context compaction | 🟡 | P | MS-AF, ADK, Open Interpreter, Aider, OpenHands | `nodus-context` has working compaction primitives (`DropToolInternalsStrategy`, budget-aware `ContextWindow.compact()`). **But** actual summarization requires a caller-supplied `summary_fn` (none bundled — emits a placeholder otherwise); token counting is a chars//4 heuristic unless `tiktoken` is installed. In-memory only. |
| 17 | Persistence substrate / single state authority | 🟡 | P + iC | Temporal, LangGraph | `nodus-store-sql` is a real SQLAlchemy substrate (`nodus_runs`/`nodus_events`/`nodus_jobs`, sync+async); `nodus_lang_workflow` has WAL SQLite + atomic file store. **But there is no single state authority** — every package owns its own store independently; they share no schema or DB. `create_all()` is dev-only bootstrap; production migrations unmanaged. *(Downgrade: aindy's Postgres system-of-record is excluded.)* |
| 18 | Process-local KV / namespaced memory | ✅ | C | (CrewAI scope-paths) | Core `std:memory`: `get/put/delete/keys/has` + namespaced `recall_from`/`recall_all`/`share`/`tag`. Complete as a primitive; in-process only, no TTL/persistence. |

### Tier 3 — Multi-agent & interop

| # | Capability | Strict rating | Layer | Exemplar systems | Strict evidence note |
|---|---|---|---|---|---|
| 19 | Multi-agent coordination / delegation | 🟡 | C + P | Open Interpreter, CrewAI, MetaGPT | Core in-process agent registry (`register_agent`/`call_agent`); `nodus-a2a` `AgentCoordinator` adds capability-match selection, load-balancing, dead-letter, watchdog. **But decision/selection + bookkeeping only — it does not transport the delegation anywhere** (no send/dispatch; caller executes). All in-memory. |
| 20 | A2A — cross-process agent-to-agent protocol | 🟡 | P | CrewAI (a2a-sdk), ADK, Google A2A | A real A2A **wire protocol** (agent cards, codec, transport, auth validators, 180 tests) exists as the `nodus-a2a` companion — **but only in the GitHub `src/` layout; the locally-installed Tier-2 package contains coordination primitives only, no wire transport.** Strictly: the capability *exists as a Nodus companion* but is currently bifurcated and un-integrated. |
| 21 | MCP interoperability (client + server) | ✅ | P | MS-AF, ADK, CrewAI, Open Interpreter, OpenHands | **`nodus-mcp` implements both client and server** (Phase A–N: tools/resources/prompts, elicitation/sampling, stdio + HTTP transports), and **`nodus-mcp-server` v0.1.11 is published and interops with real Claude Desktop / ChatGPT Desktop via the official MCP SDK.** **Caveat:** `nodus-mcp`'s own HTTP transport is a custom single-POST JSON-RPC ("MCP-shaped," `server/discover` rather than the spec `initialize` handshake), not official Streamable-HTTP/SSE — production interop rides on `nodus-mcp-server`. ***Notably this is an UPGRADE vs the aindy-era doc, which rated MCP a 🔴 gap.*** |

### Tier 4 — Safety, isolation & governance

| # | Capability | Strict rating | Layer | Exemplar systems | Strict evidence note |
|---|---|---|---|---|---|
| 22 | Capability / permission gating | 🟡 | C + P | (SWE-agent liveness guard) | Enforced surfaces: core sandbox allow-lists (`allowed_hosts`/`allowed_commands`/`allowed_paths`) and `nodus-extension` `CapabilityGate`. **But** these are coarse boolean/allow-list toggles, not a capability model; the named syscall `capability` is unenforced (#1); `nodus-auth` scopes are bypassed for JWT principals. |
| 23 | Sandboxing / execution isolation | 🟡 | C + P | **Open Interpreter**, **OpenHands**, SWE-agent | Core has a working **in-process soft sandbox** (`allowed_paths`, network/subprocess/env gates, step/time/depth limits); `nodus-extension` runs plugins in a **subprocess "insecure-dev" tier only** (plain `Popen`, no seccomp/OCI/namespace/rlimit). **No OS/VM-level isolation; default execution is trusted in-process.** This remains Nodus's weakest category vs the execution-plane peers. |
| 24 | Secrets / egress governance | 🔴 | — | OpenHands (JWE/JWS broker) | **None.** `std:secrets` is only RNG/token generation (misnamed). No vault, no redaction, no egress allow-list-as-policy, no secret broker anywhere. API keys are held in plaintext on `CredentialProfile`. The one genuine substrate-level *gap* (not merely thin). |
| 25 | Cost / budget governance | 🟡 | P | MetaGPT (`CostManager`), SWE-agent, CrewAI | `nodus-observability-framework/cost.py` is a **passive ledger** (`TokenUsage`/`CostTracker`) — token counts and `cost_usd` are **caller-supplied** (no tokenizer, no pricing table). **No budget enforcement / spend cap / throttle anywhere.** Accounting only. |

### Tier 5 — Models, providers, streaming, language

| # | Capability | Strict rating | Layer | Exemplar systems | Strict evidence note |
|---|---|---|---|---|---|
| 26 | Provider / model abstraction | 🟡 | P | CrewAI, MS-AF (~20), ADK (100+ LiteLlm) | `nodus-llm` has **three concrete real-API providers: OpenAI, Anthropic, OpenAI-compat** (OpenRouter/LM Studio/vLLM via `base_url`) + credential-failover. **No Gemini provider; no native local (llama.cpp/Ollama)**; no model registry; selection is manual via a caller factory. ***Broader than the aindy-era doc's "OpenAI+DeepSeek only" — Anthropic is a real upgrade*** — but narrow vs the multi-SDK peers. |
| 27 | Streaming output | 🟡 | C + P | MS-AF, ADK, CrewAI | **`nodus-llm` has zero LLM token streaming** (`chat()` returns a `str`). Core HTTP client can *consume* SSE/chunk streams; `nodus-observability-framework` `BlockStream` is an in-process execution-event broadcast for SSE endpoints. No first-class streamed-token abstraction. |
| 28 | Embedded scripting language / DSL | ✅ | C | **(unique — no peer has one)** | The core competency: real bytecode-compiled language, stack VM (BYTECODE_VERSION 4), closures, records-vs-maps, first-class `workflow`/`goal`/`step`/`spawn`/task-graph syntax + cooperative scheduler + `NodusRuntime` embedding API (+ LSP/DAP). **No system in the reference set has a purpose-built orchestration *language*.** |

### Tier 6 — Observability & ops

| # | Capability | Strict rating | Layer | Exemplar systems | Strict evidence note |
|---|---|---|---|---|---|
| 29 | Tracing / metrics / event bus | ✅ | P + C | ADK, MS-AF (OTel GenAI) | `nodus-observability` does **real OTel export** (`TracerProvider` + `BatchSpanProcessor` + OTLP gRPC exporter) and **real Prometheus** (`CollectorRegistry`, concrete Counters/Histograms/Gauges); core has an in-process `RuntimeEventBus`. Genuine export, not just logging — though OTel/Prometheus are optional extras (no-op without them). |
| 30 | Hosting / REST API / auth | 🟡 | C + P | OpenHands, MS-AF hosting | Real REST surface (core `nodus serve` + FastAPI `api.py`; `nodus-sdk` `create_nodus_router`: `/run`, `/health`, `/syscalls`, memory CRUD). `nodus-auth` has real JWT/bcrypt/API-key-scopes. **But the SDK router has NO auth wired** (`/run` executes arbitrary source unauthenticated); no OAuth; **JWT principals bypass scope checks** (`has_scope()` returns True unconditionally). Pieces exist; not assembled into a secured host. *(Downgrade: aindy's 38-route authed platform is excluded.)* |
| 31 | Deployment topology / packaging | 🟡 | C + P | OpenHands, ADK (Cloud Run) | PyPI packaging + `nodus-sdk` extras auto-wiring + `nodus-run-action` for CI. **No container/IaC/compose shipped as a product.** A packaging/wiring story, not a deploy platform. |
| 32 | Plugin / extension architecture | ✅ | P + C | MS-AF, CrewAI | `nodus-extension` is a complete typed plugin framework (Pydantic manifest, capability declarations, host load→gate→invoke, provenance, `_ext_*` host fns) + core import/entry-point substrate (`[project.entry-points."nodus.nd"]`). Architecture is solid; **isolation is the weak axis** (subprocess tier-1 only, #23). |

### Tier 7 — Application-layer capabilities (Nodus HOSTS these; correctly does not provide them)

| # | Capability | Strict rating | Layer | Exemplar systems | Strict note |
|---|---|---|---|---|---|
| 33 | Agent ReAct loop (model→act→observe) | ⚪🔴 | — | all agent systems | Core `agent_runtime` is a registry+dispatch, not a ReAct controller. A coding-agent harness supplies the loop *on top of* Nodus. |
| 34 | Planning (plan object / task list) | 🟡⚪ | C | MetaGPT, ADK, CrewAI, GPT-Engineer | `plan_graph`/`plan_goal` produce a **deterministic topological execution-schedule preview** — **not** LLM goal-decomposition. Real planning content is prompt/app-level. |
| 35 | Repo-map / code-context builder | 🔴⚪ | — | **Aider** (tree-sitter+PageRank), Open Interpreter | None. High-value coding-agent capability to host/absorb. |
| 36 | Edit-format application (SEARCH/REPLACE, diffs) | 🔴⚪ | — | Aider, GPT-Engineer, OpenHands | None. `nodus fmt` is a source formatter, not an agent edit-applier. App-level. |
| 37 | Git-as-spine (persistence + undo + artifact) | 🔴⚪ | — | Aider | None. App-level pattern; not a runtime concern. |
| 38 | Harness emulation ("harness is data") | 🔴⚪ | — | **Open Interpreter** (unique) | None. The most novel ecosystem idea; a natural fit at the Nodus language boundary to *absorb*. |
| 39 | Agent-Computer Interface / tool bundles | 🔴⚪ | — | **SWE-agent** (ACI), Open Interpreter | None as an abstraction. Core provides tool/subprocess/http *primitives*; the ACI is content Nodus would dispatch+sandbox. |
| 40 | Eval / reproducibility / replay harness | 🟡⚪ | C | SWE-agent, ADK | `std:test` is a full **unit-test** DSL + golden-bytecode determinism + workflow snapshot-replay — **not** an eval/judge/dataset/metric harness. |

---

## 2. Strict counts

| Rating | Count | Concerns |
|---|---|---|
| ✅ **Full** | **9** | 2 (tools), 3 (DAG), 7 (retry/CB), 14 (identity), 18 (KV), 21 (MCP), 28 (DSL), 29 (observability), 32 (plugins) |
| 🟡 **Partial** | **24** | 1, 4, 5, 6, 8, 9, 10, 11, 12, 13, 15, 16, 17, 19, 20, 22, 23, 25, 26, 27, 30, 31, 34, 40 |
| 🔴 **None** | **7** | 24 (secrets/egress), 33 (ReAct), 35 (repo-map), 36 (edit-format), 37 (git-spine), 38 (harness), 39 (ACI) |

**Of the 7 Nones, six (33, 35–39) are application-layer concerns Nodus is *designed to host, not provide* — their absence is correct.** Only **#24 (secrets/egress governance)** is a genuine substrate-level gap that scores zero.

So at the **substrate** level (Tiers 1–6, concerns 1–32), strict Nodus is: **9 Full · 22 Partial · 1 None.** Breadth is near-total; the story is entirely in the *depth* of those 22 Partials.

---

## 3. How the strict view differs from the aindy-era doc

Stripping aindy moves rows in **both** directions. This is the most important section.

### Rows that DROPPED (these were aindy's kernel, not Nodus's)

| # | Capability | Was (A+N) | Strict (Nodus) | Why |
|---|---|---|---|---|
| 1 | Syscall capability-gated dispatch | ✅ (A) | 🟡 | aindy's dispatcher *enforced* capability/tenant/quota; Nodus's syscall layer only schema-validates — capability field unenforced. |
| 4 | WAIT/RESUME + HITL | ✅ (A) | 🟡 | aindy was DB-backed + Redis cross-instance; Nodus is in-memory, not crash-durable. |
| 13 | Multi-tenancy / isolation | ✅ (A) | 🟡 | `TenantContext` + 27 tenant tables were aindy's. Nodus has session/instance isolation, no tenants. |
| 15 | Vector / RAG memory | ✅ (A) | 🟡 | aindy's pgvector `Vector(1536)` excluded; Nodus = brute-force cosine, no index, no bundled embedder. |
| 17 | Persistence / state authority | ✅ (A) | 🟡 | aindy's Postgres system-of-record excluded; Nodus = per-package stores, no single authority. |
| 30 | Hosting / REST / auth | ✅ (A) | 🟡 | aindy's 38-route authed platform excluded; Nodus has an *unauthenticated* SDK router + a separate, un-wired auth package. |
| 8, 19, 29 | Dead-letter, multi-agent, observability | ✅ (A) | 🟡 / ✅ | Recovered partly or fully by companions (`nodus-a2a`, `nodus-observability`) rather than aindy. |

### Rows that ROSE (companions get full credit; aindy had punted them)

| # | Capability | Was (A+N) | Strict (Nodus) | Why |
|---|---|---|---|---|
| 21 | **MCP interoperability** | 🔴 Gap | ✅ **Full** | The aindy-era doc rated MCP a gap ("not implemented in AINDY; nodus-mcp out-of-tree"). Strictly, `nodus-mcp` (client+server) **is** a Nodus companion and `nodus-mcp-server` is **published and interops with real MCP clients.** |
| 26 | Provider abstraction | 🟡 (OpenAI+DeepSeek) | 🟡 (OpenAI+**Anthropic**+compat) | `nodus-llm` adds a real Anthropic provider — broader than the aindy-tree set, though still narrow vs the multi-SDK peers. |
| 20 | A2A protocol | 🔴 | 🟡 | The A2A wire protocol exists as a Nodus companion (currently bifurcated local/remote), so it earns Partial rather than a flat gap. |

**The lesson:** aindy's strength was the **integrated, enforced kernel** (capability gating, tenancy, durable DB-backed waits, single state authority). That's exactly what drops out. Nodus's strength is **breadth of primitives + a unique language**, and on the *interop* axis (MCP, providers) the companion-credit lens actually makes Nodus look *better* than the conflated stack did.

---

## 4. Per-system strict coverage

For each reference system: how much of *its* distinctive surface does strict Nodus cover?

1. **Microsoft Agent Framework** — Covered: tool loop+registry, checkpoint/resume, OTel observability, plugin/extension, **MCP (both have it now)**. Partial: provider breadth (3 vs ~20), WAIT/RESUME (theirs durable via Durable Task), compaction, streaming. Gap: their transactional per-superstep BSP commit; multi-tenancy. **~55% of substrate.**
2. **Devika** — Covered: ~everything Devika lacks maps to a Nodus primitive (DAG, retry, effects, KV memory, dead-letter). Devika is a pure "before" picture. **~90%** — the cleanest win, because Devika has no durable/tenant/sandbox depth to expose Nodus's thin spots.
3. **Google ADK 2.0** — Covered: flow engine, generic retry, observability, **MCP**, eval-shaped test. Partial: provider breadth (their genai-types lingua franca), WAIT/RESUME. Gap: their **event-sourced state fold** (Nodus is snapshot, #9), Vertex RAG depth. **~55%.**
4. **GPT Engineer** — Covered/Hosted: a linear generator that "collapses into a single Nodus flow." Every framework concern is a primitive; the rest is app content Nodus hosts. **~90% of substrate; it's an app.**
5. **LangGraph** — Covered: DAG core + everything around it (retry, observability, identity). Gap: their **channel-state + reducer + pending-writes mid-superstep replay** is a materially stronger crash-consistency-of-state story than Nodus's snapshot model (#9). **~60% — Nodus surrounds it but their inner state-engine is more rigorous.**
6. **MetaGPT** — Covered: round-loop→scheduler, retries→retry/CB, tool registry→`std:tool`, Memory→`nodus-memory`. Gap: their first-class `CostManager`/`NoMoneyException` budget governor (Nodus has accounting only, #25). Absorb: `ActionNode` (schema→prompt→validated-parse). **~75%.**
7. **OpenHands** — Covered: control-plane shape (persistence, HITL/confirmation via `nodus-approvals`, event trajectory, observability). Gap (material): their **remote gVisor/sysbox sandboxed execution plane** — Nodus's weakest area (#23); their **MCP-as-egress-broker** secret pattern (#24 None). **~40%; sandbox + secrets/egress are the real misses.**
8. **Open Interpreter** — Covered: tool-as-capability-bus, resume/rehydration, lifecycle hooks, multi-agent. Gap (material): **multi-OS sandboxing** (Seatbelt/bubblewrap/Landlock; #23), **auto-compaction** (#16 needs caller LLM fn), and **harness-emulation** (#38, None) — which fits naturally at the Nodus language boundary. **~45%.**
9. **SWE-agent** — Covered: tool routing, retries, event-log+checkpoint, scheduler, test framework. Gap: **swe-rex sandbox extraction** (#23), **reproducibility/replay** (deterministic ReplayModel, #40 is unit-test+snapshot only). Hosted: the ACI (#39). **~50%.**
10. **Temporal** — Covered: durable suspend/resume around WAIT points, checkpointing, fencing-ish claim tokens, Redis durable queue+DLQ, idempotency surface — **plus the whole agent/tool/memory/language layer Temporal lacks.** Gap (headline): **event-sourced replay + transparent crash continuation** (#9, snapshot only), **leader election** (#11, None), **durable scheduling** (#5, no cron), **workflow-as-portable-data** (#10). **~45% of the durability substrate — Nodus's deepest structural debt, exactly as before.** |
11. **Aider** — Covered/Hosted: Aider declines all runtime concerns by design ("a REPL, not a runtime"). Gap (to absorb): the **repo-map** (tree-sitter+PageRank, #35 None) and **prompt-cache warming**. **Substrate N/A; absorb repo-map.**
12. **CrewAI** — Covered: multi-agent (delegation), tool loop, memory (their scope-paths ≈ `nodus-memory` MAS paths), HITL pause/resume, **MCP + A2A (both now Nodus companions, #20/#21)**. Partial: their **native multi-SDK LLM layer** with Anthropic prompt-cache survival is still ahead of `nodus-llm` (#26). **~70% — Nodus is the runtime layer CrewAI offloads to a closed cloud; absorb CrewAI's LLM layer.**

---

## 5. Honest gap register (strict, prioritized)

Ranked by how structural the gap is and how many peers have it. **Note:** the aindy-era doc's #1 gap ("AINDY↔Nodus integration unbuilt") is *moot* here — we're scoring Nodus alone — but it's replaced by an analogous Nodus-internal caveat (P0 below).

| Pri | Gap | Severity | Who has it | Why it matters for strict Nodus |
|---|---|---|---|---|
| **P0** | **Companions are un-integrated v0.1.0 packages, mostly in-memory/single-process** | Critical (structural) | (integrated runtimes: Temporal, aindy) | "Coverage" is a bag of primitives the host must install + wire. Durability, idempotency, approvals, memory all default to in-memory. There is no Nodus that *is* the coordinated stack — that was aindy. |
| **P0** | **Event-sourced durable execution / crash continuation** | Critical | Temporal, LangGraph (partial), Open Interpreter | Snapshot/checkpoint only; no replay log; in-flight work lost on crash (#9). The single deepest substrate debt. |
| **P1** | **Hostile-safe sandboxing (default-on OS isolation)** | High | OpenHands, Open Interpreter, SWE-agent | Default execution is trusted in-process; plugin tier is "insecure-dev" subprocess. Blocks untrusted workloads (#23). |
| **P1** | **Secrets / egress governance** | High | OpenHands (JWE/JWS broker) | The only substrate concern scoring a flat 🔴. No vault, redaction, or egress policy (#24). |
| **P1** | **Multi-tenancy (identity, quota, RBAC)** | High | (most peers single-tenant; this was aindy's edge) | Nodus has isolation, not tenancy (#13). Re-acquiring this is the main thing strict Nodus *lost* by excluding aindy. |
| **P2** | **Enforced capability model** | Medium | (SWE-agent partial) | Syscall capability is declarative/unenforced (#1); gating is coarse allow-lists; auth scopes bypassed for JWT (#22/#30). |
| **P2** | **Durable, crash-safe WAIT/RESUME + HITL** | Medium | Temporal, ADK, OpenHands | Approvals/waits are in-memory; don't survive restart (#4). |
| **P2** | **Real vector/RAG store + bundled embedder** | Medium | CrewAI, ADK, LangGraph | Brute-force cosine, no index, zero-vectors without an OpenAI key (#15). |
| **P2** | **Single state authority + durable scheduling** | Medium | Temporal, LangGraph | Per-package stores, no shared authority (#17); no cron/recurring schedule (#5). |
| **P3** | **Provider breadth + LLM token streaming** | Medium | CrewAI, MS-AF, ADK | 3 providers, no Gemini/native-local, no streamed tokens (#26/#27). |
| **P3** | **Cost/budget enforcement** | Low-Med | MetaGPT, SWE-agent, CrewAI | Accounting ledger exists; no spend cap/throttle (#25). |
| **P3** | **A2A wire-protocol consolidation** | Low-Med | CrewAI, ADK | The protocol exists but is bifurcated local/remote and un-integrated (#20). |
| **P4** | Repo-map / harness-emulation / ACI (app-level, to *absorb* at the language boundary) | Low (novel) | Aider, Open Interpreter, SWE-agent | #35/#38/#39 — high-value ideas, not runtime gaps. |

---

## 6. Coverage summary — is Nodus useful to the ecosystem, and how much does it cover?

**Where strict Nodus is genuinely strong:**
- **A purpose-built orchestration *language* (#28) that no peer in the set has** — the single most differentiated asset.
- **First-class tool registry + DAG/workflow + cooperative scheduler (#2/#3) in-process**, with a clean `NodusRuntime` embedding API.
- **A surprisingly complete interop + ops ring via companions: real MCP client/server (#21), genuine OTel/Prometheus export (#29), a typed plugin framework (#32), three real LLM providers incl. Anthropic (#26), retry/circuit-breaker (#7).** On interop specifically, the strict/companion lens makes Nodus look *better* than the aindy-conflated doc did.

**Where strict Nodus is genuinely behind (the reference implementations beat it):**
- **Durable execution / event-sourcing (Temporal, LangGraph)** — snapshot-only, no replay (#9).
- **Hostile-safe sandboxed execution planes (OpenHands, Open Interpreter, SWE-agent)** — trusted in-process default (#23).
- **The integrated, enforced kernel** — multi-tenancy, capability enforcement, durable WAIT/RESUME, single state authority (#1/#4/#13/#17). *This is precisely what `aindy-runtime` provided and what excluding it removes.*

**The coverage headline, honestly stated:**
- Nodus touches **33 of 40** ecosystem concerns (9 Full, 24 Partial) and is correctly absent on **6 application-layer concerns it should host, not provide.** Only **1 substrate concern (secrets/egress) scores zero.**
- **Breadth is near-total; depth is the whole story.** The 24 Partials are mostly *"a v0.1.0 primitive exists, in-memory, that you must wire yourself."* The deepest-difficulty capabilities — event-sourced durability, hostile-safe sandboxing, enforced multi-tenant capability gating — are partial-to-absent.
- **The integration caveat is load-bearing:** strict Nodus is *a strong embeddable language + a wide bag of independent primitive packages*, not a coordinated runtime. The thing that would make them a runtime is the layer this audit excludes (aindy).

**The wedge — where Nodus uniquely sits in the ecosystem:**
Nodus is the **only system in the set that pairs an embeddable, sandbox-aware orchestration *language* with a broad ecosystem of runtime primitives (workflow, memory, MCP, A2A, observability, retry, approvals).** Against the "before pictures" — Devika, GPT-Engineer, MetaGPT, Aider, CrewAI — it is a clear superset of what they hand-roll or offload. Against the specialists — Temporal (durability), OpenHands/Open Interpreter (sandboxing) — it is materially behind on the one hard thing each does best. **Nodus is most useful to the ecosystem as the scriptable orchestration substrate that hosts coding/agent applications, and as a primitive library others embed — not (yet) as a durable, hostile-safe, multi-tenant runtime, which is a depth story that needs either the excluded aindy kernel or substantial new core work (P0–P1) to close.**

---

*Generated from source-verified, file-level inventories of `C:\dev\Coding Language` + `C:\dev\nodus-*`. `aindy-runtime` was excluded entirely. Per-system percentages are deliberate judgment bands, not measured metrics.*
