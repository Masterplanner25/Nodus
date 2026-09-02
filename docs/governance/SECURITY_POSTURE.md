# Security Posture

**Last reviewed:** 2026-09-01, against 5.9.0
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
program cannot write into the runtime's own state, because a guest that can write
there can forge workflow run records.

**That protection follows relocated state as of #585, and did not before.** The
floor answered "is this the runtime's state?" by matching a literal `.nodus` path
segment, so the supported way to move the store —
`NODUS_WORKFLOW_STORE_ROOT`, and now `NODUS_RUN_STATE_ROOT` — also moved it out of
the floor's reach. Demonstrated rather than reasoned about: with that variable set,
a guest's `fs.write("../relocated/pwned.txt", "x")` landed in the live run store
while the identical write to the default location was denied. The floor now also
asks whether the path is inside a root the runtime is *currently* using
(`nodus/runtime/state_paths.py`), so **a new state directory that does not go
through that module is unprotected**.

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
| Runtime-state floor | — | always on | Guest writes into the runtime's state — `.nodus/`, **and wherever `NODUS_RUN_STATE_ROOT` points** (#585) — are refused; no policy can override it |
| Call stack cap | `max_frames` | `None` → `MAX_STACK_DEPTH` (10,000) | Deep recursion raises `Call stack overflow`; tighten to 200–1000 for untrusted code |
| Instruction limit | `max_steps` | `MAX_STEPS` (large) | Prevents infinite loops from running indefinitely |
| Memory limit | `max_memory_mb` | `None` (unbounded) | Aborts when the run has grown the process past the bound (#160). Bounds growth over time, not a single allocation — see §5 |
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
- **Memory exhaustion, in one direction only.** `max_memory_mb` (#160) bounds how
  much a run may grow the process, polled every 256 instructions against the OS's
  own RSS reading. It stops the case it was filed for — a script that grows a list
  in a loop — and it is **off by default**, like `max_steps` and `timeout_ms`.

  What it cannot do: polling bounds growth *over time*, not a **single**
  allocation. A program that asks for one enormous list gets it, and the check
  fires afterwards if the process survives. Only an OS-level limit (`ulimit -v`, a
  cgroup, a container memory cap) prevents that, and for untrusted code it remains
  the answer rather than something this replaces.

  Two more caveats before relying on it. It measures **process** RSS, so a host
  allocating concurrently on another thread is counted against the guest's budget.
  And it is refused at construction where the platform cannot be metered, rather
  than accepted and silently unenforced.
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

Both are **published on PyPI** — this section described them as "prepared"
(built but unpublished) until 2026-09-01. Do not write a version number here;
`tools/check_publish_drift.py` prints each companion's published version.

### nodus-mcp
- Bearer token only; no OAuth
- `requestState` is visible to the MCP client — never checkpoint secrets in sentinel state
- Server-initiated requests over HTTP are stdio-only (no push channel in HTTP)
- See `nodus-mcp/docs/governance/TECH_DEBT.md` for detailed TD items

### nodus-a2a
- Production deployments must configure a `token_validator`; dev mode accepts all requests
- No authentication without `token_validator` — do not expose to the internet without one
- HTTP+JSON only; no TLS in the stdlib HTTP server; use a reverse proxy for production

### Every other companion
The security-relevant contract a companion must meet is
`docs/governance/COMPANION_LIBRARY_CONTRACT.md`. Per-repo notes are in
`docs/ecosystem/COMPANION_REPOS.md`.

---

## 11. CLI vs. embedded default divergence

The CLI (`nodus run`) and the embedding API (`NodusRuntime`) have different security defaults:

| Control | CLI (`nodus run`) | Embedded (`NodusRuntime()`) |
|---------|-------------------|-----------------------------|
| Filesystem | Restricted to project root / CWD automatically | Restricted to `[os.getcwd()]` by default |
| Wall-clock timeout | **200 ms** (`EXECUTION_TIMEOUT_MS`), for the **whole program** | `None` — no deadline |
| Subprocess | Available (no flag) | **Denied** — pass `allow_subprocess=True` to enable |
| Network | Available (no flag) | **Denied** — pass `allow_network=True` to enable |
| Env vars | Available (no flag) | **Denied** — pass `allow_env=True` to enable |

The last three rows read *"Available — set `allow_subprocess=False` to disable"* until
2026-09-01, describing the pre-5.0.0 default. That is **the opposite of current
behaviour**, and it contradicted §4 of this same document, which has said `False`
since #405 shipped. Verified by construction, not by reading: a bare
`NodusRuntime()` reports `allow_subprocess`, `allow_network` and `allow_env` all
`False`. Any advice written against the old default — including "a bare runtime can
shell out" — is now backwards.

Two live differences remain:

- **`timeout_ms` is `None` in embedded mode**, so a script calling `http.get()` or
  `subprocess.run()` over a slow network blocks the host indefinitely unless the
  embedder sets it. That is deliberate (EMBED-001, #97: the old 200 ms default made
  `NodusRuntime` unusable for servers), and it is the embedder's job to bound.
- **The CLI's 200 ms budget bounds the whole program**, not just a coroutine —
  a plain counting loop dies the same way a sleeping one does, and an `import` is
  charged to it because the import compiles the module during the run. `--time-limit N`
  (in **seconds**) raises it. SCHED-001.

The divergence itself is a decision, not an oversight: the CLI builds a `VM` directly
and never constructs a `NodusRuntime`, and a test pins **both** halves so a later
reader does not "fix" the inconsistency. Deny-by-default protects against *hosting
code you did not author*; a developer running a script they just wrote is not that.

The filesystem default changed from `None` (unrestricted) to `[os.getcwd()]` in v4.0.1
(security fix #119). An explicit `allowed_paths=None` still grants unrestricted access.

---

## 12. Multi-tenant isolation

**Memory is isolated per `NodusRuntime` as of 5.0.3** (#185 / #390, closing
DESIGN-005 / #155). Two runtimes in one process no longer share a memory store —
verified by construction: `NodusRuntime()._memory_store is NodusRuntime()._memory_store`
is `False`.

| Surface | Isolated by default? | How to change it |
|---|---|---|
| `std:memory` store | **Yes**, per runtime | `share_process_state=True` restores the old process-global sharing; `memory_store=` injects a specific store |
| Agent registry | **No — deliberately** | `agent_registry=` scopes it per tenant |
| Workflow runner | No — process-global | `workflow_runner=` gives a runtime its own |

**A guest cannot register an agent**, which is why the registry is shared by
default. The only agent builtins are `agent_call` / `agent_available` /
`agent_describe`; registration is host-only from Python. So a shared registry
holds what the *host* put there, and isolating it by default would break
`register_agent(...)` → `run_source(...)` — it broke 11 tests when tried — to
prevent a leak guests cannot cause. Memory is the opposite: a guest script writes
it via `memory_put`, so a shared store was a channel between tenants.

**A bare `VM` and the CLI keep the process-global memory store**, single-tenant by
construction.

**What this section said until 2026-09-01:** that `GLOBAL_MEMORY_STORE` is shared,
that multi-tenant execution *"is not secure if scripts use `std:memory`"*, that the
workaround is a separate OS process per tenant, and that #155 was the open tracking
issue. #155 has been closed since 5.0.3. The advice was not merely stale — it told
an embedder to pay for process isolation it no longer needs, in the document they
would consult to decide.

---

## Related documents

- `docs/runtime/EXECUTION_INVARIANTS.md` — sandbox invariants
- `docs/runtime/FAILURE_AND_DEGRADATION_MODEL.md` — how security violations surface
- `docs/runtime/EMBEDDING.md` — embedding API including sandbox parameters
- `docs/governance/TECH_DEBT.md` — open security-adjacent items
