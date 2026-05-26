# Nodus v4.0 — Design Doc 01: HTTP API

**Phase:** 1 (design docs)
**Status:** Locked
**Implements:** Decision 5 (HTTP API Shape) from `00-phase-0-decisions.md`
**Date:** 2026-05-26
**Maintainer:** Shawn Knight (Masterplanner25)

---

## Problem statement

v4.0 ships an HTTP client as the first orchestration stdlib namespace.
Decision 5 (Phase 0) locked the high-level shape: sync default with async
opt-in, buffered default with streaming opt-in, rich err records with a
`category` field. This doc specifies the API surface in implementable
detail.

The HTTP client is foundational. It is the most-called stdlib namespace
in any orchestration workload. It is also the dependency for both
`nodus-mcp` (HTTP transport, Streamable HTTP transport) and `nodus-a2a`
(JSON-RPC binding, HTTP+JSON/REST binding). Design choices here shape
those libraries' implementations.

---

## What Phase 0 already settled

From Decision 5:

- Sync default with async opt-in (separate functions, not flags)
- Buffered default with streaming opt-in
- Function set: `http.get/post/put/delete/patch/head/options(url, options)`,
  `_async` variants, `http.stream(url, options)`, generic
  `http.request(method, url, options)`
- Response object: `status`, `headers`, `body`, `response.json()`
- Err shape: `kind: "http_error"`, payload with `status`, `url`, `method`,
  `category`, `body`
- Category values: `"network"`, `"timeout"`, `"client_error"`,
  `"server_error"`, `"decode_error"`

This doc resolves the remaining specification:

- Options object layout
- Response object full shape
- Stream response shape and channel semantics
- SSE function shape
- Network behavior (redirects, TLS, pooling, proxy, HTTP/2)
- Implementation substrate
- MCP/A2A consumer validation

---

## API surface

### Function set

The full list of public functions in `std:http`:

```
http.get(url, options?)
http.post(url, options?)
http.put(url, options?)
http.delete(url, options?)
http.patch(url, options?)
http.head(url, options?)
http.options(url, options?)
http.request(method, url, options?)

http.get_async(url, options?)
http.post_async(url, options?)
http.put_async(url, options?)
http.delete_async(url, options?)
http.patch_async(url, options?)
http.head_async(url, options?)
http.options_async(url, options?)
http.request_async(method, url, options?)

http.stream(url, options?)
http.sse(url, options?)
```

19 functions total. The `_async` variants return coroutines per Nodus's
existing coroutine system; sync variants block.

`http.stream` and `http.sse` are streaming-only (no `_async` variant
needed; channel-based streaming is inherently async-friendly per Nodus's
runtime model).

### Options object — flat layout

The options object is a flat map. Keys are organized below by concern,
but all live at the top level of the map.

**Body keys (mutually exclusive; using more than one is a parse error):**

| Key | Type | Behavior |
|---|---|---|
| `json` | map or list | Body is `json.serialize(value)`; sets `Content-Type: application/json` (unless overridden in `headers`) |
| `form` | map of string-to-string | Body is `application/x-www-form-urlencoded` |
| `multipart` | map of string-to-value | Body is `multipart/form-data`; values may be strings, bytes, or `{filename, data, content_type}` records for file uploads |
| `bytes` | bytes | Body is raw bytes; no `Content-Type` set unless in `headers` |
| `text` | string | Body is raw text (UTF-8 encoded); no `Content-Type` set unless in `headers` |

Specifying any body key on a method that doesn't accept a body (`get`,
`head`, `options`, `delete` per RFC 7231 conventions) produces an err
record with `category: "client_error"` and message indicating the method
does not accept a body. (Note: some servers do accept bodies on these
methods. The library is conservative; users who need it can use
`http.request` with method explicitly specified.)

**Header and query keys:**

| Key | Type | Behavior |
|---|---|---|
| `headers` | map of string-to-string | Request headers; case-insensitive lookup normalized internally |
| `query` | map of string-to-string-or-list | URL query parameters; lists serialize as repeated keys (`?tag=a&tag=b`) |

**Authentication shortcuts** (sugar for common header patterns):

| Key | Type | Behavior |
|---|---|---|
| `auth_bearer` | string | Sets `Authorization: Bearer <value>` |
| `auth_basic` | record `{username, password}` | Sets `Authorization: Basic <base64>` |

Using `auth_bearer` or `auth_basic` together with an explicit
`Authorization` header in `headers` produces an err record.

**Network keys:**

| Key | Type | Default | Behavior |
|---|---|---|---|
| `timeout_ms` | int | (unlimited) | Total request timeout in milliseconds; err with `category: "timeout"` on exceeded |
| `connect_timeout_ms` | int | (timeout_ms or 30000) | Connection establishment timeout |
| `read_timeout_ms` | int | (timeout_ms or unlimited) | Read timeout between bytes |
| `follow_redirects` | bool | `true` | Follow 3xx redirects; cross-host strips auth headers |
| `max_redirects` | int | `10` | Redirect limit; err with `category: "redirect_error"` on exceeded |
| `verify_tls` | bool or string | `true` | `true` for system CAs, `false` to disable, string path to custom CA bundle |
| `proxy` | string | (env-driven) | Explicit proxy URL (e.g., `"http://proxy.local:8080"`); overrides `HTTP_PROXY`/`HTTPS_PROXY` env vars |

### Response object

Returned by `http.get`, `http.post`, ..., `http.request` (and async
variants once their coroutine resolves):

| Field | Type | Description |
|---|---|---|
| `status` | int | HTTP status code (e.g., 200, 404, 500) |
| `headers` | map of string-to-list-of-string | Response headers; all values are lists (even single-value); case-insensitive lookup |
| `body` | string or bytes | Body decoded to string for text-like Content-Type; bytes otherwise |
| `url` | string | Final URL after redirect following |
| `method` | string | HTTP method used (relevant for `http.request`) |

**Method properties:**

| Property | Type | Description |
|---|---|---|
| `r.ok` | bool | `true` for 2xx status codes |
| `r.is_redirect` | bool | `true` for 3xx status codes (only set if `follow_redirects: false`; otherwise final redirected response is what's returned) |
| `r.is_client_error` | bool | `true` for 4xx |
| `r.is_server_error` | bool | `true` for 5xx |

**Methods:**

| Method | Returns | Description |
|---|---|---|
| `r.json()` | parsed value or err record | Parse `r.body` as JSON; returns err on parse failure (`kind: "http_error"`, `category: "decode_error"`) |
| `r.header(name)` | string or nil | First value of header `name` (case-insensitive); nil if absent |
| `r.headers_all(name)` | list of string or nil | All values of header `name`; nil if absent (use this when expecting multi-value headers like `Set-Cookie`) |

### Stream response

Returned by `http.stream`:

| Field | Type | Description |
|---|---|---|
| `status` | int | HTTP status code |
| `headers` | map of string-to-list-of-string | Response headers (immediately available) |
| `url` | string | Final URL after redirect following |
| `method` | string | HTTP method used |
| `chunks` | channel | Channel yielding bytes or string chunks per Content-Type |

**Properties:** `r.ok`, `r.is_redirect`, `r.is_client_error`,
`r.is_server_error` — same semantics as buffered response.

**Methods:**

| Method | Returns | Description |
|---|---|---|
| `r.header(name)` | string or nil | First value of header `name` |
| `r.headers_all(name)` | list of string or nil | All values of header `name` |
| `r.as_sse()` | channel of event records | Convert chunks channel to SSE event channel; for Content-Type-negotiated streaming patterns like MCP's Streamable HTTP transport |
| `r.close()` | nil | Close the connection immediately; discards any buffered chunks not yet read |

**Channel chunk semantics:**

- Chunks are bytes if Content-Type is binary, strings if text-like
  (same rules as buffered response body)
- For text decoding: UTF-8 boundary buffering is handled internally;
  no chunk yielded mid-character
- Chunks are arbitrary boundaries: a streamed text response may split
  lines, words, or messages mid-chunk
- No line/message splitting is done by `http.stream`; consumers compose
  that via channel transformation
- Connection auto-closes when channel is fully consumed
- Explicit `r.close()` closes connection immediately, discards buffered

**Mid-stream errors:**

If the stream fails before completion (network drop, chunk-encoding
error, etc.), the channel emits exactly one err record as its final
value, then closes. The err record has the standard shape:

```
err {
    kind: "http_error",
    payload: {
        status: ...,           # status from the original response
        url: ...,
        method: ...,
        category: ...,         # "network" or "decode_error"
        body: ...,             # any buffered partial body, up to 64KB
        body_truncated: ...,   # bool
        bytes_received: ...    # int; how much was received before failure
    }
}
```

Consumer pattern:

```nodus
let r = http.stream(url)
if !r.ok { return error_path(r) }
for chunk in r.chunks {
    if type(chunk) == "error" {
        // mid-stream failure
        return partial_path(chunk)
    }
    process(chunk)
}
// Channel closed; stream complete
```

### SSE response

Returned by `http.sse`:

| Field | Type | Description |
|---|---|---|
| `status` | int | HTTP status code |
| `headers` | map of string-to-list-of-string | Response headers |
| `url` | string | Final URL after redirect following |
| `events` | channel of event records | Channel yielding SSE event records |
| `last_event_id` | string | Last event id seen (updates as events arrive; useful for resumption via `Last-Event-ID` header on reconnect) |

**Properties:** `r.ok`, `r.is_redirect`, `r.is_client_error`,
`r.is_server_error` — same semantics.

**Methods:** `r.header(name)`, `r.headers_all(name)`, `r.close()` —
same semantics as stream response.

**Event record shape:**

```
{
    event: string,    # event type (default "message" if not specified)
    data: string,     # event data (multi-line data: lines concatenated with \n)
    id: string,       # event id, if specified by server
    retry: int        # reconnect delay in ms, if specified by server
}
```

Fields not provided by the server are absent from the record (Nodus
records support optional fields).

**Auto-reconnect:** NOT supported in v0.1. The `retry:` directive value
is exposed via the `retry` field on events; consumers handle reconnect
by checking the channel for close, reading `r.last_event_id`, and
calling `http.sse` again with the `Last-Event-ID` header set. v4.x may
add `std:sse` helper functions or workflow patterns for reconnection.

This is per the capabilities-not-orchestration principle: connection
management and retry are workflow concerns, not capability options. See
`LANGUAGE_VISION.md` principle #6 and `STYLE_GUIDE.md` § "Retry,
backoff, and recovery".

---

## Err record shape

All `std:http` errors return err records with this shape:

```
err {
    kind: "http_error",
    message: string,    # human-readable description
    path: ...,          # standard err record location field
    line: ...,
    column: ...,
    stack: ...,
    payload: {
        status: int or nil,         # HTTP status if available; nil for pre-response errors
        url: string,                # the URL requested
        method: string,             # HTTP method
        category: string,           # see category enumeration below
        body: string or bytes or nil, # response body if available
        body_truncated: bool,       # true if body was truncated to 64KB
        bytes_received: int or nil  # for streaming errors; how much was received
    }
}
```

**Category enumeration (six values):**

| Category | When emitted |
|---|---|
| `"network"` | Connection refused, connection reset, DNS resolution failure, TLS handshake failure |
| `"timeout"` | `timeout_ms`, `connect_timeout_ms`, or `read_timeout_ms` exceeded |
| `"client_error"` | (Only emitted if user opts into status-as-error; see below) |
| `"server_error"` | (Only emitted if user opts into status-as-error; see below) |
| `"decode_error"` | Body could not be decoded per Content-Type charset; `r.json()` parse failure |
| `"redirect_error"` | `max_redirects` exceeded or redirect loop detected |

**Note on `"client_error"` and `"server_error"`:** By default, `std:http`
does NOT return err records for non-2xx HTTP statuses. The response is
returned with `r.ok = false`; the consumer branches on status. These two
categories exist for consumer libraries (like `nodus-mcp` and
`nodus-a2a`) that wrap `std:http` calls and convert non-2xx responses
into err records of their own. They also exist for users who explicitly
opt into status-as-error via wrapping their own helper.

**Body truncation:** When an err record includes a body, it is truncated
to 64KB. The `body_truncated` flag indicates whether truncation occurred.
This applies to both response-body inclusion (when status-as-error is
opted into) and streaming-mid-failure partial bodies.

---

## Network behavior

### Redirect handling

- Follow redirects by default (`follow_redirects: true`)
- Maximum 10 redirects (`max_redirects: 10`)
- Exceeding maximum emits err with `category: "redirect_error"`
- Redirect loop detection emits err with `category: "redirect_error"`
- **Cross-host redirects strip auth headers.** If the original request
  has `Authorization` or `Cookie` headers, and the redirect goes to a
  different host, those headers are NOT sent to the new host. This is
  the standard behavior in modern HTTP libraries (curl, httpx, requests)
  and prevents credential leakage.
- **301/302/303 → GET.** Per RFC 7231, these status codes historically
  cause method change to GET. The body is dropped on redirect.
- **307/308 → preserve method.** Per RFC 7538, these preserve the
  original method and body.

To get the 3xx response without following, set `follow_redirects: false`.
The response is returned with `r.is_redirect == true`; `r.headers["location"]`
contains the redirect target.

### TLS verification

- Verify by default (`verify_tls: true`), using system CA bundle
- Set `verify_tls: false` to disable verification (for self-signed
  development servers); not recommended in production
- Set `verify_tls: "/path/to/ca-bundle.pem"` to verify against a custom
  CA bundle (for corporate environments with internal CAs)

### Connection pooling

- Transparent. The library maintains an internal connection pool that
  reuses connections to the same host across requests within the same
  VM instance.
- No user-facing pool configuration. The substrate (httpx) handles
  pool sizing and keep-alive timeouts with sensible defaults.

### Proxy support

- Env-driven by default: `HTTP_PROXY`, `HTTPS_PROXY`, `NO_PROXY`
  environment variables are read at request time.
- Explicit `proxy` option overrides env vars. Format:
  `"http://proxy.host:port"` or `"http://user:pass@proxy.host:port"`.

### HTTP/2

- Auto-negotiated if the `h2` Python package is installed (via the
  `http2` optional extras on `nodus-lang`).
- Falls back to HTTP/1.1 transparently if `h2` is not installed.
- No user-facing configuration.

---

## Migration impact

`std:http` is a new namespace in v4.0. No migration is required from
v3.x — there was no `std:http` before. Existing v3.x code that used
Python via subprocess or the embedding API for HTTP continues to work;
migration to native `std:http` is opt-in.

---

## Implementation outline

### Substrate: httpx

`std:http` is implemented on top of httpx
(https://www.python-httpx.org/), version pinned to `>=0.27,<1`.

Reasoning (locked in cluster 6 of Phase 1 design):

1. Unified sync + async API matches Decision 5's sync/async function set
2. First-class streaming and SSE support
3. Connection pooling and keep-alive out of the box
4. HTTP/2 via optional `h2` package, transparent fallback
5. Active maintenance and Python ecosystem alignment
6. Compatible with MCP's HTTP/Streamable HTTP transports and A2A's
   HTTP+JSON binding

**The httpx substrate is fully hidden from users.** Nodus has its own
response shape, its own err records, its own option names. No `r.raw`,
no `http.raw_client()`. If `std:http` does not expose what a user
needs, the workaround is the embedding API (call httpx directly from
Python host code, pass results to Nodus).

This insulates Nodus from substrate evolution and keeps `std:http` an
orchestration-DSL surface, not a Python HTTP library wrapper.

### pyproject.toml dependencies

```
[project]
dependencies = ["httpx>=0.27,<1"]

[project.optional-dependencies]
http2 = ["h2>=4,<5"]
```

Install size impact: httpx (~600KB) is a hard dependency. `h2` adds
~500KB when installed via `nodus-lang[http2]` extras.

### Async bridging

Decision 5 locked `_async` variants returning coroutines. Implementation
direction: **true async via asyncio bridge.**

Nodus's coroutine primitive in the VM bridges to asyncio. When a script
calls `http.get_async(url)`, the Nodus runtime suspends the calling
coroutine, schedules an `httpx.AsyncClient.get(url)` call on its
internal asyncio loop, and resumes the Nodus coroutine when the result
is ready.

This means: a workflow that fans out to 100 HTTP endpoints in parallel
uses one OS thread with async I/O, not 100 thread-pool workers. The
performance characteristic matches the orchestration DSL's expected
workload.

**Open implementation questions for Phase 3B (see "Open implementation
questions" section below):**

- One asyncio loop per VM instance, or shared global loop?
- Thread-safety contract between Nodus VM and asyncio loop
- Cleanup semantics for in-flight async HTTP calls when the VM shuts
  down

These are implementation specifics; the interface (Decision 5: async
variants exist) is locked.

### Header normalization

Request-side: user provides headers as a case-sensitive map (Question 3a
locked this). Library normalizes to lowercase (or whatever wire format)
internally before sending. Provides:

```
http.get(url, {headers: {"Content-Type": "application/json"}})
http.get(url, {headers: {"content-type": "application/json"}})
http.get(url, {headers: {"CONTENT-TYPE": "application/json"}})
```

All three produce the same wire-level request.

Response-side: server may send headers in any casing. Library normalizes
to lowercase for internal storage. `r.headers["Content-Type"]`,
`r.headers["content-type"]`, and `r.header("Content-Type")` all return
the same value.

### Multi-value header storage

All response headers stored as lists of strings, even for single-value
headers:

```nodus
r.headers["content-type"]  // ["application/json"]
r.headers["set-cookie"]     // ["a=1; HttpOnly", "b=2; Secure"]
```

The `r.header(name)` helper returns the first value as a string for the
common single-value case:

```nodus
r.header("content-type")    // "application/json"
r.header("set-cookie")       // "a=1; HttpOnly" (loses b=2; use r.headers_all)
```

The `r.headers_all(name)` helper returns the full list:

```nodus
r.headers_all("set-cookie") // ["a=1; HttpOnly", "b=2; Secure"]
```

### Body decoding

Smart decode per Content-Type:

- Text-like Content-Type → decode to string using charset (default UTF-8)
- Binary Content-Type → bytes
- Missing Content-Type → bytes
- Charset specified in Content-Type used; falls back to UTF-8 if unknown

Text-like Content-Types include: `text/*`, `application/json`,
`application/xml`, `application/javascript`, `application/x-www-form-urlencoded`,
`application/xhtml+xml`. The complete list is maintained in the
implementation; users who need to override decoding should use
`r.body` as bytes (cast or check the type) and decode manually.

Decoding failures emit err records with `category: "decode_error"`. The
err includes the partial-decoded body if available.

### SSE parsing

`http.sse` parses event streams per the W3C Server-Sent Events
specification:

- Events terminated by blank line (`\n\n`)
- Fields: `event:`, `data:`, `id:`, `retry:`
- Multiple `data:` lines within an event concatenate with `\n`
- Comments (`:` prefix) ignored
- Unknown fields ignored

`r.as_sse()` on a `http.stream` response provides the same parsing as a
transformation on the chunks channel, for cases like MCP's Streamable
HTTP transport where Content-Type negotiation determines whether the
response is SSE or buffered JSON.

---

## Open implementation questions for Phase 3B

These are implementation specifics that will be resolved during Phase 3B
execution. They do not affect the API surface.

1. **Asyncio loop strategy.** One loop per VM instance vs shared global
   loop. Tradeoff: isolation (per-VM) vs resource efficiency (global).
   Tentative direction: per-VM loop, with the loop started lazily on
   first `_async` call.

2. **Thread-safety between Nodus VM and asyncio loop.** The Nodus VM is
   single-threaded by default; asyncio runs in the same thread. Question:
   if a Nodus VM is embedded in a multi-threaded Python host, does the
   asyncio loop need protection? Tentative direction: document
   single-threaded usage as the supported model; multi-threaded embedding
   requires user-provided synchronization.

3. **Connection pool lifecycle.** When does the httpx Client get created
   and torn down? Lazy on first request? Per-VM lifetime? Shared across
   VMs? Tentative direction: lazy creation, per-VM lifetime, closed on
   VM shutdown.

4. **Channel implementation for streaming.** Does Nodus's existing
   channel primitive support cancellation that maps to httpx stream
   cancellation? If not, what's the bridge? Tentative direction: verify
   channel primitive supports the necessary lifecycle; if gaps, file as
   Phase 3B work item.

5. **Memory bounds on buffered responses.** A pathological server can
   send a multi-gigabyte body. Should `http.get` have an implicit max
   body size with explicit opt-out? Tentative direction: no implicit
   limit (matches httpx default); users who care set `timeout_ms` and
   use `http.stream` for large bodies.

6. **UTF-8 boundary buffering implementation.** httpx provides
   line-buffered iteration but not character-boundary-buffered iteration.
   The library must implement the boundary buffer for the chunks channel.
   Tentative direction: incremental decoder pattern (Python's
   `codecs.getincrementaldecoder`).

---

## Scope ceiling

`std:http` is deliberately narrow. The following are NOT included in
v4.0 and will not be added unless real demand surfaces with concrete
use cases:

### Explicitly out of scope

- **HTTP server functionality.** `std:http` is a client. The case for
  an `std:server` namespace becomes concrete after `nodus-mcp` and
  `nodus-a2a` ship (both libraries bundle their own HTTP servers in
  v0.1). Captured as a v4.1 candidate in TECH_DEBT.md.

- **Built-in retry, backoff, circuit breaking, rate limiting.** Per the
  capabilities-not-orchestration principle, these are orchestration
  concerns that compose through workflow primitives. See:
  - `docs/language/LANGUAGE_VISION.md` principle #6
  - `docs/language/DESIGN.md` § "Capability surfaces stay narrow"
  - `docs/language/STYLE_GUIDE.md` § "Retry, backoff, and recovery"
  - `docs/governance/LIBRARY_ECOSYSTEM.md` § "Not pursued: per-call
    orchestration options in stdlib"

- **WebSocket support.** Different protocol semantics. Possibly v4.x or
  a `nodus-websocket` registry library if demand emerges.

- **Cookie jar / session management.** Users handle cookies manually
  via `headers["cookie"]` and reading `set-cookie` from responses.

- **OAuth flows beyond bearer tokens.** OAuth dance (authorization code
  flow, refresh tokens, PKCE) is multi-step and stateful; out of scope
  for a stateless capability function. `nodus-a2a` v0.2 will add OAuth2
  support for A2A's auth schemes; that may evolve into a `std:oauth`
  helper.

- **HTTP/3 / QUIC support.** Not in httpx's current scope. Re-evaluate
  if the substrate adds it.

- **Custom transports.** httpx supports custom transports; `std:http`
  does not expose this. Users with custom-transport needs use the
  embedding API.

- **Auto-reconnection for `http.sse`.** Per capabilities-not-orchestration:
  reconnection is workflow concern. v4.x may add helpers in
  `std:sse` namespace.

### Reconsideration triggers

`std:http` scope expands if:

- Real user issues file requests for a specific addition (10+ issues
  across distinct use cases for the same feature)
- A v4.0 library's implementation reveals a missing primitive that can
  only be cleanly provided by `std:http`
- The orchestration DSL identity changes (per LANGUAGE_VISION.md
  reconsideration triggers)

Until one of those fires, scope is locked.

---

## MCP and A2A consumer validation

The design was validated against both `nodus-mcp` v0.1 and `nodus-a2a`
v0.1 consumer requirements (Phase 1 design conversation, cluster 7).

### nodus-mcp consumer needs

- ✓ HTTP transport (POST + SSE response) handled by `http.post` +
  `http.sse`
- ✓ Streamable HTTP transport (Content-Type-negotiated) handled by
  `http.stream` + `r.as_sse()` for the SSE branch
- ✓ Bearer-token auth via `auth_bearer` option or `headers`
- ✓ Connection reuse via transparent pooling
- ✓ stdio transport handled by `std:subprocess` (not `std:http`'s concern)

### nodus-a2a consumer needs

- ✓ All HTTP verbs for REST binding (GET, POST, PUT, DELETE, PATCH)
- ✓ JSON-RPC binding via `http.post` with `json` body
- ✓ Streaming via `http.sse` for `POST /message:stream` and
  `POST /tasks/{id}:subscribe`
- ✓ Multipart bodies for file uploads via `multipart` body key
- ✓ Header-based authentication
- ⚠ Push notification webhook **reception** requires HTTP server
  functionality not in `std:http`. `nodus-a2a` v0.1 bundles its own
  HTTP server. Captured in TECH_DEBT.md as v4.1 candidate.
- ✓ gRPC binding uses `grpcio` directly in `nodus-a2a`, not via
  `std:http`

---

## Cross-references

- `docs/design/v4/00-phase-0-decisions.md` Decision 5 (HTTP API shape)
- `docs/design/v4/00-phase-0-decisions.md` Decision 16 (nodus-mcp v0.1)
- `docs/design/v4/00-phase-0-decisions.md` Decision 17 (nodus-a2a v0.1)
- `docs/governance/LIBRARY_ECOSYSTEM.md` (three-tier ecosystem,
  protocols-are-adapters)
- `docs/language/LANGUAGE_VISION.md` principle #6 (capabilities not
  orchestration)
- `docs/language/DESIGN.md` § "Capability surfaces stay narrow"
- `docs/language/STYLE_GUIDE.md` § "Retry, backoff, and recovery"
- `docs/governance/TECH_DEBT.md` § "Phase 4 deferred content:
  STDLIB_PHILOSOPHY.md" (canonical statement of capabilities-not-
  orchestration principle)
- `docs/governance/TECH_DEBT.md` § "v4.1 candidates: std:server" (to be
  added in this commit)

---

## Phase 3B implementation handoff

When Phase 3B begins (HTTP namespace implementation), the following
artifacts are ready:

1. This design doc (`01-http-api.md`)
2. Decision 5 (Phase 0)
3. Six open implementation questions enumerated above
4. Substrate locked: httpx with optional h2 extras
5. Test surface to cover (per the test framework decision):
   - All 19 public functions
   - All body shapes (json, form, multipart, bytes, text)
   - All six err categories
   - Redirect behavior (cross-host strip, method change rules)
   - TLS verification modes
   - Streaming chunk semantics and mid-stream errors
   - SSE parsing edge cases (multi-line data, retry directive, comments)
   - Async variants (basic correctness; full async test patterns in
     Phase 3C with test framework)

Estimated implementation effort: 2-3 days focused work for full coverage
including tests. Streaming and async edge cases are the most complex
pieces; basic verb implementations are straightforward httpx wrapping.

---

**Phase 1 doc 01-http-api.md: COMPLETE.**