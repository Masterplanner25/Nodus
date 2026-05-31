Build a compliance-style test matrix for nodus-mcp protocol and transport correctness
(Milestone 3). Goal: move nodus-mcp from "architecturally plausible" to "behaviorally
predictable" — every transport path has explicit edge-case coverage.

Prerequisites: nodus-mcp v0.1.0 is complete (Phases A-N, 361 tests passing).
This milestone adds a compliance layer ON TOP of the existing unit tests.

GitHub repo: C:\dev\nodus-mcp

## What this delivers

1. A compliance test matrix covering stdio + HTTP transports
2. Edge-case tests for protocol error handling
3. Golden message fixtures for representative protocol exchanges

## Implementation

### Step 1 — Compliance matrix for core operations

Create `tests/compliance/` directory in nodus-mcp.
One test class per operation, covering both transports where applicable.

Operations to cover:

| Operation | stdio | HTTP | Notes |
|-----------|-------|------|-------|
| initialize/server.discover | required | required | Capability negotiation |
| tools/list | required | required | Full tool enumeration |
| tools/call (success) | required | required | Normal invocation |
| tools/call (tool error) | required | required | Tool returns err record |
| tools/call (schema violation) | required | required | Invalid args |
| elicitation (MRTR loop) | required | stdio only | TD-007 suppresses in HTTP |
| resources/list | required | required | Phase D coverage |
| prompts/list | required | required | Phase E coverage |
| unknown method | required | required | → -32601 MethodNotFound |
| malformed JSON | required | required | → -32700 ParseError |
| invalid JSON-RPC structure | required | required | → -32600 InvalidRequest |
| missing required params | required | required | → -32602 InvalidParams |
| connection teardown | required | required | Clean shutdown |

```python
# tests/compliance/test_tools_call_compliance.py
class ToolsCallComplianceTests(unittest.TestCase):
    """Compliance: tools/call behavior across both transports."""

    def _run(self, transport_factory, source):
        # Factory pattern: test body is transport-agnostic
        ...

    def test_tools_call_success_stdio(self): ...
    def test_tools_call_success_http(self): ...
    def test_tools_call_unknown_tool(self): ...
    def test_tools_call_schema_violation_stdio(self): ...
    def test_tools_call_schema_violation_http(self): ...
```

### Step 2 — Edge case tests

Add to `tests/compliance/test_error_handling.py`:

- **Malformed JSON-RPC:** Send `{"jsonrpc": "2.0"}` (missing method/id) → expect -32600
- **Unknown method:** `{"method": "nonexistent/method"}` → expect -32601
- **Missing required params:** `tools/call` without `name` param → expect -32602
- **Oversized payload:** Tool arg exceeding a reasonable size limit → expect -32602 or server-defined limit
- **Concurrent requests (HTTP):** Two simultaneous `tools/call` requests → both succeed independently
- **Reconnect (HTTP):** Client reconnects after connection drop → new session, full discover
- **Server timeout (stdio):** No response within timeout → client raises cleanly
- **Transport interruption:** Kill server mid-response → client gets clean exception, not hang

### Step 3 — Golden message fixtures

Create `tests/compliance/fixtures/`:

```
initialize_request.json
initialize_response.json
tools_list_request.json
tools_list_response.json
tools_call_success_request.json
tools_call_success_response.json
tools_call_error_request.json
tools_call_error_response.json
elicitation_request.json
elicitation_response.json
```

Each fixture pair is a request/response that represents the canonical wire format.
Tests that use them verify: (a) the library produces output matching the golden fixture,
and (b) the library correctly parses the golden fixture as input.

### Step 4 — Transport-specific invariants

Add `tests/compliance/test_transport_invariants.py`:

- stdio: `server_initiated_capabilities` MUST be suppressed (TD-007 invariant)
- HTTP: Every response is `application/json` with `jsonrpc: "2.0"`
- Both: Error responses always have `error.code` as an integer and `error.message` as a string
- Both: `id` in error response matches `id` in request (or null if request was invalid)

## Exit criteria

- All operations in the compliance matrix have at least one passing test on each applicable transport
- All edge cases have tests
- Golden fixtures exist and are validated bidirectionally
- TD-007 (stdio-only server-initiated capabilities) is tested as a transport invariant

## Dev environment

```powershell
cd C:\dev\nodus-mcp
PYTHONPATH="C:/dev/Coding Language/src" `
  "C:/dev/Coding Language/.venv/Scripts/python.exe" `
  -m pytest tests/compliance/ -v
```
