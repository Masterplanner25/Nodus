Implement OAuth 2.0 + PKCE support for nodus-mcp v1.0. This is a new capability
addition targeted at v1.0 (not v0.1). Bearer token auth already ships in v0.1
and is preserved unchanged. OAuth adds the Authorization Code + PKCE flow,
client credentials flow, and token lifecycle management so nodus-mcp can connect
to production MCP servers that require OAuth (Anthropic hosted, GitHub Copilot,
OIDC-gated enterprise deployments).

Arguments: $ARGUMENTS
(Pass "phase1" to write the Phase 1 design doc, or a phase letter O1/O2/O3/O4
to implement that phase. If omitted, determine from context.)

## Pre-flight checks

Before touching any files:

1. Read `C:\dev\nodus-mcp\docs\design\00-decisions.md` — Decision 15 explicitly
   deferred OAuth to v0.2+. This skill targets v1.0; confirm the user intends
   to start v1.0 work before proceeding. If ambiguous, ask.
2. Read `C:\dev\nodus-mcp\src\nodus_mcp\http.py` — understand the existing
   `HttpTransport(url, bearer_token=...)` implementation that OAuth wraps.
3. Read `C:\dev\nodus-mcp\src\nodus_mcp\client.py` — understand `McpClient.connect()`
   signature so the OAuth path integrates cleanly.
4. Check tests pass:
   ```powershell
   cd C:\dev\nodus-mcp
   PYTHONPATH="C:/dev/Coding Language/src" `
     "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/ -q
   ```

## Phase O1 — Transport layer (OAuthTransport + token lifecycle)

Target: `src/nodus_mcp/oauth.py` + updates to `http.py`.

Deliverables:
- `OAuthTransport` class: wraps `HttpTransport`, handles token lifecycle
  transparently. Constructor: `OAuthTransport(url, *, client_id, client_secret=None,
  scopes=None, token_store=None)`
- `TokenStore` protocol: `get(issuer) -> Token | None`, `save(issuer, token)`.
  `InMemoryTokenStore` is the default implementation.
- `Token` dataclass: `access_token`, `token_type`, `expires_at`, `refresh_token`.
- Authorization Code + PKCE flow:
  - `generate_pkce_pair()` → `(code_verifier, code_challenge)` using S256
  - `build_auth_url(metadata, code_challenge, redirect_uri, state)` → str
  - `exchange_code(metadata, code, code_verifier, redirect_uri)` → `Token`
  - Automatic token refresh on 401 response (one retry)
- Client credentials flow (machine-to-machine, no user interaction):
  - `fetch_client_credentials_token(metadata, client_id, client_secret, scopes)` → `Token`
- All token endpoint calls use `httpx`; add `httpx` to dependencies if not already present.

Tests (mock OAuth server — no live service needed):
- PKCE pair is valid S256: `base64url(sha256(verifier)) == challenge`
- `build_auth_url` includes `code_challenge`, `code_challenge_method=S256`
- `exchange_code` posts correct body fields, returns `Token`
- `fetch_client_credentials_token` posts `grant_type=client_credentials`
- Token refresh triggered on 401, retried with new token, not retried again on second 401
- `InMemoryTokenStore` get/save round-trips correctly

## Phase O2 — Server discovery (OAuth metadata)

Target: `src/nodus_mcp/oauth.py` (add `OAuthServerMetadata` class).

Deliverables:
- `OAuthServerMetadata.discover(issuer_url)` → `OAuthServerMetadata`:
  - Fetches `{issuer_url}/.well-known/oauth-authorization-server` first
  - Falls back to `{issuer_url}/.well-known/openid-configuration` (OIDC compatibility)
  - Caches result per issuer URL (in-process, no TTL in v1.0)
  - Fields: `issuer`, `authorization_endpoint`, `token_endpoint`, `scopes_supported`
- `OAuthTransport` uses `discover()` automatically when `client_id` is provided but
  no explicit metadata is passed
- Explicit metadata path: `OAuthTransport(url, client_id=..., oauth_metadata=OAuthServerMetadata(...))`

Tests:
- `discover()` reads `authorization_server` metadata correctly
- `discover()` falls back to `openid-configuration` when AS endpoint 404s
- Caching: second call does not make a network request (mock `httpx`)
- `OAuthTransport` auto-discovers when only `client_id` provided

## Phase O3 — Client credentials integration + McpClient wiring

Target: updates to `client.py` and `http.py`.

Deliverables:
- `McpClient.connect()` accepts `oauth_transport: OAuthTransport` as an alternative
  to the current `transport` parameter. Bearer token path unchanged.
- For machine-to-machine scenarios: `OAuthTransport` in client_credentials mode
  fetches a token before the first `server/discover` call, injects it as a
  `Bearer` header. Transparent to the rest of the `McpClient` flow.
- Update `cli.py` to accept `--client-id` / `--client-secret` flags alongside
  the existing `--bearer-token` flag.

Tests:
- `McpClient.connect(oauth_transport=...)` makes `server/discover` with correct
  Authorization header populated by `OAuthTransport`
- CLI flag `--client-id` without `--bearer-token` uses client_credentials flow

## Phase O4 — Polish (README, invariant tests, CHANGELOG)

Target: docs, tests, CHANGELOG.

Deliverables:
- Update `README.md` OAuth warning section: change from "v0.1 does not support..."
  to a usage example showing both flows
- Update `test_invariants.py`: replace the "README must contain OAuth warning"
  assertion with "README documents both bearer and OAuth flows"
- `CHANGELOG.md`: add v1.0 section with OAuth entries
- Coverage: ensure Phase O1–O3 code is covered at ≥85%
- `docs/design/06-oauth.md`: brief design note documenting the PKCE choice,
  the two supported grant types, and the explicit deferral of dynamic client
  registration and DPoP to v2.0

## Key constraints

- Bearer token auth (`HttpTransport(url, bearer_token=...)`) is UNCHANGED.
  Existing v0.1 callers require zero migration.
- `OAuthTransport` is a NEW class — it does not inherit from `HttpTransport`,
  it wraps it. The public interface of `HttpTransport` does not change.
- No new mandatory dependencies. `httpx` is likely already present.
  `python-jose[cryptography]` is NOT required — token endpoint calls are plain
  HTTP; JWT validation is the server's concern, not the client's.
- PKCE must use S256 (SHA-256 challenge method). Plain is not implemented.
- Token storage is in-memory by default. Persistent storage is via the
  pluggable `TokenStore` protocol — no file I/O in the core library.
- Dynamic client registration (RFC 7591) is deferred to v2.0.
- DPoP (RFC 9449) is deferred to v2.0.

## Dev environment

```powershell
cd C:\dev\nodus-mcp
PYTHONPATH="C:/dev/Coding Language/src" `
  "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/ -q

# nodus-lang regression guard
cd "C:/dev/Coding Language"
PYTHONPATH="C:/dev/Coding Language/src" `
  "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/ -q `
  --ignore=tests/test_scheduler_fairness.py
```

Shared venv: `C:\dev\Coding Language\.venv`.

## Commit and push

```powershell
git commit -m @'
feat(oauth): <description>

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
'@
```

Push to `github.com/Masterplanner25/nodus-mcp` after each phase.
