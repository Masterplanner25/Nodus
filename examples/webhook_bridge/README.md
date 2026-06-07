# Webhook Bridge Example

A production-shaped FastAPI shell that sits in front of `nodus serve` and
handles the concerns the Nodus DSL deliberately does not: URL routing,
request-body access, request-level auth, a durable SQL audit log, and replay.

The orchestration logic — retry, exactly-once idempotency, outbound HTTP —
lives in a dynamically generated `.nd` workflow that runs inside `nodus serve`.

## What it demonstrates

- **Serve mode integration** — how to drive `nodus serve` via `POST /workflow/run`
  and `POST /workflow/replay` from a Python host
- **Dynamic `.nd` generation** — embedding caller-controlled data safely in a
  code string using `json.dumps` as the escaping boundary
- **`std:effects` idempotency** — `fx.action_id` / `fx.resolve` / `fx.pending` /
  `fx.complete` for exactly-once delivery
- **`std:http` outbound** — `http.post` with `"json"` and `"headers"` options
- **The host/Nodus boundary** — what stays Python (auth, DB, routing) vs what
  goes in `.nd` (retry, idempotency, HTTP call)

## Quick start

```bash
# 1. Install dependencies
pip install nodus-lang fastapi uvicorn httpx sqlalchemy psycopg2-binary

# 2. Start nodus serve with an auth token (SEC-001: required)
nodus serve --auth-token mysecret --port 8080

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

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `NODUS_SERVE_URL` | `http://127.0.0.1:8080` | URL of the running `nodus serve` instance |
| `NODUS_SERVE_TOKEN` | *(required)* | Bearer token matching `--auth-token` on `nodus serve` |
| `DATABASE_URL` | `postgresql://...` | SQLAlchemy connection string for the audit log |
| `API_KEY` | `super-secret-key` | Key callers must send in `X-API-KEY` header |
| `SLACK_WEBHOOK_URL` | *(placeholder)* | Outbound Slack (or any HTTP) target |

## Security flags

- **SEC-001** — `NODUS_SERVE_TOKEN` is required. The bridge refuses to start
  without it. Without a token, `nodus serve` accepts arbitrary `.nd` from any caller.
- **SRV-001** — `build_workflow_code` is the highest-value unit-test target.
  It is the security boundary between caller-controlled webhook data and code
  that executes on the Nodus VM. Test it with adversarial payloads.

## Related

- Guide: `docs/guide/real-world-integration.md`
- Embedded-mode equivalent: `C:\dev\sed` (embedded runtime, not serve mode)
- `nodus serve` reference: `docs/tooling/`
