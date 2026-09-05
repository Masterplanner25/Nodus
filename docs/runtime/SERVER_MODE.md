# Server Mode and Sessions

Nodus can run as an HTTP service to execute code, manage sessions, and coordinate worker-backed task graphs.

## Canonical Surface

The canonical user-facing HTTP API is the surface exposed by `nodus serve`
and implemented in `src/nodus/services/server.py`.

`src/nodus/services/api.py` also defines a FastAPI app factory, but that module
is internal and runner-oriented. It is retained as a helper surface rather than
the documented public server contract.

## Start Server

```bash
nodus serve --port 7331
```

Install options:

- `pip install nodus-lang` keeps server dependencies optional. `nodus serve`
  still works and uses the built-in fallback HTTP server.
- `pip install "nodus-lang[server]"` installs the optional FastAPI/Uvicorn
  stack used when those packages are available.

Optional:
- `--trace` enables trace output
- `--worker-sweep-interval-ms <ms>` controls worker liveness checks
- `--allow-paths <paths>` restricts filesystem builtins to an allowlist
- `--auth-token <token>` requires a Bearer token on all requests
- `--allow-input` permits `input()` in server mode (disabled by default)
Snapshot/restore/worker CLI helpers also accept `--auth-token <token>` to supply the Authorization header.

You can also set `NODUS_ALLOWED_PATHS` (path-separated, e.g. `C:\safe;D:\more` on Windows or `/safe:/more` on Unix).
If `NODUS_SERVER_TOKEN` is set, clients must send `Authorization: Bearer <token>`.
Set `NODUS_SERVER_ALLOW_INPUT=1` to allow `input()` without the flag.

Binding to a non-local host requires an auth token; otherwise the server refuses to start.

### Submitted code is confined (#754)

Code sent to `POST /execute` — or to `/graph`, `/workflow/run`, `/goal/run` —
**cannot run subprocesses, open sockets or read the process environment** unless
the operator grants it. This matches `NodusRuntime` and deliberately does *not*
match `nodus run`: what deny-by-default protects is work you did not fully
author, and a script the developer wrote and chose to run is not that, while
source arriving over a socket is.

| Flag | Environment variable | Grants |
|---|---|---|
| `--allow-subprocess` | `NODUS_SERVER_ALLOW_SUBPROCESS` | `std:subprocess` |
| `--allow-network` | `NODUS_SERVER_ALLOW_NETWORK` | `std:http` and the network builtins |
| `--allow-env` | `NODUS_SERVER_ALLOW_ENV` | `std:env` |
| `--allowed-commands a,b` | `NODUS_SERVER_ALLOWED_COMMANDS` | narrows a subprocess grant to named executables |
| `--allowed-hosts a,b` | `NODUS_SERVER_ALLOWED_HOSTS` | narrows a network grant to named hosts |

```bash
# A server whose workflows post to Slack and do nothing else outbound.
nodus serve --auth-token "$TOKEN" --allow-network --allowed-hosts hooks.slack.com
```

Grant the narrowest set that works, and prefer the allowlist forms: the
difference between `--allow-network` and `--allow-network --allowed-hosts …` is
the difference between "this server may reach the internet" and "this server may
reach one host".

A refusal has `kind: "sandbox"` and names the capability that would grant it:

```
Blocked: subprocess execution is not granted; pass allow_subprocess=True to NodusRuntime to allow it
```

The wording names the **embedding** API because the message is shared with
`NodusRuntime` and the flag name in it is a published contract downstream matches
on (#443). On a server, read `allow_subprocess=True` as `--allow-subprocess`;
the capability being named is the part that matters.

Earlier releases had none of this: submitted code ran with all three permitted
and no flag could change it. If you are pinned to one, put the server behind a
proxy that authenticates and treat every caller as able to run arbitrary commands
as the server's user.

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

- Execution and inspection:
  - Canonical: `/execute`, `/check`, `/ast`, `/dis`
  - Compatibility alias: `/disassemble` (same behavior as `/dis`)
- Task graphs:
  - Canonical: `/graph`, `/graph/run`, `/graph/plan`, `/graph/resume`
  - Compatibility aliases: `/plan_graph`, `/graph_plan`, `/resume_graph`
- Workflows/goals: `/workflow/run`, `/workflow/plan`, `/workflow/resume`, `/goal/run`, `/goal/plan`, `/goal/resume`
- Tooling services: `/tool/call`, `/agent/call`, `/memory`
- Sessions and snapshots: `/session`, `/snapshot`, `/restore`
- Workers: `/worker/register`, `/worker/poll`, `/worker/heartbeat`, `/worker/result`

Payloads are JSON and typically accept `code`, `filename`, and optional `session` id. See `server.py` for exact request/response shapes.
