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

**This is intentional, and was reaffirmed when embedded mode moved to
deny-by-default (#405).** CLI mode is a developer tool, equivalent to running a
Python script. Treat it with the same security assumptions as `python script.py`.
The threat model that motivates the embedded default — *hosting code you did not
author* — does not describe a developer running a script they just wrote, and the
two are separate code paths: `nodus run` never constructs a `NodusRuntime`.

The one control that applies in **both** modes is the capability floor: a Nodus
program cannot write into `.nodus/`, because a guest that can write there can
forge workflow run records.

**What CLI mode does protect against:**
- Relative import path traversal (cannot escape the project root)
- Bearer-token authentication for the HTTP server mode (if running server mode on
  non-local bindings)

**CLI vs. embedded code-path divergence (#192):**

The CLI (`nodus run`) and the HTTP server (`nodus serve`) execute scripts via
`tooling/runner.py`, which constructs VM instances directly — it does **not** go
through `NodusRuntime`. This creates an important split:

| | `NodusRuntime` | CLI / `nodus serve` |
|--|--|--|
| Default timeout | `None` (no deadline) | `EXECUTION_TIMEOUT_MS` = 200 ms |
| `allow_env` / `allow_subprocess` / `allow_network` flags | Honoured | Not wired — VM defaults apply |
| Error shape | Consistent `{ok, error, errors}` | Varies by call site |

Consequence: sandbox flags set on a `NodusRuntime` instance in tests or application
code do **not** apply when the same script is executed via the CLI. If your
security posture relies on `allow_env=False` or similar controls, enforce them
through `NodusRuntime` in your host application — never assume the CLI shares
that configuration. See GitHub #192 for the long-term unification plan (v5 scope).

---

## 4. Embedded mode security posture

**Threat level: Configurable, up to semi-untrusted code. Denies by default.**

`NodusRuntime` is designed for host applications that want to run Nodus scripts on
behalf of users or services.

> **Changed in #405.** `allow_subprocess`, `allow_network` and `allow_env` all
> default to **`False`**. A bare `NodusRuntime()` cannot shell out, open sockets,
> or read the environment. Previously all three defaulted to `True`, which is
> what audit 03 meant by *"the chokepoint is built; the door is propped open by
> registering subprocess and http by default."*
>
> Migration: [`docs/migration/v5.0-deny-by-default.md`](../migration/v5.0-deny-by-default.md).

The security controls available are:

| Control | Parameter | Default | Effect |
|---------|-----------|---------|--------|
| Filesystem restriction | `allowed_paths` | `[os.getcwd()]` | Restricts `read_file`, `write_file`, `append_file`, `mkdir`, `list_dir`, `exists` to listed directories |
| stdin block | `allow_input` | `False` | Blocks `input()` — cannot block on stdin in embedded mode |
| Subprocess | `allow_subprocess` | **`False`** | Denied unless granted (#405). Pass `True` to enable `subprocess_*` |
| Network | `allow_network` | **`False`** | Denied unless granted. Pass `True` to enable `http_*` |
| Env | `allow_env` | **`False`** | Denied unless granted. Pass `True` to enable `env_*` (read/write/delete of `os.environ`) |
| Per-call policy | `capability_policy` | `None` | Decides per call and can read the call's arguments — finer than the all-or-nothing flags above |
| Approval channel | `approval_channel` | `None` | Answers an `ask` decision. **With no channel, `ask` is `deny`** |
| Runtime-state floor | — | always on | Guest writes into `.nodus/` are refused; no policy can override it |
| Call stack cap | `max_frames` | `None` → `MAX_STACK_DEPTH` (10,000) | Deep recursion raises `Call stack overflow`; tighten to 200–1000 for untrusted code |
| Instruction limit | `max_steps` | `MAX_STEPS` (large) | Prevents infinite loops from running indefinitely |
| Wall-clock limit | `timeout_ms` | `None` (no deadline) | Prevents long-running scripts from blocking the host |

> **`max_frames` had no working default through v4.1.1**
> ([#350](https://github.com/Masterplanner25/Nodus/issues/350), fixed). A bare
> `NodusRuntime()` left `vm.max_frames` at `None`, so unbounded recursion grew the
> frame stack until the host stopped responding rather than raising
> `Call stack overflow`: `configure_vm_limits()` installed `MAX_STACK_DEPTH` and
> `embedding.py` overwrote it with `self.max_frames` on the next line. That
> assignment is now conditional, so `None` means the documented 10,000.
>
> The CLI was never affected. If you are pinned to v4.1.1 or earlier, pass
> `max_frames` explicitly — most of all in the configuration recommended for
> long-lived hosts (`timeout_ms=None, max_steps=None`, per #97), which removes the
> other two guards by design and so had no guard at all.

**Minimum recommended configuration for untrusted code:**
```python
runtime = NodusRuntime(
    max_steps=100_000,
    timeout_ms=5_000,
    allowed_paths=["/safe/directory"],
    allow_input=False,
    allow_subprocess=False,
    allow_network=False,
    allow_env=False,
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
  Disable via `allow_subprocess=False` on `NodusRuntime`. When enabled, the subprocess
  binary and its arguments are unrestricted — only `stdout`/`stderr` redirect paths and
  `cwd` are validated against `allowed_paths`. A script can run `subprocess_run(["cat",
  "/etc/passwd"])` regardless of `allowed_paths`. Prefer `allow_subprocess=False` for
  untrusted code.
- **Network access** — `std:http` (v4.0+) allows arbitrary outbound HTTP. Disable via
  `allow_network=False` on `NodusRuntime`. When enabled, there is no `allowed_hosts`
  restriction — scripts can reach any reachable host.
- **Environment variable access** — `std:env` (v4.0+) exposes full read/write/delete
  access to `os.environ`. Disable via `allow_env=False` on `NodusRuntime`. When enabled,
  a script can read any process-level environment variable including credentials
  (`AWS_SECRET_ACCESS_KEY`, `DATABASE_URL`, API tokens, etc.). Prefer `allow_env=False`
  for untrusted code running in environments with secrets in the process environment.
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

## 6b. Workflow store source persistence (#499)

Every workflow run persists **the whole program source, verbatim**, into
`.nodus/graphs/<graph_id>.json` — it is the rebuild handle that makes
cross-process resume work (`_rebuild_workflow_graph` recompiles it). The copy
is plaintext, lands in the CWD-relative `.nodus/` tree, and carries everything
the module carries: string literals (including any hardcoded secret), comments,
unrelated functions.

Controls:

- `nodus workflow cleanup` removes terminal runs older than 30 days by default
  (`NODUS_WORKFLOW_RETENTION_SECONDS` overrides; `=0` disables retention-based
  removal). Nothing prunes automatically — cleanup runs when invoked.
- An embedder running code it did not author can opt out per runtime:
  `NodusRuntime(persist_workflow_source=False)`. Resume then degrades as
  documented: a `run_file` run rebuilds from the file as it is on disk, and a
  `run_source` run is not resumable across processes.

**Asymmetry with the Floor, stated deliberately:** `DEFAULT_FLOOR` makes it
unbypassable that a Nodus *program* cannot write into `.nodus/` — while the
*runtime* writes that program's own source there on its behalf. The Floor's
rule protects the store's integrity from the guest; the persistence above is
the host-side runtime writing its own bookkeeping. They are different actors,
which is why this is not a contradiction — but a host that considers guest
source sensitive should treat the workflow store with the same care as the
source itself, or opt out.

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

## 11. CLI vs. embedded default divergence

The CLI (`nodus run`) and the embedding API (`NodusRuntime`) have different security defaults:

| Control | CLI (`nodus run`) | Embedded (`NodusRuntime()`) |
|---------|-------------------|-----------------------------|
| Filesystem | Restricted to project root / CWD automatically | Restricted to `[os.getcwd()]` by default |
| Wall-clock timeout | 200 ms (`EXECUTION_TIMEOUT_MS`) | None — no deadline |
| Subprocess | Available (no flag) | Available — set `allow_subprocess=False` to disable |
| Network | Available (no flag) | Available — set `allow_network=False` to disable |
| Env vars | Available (no flag) | Available — set `allow_env=False` to disable |

The critical difference: `timeout_ms` defaults to `None` in embedded mode (unlimited).
Scripts that call `http.get()` or `subprocess.run()` over a slow network or slow process
will block the host process indefinitely unless the embedder sets `timeout_ms` explicitly.
EMBED-001 (#97) is closed: `NodusRuntime()` now defaults to `timeout_ms=None` (fixed in v4.0.1).

The filesystem default changed from `None` (unrestricted) to `[os.getcwd()]` in v4.0.1
(security fix #119). An explicit `allowed_paths=None` still grants unrestricted access.

---

## 12. Multi-tenant isolation

**Process-level singletons are NOT isolated between `NodusRuntime` instances.**

Two scripts running in separate `NodusRuntime` instances in the same process share:

- `GLOBAL_MEMORY_STORE` — all `std:memory` reads/writes go to the same store.
  Script A writing `mem.put("secret", value)` is readable by Script B.
- `AGENT_REGISTRY` — agent registrations from one runtime are visible to all others.

`shutdown()` does not clear these stores.

**Consequence:** multi-tenant script execution (one runtime per user/request in the same
process) is not secure if scripts use `std:memory` or `std:agent`. Any tenant can read
or overwrite any other tenant's memory keys.

**Workaround:** avoid `std:memory` and `std:agent` in multi-tenant contexts, or run each
tenant's scripts in a separate OS process.

**Tracking issue:** DESIGN-005 (#155) — per-instance memory store parameter.

---

## Related documents

- `docs/runtime/EXECUTION_INVARIANTS.md` — sandbox invariants
- `docs/runtime/FAILURE_AND_DEGRADATION_MODEL.md` — how security violations surface
- `docs/runtime/EMBEDDING.md` — embedding API including sandbox parameters
- `docs/governance/TECH_DEBT.md` — open security-adjacent items
