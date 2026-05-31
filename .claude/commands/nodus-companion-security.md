Document and test the security trust model for Nodus companion libraries (Milestone 4).
Goal: make trust assumptions explicit and transport-specific, tested, not just documented.

Applies primarily to nodus-mcp but the pattern should be reusable for any transport-based
companion library (nodus-a2a, future protocol adapters).

## What this delivers

1. A trust model document for companion library security
2. Tests for auth enforcement, tool exposure scope, and schema validation
3. Review of all paths where Python tools are surfaced into Nodus and vice versa

## Trust model document

Create `C:\dev\nodus-mcp\docs\design\07-security-trust-model.md`:

### Trust tiers

| Transport | Trust level | Auth default |
|-----------|-------------|-------------|
| stdio (local) | Trusted/local — same machine, same user | No auth required |
| HTTP (network) | Untrusted — explicit bearer token required | Mandatory if `bearer_token` is configured; dev-mode allow-all if no validator |

### What is enforced

- **stdio:** No network exposure. Only the local process can connect. Trust is the OS boundary.
- **HTTP (server):** `validate_auth(token, token_validator)` enforces bearer token on every request except `GET /.well-known/agent-card.json` (public discovery endpoint).
- **HTTP (client):** `HttpTransport(url, bearer_token=...)` sends the token on every request.

### What is NOT enforced (by design)

- No per-tool authorization. All tools are visible to any authenticated caller.
- No IP allowlist. Any network-accessible client that has a valid token can call tools.
- No rate limiting in v0.1. Denial-of-service mitigation is the embedder's responsibility.

### Tool exposure scope

- Only tools explicitly registered via `tool.register(...)` or `rt.tool_registry.register(...)` are surfaced.
- Tools from the host Python environment are NOT automatically surfaced.
- The tool list returned by `tools/list` is exactly the registered set — no more.

## Tests to add

Create `tests/test_mcp_security.py` in nodus-mcp:

### Auth enforcement tests

```python
def test_http_server_requires_bearer_token_when_configured():
    # Server configured with token_validator
    # Request without Authorization header → 401
    # Request with wrong token → 401
    # Request with correct token → 200

def test_http_server_dev_mode_allows_all_when_no_validator():
    # Server configured with token_validator=None
    # Request without Authorization header → 200 (dev mode)

def test_agent_card_endpoint_is_always_public():
    # GET /.well-known/agent-card.json never requires auth
    # Even with token_validator configured → 200

def test_stdio_transport_has_no_auth_requirement():
    # stdio connection succeeds without any token
```

### Tool exposure scope tests

```python
def test_tools_list_only_returns_registered_tools():
    # Register 2 tools, verify tools/list returns exactly 2
    # No builtin Nodus functions leak through

def test_unregistered_tool_call_returns_error():
    # tools/call with name of an unregistered tool → -32601 MethodNotFound

def test_tool_schema_validation_blocks_invalid_args():
    # Tool with required string param
    # tools/call with int arg → -32602 InvalidParams
    # tools/call with missing required param → -32602 InvalidParams
```

### Python↔Nodus tool crossing tests

```python
def test_python_tool_result_marshals_correctly():
    # Python tool returns dict → Nodus receives as map record
    # Python tool returns list → Nodus receives as list
    # Python tool returns None → Nodus receives nil

def test_python_tool_exception_becomes_nodus_error():
    # Python tool raises ValueError → Nodus receives err record
    # kind is "host_error"; message is the exception message
    # No Python traceback leaks to the Nodus caller
```

## Path review

For each path where Python tools are surfaced into Nodus (or vice versa):

1. `rt.tool_registry.register()` → `tool.call()` in Nodus script
   - Verify: only the registered tools are accessible
   - Verify: args are validated before handler is called

2. `tool.register()` in Nodus script → `rt.tool_registry.invoke()` from Python
   - Verify: Nodus-registered tools are accessible from Python via `invoke()`
   - Verify: they are NOT automatically surfaced to MCP clients (tool scope isolation)

3. `nodus-mcp` MCP client → `tools/call` → Python handler
   - Verify: bearer token is checked before any tool dispatch
   - Verify: invalid tool name returns -32601 before calling any handler

Document any gaps found during this review.

## Exit criteria

- Trust tiers documented with transport-specific guarantees
- Auth enforcement has explicit passing tests for both server and client paths
- Tool exposure scope is tested: only registered tools, no leakage
- Schema validation blocking invalid args is tested
- Path review is documented with findings

## Dev environment

```powershell
cd C:\dev\nodus-mcp
PYTHONPATH="C:/dev/Coding Language/src" `
  "C:/dev/Coding Language/.venv/Scripts/python.exe" `
  -m pytest tests/test_mcp_security.py -v
```
