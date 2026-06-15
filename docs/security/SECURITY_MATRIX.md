# Nodus Security Matrix

**Version:** 4.0.3  
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
| Blocks `../` traversal out of project root | ✅ enforced | ✅ enforced | ✅ enforced | `test_path_traversal.py`, `test_fs_path_traversal.py` |
| `allowed_paths` restricts reads/writes/listdir | n/a | ✅ enforced | ✅ enforced | `test_cli_allowed_paths.py`, `test_sandbox_filesystem.py` |
| Absolute paths to system dirs blocked | ✅ enforced | ✅ enforced | ✅ enforced | `test_sandbox_filesystem.py` |
| Write to read-only path raises `io_error` | ✅ (OS) | ✅ (OS) | ✅ (OS) | none |

**Fixed — #119 (PR #133, 2026-06-06):** `NodusRuntime()` now defaults
`allowed_paths` to `[os.getcwd()]`, jailing embedded scripts to the project
tree — matching the CLI sandbox. Pass `allowed_paths=None` for unrestricted
access. The `NODUS_ALLOWED_PATHS` env var is also honoured when set.

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
| Default time limit | none | none | none | `test_sandbox_limits.py` |
| Limits non-bypassable from inside script | ✅ | ✅ | ✅ | `test_sandbox_limits.py` |

**Fixed — #97 / EMBED-001 (PR #133, 2026-06-06):** `NodusRuntime()` now
defaults `timeout_ms=None` (unlimited). The 200ms guardrail is only applied
when explicitly passed (e.g. `timeout_ms=200`). Long-lived hosts — MCP
servers, workflow engines, event loops — are no longer silently killed by
default.

**Fixed — SCHED-001 / #94:** The scheduler now extends the deadline by the
actual wall-clock duration of each sleep call. Only active instruction
execution consumes the deadline budget; idle sleep time is excluded. A
coroutine sleeping 4×100ms with `timeout_ms=200` now completes cleanly.

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

**Fixed — BUG-113 (PR #133, 2026-06-06):** `NodusRuntime()` now defaults
`allowed_paths=[os.getcwd()]`, making the embedded server sandbox match the
CLI default. The open-by-default exposure that made this audit finding
necessary has been resolved.

---

## Gap summary

| Gap | Severity | Status |
|-----|----------|--------|
| Embedded runtime filesystem open by default | HIGH | ✅ Fixed #119 (PR #133, 2026-06-06) |
| Subprocess not sandboxed in any context | MEDIUM | Open — known limitation |
| Network access unrestricted | MEDIUM | Open — by design |
| 200ms trap in NodusRuntime() | HIGH | ✅ Fixed #97 (PR #133, 2026-06-06) |
| Wall-clock deadline counts sleep (SCHED-001) | HIGH | ✅ Fixed #94 |
| Server mode sandbox untested | MEDIUM | ✅ Fixed #113 (PR #133, 2026-06-06) |
| No memory limit | LOW | Open — not filed |

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
