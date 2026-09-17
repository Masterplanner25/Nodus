# Demo 2 — Agent-triggered workflow orchestration (design doc)

**Status:** Not runnable today. This document captures what the demo would
look like, what infrastructure already exists, and what needs to be built.

**Last reviewed:** 2026-09-16 against nodus-lang 5.13.0. Written 2026-06-07
against 4.0.x; the *What already exists* and *What is missing* sections were
re-checked against `src/nodus/services/server.py` and are current.

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
nodus serve --port 7331 --allow-network --allowed-hosts jsonplaceholder.typicode.com
```

Since 5.10.0 code submitted to `nodus serve` is denied network, subprocess
and environment access by default, and since 5.13.0 the filesystem is jailed
to the server's working directory. A plan whose first step is an HTTP fetch
needs the grant on the command line — narrowed to the host it will reach.

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
| Workflow run/plan/resume | ✅ Live | `POST /workflow/run`, `/workflow/plan`, `/workflow/resume` |
| Workflow run list / inspect | ✅ Live | `GET /workflow/runs`, `GET /workflow/runs/{id}` |
| **Park a run until a human acts** | ✅ Live (5.4.0) | `workflow_wait("approval", ...)` in a step; the run is recorded `waiting` |
| **Deliver the event that resumes it** | ✅ Live (5.4.0) | `POST /workflow/deliver`, or `nodus workflow deliver <event>` |
| Runtime events stream | ✅ Live | `GET /runtime/events` |
| Dead-letter replay | ✅ Live | `POST /workflow/replay` |
| Worker registration / polling | ✅ Live | `POST /worker/register`, `/worker/poll`, `/worker/heartbeat`, `/worker/result` |
| Memory read/write | ✅ Live | `POST /memory`, `DELETE /memory/{key}` |
| Agent call | ✅ Live | `POST /agent/call` |
| **Step-level retry with backoff** | ✅ Live | `step x with { retries: N, retry_delay_ms: M }`; `goal` retries identically (#393) |
| **The plan → act pattern, in the language** | ✅ Live (5.8.0, #465) | `examples/plan_then_act.nd`; `docs/guide/workflows-and-tasks.md` §9 |
| Server-side capability confinement | ✅ Live (5.10.0 / 5.13.0) | `nodus serve --allow-network --allowed-hosts ...` etc. |

The three bold rows are what changed since this document was written. The
approval gate this demo wants is no longer missing as a *primitive* — a step
that calls `workflow_wait("plan.approved")` parks the run, and
`POST /workflow/deliver` with that event resumes it. `docs/guide/real-world-integration.md`
shows exactly that shape for an approval-gated deployment.

---

## What is missing

### 1. A goal-level approval endpoint (the core gap, narrowed)

`POST /goal/plan` returns a plan; `POST /goal/run` executes one. There is
still no `pending_approval` state on a *goal* run and no
`POST /goal/runs/{id}/approve` / `reject`.

But the demo does not need them to be new machinery. The shortest path is a
workflow whose first step produces the plan and whose second step is gated:

```nd
workflow plan_then_act {
    state plan = ""
    step plan_it {
        plan = agent_call("planner", request)
        checkpoint "planned"
    }
    step await_approval after plan_it {
        return workflow_wait("plan.approved")
    }
    step act after await_approval {
        return agent_call("executor", plan)
    }
}
```

`POST /workflow/run` starts it; the run parks at `await_approval` as
`waiting`; `POST /workflow/deliver {"event_type": "plan.approved"}` is the
approve button. That gives the demo its gate with **zero server changes**.
The `/goal/runs/{id}/approve` route becomes a thin alias over deliver.

Verified 2026-09-16 with the CLI form of the same cycle (the `agent_call`s
replaced by literals): `nodus run` left the run `waiting` at checkpoint
`planned`; `nodus workflow deliver plan.approved --all` resumed it, the
`act` step printed the plan out of `state`, and `nodus workflow runs`
showed it `completed`.

**Build estimate:** half a day for the workflow and a script that drives it;
one more day if the goal-level routes are wanted as well.

### 2. Goal run list / status endpoint

`GET /workflow/runs` and `GET /workflow/runs/{id}` exist and cover a run
started through `/workflow/run`. There is still no `GET /goal/runs`. If the
demo takes the workflow-shaped path above, this gap does not apply.

**Build estimate:** half a day, if wanted.

### 3. Event stream filtering by run_id

`GET /runtime/events` returns the events of the service's current VM and
takes no query parameters (`services/api.py`, `services/server.py`). A
polling client sees every event from every run.

**Build estimate:** half a day. Add a `run_id` query param that filters the
event log.

### 4. Retry on the demo's HTTP step

Was "not wired into goal execution" in June; step-level retry is in the DSL
now and `goal` uses the same path (#393). What is left is only that a
*generated* plan carries `with { retries: N }` on the fetch step.

**Build estimate:** none beyond writing the step.

---

## Implementation order (if we want this runnable)

1. **Workflow-shaped approval gate** — `plan_then_act` with a
   `workflow_wait` step, driven by `POST /workflow/run` + `/workflow/deliver`.
   (~0.5 days)
2. **Event stream `run_id` filter** — `GET /runtime/events?run_id=X`.
   (~0.5 days)
3. **Optional: goal-level routes** — `POST /goal/runs/{id}/approve` and
   `GET /goal/runs` as aliases over the workflow store. (~1 day)

Total to a runnable demo: **~1 day**; ~2 with the goal-level routes. This was
~3.5 days when written; the difference is the resume/persistence cluster
(5.4.0) and #465.

---

## History

The two identifiers this section used to cite are closed: **E2E-01** (#190,
pre-run observer registration) and **E2E-02** (#191, per-coroutine timeout
on `NodusRuntime`) were both fixed in PR #200 on 2026-06-07, the day this
document was written. Neither is a dependency of the demo any more.

---

## Demo script (for when it's built)

```bash
# 1. Start server (grant only the host the plan will reach)
nodus serve --port 7331 --allow-network --allowed-hosts jsonplaceholder.typicode.com

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
