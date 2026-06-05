# Nodus Security Matrix

**Version:** 4.0.0  
**Status:** Governing document  
**Relates to:** `docs/governance/SECURITY_POSTURE.md` (policy intent),
`docs/governance/TECH_DEBT.md` (known gaps)

This matrix maps each security-relevant behavior to the contexts where it is
enforced, the enforcement code path, and the test file that covers it. Its
purpose is to make gaps visible — a row with no test file entry is an open
testing gap.

---

## Context key

| Symbol | Context |
|--------|---------|
| CLI | `nodus run script.nd` (the `nodus` executable) |
| EMB | `NodusRuntime` embedded in a Python host |
| SRV | `nodus serve` HTTP server mode |
| MOD | Module loader (`import "./path"` or `import "std:x"`) |
| STD | Stdlib wrapper functions (`std:fs`, `std:subprocess`, `std:http`, etc.) |

---

## Filesystem access

| Behavior | CLI | EMB | SRV | Test file |
|----------|:---:|:---:|:---:|-----------|
| Blocks `../` traversal out of project root | ✅ enforced | ⚠️ opt-in (`allowed_paths`) | ✅ enforced | `test_path_traversal.py`, `test_fs_path_traversal.py` |
| `allowed_paths` restricts reads/writes/listdir | n/a | ✅ enforced | ✅ enforced | `test_cli_allowed_paths.py`, `test_sandbox_filesystem.py` |
| Absolute paths to system dirs blocked | ✅ enforced | ⚠️ opt-in (`allowed_paths`) | ✅ enforced | `test_sandbox_filesystem.py` |
| Write to read-only path raises `io_error` | ✅ (OS) | ✅ (OS) | ✅ (OS) | none |

**Known gap — BUG-119:** The embedded runtime has no filesystem sandbox by
default. `NodusRuntime()` with no `allowed_paths` argument grants unrestricted
disk read/write to any path the OS user can access. The CLI jails to the
project root; the embedded runtime does not. Callers must opt in with
`NodusRuntime(allowed_paths=[...])`. Fix tracked in #119.

---

## Subprocess execution

| Behavior | CLI | EMB | SRV | Test file |
|----------|:---:|:---:|:---:|-----------|
| `subprocess.run` allowed | ✅ | ✅ | ✅ | `test_subprocess_sandbox.py` |
| `subprocess_spawn` available | ✅ | ✅ | ✅ | `test_subprocess_sandbox.py` |
| Subprocess inherits filesystem restrictions | ❌ not enforced | ❌ not enforced | ❌ not enforced | none |
| Subprocess stdout/stderr captured, not raw | ✅ | ✅ | ✅ | `test_subprocess_sandbox.py` |

**Known gap:** Subprocess execution is not sandboxed. A script can spawn
`cmd /c del /f /q C:\important` regardless of `allowed_paths`. This is
by-design for CLI (trusted code); it is a known limitation for embedded
use. Document in `embedding-nodus.md` and `SECURITY_POSTURE.md` if not already.

---

## Network access

| Behavior | CLI | EMB | SRV | Test file |
|----------|:---:|:---:|:---:|-----------|
| `http.get` / `http.post` allowed | ✅ | ✅ | ✅ | none |
| URL allowlist / denylist | ❌ not available | ❌ not available | ❌ not available | none |
| TLS certificate verification | ✅ (httpx default) | ✅ | ✅ | none |

**Known gap:** No URL-level network restriction exists. A script running in an
embedded host can make arbitrary outbound HTTP calls. Embedders requiring
network isolation must proxy or firewall at the OS/container level.

---

## Execution limits

| Behavior | CLI | EMB | SRV | Test file |
|----------|:---:|:---:|:---:|-----------|
| `--step-limit N` caps instruction count | ✅ | ✅ (`max_steps=N`) | ✅ | `test_sandbox_limits.py` |
| `--time-limit N` caps wall-clock ms | ✅ | ✅ (`timeout_ms=N`) | ✅ | `test_sandbox_limits.py` |
| Default step limit | none | none | none | — |
| Default time limit | none | 200ms | none | `test_sandbox_limits.py` |
| Limits non-bypassable from inside script | ✅ | ✅ | ✅ | `test_sandbox_limits.py` |

**Known gap — BUG-97 / EMBED-001:** The 200ms default in `NodusRuntime()` is
a trap for embedders building servers, workflows, or MCP hosts — any coroutine
sleeping more than 200ms cumulative is killed silently. Use
`NodusRuntime(timeout_ms=None, max_steps=None)` for long-lived hosts. This is
documented in `docs/runtime/OPERATOR_OR_EMBEDDER_RUNBOOK.md` but not surfaced
at the API call site.

**Known gap — SCHED-001 / #94:** The wall-clock deadline counts cooperative
sleep time. A coroutine doing 4 × 50ms sleeps is killed after 200ms even
though it consumed no CPU. The intent was CPU-time limiting, but the
implementation is wall-clock. Fix tracked in #94.

---

## Module loading

| Behavior | CLI | EMB | SRV | MOD | Test file |
|----------|:---:|:---:|:---:|:---:|-----------|
| Relative import `../` traversal blocked | ✅ | ✅ | ✅ | ✅ | `test_path_traversal.py` |
| Absolute import path blocked | ✅ | ✅ | ✅ | ✅ | `test_path_traversal.py` |
| Import of non-`.nd` files blocked | ✅ | ✅ | ✅ | ✅ | none |
| Circular import detection | ✅ | ✅ | ✅ | ✅ | none |
| `std:` namespace isolated from user modules | ✅ | ✅ | ✅ | ✅ | none |

Module loader enforcement is consistent across contexts because the path
resolver runs before the file is read, independent of the runtime context.

---

## Call stack and memory

| Behavior | CLI | EMB | SRV | Test file |
|----------|:---:|:---:|:---:|-----------|
| Stack overflow raises `"sandbox"` err | ✅ | ✅ | ✅ | `test_sandbox_limits.py` |
| Stack depth limit configurable | ❌ hardcoded | ❌ hardcoded | ❌ hardcoded | — |
| Memory limit enforced | ❌ not enforced | ❌ not enforced | ❌ not enforced | none |

---

## Server mode (`nodus serve`)

| Behavior | Test file |
|----------|-----------|
| Bearer token authentication on non-local bindings | none |
| Sandbox defaults (filesystem, limits) same as EMB | none |
| Request isolation (one runtime per request vs shared) | none |

**Known gap — BUG-113:** Server mode sandbox behavior is not tested. The
sandbox configuration at server startup and the relationship between per-request
and per-server state needs a test pass. Tracked in #113.

---

## Gap summary

| Gap | Severity | Issue |
|-----|----------|-------|
| Embedded runtime filesystem open by default | HIGH | #119 |
| Subprocess not sandboxed in any context | MEDIUM | (not filed; known limitation) |
| Network access unrestricted | MEDIUM | (by design; note in docs) |
| 200ms trap in NodusRuntime() | HIGH | #97 |
| Wall-clock deadline counts sleep (SCHED-001) | HIGH | #94 |
| Server mode sandbox untested | MEDIUM | #113 |
| No memory limit | LOW | (not filed) |

---

## Test file index

| File | What it covers |
|------|----------------|
| `tests/test_path_traversal.py` | `../` traversal in imports and fs calls, both CLI and EMB |
| `tests/test_fs_path_traversal.py` | Filesystem path traversal via `std:fs` |
| `tests/test_cli_allowed_paths.py` | `--allow-paths` CLI flag enforcement |
| `tests/test_sandbox_filesystem.py` | `allowed_paths` in NodusRuntime, absolute paths |
| `tests/test_sandbox_limits.py` | `--step-limit`, `--time-limit`, stack overflow |
| `tests/test_subprocess_sandbox.py` | subprocess availability and output capture |
