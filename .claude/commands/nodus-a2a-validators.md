Add built-in auth validator implementations to nodus-a2a v1.0. The bearer token
enforcement infrastructure already exists (extract_bearer_token, validate_auth,
token_validator callable). This skill adds convenience validator classes so callers
don't have to implement validation themselves: HMACValidator, JWTValidator,
StaticTokenValidator, CompositeValidator.

Targets the ORIGINAL nodus-a2a wire protocol adapter (Phases A-J, 180 tests) at
github.com/Masterplanner25/nodus-a2a — NOT the local C:\dev\nodus-a2a which is
the Tier 2 AgentCoordinator replacement. Clone or work from the GitHub version.

Arguments: $ARGUMENTS
(Omit to run the full implementation. Pass "design" to write the design doc only.)

## Pre-flight checks

1. Determine which nodus-a2a is being worked on. The local C:\dev\nodus-a2a is
   the AgentCoordinator (no HTTP transport, validators don't apply). The target
   is the ORIGINAL A2A wire protocol adapter. Check whether it has been cloned
   locally; if not, ask the user where to work (clone from GitHub or temporary
   directory).
2. Confirm the existing bearer auth is working:
   - Read `transport.py` — find `extract_bearer_token`, `validate_auth`, and
     `token_validator: Callable[[str], bool] | None` in `ServerConfig`.
   - The existing code is the base; validators extend it without modifying it.
3. Run existing tests — confirm all pass before touching anything.

## Implementation — single phase

All work lives in one new file: `src/nodus_a2a/validators.py`.

### StaticTokenValidator

```python
class StaticTokenValidator:
    def __init__(self, token: str) -> None: ...
    def __call__(self, token: str) -> bool: ...
```

Equality check. Use case: single shared secret for dev/testing, or a single
long-lived API key. Already implicit in every test that does
`token_validator=lambda t: t == "secret"` — this gives it a name.

### HMACValidator

```python
class HMACValidator:
    def __init__(self, secret: str | bytes, algorithm: str = "sha256") -> None: ...
    def __call__(self, token: str) -> bool: ...
```

Verifies `HMAC-{algorithm}(secret, token) == token` using `hmac.compare_digest`.
Use case: internal mesh of agents that share a secret. No expiry — token is
the MAC itself, so callers must rotate secrets rather than expire tokens.
`algorithm` accepts any value accepted by `hmac.new` (sha256, sha512).

### JWTValidator

```python
class JWTValidator:
    def __init__(
        self,
        secret_or_key: str | bytes,
        algorithms: list[str] | None = None,
        audience: str | None = None,
        issuer: str | None = None,
        leeway: int = 0,
    ) -> None: ...
    def __call__(self, token: str) -> bool: ...
```

Validates a signed JWT. Delegates to `python-jose`; returns `False` on any
`JWTError` (expired, bad sig, wrong audience, etc.).
`algorithms` defaults to `["HS256"]`.
`leeway` is in seconds (clock-skew tolerance).

Add `python-jose[cryptography]` as an OPTIONAL dependency under
`[project.optional-dependencies]` with key `jwt`:
```toml
[project.optional-dependencies]
jwt = ["python-jose[cryptography]>=3.3"]
```

Import guard in `validators.py` — if `jose` is not installed and
`JWTValidator` is imported, raise `ImportError` with a clear message:
`"JWTValidator requires python-jose: pip install nodus-a2a[jwt]"`.

### CompositeValidator

```python
class CompositeValidator:
    def __init__(self, *validators: Callable[[str], bool]) -> None: ...
    def __call__(self, token: str) -> bool: ...
```

OR logic: passes if ANY validator accepts the token. Use case: migrating from
one key to another (accept both the old and new key during rollover).

### Exports

Add to `src/nodus_a2a/__init__.py`:
```python
from .validators import (
    StaticTokenValidator,
    HMACValidator,
    JWTValidator,
    CompositeValidator,
)
```

### Tests

Add `tests/test_validators.py` with:
- `StaticTokenValidator`: correct token passes, wrong token rejects
- `HMACValidator`: correct MAC passes, tampered token rejects, sha512 variant works
- `HMACValidator`: uses `hmac.compare_digest` (timing-safe, not `==`)
- `JWTValidator` (HS256): valid token passes, expired token rejects,
  wrong audience rejects, bad signature rejects
- `JWTValidator` import error when jose not installed (mock the import)
- `CompositeValidator`: passes if first accepts, passes if second accepts,
  rejects if none accept
- End-to-end: `A2AServer(config=ServerConfig(token_validator=HMACValidator("secret")))` +
  request with correct HMAC token returns 200, request with wrong token returns 401

### README update

Add a "Validator reference" section under the existing auth section showing
all four types with one-line examples. Point to `nodus-a2a[jwt]` for JWT.

## Key constraints

- `validators.py` is pure stdlib except for `JWTValidator` which needs `jose`
- `hmac.compare_digest` is mandatory for `HMACValidator` (timing-safe)
- `JWTValidator` must NOT be imported at module level — guard with try/except
- `validate_auth()` in `transport.py` is NOT modified — validators are passed
  as the `token_validator` callable, same as before
- `StaticTokenValidator` uses `secrets.compare_digest` or `hmac.compare_digest`
  (NOT `==`) to prevent timing attacks even on static tokens
- No new mandatory dependencies at the package level

## Dev environment

```powershell
# Adjust path to wherever the original nodus-a2a is being worked on
cd <nodus-a2a-original-path>
"C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/ -q
```

To install the JWT extra locally:
```powershell
"C:/dev/Coding Language/.venv/Scripts/python.exe" -m pip install python-jose[cryptography]
```

## Commit and push

```powershell
git commit -m @'
feat(validators): add HMACValidator, JWTValidator, StaticTokenValidator, CompositeValidator

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
'@
```

Push to `github.com/Masterplanner25/nodus-a2a`.
