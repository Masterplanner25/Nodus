# `nodus-http`

> **Status:** v0.1.0 implemented and **published on PyPI** ✅ — `C:\dev\nodus-http`, 13 tests.
> This document is the original design spec; the implementation was built against it.

## Summary

`nodus-http` is a Python-first outbound HTTP library for AI-native runtimes.
Its public Python API is the canonical contract that a future thin Nodus
builtin will wrap. The library exists to eliminate repeated ad hoc wrapping of
`httpx` with retry, timeout, circuit breaker, trace propagation, and error
normalization.

V1 scope is a reusable core plus adapter seams, not a provider-specific SDK and
not a framework integration layer.

## Public Python API

The Python surface should be stable, typed, and builtin-friendly.

```python
client = NodusHttpClient(...)
response = client.request(request: HttpRequest, options: RequestOptions | None = None)
response = await client.arequest(request: HttpRequest, options: RequestOptions | None = None)
```

Required public types:

- `NodusHttpClient`
- `HttpRequest`
- `HttpResponse`
- `RequestOptions`
- `HttpCallMetadata`
- `CircuitBreaker` protocol
- `RetryExecutor` protocol
- `TracePropagator` protocol
- `HttpCallError`
- `HttpTimeoutError`
- `HttpCircuitOpenError`

## Public Model Contracts

### `HttpRequest`

Required fields:

- `method: str`
- `url: str`
- `headers: dict[str, str]`
- `query: dict[str, str | int | float | bool | None]`
- `json_body: object | None`
- `body: bytes | str | None`
- `timeout_seconds: float | None`
- `metadata: HttpCallMetadata | None`

Rules:

- exactly one of `json_body` or `body` may be set
- request objects are immutable after creation
- the client must not mutate caller-owned header or query dicts

### `HttpCallMetadata`

Required fields:

- `service_name: str`
- `operation_name: str`
- `endpoint_name: str | None`
- `trace_id: str | None`
- `correlation_id: str | None`
- `tags: dict[str, str]`

This metadata is used for trace propagation, circuit breaker labeling, retry
classification, and downstream observability hooks.

### `RequestOptions`

Required fields:

- `retry_executor: RetryExecutor | None`
- `circuit_breaker: CircuitBreaker | None`
- `trace_propagator: TracePropagator | None`
- `follow_redirects: bool | None`

`RequestOptions` configures per-call behavior without requiring env-driven
global state.

### `HttpResponse`

Required fields:

- `status_code: int`
- `headers: dict[str, str]`
- `body: bytes`
- `text: str`
- `json_value: object | None`
- `metadata: HttpCallMetadata | None`

Rules:

- response normalization happens once in the transport layer
- JSON decoding failure must not destroy access to raw body or text
- response objects should expose a helper for `is_success`

## Architecture

Split the library into three layers:

1. Pure request/response model layer
2. Pure orchestration layer
3. Transport adapter layer

### Pure model layer

Contains:

- request models
- response models
- metadata models
- exception types

No `httpx` imports are allowed here.

### Pure orchestration layer

Contains:

- request validation
- timeout resolution
- retry handoff
- circuit breaker preflight and post-call lifecycle
- trace propagation handoff
- error normalization

This layer can depend on public protocols but not on `httpx.Client` directly.

### Transport adapter layer

Contains:

- sync adapter over `httpx.Client`
- async adapter over `httpx.AsyncClient`
- conversion between `HttpRequest` and `httpx` call parameters
- conversion between `httpx.Response` and `HttpResponse`

This is the only layer that should depend directly on `httpx`.

## Backend Protocols

### `RetryExecutor`

Required sync method:

```python
execute(operation_name: str, metadata: HttpCallMetadata | None, fn: Callable[[], HttpResponse]) -> HttpResponse
```

Required async method:

```python
aexecute(operation_name: str, metadata: HttpCallMetadata | None, fn: Callable[[], Awaitable[HttpResponse]]) -> HttpResponse
```

The executor is responsible for retries. `nodus-http` decides whether to route
through it, but does not own retry policy logic.

### `CircuitBreaker`

Required methods:

- `before_call(operation_name: str, metadata: HttpCallMetadata | None) -> None`
- `after_success(operation_name: str, metadata: HttpCallMetadata | None) -> None`
- `after_failure(operation_name: str, error: Exception, metadata: HttpCallMetadata | None) -> None`

If `before_call` rejects the request, `nodus-http` raises
`HttpCircuitOpenError`.

### `TracePropagator`

Required method:

- `inject(headers: dict[str, str], metadata: HttpCallMetadata | None) -> dict[str, str]`

The propagator returns a new header map. It must not mutate shared caller
state.

## Behavior

- `request()` and `arequest()` are first-class APIs in v1.
- if a circuit breaker is configured, it is checked before any transport work
- if a trace propagator is configured, it runs before transport dispatch
- if a retry executor is configured, the actual transport call is wrapped by it
- if no retry executor is configured, the call runs exactly once
- transport exceptions are normalized into `HttpCallError` subclasses
- timeout errors normalize to `HttpTimeoutError`
- circuit-open rejection normalizes to `HttpCircuitOpenError`

The library must not:

- include provider-specific OpenAI or webhook client helpers
- require OpenTelemetry packages in core logic
- own retry policy declarations

## Package Dependencies

Required:

- `httpx`

Optional:

- `opentelemetry-api`
- `tenacity`

The core package should function without optional dependencies installed.

## Test Plan

Required tests:

- sync success path
- async success path
- JSON body request encoding
- raw body request encoding
- timeout normalization
- non-timeout transport exception normalization
- circuit breaker preflight rejection
- circuit breaker success callback
- circuit breaker failure callback
- retry executor sync integration
- retry executor async integration
- trace propagation header injection
- response JSON decode failure still preserves raw body and text

## Acceptance Criteria

- A future thin Nodus builtin can map one request object into one Python call
  with no hidden environment assumptions.
- All retry, breaker, and tracing behavior can be supplied through adapters.
- The pure model and orchestration layers can be imported without `httpx`
  clients being constructed.
