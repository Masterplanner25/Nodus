# Nodus Security Matrix

**Last reviewed:** 2026-09-07, against 5.12.0
**Status:** Governing document
**Relates to:** [`SECURITY_POSTURE.md`](../governance/SECURITY_POSTURE.md) (policy
intent), [`TECH_DEBT.md`](../governance/TECH_DEBT.md) (known gaps),
[`EXECUTION_INVARIANTS.md`](../runtime/EXECUTION_INVARIANTS.md) (the `I-SAND-*`
invariants)

This matrix maps each security-relevant behaviour to the contexts where it is
enforced and the tests that cover it. A row with no test file is an open testing
gap — that is what the document is for.

> **Every row below was re-derived by running it, not carried forward.** The
> previous revision was stamped `Version: 4.1.1` and had gone wrong in the
> direction that costs a reader their model of the system: it stated that
> subprocess and network were **allowed and unsandboxed in every context**, which
> stopped being true for embedded runtimes at v5.0.0 (#405) and for `nodus serve`
> at v5.10.0 (#754). It also reported a memory limit and URL restriction as
> missing when both exist, and did not mention the capability policy, the Floor,
> `writable_paths`, or environment access at all. Do not edit a row here without
> running it.

---

## Ask the runtime, don't trust this table

A Nodus program can report its own capabilities, which is the authoritative
answer for a given configuration:

```
import "std:runtime" as rt
print(str(rt.capabilities()))
```

Under a bare `NodusRuntime()`:

```
{"agent.call": "allow", "env": "deny", "fs.read": "allow", "fs.write": "allow",
 "memory.read": "allow", "memory.write": "allow", "network": "deny",
 "subprocess": "deny", "syscall": "allow", "tool.invoke": "allow"}
```

Ten capabilities, and the map moves with the configuration — passing
`allow_network=True` flips `network` to `"allow"`. Covered by
`tests/test_runtime_capabilities.py`.

---

## Context key

| Symbol | Context |
|--------|---------|
| CLI | `nodus run script.nd` |
| EMB | `NodusRuntime` embedded in a Python host |
| SRV | `nodus serve` — code submitted to `POST /execute` |
| MOD | Module loader (`import "./path"`, or any `std:` module) |

**CLI is deliberately unconfined and that is a decision, not an oversight.** What
deny-by-default protects is work you did not fully author; a developer running a
script they just wrote is not that. The distinction is stated in the
`RuntimeService` constructor and pinned by test so a later reader does not "tidy
away" the inconsistency.

---

## The three enforcement layers

Reading any row below requires knowing which layer answers it.

| Layer | What it is | Bypassable |
|---|---|---|
| **Confinement flags** | `allow_subprocess`, `allow_network`, `allow_env`, `allowed_paths`, `writable_paths`, `allowed_commands`, `allowed_hosts` | by the host, at construction |
| **`CapabilityPolicy`** | optional, consulted at the two host chokepoints; three-valued `allow` / `ask` / `deny`. `ask` with no approval channel denies | by the host |
| **The Floor** (`DEFAULT_FLOOR`) | unbypassable. A policy that allows everything cannot override it | **no** |

The two chokepoints are `_invoke_host_function` (host functions) and
`VM.call_builtin` (builtins). A guard added to only one covers nothing that
matters — see the recurring-bug-shape section in `CLAUDE.md`.

The Floor's one rule today: a Nodus program cannot **write** into `.nodus/` —
the workflow store, graph state and bytecode cache. Verified with
`allowed_paths=None` (no jail at all) and over HTTP against a running server;
both refused with *"Blocked: writing to the runtime's own state directory is
never permitted"*. Reads are untouched.

### Constructor defaults, pinned

Every boolean switch on `NodusRuntime.__init__`, with the default the
constructor actually has:

| Parameter | Type | Default | What it gates |
|---|---|---|---|
| `allow_subprocess` | `bool` | **`False`** (#405) | `std:subprocess` |
| `allow_network` | `bool` | **`False`** (#405) | `std:http` and sockets |
| `allow_env` | `bool` | **`False`** (#405) | `std:env` reads and writes |
| `allow_input` | `bool` | **`False`** | reading stdin |
| `share_process_state` | `bool` | **`False`** (#185) | whether two runtimes in one process share the memory store |
| `persist_workflow_source` | `bool` | **`True`** (#499) | whether a workflow snapshot stores the program's source on disk |

`tests/test_documented_defaults_agree.py` reads this table and
`NodusRuntime.__init__` and compares them, so a reversal here fails the suite.
**This document was not registered in that test until 2026-09-07**, which is why
the reversal it was written to catch survived here longest: the guard existed,
covered `OPERATOR_OR_EMBEDDER_RUNBOOK.md` and `EMBEDDING.md`, and the security
matrix — the document where a reversed capability default matters most — was not
one of the two.

`share_process_state` and `persist_workflow_source` are in this table because
they are security decisions even though neither is named `allow_*`. A guest
script writes memory via `memory_put`, so a shared store is a channel between
tenants; and a persisted snapshot puts submitted source on disk where the
submitter cannot see who reads it.

---

## Filesystem access

| Behaviour | CLI | EMB | SRV | Test file |
|----------|:---:|:---:|:---:|-----------|
| Default jail | project root | **cwd** (`allowed_paths=[os.getcwd()]`) | ⛔ **none — [#843](https://github.com/Masterplanner25/Nodus/issues/843)** | `test_sandbox_filesystem.py` |
| `allowed_paths` restricts reads/writes | ✅ `--allow-paths` | ✅ | ✅ when passed | `test_cli_allowed_paths.py`, `test_sandbox_filesystem.py` |
| `writable_paths` splits read from write | n/a | ✅ | ✅ when passed | `test_path_scope.py` |
| Blocks `../` traversal out of the root | ✅ | ✅ | n/a (no root) | `test_path_traversal.py`, `test_fs_path_traversal.py` |
| Write into `.nodus/` refused (Floor) | ✅ | ✅ | ✅ | `test_capability_policy.py` |

**Open — [#843](https://github.com/Masterplanner25/Nodus/issues/843), severity:high.**
`nodus serve` with no `--allow-paths` applies **no filesystem confinement**.
`RuntimeService` passes `allowed_paths=None` to a VM built with
`source_path=None`, so both halves of the fallback in `VM._ensure_path_allowed`
are absent and the check returns without restricting anything. Confirmed against
a running server: submitted code read `C:/Windows/System32/drivers/etc/hosts`
(1027 bytes) and wrote a file under `C:/Windows/Temp/`, verified off disk.

This is the same asymmetry #754 closed for subprocess, network and environment.
The filesystem was not part of that fix, and `RuntimeService` does not go through
the `NodusRuntime` default. **An earlier revision of this document asserted the
opposite** — that BUG-113 had resolved it because `NodusRuntime()` defaults
`allowed_paths` — which is true of `NodusRuntime` and not of the server.

`writable_paths` is the two-tier model (#467): a tree readable as context, a
subtree editable. Verified — with `allowed_paths=[cwd], writable_paths=[]` a read
returned its contents and the write was refused with
*"no path is writable"*, `kind="sandbox"`.

---

## Subprocess execution

| Behaviour | CLI | EMB | SRV | Test file |
|----------|:---:|:---:|:---:|-----------|
| Subprocess permitted by default | ✅ allowed | ⛔ **denied** | ⛔ **denied** | `test_subprocess_sandbox.py` |
| Grant | n/a | `allow_subprocess=True` | `--allow-subprocess` | `test_capability_policy.py`, `test_embedding.py` |
| Narrow to named executables | n/a | `allowed_commands=[…]` | `--allowed-commands` | `test_sandbox_allowlists.py` |
| stdout/stderr captured, not raw | ✅ | ✅ | ✅ | `test_subprocess_sandbox.py` |
| Subprocess inherits the filesystem jail | ❌ | ❌ | ❌ | none |

Denial is `kind="sandbox"` with the granting flag named in the message:
*"Blocked: subprocess execution is not granted; pass allow_subprocess=True to
NodusRuntime to allow it"*.

**Open — a granted subprocess is not itself sandboxed.** Once
`allow_subprocess=True`, the child process is an OS process and `allowed_paths`
does not reach it. `allowed_commands` narrows *which* executables may run, which
is the available mitigation; confining the child requires an OS-level boundary.

---

## Network access

| Behaviour | CLI | EMB | SRV | Test file |
|----------|:---:|:---:|:---:|-----------|
| Network permitted by default | ✅ allowed | ⛔ **denied** | ⛔ **denied** | `test_documented_defaults_agree.py`, `test_runtime_capabilities.py` |
| Grant | n/a | `allow_network=True` | `--allow-network` | `test_sandbox_allowlists.py` |
| Host allowlist | n/a | `allowed_hosts=[…]` | `--allowed-hosts` | `test_sandbox_allowlists.py` |
| TLS certificate verification | ✅ (httpx default) | ✅ | ✅ | none |

A previous revision recorded *"No URL-level network restriction exists"* as an
open gap. `allowed_hosts` (#162) is that restriction.

---

## Environment access

| Behaviour | CLI | EMB | SRV | Test file |
|----------|:---:|:---:|:---:|-----------|
| `std:env` reads permitted by default | ✅ allowed | ⛔ **denied** | ⛔ **denied** | `test_env_sandbox.py` |
| Grant | n/a | `allow_env=True` | `--allow-env` | `test_env_sandbox.py` |

Absent from every earlier revision of this document. The block covers `env_get`,
`env_set`, `env_unset`, `env_has`, `env_list` and `env_list_keys`, both as direct
builtins and through `import "std:env"`.

---

## Execution limits

| Behaviour | CLI | EMB | SRV | Test file |
|----------|:---:|:---:|:---:|-----------|
| Default step limit | **10,000,000** | **10,000,000** | 10,000,000 | `test_sandbox_limits.py` |
| Default wall-clock limit | **200 ms** (`EXECUTION_TIMEOUT_MS`) | none (`timeout_ms=None`) | none | `test_sandbox_limits.py` |
| Default call-depth cap | 10,000 | 10,000 | 10,000 | `test_max_frames_default.py` |
| Default memory cap | none | none | none | `test_memory_limit.py` |
| Override | `--step-limit`, `--time-limit` (seconds) | `max_steps=`, `timeout_ms=`, `max_frames=`, `max_memory_mb=` | flags | `test_sandbox_limits.py` |
| Limits non-bypassable from inside the script | ✅ | ✅ | ✅ | `test_sandbox_limits.py` |

**Three corrections to the previous revision, all measured.** It recorded "Default
step limit: none" and "Default time limit: none" in every context. Neither is
true of the CLI, which applies `MAX_STEPS` and `EXECUTION_TIMEOUT_MS` through
`max_steps=MAX_STEPS if max_steps is None else max_steps` in `run_file` — a
program with no `--time-limit` dies at 200 ms of wall clock, and cooperative
sleep no longer counts toward it (SCHED-001). `NodusRuntime` defaults
`max_steps=10_000_000` and only `timeout_ms` is unbounded.

**The call-depth cap must be checked by behaviour, not by reading the field.**
`NodusRuntime().max_frames` is `None`, which reads as "no cap" and is not:
`configure_vm_limits()` installs `MAX_STACK_DEPTH` (10,000) and the attribute is
only an override. Verified by recursing without bound — `Call stack overflow`,
`kind="sandbox"`, including under `NodusRuntime(timeout_ms=None, max_steps=None)`,
which is the configuration recommended for long-lived hosts and the one where the
other two guards are gone by design (#350).

**A memory bound exists — `max_memory_mb` (#160).** An earlier revision listed
"no memory limit" as an unfiled gap. Verified: `max_memory_mb=1` on a
list-growing loop failed with *"Memory limit exceeded: this run grew the process
to 32 MB, past its 32 MB ceiling"*, `kind="sandbox"`, and `max_memory_mb=0` is
refused at construction. Two caveats it states about itself, both load-bearing:
it polls RSS, so it bounds **growth over time and not a single allocation** — one
enormous allocation succeeds and the check fires afterwards; and an unenforceable
limit is **refused** at construction rather than accepted and ignored, on the
grounds that a declared-but-unenforced control is worse than none (the shape #473
and #478 were filed for).

---

## Module loading

| Behaviour | CLI | EMB | SRV | MOD | Test file |
|----------|:---:|:---:|:---:|:---:|-----------|
| Relative `../` traversal blocked | ✅ | ✅ | ✅ | ✅ | `test_path_traversal.py` |
| Absolute import path blocked | ✅ | ✅ | ✅ | ✅ | `test_path_traversal.py` |
| Import of a non-`.nd` file blocked | ✅ | ✅ | ✅ | ✅ | none |
| Circular import detected | ✅ | ✅ | ✅ | ✅ | none |
| `std:` namespace not shadowable | ✅ | ✅ | ✅ | ✅ | none |

Enforcement is consistent across contexts because the path resolver runs before
the file is read, independent of runtime context. The four rows marked ✅ with no
test were each confirmed by running them: `import "./secret.txt"` and
`import "./secret"` both fail *Import not found*; a mutual import fails *Circular
import detected*; a user file named to collide with `std:fs` does not shadow it;
and `import "../../outside"` fails *"path escapes the"* project root.

---

## Host-boundary surfaces

| Behaviour | Default | Test file |
|----------|---------|-----------|
| Every builtin classified as carrying authority or not | ✅ (#473) | `test_capability_coverage.py` |
| `SyscallSpec.capability` enforced, not decorative | ✅ (#478) | `test_syscall_capability.py` |
| `tool_call` / `agent_call` / memory store reachable by policy | ✅ (#473) | `test_capability_coverage.py` |
| Host agent handler bounded | `agent_timeout_ms=` | — |
| Memory store isolated per `NodusRuntime` | ✅ (#185) | — |
| `register_function` cannot override a builtin | ✅ | `test_downstream_contracts.py` |
| Capability policy honoured for the **async** form of a call | ✅ since 5.6.0 (#616) | `tests/closed_issues/issue_616.py` |

`agent_timeout_ms` stops the **wait**, not the handler: arbitrary Python cannot be
preempted, so the handler runs on a daemon thread and is abandoned at the
deadline. Abandoned calls are recorded — `abandoned_agent_calls()`.

**#616 is why an embedder should not sit below 5.6.0**: a capability policy could
be bypassed by writing the async form of a call.

---

## Server mode (`nodus serve`)

| Behaviour | Status | Test file |
|----------|--------|-----------|
| subprocess / network / env denied by default | ✅ (#754) | `test_serve_denies_by_default.py`, `test_server_policy_chokepoint.py` |
| Filesystem confined by default | ⛔ **no — [#843](https://github.com/Masterplanner25/Nodus/issues/843)** | none |
| Bearer token auth on non-local bindings | `--auth-token` | none |
| Request isolation (one VM per request) | ✅ `_new_vm()` per request | none |

The three capability denials were confirmed against a live server on
`POST /execute`, not read off `--help`.

> **The payload key is `code`, not `source`, and an unrecognised key runs
> nothing and returns `ok: true`.** A probe posting `{"source": …}` gets a
> successful-looking empty result. Worth knowing before concluding from a green
> response that anything executed — it cost a wrong reading of these rows during
> this review.

---

## Gap summary

| Gap | Severity | Status |
|-----|----------|--------|
| `nodus serve` unconfined filesystem | **HIGH** | **Open — [#843](https://github.com/Masterplanner25/Nodus/issues/843)** (filed 2026-09-07) |
| A granted subprocess is not itself sandboxed | MEDIUM | Open — needs an OS boundary; `allowed_commands` narrows it |
| Embedded runtime filesystem open by default | HIGH | ✅ Fixed #119 |
| 200 ms trap in `NodusRuntime()` | HIGH | ✅ Fixed #97 |
| Wall-clock deadline counted sleep | HIGH | ✅ Fixed SCHED-001 / #94 |
| No call-depth cap in embedded mode | HIGH | ✅ Fixed #350 |
| Network access unrestricted | MEDIUM | ✅ Fixed — denied by default (#405), `allowed_hosts` (#162) |
| No memory limit | LOW | ✅ Fixed — `max_memory_mb` (#160) |
| Capability policy blind to non-sandbox surfaces | HIGH | ✅ Fixed #473 / #478 |
| Policy bypassable via the async call form | HIGH | ✅ Fixed 5.6.0 (#616) |

---

## Test file index

| File | Tests | What it covers |
|------|:---:|----------------|
| `tests/test_capability_policy.py` | 29 | policy at both host chokepoints (#405) |
| `tests/test_capability_coverage.py` | 20 | every builtin classified as carrying authority or not (#473) |
| `tests/test_sandbox_allowlists.py` | 17 | `allowed_commands` (#161), `allowed_hosts` (#162) |
| `tests/test_env_sandbox.py` | 15 | `allow_env` across builtins and `std:env` |
| `tests/test_runtime_capabilities.py` | 11 | `std:runtime.capabilities()` (#87) |
| `tests/test_syscall_capability.py` | 10 | `SyscallSpec.capability` enforced (#478) |
| `tests/test_path_traversal.py` | — | `../` traversal in imports and fs calls, CLI and EMB |
| `tests/test_fs_path_traversal.py` | — | filesystem traversal via `std:fs` |
| `tests/test_cli_allowed_paths.py` | — | `--allow-paths` enforcement |
| `tests/test_sandbox_filesystem.py` | — | `allowed_paths` in `NodusRuntime`, absolute paths |
| `tests/test_path_scope.py` | — | the read/write split, and that every fs builtin declares which it is |
| `tests/test_sandbox_limits.py` | — | `--step-limit`, `--time-limit`, stack overflow |
| `tests/test_max_frames_default.py` | — | the embedded call-depth default and per-call override |
| `tests/test_memory_limit.py` | — | `max_memory_mb` (#160) |
| `tests/test_subprocess_sandbox.py` | — | subprocess availability and output capture |
| `tests/test_downstream_contracts.py` | — | `GATED_BUILTINS`, the denial contract, `register_function` |

The first six were invisible to every earlier revision of this document — 102
tests covering the entire v5 capability system, while the matrix reported those
same areas as untested gaps.
