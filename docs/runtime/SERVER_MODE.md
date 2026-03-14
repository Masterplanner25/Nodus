# Server Mode and Sessions

Nodus can run as an HTTP service to execute code, manage sessions, and coordinate worker-backed task graphs.

## Start Server

```bash
nodus serve --port 7331
```

Optional:
- `--trace` enables trace output
- `--worker-sweep-interval-ms <ms>` controls worker liveness checks

## Sessions
The server can create and reuse sessions. Sessions maintain VM state and memory across executions.

CLI helpers:
- `nodus snapshot <session>`
- `nodus snapshots`
- `nodus restore <snapshot>`

Snapshots are stored under the configured snapshot directory (see `config.py`).

## Worker Mode
Workers can connect to a server and execute tasks that specify a `worker` capability:

```bash
nodus worker --host 127.0.0.1 --port 7331
```

## HTTP Endpoints (High Level)
The server exposes JSON endpoints for:

- Execution and inspection: `/execute`, `/check`, `/ast`, `/dis` (also `/disassemble`)
- Task graphs: `/graph`, `/graph/run`, `/graph/plan`, `/graph/resume`
- Workflows/goals: `/workflow/run`, `/workflow/plan`, `/workflow/resume`, `/goal/run`, `/goal/plan`, `/goal/resume`
- Tooling services: `/tool/call`, `/agent/call`, `/memory`
- Sessions and snapshots: `/session`, `/snapshot`, `/restore`
- Workers: `/worker/register`, `/worker/poll`, `/worker/heartbeat`, `/worker/result`

Payloads are JSON and typically accept `code`, `filename`, and optional `session` id. See `server.py` for exact request/response shapes.
