# Webhook Bridge Example

A production-shaped FastAPI shell that sits in front of `nodus serve` and
handles the concerns the Nodus DSL deliberately does not: URL routing,
request-body access, request-level auth, a durable SQL audit log, and replay.

The orchestration logic — retry and the outbound HTTP call — lives in a
dynamically generated `.nd` workflow that runs inside `nodus serve`.

## Status

**Re-verified 2026-09-17 against nodus-lang 5.13.0**, with `nodus serve` on
a local port and a local HTTP server standing in for Slack, exercising the
bridge's own `build_workflow_code` / `run_on_nodus` directly (the FastAPI
layer itself was import-checked, not driven; it needs Postgres):

| | |
|---|---|
| Generated program parses and runs under `serve` | yes — `ok: true`, `result.steps.execute = "Success"` |
| One Slack post per webhook | yes — counted at the stub |
| `graph_id` returned for replay | yes — from the `/workflow/run` response |
| `POST /workflow/replay` on a completed run | returns the recorded result; **does not post again** |
| Same webhook delivered twice | **posts twice** — see *What `std:effects` does here* |

Three things found on that day are filed and worth knowing before you build
on this:

- **#858** (fixed) — `POST /workflow/run` used to run the workflow the
  program *defines* even when the program had already called
  `run_workflow(...)` itself, so the first revision of this example posted to
  Slack **twice** per webhook. The endpoint now reports the program's own run
  instead of starting another; the generated program is definition-only
  anyway, which is the clearer shape.
- **#857** (fixed) — every program under `nodus serve` used to run at the
  CLI's 200 ms default with no way to raise it; the first revision of this
  workflow timed out *after* posting and reported the delivery as failed.
  The quick start now passes `--time-limit 30` to the server and the bridge
  asks for `timeout_ms` per request (`WORKFLOW_TIMEOUT_MS`, default 30 s,
  capped by the server). A step past the budget returns `ok: false` now
  rather than hanging the request, which it did through 5.13.0 (#862).
- **#855** (fixed) — each request used to pay ~0.5 s building its HTTP
  client's trust store; the store is per process now, so only the first
  request after the server starts pays it.

## What it demonstrates

- **Serve mode integration** — how to drive `nodus serve` via `POST /workflow/run`
  and `POST /workflow/replay` from a Python host
- **Dynamic `.nd` generation** — embedding caller-controlled data safely in a
  code string using `json.dumps` as the escaping boundary
- **`std:http` outbound** — `http.post` with `"json"` and `"headers"` options
- **Step retry** — `with { retries: 3, retry_delay_ms: 2000 }` on the step
- **The host/Nodus boundary** — what stays Python (auth, DB, routing) vs what
  goes in `.nd` (retry, HTTP call)

### What `std:effects` does here

The `fx.action_id` / `fx.resolve` / `fx.pending` / `fx.complete` guard in the
step is scoped to **one request**. The effect store is in-memory and per VM
(`docs/guide/ai-primitives.md`), and `nodus serve` builds a fresh VM per
request. So it prevents a re-post when the step retries *within* a request
after a partial failure, and it does nothing about the same webhook arriving
twice — measured: two identical requests, two posts. If you need
cross-request exactly-once, dedupe in the `AutomationLog` table on the Python
side; `serve` cannot yet be handed a persistent effect store.

## Quick start

```bash
# 1. Install dependencies
pip install nodus-lang fastapi uvicorn httpx sqlalchemy psycopg2-binary

# 2. Start nodus serve with an auth token (SEC-001: required) and the one
#    capability this workflow needs. Submitted code is denied subprocess,
#    network and environment access by default (#754); the generated .nd posts
#    to Slack, so it needs --allow-network. Naming the host with
#    --allowed-hosts is the tighter grant and is what you want in production.
nodus serve --auth-token mysecret --port 8080 \
    --allow-network --allowed-hosts hooks.slack.com --time-limit 30

# 3. Configure and start the bridge
export NODUS_SERVE_TOKEN=mysecret
export DATABASE_URL=postgresql://user:pass@localhost/mydb
export API_KEY=my-api-key
export SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/HOOK

uvicorn nodus_webhook_bridge:app --port 8000

# 4. Send a webhook
curl -X POST http://localhost:8000/webhook/github \
  -H "X-API-KEY: my-api-key" \
  -H "Content-Type: application/json" \
  -d '{"event": "push", "repo": "my-repo"}'

# 5. Replay a run by its log id
curl -X POST http://localhost:8000/replay/1 \
  -H "X-API-KEY: my-api-key"
```

`DATABASE_URL` accepts any SQLAlchemy URL; `sqlite:///bridge.db` works for a
local try-out without Postgres.

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `NODUS_SERVE_URL` | `http://127.0.0.1:8080` | URL of the running `nodus serve` instance |
| `NODUS_SERVE_TOKEN` | *(required)* | Bearer token matching `--auth-token` on `nodus serve` |
| `DATABASE_URL` | `postgresql://...` | SQLAlchemy connection string for the audit log |
| `API_KEY` | `super-secret-key` | Key callers must send in `X-API-KEY` header |
| `SLACK_WEBHOOK_URL` | *(placeholder)* | Outbound Slack (or any HTTP) target |
| `WORKFLOW_TIMEOUT_MS` | `30000` | Budget asked of `nodus serve` per request; the server's `--time-limit` caps it |

## Security flags

- **SEC-001** — `NODUS_SERVE_TOKEN` is required. The bridge refuses to start
  without it. Without a token, `nodus serve` accepts arbitrary `.nd` from any caller.
- **SRV-001** — `build_workflow_code` is the highest-value unit-test target.
  It is the security boundary between caller-controlled webhook data and code
  that executes on the Nodus VM. Test it with adversarial payloads.

## Related

- Guide: `docs/guide/real-world-integration.md`
- Server mode: `docs/runtime/SERVER_MODE.md`
- Embedded-mode alternative (no server): `docs/guide/embedding-nodus.md`
