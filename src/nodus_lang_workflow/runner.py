"""Framework runner layered over Nodus task-graph execution."""

from __future__ import annotations

import os
import threading

from nodus.orchestration.task_graph import (
    TaskGraph,
    get_registered_graph,
    get_registered_vm,
    load_graph_state,
    register_graph,
    register_graph_vm,
    run_task_graph,
)
from nodus.runtime.runtime_stats import runtime_time_ms

from .models import (
    RUN_STATUS_COMPLETED,
    RUN_STATUS_DEAD_LETTERED,
    RUN_STATUS_FAILED,
    RUN_STATUS_RETRY_SCHEDULED,
    RUN_STATUS_RUNNING,
    RUN_STATUS_WAITING,
    WorkflowRunRecord,
)
from .store import LocalWorkflowStore, WorkflowStore, create_workflow_store


_DEFAULT_RUNNER = None
_DEFAULT_RUNNER_ROOT = None
_DEFAULT_RUNNER_LOCK = threading.Lock()
_REHYDRATABLE_STATUSES = {RUN_STATUS_WAITING, RUN_STATUS_RUNNING, RUN_STATUS_RETRY_SCHEDULED}
_KNOWN_RUN_STATUSES = {
    "pending",
    RUN_STATUS_RUNNING,
    RUN_STATUS_WAITING,
    RUN_STATUS_RETRY_SCHEDULED,
    RUN_STATUS_COMPLETED,
    RUN_STATUS_FAILED,
    RUN_STATUS_DEAD_LETTERED,
}


def _normalize_statuses(statuses: set[str] | None) -> set[str] | None:
    if not statuses:
        return None
    normalized = {status for status in statuses if status in _KNOWN_RUN_STATUSES}
    return normalized or set()


def _matches_has_retry(record: WorkflowRunRecord, expected: bool | None) -> bool:
    if expected is None:
        return True
    return isinstance(record.metadata.get("retry"), dict) is expected


def _matches_has_wait(record: WorkflowRunRecord, expected: bool | None) -> bool:
    if expected is None:
        return True
    return (record.wait is not None) is expected


def _matches_replay_count_min(record: WorkflowRunRecord, minimum: int | None) -> bool:
    if minimum is None:
        return True
    value = record.metadata.get("replay_count", 0)
    if not isinstance(value, int):
        value = 0
    return value >= minimum


def _matches_updated_after(record: WorkflowRunRecord, updated_after_ms: float | None) -> bool:
    if updated_after_ms is None:
        return True
    updated_at = record.updated_at
    if not isinstance(updated_at, (int, float)):
        return False
    return float(updated_at) >= float(updated_after_ms)


def _matches_updated_before(record: WorkflowRunRecord, updated_before_ms: float | None) -> bool:
    if updated_before_ms is None:
        return True
    updated_at = record.updated_at
    if not isinstance(updated_at, (int, float)):
        return False
    return float(updated_at) <= float(updated_before_ms)


def _apply_run_filters(
    records: list[WorkflowRunRecord],
    *,
    statuses: set[str] | None = None,
    workflow_name: str | None = None,
    execution_kind: str | None = None,
    updated_after_ms: float | None = None,
    updated_before_ms: float | None = None,
    has_retry: bool | None = None,
    has_wait: bool | None = None,
    replay_count_min: int | None = None,
) -> list[WorkflowRunRecord]:
    normalized = _normalize_statuses(statuses)
    if normalized == set():
        return []
    filtered = records
    if normalized:
        filtered = [record for record in filtered if record.status in normalized]
    if workflow_name is not None:
        filtered = [record for record in filtered if record.workflow_name == workflow_name]
    if execution_kind is not None:
        filtered = [record for record in filtered if record.execution_kind == execution_kind]
    filtered = [
        record
        for record in filtered
        if _matches_updated_after(record, updated_after_ms)
        and _matches_updated_before(record, updated_before_ms)
        and _matches_has_retry(record, has_retry)
        and _matches_has_wait(record, has_wait)
        and _matches_replay_count_min(record, replay_count_min)
    ]
    return filtered


def _cursor_offset(cursor: str | None) -> int | None:
    if cursor is None:
        return None
    raw = str(cursor).strip()
    if not raw:
        return None
    if raw.startswith("o:"):
        raw = raw[2:]
    try:
        return max(0, int(raw))
    except ValueError:
        return None


def _encode_cursor(offset: int | None) -> str | None:
    if offset is None:
        return None
    return f"o:{max(0, int(offset))}"


def _paginate_run_records(
    records: list[WorkflowRunRecord],
    *,
    limit: int | None = None,
    offset: int = 0,
    cursor: str | None = None,
) -> tuple[list[WorkflowRunRecord], dict[str, int | bool | str | None]]:
    cursor_offset = _cursor_offset(cursor)
    start = cursor_offset if cursor_offset is not None else max(0, int(offset))
    total = len(records)
    if limit is None:
        page = records[start:]
        return page, {
            "total": total,
            "returned": len(page),
            "limit": None,
            "offset": start,
            "has_more": start + len(page) < total,
            "cursor": _encode_cursor(start),
            "next_cursor": None,
        }
    size = max(0, int(limit))
    page = records[start : start + size]
    next_offset = start + len(page)
    return page, {
        "total": total,
        "returned": len(page),
        "limit": size,
        "offset": start,
        "has_more": next_offset < total,
        "cursor": _encode_cursor(start),
        "next_cursor": _encode_cursor(next_offset) if next_offset < total else None,
    }


def _result_is_error_record(result) -> bool:
    return getattr(result, "kind", None) == "error"


def _result_status(result) -> tuple[str, str | None]:
    if isinstance(result, dict) and result.get("status") == "waiting":
        return RUN_STATUS_WAITING, None
    if isinstance(result, dict) and result.get("status") == "retry_scheduled":
        retry = result.get("retry")
        last_error = retry.get("last_error") if isinstance(retry, dict) else None
        return RUN_STATUS_RETRY_SCHEDULED, last_error if isinstance(last_error, str) else None
    if _result_is_error_record(result):
        payload = getattr(result, "fields", {})
        return RUN_STATUS_FAILED, payload.get("message")
    if isinstance(result, dict):
        if result.get("ok") is False:
            return RUN_STATUS_FAILED, result.get("error")
        failed = result.get("failed")
        if isinstance(failed, list) and failed:
            return RUN_STATUS_FAILED, result.get("error")
    return RUN_STATUS_COMPLETED, None


def _current_checkpoint_label(result) -> str | None:
    if not isinstance(result, dict):
        return None
    checkpoints = result.get("checkpoints")
    if not isinstance(checkpoints, list) or not checkpoints:
        return None
    last = checkpoints[-1]
    if not isinstance(last, dict):
        return None
    label = last.get("label")
    return label if isinstance(label, str) else None


def _mark_wait_from_result(
    runner: "WorkflowFrameworkRunner",
    graph_id: str,
    result,
) -> None:
    if not isinstance(result, dict):
        return
    if result.get("status") != "waiting":
        return
    wait = result.get("wait")
    if not isinstance(wait, dict):
        return
    runner.mark_waiting(
        graph_id,
        event_type=wait.get("event_type") if isinstance(wait.get("event_type"), str) else "workflow.wait",
        correlation_key=wait.get("correlation_key") if isinstance(wait.get("correlation_key"), str) else None,
        payload=wait.get("payload") if isinstance(wait.get("payload"), dict) else {},
        deadline_ms=wait.get("deadline_ms") if isinstance(wait.get("deadline_ms"), (int, float)) else None,
    )


def _mark_retry_from_result(
    runner: "WorkflowFrameworkRunner",
    graph_id: str,
    result,
) -> None:
    if not isinstance(result, dict):
        return
    if result.get("status") != "retry_scheduled":
        return
    retry = result.get("retry")
    if not isinstance(retry, dict):
        return
    runner.store.schedule_retry(
        graph_id,
        task_id=retry.get("task_id") if isinstance(retry.get("task_id"), str) else None,
        step_name=retry.get("step") if isinstance(retry.get("step"), str) else None,
        attempt=float(retry.get("attempt")) if isinstance(retry.get("attempt"), (int, float)) else None,
        max_retries=float(retry.get("max_retries")) if isinstance(retry.get("max_retries"), (int, float)) else None,
        delay_ms=float(retry.get("delay_ms")) if isinstance(retry.get("delay_ms"), (int, float)) else None,
        next_attempt_at=float(retry.get("next_attempt_at")) if isinstance(retry.get("next_attempt_at"), (int, float)) else None,
        classification=retry.get("classification") if isinstance(retry.get("classification"), str) else None,
        last_error=retry.get("last_error") if isinstance(retry.get("last_error"), str) else None,
    )


def _mark_terminal_retry_from_result(
    record: WorkflowRunRecord,
    result,
) -> None:
    if not isinstance(result, dict):
        return
    retry = result.get("retry")
    if not isinstance(retry, dict):
        return
    record.metadata["retry"] = dict(retry)


def _metadata_from_graph(graph: TaskGraph, vm) -> dict[str, object]:
    metadata = dict(graph.metadata) if isinstance(graph.metadata, dict) else {}
    metadata.setdefault("source_path", getattr(vm, "source_path", None))
    metadata.setdefault("coordination_mode", "local_only")
    metadata.setdefault("framework", "nodus_lang_workflow")
    metadata.setdefault("framework_created_at", runtime_time_ms())
    return metadata


class WorkflowFrameworkRunner:
    def __init__(self, store: WorkflowStore | None = None) -> None:
        self.store = store or LocalWorkflowStore()

    def get_run(self, run_id: str) -> WorkflowRunRecord | None:
        return self.store.get_run(run_id)

    def list_runs(self) -> list[WorkflowRunRecord]:
        return self.store.list_runs()

    def list_runs_filtered(
        self,
        *,
        statuses: set[str] | None = None,
        workflow_name: str | None = None,
        execution_kind: str | None = None,
        updated_after_ms: float | None = None,
        updated_before_ms: float | None = None,
        has_retry: bool | None = None,
        has_wait: bool | None = None,
        replay_count_min: int | None = None,
        limit: int | None = None,
        offset: int = 0,
        cursor: str | None = None,
    ) -> list[WorkflowRunRecord]:
        filtered = _apply_run_filters(
            self.list_runs(),
            statuses=statuses,
            workflow_name=workflow_name,
            execution_kind=execution_kind,
            updated_after_ms=updated_after_ms,
            updated_before_ms=updated_before_ms,
            has_retry=has_retry,
            has_wait=has_wait,
            replay_count_min=replay_count_min,
        )
        page, _meta = _paginate_run_records(filtered, limit=limit, offset=offset, cursor=cursor)
        return page

    def run_status_counts(self, records: list[WorkflowRunRecord] | None = None) -> dict[str, int]:
        counts = {status: 0 for status in sorted(_KNOWN_RUN_STATUSES)}
        source = records if records is not None else self.list_runs()
        for record in source:
            counts[record.status] = counts.get(record.status, 0) + 1
        return counts

    def run_inventory(
        self,
        *,
        statuses: set[str] | None = None,
        workflow_name: str | None = None,
        execution_kind: str | None = None,
        updated_after_ms: float | None = None,
        updated_before_ms: float | None = None,
        has_retry: bool | None = None,
        has_wait: bool | None = None,
        replay_count_min: int | None = None,
        limit: int | None = None,
        offset: int = 0,
        cursor: str | None = None,
    ) -> dict[str, object]:
        filtered = _apply_run_filters(
            self.list_runs(),
            statuses=statuses,
            workflow_name=workflow_name,
            execution_kind=execution_kind,
            updated_after_ms=updated_after_ms,
            updated_before_ms=updated_before_ms,
            has_retry=has_retry,
            has_wait=has_wait,
            replay_count_min=replay_count_min,
        )
        page, pagination = _paginate_run_records(filtered, limit=limit, offset=offset, cursor=cursor)
        normalized = _normalize_statuses(statuses)
        return {
            "runs": [record.to_dict() for record in page],
            "counts": self.run_status_counts(filtered),
            "filter": {
                "status": sorted(normalized) if normalized else [],
                "workflow": workflow_name,
                "execution_kind": execution_kind,
                "updated_after_ms": updated_after_ms,
                "updated_before_ms": updated_before_ms,
                "has_retry": has_retry,
                "has_wait": has_wait,
                "replay_count_min": replay_count_min,
                "limit": pagination["limit"],
                "offset": pagination["offset"],
                "cursor": cursor,
            },
            "pagination": pagination,
        }

    def list_rehydratable_runs(self) -> list[WorkflowRunRecord]:
        return self.store.list_rehydratable_runs()

    def list_dead_lettered_runs(self) -> list[WorkflowRunRecord]:
        return [
            record
            for record in self.store.list_terminal_runs()
            if record.status == RUN_STATUS_DEAD_LETTERED
        ]

    def expire_wait_timeouts(self, *, now_ms: float | None = None) -> list[WorkflowRunRecord]:
        return self.store.expire_wait_timeouts(now_ms=now_ms)

    def list_due_retry_runs(self, *, now_ms: float | None = None) -> list[WorkflowRunRecord]:
        return self.store.list_due_retry_runs(now_ms=now_ms)

    def sweep(self, vm_factory, *, now_ms: float | None = None) -> dict[str, object]:
        expired = self.expire_wait_timeouts(now_ms=now_ms)
        expired_ids = {record.run_id for record in expired}
        resumed_retries: list[dict[str, object]] = []
        due_retries = self.list_due_retry_runs(now_ms=now_ms)
        for record in due_retries:
            if record.run_id in expired_ids:
                continue
            vm = vm_factory(record)
            rebuild_graph = getattr(vm, "_rebuild_workflow_graph", None)
            if vm is None or not callable(rebuild_graph):
                continue
            result = self.resume_workflow(
                vm,
                record.run_id,
                now_ms=now_ms,
                rebuild_graph=rebuild_graph,
            )
            resumed_retries.append(
                {
                    "run_id": record.run_id,
                    "workflow_name": record.workflow_name,
                    "ok": not (isinstance(result, dict) and result.get("ok") is False),
                    "result": result,
                }
            )

        skip_ids = expired_ids | {item["run_id"] for item in resumed_retries}
        rehydrated: list[dict[str, object]] = []
        for record in self.list_rehydratable_runs():
            if record.run_id in skip_ids:
                continue
            vm = vm_factory(record)
            rebuild_graph = getattr(vm, "_rebuild_workflow_graph", None)
            if vm is None or not callable(rebuild_graph):
                continue
            info = self.rehydrate_run(vm, record.run_id, rebuild_graph=rebuild_graph)
            if info is not None:
                rehydrated.append(info)

        return {
            "expired_waits": [record.run_id for record in expired],
            "resumed_retries": resumed_retries,
            "rehydrated_runs": rehydrated,
        }

    def rehydrate_run(self, vm, run_id: str, *, rebuild_graph):
        expired = self.store.expire_wait_timeout(run_id)
        if expired is not None and expired.status == RUN_STATUS_DEAD_LETTERED:
            return None
        record = self.store.get_run(run_id)
        if record is None or record.status not in _REHYDRATABLE_STATUSES:
            return None
        state = load_graph_state(run_id)
        if not isinstance(state, dict):
            return None
        graph = get_registered_graph(run_id)
        registered_vm = get_registered_vm(run_id)
        if graph is None or (registered_vm is not None and registered_vm is not vm):
            graph = rebuild_graph(run_id, state)
        if graph is None:
            record.last_error = f"Failed to rehydrate workflow run '{run_id}'"
            self.store.save_run(record)
            return None
        graph = register_graph(graph)
        register_graph_vm(run_id, vm)
        if isinstance(graph.metadata, dict):
            graph.metadata["framework_rehydrated_at"] = runtime_time_ms()
            graph.metadata["framework_rehydrated_status"] = record.status
        record.metadata["rehydrated_at"] = runtime_time_ms()
        record.metadata["rehydrated_status"] = record.status
        self.store.save_run(record)
        return {
            "run_id": record.run_id,
            "graph_id": record.graph_id,
            "status": record.status,
            "workflow_name": record.workflow_name,
            "execution_kind": record.execution_kind,
            "wait": record.wait.to_dict() if record.wait is not None else None,
        }

    def rehydrate_runs(self, vm_factory) -> list[dict[str, object]]:
        rehydrated: list[dict[str, object]] = []
        for record in self.list_rehydratable_runs():
            vm = vm_factory(record)
            rebuild_graph = getattr(vm, "_rebuild_workflow_graph", None)
            if vm is None or not callable(rebuild_graph):
                continue
            info = self.rehydrate_run(vm, record.run_id, rebuild_graph=rebuild_graph)
            if info is not None:
                rehydrated.append(info)
        rehydrated.sort(key=lambda item: (str(item.get("status")), str(item.get("run_id"))))
        return rehydrated

    def mark_waiting(
        self,
        run_id: str,
        *,
        event_type: str,
        correlation_key: str | None = None,
        payload: dict[str, object] | None = None,
        deadline_ms: float | None = None,
    ) -> WorkflowRunRecord | None:
        return self.store.register_wait(
            run_id,
            event_type=event_type,
            correlation_key=correlation_key,
            payload=payload,
            deadline_ms=deadline_ms,
        )

    def revive_dead_lettered_run(self, run_id: str) -> WorkflowRunRecord | None:
        record = self.store.get_run(run_id)
        if record is None:
            return None
        if record.status != RUN_STATUS_DEAD_LETTERED:
            return record
        revived_at = runtime_time_ms()
        next_status = RUN_STATUS_WAITING if record.wait is not None else RUN_STATUS_FAILED
        replay_history = record.metadata.get("replay_history")
        if not isinstance(replay_history, list):
            replay_history = []
        replay_history.append(
            {
                "replayed_at": revived_at,
                "from_status": RUN_STATUS_DEAD_LETTERED,
                "to_status": next_status,
                "reason": record.last_error,
            }
        )
        record.metadata["replay_history"] = replay_history
        record.metadata["replay_count"] = int(record.metadata.get("replay_count", 0) or 0) + 1
        record.metadata["last_replayed_at"] = revived_at
        record.metadata.pop("wait_timeout", None)
        record.status = next_status
        record.claim = None
        record.last_error = None
        if record.wait is not None:
            record.wait.registered_at = revived_at
        return self.store.save_run(record)

    def start_graph(self, vm, graph: TaskGraph):
        graph = register_graph(graph)
        register_graph_vm(graph.graph_id, vm)
        metadata = _metadata_from_graph(graph, vm)
        workflow_name = metadata.get("workflow_name")
        if not isinstance(workflow_name, str):
            workflow_name = None
        execution_kind = metadata.get("execution_kind")
        if not isinstance(execution_kind, str):
            execution_kind = None
        self.store.create_run(
            run_id=graph.graph_id,
            graph_id=graph.graph_id,
            workflow_name=workflow_name,
            execution_kind=execution_kind,
            metadata=metadata,
        )
        owner = f"vm:{id(vm)}"
        claim = self.store.claim_run(graph.graph_id, owner=owner)
        if claim is None:
            return vm.make_err(
                "workflow_error",
                f"Workflow run '{graph.graph_id}' is already claimed",
                payload={"category": "workflow_claim_conflict", "graph_id": graph.graph_id},
            )
        record = self.store.get_run(graph.graph_id)
        if record is not None:
            record.status = RUN_STATUS_RUNNING
            record.claim = claim
            record.metadata.update(metadata)
            self.store.save_run(record)
        try:
            result = run_task_graph(vm, graph)
            status, last_error = _result_status(result)
            record = self.store.get_run(graph.graph_id)
            if record is not None:
                record.status = status
                record.last_error = last_error
                record.current_checkpoint = _current_checkpoint_label(result)
                if status == RUN_STATUS_COMPLETED:
                    record.metadata.pop("retry", None)
                elif status == RUN_STATUS_FAILED:
                    _mark_terminal_retry_from_result(record, result)
                self.store.save_run(record)
            if status == RUN_STATUS_WAITING:
                _mark_wait_from_result(self, graph.graph_id, result)
            if status == RUN_STATUS_RETRY_SCHEDULED:
                _mark_retry_from_result(self, graph.graph_id, result)
            return result
        finally:
            self.store.release_claim(graph.graph_id, claim.token)

    def resume_workflow(
        self,
        vm,
        graph_id: str,
        checkpoint=None,
        *,
        resume_payload: dict[str, object] | None = None,
        event_type: str | None = None,
        correlation_key: str | None = None,
        now_ms: float | None = None,
        rebuild_graph,
    ):
        owner = f"vm:{id(vm)}"
        expired = self.store.expire_wait_timeout(graph_id)
        if expired is not None and expired.status == RUN_STATUS_DEAD_LETTERED:
            return {"ok": False, "error": expired.last_error or f"Wait timeout expired for '{graph_id}'"}
        record = self.store.get_run(graph_id)
        if record is not None and record.status == RUN_STATUS_DEAD_LETTERED:
            return {"ok": False, "error": record.last_error or f"Workflow run '{graph_id}' is dead-lettered"}
        if record is not None and record.status == RUN_STATUS_RETRY_SCHEDULED and not self.store.retry_due(graph_id, now_ms=now_ms):
            retry = record.metadata.get("retry")
            next_attempt_at = retry.get("next_attempt_at") if isinstance(retry, dict) else None
            return {"ok": False, "error": f"Retry not due for '{graph_id}'", "next_attempt_at": next_attempt_at}
        if record is not None and record.status == RUN_STATUS_WAITING:
            if event_type is not None and (record.wait is None or record.wait.event_type != event_type):
                return {"ok": False, "error": f"Wait event type mismatch for '{graph_id}'"}
            if correlation_key is not None and (record.wait is None or record.wait.correlation_key != correlation_key):
                return {"ok": False, "error": f"Wait correlation mismatch for '{graph_id}'"}
            claim = self.store.claim_waiting_run_for_resume(
                graph_id,
                owner=owner,
                event_type=event_type,
                correlation_key=correlation_key,
            )
        else:
            claim = self.store.claim_run(
                graph_id,
                owner=owner,
                expected_statuses=(
                    RUN_STATUS_RUNNING,
                    RUN_STATUS_COMPLETED,
                    RUN_STATUS_FAILED,
                    RUN_STATUS_WAITING,
                    RUN_STATUS_RETRY_SCHEDULED,
                    "pending",
                ),
            )
        if claim is None:
            return {"ok": False, "error": f"Workflow run '{graph_id}' is already claimed"}
        try:
            state = load_graph_state(graph_id)
            if state is None:
                return {"ok": False, "error": "Graph state not found"}
            graph = get_registered_graph(graph_id)
            registered_vm = get_registered_vm(graph_id)
            if graph is None or (registered_vm is not None and registered_vm is not vm):
                graph = rebuild_graph(graph_id, state)
            if graph is None:
                return {"ok": False, "error": "Unknown graph"}
            metadata = state.get("metadata")
            if not isinstance(metadata, dict):
                metadata = {}
                state["metadata"] = metadata
            if resume_payload is not None:
                metadata["resume_payload"] = dict(resume_payload)
                if isinstance(graph.metadata, dict):
                    graph.metadata["resume_payload"] = dict(resume_payload)
            else:
                metadata.pop("resume_payload", None)
                if isinstance(graph.metadata, dict):
                    graph.metadata.pop("resume_payload", None)
            if checkpoint is not None:
                if not isinstance(checkpoint, str):
                    return {"ok": False, "error": "Checkpoint must be a string"}
                checkpoints = state.get("engine_checkpoints")
                if not isinstance(checkpoints, list) and isinstance(state.get("metadata"), dict):
                    checkpoints = state["metadata"].get("engine_checkpoints")
                if not isinstance(checkpoints, list):
                    checkpoints = state.get("checkpoints")
                if not isinstance(checkpoints, list) and isinstance(state.get("metadata"), dict):
                    checkpoints = state["metadata"].get("checkpoints")
                entry = None
                if isinstance(checkpoints, list):
                    for item in reversed(checkpoints):
                        if isinstance(item, dict) and item.get("label") == checkpoint:
                            entry = item
                            break
                if entry is None:
                    return {"ok": False, "error": f"Checkpoint not found: {checkpoint}"}
                if "state" in entry:
                    state["workflow_state"] = entry.get("state")
                vm._rollback_to_checkpoint(graph, state, entry)
                vm.event_bus.emit_event("graph_resume", data={"graph_id": graph_id, "checkpoint": checkpoint})
            else:
                vm.event_bus.emit_event("graph_resume", data={"graph_id": graph_id})
            record = self.store.get_run(graph_id)
            if record is not None:
                record.status = RUN_STATUS_RUNNING
                record.wait = None
                record.resume_count += 1
                record.metadata.pop("retry", None)
                if resume_payload is not None:
                    record.metadata["resume_payload"] = dict(resume_payload)
                if checkpoint is not None:
                    record.current_checkpoint = checkpoint
                self.store.save_run(record)
            result = run_task_graph(vm, graph, resume_state=state)
            status, last_error = _result_status(result)
            record = self.store.get_run(graph_id)
            if record is not None:
                record.status = status
                record.last_error = last_error
                record.current_checkpoint = _current_checkpoint_label(result) or record.current_checkpoint
                if status == RUN_STATUS_COMPLETED:
                    record.metadata.pop("retry", None)
                elif status == RUN_STATUS_FAILED:
                    _mark_terminal_retry_from_result(record, result)
                self.store.save_run(record)
            if status == RUN_STATUS_WAITING:
                _mark_wait_from_result(self, graph_id, result)
            if status == RUN_STATUS_RETRY_SCHEDULED:
                _mark_retry_from_result(self, graph_id, result)
            return result
        finally:
            self.store.release_claim(graph_id, claim.token)

    def replay_workflow(
        self,
        vm,
        graph_id: str,
        checkpoint=None,
        *,
        resume_payload: dict[str, object] | None = None,
        event_type: str | None = None,
        correlation_key: str | None = None,
        rearm_only: bool = False,
        now_ms: float | None = None,
        rebuild_graph,
    ):
        record = self.store.get_run(graph_id)
        if record is None:
            return {"ok": False, "error": f"Workflow run '{graph_id}' not found"}
        if record.status == RUN_STATUS_DEAD_LETTERED:
            record = self.revive_dead_lettered_run(graph_id)
            if record is None:
                return {"ok": False, "error": f"Workflow run '{graph_id}' not found"}
        if rearm_only:
            if record.status != RUN_STATUS_WAITING:
                return {"ok": False, "error": f"Workflow run '{graph_id}' is not waiting and cannot be rearmed only"}
            return {
                "ok": True,
                "status": "waiting",
                "rearmed": True,
                "run": record.to_dict(),
            }
        return self.resume_workflow(
            vm,
            graph_id,
            checkpoint,
            resume_payload=resume_payload,
            event_type=event_type,
            correlation_key=correlation_key,
            now_ms=now_ms,
            rebuild_graph=rebuild_graph,
        )

    def store_info(self) -> dict[str, object]:
        return self.store.store_info()


def get_default_workflow_runner() -> WorkflowFrameworkRunner:
    global _DEFAULT_RUNNER, _DEFAULT_RUNNER_ROOT
    with _DEFAULT_RUNNER_LOCK:
        root = os.path.abspath(os.getcwd())
        if _DEFAULT_RUNNER is None or _DEFAULT_RUNNER_ROOT != root:
            _DEFAULT_RUNNER = WorkflowFrameworkRunner(
                LocalWorkflowStore(root=os.path.join(".nodus", "workflow_framework"))
            )
            _DEFAULT_RUNNER_ROOT = root
        return _DEFAULT_RUNNER


def configure_default_workflow_runner(
    *,
    backend: str | None = None,
    root: str | None = None,
    path: str | None = None,
    runner: WorkflowFrameworkRunner | None = None,
) -> WorkflowFrameworkRunner:
    global _DEFAULT_RUNNER, _DEFAULT_RUNNER_ROOT
    with _DEFAULT_RUNNER_LOCK:
        resolved_runner = runner
        if resolved_runner is None:
            resolved_runner = WorkflowFrameworkRunner(
                create_workflow_store(
                    backend=backend,
                    root=root,
                    path=path,
                )
            )
        _DEFAULT_RUNNER = resolved_runner
        _DEFAULT_RUNNER_ROOT = os.path.abspath(os.getcwd())
        return resolved_runner
