<!-- Authored by Codex during non coding session. Needs review before repo commit and push. -->

# Security Posture

**Version:** 3.0.2
**Status:** Governing document
**Maintainer:** Shawn Knight (Masterplanner25)

---

## 1. What this document is

This document describes the Nodus security model: what the runtime protects against,
what it explicitly does not protect against, and what configuration is required for
different threat levels. It is not a threat matrix — it is a posture statement.

---

## 2. Primary security surface

Nodus is used in two contexts:

1. **CLI mode** — a developer runs trusted scripts from a project directory
2. **Embedded mode** — a host application runs potentially-untrusted scripts via `NodusRuntime`

The threat model differs significantly between these contexts.

---

## 3. CLI mode security posture

**Threat level: Trusted code only.**

CLI mode (`nodus run script.nd`) assumes the script is trusted. No sandbox restrictions
are applied by default. The script can:
- Read and write any file accessible to the OS user running `nodus`
- Execute subprocesses (via `std:subprocess` when available)
- Make network calls (via `std:http` when available)
- Block indefinitely (no timeout by default)

**This is intentional.** CLI mode is a developer tool, equivalent to running a Python
script. Treat it with the same security assumptions as `python script.py`.

**What CLI mode does protect against:**
- Relative import path traversal (cannot escape the project root)
- Bearer-token authentication for the HTTP server mode (if running server mode on
  non-local bindings)

---

## 4. Embedded mode security posture

**Threat level: Configurable, up to semi-untrusted code.**

`NodusRuntime` is designed for host applications that want to run Nodus scripts on
behalf of users or services. The security controls available are:

| Control | Parameter | Default | Effect |
|---------|-----------|---------|--------|
| Filesystem restriction | `allowed_paths` | `None` (unrestricted) | Restricts `read_file`, `write_file`, `append_file`, `mkdir`, `list_dir`, `exists` to listed directories |
| stdin block | `allow_input` | `False` | Blocks `input()` — cannot block on stdin in embedded mode |
| Call stack cap | `max_frames` | `None` (uses `MAX_STACK_DEPTH`) | Prevents deep recursion from exhausting Python's stack |
| Instruction limit | `max_steps` | `MAX_STEPS` (large) | Prevents infinite loops from running indefinitely |
| Wall-clock limit | `timeout_ms` | `EXECUTION_TIMEOUT_MS` | Prevents long-running scripts from blocking the host |

**Minimum recommended configuration for untrusted code:**
```python
runtime = NodusRuntime(
    max_steps=100_000,
    timeout_ms=5_000,
    allowed_paths=["/safe/directory"],
    allow_input=False,
    max_frames=500,
)
```

---

## 5. What the sandbox does NOT protect against

The Nodus sandbox is not a full security sandbox. It does not protect against:

- **CPU exhaustion via tight computation** — `max_steps` limits instructions but not
  CPU time; a tight loop can consume significant CPU before the step limit fires.
  Use `timeout_ms` in addition to `max_steps`.
- **Memory exhaustion** — No limit on heap allocation. A script that builds a large
  list or map can exhaust host memory. No equivalent of `max_memory`.
- **Subprocess execution** — `std:subprocess` (v4.0+) allows arbitrary process execution.
  The process itself is not sandboxed (no `allow_subprocess` flag; if the stdlib is
  available, it is available). However, `stdout`/`stderr` file redirect paths and the
  `cwd` option are validated against `allowed_paths`/`fs_root` — a script cannot use
  subprocess redirection to write files outside the sandbox.
- **Network access** — `std:http` (v4.0+) allows arbitrary outbound HTTP. There is no
  `allowed_hosts` restriction in v3.0.2.
- **Information leakage via timing** — The scheduler does not provide timing isolation
  between coroutines.
- **Bytecode injection** — The runtime only loads `.nd` source files through the normal
  pipeline; it does not accept arbitrary bytecode from untrusted sources. However, the
  cache can be pre-populated by an attacker with write access to `.nodus/cache/` —
  the checksum would need to be valid. (Mitigation: use `project_root` pointing to a
  directory that untrusted code cannot write to.)

---

## 6. Bytecode cache security

The bytecode cache uses:
- `NDSC` magic header (4 bytes)
- Format version (1 byte)
- SHA-256 checksum (32 bytes) of the marshal payload
- `marshal` payload (not `pickle` — no arbitrary code execution risk)

The checksum is verified on load. A corrupt or tampered cache is silently discarded and
recompiled from source. The cache cannot be used to inject code — any tampered cache
fails the checksum and is rebuilt. The migration from `pickle` to `marshal` (Fix 14)
eliminated the pickle arbitrary-code-execution risk.

**Caveat:** If an attacker can write both the cache file and compute a valid SHA-256
of their forged payload, they can inject bytecode. This requires write access to the
project's `.nodus/cache/` directory. In practice: if an attacker controls the cache
directory, they also control the source directory, so source injection is equally possible.
The cache checksum protects against accidental corruption, not against a privileged attacker.

---

## 7. HTTP server mode security

Server mode (`nodus-lang[server]`, using FastAPI/Uvicorn) enforces bearer-token
authentication when binding to non-local addresses. The token is configured via the
host or environment. Local-only binding (127.0.0.1) does not require a token by default.

Server mode is experimental. Do not expose it to the public internet without a reverse
proxy that enforces TLS, rate limiting, and authentication.

---

## 8. Security fix policy

Security fixes that close sandbox bypasses are applied as patch releases regardless of
whether they change observable behavior. Scripts that relied on the bypass were relying
on a bug.

Example: `allowed_paths` enforcement (BUG-046, v2.1.1) was applied as a security patch.
The fix broke scripts that bypassed the sandbox, but those scripts were relying on a
vulnerability.

**Test rule:** Any security boundary fix must have tests covering both CLI mode and
`NodusRuntime` embedded mode. The enforcement code path differs between contexts.
See `docs/governance/TECH_DEBT.md §Security boundary test rule`.

---

## 9. Import path security

The module loader enforces project-root containment for relative imports. A script cannot
import files outside the project root via relative paths (`../`). This applies in:
- CLI mode (project mode and single-file mode)
- Embedded mode when `project_root` is set
- REPL mode

The containment check uses the resolved absolute path, not the string representation.
Symlinks that point outside the project root are currently resolved by the OS before
the check; the check sees the symlink target, not the symlink path. A symlink inside
the project root that points outside can be used to bypass containment. This is a known
limitation.

---

## 10. Companion library security notes

### nodus-mcp (v0.1.0, prepared)
- Bearer token only; no OAuth in v0.1
- `requestState` is visible to the MCP client — never checkpoint secrets in sentinel state
- Server-initiated requests over HTTP are stdio-only (no push channel in HTTP)
- See `nodus-mcp/docs/governance/TECH_DEBT.md` for detailed TD items

### nodus-a2a (v0.1.0, prepared)
- Production deployments must configure a `token_validator`; dev mode accepts all requests
- No authentication without `token_validator` — do not expose to the internet without one
- HTTP+JSON only; no TLS in the stdlib HTTP server; use a reverse proxy for production

---

## Related documents

- `docs/runtime/EXECUTION_INVARIANTS.md` — sandbox invariants
- `docs/runtime/FAILURE_AND_DEGRADATION_MODEL.md` — how security violations surface
- `docs/runtime/EMBEDDING.md` — embedding API including sandbox parameters
- `docs/governance/TECH_DEBT.md` — open security-adjacent items
