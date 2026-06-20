# Nodus Ecosystem

`nodus-lang` is the core language and runtime. The surrounding ecosystem is
**35 standalone Python packages** that extend it for specific domains: MCP
integration, agent coordination, memory, observability, circuit breaking, auth,
queuing, SQL persistence, and more.

All packages are at `github.com/Masterplanner25` and published on PyPI.

---

## Quick Start: Unified SDK

The fastest way to get the full ecosystem is the unified SDK:

```bash
pip install nodus-sdk                          # core + nodus-lang
pip install nodus-sdk[agent]                   # + agent coordination
pip install nodus-sdk[sql]                     # + SQL persistence
pip install nodus-sdk[fastapi]                 # + FastAPI bridge
pip install nodus-sdk[agent,sql,fastapi]       # everything
```

`nodus-sdk` auto-wires the packages it installs: when you create a
`NodusSDKRuntime`, the relevant bridges connect automatically.

```python
from nodus_sdk import create_runtime

rt = create_runtime(
    http=True,         # enable http bridge
    llm=True,          # enable LLM client
    sql="sqlite:///db.sqlite3",  # SQL store
)
result = rt.run_source(source)
```

---

## Language Extension Packages

These packages expose `.nd` files through the `nodus.nd` entry-point group,
making them importable directly from Nodus scripts:

### nodus-mcp — MCP Protocol Library

```bash
pip install nodus-mcp
```

```nd
import "nodus-mcp" as mcp

let client = mcp.client()
let conn = client.connect("https://mcp.example.com", bearer_token="sk-...")
let tools = conn.tools()
```

Full bidirectional MCP client + server implementing the 2026-07-28 RC
specification. Supports stdio and HTTP transports, elicitation, roots,
and sampling. Bearer-token auth in v0.1; OAuth 2.0 + PKCE in v1.0.

See: [`/nodus-mcp-phase`](../../.claude/commands/nodus-mcp-phase.md) skill,
[`/nodus-mcp-oauth`](../../.claude/commands/nodus-mcp-oauth.md) skill.

### nodus-extension — Plugin Framework

```bash
pip install nodus-extension
```

```nd
import "nodus-extension" as ext

ext_load("/path/to/my-plugin")
let result = ext_invoke("my-plugin", "tool.name", "{\"key\": \"value\"}")
```

Typed, versioned, sandboxed plugin framework. Third-party developers write
`nodus-extension.json` + `extension.py`; the framework loads them via
subprocess. Supports capability gating and ABI versioning.

---

## Python-Side Companion Packages

These packages are Python APIs, not Nodus language extensions. They integrate
with `NodusRuntime` or work standalone.

### Protocol and Integration

| Package | What it does |
|---------|-------------|
| `nodus-a2a` | AgentCoordinator — local/delegate mode, dead-letter service, watchdog |
| `nodus-native-memory-engine` | PyO3/Maturin Rust extension — 9 native memory operations with Python fallback |

### Memory and Storage

| Package | What it does |
|---------|-------------|
| `nodus-memory` | MemoryNode, InMemoryStore, semantic scoring, recall, feedback |
| `nodus-store-sql` | SQLAlchemy-backed RunStore, EventStore, JobStore (sync + async) |

### Agent Infrastructure

| Package | What it does |
|---------|-------------|
| `nodus-agent` | AgentRun, CapabilityToken (HMAC-SHA256), LocalPlanner/LLMPlanner |
| `nodus-workflow` | FlowDefinition, SchedulerEngine, FlowExecutor (standalone, no server wiring) |
| `nodus-state` | FlowStatus, UnitStatus, AgentStatus, WaitCondition, ResumeSpec |
| `nodus-session` | SessionEntry, InMemorySessionStore, SessionPruningPolicy |

### Reliability

| Package | What it does |
|---------|-------------|
| `nodus-retry` | RetryPolicy (6 named policies), execute_with_retry sync + async |
| `nodus-circuit-breaker` | Three-state CB, sync + async, optional Prometheus |

### Observability

| Package | What it does |
|---------|-------------|
| `nodus-observability` | Trace ContextVars, init_otel(), create_registry(), configure_logging() |
| `nodus-observability-framework` | AIMetrics, RequestMetricWriter, middleware, health router |

### Networking and Communication

| Package | What it does |
|---------|-------------|
| `nodus-http` | HttpClient with circuit breaker + retry + trace headers |
| `nodus-channels` | ChannelAdapter protocol, ChannelRegistry, HealthMonitor |
| `nodus-delivery` | DeliveryPlan, SizeChunker, ParagraphChunker, MarkdownBlockChunker |
| `nodus-gateway` | GatewayServer (WebSocket + handler dispatch + idempotency cache) |
| `nodus-adapter-base` | BaseChannelAdapter (reconnect backoff, health recording) |

### Data and Schema

| Package | What it does |
|---------|-------------|
| `nodus-schema` | validate_payload(), parse_versioned_name(), SchemaRegistry |
| `nodus-protocol` | RequestEnvelope, ResponseEnvelope, EventEnvelope with JSON encode/decode |
| `nodus-events` | EventBus (Redis pub/sub, dedup, pre-rehydration buffer), AuditStore |
| `nodus-queue` | RedisQueueBackend LPUSH/BRPOP, DLQ, delayed jobs |

### Access and Identity

| Package | What it does |
|---------|-------------|
| `nodus-auth` | JWT/API-key/bcrypt; requires `bcrypt<5.0` |
| `nodus-approvals` | ApprovalGate (check/approve/deny/poll), ApprovalPolicy, PairingStore |
| `nodus-governance` | OperatorScope, PolicyBundle, TrustSurface (deny-by-default), AuditTrail |

### Language Integration

| Package | What it does |
|---------|-------------|
| `nodus-context` | ContextBudget, ContextWindow (add/compact/guard_tool_results) |
| `nodus-router` | RouteBinding, RoutingTable, RouteResolver |
| `nodus-llm` | CredentialStore, FailoverClient (5m→10m→20m→40m→1h backoff) |

---

## Install Tiers

The packages have layered dependencies:

```
Tier 0: nodus-lang (core — all other packages depend on this)

Tier 1: Zero-dep standalone
  nodus-circuit-breaker, nodus-retry, nodus-channels, nodus-protocol,
  nodus-schema, nodus-approvals, nodus-context, nodus-state, nodus-session,
  nodus-governance, nodus-agent, nodus-workflow, nodus-a2a, nodus-store-sql

Tier 2: Requires Tier 1
  nodus-auth (python-jose, passlib, bcrypt<5.0)
  nodus-observability (python-json-logger optional)
  nodus-queue (tenacity; redis optional)
  nodus-events (redis optional)
  nodus-router (nodus-session optional)
  nodus-delivery (nodus-channels)
  nodus-http (httpx)
  nodus-llm (openai/anthropic optional)
  nodus-gateway (websockets optional)
  nodus-observability-framework (nodus-observability)
  nodus-adapter-base (nodus-channels)

Tier 3: Requires nodus-lang on PyPI
  nodus-extension (nodus-lang, pydantic)
  nodus-memory (nodus-events; pgvector/openai optional)
  nodus-mcp (nodus-lang, httpx)
  nodus-native-memory-engine (PyO3/Maturin wheel)

Tier 4: Unified SDK
  nodus-sdk (nodus-lang, nodus-schema, nodus-protocol, nodus-retry)
```

**Note:** `nodus-retry` and `nodus-circuit-breaker` are required dependencies
of `nodus-lang` itself (they back `std:retry` and `std:circuit_breaker`).

---

## Third-Party Libraries

Any Python package can become a Nodus library by registering a `nodus.nd`
entry-point:

```toml
# In your package's pyproject.toml:
[project.entry-points."nodus.nd"]
my-library = "my_package.nd:get_nd_root"
```

When installed via `pip install my-library`, it becomes importable in any Nodus
script as `import "my-library"`. See [library-entry-points.md](library-entry-points.md)
for the complete authoring guide.

---

## See also

- [ai-primitives.md](ai-primitives.md) — std:tool, std:identity, std:effects, std:memory, std:retry, std:circuit_breaker
- [library-entry-points.md](library-entry-points.md) — how to publish a Nodus library
- [embedding-nodus.md](embedding-nodus.md) — NodusRuntime and nodus-sdk integration
- `docs/governance/ECOSYSTEM_READINESS_ASSESSMENT.md` — readiness status per package
