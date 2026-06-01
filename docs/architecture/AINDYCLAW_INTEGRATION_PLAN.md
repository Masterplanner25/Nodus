# AindyClaw / NodusClaw — Integration Plan
**Working name:** AindyClaw  
**Status:** Discovery / Planning  
**Scope:** Wrap, adapt, supervise — no rewrite

---

## Origin Context — Where the Libraries Came From

The Nodus standalone library ecosystem has two origin codebases:

| Origin | Packages extracted |
|---|---|
| **aindy-runtime** (Python) | Group 1: nodus-circuit-breaker, nodus-auth, nodus-observability, nodus-queue, nodus-state, nodus-observability-framework, nodus-mcp (aindy bridge) |
| **OpenClaw** (TypeScript) | Group 2: nodus-context, nodus-approvals, nodus-channels, nodus-llm, nodus-delivery |

The Group 2 packages are **Python distillations of OpenClaw's TypeScript patterns** — not generic utilities. The specific mapping:

| OpenClaw TypeScript | Nodus Python twin |
|---|---|
| `exec-approval-manager.ts` + internal hooks | `nodus-approvals` (ApprovalGate, ApprovalPolicy) |
| `src/channels/` + channel health monitor | `nodus-channels` (ChannelAdapter, ChannelRegistry, HealthMonitor) |
| `model-auth.ts` + `model-fallback.ts` + auth-profiles | `nodus-llm` (CredentialStore, FailoverClient) |
| `context-window-guard.ts` + compaction | `nodus-context` (ContextWindow, guard/compact) |
| `reply-dispatcher.ts` + chunking | `nodus-delivery` (chunkers, DeliveryRouter) |

**Architectural consequence:** When building AindyClaw, the bridge is not creating a foreign adapter. It is reconnecting Python twins back to their TypeScript origin. `nodus-approvals` was built from OpenClaw's approval gate — it will bridge back to it. The integration surfaces were pre-shaped by extraction. Use the twins; do not re-implement.

---

## Table of Contents

1. [Architecture Map](#1-architecture-map)
2. [Integration Plan](#2-integration-plan)
3. [Minimal Demo Proposal](#3-minimal-demo-proposal)
4. [Risk Assessment](#4-risk-assessment)
5. [Implementation Checklist](#5-implementation-checklist)

---

## 1. Architecture Map

### 1.1 OpenClaw — What It Is

OpenClaw is a TypeScript personal AI assistant (Node.js 22+, ESM, Vitest). It is **not a library** — it is a running daemon: a WebSocket gateway server with an embedded LLM agent runner, multi-channel messaging adapters, a tool suite, a plugin hook system, and scheduled execution.

**Runtime stack:**
```
User channels (WhatsApp, Telegram, Slack, Discord, Signal, iMessage, WebChat, etc.)
    ↓ inbound message
Channel adapters  (src/telegram, src/discord, src/slack, src/signal, src/web, extensions/*)
    ↓
auto-reply dispatcher  (src/auto-reply/dispatch.ts → dispatchInboundMessage)
    ↓
command queue / lanes  (src/process/command-queue.ts → enqueueCommandInLane)
    ↓
pi-embedded-runner  (src/agents/pi-embedded-runner/run.ts → runEmbeddedPiAgent)
    ↓  (uses @mariozechner/pi-coding-agent + @mariozechner/pi-agent-core)
LLM provider  (Anthropic/OpenAI/Gemini/Bedrock via auth-profile rotation)
    ↓ tool calls
Tool suite  (bash, web, memory, sessions, cron, canvas, image, TTS, message, subagents)
    ↓ bash tool → approval gate
ExecApprovalManager  (src/gateway/exec-approval-manager.ts)
    ↓ decision
reply dispatcher → channel adapter → user
```

**Server surface:**
```
Gateway WebSocket server  (src/gateway/server.impl.ts → startGatewayServer)
├── WS methods: connect, chat.send, chat.abort, agent.run, sessions.*, cron.*, 
│              exec.approval.request, exec.approval.resolve, skills.*, health, ...
├── HTTP: GET /health, POST /v1/chat/completions (OpenAI-compat), POST /v1/responses
└── Control UI (optional, served from gateway)
```

### 1.2 OpenClaw — Key Files

| Component | File | Role |
|---|---|---|
| Gateway startup | `src/gateway/server.impl.ts` | Single startup function, all subsystems |
| Message dispatch | `src/auto-reply/dispatch.ts` | Inbound message → agent routing |
| Agent runner | `src/agents/pi-embedded-runner/run.ts` | LLM loop, failover, compaction |
| Tool surface | `src/agents/openclaw-tools.ts` | All tools assembled per-session |
| Exec approval | `src/gateway/exec-approval-manager.ts` | Bash command approval gate |
| Internal hooks | `src/hooks/internal-hooks.ts` | `command`, `session`, `agent`, `gateway`, `message` events |
| Agent events | `src/infra/agent-events.ts` | `lifecycle`, `tool`, `assistant`, `error` stream |
| Plugin hooks | `src/plugins/types.ts` + `hook-runner-global.ts` | `beforeAgentStart`, `afterAgentStop`, tool factories |
| Cron | `src/gateway/server-cron.ts` + `src/cron/service.ts` | Scheduled agent turns |
| Memory | `src/memory/manager.ts` | Embedding search, multi-backend (sqlite, remote) |
| Command queue | `src/process/command-queue.ts` | Serialized lane execution |
| WS method handlers | `src/gateway/server-methods/*.ts` | One file per API domain |
| OpenAI-compat HTTP | `src/gateway/openai-http.ts` | External HTTP API |

### 1.3 OpenClaw — Core Execution Points

These are the places where a wrapper can intercept cleanly:

| Execution point | Where | What it does | Hook-ability |
|---|---|---|---|
| Inbound message received | `dispatchInboundMessage` | Routes message to agent | Internal hook `message:received` |
| Agent run begins | `runEmbeddedPiAgent` | Starts LLM loop | Plugin `beforeAgentStart` |
| Tool call about to execute | `pi-tools.before-tool-call.ts` | Pre-tool policy | Plugin hook |
| Bash command needs approval | `ExecApprovalManager.register()` | Waits for approve/deny | Direct WS: `exec.approval.resolve` |
| Agent run ends | `runEmbeddedPiAgent` returns | Result + usage | Plugin `afterAgentStop` |
| Agent event emitted | `emitAgentEvent()` | Stream of `lifecycle/tool/assistant/error` | `onAgentEvent()` subscription |
| Cron fires | `CronService.run()` | Scheduled agent turn | Observable via WS + cron handlers |
| Reply sent to user | `reply-dispatcher.ts` | Outbound message | Internal hook `message:sent` |

### 1.4 A.I.N.D.Y. Runtime — What It Provides

A.I.N.D.Y. is a FastAPI + PostgreSQL + Redis Python runtime with:

```
AINDY/kernel/syscall_dispatcher.py    — sys.v1.domain.action dispatch
AINDY/core/execution_service.py       — ExecUnit lifecycle management
AINDY/core/observability_events.py    — SystemEvent emission
AINDY/kernel/event_bus.py             — Redis pub/sub event bus
AINDY/runtime/nodus_worker.py         — NodusRuntime host + DeferredMemoryBuiltins
AINDY/memory/                          — pgvector memory backend
AINDY/agents/                          — agent registry + flow engine
```

Key existing syscalls: `sys.v1.memory.read`, `sys.v1.memory.write`, `sys.v1.event.emit`.  
Nodus runs inside `NodusRuntime` (from nodus-lang), hosted by `nodus_worker.py`.

### 1.5 Nodus — What It Provides

Nodus (Python, `nodus-lang`) is a bytecode-compiled scripting language with:
- Workflow declaration and orchestration (nodus_lang_workflow in-tree)
- Coroutine scheduler (spawn/await pattern)
- Syscall dispatch to A.I.N.D.Y. kernel
- `std:retry`, `std:circuit_breaker`, `std:effects` (idempotency)
- `NodusRuntime` Python embedding API
- Memory, approval, events bindings via stdlib or host functions

### 1.6 Target Architecture

```
User channels (WhatsApp, Telegram, Slack, Discord, etc.)
        ↓
OpenClaw Gateway (TypeScript, Node.js 22)
├── Channel adapters + message dispatch
├── Agent runner (pi-embedded-runner)
├── Tool suite (bash, web, memory, sessions, cron)
├── Exec approval gate
├── Plugin hook system ←──────────────────────────────┐
└── Agent event stream (onAgentEvent) ←────────────────┤
        │                                              │
        │  HTTP (OpenAI-compat or direct WS calls)     │
        ↓                                              │
AindyClaw Adapter (Python, thin bridge service)  ──────┘
├── OpenClaw event subscriber (SSE or WS client)
├── Approval bridge (exec.approval.resolve → Nodus gate)
├── NodusRuntime host
└── Syscall forwarder → A.I.N.D.Y. kernel
        ↓
Nodus workflow layer (.nd scripts)
├── Workflow declaration
├── Action orchestration
├── Approval gates (std:approvals)
├── Retry/fallback (std:retry, std:circuit_breaker)
└── Scriptable task dispatch
        ↓
A.I.N.D.Y. Runtime (FastAPI + PostgreSQL + Redis)
├── Syscall dispatcher (sys.v1.*)
├── Execution service (ExecUnit lifecycle)
├── Event bus (Redis pub/sub)
├── Memory backend (pgvector)
├── Observability (metrics, trace IDs)
└── Approval lifecycle (nodus-approvals)
        ↓
Observability stack
├── Structured logs (nodus-observability)
├── Event stream (nodus-events)
├── Metrics (Prometheus optional)
└── Dashboard / mobile control surface (Phase 5)
```

### 1.7 External Dependencies (OpenClaw)

| Category | Packages |
|---|---|
| LLM providers | `@mariozechner/pi-agent-core`, `@mariozechner/pi-coding-agent`, `@mariozechner/pi-ai` |
| Channels | `@grammyjs/runner` (Telegram), `@slack/bolt`, `@whiskeysockets/baileys` (WhatsApp), `@buape/carbon` (Discord), `@line/bot-sdk`, `@larksuiteoapi/node-sdk` |
| Infrastructure | `@homebridge/ciao` (mDNS), `ws` (WebSocket), Node.js built-ins |
| Schema | `@sinclair/typebox` |
| Memory | `better-sqlite3`, embedding providers (OpenAI/Voyage/Gemini) |

---

## 2. Integration Plan

### Phase 0 — Discovery (Already Complete)

**What we now know:**

1. OpenClaw is not importable as a library — it is a running gateway process.
2. Three clean integration surfaces exist: plugin hooks, agent event stream (`onAgentEvent`), and the WebSocket/HTTP API.
3. The exec approval gate (`ExecApprovalManager`) is a ready-made async approval primitive.
4. The internal hook system fires on `message:received`, `agent:bootstrap`, `message:sent`.
5. A.I.N.D.Y. already has a working `nodus_worker.py` that hosts `NodusRuntime`.
6. The syscall dispatcher already handles `sys.v1.memory.*` and `sys.v1.event.emit`.
7. There is no existing bridge between OpenClaw events and Nodus/A.I.N.D.Y.

**Gaps identified:**
- No `sys.v1.openclaw.*` syscalls exist in A.I.N.D.Y.
- No Nodus workflow script targeting OpenClaw actions exists.
- No approval bridge between `ExecApprovalManager` and Nodus approval gates exists.
- OpenClaw's agent event stream has no external consumer.

---

### Phase 1 — Adapter / Wrapper

**Goal:** Stand up the bridge service. No Nodus workflows yet — just connectivity.

**What to build:** `aindyclaw/` Python package (new repo or directory in `aindy-apps-monolith`).

**Key principle:** Use the Group 2 Python twins — do not reinvent. `nodus-approvals` was extracted from OpenClaw's approval gate. `nodus-channels` was extracted from OpenClaw's channel patterns. `nodus-llm` was extracted from OpenClaw's model failover. Wire the twins back to their origin rather than writing new adapter code from scratch.

**Components:**

#### 1A. OpenClaw WS Client (`aindyclaw/openclaw_client.py`)
Connect to the running OpenClaw gateway as an operator-role WebSocket client.

```python
# Connects to ws://localhost:18789 with operator credentials
# Calls: connect, subscribes to agent events via server-node-events
class OpenClawGatewayClient:
    async def connect(self): ...
    async def send_message(self, session_key, message): ...
    async def run_agent(self, message, session_key): ...
    async def resolve_approval(self, approval_id, decision): ...  # "allow" | "deny"
    async def subscribe_agent_events(self, on_event): ...
```

The gateway WebSocket protocol is JSON-RPC style: `{"method": "chat.send", "params": {...}}`.  
Auth: set `role: "operator"` in the `connect` call. Credentials come from OpenClaw config.

**Wrap with nodus-channels:** Register `OpenClawGatewayClient` as a `ChannelAdapter` in a  
`ChannelRegistry`. The `HealthMonitor` then tracks CONNECTED → DEGRADED → DISCONNECTED  
automatically — same state machine OpenClaw already uses internally.

```python
from nodus_channels import ChannelRegistry, HealthMonitor
registry = ChannelRegistry()
registry.register("openclaw-gateway", OpenClawChannelAdapter(client))
monitor = HealthMonitor(registry)  # automatic health tracking
```

#### 1B. Agent Event Forwarder (`aindyclaw/event_forwarder.py`)
Subscribe to `onAgentEvent()` via WS (gateway broadcasts agent events on `server-node-events.ts`)  
and forward each event to A.I.N.D.Y. event bus.

```python
# Maps OpenClaw event streams → sys.v1.event.emit syscalls
# Event shapes: { runId, stream: "lifecycle|tool|assistant|error", data, sessionKey }
async def forward_event(event: dict):
    await dispatcher.dispatch("sys.v1.event.emit", {
        "event_type": f"openclaw.agent.{event['stream']}",
        "payload": event,
        "source": "openclaw-adapter",
    }, ctx)
```

#### 1C. Approval Bridge (`aindyclaw/approval_bridge.py`)
When the OpenClaw exec approval gate fires (via `exec.approval.request` WS event),  
route through `nodus-approvals` ApprovalGate (the Python twin of `ExecApprovalManager`)  
and forward the decision back.

```python
from nodus_approvals import ApprovalGate, ApprovalPolicy

# Policy mirrors OpenClaw's existing risk patterns
policy = ApprovalPolicy(rules=[
    "rm *", "sudo *", "curl *", "wget *", "chmod *", "chown *",
])

async def on_approval_request(approval_payload: dict):
    # approval_payload: { id, command, cwd, agentId, sessionKey, ... }
    command = approval_payload["command"]
    if policy.requires_approval(command):
        gate = ApprovalGate(store)
        request_id = gate.check(command)
        decision = await gate.poll(request_id, timeout_ms=30_000)
    else:
        decision = "approved"  # auto-approve non-risk commands
    await openclaw_client.resolve_approval(approval_payload["id"], decision)
```

Note: `nodus-approvals` was extracted from `ExecApprovalManager` — the gate semantics  
(check/approve/deny/poll) map directly to OpenClaw's `register/resolve/awaitDecision`.

#### 1D. LLM Failover Layer (`aindyclaw/llm_client.py`)
When AindyClaw needs to make its own LLM calls (summarization, routing decisions),  
use `nodus-llm` FailoverClient — the Python twin of OpenClaw's `model-auth.ts` failover.

```python
from nodus_llm import FailoverClient, CredentialStore

# Same backoff profile as OpenClaw: 5m→10m→20m→40m→1h
creds = CredentialStore.from_env()
client = FailoverClient(creds)
response = await client.chat(messages=[...])
```

#### 1E. Syscall Registration (`aindyclaw/syscalls.py`)
Register `sys.v1.openclaw.*` syscalls in A.I.N.D.Y.'s syscall registry.

```python
# New syscalls to register:
# sys.v1.openclaw.send_message   — send a message via OpenClaw to any channel
# sys.v1.openclaw.run_agent      — trigger an agent run
# sys.v1.openclaw.get_session    — get session state
# sys.v1.openclaw.list_channels  — list connected channels
```

#### 1F. Context Window Guard (`aindyclaw/context.py`)
When preparing messages for Nodus workflow prompts or syscall payloads,  
use `nodus-context` ContextWindow — the Python twin of OpenClaw's `context-window-guard.ts`.

```python
from nodus_context import ContextWindow, DropToolInternalsStrategy

# Guard tool results before passing to Nodus workflow context
window = ContextWindow(budget=8000)
window.add(session_history)
window.guard_tool_results()  # drops oversized tool results, same as OpenClaw does
safe_payload = window.messages
```

**Deliverable:** OpenClaw gateway events arrive in A.I.N.D.Y.'s event bus. Approval requests  
go through `nodus-approvals` gates (the Python twin of `ExecApprovalManager`). Nodus scripts  
can trigger OpenClaw actions via syscalls. The channel is tracked by `nodus-channels` health monitor.

---

### Phase 2 — Nodus Workflow

**Goal:** Write the first `.nd` workflow script that wraps a real OpenClaw action.

**What to build:** `aindyclaw/workflows/` directory of `.nd` files, loaded by `nodus_worker.py`.

#### 2A. Minimal workflow: supervised message dispatch

```nodus
// aindyclaw/workflows/message_dispatch.nd
import "std:memory" as mem
import "std:retry" as retry

fn handle_inbound(session_key, message, channel) {
    // Record arrival
    mem.put("last_msg_channel", channel)
    
    // Dispatch to OpenClaw agent with retry
    let result = retry.call(
        fn() { sys("sys.v1.openclaw.run_agent", {"session_key": session_key, "message": message}) },
        {"max_attempts": 3i, "backoff_ms": 1000i}
    )
    
    sys("sys.v1.event.emit", {
        "event_type": "aindyclaw.dispatch.complete",
        "payload": {"session_key": session_key, "ok": result}
    })
    
    return result
}
```

#### 2B. Approval workflow: bash command gate

```nodus
// aindyclaw/workflows/exec_approval.nd
import "std:approvals" as approvals

fn gate_exec(command, agent_id, session_key) {
    // High-risk commands require explicit approval
    let needs_review = command == "rm" or command == "sudo" or command == "curl"
    
    if (needs_review) {
        let decision = approvals.request({
            "resource": command,
            "reason": "\(agent_id) wants to run: \(command)",
            "timeout_ms": 30000i
        })
        if (decision != "approved") {
            return {"allowed": false, "reason": "denied by approval gate"}
        }
    }
    
    return {"allowed": true}
}
```

#### 2C. NodusRuntime entrypoint (`aindyclaw/nodus_runner.py`)

```python
from nodus.runtime.embedding import NodusRuntime

class AindyClawRunner:
    def __init__(self, syscall_dispatcher):
        self.rt = NodusRuntime(timeout_ms=None, max_steps=None)
        # Register syscall bridge
        self.rt.register_function("sys", self._syscall, arity=2)
    
    def _syscall(self, name, payload):
        ctx = build_syscall_context()
        return syscall_dispatcher.dispatch(name, payload, ctx)
    
    def run_workflow(self, script_path, fn_name, args):
        source = open(script_path).read()
        result = self.rt.run_source(source)
        # Call specific function with args
        ...
```

---

### Phase 3 — Runtime Supervision

**Goal:** A.I.N.D.Y. runtime owns the lifecycle of every OpenClaw-triggered Nodus run.

**What to build:**
- Register each workflow run as an `ExecUnit` in A.I.N.D.Y.'s execution service.
- Use A.I.N.D.Y.'s `resume_watchdog.py` to detect stuck runs.
- Map OpenClaw session key → A.I.N.D.Y. execution unit ID.
- Emit `EXEC_UNIT_STARTED`, `EXEC_UNIT_COMPLETED`, `EXEC_UNIT_FAILED` events.

**Integration point:** `AINDY/core/execution_service.py` — call `create_execution_unit()` when a workflow starts, `complete_execution_unit()` when it finishes.

**Key pattern:**
```python
exec_unit = await execution_service.create_execution_unit(
    user_id=user_id,
    workflow_id="aindyclaw.message_dispatch",
    input_payload={"session_key": session_key, "message": message},
)
try:
    result = runner.run_workflow("message_dispatch.nd", "handle_inbound", {...})
    await execution_service.complete_execution_unit(exec_unit.id, result)
except Exception as exc:
    await execution_service.fail_execution_unit(exec_unit.id, str(exc))
```

---

### Phase 4 — Observability

**Goal:** Every OpenClaw action that touches the Nodus/A.I.N.D.Y. layer is visible and traceable.

**What to build:**
- Emit structured events for every integration point (message received, agent started, tool called, approval requested, approval resolved, run completed).
- Tag all events with `source: "openclaw"`, `session_key`, `agent_id`, `run_id`.
- Surface in A.I.N.D.Y.'s platform dashboard (`/platform`).

**Event taxonomy:**
```
openclaw.message.received     { session_key, channel, from, message_id }
openclaw.agent.started        { run_id, session_key, model }
openclaw.agent.tool_call      { run_id, tool_name, input_summary }
openclaw.approval.requested   { approval_id, command, agent_id }
openclaw.approval.resolved    { approval_id, decision, resolved_by }
openclaw.agent.completed      { run_id, session_key, usage }
openclaw.agent.failed         { run_id, error, stage }
aindyclaw.dispatch.complete   { session_key, ok }
```

**Integration with nodus-observability:**
- Use `nodus-observability` trace ContextVars to carry trace ID through the Python side.
- Pass `X-Trace-ID` when calling OpenClaw HTTP endpoints.
- Log all syscall results with duration and status.

---

### Phase 5 — Dashboard / Mobile Control Surface

**Goal:** See and control OpenClaw sessions from A.I.N.D.Y.'s platform UI, plus an optional mobile app.

**Out of scope for v1.** Needs Phase 1–4 stable first.

**Planned surface:**
- A.I.N.D.Y. platform shows `openclaw.agent.*` event stream in real time.
- Approval requests surface as actionable items in the control UI.
- Mobile push notifications for approval requests (via nodus-mcp or mobile bridge).

---

## 3. Minimal Demo Proposal

**Name:** AindyClaw Hello-World  
**Goal:** Prove the architecture. One message in → one supervised, observable, approvable run out.

### 3.1 One Workflow

**File:** `aindyclaw/workflows/supervised_hello.nd`

```nodus
// Minimal supervised hello-world workflow
import "std:memory" as mem
import "std:effects" as fx

fn supervised_hello(session_key, message) {
    // Idempotency: skip duplicate runs with the same session+message
    let action_id = fx.action_id("aindyclaw.hello", {}, session_key)
    let r = fx.resolve(action_id)
    if (r.done) { return "already-ran" }
    
    fx.pending(action_id, message)
    
    // Record intent
    mem.put("last_session", session_key)
    mem.put("last_message", message)
    
    // Call OpenClaw agent
    let result = sys("sys.v1.openclaw.run_agent", {
        "session_key": session_key,
        "message": message
    })
    
    fx.complete(action_id, "success", {"result": result})
    
    sys("sys.v1.event.emit", {
        "event_type": "aindyclaw.hello.complete",
        "payload": {"session_key": session_key, "ok": true}
    })
    
    return result
}
```

### 3.2 One Nodus Entrypoint

**File:** `aindyclaw/nodus_runner.py`

```python
from nodus.runtime.embedding import NodusRuntime
from pathlib import Path

WORKFLOWS_DIR = Path(__file__).parent / "workflows"

class AindyClawRunner:
    def __init__(self, dispatcher, ctx_factory):
        self.rt = NodusRuntime(timeout_ms=None, max_steps=None)
        self.rt.register_function("sys", lambda name, payload: 
            dispatcher.dispatch(name, payload, ctx_factory()), arity=2)
    
    def run_supervised_hello(self, session_key: str, message: str):
        src = (WORKFLOWS_DIR / "supervised_hello.nd").read_text()
        # Run the script (defines the function), then call it
        self.rt.run_source(src)
        return self.rt.run_source(f'supervised_hello("{session_key}", "{message}")')
```

### 3.3 One Runtime Entrypoint

**File:** `aindyclaw/service.py` — a small FastAPI app or background task that:

1. Starts the OpenClaw gateway client (connects as operator).
2. Subscribes to agent events → forwards to A.I.N.D.Y. event bus.
3. Listens for `exec.approval.request` from gateway → routes through Nodus approval gate.
4. Exposes `POST /aindyclaw/run` → triggers `supervised_hello` workflow.

```python
@app.post("/aindyclaw/run")
async def run(body: RunRequest):
    exec_unit = await execution_service.create_execution_unit(...)
    result = runner.run_supervised_hello(body.session_key, body.message)
    await execution_service.complete_execution_unit(exec_unit.id, result)
    return {"ok": True, "result": result, "exec_unit_id": exec_unit.id}
```

### 3.4 One Observable Event Stream

Subscribe to `sys.v1.event.*` in A.I.N.D.Y.'s event bus and watch:

```
openclaw.message.received  →  aindyclaw.hello.started  →  openclaw.agent.started  
  →  openclaw.agent.completed  →  aindyclaw.hello.complete
```

Visible at: `GET /platform` → Events tab, filtered by `source=openclaw`.

### 3.5 One Approval / Safety Boundary

When OpenClaw's agent calls the `bash` tool with a command matching a risk pattern  
(`rm -rf`, `sudo`, `curl`, `wget`, network writes), the approval bridge intercepts  
`exec.approval.request` from the gateway WS stream and routes it through a Nodus gate:

```
OpenClaw ExecApprovalManager (create + register)
    ↓ WS event: exec.approval.request
AindyClaw approval_bridge.py
    ↓
Nodus: approvals.request({ resource: command, timeout_ms: 30_000 })
    ↓ operator approves/denies (via /platform UI or mobile push)
AindyClaw: openclaw_client.resolve_approval(approval_id, decision)
    ↓
OpenClaw ExecApprovalManager resolves → bash runs or aborts
```

**Safety rule for v1:** Any bash command containing `rm`, `sudo`, `curl`, `wget`, `chmod`, or `chown` requires explicit approval. All others auto-approve (fail-open initially, tighten in v2).

---

## 4. Risk Assessment

### 4.1 Architectural Risks

| Risk | Severity | Mitigation |
|---|---|---|
| OpenClaw WS protocol is undocumented externally | Medium | Read `src/gateway/server-methods-list.ts` and `src/gateway/protocol/` for schema. Use `connect` → subscribe pattern. |
| OpenClaw's event broadcast may not include all agent events by default | Medium | Verify `server-node-events.ts` sends to operator-role WS clients. May need a dedicated `node` connection. |
| `ExecApprovalManager` approval IDs are UUID-scoped per gateway instance | Low | The bridge must proxy the same ID back; do not generate a new one. |
| A.I.N.D.Y. syscall dispatcher currently has no `sys.v1.openclaw.*` handlers | High (known gap) | Phase 1 registers them. This is the first thing to build. |
| Nodus `NodusRuntime` 200ms default timeout kills long agent waits | High (known) | Always instantiate with `timeout_ms=None, max_steps=None` (EMBED-001). |
| OpenClaw uses Node.js; A.I.N.D.Y. is Python — no shared in-process state | Low | The HTTP/WS bridge pattern handles this. Do not try to share memory. |
| A.I.N.D.Y.'s `nodus_worker.py` was built for single-user in-process execution | Medium | For AindyClaw, run a separate `NodusRuntime` instance per workflow run. Do not reuse. |

### 4.2 Security Risks

| Risk | Severity | Mitigation |
|---|---|---|
| OpenClaw gateway exposes bash tool with real host execution | Critical | Do not weaken OpenClaw's existing sandbox. AindyClaw approval gate must be additive, not a bypass. |
| AindyClaw WS client holds operator-role credential | High | Store credential in A.I.N.D.Y.'s secret store; never in .nd files or logs. Use `nodus-auth` token model. |
| Approval bridge has a TOCTOU window: approval granted → command changes | Medium | The approval ID is bound to the specific command payload in `ExecApprovalRecord`. Do not re-verify at bridge layer; OpenClaw already does it. |
| Syscall `sys.v1.openclaw.send_message` could be called by any Nodus script | Medium | Gate with `SyscallContext.capabilities` check: require `"openclaw.send"` capability. |
| Event forwarding from OpenClaw may leak session content to A.I.N.D.Y.'s event bus | Medium | Strip `content`/`messages` fields from forwarded events; forward only metadata (run_id, session_key, tool_name, stream type). |

### 4.3 Reliability Risks

| Risk | Severity | Mitigation |
|---|---|---|
| AindyClaw bridge service crash disconnects all event forwarding | High | Run under A.I.N.D.Y.'s apscheduler or as a supervised process. Reconnect on disconnect. Use `nodus-circuit-breaker` around WS calls. |
| OpenClaw gateway restart orphans pending approval requests | Medium | Approval timeout is already built into `ExecApprovalManager` (15s grace). Bridge should auto-deny on disconnect. |
| A.I.N.D.Y. syscall calls block the Nodus coroutine scheduler | High (known: EMBED-004) | `*_async` builtins are serial. Use subprocess_spawn pattern or run syscalls in Python threads. For v1, accept serial behavior. |
| Long-running OpenClaw agent runs may exceed Nodus step limit | Medium | Set `max_steps=None` on runtime. Monitor run duration via A.I.N.D.Y. observability. |

### 4.4 Scope Creep Risks

| Risk | Mitigation |
|---|---|
| Rebuilding OpenClaw features inside Nodus | Constraint: Nodus only orchestrates. It does not re-implement channels, memory search, auth profiles, or model routing. Those stay in OpenClaw. |
| Moving A.I.N.D.Y. app logic into the bridge service | Constraint: Bridge is stateless transport only. App logic stays in A.I.N.D.Y. workflows and Python domain code. |
| Adding dashboard/mobile before Phase 1–4 are stable | Phase 5 is explicitly blocked on Phase 4 complete. No dashboard work until events are flowing reliably. |
| Expanding the approval gate to all tool calls | v1 approval gate covers bash only (`exec.approval.*`). Memory, web-fetch, message tools are out of scope for v1. |

---

## 5. Implementation Checklist

### Phase 1 Checklist — Adapter / Wrapper

#### Install Group 2 twins first

```bash
pip install -e C:\dev\nodus-channels --no-deps
pip install -e C:\dev\nodus-approvals --no-deps
pip install -e C:\dev\nodus-context --no-deps
pip install -e C:\dev\nodus-circuit-breaker --no-deps   # nodus-llm dep
pip install -e C:\dev\nodus-llm --no-deps
pip install -e C:\dev\nodus-delivery --no-deps
```

#### Files to create

- [ ] `aindyclaw/__init__.py`
- [ ] `aindyclaw/openclaw_client.py` — WS client wrapped as `nodus-channels` ChannelAdapter
- [ ] `aindyclaw/event_forwarder.py` — `forward_agent_event()` → `sys.v1.event.emit`
- [ ] `aindyclaw/approval_bridge.py` — `nodus-approvals` ApprovalGate + policy + OpenClaw resolve-back
- [ ] `aindyclaw/context.py` — `nodus-context` ContextWindow for session payload guard
- [ ] `aindyclaw/llm_client.py` — `nodus-llm` FailoverClient for AindyClaw's own LLM calls
- [ ] `aindyclaw/syscalls.py` — register `sys.v1.openclaw.send_message`, `sys.v1.openclaw.run_agent`, `sys.v1.openclaw.get_session`, `sys.v1.openclaw.list_channels`
- [ ] `aindyclaw/service.py` — FastAPI app or background task runner
- [ ] `aindyclaw/config.py` — `OPENCLAW_WS_URL`, `OPENCLAW_OPERATOR_TOKEN`, `OPENCLAW_DEFAULT_SESSION_KEY`
- [ ] `tests/test_openclaw_client.py` — mock WS server, test connect + channel health state
- [ ] `tests/test_event_forwarder.py` — mock dispatcher, verify event shape forwarded
- [ ] `tests/test_approval_bridge.py` — mock gateway + ApprovalGate, verify round-trip + policy

#### Files to inspect first

- [ ] `C:\codev\openclaw_research\openclaw\src\gateway\server-methods-list.ts` — full list of WS methods
- [ ] `C:\codev\openclaw_research\openclaw\src\gateway\protocol\` — param schemas for each method
- [ ] `C:\codev\openclaw_research\openclaw\src\gateway\server-node-events.ts` — verify operator clients receive agent events
- [ ] `C:\codev\openclaw_research\openclaw\src\gateway\server-methods\connect.ts` — auth + role connect flow
- [ ] `C:\codev\openclaw_research\openclaw\src\infra\exec-approvals.ts` — `ExecApprovalDecision` shape
- [ ] `C:\dev\aindy-runtime\AINDY\kernel\syscall_registry.py` — how to register new syscalls

#### Commands to run

```bash
# Verify OpenClaw gateway is running and reachable
cd C:\codev\openclaw_research\openclaw
pnpm openclaw gateway run --port 18789 --verbose

# Inspect WS protocol (connect as operator and list methods)
# Use wscat: npx wscat -c ws://localhost:18789
# Send: {"id": 1, "method": "connect", "params": {"role": "operator"}}
# Then: {"id": 2, "method": "health", "params": {}}

# Run existing aindy-runtime tests to confirm baseline
cd C:\dev\aindy-runtime
python -m pytest tests/ -q --ignore=tests/integration/ -x

# Confirm NodusRuntime works from aindy-runtime context
PYTHONPATH="C:/dev/Coding Language/src" python -c "from nodus.runtime.embedding import NodusRuntime; rt = NodusRuntime(timeout_ms=None, max_steps=None); print(rt.run_source('print(\"ok\")'))"
```

---

### Phase 2 Checklist — Nodus Workflow

#### Files to create

- [ ] `aindyclaw/workflows/supervised_hello.nd` — minimal supervised dispatch workflow
- [ ] `aindyclaw/workflows/exec_approval.nd` — approval gate workflow
- [ ] `aindyclaw/nodus_runner.py` — `AindyClawRunner` class with `sys()` host function
- [ ] `tests/test_nodus_runner.py` — mock syscall dispatcher, verify workflows execute

#### Verify .nd scripts work locally

```powershell
# Test supervised_hello.nd syntax
PYTHONPATH="C:/dev/Coding Language/src" "C:/dev/Coding Language/.venv/Scripts/python.exe" `
  -m nodus check aindyclaw/workflows/supervised_hello.nd

# Test exec_approval.nd syntax
PYTHONPATH="C:/dev/Coding Language/src" "C:/dev/Coding Language/.venv/Scripts/python.exe" `
  -m nodus check aindyclaw/workflows/exec_approval.nd
```

---

### Phase 3 Checklist — Runtime Supervision

#### Files to modify

- [ ] `aindyclaw/service.py` — wrap each workflow run in `create_execution_unit` / `complete_execution_unit`
- [ ] `AINDY/core/execution_service.py` — verify `create_execution_unit` accepts `workflow_id` field

#### Files to create

- [ ] `aindyclaw/exec_unit_wrapper.py` — context manager: `async with exec_unit_context(service, user_id, workflow_id) as unit: ...`

#### Commands to run

```bash
# Verify execution_service integration
cd C:\dev\aindy-runtime
python -m pytest tests/unit/test_execution_service.py -v

# Check execution_unit table exists in DB
docker compose exec postgres psql -U aindy -c "\dt nodus_*"
```

---

### Phase 4 Checklist — Observability

#### Files to create

- [ ] `aindyclaw/events.py` — `AINDYCLAW_EVENT_TYPES` constants, `emit_aindyclaw_event()` helper
- [ ] `aindyclaw/trace.py` — `TraceContext` that carries trace_id through WS → syscall → Nodus

#### Files to modify

- [ ] `aindyclaw/openclaw_client.py` — add `X-Trace-ID` header to any HTTP calls
- [ ] `aindyclaw/event_forwarder.py` — strip sensitive fields before forwarding

#### Verify events are visible

```bash
# Watch A.I.N.D.Y. event bus for aindyclaw events
cd C:\dev\aindy-runtime
python -c "
from AINDY.kernel.event_bus import get_event_bus
import asyncio
async def main():
    bus = get_event_bus()
    async for event in bus.subscribe('aindyclaw.*'):
        print(event)
asyncio.run(main())
"
```

---

## Answers to the 10 Questions

**Q1. Current architecture of OpenClaw?**  
TypeScript gateway daemon. WS server + embedded LLM agent runner + multi-channel adapters + plugin hook system + tool suite + exec approval gate + cron. Not a library; a running process.

**Q2. Core execution points?**  
`dispatchInboundMessage` → `enqueueCommandInLane` → `runEmbeddedPiAgent` → tool calls → `ExecApprovalManager` → reply dispatch.

**Q3. Actions that could be Nodus-callable commands?**  
`sys.v1.openclaw.run_agent`, `sys.v1.openclaw.send_message`, `sys.v1.openclaw.get_session`, `sys.v1.openclaw.list_channels`, `sys.v1.openclaw.resolve_approval`.

**Q4. What does a `.nd` workflow look like for the smallest demo?**  
See `supervised_hello.nd` in §3.1. ~15 lines. Uses `std:effects` for idempotency, calls `sys()` host function, emits completion event.

**Q5. What runtime endpoint receives the workflow?**  
`POST /aindyclaw/run` on the AindyClaw bridge service, which hosts `AindyClawRunner` and connects to A.I.N.D.Y.'s syscall dispatcher.

**Q6. What events should be emitted?**  
`openclaw.message.received`, `openclaw.agent.started`, `openclaw.agent.tool_call`, `openclaw.approval.requested`, `openclaw.approval.resolved`, `openclaw.agent.completed`, `aindyclaw.dispatch.complete`.

**Q7. What should be visible in observability?**  
Every run's trace (trace_id), session_key, agent_id, tool calls made, approval decisions, run duration, syscall durations, and final status.

**Q8. What should require approval?**  
Bash commands containing `rm`, `sudo`, `curl`, `wget`, `chmod`, `chown`. All others auto-approve in v1.

**Q9. What is explicitly out of scope for v1?**  
Channel adapter changes in OpenClaw, memory search integration, multi-agent orchestration, mobile control surface, OpenClaw UI changes, A.I.N.D.Y. domain application logic, model routing decisions.

**Q10. Safest, fastest path to a working demo?**  
1. Confirm OpenClaw gateway runs locally and the WS protocol is readable.  
2. Build `openclaw_client.py` with `connect()` + `run_agent()` + mock-tested.  
3. Register `sys.v1.openclaw.run_agent` in A.I.N.D.Y. syscall registry.  
4. Write `supervised_hello.nd` calling that syscall.  
5. Run `AindyClawRunner.run_supervised_hello("main", "hello world")`.  
6. Watch event bus output.  
7. Add approval bridge last (it requires a running agent making bash calls to test).

Total: ~3–5 focused days for a working, observable Phase 1+2 demo.
