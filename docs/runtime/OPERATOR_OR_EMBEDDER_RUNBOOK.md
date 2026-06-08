<!-- Authored by Codex during non coding session. Needs review before repo commit and push. -->

# Operator / Embedder Runbook

**Version:** 3.0.2
**Status:** Governing document
**Maintainer:** Shawn Knight (Masterplanner25)

This runbook is for engineers who embed Nodus in a host application or operate a
service built on Nodus. It covers: setup, configuration, monitoring, troubleshooting,
and upgrade procedures.

---

## 1. Embedding setup

### 1.1 Install

```bash
pip install nodus-lang==3.0.2
```

For the FastAPI/Uvicorn server stack (experimental):
```bash
pip install "nodus-lang[server]==3.0.2"
```

### 1.2 Minimal embedding

```python
from nodus import NodusRuntime

runtime = NodusRuntime(
    max_steps=100_000,
    timeout_ms=5_000,
    allowed_paths=["/app/scripts"],
    allow_input=False,
    max_frames=500,
)
result = runtime.run_source(source_code)
if not result["ok"]:
    logger.error("script_failed", error=result["error"], stderr=result["stderr"])
```

### 1.3 Construction once, run many times

`NodusRuntime` is designed to be constructed once and reused across multiple `run_source()`
calls. Each call is independent — globals are not shared between calls. The runtime caches
compiled module bytecode across runs.

If you need to reset the runtime state (e.g., clear module cache), call `runtime.reset()`.

---

## 2. Configuration reference

| Parameter | Type | Default | When to change |
|-----------|------|---------|----------------|
| `max_steps` | `int \| None` | `MAX_STEPS` (~10M) | Lower for untrusted/short-running scripts |
| `timeout_ms` | `int \| None` | **200 ms** | **Set `None` for servers/loops/MCP hosts.** The default 200 ms matches `nodus run` and kills coroutines that sleep > 200 ms cumulatively. For latency-bounded batch scripts, keep it short; for long-lived embedding, always pass `timeout_ms=None`. (EMBED-001 / #97) |
| `max_stdout_chars` | `int \| None` | `MAX_STDOUT_CHARS` | Lower for log-constrained environments |
| `project_root` | `str \| None` | `None` | Set to project directory when scripts use imports |
| `allowed_paths` | `list[str] \| None` | `None` (unrestricted) | Set for untrusted scripts; restrict to needed directories |
| `allow_input` | `bool` | `False` | Keep `False`; set `True` only for interactive use cases |
| `max_frames` | `int \| None` | `None` (uses `MAX_STACK_DEPTH`) | Set to 200-1000 for untrusted code |

---

## 3. Monitoring

### 3.1 Success/failure rate

Check `result["ok"]` on every `run_source()` call and emit a metric or log entry.

```python
result = runtime.run_source(code)
metrics.increment("nodus.run", tags={"ok": str(result["ok"])})
if not result["ok"]:
    logger.warning("nodus.run.failed", error=result["error"])
```

### 3.2 Resource limit hits

`RuntimeLimitExceeded` appears in `result["error"]`. Track separately from script
errors — resource limit hits indicate scripts that are too slow or too big, not
script bugs.

```python
if not result["ok"] and "RuntimeLimitExceeded" in result.get("error", ""):
    metrics.increment("nodus.run.limit_exceeded")
```

### 3.3 Sandbox violations

`kind="sandbox"` in the error indicates a script tried to access a restricted resource.

### 3.4 Stdout/stderr size

Monitor `len(result["stdout"])` relative to `max_stdout_chars`. If scripts frequently
hit the truncation limit, scripts may be producing too much output or the limit is too
low.

---

## 4. Troubleshooting

### 4.1 Script fails with `ok=false`

1. Check `result["error"]` for the error type and location
2. Check `result["stderr"]` for additional diagnostic output
3. For syntax errors: fix the script; they are always script-side issues
4. For runtime errors: check the error `kind` and `message`
5. For sandbox errors: check `allowed_paths` configuration

### 4.2 Script runs but produces no output

- Verify `result["ok"]` is `True`
- Verify the script calls `print()` (Nodus scripts must explicitly print; no auto-print)
- Check `result["stdout"]` directly
- Check `max_stdout_chars` — if the script produced more than the limit, stdout is truncated

### 4.3 Script hangs

- Set `timeout_ms` if not already set — without it, scripts with infinite loops run until
  `max_steps` fires (which may be slow)
- Use `max_steps` as a secondary guard
- Check for deadlocked coroutines (all coroutines waiting on channels with no sender)

### 4.4 Import errors

- Set `project_root` to the directory containing the script's imports
- Verify the import path is relative to the project root
- For stdlib imports (`std:json`, etc.): these are bundled — if they fail, the nodus-lang
  install may be corrupt (reinstall)

### 4.5 Module cache corruption

If a `ModuleError` mentions the cache or bytecode version mismatch:
```bash
rm -rf .nodus/cache/
```
The cache rebuilds automatically on the next run. This is always safe.

### 4.6 Workflow resume fails

If `resume_workflow()` fails:
1. Check `.nodus/graphs/<id>.json` exists and is valid JSON
2. Verify `project_root` is set consistently across the original run and the resume
3. If the graph is corrupt, delete `<id>.json` and restart the workflow from scratch

---

## 5. Upgrade procedure

### 5.1 Patch release (x.y.Z)

Patch releases are backward-compatible. Upgrade by replacing the `nodus-lang` package.
No script changes required. No API changes. The bytecode cache may be invalidated if the
patch bumps `BYTECODE_VERSION` (rare; noted in CHANGELOG.md).

```bash
pip install nodus-lang==3.0.Z
```

After upgrade, verify with `nodus --version` and a smoke-test run.

### 5.2 Minor release (x.Y.z)

Minor releases add functionality. Upgrade is safe; no breaking changes to stable APIs.
New stdlib functions may be available in scripts. Review CHANGELOG.md for new features.

### 5.3 Major release (X.y.z)

Major releases may include breaking changes to the language, stdlib, or embedding API.
Before upgrading to a major version:

1. Read CHANGELOG.md carefully — all breaking changes are listed
2. Read `docs/migration/` for migration guides (e.g., `v3-to-v4.md`)
3. Review `docs/governance/COMPATIBILITY_MODEL.md` for what changed
4. Test all scripts against the new version in a non-production environment
5. Upgrade `BYTECODE_VERSION` handling if persisting compiled bytecode (most embedders
   do not persist bytecode — they compile from source on each run)

---

## 6. Production checklist

Before deploying a Nodus-embedded application to production:

- [ ] `NodusRuntime` is configured with explicit `max_steps` and `timeout_ms`
- [ ] `allowed_paths` is set if the application handles untrusted scripts
- [ ] `allow_input=False` (the default; verify it has not been overridden)
- [ ] `max_frames` is set for untrusted code
- [ ] `result["ok"]` is checked on every `run_source()` call
- [ ] Error logging includes both `result["error"]` and `result["stderr"]`
- [ ] Nodus version is pinned in `requirements.txt` or `pyproject.toml`
- [ ] Upgrade procedure has been tested (at minimum, a version bump smoke test)
- [ ] Workflow persistence directory (`.nodus/`) is on a persistent volume if workflows are used
- [ ] If workflows are used in production, `SQLiteWorkflowStore` is configured (see §6.1)

---

## 6.1 Workflow store durability (#174)

The default workflow runner uses `LocalWorkflowStore` — file-backed JSON at
`.nodus/workflow_framework/runs/`. This store is **not crash-safe**: a process kill
between the read-modify-write of a run file can corrupt run state. It is appropriate
for development and short-lived scripts only.

For any production deployment where workflows must survive a restart:

```python
from nodus_lang_workflow.runner import configure_default_workflow_runner

configure_default_workflow_runner(backend="sqlite", path=".nodus/workflow.db")
```

Call this once at application startup, before any `run_workflow()` or
`NodusRuntime` usage that triggers a workflow.

`SQLiteWorkflowStore` uses WAL mode for atomic writes and survives unexpected
process exits. The default path can be any writable path on a persistent volume.

The HTTP server (`nodus serve`) accepts `--workflow-store-backend sqlite` and
`--workflow-store-path PATH` flags for the same effect.

---

## 7. Companion library notes

### nodus-mcp

When embedding with nodus-mcp:
- The MCP server and client are managed through `NodusRuntime.register_function()` or
  the nodus-mcp Python API directly
- nodus-mcp v0.1 is not yet published (three-artifact launch pending)
- Server-initiated requests (roots/list, sampling/createMessage) are stdio-only in v0.1

### nodus-a2a

When embedding with nodus-a2a:
- The A2A server runs in a thread via `A2AHttpServer.serve_in_thread()`
- Production deployments must configure `token_validator` — dev mode accepts all requests
- v0.1 is message-only; no Task lifecycle, no streaming
- Not yet published (three-artifact launch pending)

---

## Related documents

- `docs/runtime/EMBEDDING.md` — full embedding API reference
- `docs/runtime/EXECUTION_INVARIANTS.md` — runtime guarantees
- `docs/runtime/FAILURE_AND_DEGRADATION_MODEL.md` — failure modes
- `docs/governance/SECURITY_POSTURE.md` — security configuration
