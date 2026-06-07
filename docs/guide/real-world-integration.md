# Real-World Integration: Agent Orchestration with WAIT/RESUME

This guide shows how to build a production-shaped AI agent execution loop
using Nodus as the orchestration layer. It covers the architectural boundary
between `.nd` and Python, the WAIT/RESUME approval gate pattern, event-driven
flow resumption, and dynamic workflow generation from intent.

**Prerequisites:** Read [embedding-nodus.md](embedding-nodus.md) and
[workflows-and-tasks.md](workflows-and-tasks.md) first. This guide does not
re-explain `NodusRuntime`, `workflow { }`, or step syntax — it shows how they
compose in a real system.

**Full runnable example:** `C:\dev\sed` (or the companion GitHub repo).
Every code snippet here is drawn from that example verbatim.

---

## The scenario

An AI agent execution loop — call it AINDY — needs to:

1. Analyze a goal
2. Pause for human approval before execution
3. Execute only if approved
4. Evaluate the result

This is a common pattern: orchestration with a governance gate. The loop
must survive process restarts (durable state), handle retries on failure
(crash-safe attempt tracking), and be event-driven on the resume side
(no polling). It needs to scale to indefinitely long waits — hours or days
between human approval events.

---

## Architecture: what Nodus owns vs what the host owns

The most important decision in any Nodus integration is where to draw the line.

| Concern | Owner | Why |
|---------|-------|-----|
| DAG execution order | Nodus `.nd` | `step after` is the primitive |
| Retry + attempt tracking | Nodus `.nd` | `step with { retries }` writes to durable graph JSON |
| WAIT / RESUME protocol | Nodus `.nd` | `workflow_wait()` / `workflow_resume_payload()` are native builtins |
| Checkpoints | Nodus `.nd` | `checkpoint "label"` persists to graph JSON |
| Event routing (which run to resume) | Python host | Nodus has no event-bus primitive |
| Outcome scoring / strategy learning | Python host | No ML primitive in Nodus |
| Policy / governance enforcement | Python host | No capability-check primitive |
| Intent → workflow compilation | Python host | No "compile plan to workflow" primitive |
| Auth on resume | Python host / API layer | Cannot be expressed in DSL |

Nodus owns the orchestration shell. Python owns everything that requires
application-specific logic, external state, or security enforcement.

---

## Part 1: The workflow

### Linear variant

```nodus
workflow aindy_execute {
    state confidence = 0

    step analyze with { retries: 3, retry_delay_ms: 500 } {
        checkpoint "after_analyze"
        return 1
    }

    step execute after analyze {
        checkpoint "after_execute"
        return analyze + 1
    }

    step evaluate after execute {
        confidence = 90
        return confidence
    }
}

let result = run_workflow(aindy_execute)
```

`step analyze with { retries: 3, retry_delay_ms: 500 }` — attempt count is
written to `.nodus/graphs/<id>.json` on every failure. A process crash between
retries does not reset the counter. This fixes the most common prototype bug:
an in-memory dict that resets to zero on restart.

`checkpoint "after_analyze"` — records a recovery point in the graph JSON.
After a process restart, the host can resume from the last checkpoint rather
than re-running steps that already succeeded.

`state confidence = 0` — workflow-level mutable state persisted in the graph
JSON after each step. Downstream steps can read it.

### Gated variant with WAIT/RESUME

```nodus
workflow aindy_gated_execute {
    state confidence = 0
    state approved = false

    step analyze with { retries: 3, retry_delay_ms: 500 } {
        checkpoint "after_analyze"
        return 1
    }

    step gate after analyze {
        return workflow_wait("aindy.approval.granted", "approve-aindy", {kind: "aindy_approval"})
    }

    step execute after gate {
        let payload = workflow_resume_payload()
        if (payload == nil) {
            throw "Execution blocked: no approval payload received"
        }
        approved = payload["approved"]
        if (approved == false) {
            throw "Execution blocked: approval denied"
        }
        checkpoint "after_execute"
        return 1
    }

    step evaluate after execute {
        confidence = 90
        return confidence
    }
}
```

`workflow_wait("aindy.approval.granted", "approve-aindy", {kind: "aindy_approval"})` — suspends
the flow run and records the wait in the store. The run status becomes
`"waiting"`. No timeout is set, so the wait is indefinite — required for
long-lived human-approval flows. To time-box, pass a `deadline_ms` as the
fourth argument.

`workflow_resume_payload()` — retrieves the dict the host passed in the
resume call. This is how the human's decision (approved/denied) crosses from
the Python event router into the Nodus step body.

The `gate` step is a pure orchestration step — it does nothing except park the
flow until the external signal arrives. The `execute` step reads the payload
and decides whether to proceed. The design keeps the policy logic in the step
body and the routing logic in the host.

---

## Part 2: The embedded bridge

### Why embedded, not serve mode

Nodus can run as a standalone HTTP server (`nodus serve`) or as an embedded
library. This example uses embedded for three reasons:

1. The event router needs to call `resume_workflow()` synchronously inside
   the same process — no HTTP round-trip.
2. The sweep loop rehydrates waiting runs in-process after restarts.
3. The host's DB sessions for outcome tracking live in the same process;
   embedded mode keeps the import graph coherent.

For horizontal scaling across multiple workers, put a distributed work queue
in front of the bridge and keep the embedded runtime per-worker. Switching to
serve mode adds a network hop per resume and requires running the Nodus server
as a separate process.

### Store and runner setup

```python
from nodus_lang_workflow.runner import WorkflowFrameworkRunner
from nodus_lang_workflow.store import LocalWorkflowStore, SQLiteWorkflowStore

def _make_store():
    if os.environ.get("AINDY_STORE_BACKEND") == "sqlite":
        return SQLiteWorkflowStore(path=".nodus/aindy.sqlite3")
    return LocalWorkflowStore(root=".nodus/workflow_framework")

_store = _make_store()
_runner = WorkflowFrameworkRunner(_store)
```

`LocalWorkflowStore` writes one JSON file per run under the store root —
suitable for development and single-process deployments. `SQLiteWorkflowStore`
is cross-process safe and better for restarts under load. For Postgres-backed
multi-worker deployments, subclass `WorkflowStore` and pass it to the runner.

### Running a workflow file

```python
from nodus.tooling.runner import run_workflow_code
from nodus.cli import cli as nodus_cli
from nodus.vm.vm import VM

def _fresh_vm(source_path=None):
    return VM([], {}, code_locs=[], source_path=source_path)

def run_nd_file(nd_path, initial_globals=None):
    # SEC-001: authenticate before calling this.
    with open(nd_path, encoding="utf-8") as fh:
        source = fh.read()

    vm = _fresh_vm(source_path=nd_path)
    if initial_globals:
        for key, value in initial_globals.items():
            vm.globals[key] = value

    with nodus_cli._project_root_context(PROJECT_ROOT):
        result, _vm = run_workflow_code(
            vm, source, filename=nd_path, project_root=PROJECT_ROOT
        )
    return result
```

`initial_globals` — the mechanism for passing host-side values into the
workflow. The `.nd` step bodies read them as ordinary Nodus variables.
This is the bridge for pre-computed values (goals, configuration) that
the host knows before the workflow starts.

`_project_root_context` — sets the project root so graph JSON and bytecode
cache resolve correctly relative to the service working directory.

### Resuming a waiting run

```python
from nodus.tooling.runner import resume_workflow as nodus_resume_workflow

def resume_nd(graph_id, checkpoint=None, resume_payload=None,
              event_type=None, correlation_key=None):
    # SEC-001: authenticate and verify caller is permitted to resume graph_id.
    with nodus_cli._project_root_context(PROJECT_ROOT):
        result, _vm = nodus_resume_workflow(
            graph_id,
            checkpoint,
            resume_payload=resume_payload,
            event_type=event_type,
            correlation_key=correlation_key,
        )
    return result
```

### The sweep loop

After a process restart, waiting flow runs are not in memory. The sweep loop
discovers them from the store and rehydrates them into the scheduler so they
can receive resume events.

```python
import threading, time

class SweepLoop:
    def __init__(self, interval_s=30.0):
        self._interval = interval_s
        self._stop = threading.Event()

    def start(self):
        t = threading.Thread(target=self._loop, daemon=True, name="aindy-sweep")
        t.start()

    def _loop(self):
        while not self._stop.wait(timeout=self._interval):
            try:
                now_ms = int(time.time() * 1000)
                with nodus_cli._project_root_context(PROJECT_ROOT):
                    _runner.sweep(lambda _record: _fresh_vm(), now_ms=now_ms)
            except Exception as exc:
                logger.error("Sweep error: %s", exc)

sweep_loop = SweepLoop(interval_s=30)
```

Always call `sweep_loop.start()` before accepting any traffic. Skipping it
means runs that were in `"waiting"` status when the process last shut down
will never receive resume events after restart.

---

## Part 3: Routing events to waiting flows

Nodus provides the WAIT/RESUME contract. Routing — matching an arriving event
to the correct waiting run — is the host's job.

```python
from nodus_lang_workflow.runner import WorkflowFrameworkRunner

class EventRouter:
    def __init__(self, runner: WorkflowFrameworkRunner):
        self._runner = runner

    def route_event(self, event_type, correlation_key, payload):
        # 1. Query waiting runs — short-lived session, closed before any resume.
        waiting = self._runner.store.list_runs_filtered(statuses={"waiting"})
        targets = [
            r for r in waiting
            if r.wait is not None
            and r.wait.event_type == event_type
            and r.wait.correlation_key == correlation_key
        ]
        run_ids = [r.run_id for r in targets]

        # 2. Resume each run in isolation.
        resumed = []
        for run_id in run_ids:
            vm = _fresh_vm()
            result = self._runner.resume_workflow(
                vm,
                run_id,
                resume_payload=payload,
                event_type=event_type,
                correlation_key=correlation_key,
                rebuild_graph=vm._rebuild_workflow_graph,
            )
            if result.get("ok"):
                resumed.append(run_id)
        return resumed
```

The session that queries waiting runs is closed before any resume begins.
Opening one session for the query and then calling `resume_workflow()` (which
opens its own session internally) inside the same session causes nested
sessions on the same connection — a deadlock hazard on `commit()` that the
prototype had. Closing the query session first eliminates it entirely.

`rebuild_graph=vm._rebuild_workflow_graph` — pass the VM's own bound method
directly. Do not wrap it in a lambda; the method requires two arguments
(`graph_id`, `state`) and must be the same VM instance used for the resume.

---

## Part 4: Generating workflows from intent

When the exact workflow structure is not known at write time, the host can
generate `.nd` source dynamically and feed it to the bridge.

```python
def compile_plan_to_nd(plan, flow_name="dynamic_flow"):
    steps = plan.get("steps", [])
    lines = [f"workflow {flow_name} {{"]
    for i, step in enumerate(steps):
        dep = f" after {steps[i-1]}" if i > 0 else ""
        lines += [
            f"    step {step}{dep} {{",
            f'        checkpoint "after_{step}"',
            f"        return {steps[i-1] + ' + 1' if i > 0 else '1'}",
            "    }",
            "",
        ]
    lines.append("}")
    return "\n".join(lines)

def execute_intent(intent_data):
    intent_type = intent_data.get("intent", "unknown")
    enforce_policy(intent_type, intent_data)   # host-side, before compilation
    plan = generate_plan_from_intent(intent_data)
    nd_source = compile_plan_to_nd(plan, flow_name=f"aindy_{intent_type}")
    return run_nd_source(nd_source, initial_globals={"goal": intent_data})
```

The generated `.nd` source is an orchestration shell — it provides DAG
ordering, retry tracking, and checkpoints. Step bodies delegate real work
back to the host via `initial_globals` callables or by reading host-provided
values. Nodus executes the structure; Python provides the logic.

Policy enforcement runs before compilation so blocked intent types never
become running workflow runs. This is the same boundary as
`AINDY/runtime/nodus_security.py` in the full aindy-runtime.

---

## Two flags to carry everywhere

### SEC-001 — auth at the API layer

`run_nd_file()`, `run_nd_source()`, and `resume_nd()` do not enforce
authentication. The `.nd` file cannot enforce it either. Every call into
the bridge must be gated by an auth check in the API layer — a FastAPI
dependency, middleware, or decorator — before the bridge function is invoked.

For resume specifically: verify the caller is permitted to resume the
specific `graph_id` they are requesting, not just that they hold a valid
token. Unchecked resume endpoints allow arbitrary workflow manipulation.

### SCHED-001 — always start the sweep loop

`workflow_wait()` without a `deadline_ms` argument waits indefinitely. When
the process restarts, those waiting runs exist in the store but are not in
memory. Without `sweep_loop.start()`, they are stranded — they can never
receive resume events.

Call `sweep_loop.start()` at service startup, before the first request is
accepted. In a multi-worker deployment, every worker runs its own sweep loop;
the store backend (SQLite or Postgres) serializes concurrent sweep attempts.

---

## Running the full example

The full runnable example lives at `C:\dev\sed`. It includes `host/db_models.py`
(SQLAlchemy models for outcome tracking and strategy learning) and
`host/strategy.py` (best-score selection across past runs) — two
purely host-side subsystems that have no Nodus equivalent.

```bash
# Install dependencies
pip install nodus-lang nodus-lang-workflow sqlalchemy psycopg2-binary

# Run the linear flow
python -c "
from host.bridge import run_nd_file, sweep_loop
sweep_loop.start()
result = run_nd_file('nodus/aindy_core.nd')
print(result)
"

# Run the gated flow and approve it
python -c "
from host.bridge import run_nd_file, sweep_loop
from host.event_router import EventRouter
from host.bridge import _runner
sweep_loop.start()
result = run_nd_file('nodus/aindy_core.nd', initial_globals={'_run_gated': True})
print('Waiting:', result)
router = EventRouter(_runner)
router.route_event('aindy.approval.granted', 'approve-aindy', {'approved': True})
"
```

For a reference implementation that shows these patterns running at
production scale (Redis pub/sub, Postgres-backed store, distributed workers,
FastAPI endpoints, platform UI), see `C:\dev\aindy-runtime`.

For a complementary example using **serve mode** instead of embedded — where a
thin FastAPI shell drives `nodus serve` via HTTP, handles request-level auth, and
maintains a durable SQL audit log — see
[`examples/webhook_bridge/`](../../examples/webhook_bridge/).

---

## Where this fits in the guide

| Guide | What it covers |
|-------|---------------|
| [embedding-nodus.md](embedding-nodus.md) | `NodusRuntime` API, `run_source`, sandbox, `register_function` |
| [workflows-and-tasks.md](workflows-and-tasks.md) | `workflow { }` DSL, steps, state, checkpoints, retries |
| **This guide** | Embedding + workflows together; WAIT/RESUME; event routing; dynamic `.nd` generation |
| [ai-primitives.md](ai-primitives.md) | `std:tool`, `std:effects`, `std:retry`, `std:circuit_breaker` |
