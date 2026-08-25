"""Task graph runtime support."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast
import copy
import dataclasses
import hashlib
import json
import sys
import os
import threading
import uuid

from nodus.runtime.runtime_stats import runtime_time_ms
from nodus.runtime.coroutine import Coroutine
from nodus.orchestration.workflow_state import (
    TrackedState,
    is_fold_policy,
    checkpoints_public,
    clone_state,
    concurrent_write_conflicts,
)


class WorkflowRebuildError(Exception):
    """Rebuilding a persisted run's graph from its source failed.

    Distinct from "this graph_id is not known" (#399). Resume used to answer both
    with ``Unknown graph``, because the rebuild swallowed every exception and
    returned ``None`` — so a run that ``nodus workflow runs`` listed as waiting,
    whose state file was on disk, reported that it did not exist. The real cause
    was discarded, which is why the defect survived across releases.

    ``reason`` is the short, user-facing explanation; ``cause`` is the underlying
    exception when the failure came from re-executing the module.
    """

    def __init__(self, reason: str, *, cause: BaseException | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.cause = cause

    def describe(self) -> str:
        if self.cause is None:
            return self.reason
        return f"{self.reason}: {type(self.cause).__name__}: {self.cause}"


# The dependency outcomes a step may declare it accepts, via `with { on: [...] }`.
# Deliberately the same names `statuses` reports, so what a run tells you and what
# a step can ask for are one vocabulary rather than two that drift.
#
# Only the two a dependency can actually *reach while the run is going*. The other
# reported statuses are conclusions drawn once the run winds down: `upstream_failed`
# and `cancelled` are computed by walking the finished graph, so a step waiting on
# one would never become ready and the option would be a knob that silently never
# fires -- "declared but not enforced", which this codebase has five other instances
# of.
#
# `skipped` is admissible because a guard decides it *while the run is going*, which
# is what separates it from the two above. `omitted` is not: it is the transitive
# closure of `skipped`, drawn at the end, so it belongs with `upstream_failed`.
#
# This comment used to say `skipped` was absent "until a conditional-edge design
# exists (#471)", one line above a tuple that contains it -- written before step
# guards landed and not revisited when they did. `TASK_STATUSES` below now names the
# reported vocabulary, and `tests/test_status_vocabulary.py` holds the guide to both
# tuples, because the same staleness reached the CHANGELOG and the README.
JOIN_ON_STATES = ("completed", "failed", "skipped")

# Every value `task_statuses()` can report. Named here rather than left implicit in
# that function's if-chain so the guide can be pinned to it.
TASK_STATUSES = (
    "completed",
    "failed",
    "upstream_failed",
    "skipped",
    "omitted",
    "cancelled",
    "abandoned",
)

# What `after` has always meant: every dependency must have produced a value.
DEFAULT_JOIN_ON = frozenset({"completed"})


@dataclass
class TaskNode:
    task_id: str
    function: object
    dependencies: list["TaskNode"] = field(default_factory=list)
    # Which dependency outcomes satisfy this task's join (#475).
    on_states: frozenset[str] = DEFAULT_JOIN_ON
    # `when <predicate>` as data -- a nested map the runtime walks against the
    # checkpoints reached so far. None means unconditional (#471).
    when: object | None = None
    step_name: str | None = None
    worker: str | None = None
    worker_timeout_ms: float | None = None
    result: object | None = None
    status: str = "pending"
    started_at: float | None = None
    finished_at: float | None = None
    error: str | None = None
    timeout_ms: float | None = None
    attempts: int = 0
    max_retries: int = 0
    retry_delay_ms: float = 0.0
    last_error: str | None = None
    next_retry_at: float | None = None
    retry_classification: str | None = None
    cache: bool = False
    cache_key: str | None = None


@dataclass
class TaskGraph:
    tasks: list[TaskNode]
    graph_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


_GRAPH_REGISTRY: dict[str, TaskGraph] = {}
_GRAPH_VMS: dict[str, object] = {}
_DEFAULT_DISPATCHER = None
_GRAPH_ROOT = os.path.join(".nodus", "graphs")
_STATE_LOCK = threading.Lock()


def set_default_dispatcher(dispatcher) -> None:
    global _DEFAULT_DISPATCHER
    _DEFAULT_DISPATCHER = dispatcher


def _graph_state_path(graph_id: str) -> str:
    root = _ensure_graph_root()
    return os.path.join(root, f"{graph_id}.json")


def _checkpoint_path(graph_id: str) -> str:
    root = _ensure_graph_root()
    return os.path.join(root, f"{graph_id}.checkpoint.json")


def _ensure_graph_root() -> str:
    os.makedirs(_GRAPH_ROOT, exist_ok=True)
    return _GRAPH_ROOT


def _fsync_directory(path: str) -> None:
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        try:
            os.close(fd)
        except OSError:
            pass


def _atomic_write_json(path: str, data: dict) -> None:
    tmp_path = f"{path}.{uuid.uuid4().hex}.tmp"
    dirpath = os.path.dirname(path) or "."
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, sort_keys=True, separators=(",", ":"))
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp_path, path)
    _fsync_directory(dirpath)


def _scheduler_queue_snapshot(vm) -> list[str]:
    scheduler = getattr(vm, "scheduler", None)
    if scheduler is None:
        return []
    queue = getattr(scheduler, "ready_queue", None)
    if queue is None:
        return []
    result = []
    for coroutine in queue:
        name = getattr(coroutine, "name", None)
        if isinstance(name, str):
            result.append(name)
    return result


def _new_graph_id() -> str:
    return f"g_{uuid.uuid4().hex[:8]}"


def register_graph(graph: TaskGraph) -> TaskGraph:
    if graph.graph_id is None:
        graph.graph_id = _new_graph_id()
    _GRAPH_REGISTRY[graph.graph_id] = graph
    return graph


def get_registered_graph(graph_id: str) -> TaskGraph | None:
    return _GRAPH_REGISTRY.get(graph_id)


def register_graph_vm(graph_id: str, vm) -> None:
    if graph_id:
        _GRAPH_VMS[graph_id] = vm


def get_registered_vm(graph_id: str):
    return _GRAPH_VMS.get(graph_id)


def _durable_state(workflow_state, graph):
    """Drop cells declared `durable: false` before the state is written to disk.

    A cell holding a live handle -- a connection, a channel, a memoized comparator
    -- has no meaning after a resume, and today there was no way to say so: every
    cell was persisted, and a value `json` cannot encode killed the run at the
    first persist with a message naming no cell (#498).

    Excluded rather than emptied. A cell restored as `nil` would look like a value
    the workflow had set, which is a different lie from the one being fixed; a
    resumed step re-derives it instead.
    """
    if not isinstance(workflow_state, dict):
        return workflow_state
    policies = {}
    if isinstance(graph.metadata, dict):
        raw = graph.metadata.get("state_policies")
        if isinstance(raw, dict):
            policies = raw
    skip = {
        key for key, policy in policies.items()
        if isinstance(policy, dict) and policy.get("durable") is False
    }
    if not skip:
        return workflow_state
    return {key: value for key, value in workflow_state.items() if key not in skip}


def _persist_graph_state(
    graph: TaskGraph,
    tasks: list[TaskNode],
    attempts: dict[str, float],
    results: dict[str, object],
    status: str,
    pending_queue: list[str],
    task_values: dict[str, object],
    workflow_state: object | None,
    checkpoints: list[dict] | None,
    engine_checkpoints: list[dict] | None,
    vm,
) -> dict:
    metadata = graph.metadata
    if isinstance(metadata, dict):
        metadata = copy.deepcopy(metadata)
    state: dict[str, Any] = {
        "graph_id": graph.graph_id,
        "status": status,
        "tasks": {},
        "metadata": metadata,
        "pending": list(pending_queue),
        "scheduler_queue": _scheduler_queue_snapshot(vm),
        "task_outputs": {tid: task_values.get(tid) for tid in task_values},
        "results": {tid: results.get(tid) for tid in results},
        "workflow_state": _durable_state(workflow_state, graph),
        "checkpoints": checkpoints,
        "engine_checkpoints": engine_checkpoints,
        "updated_at": runtime_time_ms(),
    }
    if isinstance(graph.metadata, dict):
        for key in ("workflow_name", "goal_name", "execution_kind"):
            value = graph.metadata.get(key)
            if value is not None:
                state[key] = value
    for task in tasks:
        task_state: dict[str, object | float] = {"state": task.status, "attempts": float(task.attempts)}
        if task.task_id in results:
            task_state["result"] = results[task.task_id]
        if task.last_error:
            task_state["last_error"] = task.last_error
        if task.step_name is not None:
            task_state["step_name"] = task.step_name
        if task.worker is not None:
            task_state["worker"] = task.worker
        if task.worker_timeout_ms is not None:
            task_state["worker_timeout_ms"] = task.worker_timeout_ms
        if task.started_at is not None:
            task_state["started_at"] = task.started_at
        if task.finished_at is not None:
            task_state["finished_at"] = task.finished_at
        if task.timeout_ms is not None:
            task_state["timeout_ms"] = task.timeout_ms
        if task.max_retries:
            task_state["max_retries"] = float(task.max_retries)
        if task.retry_delay_ms:
            task_state["retry_delay_ms"] = float(task.retry_delay_ms)
        if task.next_retry_at is not None:
            task_state["next_retry_at"] = task.next_retry_at
        if task.retry_classification is not None:
            task_state["retry_classification"] = task.retry_classification
        if task.cache:
            task_state["cache"] = True
        if task.cache_key is not None:
            task_state["cache_key"] = task.cache_key
        if task.last_error:
            task_state["last_error"] = task.last_error
        state["tasks"][task.task_id] = task_state
    assert graph.graph_id is not None
    with _STATE_LOCK:
        _atomic_write_json(_graph_state_path(graph.graph_id), state)
    return state


def _load_graph_state(graph_id: str) -> dict | None:
    path = _graph_state_path(graph_id)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return _normalize_workflow_snapshot(json.load(f))


def load_checkpoint(graph_id: str) -> dict | None:
    path = _checkpoint_path(graph_id)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return _normalize_workflow_snapshot(json.load(f))


def _normalize_checkpoint_lists(payload: dict) -> dict:
    if not isinstance(payload, dict):
        return payload
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
        payload["metadata"] = metadata
    raw_top_level_checkpoints = payload.get("checkpoints")
    public_checkpoints = raw_top_level_checkpoints
    engine_checkpoints = payload.get("engine_checkpoints")
    legacy_meta_checkpoints = metadata.get("checkpoints")
    legacy_meta_public = metadata.get("workflow_checkpoints")
    legacy_meta_engine = metadata.get("engine_checkpoints")

    if not isinstance(public_checkpoints, list):
        if isinstance(legacy_meta_public, list):
            public_checkpoints = checkpoints_public(legacy_meta_public)
        elif isinstance(legacy_meta_checkpoints, list):
            public_checkpoints = checkpoints_public(legacy_meta_checkpoints)
        else:
            public_checkpoints = []
        payload["checkpoints"] = public_checkpoints
    else:
        public_checkpoints = checkpoints_public(public_checkpoints)
        payload["checkpoints"] = public_checkpoints

    if not isinstance(engine_checkpoints, list):
        if isinstance(legacy_meta_engine, list):
            engine_checkpoints = copy.deepcopy(legacy_meta_engine)
        elif isinstance(legacy_meta_checkpoints, list):
            engine_checkpoints = copy.deepcopy(legacy_meta_checkpoints)
        elif isinstance(raw_top_level_checkpoints, list) and any("state" in entry for entry in raw_top_level_checkpoints if isinstance(entry, dict)):
            engine_checkpoints = copy.deepcopy(raw_top_level_checkpoints)
        else:
            engine_checkpoints = []
        payload["engine_checkpoints"] = engine_checkpoints

    metadata["workflow_checkpoints"] = checkpoints_public(public_checkpoints)
    metadata["engine_checkpoints"] = copy.deepcopy(engine_checkpoints)
    metadata["checkpoints"] = metadata["workflow_checkpoints"]
    return payload


def _normalize_workflow_snapshot(payload: dict | None) -> dict | None:
    if not isinstance(payload, dict):
        return payload
    return _normalize_checkpoint_lists(payload)


def _load_raw_json(path: str) -> dict | None:
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload if isinstance(payload, dict) else None


def delete_checkpoint(graph_id: str) -> None:
    path = _checkpoint_path(graph_id)
    try:
        os.remove(path)
    except OSError:
        pass


def delete_graph_state(graph_id: str) -> None:
    path = _graph_state_path(graph_id)
    try:
        os.remove(path)
    except OSError:
        pass


def load_graph_state(graph_id: str) -> dict | None:
    return _load_graph_state(graph_id)


def migrate_graph_snapshot(graph_id: str) -> dict:
    graph_path = _graph_state_path(graph_id)
    checkpoint_path = _checkpoint_path(graph_id)
    graph_state_updated = False
    checkpoint_updated = False

    raw_graph_state = _load_raw_json(graph_path)
    if isinstance(raw_graph_state, dict):
        normalized_graph_state = _normalize_workflow_snapshot(copy.deepcopy(raw_graph_state))
        assert isinstance(normalized_graph_state, dict)
        if normalized_graph_state != raw_graph_state:
            with _STATE_LOCK:
                _atomic_write_json(graph_path, normalized_graph_state)
            graph_state_updated = True

    raw_checkpoint = _load_raw_json(checkpoint_path)
    if isinstance(raw_checkpoint, dict):
        normalized_checkpoint = _normalize_workflow_snapshot(copy.deepcopy(raw_checkpoint))
        assert isinstance(normalized_checkpoint, dict)
        if normalized_checkpoint != raw_checkpoint:
            with _STATE_LOCK:
                _atomic_write_json(checkpoint_path, normalized_checkpoint)
            checkpoint_updated = True

    return {
        "graph_id": graph_id,
        "graph_state_exists": isinstance(raw_graph_state, dict),
        "checkpoint_exists": isinstance(raw_checkpoint, dict),
        "graph_state_updated": graph_state_updated,
        "checkpoint_updated": checkpoint_updated,
        "updated": graph_state_updated or checkpoint_updated,
    }


def migrate_all_graph_snapshots() -> list[dict]:
    return [migrate_graph_snapshot(graph_id) for graph_id in list_graph_ids()]


def latest_graph_state() -> tuple[str | None, dict | None]:
    root = _ensure_graph_root()
    if not os.path.isdir(root):
        return None, None
    candidates = [name for name in os.listdir(root) if name.endswith(".json") and not name.endswith(".checkpoint.json")]
    if not candidates:
        return None, None
    candidates.sort()
    latest = candidates[-1]
    graph_id = latest.rsplit(".", 1)[0]
    return graph_id, _load_graph_state(graph_id)


def list_graph_ids() -> list[str]:
    root = _ensure_graph_root()
    if not os.path.isdir(root):
        return []
    ids = [
        name[:-5]
        for name in os.listdir(root)
        if name.endswith(".json") and not name.endswith(".checkpoint.json")
    ]
    ids.sort()
    return ids


def list_graph_snapshots_info() -> list[dict]:
    infos: list[dict] = []
    for graph_id in list_graph_ids():
        state = load_graph_state(graph_id)
        if not isinstance(state, dict):
            continue
        checkpoint = load_checkpoint(graph_id)
        _meta_raw = state.get("metadata")
        metadata: dict[str, Any] = _meta_raw if isinstance(_meta_raw, dict) else {}
        info = {
            "graph_id": graph_id,
            "status": state.get("status"),
            "workflow": state.get("workflow_name") or metadata.get("workflow_name"),
            "goal": state.get("goal_name") or metadata.get("goal_name"),
            "execution_kind": state.get("execution_kind") or metadata.get("execution_kind") or metadata.get("kind"),
            "updated_at": state.get("updated_at"),
            "pending": len(state.get("pending") or []),
            "tasks": len(state.get("tasks") or {}),
            "has_checkpoint": checkpoint is not None,
            "checkpoint_label": checkpoint.get("label") if isinstance(checkpoint, dict) else None,
            "checkpoint_timestamp": checkpoint.get("timestamp") if isinstance(checkpoint, dict) else None,
        }
        infos.append(info)
    return infos


def persist_checkpoint_snapshot(graph_id: str, snapshot: dict, label: str | None) -> None:
    checkpoint = {
        "graph_id": graph_id,
        "label": label,
        "timestamp": runtime_time_ms(),
        "status": snapshot.get("status"),
        "tasks": snapshot.get("tasks"),
        "pending": snapshot.get("pending"),
        "scheduler_queue": snapshot.get("scheduler_queue"),
        "task_outputs": snapshot.get("task_outputs"),
        "results": snapshot.get("results"),
        "workflow_state": snapshot.get("workflow_state"),
        "metadata": snapshot.get("metadata"),
        "checkpoints": snapshot.get("checkpoints"),
        "engine_checkpoints": snapshot.get("engine_checkpoints"),
    }
    with _STATE_LOCK:
        _atomic_write_json(_checkpoint_path(graph_id), checkpoint)


def _merge_resume_state(state: dict | None, checkpoint: dict | None) -> dict | None:
    if state is None and checkpoint is None:
        return None
    merged = dict(state) if isinstance(state, dict) else {}
    if isinstance(checkpoint, dict):
        merged.setdefault("tasks", {})
        merged_tasks = dict(merged.get("tasks") or {})
        checkpoint_tasks = checkpoint.get("tasks")
        if isinstance(checkpoint_tasks, dict):
            merged_tasks.update(checkpoint_tasks)
        merged["tasks"] = merged_tasks
        for key in ("pending", "scheduler_queue", "workflow_state", "metadata", "results", "task_outputs", "engine_checkpoints"):
            if key in checkpoint:
                merged[key] = checkpoint[key]
        if "label" in checkpoint:
            merged["checkpoint_label"] = checkpoint["label"]
    return merged


def _workflow_wait_info(value) -> dict | None:
    if not isinstance(value, dict):
        return None
    if value.get("__workflow_wait__") is not True:
        return None
    event_type = value.get("event_type")
    if not isinstance(event_type, str) or not event_type:
        return None
    correlation_key = value.get("correlation_key")
    if not isinstance(correlation_key, str):
        correlation_key = None
    payload = value.get("payload")
    if not isinstance(payload, dict):
        payload = {}
    deadline_ms = value.get("deadline_ms")
    if not isinstance(deadline_ms, (int, float)):
        deadline_ms = None
    return {
        "event_type": event_type,
        "correlation_key": correlation_key,
        "payload": payload,
        "deadline_ms": float(deadline_ms) if deadline_ms is not None else None,
    }


def _detect_cycle_task_ids(tasks: list, results: dict) -> list[str] | None:
    """Return one dependency cycle as task ids, or None.

    Delegates to `support.graph_cycles.detect_cycle` so the parser (#396) and the
    runtime (#323) cannot disagree about what counts as a cycle. `results` is
    unused and kept for call-site compatibility.
    """
    from nodus.support.graph_cycles import detect_cycle

    return detect_cycle(
        {t.task_id: [dep.task_id for dep in t.dependencies] for t in tasks}
    )

def _retry_is_swept() -> bool:
    """Is a sweeper registered to resume runs deferred to ``retry_scheduled``?

    #392/#393. The retry decision used to read ``execution_kind == "workflow"``,
    so it depended on which keyword you wrote and — for `workflow` — on which of
    five entry points you called. Only `nodus workflow-run` had an inline retry
    loop, and only a running `RuntimeService` drives ``sweep()``; everywhere else
    the deferral was simply dropped, and the run returned ``ok: True`` having made
    one attempt.

    Deferral is not a property of the construct. Persisting ``retry_scheduled``
    and returning is correct exactly when something will pick the run back up, so
    ask that instead, for both kinds alike.

    Lazy import for the same reason as ``vm.py``'s workflow-runner imports
    (CIRC-001, #103): ``nodus_lang_workflow`` imports this module.
    """
    try:
        from nodus_lang_workflow.runner import retry_sweeper_active  # noqa: E402
    except ImportError:
        return False
    return retry_sweeper_active()


def run_task_graph(vm, graph: TaskGraph, resume_state: dict | None = None) -> dict:
    tasks = list(graph.tasks)
    graph = register_graph(graph)
    assert graph.graph_id is not None
    register_graph_vm(graph.graph_id, vm)
    for idx, task in enumerate(tasks, 1):
        task.task_id = task.task_id or f"task_{idx}"
    by_id = {task.task_id: task for task in tasks}
    pending = set(task.task_id for task in tasks)
    pending_queue = [task.task_id for task in tasks]
    scheduler_order_map: dict[str, int] = {}
    def _remove_task_from_pending(task_id: str) -> None:
        pending.discard(task_id)
        try:
            pending_queue.remove(task_id)
        except ValueError:
            pass

    def _mark_task_pending(task_id: str) -> None:
        if task_id not in by_id:
            return
        if task_id not in pending:
            pending.add(task_id)
        if task_id not in pending_queue:
            pending_queue.append(task_id)

    results: dict[str, object] = {}
    timings: dict[str, dict] = {}
    attempts: dict[str, float] = {}
    task_values: dict[str, object] = {}
    running: dict[int, TaskNode] = {}
    failed: dict | None = None
    waiting: dict | None = None
    retry_scheduled: dict | None = None
    cache_hits: list[str] = []
    skipped_ids: set[str] = set()
    if not hasattr(vm, "task_cache"):
        vm.task_cache = {}

    dispatcher = getattr(vm, "worker_dispatcher", None)
    if dispatcher is None and _DEFAULT_DISPATCHER is not None and getattr(_DEFAULT_DISPATCHER, "force_dispatch", False):
        if any(task.worker is not None for task in tasks):
            dispatcher = _DEFAULT_DISPATCHER
    if dispatcher is not None and getattr(dispatcher, "event_bus", None) is None:
        dispatcher.event_bus = vm.event_bus

    # #492: `worker:` names where a step runs. With a dispatcher, an unsatisfiable
    # name already fails -- `WorkerPool.submit` waits for a worker advertising the
    # capability and raises "No workers registered with capability: X". Without
    # one, the step fell through to in-process execution and reported success, so
    # `worker: "hardened-sandbox"` and `worker: "gpu"` behaved exactly like no
    # declaration at all.
    #
    # That is the sibling-path shape: the check exists, and only one of the two
    # paths reaches it. The declaration is an isolation intent, so silently
    # running here is the worst available answer.
    #
    # Warned rather than refused for 5.x because running in-process is what every
    # prior release did and a CLI author may be relying on it; 6.0.0 makes it an
    # error, matching how the concurrent-write conflict was staged (#547).
    if dispatcher is None:
        _unhonoured = sorted({t.worker for t in tasks if t.worker is not None})
        if _unhonoured:
            _names = ", ".join(f"'{w}'" for w in _unhonoured)
            print(
                f"warning: {'step declares' if len(_unhonoured) == 1 else 'steps declare'} "
                f"worker {_names}, but no worker dispatcher is registered, so "
                f"{'it runs' if len(_unhonoured) == 1 else 'they run'} in this "
                f"process with no isolation. Run under `nodus serve` with a "
                f"registered worker, or pass `worker_dispatcher=` to "
                f"NodusRuntime. This becomes an error in 6.0.0.",
                file=sys.stderr,
            )
            vm.event_bus.emit_event(
                "workflow_worker_unhonoured",
                data={
                    "workflow": (
                        graph.metadata.get("workflow_name")
                        if isinstance(graph.metadata, dict)
                        else None
                    ),
                    "graph_id": graph.graph_id,
                    "workers": _unhonoured,
                },
            )

    vm.event_bus.emit_event("task_graph_start", data={"tasks": float(len(tasks))})
    workflow_name = graph.metadata.get("workflow_name") if isinstance(graph.metadata, dict) else None
    execution_kind = graph.metadata.get("execution_kind") if isinstance(graph.metadata, dict) else None
    goal_name = graph.metadata.get("goal_name") if isinstance(graph.metadata, dict) else None
    # Can a failed step's retry be *deferred* — persisted as `retry_scheduled` and
    # left for a sweeper — rather than taken in-process? Only if the run is durably
    # tracked at all. `workflow` and `goal` both go through
    # `WorkflowFrameworkRunner.start_graph`, which registers them in the workflow
    # store; a bare `run_graph([...])` is registered nowhere, so deferring one
    # loses it outright. This asks whether the run is durable, NOT which keyword
    # was written — the two flow kinds are treated alike (#392, #393).
    run_is_durable = execution_kind in ("workflow", "goal")

    # ENH-323 (#323): reject dependency cycles up front, before the scheduler runs.
    # A cyclic `after` graph used to be caught only after the run loop drained with
    # tasks stuck pending (see the identical check further below, kept as a backstop).
    # Detecting it here — the moment the graph is built — turns a late, post-stall
    # failure into an immediate one, with the same workflow_error record.
    _cycle_ids = _detect_cycle_task_ids(tasks, {})
    if _cycle_ids:
        _t2s_up = graph.metadata.get("task_to_step") if isinstance(graph.metadata, dict) else None
        _t2s_up = _t2s_up if isinstance(_t2s_up, dict) else {}
        _cycle_names = [_t2s_up.get(tid, tid) for tid in _cycle_ids]
        _cycle_str = " -> ".join(_cycle_names + [_cycle_names[0]])
        return vm.make_err(
            "workflow_error",
            f"Dependency cycle detected: {_cycle_str}",
            payload={
                "category": "cyclic_workflow",
                "cycle": _cycle_names,
                "workflow_name": workflow_name,
            },
        )

    workflow_state: dict | None = None
    checkpoints: list[dict] | None = None
    engine_checkpoints: list[dict] | None = None
    if workflow_name is not None and isinstance(graph.metadata, dict):
        workflow_state = cast("dict | None", graph.metadata.get("workflow_state"))
        checkpoints = cast("list[dict] | None", graph.metadata.get("workflow_checkpoints"))
        legacy_checkpoints = graph.metadata.get("checkpoints")
        if checkpoints is None and isinstance(legacy_checkpoints, list):
            checkpoints = checkpoints_public(legacy_checkpoints)
        engine_checkpoints = cast("list[dict] | None", graph.metadata.get("engine_checkpoints"))
        if engine_checkpoints is None and isinstance(legacy_checkpoints, list):
            engine_checkpoints = copy.deepcopy(legacy_checkpoints)
        if resume_state:
            _resume_meta_raw = resume_state.get("metadata")
            resume_meta: dict[str, Any] = _resume_meta_raw if isinstance(_resume_meta_raw, dict) else {}
            if "workflow_state" in resume_state:
                workflow_state = cast("dict | None", resume_state.get("workflow_state"))
            elif "workflow_state" in resume_meta:
                workflow_state = cast("dict | None", resume_meta.get("workflow_state"))
            if "checkpoints" in resume_state:
                checkpoints = cast("list[dict] | None", resume_state.get("checkpoints"))
            elif "workflow_checkpoints" in resume_meta:
                checkpoints = cast("list[dict] | None", resume_meta.get("workflow_checkpoints"))
            elif "checkpoints" in resume_meta:
                checkpoints = checkpoints_public(cast(list, resume_meta.get("checkpoints") or []))
            if "engine_checkpoints" in resume_state:
                engine_checkpoints = cast("list[dict] | None", resume_state.get("engine_checkpoints"))
            elif "engine_checkpoints" in resume_meta:
                engine_checkpoints = cast("list[dict] | None", resume_meta.get("engine_checkpoints"))
            elif engine_checkpoints is None and "checkpoints" in resume_state:
                engine_checkpoints = copy.deepcopy(cast(list, resume_state.get("checkpoints") or []))
            elif engine_checkpoints is None and "checkpoints" in resume_meta:
                engine_checkpoints = copy.deepcopy(cast(list, resume_meta.get("checkpoints") or []))
        if workflow_state is None:
            workflow_state = {}
        # #485: wrap so each write records who made it. Two fan-out branches that
        # read a key, yield, and write it back silently lose one of the writes;
        # this cannot stop that, but it can stop it being silent.
        if not isinstance(workflow_state, TrackedState):
            workflow_state = TrackedState(workflow_state)
        # The fold happens at `end_step`, where the cell's policy is what decides
        # whether there is anything to fold, so the state carries the policies.
        if isinstance(graph.metadata, dict):
            workflow_state.set_policies(graph.metadata.get("state_policies"))
        if checkpoints is None:
            checkpoints = []
        if engine_checkpoints is None:
            engine_checkpoints = []
        graph.metadata["workflow_state"] = workflow_state
        graph.metadata["workflow_checkpoints"] = checkpoints
        graph.metadata["engine_checkpoints"] = engine_checkpoints
        graph.metadata["checkpoints"] = checkpoints
    if resume_state:
        stored_pending = resume_state.get("pending")
        if isinstance(stored_pending, list):
            filtered = []
            seen = set()
            for tid in stored_pending:
                if not isinstance(tid, str) or tid not in by_id or tid in seen:
                    continue
                filtered.append(tid)
                seen.add(tid)
            pending = set(filtered)
            pending_queue[:] = filtered
        stored_scheduler = resume_state.get("scheduler_queue")
        if isinstance(stored_scheduler, list):
            filtered_hint = []
            seen_hint = set()
            for tid in stored_scheduler:
                if not isinstance(tid, str) or tid not in by_id or tid in seen_hint:
                    continue
                filtered_hint.append(tid)
                seen_hint.add(tid)
            scheduler_order_map = {tid: idx for idx, tid in enumerate(filtered_hint)}
    if workflow_name is not None:
        vm.event_bus.emit_event("workflow_start", data={"workflow": workflow_name, "graph_id": graph.graph_id})
    if execution_kind == "goal" and isinstance(goal_name, str):
        vm.event_bus.emit_event("goal_start", data={"goal": goal_name, "workflow": workflow_name, "graph_id": graph.graph_id})

    def step_results() -> dict[str, object]:
        if not isinstance(graph.metadata, dict):
            return {}
        task_to_step = graph.metadata.get("task_to_step", {})
        if not isinstance(task_to_step, dict):
            return {}
        mapped = {}
        for task_id, result in task_values.items():
            step_name = task_to_step.get(task_id)
            if isinstance(step_name, str):
                mapped[step_name] = result
        return mapped

    def workflow_event_payload(task: TaskNode) -> dict | None:
        if workflow_name is None or task.step_name is None:
            return None
        return {
            "workflow": workflow_name,
            "graph_id": graph.graph_id,
            "step": task.step_name,
            "task_id": task.task_id,
        }

    def goal_event_payload(task: TaskNode | None = None) -> dict | None:
        if execution_kind != "goal" or not isinstance(goal_name, str):
            return None
        payload = {
            "goal": goal_name,
            "workflow": workflow_name,
            "graph_id": graph.graph_id,
        }
        if task is not None and task.step_name is not None:
            payload["step"] = task.step_name
            payload["task_id"] = task.task_id
        return payload

    def workflow_result_payload() -> dict:
        payload = {
            "state": clone_state(workflow_state) if isinstance(workflow_state, dict) else {},
            "checkpoints": checkpoints_public(checkpoints or []),
        }
        if workflow_name is not None:
            payload["workflow"] = workflow_name
        if execution_kind == "goal" and isinstance(goal_name, str):
            payload["goal"] = goal_name
        return payload

    def waiting_result_payload(wait_info: dict, task: TaskNode) -> dict:
        payload = {
            "status": "waiting",
            "wait": {
                "event_type": wait_info.get("event_type"),
                "correlation_key": wait_info.get("correlation_key"),
                "payload": wait_info.get("payload") or {},
                "deadline_ms": wait_info.get("deadline_ms"),
                "step": task.step_name,
                "task_id": task.task_id,
            },
            "tasks": task_values,
            "steps": step_results(),
            "timings": timings,
            "attempts": attempts,
            "failed": [],
            "cache_hits": cache_hits,
            "graph_id": graph.graph_id,
        }
        payload.update(workflow_result_payload())
        return with_statuses(payload)

    def retry_result_payload(task: TaskNode, retry_info: dict) -> dict:
        payload = {
            "status": "retry_scheduled",
            "retry": {
                "task_id": task.task_id,
                "step": task.step_name,
                "attempt": float(task.attempts),
                "max_retries": float(task.max_retries),
                "delay_ms": float(task.retry_delay_ms),
                "next_attempt_at": retry_info.get("next_attempt_at"),
                "classification": retry_info.get("classification"),
                "last_error": retry_info.get("last_error"),
            },
            "tasks": task_values,
            "steps": step_results(),
            "timings": timings,
            "attempts": attempts,
            "failed": [],
            "cache_hits": cache_hits,
            "graph_id": graph.graph_id,
        }
        payload.update(workflow_result_payload())
        return with_statuses(payload)

    def failed_id(task: TaskNode) -> str:
        if task.step_name is not None:
            return task.step_name
        return task.task_id

    worker_lock = threading.RLock()
    worker_cond = threading.Condition(worker_lock)
    active_workers = 0
    worker_mode = False

    def _dep_satisfied(task: TaskNode, dep: TaskNode) -> bool:
        """Has this dependency finished in a way this task declared it accepts?

        The join policy used to be hardcoded here as `dep.task_id in results` --
        every dependency must have produced a value. That is still the default, and
        `with { on: [...] }` is how a step says otherwise (#475).
        """
        if dep.task_id in results:
            return "completed" in task.on_states
        if dep.status == "failed":
            return "failed" in task.on_states
        if dep.task_id in skipped_ids:
            return "skipped" in task.on_states
        return False

    def tolerates_failure(task: TaskNode) -> bool:
        """Did this step explicitly ask to run on an outcome other than success?

        Once a step fails the run stops scheduling new work, which is right for
        ordinary steps but would make `on: ["failed"]` unreachable -- the one
        policy whose entire purpose is to run *because* something failed. Opting
        in has to be explicit, or relaxing the guard would quietly turn fail-fast
        off for every independent branch as well.
        """
        return task.on_states != DEFAULT_JOIN_ON

    def ready_tasks():
        ready = []
        for task in tasks:
            if task.task_id in pending and all(
                _dep_satisfied(task, dep) for dep in task.dependencies
            ):
                ready.append(task)
        if scheduler_order_map:
            ready.sort(key=lambda task: scheduler_order_map.get(task.task_id, len(scheduler_order_map)))
        return ready

    def guard_holds(task: TaskNode) -> bool:
        """Evaluate a step's `when` predicate against the checkpoints reached so far.

        The predicate is data (a nested map), walked by the same interpreter a
        goal's `until` uses. Evaluated at the moment the step becomes ready, so it
        sees every checkpoint its dependencies recorded.
        """
        if task.when is None:
            return True
        reached = {
            entry["label"]
            for entry in (checkpoints or [])
            if isinstance(entry, dict) and isinstance(entry.get("label"), str)
        }
        return bool(vm._evaluate_goal_predicate(task.when, reached))

    def schedule_ready() -> None:
        """Start everything that is ready, skipping whatever its guard excludes.

        Loops because a skip resolves its dependents' joins: skipping `deploy` can
        make `notify` classifiable in the same pass. Bounded -- every iteration
        that repeats removes at least one task from `pending`.
        """
        while True:
            skipped_any = False
            for task in ready_tasks():
                if not guard_holds(task):
                    skipped_ids.add(task.task_id)
                    _remove_task_from_pending(task.task_id)
                    vm.event_bus.emit_event("task_skipped", name=task.task_id)
                    workflow_data = workflow_event_payload(task)
                    if workflow_data is not None:
                        vm.event_bus.emit_event(
                            "workflow_step_skipped", name=task.step_name, data=workflow_data
                        )
                    skipped_any = True
                else:
                    spawn_task(task)
            if not skipped_any:
                return

    def task_statuses() -> dict[str, str]:
        """Classify every task in the graph once the run has drained.

        A run used to end the moment a step failed, so a task that never got a
        turn simply vanished from the result: `steps` omitted it and `failed`
        named only the step that threw. Four distinguishable outcomes, one
        reported. This names all of them (#475, #503).

        The distinctions are the ones the runtime can draw, and no others.
        `skipped` is still absent: it needs a guard on the step itself, which is
        a conditional-edge design (#471). `omitted` is here because `on:` is a
        construct that means it -- a join condition that was evaluated and not
        met -- which is the bar a status has to clear.
        """
        failed_ids = {task.task_id for task in tasks if task.status == "failed"}

        # Two transitive closures over dependencies, distinguishing *why* a task
        # never ran. Iterate to a fixed point rather than assuming the task list
        # is topologically ordered -- `run_graph` takes an arbitrary list.
        #
        # The distinction is Argo's, and it is the one that makes the report worth
        # reading: `upstream_failed` means something above me broke, `omitted`
        # means the condition I declared was not met. Collapsing them would lose
        # exactly what a failure-tolerant join is for.
        blocked: set[str] = set()          # -> upstream_failed
        omitted: set[str] = set()          # -> omitted
        skipped: set[str] = set(skipped_ids)  # -> skipped, guard said no
        changed = True
        while changed:
            changed = False
            for task in tasks:
                tid = task.task_id
                if (
                    tid in results or tid in failed_ids
                    or tid in blocked or tid in omitted or tid in skipped
                ):
                    continue
                for dep in task.dependencies:
                    # Failure dominates: a task downstream of both a break and an
                    # unmet condition reports the break.
                    if dep.task_id in blocked or (
                        dep.task_id in failed_ids and "failed" not in task.on_states
                    ):
                        blocked.add(tid)
                        changed = True
                        break
                    # The dependency finished in a state this task said it does
                    # not accept -- most often a step declaring `on: ["failed"]`
                    # whose dependency succeeded, which is the whole point of it.
                    # A skipped dependency cascades unless this step declared it
                    # acceptable. `after` reads as *needs*, so a step whose
                    # dependency never ran should not fire with `nil` for it --
                    # `on: [..., "skipped"]` is how to say otherwise.
                    if dep.task_id in skipped and "skipped" not in task.on_states:
                        skipped.add(tid)
                        changed = True
                        break
                    if dep.task_id in omitted or (
                        dep.task_id in results and "completed" not in task.on_states
                    ):
                        omitted.add(tid)
                        changed = True
                        break

        statuses: dict[str, str] = {}
        for task in tasks:
            if task.task_id in results:
                statuses[task.task_id] = "completed"
            elif task.task_id in failed_ids:
                statuses[task.task_id] = "failed"
            elif task.task_id in blocked:
                statuses[task.task_id] = "upstream_failed"
            elif task.task_id in skipped:
                statuses[task.task_id] = "skipped"
            elif task.task_id in omitted:
                statuses[task.task_id] = "omitted"
            elif task.status == "running":
                # Still running when the run ended. Draining should make this
                # unreachable for the failure path; if it appears, something
                # dropped a coroutine without unwinding it (#502).
                statuses[task.task_id] = "abandoned"
            elif failed_ids:
                # Its dependencies were satisfiable, but the run stopped
                # scheduling new work when the first step failed. Whether these
                # should run anyway is the open half of #475 -- naming them makes
                # the choice visible instead of silent.
                statuses[task.task_id] = "cancelled"
            else:
                statuses[task.task_id] = task.status
        return statuses

    def step_statuses(by_task: dict[str, str]) -> dict[str, str]:
        if not isinstance(graph.metadata, dict):
            return {}
        task_to_step = graph.metadata.get("task_to_step", {})
        if not isinstance(task_to_step, dict):
            return {}
        mapped = {}
        for task_id, status in by_task.items():
            step_name = task_to_step.get(task_id)
            if isinstance(step_name, str):
                mapped[step_name] = status
        return mapped

    def _finalize_failed(payload: dict) -> dict:
        """Refresh the snapshot fields of a failure payload built mid-run.

        `_fail_task` builds the payload when the first step fails, but the run
        now keeps draining afterwards, so anything captured by value there is
        stale by the time it is returned. `tasks`, `timings`, `attempts` and
        `cache_hits` hold live references and need no refresh; `steps` was a
        snapshot, and `failed` named only the first casualty.
        """
        payload["steps"] = step_results()
        payload["failed"] = [failed_id(task) for task in tasks if task.status == "failed"]
        return payload

    def report_write_conflicts() -> None:
        """Say so when two concurrent steps wrote the same state key.

        The write that lost is gone and cannot be recovered here -- this reports
        rather than repairs, because repairing means changing what a state write
        *is* (#485), which wants deciding with the type and durability axes that
        attach to the same declaration.

        Not an error. Two branches writing one key can be perfectly deliberate
        when the author knows they agree, and there is currently no way to say so
        -- refusing would break correct workflows to catch incorrect ones. Once a
        declaration exists, the default can tighten.
        """
        ancestors: dict[str, set[str]] = {}

        def _ancestors_of(task_id: str) -> set[str]:
            """Every task that must finish before this one starts."""
            if task_id in ancestors:
                return ancestors[task_id]
            ancestors[task_id] = set()  # guard against a cycle mid-walk
            node = by_id.get(task_id)
            found: set[str] = set()
            if node is not None:
                for dep in node.dependencies:
                    found.add(dep.task_id)
                    found |= _ancestors_of(dep.task_id)
            ancestors[task_id] = found
            return found

        def _ordered(a: str, b: str) -> bool:
            return b in _ancestors_of(a) or a in _ancestors_of(b)

        conflicts = concurrent_write_conflicts(workflow_state, _ordered)
        if not conflicts:
            return
        policies = {}
        if isinstance(graph.metadata, dict):
            raw = graph.metadata.get("state_policies")
            if isinstance(raw, dict):
                policies = raw
        task_to_step = {}
        if isinstance(graph.metadata, dict):
            raw = graph.metadata.get("task_to_step")
            if isinstance(raw, dict):
                task_to_step = raw
        for conflict in conflicts:
            # No default here on purpose. An *undeclared* cell behaves as `any`
            # but still warns -- that warning is the only thing standing between a
            # lost update and silence. Only an explicit `merge: "any"` silences it,
            # so the warning is quieted by stating intent rather than by a default
            # nobody wrote.
            merge = policies.get(conflict["key"], {}).get("merge")
            names = [task_to_step.get(tid, tid) for tid in conflict["tasks"]]
            winner = task_to_step.get(conflict["winner"], conflict["winner"])
            if merge == "once":
                vm.runtime_error(
                    "workflow_error",
                    f"state '{conflict['key']}' is declared merge: \"once\", but "
                    f"steps {' and '.join(names)} both wrote it while running "
                    f"concurrently.",
                )
            if merge == "any":
                # Declared last-write-wins. The author has said the branches agree,
                # so the warning would be noise -- silencing it by *stating intent*
                # is the whole reason `any` is sayable.
                continue
            if is_fold_policy(merge):
                # Two branches contributing to a folded cell is the feature, not
                # the defect: neither read it, so neither lost the other's write.
                continue
            if not conflict.get("lost_update"):
                # Both branches wrote the same constant and neither read the cell
                # first, so nothing was lost whichever won. Warning here is the
                # noise that teaches people to ignore the warning that matters --
                # and it is the case that made `once` unusable as a default, since
                # these workflows are correct as written.
                continue
            if conflict.get("read_modify_write"):
                cause = (
                    "each read it before writing, so one update was lost"
                )
            else:
                cause = (
                    "with different values, so one was lost"
                )
            message = (
                f"warning: steps {' and '.join(names)} both wrote state "
                f"'{conflict['key']}' while running concurrently and {cause}; "
                f"only {winner}'s write survives. Declare "
                f"`with {{ merge: \"sum\" }}` (or \"append\") to combine them, "
                f"or `merge: \"any\"` if you meant last-write-wins. "
                f"This becomes an error in 6.0.0."
            )
            print(message, file=sys.stderr)
            vm.event_bus.emit_event(
                "workflow_state_write_conflict",
                data={
                    "workflow": workflow_name,
                    "graph_id": graph.graph_id,
                    "key": conflict["key"],
                    "steps": names,
                    "winner": winner,
                },
            )

    def with_statuses(payload: dict) -> dict:
        """Attach the status report, mirroring how `tasks`/`steps` are keyed.

        Both keys are set unconditionally, empty if they have nothing to say.
        `steps` behaves the same way -- present and `{}` for a bare `run_graph`,
        which has no step names -- and the reason matters: Nodus maps raise on a
        missing key, so a key that appears on some result shapes and not others
        turns `r["statuses"]` into a crash that depends on how the run was
        started. That is the #399 failure mode.
        """
        report_write_conflicts()
        by_task = task_statuses()
        payload["task_statuses"] = by_task
        payload["statuses"] = step_statuses(by_task)
        return payload

    def _serialize_value(value):
        if value is None:
            return None
        if isinstance(value, (int, float, str, bool)):
            return value
        if isinstance(value, list):
            return [_serialize_value(v) for v in value]
        if isinstance(value, dict):
            return {str(k): _serialize_value(v) for k, v in value.items()}
        if dataclasses.is_dataclass(value):
            return {"__dataclass__": type(value).__name__, **{k: _serialize_value(v) for k, v in value.__dict__.items()}}
        return repr(value)

    def _default_cache_key(task: TaskNode, dep_values: list):
        fn = task.function
        fn_info = getattr(fn, "function", fn)
        payload = {
            "fn": type(fn_info).__name__,
            "fn_name": getattr(fn_info, "name", None),
            "deps": _serialize_value(dep_values),
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _record_checkpoint(task: TaskNode, label: str) -> None:
        if workflow_name is None:
            return
        if not isinstance(label, str):
            return
        entry = {
            "label": label,
            "step": task.step_name,
            "task_id": task.task_id,
            "timestamp": runtime_time_ms(),
        }
        # A checkpoint records what the step has done so far, folded contributions
        # included: `counter += 1i; checkpoint "l"` must record the contributed
        # value, or a resume from that label contributes again and the total is
        # wrong. Merged into a copy -- other branches still must not see it before
        # the join.
        state_now = workflow_state
        if isinstance(workflow_state, TrackedState):
            pending = workflow_state.pending_fold(task.task_id)
            if pending:
                state_now = {**workflow_state, **pending}
        if isinstance(state_now, dict):
            entry["state"] = clone_state(state_now)
        if isinstance(checkpoints, list):
            checkpoints.append(
                {
                    "label": entry["label"],
                    "step": entry["step"],
                    "task_id": entry["task_id"],
                    "timestamp": entry["timestamp"],
                }
            )
        if isinstance(engine_checkpoints, list):
            engine_checkpoints.append(entry)
        snapshot = _persist_graph_state(
            graph,
            tasks,
            attempts,
            results,
            "running",
            pending_queue,
            task_values,
            workflow_state,
            checkpoints,
            engine_checkpoints,
            vm,
        )
        persist_checkpoint_snapshot(cast(str, graph.graph_id), snapshot, label)
        vm.event_bus.emit_event("graph_persist", data={"graph_id": graph.graph_id})

    def _current_writer_task_id():
        """Which task is writing state right now, if any.

        Well-defined because the scheduler is cooperative: at any instant exactly
        one coroutine is running, and its workflow context names its task. State
        written outside a step -- by the initializer -- has no writer and is not a
        conflict with anything.
        """
        ctx = vm.current_workflow_context()
        if isinstance(ctx, dict):
            task_id = ctx.get("task_id")
            if isinstance(task_id, str):
                return task_id
        return None

    if isinstance(workflow_state, TrackedState):
        workflow_state.track_writes_with(_current_writer_task_id)

    def _begin_step_writes(task: TaskNode) -> None:
        """Open the write record for a step that is about to run."""
        if isinstance(workflow_state, TrackedState):
            workflow_state.begin_step(task.task_id)

    def _end_step_writes(task: TaskNode) -> None:
        """Close a step's write record. Where a fold will be applied (#485).

        Called from every path a task leaves `running` by: success on the
        coroutine path, success on the worker path, `_fail_task`, and
        `_pause_for_wait`. A cache hit needs none -- no step body ran, so no
        record was opened.

        Those four are the set to keep in step if a fifth exit path is added.
        `tests/test_workflow_step_writes.py` covers each separately rather than
        trusting one to stand for the others: a record left open would make the
        step's writes invisible to the merge, which is the same failure mode
        #485 is about, reintroduced by its own fix.
        """
        if isinstance(workflow_state, TrackedState):
            workflow_state.end_step(task.task_id)

    def _workflow_context(task: TaskNode) -> dict | None:
        if workflow_name is None:
            return None
        resume_payload = None
        if isinstance(graph.metadata, dict):
            candidate = graph.metadata.get("resume_payload")
            if isinstance(candidate, dict):
                resume_payload = candidate
        context = {
            "graph": graph,
            "graph_id": graph.graph_id,
            "workflow": workflow_name,
            "step": task.step_name,
            "task_id": task.task_id,
            "state": workflow_state,
            "checkpoints": checkpoints,
            "checkpoint": lambda label: _record_checkpoint(task, label),
            "resume_payload": resume_payload,
        }
        if execution_kind == "goal" and isinstance(goal_name, str):
            context["goal"] = goal_name
        _begin_step_writes(task)
        return context

    def _pause_for_wait(task: TaskNode, wait_info: dict) -> bool:
        nonlocal waiting
        # Writes made before the step suspended are real and must land; the step
        # resumes later against a fresh view.
        _end_step_writes(task)
        task.result = None
        task.status = "done"
        task.finished_at = runtime_time_ms()
        results[task.task_id] = None
        task_values[task.task_id] = None
        timings[task.task_id] = {
            "started_at": task.started_at,
            "finished_at": task.finished_at,
        }
        if isinstance(graph.metadata, dict):
            graph.metadata["wait"] = dict(wait_info)
        snapshot = _persist_graph_state(
            graph,
            tasks,
            attempts,
            results,
            "waiting",
            pending_queue,
            task_values,
            workflow_state,
            checkpoints,
            engine_checkpoints,
            vm,
        )
        snapshot["wait"] = dict(wait_info)
        waiting = waiting_result_payload(wait_info, task)
        vm.event_bus.emit_event("graph_persist", data={"graph_id": graph.graph_id})
        workflow_data = workflow_event_payload(task)
        if workflow_data is not None:
            wait_data = dict(workflow_data)
            wait_data.update(wait_info)
            vm.event_bus.emit_event("workflow_waiting", name=task.step_name, data=wait_data)
        goal_data = goal_event_payload(task)
        if goal_data is not None:
            wait_data = dict(goal_data)
            wait_data.update(wait_info)
            vm.event_bus.emit_event("goal_waiting", name=task.step_name, data=wait_data)
        return True

    def spawn_task(task: TaskNode, delay_ms: float = 0.0) -> None:
        nonlocal failed, waiting, active_workers, worker_mode
        with worker_lock:
            if waiting is not None:
                return
            if failed is not None and not tolerates_failure(task):
                return
            _remove_task_from_pending(task.task_id)
            task.status = "running"
            if task.started_at is None:
                task.started_at = runtime_time_ms()
            task.attempts += 1
            attempts[task.task_id] = float(task.attempts)
            vm.event_bus.emit_event("task_start", name=task.task_id)
            workflow_data = workflow_event_payload(task)
            if workflow_data is not None:
                vm.event_bus.emit_event("workflow_step_start", name=task.step_name, data=workflow_data)
            goal_data = goal_event_payload(task)
            if goal_data is not None:
                vm.event_bus.emit_event("goal_step_start", name=task.step_name, data=goal_data)
            # `nil` for a dependency that finished without producing a value --
            # reachable only for a step that declared `on: ["failed"]`, since any
            # other step waits for every dependency to complete. The step is bound
            # to its dependencies by name, so it needs an argument either way.
            #
            # This does not tell the step *why* the value is missing. Handing it
            # the error belongs with the partial-success envelope (#468), which is
            # where the shape of a "what happened" value gets decided.
            args = [results.get(dep.task_id) for dep in task.dependencies]
        context = _workflow_context(task)
        if task.cache:
            key = task.cache_key or _default_cache_key(task, args)
            if key in vm.task_cache:
                with worker_lock:
                    task.result = vm.task_cache[key]
                    task.status = "done"
                    task.finished_at = runtime_time_ms()
                    results[task.task_id] = task.result
                    task_values[task.task_id] = task.result
                    timings[task.task_id] = {
                        "started_at": task.started_at,
                        "finished_at": task.finished_at,
                    }
                    cache_hits.append(task.task_id)
                    vm.event_bus.emit_event("task_cache_hit", name=task.task_id)
                    _persist_graph_state(
                        graph,
                        tasks,
                        attempts,
                        results,
                        "running",
                        pending_queue,
                        task_values,
                        workflow_state,
                        checkpoints,
                        engine_checkpoints,
                        vm,
                    )
                    vm.event_bus.emit_event("graph_persist", data={"graph_id": graph.graph_id})
                    vm.event_bus.emit_event("task_success", name=task.task_id, data={"attempt": float(task.attempts)})
                    workflow_data = workflow_event_payload(task)
                    if workflow_data is not None:
                        vm.event_bus.emit_event("workflow_step_complete", name=task.step_name, data=workflow_data)
                    goal_data = goal_event_payload(task)
                    if goal_data is not None:
                        vm.event_bus.emit_event("goal_step_complete", name=task.step_name, data=goal_data)
                    schedule_ready()
                    worker_cond.notify_all()
                return
        if dispatcher is not None:
            worker_mode = True
            def _execute():
                return vm.run_closure(task.function, args, workflow_context=context)
            with worker_lock:
                active_workers += 1

            def _run_worker():
                nonlocal active_workers
                result = dispatcher.submit(
                    task.task_id,
                    args,
                    _execute,
                    delay_ms=delay_ms,
                    requirement=task.worker,
                    requirement_timeout_ms=task.worker_timeout_ms,
                )
                with worker_lock:
                    try:
                        if isinstance(result, Exception):
                            _fail_task(task, result)
                        else:
                            wait_info = _workflow_wait_info(result)
                            if wait_info is not None:
                                _pause_for_wait(task, wait_info)
                                return
                            if execution_kind in ("workflow", "goal") and getattr(result, "kind", None) == "error":
                                err_fields = getattr(result, "fields", {})
                                err_msg = err_fields.get("message", "step returned an error value") if isinstance(err_fields, dict) else "step returned an error value"
                                _fail_task(task, Exception(err_msg))
                                return
                            _end_step_writes(task)
                            task.result = result
                            task.status = "done"
                            task.finished_at = runtime_time_ms()
                            results[task.task_id] = task.result
                            task_values[task.task_id] = task.result
                            timings[task.task_id] = {
                                "started_at": task.started_at,
                                "finished_at": task.finished_at,
                            }
                            if task.cache:
                                key = task.cache_key or _default_cache_key(task, [results[dep.task_id] for dep in task.dependencies])
                                vm.task_cache[key] = task.result
                                vm.event_bus.emit_event("task_cache_store", name=task.task_id)
                            _persist_graph_state(
                                graph,
                                tasks,
                                attempts,
                                results,
                                "running",
                                pending_queue,
                                task_values,
                                workflow_state,
                                checkpoints,
                                engine_checkpoints,
                                vm,
                            )
                            vm.event_bus.emit_event("graph_persist", data={"graph_id": graph.graph_id})
                            vm.event_bus.emit_event("task_success", name=task.task_id, data={"attempt": float(task.attempts)})
                            workflow_data = workflow_event_payload(task)
                            if workflow_data is not None:
                                vm.event_bus.emit_event("workflow_step_complete", name=task.step_name, data=workflow_data)
                            goal_data = goal_event_payload(task)
                            if goal_data is not None:
                                vm.event_bus.emit_event("goal_step_complete", name=task.step_name, data=goal_data)
                            schedule_ready()
                    except Exception as _exc:
                        try:
                            _fail_task(task, _exc)
                        except Exception:
                            pass
                    finally:
                        active_workers -= 1
                        worker_cond.notify_all()

            threading.Thread(target=_run_worker, daemon=True).start()
            return
        coroutine = Coroutine(task.function)
        coroutine.workflow_context = context
        coroutine.initial_args = args
        coroutine.name = task.task_id
        coroutine.task_timeout_ms = task.timeout_ms
        coroutine.task_started_at = runtime_time_ms()
        running[id(coroutine)] = task
        if delay_ms > 0.0:
            vm.scheduler.schedule_delay(coroutine, delay_ms)
        else:
            vm.scheduler.spawn(coroutine)

    def on_complete(coroutine: Coroutine):
        nonlocal waiting
        task = running.pop(id(coroutine), None)
        if task is None:
            return False
        wait_info = _workflow_wait_info(coroutine.last_result)
        if wait_info is not None:
            return _pause_for_wait(task, wait_info)
        if execution_kind in ("workflow", "goal") and getattr(coroutine.last_result, "kind", None) == "error":
            err_fields = getattr(coroutine.last_result, "fields", {})
            err_msg = err_fields.get("message", "step returned an error value") if isinstance(err_fields, dict) else "step returned an error value"
            return _fail_task(task, Exception(err_msg))
        _end_step_writes(task)
        task.result = coroutine.last_result
        task.status = "done"
        task.finished_at = runtime_time_ms()
        results[task.task_id] = task.result
        task_values[task.task_id] = task.result
        timings[task.task_id] = {
            "started_at": task.started_at,
            "finished_at": task.finished_at,
        }
        if task.cache:
            key = task.cache_key or _default_cache_key(task, [results[dep.task_id] for dep in task.dependencies])
            vm.task_cache[key] = task.result
            vm.event_bus.emit_event("task_cache_store", name=task.task_id)
        _persist_graph_state(
            graph,
            tasks,
            attempts,
            results,
            # A step completing after an earlier step failed must not overwrite
            # the run's failed status with "running" -- the run is still failing,
            # it is only draining.
            "running" if failed is None else "failed",
            pending_queue,
            task_values,
            workflow_state,
            checkpoints,
            engine_checkpoints,
            vm,
        )
        vm.event_bus.emit_event("graph_persist", data={"graph_id": graph.graph_id})
        vm.event_bus.emit_event("task_success", name=task.task_id, data={"attempt": float(task.attempts)})
        workflow_data = workflow_event_payload(task)
        if workflow_data is not None:
            vm.event_bus.emit_event("workflow_step_complete", name=task.step_name, data=workflow_data)
        goal_data = goal_event_payload(task)
        if goal_data is not None:
            vm.event_bus.emit_event("goal_step_complete", name=task.step_name, data=goal_data)
        # No failure guard here on purpose: `spawn_task` already refuses to
        # schedule once `failed` is set, and that is the only place the decision
        # should live. Adding a second check here is how a sibling path drifts
        # out of step with it.
        schedule_ready()
        return False

    def _fail_task(task: TaskNode, err: Exception):
        nonlocal failed, retry_scheduled
        # Before overlays a failing step's writes were already in shared state,
        # because they went there as it made them. Applying keeps that true; see
        # StateView.apply_to_base on why rolling back is a separate question.
        _end_step_writes(task)
        task.last_error = str(err)
        worker_requirement = getattr(err, "worker_requirement", None)
        worker_timeout_ms = getattr(err, "worker_timeout_ms", None)
        if worker_requirement is not None:
            vm.event_bus.emit_event(
                "task_worker_timeout",
                name=task.task_id,
                data={"worker": worker_requirement, "timeout_ms": worker_timeout_ms},
            )
        vm.event_bus.emit_event(
            "task_fail",
            name=task.task_id,
            data={"message": str(err), "attempt": float(task.attempts)},
        )
        workflow_data = workflow_event_payload(task)
        if workflow_data is not None:
            fail_data = dict(workflow_data)
            fail_data["message"] = str(err)
            vm.event_bus.emit_event("workflow_step_fail", name=task.step_name, data=fail_data)
        goal_data = goal_event_payload(task)
        if goal_data is not None:
            fail_data = dict(goal_data)
            fail_data["message"] = str(err)
            vm.event_bus.emit_event("goal_step_fail", name=task.step_name, data=fail_data)
        if task.attempts <= task.max_retries:
            setattr(err, "_retry_pending", True)
            vm.event_bus.emit_event("task_retry", name=task.task_id, data={"attempt": float(task.attempts + 1)})
            if run_is_durable and _retry_is_swept():
                task.status = "retry_scheduled"
                task.finished_at = runtime_time_ms()
                task.retry_classification = "retryable"
                task.next_retry_at = runtime_time_ms() + float(task.retry_delay_ms)
                _mark_task_pending(task.task_id)
                retry_info = {
                    "next_attempt_at": task.next_retry_at,
                    "classification": task.retry_classification,
                    "last_error": str(err),
                }
                retry_scheduled = retry_result_payload(task, retry_info)
                _persist_graph_state(
                    graph,
                    tasks,
                    attempts,
                    results,
                    "retry_scheduled",
                    pending_queue,
                    task_values,
                    workflow_state,
                    checkpoints,
                    engine_checkpoints,
                    vm,
                )
                vm.event_bus.emit_event("graph_persist", data={"graph_id": graph.graph_id})
                if workflow_data is not None:
                    retry_data = dict(workflow_data)
                    retry_data.update(retry_info)
                    vm.event_bus.emit_event("workflow_retry_scheduled", name=task.step_name, data=retry_data)
                if goal_data is not None:
                    retry_data = dict(goal_data)
                    retry_data.update(retry_info)
                    vm.event_bus.emit_event("goal_retry_scheduled", name=task.step_name, data=retry_data)
                return True
            task.status = "retrying"
            _mark_task_pending(task.task_id)
            _persist_graph_state(
                graph,
                tasks,
                attempts,
                results,
                "running",
                pending_queue,
                task_values,
                workflow_state,
                checkpoints,
                engine_checkpoints,
                vm,
            )
            vm.event_bus.emit_event("graph_persist", data={"graph_id": graph.graph_id})
            spawn_task(task, delay_ms=task.retry_delay_ms)
            return False
        task.status = "failed"
        task.finished_at = runtime_time_ms()
        task.error = str(err)
        task.retry_classification = "exhausted" if task.max_retries > 0 else "non_retryable"
        if failed is not None:
            # A second failure while the run drains. The first one stays
            # authoritative for `error` and `retry`; the full set of failed steps
            # is recomputed from task state when the payload is finalised.
            return False
        failed = {
            "tasks": task_values,
            "steps": step_results(),
            "failed": [failed_id(task)],
            "error": str(err),
            "timings": timings,
            "attempts": attempts,
            "cache_hits": cache_hits,
            "graph_id": graph.graph_id,
            "retry": {
                "task_id": task.task_id,
                "step": task.step_name,
                "attempt": float(task.attempts),
                "max_retries": float(task.max_retries),
                "delay_ms": float(task.retry_delay_ms),
                "classification": task.retry_classification,
                "last_error": str(err),
            },
        }
        _persist_graph_state(
            graph,
            tasks,
            attempts,
            results,
            "failed",
            pending_queue,
            task_values,
            workflow_state,
            checkpoints,
            engine_checkpoints,
            vm,
        )
        vm.event_bus.emit_event("graph_persist", data={"graph_id": graph.graph_id})
        if workflow_name is not None:
            vm.event_bus.emit_event(
                "workflow_fail",
                data={"workflow": workflow_name, "graph_id": graph.graph_id, "failed": failed["failed"]},
            )
        if execution_kind == "goal" and isinstance(goal_name, str):
            vm.event_bus.emit_event(
                "goal_fail",
                data={"goal": goal_name, "workflow": workflow_name, "graph_id": graph.graph_id, "failed": failed["failed"]},
            )
        # A failure is a dependency outcome too. Steps declaring `on: ["failed"]`
        # become ready exactly here, and nowhere else -- readiness is otherwise
        # only re-evaluated when a step *completes*, which a failing step never
        # does. `spawn_task` refuses everything that did not opt in, so this can
        # be called unconditionally.
        schedule_ready()

        # False, not True: `True` tells the scheduler to break its loop, which
        # dropped every other coroutine where it stood -- including healthy
        # independent branches, without unwinding them (#475, #502). New work is
        # held back in `spawn_task` instead, so the run stops advancing but
        # finishes what it started.
        return False

    def on_error(coroutine: Coroutine, err: Exception):
        task = running.pop(id(coroutine), None)
        if task is None:
            return True
        return _fail_task(task, err)

    if resume_state and resume_state.get("tasks"):
        for task in tasks:
            saved = resume_state["tasks"].get(task.task_id)
            if not saved:
                continue
            task.attempts = int(saved.get("attempts", 0))
            attempts[task.task_id] = float(task.attempts)
            next_retry_at = saved.get("next_retry_at")
            if isinstance(next_retry_at, (int, float)):
                task.next_retry_at = float(next_retry_at)
            retry_classification = saved.get("retry_classification")
            if isinstance(retry_classification, str):
                task.retry_classification = retry_classification
            if saved.get("state") in {"completed", "done"}:
                results[task.task_id] = saved.get("result")
                task_values[task.task_id] = saved.get("result")
                task.status = "completed"
                _remove_task_from_pending(task.task_id)
            elif saved.get("state") in {"failed"}:
                task.status = "failed"
                failed = {
                    "tasks": task_values,
                    "steps": step_results(),
                    "failed": [failed_id(task)],
                    "error": saved.get("last_error") or "Task failed",
                    "timings": timings,
                    "attempts": attempts,
                    "cache_hits": cache_hits,
                    "graph_id": graph.graph_id,
                }
                failed.update(workflow_result_payload())
                return with_statuses(failed)
            else:
                task.status = "pending"
        for task in tasks:
            if task.task_id not in results and task.task_id not in pending:
                _mark_task_pending(task.task_id)

    schedule_ready()

    if failed is not None:
        failed.update(workflow_result_payload())
        return with_statuses(_finalize_failed(failed))

    if waiting is not None:
        return waiting

    if retry_scheduled is not None:
        return retry_scheduled

    if worker_mode:
        with worker_cond:
            # Once a step has failed, no further work is scheduled, so `pending`
            # can never drain -- wait only on what is still in flight.
            while waiting is None and ((pending and failed is None) or active_workers > 0):
                worker_cond.wait(timeout=0.05)
    else:
        vm.scheduler.run_loop(on_complete=on_complete, on_error=on_error)

    if failed is not None:
        failed.update(workflow_result_payload())
        return with_statuses(_finalize_failed(failed))

    if waiting is not None:
        return waiting

    if retry_scheduled is not None:
        return retry_scheduled

    # A task left pending because its declared join condition was not met is a
    # reported outcome, not a broken graph. Only tasks with no explanation at all
    # still mean the workflow could never have run -- a cycle, or a dependency
    # that does not exist.
    unexplained_pending = {
        tid for tid, status in task_statuses().items()
        if tid in pending and status not in ("omitted", "upstream_failed", "cancelled", "skipped")
    }

    if unexplained_pending:
        cycle_ids = _detect_cycle_task_ids(tasks, results)
        _ts_raw = graph.metadata.get("task_to_step") if isinstance(graph.metadata, dict) else None
        task_to_step: dict[str, str] = _ts_raw if isinstance(_ts_raw, dict) else {}
        if cycle_ids:
            cycle_names = [task_to_step.get(tid, tid) for tid in cycle_ids]
            cycle_str = " -> ".join(cycle_names + [cycle_names[0]])
            message = f"Dependency cycle detected: {cycle_str}"
            err_payload = {
                "category": "cyclic_workflow",
                "cycle": cycle_names,
                "workflow_name": workflow_name,
            }
        else:
            pending_names = [task_to_step.get(tid, tid) for tid in unexplained_pending]
            message = f"Missing task dependencies: {', '.join(sorted(pending_names))}"
            err_payload = {
                "category": "missing_tasks",
                "tasks": pending_names,
                "workflow_name": workflow_name,
            }
        return vm.make_err("workflow_error", message, payload=err_payload)

    _persist_graph_state(
        graph,
        tasks,
        attempts,
        results,
        "completed",
        pending_queue,
        task_values,
        workflow_state,
        checkpoints,
        engine_checkpoints,
        vm,
    )
    vm.event_bus.emit_event("graph_persist", data={"graph_id": graph.graph_id})
    if workflow_name is not None:
        vm.event_bus.emit_event("workflow_complete", data={"workflow": workflow_name, "graph_id": graph.graph_id})
    if execution_kind == "goal" and isinstance(goal_name, str):
        vm.event_bus.emit_event("goal_complete", data={"goal": goal_name, "workflow": workflow_name, "graph_id": graph.graph_id})
    payload = {
        "tasks": task_values,
        "steps": step_results(),
        "timings": timings,
        "attempts": attempts,
        "failed": [],
        "cache_hits": cache_hits,
        "graph_id": graph.graph_id,
    }
    payload.update(workflow_result_payload())
    return with_statuses(payload)


def resume_graph(vm, graph_id: str) -> dict:
    graph = _GRAPH_REGISTRY.get(graph_id)
    if graph is None:
        return {"ok": False, "error": "Unknown graph"}
    state = _load_graph_state(graph_id)
    checkpoint = load_checkpoint(graph_id)
    resume_state = _merge_resume_state(state, checkpoint)
    if resume_state is None:
        return {"ok": False, "error": "Graph state not found"}
    vm.event_bus.emit_event("graph_resume", data={"graph_id": graph_id})
    return run_task_graph(vm, graph, resume_state=resume_state)


def plan_graph(tasks: list[TaskNode], graph: TaskGraph | None = None) -> dict:
    if graph is None:
        graph = TaskGraph(tasks)
    graph = register_graph(graph)
    nodes = [task.task_id for task in tasks]
    edges = []
    indegree: dict[str, int] = {task.task_id: 0 for task in tasks}

    for task in tasks:
        for dep in task.dependencies:
            edges.append([dep.task_id, task.task_id])
            indegree[task.task_id] += 1

    levels: list[list[str]] = []
    remaining = set(nodes)
    while remaining:
        level = [task_id for task_id in remaining if indegree.get(task_id, 0) == 0]
        if not level:
            break
        levels.append(level)
        for task_id in level:
            remaining.discard(task_id)
            for dep_task in tasks:
                if dep_task.task_id == task_id:
                    for nxt in [t.task_id for t in tasks if dep_task in t.dependencies]:
                        indegree[nxt] -= 1
                        if indegree[nxt] < 0:
                            indegree[nxt] = 0

    parallel_groups = [list(level) for level in levels]
    # #471: which of those edges lead into a guarded step. `when` makes an edge
    # conditional, so `levels` is a *superset* of what will run -- it was exact
    # before guards existed and has quietly not been since. Reported as its own
    # list rather than by reshaping `edges`, so nothing reading the plan breaks
    # and a reader who does not care about guards sees no change.
    conditional_edges = [
        [dep.task_id, task.task_id]
        for task in tasks
        if getattr(task, "when", None) is not None
        for dep in task.dependencies
    ]
    # #537: the other way an edge is conditional. `with { on: [...] }` says which
    # dependency outcomes let this step run; the default is `completed` alone.
    #
    # Only NON-default sets are recorded. Labelling every edge "completed" would
    # be noise, so the absence of an entry carries meaning -- which is a thing to
    # say out loud in the docs rather than leave for a reader to infer.
    edge_conditions: dict[str, list[str]] = {}
    for task in tasks:
        states = getattr(task, "on_states", DEFAULT_JOIN_ON)
        if states == DEFAULT_JOIN_ON:
            continue
        for dep in task.dependencies:
            edge_conditions[f"{dep.task_id}->{task.task_id}"] = sorted(states)
    result = {"nodes": nodes, "edges": edges, "levels": levels, "parallel_groups": parallel_groups, "conditional_edges": conditional_edges, "edge_conditions": edge_conditions, "graph_id": graph.graph_id}
    if isinstance(graph.metadata, dict):
        result["metadata"] = graph.metadata
    return result
