"""HTTP service mode for Nodus runtime."""

from __future__ import annotations

import json
import threading
from urllib.parse import parse_qs, urlparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from nodus.support.config import SERVER_HOST, SERVER_PORT, SESSION_TIMEOUT_MS, MAX_SESSIONS, WORKER_SWEEP_INTERVAL_MS
from nodus.tooling.runner import (
    agent_call_result,
    build_ast,
    check_source,
    disassemble_source,
    memory_delete_result,
    memory_get_result,
    memory_keys_result,
    memory_put_result,
    run_source,
    run_in_vm,
    run_graph_code,
    run_goal_code,
    plan_graph_code,
    plan_goal_code,
    resume_graph_in_vm,
    resume_goal_in_vm,
    resume_workflow_in_vm,
    run_workflow_code,
    plan_workflow_code,
    resume_goal,
    workflow_checkpoints,
    tool_call_result,
)
from nodus.result import Result, normalize_filename
from nodus.runtime.errors import NodusRuntimeError
from nodus.runtime.diagnostics import LangRuntimeError
from nodus.orchestration.task_graph import load_graph_state, latest_graph_state
from nodus.runtime.sessions import SessionManager
from nodus.runtime.snapshots import SnapshotManager
from nodus.vm.vm import VM
import threading
import time
from nodus.orchestration.task_graph import set_default_dispatcher


class WorkerManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._workers: dict[str, set[str]] = {}
        self._worker_last_seen: dict[str, float] = {}
        self._worker_seen: dict[str, bool] = {}
        self._startup_grace_ms = 250.0
        self._jobs_by_capability: dict[str, list[dict]] = {}
        self._any_jobs: list[dict] = []
        self._inflight: dict[str, dict] = {}
        self._job_counter = 0
        self._timeout_ms = 2000
        self._capability_wait_ms = 2000
        self._worker_heartbeat_timeout_ms = 5000
        self.force_dispatch = False
        self.event_bus = None

    def _emit_event(self, event_type: str, data: dict | None = None) -> None:
        if self.event_bus is None:
            return
        self.event_bus.emit_event(event_type, data=data)

    def _is_expired(self, last_seen: float, now: float, *, grace_ms: float | None = None) -> bool:
        timeout_ms = self._worker_heartbeat_timeout_ms
        if grace_ms is None:
            grace_ms = min(10.0, timeout_ms * 0.5)
        return (now - last_seen) * 1000.0 > (timeout_ms + grace_ms)

    def register(self, capabilities: list[str] | None = None) -> str:
        with self._lock:
            worker_id = f"w_{len(self._workers) + 1}"
            caps = {cap for cap in (capabilities or []) if isinstance(cap, str)}
            self._workers[worker_id] = caps
            self._worker_last_seen[worker_id] = time.monotonic()
            self._worker_seen[worker_id] = False
            self.force_dispatch = True
            self._cond.notify_all()
            return worker_id

    def has_workers(self) -> bool:
        with self._lock:
            return bool(self._workers)

    def heartbeat(self, worker_id: str) -> dict:
        with self._cond:
            now = time.monotonic()
            self._expire_workers(now)
            if worker_id not in self._workers:
                return {"ok": False, "dead": True}
            self._worker_last_seen[worker_id] = now
            self._worker_seen[worker_id] = True
            return {"ok": True}

    def submit(
        self,
        task_id: str,
        args: list,
        execute_fn,
        delay_ms: float = 0.0,
        requirement: str | None = None,
        requirement_timeout_ms: float | None = None,
    ):
        with self._cond:
            if not self.force_dispatch and requirement is None:
                return execute_fn()
            self._expire_workers(time.monotonic())
            if requirement:
                timeout_ms = self._capability_wait_ms if requirement_timeout_ms is None else float(requirement_timeout_ms)
                deadline = time.monotonic() + (timeout_ms / 1000.0)
                while not any(requirement in caps for caps in self._workers.values()):
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        err = RuntimeError(f"No workers registered with capability: {requirement}")
                        setattr(err, "worker_requirement", requirement)
                        setattr(err, "worker_timeout_ms", float(timeout_ms))
                        return err
                    self._cond.wait(timeout=min(0.1, remaining))
            self._job_counter += 1
            job_id = f"job_{self._job_counter}"
            job = {
                "job_id": job_id,
                "task_id": task_id,
                "args": args,
                "execute_fn": execute_fn,
                "delay_until": time.monotonic() + (delay_ms / 1000.0),
                "enqueued_at": time.monotonic(),
                "requirement": requirement,
                "result": None,
                "done": False,
                "assigned_at": None,
            }
            if requirement:
                self._jobs_by_capability.setdefault(requirement, []).append(job)
            else:
                self._any_jobs.append(job)
            self._cond.notify_all()
            while not job["done"]:
                self._cond.wait(timeout=0.1)
            return job["result"]

    def _expire_workers(self, now: float, polling_worker_id: str | None = None) -> bool:
        dead_workers = []
        worker_count = len(self._workers)
        for worker_id, last_seen in list(self._worker_last_seen.items()):
            if not self._is_expired(last_seen, now):
                continue
            if polling_worker_id is not None and worker_id != polling_worker_id and not self._worker_seen.get(worker_id, False):
                continue
            if polling_worker_id is not None and worker_id == polling_worker_id:
                if not self._worker_seen.get(worker_id, False) and worker_count > 1:
                    continue
                dead_workers.append(worker_id)
                continue
            if not self._worker_seen.get(worker_id, False):
                timeout_ms = self._worker_heartbeat_timeout_ms
                grace_ms = min(10.0, timeout_ms * 0.5)
                expire_after = max(timeout_ms + grace_ms, self._startup_grace_ms)
                if (now - last_seen) * 1000.0 <= expire_after:
                    continue
            dead_workers.append(worker_id)
        if not dead_workers:
            return False
        requeued = False
        for worker_id in dead_workers:
            self._workers.pop(worker_id, None)
            self._worker_last_seen.pop(worker_id, None)
            self._worker_seen.pop(worker_id, None)
            self._emit_event("worker_dead", {"worker_id": worker_id})
        for job_id, job in list(self._inflight.items()):
            if job.get("assigned_worker") in dead_workers:
                self._inflight.pop(job_id, None)
                job["assigned_at"] = None
                job["assigned_worker"] = None
                self._requeue(job)
                self._emit_event("task_requeued", {"task_id": job.get("task_id"), "job_id": job_id})
                requeued = True
        self._cond.notify_all()
        return requeued

    def sweep(self) -> None:
        with self._cond:
            self._expire_workers(time.monotonic())

    def _requeue(self, job: dict) -> None:
        requirement = job.get("requirement")
        if requirement:
            self._jobs_by_capability.setdefault(requirement, []).append(job)
        else:
            self._any_jobs.append(job)

    def _find_ready(self, queue: list[dict], now: float):
        for idx, job in enumerate(queue):
            if job["delay_until"] <= now:
                return idx, job
        return None, None

    def _next_job(self, capabilities: set[str], now: float):
        candidates: list[tuple[float, dict, list[dict], int]] = []
        for cap in sorted(capabilities):
            queue = self._jobs_by_capability.get(cap, [])
            idx, job = self._find_ready(queue, now)
            if job is not None:
                candidates.append((job["enqueued_at"], job, queue, idx))
        idx, job = self._find_ready(self._any_jobs, now)
        if job is not None:
            candidates.append((job["enqueued_at"], job, self._any_jobs, idx))
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0])
        _ts, job, queue, idx = candidates[0]
        queue.pop(idx)
        return job

    def poll(self, worker_id: str) -> dict:
        with self._cond:
            now = time.monotonic()
            if worker_id in self._workers:
                last_seen = self._worker_last_seen.get(worker_id, now)
                if not self._is_expired(last_seen, now, grace_ms=0.0):
                    self._worker_last_seen[worker_id] = now
            self._expire_workers(now, polling_worker_id=worker_id)
            if worker_id not in self._workers:
                return {"job_id": None}
            self._worker_last_seen[worker_id] = now
            self._worker_seen[worker_id] = True
            for job in self._inflight.values():
                if job.get("assigned_worker") == worker_id:
                    return {"job_id": job["job_id"], "task_id": job["task_id"], "args": job["args"]}
            for job in list(self._inflight.values()):
                if job["assigned_at"] and (now - job["assigned_at"]) * 1000.0 > self._timeout_ms:
                    job["assigned_at"] = None
                    self._requeue(job)
            job = self._next_job(self._workers.get(worker_id, set()), now)
            if job is not None:
                job["assigned_at"] = now
                job["assigned_worker"] = worker_id
                self._inflight[job["job_id"]] = job
                return {"job_id": job["job_id"], "task_id": job["task_id"], "args": job["args"]}
            return {"job_id": None}

    def wait_for_job(self, worker_id: str, timeout: float = 10.0) -> dict:
        """Block until a job is available for worker_id, then return it.

        Uses the condition variable that submit() already notifies, so there
        is no polling delay and no race between enqueue and wakeup.
        Mirrors poll() logic: checks _inflight for already-assigned jobs
        first, then tries to dequeue a new job from the capability queues.
        """
        deadline = time.monotonic() + timeout
        with self._cond:
            while True:
                now = time.monotonic()
                if worker_id not in self._workers:
                    return {"job_id": None}
                self._worker_last_seen[worker_id] = now
                self._worker_seen[worker_id] = True
                for job in self._inflight.values():
                    if job.get("assigned_worker") == worker_id:
                        return {"job_id": job["job_id"], "task_id": job["task_id"], "args": job["args"]}
                job = self._next_job(self._workers.get(worker_id, set()), now)
                if job is not None:
                    job["assigned_at"] = now
                    job["assigned_worker"] = worker_id
                    self._inflight[job["job_id"]] = job
                    return {"job_id": job["job_id"], "task_id": job["task_id"], "args": job["args"]}
                remaining = deadline - now
                if remaining <= 0:
                    return {"job_id": None}
                self._cond.wait(timeout=min(0.1, remaining))

    def result(self, worker_id: str, job_id: str, status: str, result=None) -> dict:
        with self._cond:
            if worker_id in self._workers:
                self._worker_last_seen[worker_id] = time.monotonic()
            job = self._inflight.pop(job_id, None)
            if job is None:
                return {"ok": False}
            if status == "execute":
                try:
                    result = job["execute_fn"]()
                except Exception as err:
                    result = err
            job["result"] = result
            job["done"] = True
            self._cond.notify_all()
            return {"ok": True}
from nodus.support.version import VERSION

try:
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse

    FASTAPI_AVAILABLE = True
except Exception:
    FASTAPI_AVAILABLE = False

try:
    import uvicorn

    UVICORN_AVAILABLE = True
except Exception:
    UVICORN_AVAILABLE = False


class RuntimeService:
    def __init__(
        self,
        *,
        trace: bool = False,
        session_timeout_ms: int = SESSION_TIMEOUT_MS,
        max_sessions: int = MAX_SESSIONS,
        worker_sweep_interval_ms: int = WORKER_SWEEP_INTERVAL_MS,
        allowed_paths: list[str] | None = None,
        allow_input: bool = False,
        auth_token: str | None = None,
    ):
        self.trace = trace
        self.last_vm = None
        self.sessions = SessionManager(timeout_ms=session_timeout_ms, max_sessions=max_sessions)
        self.snapshots = SnapshotManager()
        self.workers = WorkerManager()
        set_default_dispatcher(self.workers)
        self._worker_sweep_interval_ms = worker_sweep_interval_ms
        self.allowed_paths = allowed_paths
        self.allow_input = allow_input
        self.auth_token = auth_token
        self._sweeper_thread = threading.Thread(target=self._worker_sweeper_loop, daemon=True)
        self._sweeper_thread.start()

    def _worker_sweeper_loop(self):
        while True:
            self.workers.sweep()
            interval = self._worker_sweep_interval_ms / 1000.0
            timeout_ms = getattr(self.workers, "_worker_heartbeat_timeout_ms", None)
            if timeout_ms is not None:
                interval = min(interval, timeout_ms / 1000.0)
            interval = max(0.01, interval)
            with self.workers._cond:
                self.workers._cond.wait(timeout=interval)

    def health(self):
        return {"status": "ok", "runtime": "nodus", "version": VERSION}

    def _session_error(self, message: str, *, stage: str = "execute") -> dict:
        err = NodusRuntimeError(message, filename=normalize_filename(None))
        legacy = {"type": "session", "message": message, "path": None}
        return Result.failure(
            stage=stage,
            filename=normalize_filename(None),
            stdout="",
            stderr="",
            errors=[err.to_dict()],
            error=legacy,
        ).to_dict()

    def _graph_metadata(self, vm, graph_id: str | None = None) -> dict:
        resolved_id = graph_id
        if resolved_id is None and vm is not None and getattr(vm, "last_graph_plan", None):
            resolved_id = vm.last_graph_plan.get("graph_id")
        if resolved_id is None and vm is not None:
            for event in reversed(vm.event_bus.events()):
                if event.type in {"graph_persist", "graph_resume"} and event.data and "graph_id" in event.data:
                    resolved_id = event.data["graph_id"]
                    break
        if resolved_id is None:
            resolved_id, state = latest_graph_state()
        else:
            state = load_graph_state(resolved_id)
        tasks = state.get("tasks", {}) if state else {}
        status = state.get("status") if state else None
        return {"graph_id": resolved_id, "tasks": tasks, "graph_status": status}

    def _apply_runtime_policies(self, vm: VM | None) -> None:
        if vm is None:
            return
        vm.allowed_paths = self.allowed_paths
        if not self.allow_input:
            vm.input_fn = self._blocked_input

    def _blocked_input(self, _prompt: str):
        raise LangRuntimeError("sandbox", "input() is not available in server mode")

    def is_authorized(self, auth_header: str | None) -> bool:
        if not self.auth_token:
            return True
        if not auth_header:
            return False
        expected = f"Bearer {self.auth_token}"
        return auth_header.strip() == expected

    def execute(self, payload: dict):
        code = payload.get("code", "")
        filename = payload.get("filename")
        session_id = payload.get("session")
        if session_id:
            session = self.sessions.get(session_id)
            if session is None:
                return self._session_error("Unknown session", stage="execute")
            self._apply_runtime_policies(session.vm)
            result, vm = run_in_vm(
                session.vm,
                code,
                filename,
                trace=self.trace,
                import_state=session.import_state,
            )
            session.vm = vm
            self.sessions.record_execution(session)
            self.last_vm = vm
            return result
        vm = VM([], {}, code_locs=[], source_path=None, allowed_paths=self.allowed_paths)
        self._apply_runtime_policies(vm)
        vm.worker_dispatcher = self.workers
        result, vm = run_graph_code(vm, code, filename, trace=self.trace)
        if vm is not None:
            self.last_vm = vm
        return result

    def check(self, payload: dict):
        code = payload.get("code", "")
        filename = payload.get("filename")
        return check_source(code, filename)

    def ast(self, payload: dict):
        code = payload.get("code", "")
        filename = payload.get("filename")
        return build_ast(code, filename)

    def dis(self, payload: dict):
        code = payload.get("code", "")
        filename = payload.get("filename")
        return disassemble_source(code, filename)

    def disassemble(self, payload: dict):
        return self.dis(payload)

    def graph(self, payload: dict):
        code = payload.get("code", "")
        filename = payload.get("filename")
        session_id = payload.get("session")
        set_default_dispatcher(self.workers)
        if session_id:
            session = self.sessions.get(session_id)
            if session is None:
                return self._session_error("Unknown session", stage="execute")
            session.vm.worker_dispatcher = self.workers
            self._apply_runtime_policies(session.vm)
            result, vm = run_graph_code(
                session.vm,
                code,
                filename,
                trace=self.trace,
                import_state=session.import_state,
            )
            session.vm = vm
            self.sessions.record_execution(session)
            self.last_vm = vm
            return result
        input_fn = None if self.allow_input else self._blocked_input
        result, vm = run_source(code, filename, trace=self.trace, allowed_paths=self.allowed_paths, input_fn=input_fn)
        if vm is not None:
            vm.worker_dispatcher = self.workers
            self.last_vm = vm
        return result

    def graph_run(self, payload: dict):
        result = self.graph(payload)
        vm = self.last_vm
        result.update(self._graph_metadata(vm))
        return result

    def graph_plan(self, payload: dict):
        code = payload.get("code", "")
        filename = payload.get("filename")
        session_id = payload.get("session")
        if session_id:
            session = self.sessions.get(session_id)
            if session is None:
                return self._session_error("Unknown session", stage="plan_graph")
            self._apply_runtime_policies(session.vm)
            result, vm = plan_graph_code(
                session.vm,
                code,
                filename,
                trace=self.trace,
                import_state=session.import_state,
            )
            session.vm = vm
            self.sessions.record_execution(session)
            self.last_vm = vm
            if result.get("ok"):
                result.update(self._graph_metadata(vm, result.get("plan", {}).get("graph_id")))
            return result
        plan_vm = VM([], {}, code_locs=[], source_path=None, allowed_paths=self.allowed_paths)
        self._apply_runtime_policies(plan_vm)
        result, vm = plan_graph_code(plan_vm, code, filename, trace=self.trace)
        if vm is not None:
            self.last_vm = vm
        if result.get("ok"):
            result.update(self._graph_metadata(vm, result.get("plan", {}).get("graph_id")))
        return result

    def resume_graph(self, payload: dict):
        graph_id = payload.get("graph_id")
        if not graph_id:
            err = NodusRuntimeError("Missing graph_id", filename=normalize_filename(None))
            legacy = {"type": "graph", "message": "Missing graph_id", "path": None}
            return Result.failure(
                stage="resume_graph",
                filename=normalize_filename(None),
                stdout="",
                stderr="",
                errors=[err.to_dict()],
                error=legacy,
            ).to_dict()
        session_id = payload.get("session")
        if session_id:
            session = self.sessions.get(session_id)
            if session is None:
                return self._session_error("Unknown session", stage="resume_graph")
            self._apply_runtime_policies(session.vm)
            result, vm = resume_graph_in_vm(session.vm, graph_id)
            session.vm = vm
            self.sessions.record_execution(session)
            self.last_vm = vm
            if result.get("ok"):
                result.update(self._graph_metadata(vm, graph_id))
            return result
        vm = self.last_vm or VM([], {}, code_locs=[], source_path=None, allowed_paths=self.allowed_paths)
        self._apply_runtime_policies(vm)
        result, vm = resume_graph_in_vm(vm, graph_id)
        if vm is not None:
            self.last_vm = vm
        if result.get("ok"):
            result.update(self._graph_metadata(vm, graph_id))
        return result

    def graph_resume(self, payload: dict):
        return self.resume_graph(payload)

    def workflow_run(self, payload: dict):
        code = payload.get("code", "")
        filename = payload.get("filename")
        workflow_name = payload.get("workflow")
        vm = VM([], {}, code_locs=[], source_path=None, allowed_paths=self.allowed_paths)
        self._apply_runtime_policies(vm)
        vm.worker_dispatcher = self.workers
        result, vm = run_workflow_code(vm, code, filename, workflow_name=workflow_name, trace=self.trace)
        if vm is not None:
            self.last_vm = vm
        if result.get("ok"):
            result.update(self._graph_metadata(vm, result.get("result", {}).get("graph_id")))
        return result

    def workflow_plan(self, payload: dict):
        code = payload.get("code", "")
        filename = payload.get("filename")
        workflow_name = payload.get("workflow")
        vm = VM([], {}, code_locs=[], source_path=None, allowed_paths=self.allowed_paths)
        self._apply_runtime_policies(vm)
        result, vm = plan_workflow_code(vm, code, filename, workflow_name=workflow_name, trace=self.trace)
        if vm is not None:
            self.last_vm = vm
        if result.get("ok"):
            result.update(self._graph_metadata(vm, result.get("plan", {}).get("graph_id")))
        return result

    def goal_run(self, payload: dict):
        code = payload.get("code", "")
        filename = payload.get("filename")
        goal_name = payload.get("goal")
        vm = VM([], {}, code_locs=[], source_path=None, allowed_paths=self.allowed_paths)
        self._apply_runtime_policies(vm)
        vm.worker_dispatcher = self.workers
        result, vm = run_goal_code(vm, code, filename, goal_name=goal_name, trace=self.trace)
        if vm is not None:
            self.last_vm = vm
        if result.get("ok"):
            result.update(self._graph_metadata(vm, result.get("result", {}).get("graph_id")))
        return result

    def goal_plan(self, payload: dict):
        code = payload.get("code", "")
        filename = payload.get("filename")
        goal_name = payload.get("goal")
        vm = VM([], {}, code_locs=[], source_path=None, allowed_paths=self.allowed_paths)
        self._apply_runtime_policies(vm)
        result, vm = plan_goal_code(vm, code, filename, goal_name=goal_name, trace=self.trace)
        if vm is not None:
            self.last_vm = vm
        if result.get("ok"):
            result.update(self._graph_metadata(vm, result.get("plan", {}).get("graph_id")))
        return result

    def workflow_resume(self, payload: dict):
        graph_id = payload.get("graph_id")
        checkpoint = payload.get("checkpoint")
        if not graph_id:
            err = NodusRuntimeError("Missing graph_id", filename=normalize_filename(None))
            legacy = {"type": "graph", "message": "Missing graph_id", "path": None}
            return Result.failure(
                stage="resume_workflow",
                filename=normalize_filename(None),
                stdout="",
                stderr="",
                errors=[err.to_dict()],
                error=legacy,
            ).to_dict()
        session_id = payload.get("session")
        if session_id:
            session = self.sessions.get(session_id)
            if session is None:
                return self._session_error("Unknown session", stage="resume_workflow")
            self._apply_runtime_policies(session.vm)
            result, vm = resume_workflow_in_vm(session.vm, graph_id, checkpoint)
            session.vm = vm
            self.sessions.record_execution(session)
            self.last_vm = vm
            if result.get("ok"):
                result.update(self._graph_metadata(vm, graph_id))
            return result
        vm = self.last_vm or VM([], {}, code_locs=[], source_path=None, allowed_paths=self.allowed_paths)
        self._apply_runtime_policies(vm)
        result, vm = resume_workflow_in_vm(vm, graph_id, checkpoint)
        if vm is not None:
            self.last_vm = vm
        if result.get("ok"):
            result.update(self._graph_metadata(vm, graph_id))
        return result

    def goal_resume(self, payload: dict):
        graph_id = payload.get("graph_id")
        checkpoint = payload.get("checkpoint")
        if not graph_id:
            err = NodusRuntimeError("Missing graph_id", filename=normalize_filename(None))
            legacy = {"type": "graph", "message": "Missing graph_id", "path": None}
            return Result.failure(
                stage="resume_goal",
                filename=normalize_filename(None),
                stdout="",
                stderr="",
                errors=[err.to_dict()],
                error=legacy,
            ).to_dict()
        session_id = payload.get("session")
        if session_id:
            session = self.sessions.get(session_id)
            if session is None:
                return self._session_error("Unknown session", stage="resume_goal")
            self._apply_runtime_policies(session.vm)
            result, vm = resume_goal_in_vm(session.vm, graph_id, checkpoint)
            session.vm = vm
            self.sessions.record_execution(session)
            self.last_vm = vm
            if result.get("ok"):
                result.update(self._graph_metadata(vm, graph_id))
            return result
        vm = self.last_vm or VM([], {}, code_locs=[], source_path=None, allowed_paths=self.allowed_paths)
        self._apply_runtime_policies(vm)
        result, vm = resume_goal_in_vm(vm, graph_id, checkpoint)
        if vm is not None:
            self.last_vm = vm
        if result.get("ok"):
            result.update(self._graph_metadata(vm, graph_id))
        return result

    def workflow_checkpoints(self, graph_id: str):
        if not graph_id:
            return {"ok": False, "error": "Missing graph_id", "checkpoints": []}
        return workflow_checkpoints(graph_id)

    def worker_register(self, payload: dict):
        capabilities = payload.get("capabilities") if isinstance(payload, dict) else None
        if not isinstance(capabilities, list):
            capabilities = []
        return {"worker_id": self.workers.register(capabilities)}

    def worker_poll(self, payload: dict):
        worker_id = payload.get("worker_id")
        return self.workers.poll(worker_id)

    def worker_heartbeat(self, payload: dict):
        worker_id = payload.get("worker_id")
        return self.workers.heartbeat(worker_id)

    def worker_result(self, payload: dict):
        worker_id = payload.get("worker_id")
        job_id = payload.get("job_id")
        status = payload.get("status", "ok")
        result = payload.get("result")
        return self.workers.result(worker_id, job_id, status, result)

    def tool_call(self, payload: dict):
        return tool_call_result(payload.get("name"), payload.get("args", {}), vm=self.last_vm)

    def agent_call(self, payload: dict):
        return agent_call_result(payload.get("name"), payload.get("payload"), vm=self.last_vm)

    def memory_get(self, key: str | None = None):
        if key is None:
            return memory_keys_result(vm=self.last_vm)
        return memory_get_result(key, vm=self.last_vm)

    def memory_put(self, payload: dict):
        return memory_put_result(payload.get("key"), payload.get("value"), vm=self.last_vm)

    def memory_delete(self, key: str):
        return memory_delete_result(key, vm=self.last_vm)

    def create_session(self):
        vm = VM([], {}, code_locs=[], source_path=None, allowed_paths=self.allowed_paths)
        self._apply_runtime_policies(vm)
        session = self.sessions.create(vm)
        return {"session": session.id}

    def list_sessions(self):
        return {"sessions": self.sessions.list_sessions()}

    def create_snapshot(self, payload: dict):
        session_id = payload.get("session")
        if not session_id:
            return {"error": "missing session"}
        session = self.sessions.get(session_id)
        if session is None:
            return {"error": "unknown session"}
        state_blob = {
            "vm": session.vm.export_state(),
            "import_state": session.import_state,
            "session_meta": {
                "created_time": session.created_time,
                "last_access": session.last_access,
                "execution_count": session.execution_count,
            },
        }
        snapshot = self.snapshots.create(session_id, state_blob)
        return {"snapshot": snapshot.snapshot_id}

    def restore_snapshot(self, payload: dict):
        snapshot_id = payload.get("snapshot")
        if not snapshot_id:
            return {"error": "missing snapshot"}
        snapshot = self.snapshots.get(snapshot_id)
        if snapshot is None:
            return {"error": "unknown snapshot"}
        state_blob = snapshot.state_blob
        vm_state = state_blob.get("vm", {})
        import_state = state_blob.get("import_state")
        session = self.sessions.create_from_state(vm_state, import_state=import_state)
        self._apply_runtime_policies(session.vm)
        return {"session": session.id}

    def list_snapshots(self):
        return {"snapshots": self.snapshots.list_snapshots()}

    def delete_snapshot(self, snapshot_id: str):
        ok = self.snapshots.delete(snapshot_id)
        return {"ok": ok}

    def runtime_info(self):
        vm = self.last_vm
        if vm is None:
            return {
                "scheduler": {
                    "ready": 0.0,
                    "sleeping": 0.0,
                    "completed": 0.0,
                    "spawned": 0.0,
                    "resumes": 0.0,
                    "ready_queue": [],
                    "sleeping_tasks": [],
                    "completed_tasks": [],
                },
                "tasks": [],
                "event_count": 0.0,
            }
        return {
            "scheduler": vm.builtin_runtime_scheduler_stats(),
            "tasks": vm.builtin_runtime_tasks(),
            "event_count": vm.builtin_runtime_event_count(),
        }

    def runtime_events(self):
        vm = self.last_vm
        events = [event.to_dict() for event in vm.event_bus.events()] if vm is not None else []
        return {"ok": True, "events": events}


def _read_json(handler: BaseHTTPRequestHandler) -> dict:
    length = int(handler.headers.get("Content-Length", "0"))
    if length <= 0:
        return {}
    raw = handler.rfile.read(length)
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return {}


def _write_json(handler: BaseHTTPRequestHandler, payload: dict, status: int = 200) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _unauthorized(handler: BaseHTTPRequestHandler) -> None:
    _write_json(handler, {"error": "unauthorized"}, status=401)


def _json_post(host: str, port: int, path: str, payload: dict, *, token: str | None = None):
    import http.client

    conn = http.client.HTTPConnection(host, port, timeout=5)
    body = json.dumps(payload)
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    conn.request("POST", path, body=body, headers=headers)
    resp = conn.getresponse()
    data = resp.read().decode("utf-8")
    conn.close()
    if not data:
        return {}
    return json.loads(data)


def _json_get(host: str, port: int, path: str, *, token: str | None = None):
    import http.client

    conn = http.client.HTTPConnection(host, port, timeout=5)
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    conn.request("GET", path, headers=headers)
    resp = conn.getresponse()
    data = resp.read().decode("utf-8")
    conn.close()
    if not data:
        return {}
    return json.loads(data)


def _is_local_host(host: str) -> bool:
    return host in {"127.0.0.1", "localhost", "::1"}


def snapshot_session(host: str, port: int, session_id: str, *, token: str | None = None) -> dict:
    return _json_post(host, port, "/snapshot", {"session": session_id}, token=token)


def restore_snapshot(host: str, port: int, snapshot_id: str, *, token: str | None = None) -> dict:
    return _json_post(host, port, "/restore", {"snapshot": snapshot_id}, token=token)


def list_snapshots(host: str, port: int, *, token: str | None = None) -> dict:
    return _json_get(host, port, "/snapshots", token=token)


def start_http_server(service: RuntimeService, host: str, port: int) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, _format, *_args):
            return

        def do_GET(self):
            if not service.is_authorized(self.headers.get("Authorization")):
                _unauthorized(self)
                return
            parsed = urlparse(self.path)
            if parsed.path == "/health":
                _write_json(self, service.health())
                return
            if parsed.path == "/sessions":
                _write_json(self, service.list_sessions())
                return
            if parsed.path == "/snapshots":
                _write_json(self, service.list_snapshots())
                return
            if parsed.path == "/runtime":
                _write_json(self, service.runtime_info())
                return
            if parsed.path == "/runtime/events":
                _write_json(self, service.runtime_events())
                return
            if parsed.path == "/memory":
                query = parse_qs(parsed.query)
                key = query.get("key", [None])[0]
                _write_json(self, service.memory_get(key))
                return
            if parsed.path.startswith("/workflow/checkpoints/"):
                graph_id = parsed.path.split("/", 3)[3]
                _write_json(self, service.workflow_checkpoints(graph_id))
                return
            _write_json(self, {"error": "not found"}, status=404)

        def do_POST(self):
            if not service.is_authorized(self.headers.get("Authorization")):
                _unauthorized(self)
                return
            payload = _read_json(self)
            if self.path == "/session":
                _write_json(self, service.create_session())
                return
            if self.path == "/snapshot":
                _write_json(self, service.create_snapshot(payload))
                return
            if self.path == "/restore":
                _write_json(self, service.restore_snapshot(payload))
                return
            if self.path == "/execute":
                _write_json(self, service.execute(payload))
                return
            if self.path == "/graph":
                _write_json(self, service.graph(payload))
                return
            if self.path == "/graph_plan":
                _write_json(self, service.graph_plan(payload))
                return
            if self.path == "/resume_graph":
                _write_json(self, service.resume_graph(payload))
                return
            if self.path == "/plan_graph":
                _write_json(self, service.graph_plan(payload))
                return
            if self.path == "/workflow/run":
                _write_json(self, service.workflow_run(payload))
                return
            if self.path == "/workflow/plan":
                _write_json(self, service.workflow_plan(payload))
                return
            if self.path == "/workflow/resume":
                _write_json(self, service.workflow_resume(payload))
                return
            if self.path == "/goal/run":
                _write_json(self, service.goal_run(payload))
                return
            if self.path == "/goal/plan":
                _write_json(self, service.goal_plan(payload))
                return
            if self.path == "/goal/resume":
                _write_json(self, service.goal_resume(payload))
                return
            if self.path == "/disassemble":
                _write_json(self, service.disassemble(payload))
                return
            if self.path == "/graph/run":
                _write_json(self, service.graph_run(payload))
                return
            if self.path == "/graph/plan":
                _write_json(self, service.graph_plan(payload))
                return
            if self.path == "/graph/resume":
                _write_json(self, service.graph_resume(payload))
                return
            if self.path == "/worker/register":
                _write_json(self, service.worker_register(payload))
                return
            if self.path == "/worker/poll":
                _write_json(self, service.worker_poll(payload))
                return
            if self.path == "/worker/heartbeat":
                _write_json(self, service.worker_heartbeat(payload))
                return
            if self.path == "/worker/result":
                _write_json(self, service.worker_result(payload))
                return
            if self.path == "/check":
                _write_json(self, service.check(payload))
                return
            if self.path == "/ast":
                _write_json(self, service.ast(payload))
                return
            if self.path == "/dis":
                _write_json(self, service.dis(payload))
                return
            if self.path == "/tool/call":
                _write_json(self, service.tool_call(payload))
                return
            if self.path == "/agent/call":
                _write_json(self, service.agent_call(payload))
                return
            if self.path == "/memory":
                _write_json(self, service.memory_put(payload))
                return
            _write_json(self, {"error": "not found"}, status=404)

        def do_DELETE(self):
            if not service.is_authorized(self.headers.get("Authorization")):
                _unauthorized(self)
                return
            if self.path.startswith("/snapshot/"):
                snapshot_id = self.path.split("/", 2)[2]
                _write_json(self, service.delete_snapshot(snapshot_id))
                return
            if self.path.startswith("/memory/"):
                key = self.path.split("/", 2)[2]
                _write_json(self, service.memory_delete(key))
                return
            _write_json(self, {"error": "not found"}, status=404)

    server = ThreadingHTTPServer((host, port), Handler)
    server.service = service
    return server


def create_fastapi_app(service: RuntimeService):
    if not FASTAPI_AVAILABLE:
        return None
    app = FastAPI()

    if service.auth_token:
        @app.middleware("http")
        async def auth_middleware(request: Request, call_next):
            if not service.is_authorized(request.headers.get("Authorization")):
                return JSONResponse({"error": "unauthorized"}, status_code=401)
            return await call_next(request)

    @app.get("/health")
    def health():
        return service.health()

    @app.get("/runtime")
    def runtime():
        return service.runtime_info()

    @app.get("/runtime/events")
    def runtime_events():
        return service.runtime_events()

    @app.get("/memory")
    def memory(key: str | None = None):
        return JSONResponse(service.memory_get(key))

    @app.get("/workflow/checkpoints/{graph_id}")
    def workflow_checkpoints(graph_id: str):
        return JSONResponse(service.workflow_checkpoints(graph_id))

    @app.get("/sessions")
    def sessions():
        return service.list_sessions()

    @app.get("/snapshots")
    def snapshots():
        return service.list_snapshots()

    @app.post("/session")
    async def session():
        return JSONResponse(service.create_session())

    @app.post("/snapshot")
    async def snapshot(request: Request):
        payload = await request.json()
        return JSONResponse(service.create_snapshot(payload))

    @app.post("/restore")
    async def restore(request: Request):
        payload = await request.json()
        return JSONResponse(service.restore_snapshot(payload))

    @app.delete("/snapshot/{snapshot_id}")
    async def delete_snapshot(snapshot_id: str):
        return JSONResponse(service.delete_snapshot(snapshot_id))

    @app.post("/execute")
    async def execute(request: Request):
        payload = await request.json()
        return JSONResponse(service.execute(payload))

    @app.post("/graph")
    async def graph(request: Request):
        payload = await request.json()
        return JSONResponse(service.graph(payload))

    @app.post("/graph_plan")
    async def graph_plan(request: Request):
        payload = await request.json()
        return JSONResponse(service.graph_plan(payload))

    @app.post("/resume_graph")
    async def resume_graph(request: Request):
        payload = await request.json()
        return JSONResponse(service.resume_graph(payload))

    @app.post("/plan_graph")
    async def plan_graph(request: Request):
        payload = await request.json()
        return JSONResponse(service.graph_plan(payload))

    @app.post("/workflow/run")
    async def workflow_run(request: Request):
        payload = await request.json()
        return JSONResponse(service.workflow_run(payload))

    @app.post("/workflow/plan")
    async def workflow_plan(request: Request):
        payload = await request.json()
        return JSONResponse(service.workflow_plan(payload))

    @app.post("/workflow/resume")
    async def workflow_resume(request: Request):
        payload = await request.json()
        return JSONResponse(service.workflow_resume(payload))

    @app.post("/goal/run")
    async def goal_run(request: Request):
        payload = await request.json()
        return JSONResponse(service.goal_run(payload))

    @app.post("/goal/plan")
    async def goal_plan(request: Request):
        payload = await request.json()
        return JSONResponse(service.goal_plan(payload))

    @app.post("/goal/resume")
    async def goal_resume(request: Request):
        payload = await request.json()
        return JSONResponse(service.goal_resume(payload))

    @app.post("/disassemble")
    async def disassemble(request: Request):
        payload = await request.json()
        return JSONResponse(service.disassemble(payload))

    @app.post("/graph/run")
    async def graph_run(request: Request):
        payload = await request.json()
        return JSONResponse(service.graph_run(payload))

    @app.post("/graph/plan")
    async def graph_plan_v2(request: Request):
        payload = await request.json()
        return JSONResponse(service.graph_plan(payload))

    @app.post("/graph/resume")
    async def graph_resume(request: Request):
        payload = await request.json()
        return JSONResponse(service.graph_resume(payload))

    @app.post("/worker/register")
    async def worker_register(request: Request):
        payload = await request.json()
        return JSONResponse(service.worker_register(payload))

    @app.post("/worker/poll")
    async def worker_poll(request: Request):
        payload = await request.json()
        return JSONResponse(service.worker_poll(payload))

    @app.post("/worker/heartbeat")
    async def worker_heartbeat(request: Request):
        payload = await request.json()
        return JSONResponse(service.worker_heartbeat(payload))

    @app.post("/worker/result")
    async def worker_result(request: Request):
        payload = await request.json()
        return JSONResponse(service.worker_result(payload))

    @app.post("/tool/call")
    async def tool_call(request: Request):
        payload = await request.json()
        return JSONResponse(service.tool_call(payload))

    @app.post("/agent/call")
    async def agent_call(request: Request):
        payload = await request.json()
        return JSONResponse(service.agent_call(payload))

    @app.post("/memory")
    async def memory_put(request: Request):
        payload = await request.json()
        return JSONResponse(service.memory_put(payload))

    @app.delete("/memory/{key}")
    async def memory_delete(key: str):
        return JSONResponse(service.memory_delete(key))

    @app.post("/check")
    async def check(request: Request):
        payload = await request.json()
        return JSONResponse(service.check(payload))

    @app.post("/ast")
    async def ast(request: Request):
        payload = await request.json()
        return JSONResponse(service.ast(payload))

    @app.post("/dis")
    async def dis(request: Request):
        payload = await request.json()
        return JSONResponse(service.dis(payload))

    return app


def serve(
    host: str = SERVER_HOST,
    port: int = SERVER_PORT,
    *,
    trace: bool = False,
    worker_sweep_interval_ms: int = WORKER_SWEEP_INTERVAL_MS,
    allowed_paths: list[str] | None = None,
    allow_input: bool = False,
    auth_token: str | None = None,
) -> None:
    if not _is_local_host(host) and not auth_token:
        raise ValueError("Refusing to bind to non-local host without an auth token.")
    service = RuntimeService(
        trace=trace,
        worker_sweep_interval_ms=worker_sweep_interval_ms,
        allowed_paths=allowed_paths,
        allow_input=allow_input,
        auth_token=auth_token,
    )
    if FASTAPI_AVAILABLE and UVICORN_AVAILABLE:
        app = create_fastapi_app(service)
        uvicorn.run(app, host=host, port=port, log_level="info")
        return

    server = start_http_server(service, host, port)
    server.serve_forever()


def run_in_thread(
    host: str,
    port: int,
    trace: bool = False,
    session_timeout_ms: int = SESSION_TIMEOUT_MS,
    max_sessions: int = MAX_SESSIONS,
    worker_sweep_interval_ms: int = WORKER_SWEEP_INTERVAL_MS,
    allowed_paths: list[str] | None = None,
    allow_input: bool = False,
    auth_token: str | None = None,
):
    if not _is_local_host(host) and not auth_token:
        raise ValueError("Refusing to bind to non-local host without an auth token.")
    service = RuntimeService(
        trace=trace,
        session_timeout_ms=session_timeout_ms,
        max_sessions=max_sessions,
        worker_sweep_interval_ms=worker_sweep_interval_ms,
        allowed_paths=allowed_paths,
        allow_input=allow_input,
        auth_token=auth_token,
    )
    server = start_http_server(service, host, port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread
