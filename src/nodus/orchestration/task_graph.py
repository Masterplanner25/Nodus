"""Task graph runtime support."""

from __future__ import annotations

from dataclasses import dataclass, field
import copy
import dataclasses
import hashlib
import json
import os
import threading
import uuid

from nodus.runtime.runtime_stats import runtime_time_ms
from nodus.runtime.coroutine import Coroutine
from nodus.orchestration.workflow_state import clone_state, checkpoints_public


@dataclass
class TaskNode:
    task_id: str
    function: object
    dependencies: list["TaskNode"] = field(default_factory=list)
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
    cache: bool = False
    cache_key: str | None = None


@dataclass
class TaskGraph:
    tasks: list[TaskNode]
    graph_id: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


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
    vm,
) -> dict:
    metadata = graph.metadata
    if isinstance(metadata, dict):
        metadata = copy.deepcopy(metadata)
    state: dict[str, object] = {
        "graph_id": graph.graph_id,
        "status": status,
        "tasks": {},
        "metadata": metadata,
        "pending": list(pending_queue),
        "scheduler_queue": _scheduler_queue_snapshot(vm),
        "task_outputs": {tid: task_values.get(tid) for tid in task_values},
        "results": {tid: results.get(tid) for tid in results},
        "workflow_state": workflow_state,
        "checkpoints": checkpoints,
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
        if task.cache:
            task_state["cache"] = True
        if task.cache_key is not None:
            task_state["cache_key"] = task.cache_key
        if task.last_error:
            task_state["last_error"] = task.last_error
        state["tasks"][task.task_id] = task_state
    with _STATE_LOCK:
        _atomic_write_json(_graph_state_path(graph.graph_id), state)
    return state


def _load_graph_state(graph_id: str) -> dict | None:
    path = _graph_state_path(graph_id)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_checkpoint(graph_id: str) -> dict | None:
    path = _checkpoint_path(graph_id)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


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
        metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
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
        for key in ("pending", "scheduler_queue", "workflow_state", "metadata", "results", "task_outputs"):
            if key in checkpoint:
                merged[key] = checkpoint[key]
        if "label" in checkpoint:
            merged["checkpoint_label"] = checkpoint["label"]
    return merged


def run_task_graph(vm, graph: TaskGraph, resume_state: dict | None = None) -> dict:
    tasks = list(graph.tasks)
    graph = register_graph(graph)
    register_graph_vm(graph.graph_id, vm)
    for idx, task in enumerate(tasks, 1):
        task.task_id = task.task_id or f"task_{idx}"
    by_id = {task.task_id: task for task in tasks}
    pending = set(task.task_id for task in tasks)
    pending_queue = [task.task_id for task in tasks]
    scheduler_hint: list[str] = []
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
    cache_hits: list[str] = []
    if not hasattr(vm, "task_cache"):
        vm.task_cache = {}

    dispatcher = getattr(vm, "worker_dispatcher", None)
    if dispatcher is None and _DEFAULT_DISPATCHER is not None and getattr(_DEFAULT_DISPATCHER, "force_dispatch", False):
        if any(task.worker is not None for task in tasks):
            dispatcher = _DEFAULT_DISPATCHER
    if dispatcher is not None and getattr(dispatcher, "event_bus", None) is None:
        dispatcher.event_bus = vm.event_bus

    vm.event_bus.emit_event("task_graph_start", data={"tasks": float(len(tasks))})
    workflow_name = graph.metadata.get("workflow_name") if isinstance(graph.metadata, dict) else None
    execution_kind = graph.metadata.get("execution_kind") if isinstance(graph.metadata, dict) else None
    goal_name = graph.metadata.get("goal_name") if isinstance(graph.metadata, dict) else None
    workflow_state = None
    checkpoints = None
    if workflow_name is not None and isinstance(graph.metadata, dict):
        workflow_state = graph.metadata.get("workflow_state")
        checkpoints = graph.metadata.get("checkpoints")
        if resume_state:
            resume_meta = resume_state.get("metadata") if isinstance(resume_state.get("metadata"), dict) else {}
            if "workflow_state" in resume_state:
                workflow_state = resume_state.get("workflow_state")
            elif "workflow_state" in resume_meta:
                workflow_state = resume_meta.get("workflow_state")
            if "checkpoints" in resume_state:
                checkpoints = resume_state.get("checkpoints")
            elif "checkpoints" in resume_meta:
                checkpoints = resume_meta.get("checkpoints")
        if workflow_state is None:
            workflow_state = {}
        if checkpoints is None:
            checkpoints = []
        graph.metadata["workflow_state"] = workflow_state
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
            scheduler_hint = filtered_hint
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

    def failed_id(task: TaskNode) -> str:
        if execution_kind == "goal" and task.step_name is not None:
            return task.step_name
        return task.task_id

    worker_lock = threading.RLock()
    worker_cond = threading.Condition(worker_lock)
    active_workers = 0
    worker_mode = False

    def ready_tasks():
        ready = []
        for task in tasks:
            if task.task_id in pending and all(dep.task_id in results for dep in task.dependencies):
                ready.append(task)
        if scheduler_order_map:
            ready.sort(key=lambda task: scheduler_order_map.get(task.task_id, len(scheduler_order_map)))
        return ready

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
        if isinstance(workflow_state, dict):
            entry["state"] = clone_state(workflow_state)
        if isinstance(checkpoints, list):
            checkpoints.append(entry)
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
            vm,
        )
        persist_checkpoint_snapshot(graph.graph_id, snapshot, label)
        vm.event_bus.emit_event("graph_persist", data={"graph_id": graph.graph_id})

    def _workflow_context(task: TaskNode) -> dict | None:
        if workflow_name is None:
            return None
        context = {
            "graph": graph,
            "graph_id": graph.graph_id,
            "workflow": workflow_name,
            "step": task.step_name,
            "task_id": task.task_id,
            "state": workflow_state,
            "checkpoints": checkpoints,
            "checkpoint": lambda label: _record_checkpoint(task, label),
        }
        if execution_kind == "goal" and isinstance(goal_name, str):
            context["goal"] = goal_name
        return context

    def spawn_task(task: TaskNode, delay_ms: float = 0.0) -> None:
        nonlocal failed, active_workers, worker_mode
        with worker_lock:
            if failed is not None:
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
            args = [results[dep.task_id] for dep in task.dependencies]
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
                    for next_task in ready_tasks():
                        spawn_task(next_task)
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
                            for next_task in ready_tasks():
                                spawn_task(next_task)
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
        task = running.pop(id(coroutine), None)
        if task is None:
            return False
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
            "running",
            pending_queue,
            task_values,
            workflow_state,
            checkpoints,
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
        for next_task in ready_tasks():
            spawn_task(next_task)
        return False

    def _fail_task(task: TaskNode, err: Exception):
        nonlocal failed
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
            vm.event_bus.emit_event("task_retry", name=task.task_id, data={"attempt": float(task.attempts + 1)})
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
                vm,
            )
            vm.event_bus.emit_event("graph_persist", data={"graph_id": graph.graph_id})
            spawn_task(task, delay_ms=task.retry_delay_ms)
            return False
        task.status = "failed"
        task.finished_at = runtime_time_ms()
        task.error = str(err)
        failed = {
            "tasks": task_values,
            "steps": step_results(),
            "failed": [failed_id(task)],
            "error": str(err),
            "timings": timings,
            "attempts": attempts,
            "cache_hits": cache_hits,
            "graph_id": graph.graph_id,
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
        return True

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
            if saved.get("state") in {"completed", "done"}:
                results[task.task_id] = saved.get("result")
                task_values[task.task_id] = saved.get("result")
                task.status = "completed"
                _remove_task_from_pending(task.task_id)
            elif saved.get("state") in {"failed"}:
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
                return failed
            else:
                task.status = "pending"
        for task in tasks:
            if task.task_id not in results and task.task_id not in pending:
                _mark_task_pending(task.task_id)

    for task in ready_tasks():
        spawn_task(task)

    if failed is not None:
        failed.update(workflow_result_payload())
        return failed

    if worker_mode:
        with worker_cond:
            while failed is None and (pending or active_workers > 0):
                worker_cond.wait(timeout=0.05)
    else:
        vm.scheduler.run_loop(on_complete=on_complete, on_error=on_error)

    if failed is not None:
        failed.update(workflow_result_payload())
        return failed

    if pending:
        payload = {
            "tasks": task_values,
            "steps": step_results(),
            "error": "Dependency cycle or missing tasks",
            "timings": timings,
            "attempts": attempts,
            "failed": [],
            "cache_hits": cache_hits,
            "graph_id": graph.graph_id,
        }
        payload.update(workflow_result_payload())
        return payload

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
    return payload


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
    by_id = {task.task_id: task for task in tasks}

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
    result = {"nodes": nodes, "edges": edges, "levels": levels, "parallel_groups": parallel_groups, "graph_id": graph.graph_id}
    if isinstance(graph.metadata, dict):
        result["metadata"] = graph.metadata
    return result
