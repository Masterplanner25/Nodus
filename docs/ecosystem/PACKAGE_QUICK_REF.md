# Standalone Package Quick Reference

All packages at `C:\dev\<pkg>`, GitHub repos under Masterplanner25.
Test command: `cd C:\dev\<pkg> && python -m pytest -q`.

## Group 1 — AINDY-derived (7 packages)

| Package | Key deps | Key abstraction |
|---------|----------|----------------|
| nodus-circuit-breaker | none | Three-state CB, sync+async, optional Prometheus |
| nodus-auth | python-jose, passlib, **bcrypt<5.0**, pydantic | JWT/API-key/bcrypt; **bcrypt must be <5.0** (passlib 1.7.4 incompatible with 5.x) |
| nodus-observability | python-json-logger (otel/prometheus optional) | Trace ContextVars, init_otel(), create_registry(), configure_logging() |
| nodus-queue | tenacity (redis optional) | RedisQueueBackend LPUSH/BRPOP+Lua, DLQ, delayed jobs; Redis tests need live Redis — skip with `--ignore=tests/test_redis_backend.py` |
| nodus-state | none | FlowStatus/UnitStatus/AgentStatus, WaitCondition, ResumeSpec, ExecutionContext, SessionKey |
| nodus-observability-framework | nodus-observability, fastapi optional | AIMetrics (8), RequestMetricWriter, middleware, health router, ExecutionBlock streaming, CostAttribution/CostTracker |
| nodus-mcp (aindy bridge) | mcp>=1.0.0 | ToolDefinition, ToolRegistry, NodusServer, MCPClientAdapter; flat code at `nodus_mcp_aindy/` in C:\dev\nodus-mcp |

## Group 2 — OpenClaw-derived (5 packages)

| Package | Key deps | Key abstraction |
|---------|----------|----------------|
| nodus-context | none | ContextBudget, ContextWindow (add/compact/guard_tool_results), DropToolInternalsStrategy, SummarizeStrategy |
| nodus-approvals | none | ApprovalGate (check/approve/deny/poll), ApprovalPolicy (fnmatch rules), PairingStore (6-digit codes) |
| nodus-channels | none | ChannelAdapter protocol, ChannelRegistry, HealthMonitor (CONNECTED→DEGRADED→DISCONNECTED) |
| nodus-llm | nodus-circuit-breaker | CredentialStore, FailoverClient (5m→10m→20m→40m→1h backoff), OpenAI/Anthropic providers |
| nodus-delivery | nodus-channels | DeliveryPlan, SizeChunker, ParagraphChunker, MarkdownBlockChunker, DeliveryRouter |

## Group 3 — Tier 1: Buildable standalone (7 packages)

| Package | Key deps | Key abstraction |
|---------|----------|----------------|
| nodus-retry | none | RetryPolicy (6 named), execute_with_retry sync+async, EffectStore/InMemoryEffectStore, compute_action_id() |
| nodus-http | httpx, nodus-circuit-breaker | HttpClient (circuit breaker + retry + trace headers), HttpResponse, RetryConfig; **requires `respx` for tests** |
| nodus-events | redis (optional) | EventBus (Redis pub/sub, source-instance dedup, pre-rehydration buffer), AuditStore, publish_event() |
| nodus-schema | none | validate_payload(), parse_versioned_name(), resolve_version(), SchemaRegistry, SchemaEntry |
| nodus-protocol | none | RequestEnvelope, ResponseEnvelope, EventEnvelope, JSON encode()/decode() with _type discriminator |
| nodus-session | none | SessionEntry (transcript, provenance), InMemorySessionStore, SessionPruningPolicy, SessionManager |
| nodus-router | none | RouteBinding (fnmatch), RoutingTable (priority-sorted), RouteResolver (default agent fallback) |

## Group 4 — Tier 2: Requires Tier 1 (4 packages + 1 additive)

| Package | Key deps | Key abstraction |
|---------|----------|----------------|
| nodus-memory | nodus-events; pgvector/openai optional | MemoryNode, InMemoryStore, MAS build_path()/glob_match(), score_nodes(), update_feedback(), recall()/recall_async(), EmbeddingProvider |
| nodus-workflow | nodus-state, nodus-events | FlowDefinition/FlowNode/FlowEdge, FlowStatus/FlowRun, SchedulerEngine (priority queue + WAIT/RESUME), FlowExecutor, FlowRehydrator |
| nodus-a2a | none | AgentRegistry, AgentCoordinator (local/delegate), DelegationRequest, DeadLetterService, StuckRunWatchdog |
| nodus-adapter-base (repo: `nodus-adapters/base/`) | nodus-channels | BaseChannelAdapter (reconnect backoff, health recording), ConnectionManager; path: `C:\dev\nodus-adapters\base` |

## Group 5 — Tier 3: Requires T1+T2 (2 packages)

| Package | Key deps | Key abstraction |
|---------|----------|----------------|
| nodus-agent | nodus-state, nodus-retry | AgentRun, CapabilityToken (HMAC-SHA256), mint_token()/validate_token(), LocalPlanner/LLMPlanner, DuplicateSubmissionGuard, AgentExecutor |
| nodus-gateway | nodus-protocol, websockets | GatewayServer (WebSocket + handler dispatch + idempotency cache), GatewayClient, HandlerRegistry, EventBroadcaster; **requires nodus-protocol installed** |

## Group 6 — Tier 4: Requires All (2 packages)

| Package | Key deps | Key abstraction |
|---------|----------|----------------|
| nodus-extensions | none | ExtensionManifest (ABI versioning), HookRunner (phase hooks), SubprocessSandboxRunner/OciSandboxRunner, ExtensionRegistry (disk discovery); **asyncio.run() not get_event_loop()** |
| nodus-governance | none | OperatorScope/ScopeBundle (PERM_* constants), PolicyBundle, TrustSurface (deny-by-default allowlist/blocklist), AuditTrail (append-only, multi-field query) |

## Group 7 — nodus-lang companion packages

| Package | Key deps | Key abstraction |
|---------|----------|----------------|
| nodus-extension | nodus-lang | Typed, versioned, sandboxed plugin framework; `ExtensionRegistry`, `ExtensionHost`, `attach_to_runtime()`; subprocess sandbox (tier: insecure-dev), OCI sandbox (tier: container); `_ext_*` host functions wired to nodus builtins; **ext_invoke takes JSON string args** |
| nodus-native-memory-engine | maturin/PyO3 (Rust) | Cosine similarity, blended ranking, cycle detection; `is_native()` → True when Rust .pyd loaded; pure-Python fallback for all ops |
| nodus-store-sql | sqlalchemy, aiosqlite (optional) | `RunStore` (optimistic locking), `EventStore` (append-only), `JobStore` (atomic claiming); `AsyncSqlStore`; tables: `nodus_runs/events/jobs`; **aiosqlite needed for async tests** |
| nodus-sdk | nodus-lang + 9 bridge deps | `NodusSDKRuntime`, `create_runtime()`, `detect_available()`; 9 bridges: redis/http/llm/observability/sql/vector/scheduler/webhook/api; `create_nodus_router(rt)` FastAPI router; bridge host functions return **maps** (use `r["key"]` not `r.key`) |
| nodus-mcp | nodus-lang, mcp>=1.0.0 | Full MCP protocol library (Phase A–N) at `src/nodus_mcp/`; aindy-derived bridge adapter at `nodus_mcp_aindy/`; `McpServer.dispatch()` never raises; tool names must be dotted |
| nodus-mcp-server | nodus-lang, nodus-mcp | Standalone MCP server process; 6 tools; stdio (Claude Desktop) + HTTP/SSE (ChatGPT); `StreamableHTTPSessionManager` at `POST /mcp`; ngrok static domain; shared SQLite memory DB |
| nodus-jupyter | nodus-lang, ipykernel | Jupyter kernel for `.nd` files; cross-cell state via source accumulation; `python -m nodus_jupyter install` |

## Group 8 — Non-Python published artifacts

| Artifact | Distribution | Key details |
|----------|-------------|-------------|
| nodus-vscode | VS Code Marketplace (MasterplanInfiniteWeave) | Phase 1–4: grammar/snippets, diagnostics, run/fmt/DAP, LSP; `nodus.executablePath` setting; LSP uses installed nodus.exe (not dev source) |
| nodus-run-action | GitHub Actions (`Masterplanner25/nodus-run-action@v1`) | 3 modes: `file` / `test-path` / `fmt-check`; pin version with `version: '4.0.7'` |
