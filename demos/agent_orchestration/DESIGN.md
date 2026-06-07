# Demo 2 — Agent-triggered workflow orchestration (design doc)

**Status:** Not runnable today. This document captures what the demo would
look like, what infrastructure already exists, and what needs to be built.

---

## The story

> "Submit a goal. The runtime produces a plan. You approve it. Execution
> begins — with retries, checkpoints, and events — and you can watch every
> step in real time."

This is the governance story: intelligence (LLM) plans; the Nodus runtime
executes under human-controlled policy. The approval gate is the explicit
boundary between planning and side-effects.

---

## What the demo would look like

### 1. Start the runtime server

```bash
nodus serve --port 7331
```

### 2. Submit a goal

```bash
curl -X POST http://localhost:7331/goal/plan \
  -H "Content-Type: application/json" \
  -d '{
    "goal": "Fetch https://example.com/people.json, keep only name/email, write to memory"
  }'
```

Response:
```json
{
  "run_id": "abc123",
  "status": "pending_approval",
  "plan": {
    "steps": [
      {"id": "fetch",     "description": "HTTP GET people.json",          "tool": "http_get"},
      {"id": "filter",    "description": "Keep name/email fields only",   "tool": "transform"},
      {"id": "persist",   "description": "Write filtered records to memory", "tool": "memory_set"}
    ]
  }
}
```

### 3. Approve the plan

```bash
curl -X POST http://localhost:7331/goal/runs/abc123/approve
```

### 4. Watch execution

```bash
curl http://localhost:7331/runtime/events?run_id=abc123
```

Events stream:
```
step_start  fetch     → GET https://example.com/people.json
step_done   fetch     → 200 OK, 4 records
step_start  filter    → 4 → 4 records (name, email only)
step_done   filter    
step_start  persist   → writing 4 records to memory
step_done   persist   
goal_done   abc123    → ok
```

### 5. Inject a transient failure (optional wow moment)

Configure a fake 429 on the HTTP step. Watch the runtime's retry policy
trigger automatically — the event stream shows `step_retry` events with
backoff delay before `step_done`.

---

## What already exists

| Capability | Status | API |
|---|---|---|
| Goal execution (no approval gate) | ✅ Live | `POST /goal/run` |
| Goal planning (produce plan, don't execute) | ✅ Live | `POST /goal/plan` |
| Workflow run/plan/resume | ✅ Live | `POST /workflow/run` etc. |
| Runtime events stream | ✅ Live | `GET /runtime/events` |
| Dead-letter replay | ✅ Live | `POST /workflow/replay` |
| Worker registration / polling | ✅ Live | `POST /worker/register` etc. |
| Memory read/write | ✅ Live | `POST /memory`, `DELETE /memory/{key}` |
| Agent call | ✅ Live | `POST /agent/call` |

---

## What is missing

### 1. Plan approval gate (the core gap)

`POST /goal/plan` produces a plan but then either executes it immediately or
returns it without a way to resume. There is no:

- `pending_approval` lifecycle state on a goal run
- `POST /goal/runs/{id}/approve` endpoint
- `POST /goal/runs/{id}/reject` endpoint

**Build estimate:** 1–2 days. Requires adding a `GoalRun` state machine with
`pending_approval → approved → running → done/failed` and corresponding server
routes.

### 2. Goal run list / status endpoint

There is no `GET /goal/runs` or `GET /goal/runs/{id}` — you cannot inspect a
goal run after submission.

**Build estimate:** half a day. The workflow runs list (`GET /workflow/runs`)
already exists and can serve as the model.

### 3. Event stream filtering by run_id

`GET /runtime/events` exists but does not filter by run ID in the current
server implementation. A polling client would see all events from all runs.

**Build estimate:** half a day. Add a `run_id` query param that filters the
event log.

### 4. Retry policy on goal steps

Goal steps do not automatically retry on transient failures today. The
workflow framework has retry semantics (`retry_scheduled` state), but it is
not wired into goal execution.

**Build estimate:** 1 day. Wire the goal executor through the workflow
framework's retry/backoff path.

---

## Implementation order (if we want this runnable)

1. **Goal run state machine** — add `pending_approval` state + approve/reject
   endpoints. (~1.5 days)
2. **Goal run list/status** — `GET /goal/runs` and `GET /goal/runs/{id}`.
   (~0.5 days)
3. **Event stream `run_id` filter** — `GET /runtime/events?run_id=X`.
   (~0.5 days)
4. **Retry wiring** — connect goal steps to the workflow retry mechanism.
   (~1 day)

Total to full demo: **~3.5 days** of focused implementation.

---

## Relationship to existing issues

- The plan approval gate aligns with E2E-02 (per-coroutine timeout exposure)
  and the broader goal of making the runtime's governance surface user-facing
  rather than embedding-only.
- Event stream filtering would also fix E2E-01 (pre-run observer registration)
  by giving embedders a clean way to subscribe to events for a specific run.

---

## Demo script (for when it's built)

```bash
# 1. Start server
nodus serve --port 7331

# 2. Plan a goal
RUN_ID=$(curl -s -X POST http://localhost:7331/goal/plan \
  -H "Content-Type: application/json" \
  -d '{"goal": "Fetch https://jsonplaceholder.typicode.com/users and store first 3 names"}' \
  | python -c "import json,sys; print(json.load(sys.stdin)['run_id'])")

# 3. Show the plan
curl http://localhost:7331/goal/runs/$RUN_ID | python -m json.tool

# 4. Approve
curl -X POST http://localhost:7331/goal/runs/$RUN_ID/approve

# 5. Follow events
curl "http://localhost:7331/runtime/events?run_id=$RUN_ID"
```

---

*Last updated: 2026-06-07. Track implementation in GitHub issues.*
