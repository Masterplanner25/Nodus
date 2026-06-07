"""
nodus_webhook_bridge.py
=======================

The thin FastAPI shell that closes the gap nodus-lang 4.0.0 does NOT cover:
URL routing, request-body/header access, request-level auth, durable SQL audit
log, and cron. The orchestration logic (retry, idempotency, replay, outbound
HTTP) lives in the .nd workflow and runs inside `nodus serve`.

Architecture
------------
    caller --POST /webhook/{source}--> [THIS Python shell]
        |  validates X-API-KEY (the auth nodus serve only optionally does)
        |  persists AutomationLog row (the durable cross-process log .nd lacks)
        |  builds the .nd `code` string from the webhook payload
        |  (this string-injection IS the workaround for "no request_body builtin")
        v
    POST {nodus serve}/workflow/run  with  Authorization: Bearer <token>
        |  runs the workflow; framework writes .nodus/graphs/<id>.json
        v
    response {"ok": true, "stdout": "...", "error": null}  ->  update log row

SECURITY (SEC-001): `nodus serve` MUST be started WITH --auth-token. Without it,
is_authorized() returns True and any caller can POST arbitrary .nd to /execute.
This bridge requires NODUS_SERVE_TOKEN to be set and refuses to start without it,
so the executing layer is never left open.

SRV-001: this FastAPI/uvicorn layer is exactly the untested surface flagged for
the launch. It is NOT replaced by Nodus and remains yours to test. The
`build_workflow_code` function below is the highest-value unit-test target
(string construction + escaping), followed by the auth dependency.
"""

import json
import os
from datetime import datetime, timezone

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.security.api_key import APIKeyHeader
from sqlalchemy import JSON, Column, DateTime, Integer, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# --- CONFIGURATION ---
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost/dbname")
API_KEY = os.getenv("API_KEY", "super-secret-key")
API_KEY_NAME = "X-API-KEY"

# nodus serve target. The token is REQUIRED — see SEC-001 note above.
NODUS_SERVE_URL = os.getenv("NODUS_SERVE_URL", "http://127.0.0.1:8080")
NODUS_SERVE_TOKEN = os.getenv("NODUS_SERVE_TOKEN")
if not NODUS_SERVE_TOKEN:
    raise RuntimeError(
        "NODUS_SERVE_TOKEN is not set. Refusing to start: an unauthenticated "
        "`nodus serve` (SEC-001) would let any caller execute arbitrary .nd code. "
        "Start `nodus serve --auth-token <SECRET>` and export NODUS_SERVE_TOKEN."
    )

# Slack (or other) outbound target passed through into the .nd workflow.
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "https://hooks.slack.com/services/REPLACE")

# --- DATABASE SETUP (the durable AutomationLog .nd cannot provide) ---
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class AutomationLog(Base):
    __tablename__ = "automation_logs"
    id = Column(Integer, primary_key=True)
    source = Column(String)
    payload = Column(JSON)
    status = Column(String)
    graph_id = Column(String, nullable=True)  # links our id <-> Nodus graph id
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


Base.metadata.create_all(engine)

# --- SECURITY (the request-level auth nodus serve does NOT do in-language) ---
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


async def validate_key(header: str = Depends(api_key_header)):
    if header != API_KEY:
        raise HTTPException(status_code=403, detail="Unauthorized")
    return header


app = FastAPI(title="Nodus Webhook Bridge")


# --- CODE-STRING BUILDER (the workaround for "no request_body builtin") ---
def build_workflow_code(source: str, payload: dict) -> str:
    """Build the .nd program string injected into POST /workflow/run.

    Because nodus-lang 4.0.0 has no in-language access to the HTTP request body,
    the caller's data must be embedded in the code string itself. We do that by
    JSON-encoding the payload and the config, then parsing it back inside the
    .nd program. json.dumps produces valid Nodus map/list/string literals, so
    the embedded value is also a safe escaping boundary (no manual quoting).

    This is the single most important function to unit-test (SRV-001): the
    escaping correctness here is the security boundary between caller-controlled
    data and code execution.
    """
    payload_literal = json.dumps(payload)
    slack_url_literal = json.dumps(SLACK_WEBHOOK_URL)
    source_literal = json.dumps(source)

    # NOTE: the .nd program below is the workflow from the design discussion,
    # with retry as a native annotation and std:effects for exactly-once.
    return f"""
import "std:http" as http
import "std:effects" as fx
import "std:json" as json

let payload = json.parse({json.dumps(payload_literal)})
let source = {source_literal}
let slack_url = {slack_url_literal}

workflow notify_flow {{
    step execute with {{ retries: 3, retry_delay_ms: 2000 }} {{
        let aid = fx.action_id("webhook.notify", payload, source)
        let prior = fx.resolve(aid)
        if (prior.done) {{
            return "Success (idempotent skip)"
        }}
        fx.pending(aid, "hash")
        let resp = http.post(slack_url, {{
            "json": {{"text": "task for source: " + source}},
            "headers": {{"Content-Type": "application/json"}}
        }})
        if (!resp.ok) {{
            throw record {{ code: resp.status, msg: resp.body }}
        }}
        fx.complete(aid, "success", {{"sent": true}})
        return "Success"
    }}
}}

let result = run_workflow(notify_flow)
print(result["steps"]["execute"])
print(result["graph_id"])
"""


# --- NODUS SERVE CLIENT ---
async def run_on_nodus(code: str) -> dict:
    """POST the code string to `nodus serve` with the required bearer token.

    Returns the parsed {"ok", "stdout", "error"} response. Raises on transport
    or non-2xx so the caller can mark the log row failed.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{NODUS_SERVE_URL}/workflow/run",
            headers={"Authorization": f"Bearer {NODUS_SERVE_TOKEN}"},
            json={"code": code, "filename": "webhook.nd"},
        )
        resp.raise_for_status()
        return resp.json()


def parse_graph_id(stdout: str) -> str | None:
    """The workflow prints the graph_id on its last line; pull it out so we can
    store it for /workflow/replay later."""
    lines = [ln for ln in stdout.strip().splitlines() if ln.strip()]
    return lines[-1].strip() if lines else None


# --- ENDPOINTS ---
@app.post("/webhook/{source}", dependencies=[Depends(validate_key)])
async def trigger_webhook(source: str, request: Request):
    payload = await request.json()

    db = SessionLocal()
    try:
        log = AutomationLog(source=source, payload=payload, status="Pending")
        db.add(log)
        db.commit()
        db.refresh(log)
        log_id = log.id

        code = build_workflow_code(source, payload)
        try:
            result = await run_on_nodus(code)
        except httpx.HTTPError as exc:
            log.status = f"Failed: transport: {exc}"
            db.commit()
            raise HTTPException(status_code=502, detail="nodus serve unreachable")

        if result.get("ok"):
            log.status = "Success"
            log.graph_id = parse_graph_id(result.get("stdout", ""))
        else:
            log.status = f"Failed: {result.get('error')}"
        db.commit()

        return {
            "execution_id": log_id,
            "status": log.status,
            "graph_id": log.graph_id,
            "stdout": result.get("stdout"),
        }
    finally:
        db.close()


@app.post("/replay/{log_id}", dependencies=[Depends(validate_key)])
async def replay(log_id: int):
    """Replay maps onto the native POST /workflow/replay, keyed off the Nodus
    graph_id we stored at run time — this is the app-side reconciliation of
    AutomationLog.id <-> graph_id noted in the design discussion."""
    db = SessionLocal()
    try:
        log = db.get(AutomationLog, log_id)
        if not log:
            raise HTTPException(status_code=404, detail="log not found")
        if not log.graph_id:
            raise HTTPException(status_code=409, detail="no graph_id; original run never completed")

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{NODUS_SERVE_URL}/workflow/replay",
                headers={"Authorization": f"Bearer {NODUS_SERVE_TOKEN}"},
                json={"graph_id": log.graph_id},
            )
            resp.raise_for_status()
            result = resp.json()

        log.status = "Replayed" if result.get("ok") else f"Replay failed: {result.get('error')}"
        db.commit()
        return {"message": "Replay finished", "status": log.status, "graph_id": log.graph_id}
    finally:
        db.close()


# --- CRON (stays external — no in-language timer in 4.0.0) ---
# Do NOT start an in-process scheduler here. Use OS cron / a systemd timer
# hitting this endpoint, which keeps scheduling outside the uvicorn workers and
# sidesteps SCHED-001 (the wall-clock timeout_ms trap) entirely.
@app.post("/cron/weekly-report", dependencies=[Depends(validate_key)])
async def weekly_report():
    code = (
        'print("Running scheduled weekly report")\n'
    )
    result = await run_on_nodus(code)
    return {"ok": result.get("ok"), "stdout": result.get("stdout")}
