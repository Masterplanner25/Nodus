"""Framework runner layered over Nodus task-graph execution."""

from __future__ import annotations

import os
import threading
from contextlib import contextmanager

from nodus.orchestration.task_graph import (
    TaskGraph,
    WorkflowRebuildError,
    get_registered_graph,
    get_registered_vm,
    load_graph_state,
    register_graph,
    register_graph_vm,
    run_task_graph,
)
from nodus.runtime.runtime_stats import runtime_time_ms
from nodus.runtime.state_paths import workflow_store_root

from .models import (
    REHYDRATABLE_RUN_STATUSES,
    RUN_STATUSES,
    RUN_STATUS_CANCELLED,
    RUN_STATUS_COMPLETED,
    RUN_STATUS_DEAD_LETTERED,
    RUN_STATUS_FAILED,
    RUN_STATUS_RETRY_SCHEDULED,
    RUN_STATUS_RUNNING,
    RUN_STATUS_WAITING,
    TERMINAL_RUN_STATUSES,
    WorkflowRunRecord,
)
from .store import (
    LocalWorkflowStore,
    WorkflowStore,
    create_workflow_store,
    workflow_store_backend_from_env,
    workflow_store_path_from_env,
)


_DEFAULT_RUNNER = None
_DEFAULT_RUNNER_ROOT = None
_DEFAULT_RUNNER_LOCK = threading.Lock()
_DEFAULT_SWEEP_THREAD: threading.Thread | None = None
_DEFAULT_SWEEP_STOP: threading.Event | None = None
_DEFAULT_SWEEP_INTERVAL_S = 30.0


def _auto_sweep_loop(runner_ref: "WorkflowFrameworkRunner", stop_event: threading.Event) -> None:
    # The stop event is per-thread (not the module global): a sweep thread is
    # always bound to the runner it was started for, so replacing the default
    # runner can stop exactly its own thread without racing a successor.
    while not stop_event.wait(timeout=_DEFAULT_SWEEP_INTERVAL_S):
        try:
            runner_ref.expire_wait_timeouts()
        except Exception:
            pass


def _autosweep_enabled() -> bool:
    # Default on (unchanged behavior); embedders/tests can disable the background
    # sweep entirely via env to avoid a timer thread touching the store.
    return os.environ.get("NODUS_WORKFLOW_AUTOSWEEP", "1").strip().lower() not in {"0", "false", "no", ""}


def _stop_default_sweep_locked() -> None:
    """Stop the active auto-sweep thread. Caller must hold ``_DEFAULT_RUNNER_LOCK``.

    Load-bearing for correctness: without this, replacing the default runner (on a
    cwd change or explicit configure) leaves the previous sweep thread alive and
    bound to the *old* store instance. That stale thread then writes the same run
    files as the new store instance — two objects, two locks, no mutual exclusion —
    corrupting run records (torn resume state on POSIX; ``os.replace`` PermissionError
    on Windows). Stopping it here guarantees at most one sweep thread, bound to the
    live store, whose own lock serializes it against the foreground.
    """
    global _DEFAULT_SWEEP_THREAD, _DEFAULT_SWEEP_STOP
    if _DEFAULT_SWEEP_STOP is not None:
        _DEFAULT_SWEEP_STOP.set()
    thread = _DEFAULT_SWEEP_THREAD
    if thread is not None and thread.is_alive() and thread is not threading.current_thread():
        thread.join(timeout=2.0)
    _DEFAULT_SWEEP_THREAD = None
    _DEFAULT_SWEEP_STOP = None


def _start_default_sweep_locked(runner: "WorkflowFrameworkRunner") -> None:
    """Start a fresh auto-sweep thread bound to *runner*. Caller holds the lock."""
    global _DEFAULT_SWEEP_THREAD, _DEFAULT_SWEEP_STOP
    if not _autosweep_enabled():
        return
    stop_event = threading.Event()
    thread = threading.Thread(
        target=_auto_sweep_loop,
        args=(runner, stop_event),
        daemon=True,
        name="nodus-workflow-sweep",
    )
    _DEFAULT_SWEEP_STOP = stop_event
    _DEFAULT_SWEEP_THREAD = thread
    thread.start()


def register_retry_sweeper(runner: "WorkflowFrameworkRunner | None" = None) -> "WorkflowFrameworkRunner":
    """Declare that something will resume ``retry_scheduled`` runs in *runner*'s store.

    A step retry can be handled two ways: taken in-process, or persisted as
    ``retry_scheduled`` for a sweeper to pick up later. The second is only
    correct if a sweeper actually exists — otherwise the deferral is dropped and
    the run reports success having made one attempt (#392).

    Nothing but the presence of a sweeper should decide that, which is why the
    registration lives here rather than as a parameter each caller passes. Only
    ``RuntimeService`` drives ``sweep()``, so only it registers; every other
    entry point (CLI, embedding, in-language ``run_workflow``/``run_goal``)
    retries in-process and completes before returning.

    Registered **on a runner**, not on the process: a service sweeping one store
    says nothing about runs in another. That distinction is load-bearing — the
    default runner is rebuilt per working directory, so a service started in one
    project must not change retry behaviour for a run in a different one.

    Reentrant by count, so nested or multiple services compose. Returns the
    runner it registered on, which is what ``unregister_retry_sweeper`` wants.
    """
    resolved = runner if runner is not None else get_default_workflow_runner()
    resolved.register_sweeper()
    return resolved


def unregister_retry_sweeper(runner: "WorkflowFrameworkRunner | None" = None) -> None:
    """Withdraw one ``register_retry_sweeper()`` registration."""
    resolved = runner if runner is not None else get_default_workflow_runner()
    resolved.unregister_sweeper()


def retry_sweeper_active() -> bool:
    """True when a sweeper is registered for the store the *current* runs use.

    Peeks at the cached default runner rather than calling
    ``get_default_workflow_runner()``, which would build a store and start an
    auto-sweep thread as a side effect of a step failing. No cached runner means
    nothing has registered a run durably yet, so there is nothing to sweep.

    Every uncertain case answers False, and that is the safe direction: False
    means the retry is taken in-process and the run finishes, which is at worst
    slower than deferring. True on a wrong guess means the run ends and nobody
    resumes it — the #392 failure.
    """
    with _DEFAULT_RUNNER_LOCK:
        runner = _DEFAULT_RUNNER
        root = _DEFAULT_RUNNER_ROOT
    if runner is None:
        return False
    if root is not None and root != os.path.abspath(os.getcwd()):
        return False  # cached runner belongs to another project root
    return runner.has_sweeper()


@contextmanager
def retry_sweeper(runner: "WorkflowFrameworkRunner | None" = None):
    """Scope a retry-sweeper registration."""
    resolved = register_retry_sweeper(runner)
    try:
        yield resolved
    finally:
        unregister_retry_sweeper(resolved)


def reset_default_workflow_runner() -> None:
    """Stop the auto-sweep thread and drop the cached default runner.

    For test isolation and clean shutdown: the next ``get_default_workflow_runner()``
    rebuilds against the current working directory with a fresh store + thread.
    """
    global _DEFAULT_RUNNER, _DEFAULT_RUNNER_ROOT
    with _DEFAULT_RUNNER_LOCK:
        _stop_default_sweep_locked()
        _DEFAULT_RUNNER = None
        _DEFAULT_RUNNER_ROOT = None
# Both sourced from `models`, which owns the vocabulary (#395 §7.3). The
# rehydratable set used to be defined here *and* in `store.py`, equal by
# coincidence; `_KNOWN_RUN_STATUSES` listed the members a third time.
_REHYDRATABLE_STATUSES = REHYDRATABLE_RUN_STATUSES
_KNOWN_RUN_STATUSES = frozenset(RUN_STATUSES)


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
    _et = wait.get("event_type")
    _ck = wait.get("correlation_key")
    _pl = wait.get("payload")
    _dl = wait.get("deadline_ms")
    _sc = wait.get("schema")
    runner.mark_waiting(
        graph_id,
        event_type=_et if isinstance(_et, str) else "workflow.wait",
        correlation_key=_ck if isinstance(_ck, str) else None,
        payload=_pl if isinstance(_pl, dict) else {},
        deadline_ms=_dl if isinstance(_dl, (int, float)) else None,
        schema=_sc if isinstance(_sc, dict) else None,
    )


def _wait_payload_schema_error(record, resume_payload) -> str | None:
    """Does the resume payload match the shape the wait declared (#472)?

    Returns a message, or None when it matches or nothing was declared.

    **An undeclared schema accepts anything.** That is the compatible reading and
    the one the issue prefers: every wait written before this existed declares
    nothing, and warning on them would make the feature a nuisance rather than a
    contract.

    Uses the runtime schema dialect shared with `std:tool` and
    `register_function`, so a payload failure is worded the way those are.
    """
    # Narrowed with an explicit `is None` rather than folded into a conditional
    # expression: mypy cannot narrow through `getattr`, and `wait.event_type`
    # below is used after the branch. That is the trap CLAUDE.md records — a
    # condition extracted into a helper drops the narrowing, ruff stays clean,
    # and CI fails on the type check.
    wait = getattr(record, "wait", None)
    if wait is None:
        return None
    schema = getattr(wait, "schema", None)
    if not schema:
        return None
    from nodus.runtime.schema_contract import validate_args

    error = validate_args(resume_payload or {}, schema)
    if error is None:
        return None
    declared = ", ".join(sorted(schema.get("properties", {})))
    return (
        f"Wait payload does not match the declared schema: {error}. "
        f"'{wait.event_type}' declares {{{declared}}}."
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
    _tid = retry.get("task_id")
    _step = retry.get("step")
    _att = retry.get("attempt")
    _mr = retry.get("max_retries")
    _dl = retry.get("delay_ms")
    _na = retry.get("next_attempt_at")
    _cls = retry.get("classification")
    _le = retry.get("last_error")
    runner.store.schedule_retry(
        graph_id,
        task_id=_tid if isinstance(_tid, str) else None,
        step_name=_step if isinstance(_step, str) else None,
        attempt=float(_att) if isinstance(_att, (int, float)) else None,
        max_retries=float(_mr) if isinstance(_mr, (int, float)) else None,
        delay_ms=float(_dl) if isinstance(_dl, (int, float)) else None,
        next_attempt_at=float(_na) if isinstance(_na, (int, float)) else None,
        classification=_cls if isinstance(_cls, str) else None,
        last_error=_le if isinstance(_le, str) else None,
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
        self._sweeper_lock = threading.Lock()
        self._sweeper_count = 0

    def register_sweeper(self) -> None:
        """Count one participant that will call ``sweep()`` on this runner."""
        with self._sweeper_lock:
            self._sweeper_count += 1

    def unregister_sweeper(self) -> None:
        with self._sweeper_lock:
            if self._sweeper_count > 0:
                self._sweeper_count -= 1

    def has_sweeper(self) -> bool:
        """True while something is sweeping this runner's store (#392, #393)."""
        with self._sweeper_lock:
            return self._sweeper_count > 0

    def get_run(self, run_id: str) -> WorkflowRunRecord | None:
        return self.store.get_run(run_id)

    def cancel_run(self, run_id: str) -> dict[str, object]:
        """Stop a run. Returns what happened, rather than raising (#395 §7).

        Marks the record `cancelled` — terminal, and deliberately not
        rehydratable, so a cancelled run cannot resurrect on the next sweep.

        **In-process this is immediate; across processes it is cooperative.** A
        run in flight lives in some process's scheduler, and a CLI acting against
        a shared store can only mark the record — the owning runner observes it
        at the next step boundary, where it already decides whether to dispatch.
        So a cancel is *eventually* effective, bounded by the duration of the
        step that is currently running. That is a real limit and is documented as
        one: a cancel that silently does nothing until a 40-minute agent call
        returns is worse than a cancel that says so.

        Cancelling an already-terminal run is a **no-op reporting what it found**,
        not an error — matching `cancel(task)`. The caller of a cancel usually
        cannot know the target's state, and raising would push every call site
        into a check-then-act race.
        """
        record = self.store.get_run(run_id)
        if record is None:
            return {"ok": False, "run_id": run_id, "reason": "not found"}
        if record.status in TERMINAL_RUN_STATUSES:
            return {
                "ok": False,
                "run_id": run_id,
                "reason": "already finished",
                "status": record.status,
            }

        previous = record.status
        record.status = RUN_STATUS_CANCELLED
        record.claim = None
        record.metadata["cancelled_from"] = previous
        record.metadata["cancelled_at"] = runtime_time_ms()
        self.store.save_run(record)
        return {
            "ok": True,
            "run_id": run_id,
            "status": RUN_STATUS_CANCELLED,
            "cancelled_from": previous,
        }

    def run_is_cancelled(self, run_id: str) -> bool:
        """Has this run been cancelled out from under us?

        The step-boundary question. Read by the dispatch loop so a cancellation
        marked by another process takes effect without that process being able to
        reach into this one's scheduler.
        """
        record = self.store.get_run(run_id)
        return record is not None and record.status == RUN_STATUS_CANCELLED

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

    def sweep(
        self,
        vm_factory,
        *,
        now_ms: float | None = None,
        min_idle_ms: float = 0.0,
    ) -> dict[str, object]:
        """Expire waits, resume due retries, and adopt orphaned runs.

        ``min_idle_ms`` gates the adoption half: a run updated more recently than
        that is left alone. Rehydration exists for runs whose owner is gone — a
        process that crashed with work in flight — and a run touched moments ago
        is not that (#376). Defaults to 0 so explicit callers keep adopting
        immediately; a *background* sweeper should pass a value, because it
        cannot tell the difference between an orphan and a run someone is in the
        middle of, and guessing wrong corrupts the live one.
        """
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
        idle_before = (now_ms if now_ms is not None else runtime_time_ms()) - min_idle_ms
        for record in self.list_rehydratable_runs():
            if record.run_id in skip_ids:
                continue
            if min_idle_ms > 0 and (record.updated_at or 0) > idle_before:
                continue  # recently touched: someone is probably still on it
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
        # #376: claim before adopting. Rehydration is not read-only — it calls
        # register_graph()/register_graph_vm(), which replace the process-global
        # registry entry for this run and bind it to `vm`. Doing that to a run
        # another participant is working on hands them a graph pointed at
        # someone else's VM, and the resume that follows returns ok:true with
        # empty steps. `resume_workflow` has always claimed; this path did not.
        owner = f"rehydrate:{id(vm)}"
        claim = self.store.claim_run(run_id, owner=owner)
        if claim is None:
            return None  # actively owned by someone else — not ours to adopt
        try:
            return self._rehydrate_run_claimed(vm, run_id, rebuild_graph=rebuild_graph)
        finally:
            self.store.release_claim(run_id, claim.token)

    def _rehydrate_run_claimed(self, vm, run_id: str, *, rebuild_graph):
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
            try:
                graph = rebuild_graph(run_id, state)
            except WorkflowRebuildError as err:
                # #399: record why. A sweeper adopting an orphan is the one caller
                # with nobody watching, so a bare "Failed to rehydrate" here is a
                # dead end — this is the only place the reason survives.
                record.last_error = f"Failed to rehydrate workflow run '{run_id}': {err.describe()}"
                self.store.save_run(record)
                return None
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
        schema: dict[str, object] | None = None,
    ) -> WorkflowRunRecord | None:
        return self.store.register_wait(
            run_id,
            event_type=event_type,
            correlation_key=correlation_key,
            payload=payload,
            deadline_ms=deadline_ms,
            schema=schema,
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
        _rc = record.metadata.get("replay_count")
        record.metadata["replay_count"] = (int(_rc) if isinstance(_rc, (int, str)) else 0) + 1
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
        _gid = graph.graph_id
        if not isinstance(_gid, str):
            return vm.make_err("workflow_error", "Workflow graph has no ID")
        graph_id: str = _gid
        register_graph_vm(graph_id, vm)
        metadata = _metadata_from_graph(graph, vm)
        workflow_name = metadata.get("workflow_name")
        if not isinstance(workflow_name, str):
            workflow_name = None
        execution_kind = metadata.get("execution_kind")
        if not isinstance(execution_kind, str):
            execution_kind = None
        self.store.create_run(
            run_id=graph_id,
            graph_id=graph_id,
            workflow_name=workflow_name,
            execution_kind=execution_kind,
            metadata=metadata,
        )
        owner = f"vm:{id(vm)}"
        claim = self.store.claim_run(graph_id, owner=owner)
        if claim is None:
            return vm.make_err(
                "workflow_error",
                f"Workflow run '{graph_id}' is already claimed",
                payload={"category": "workflow_claim_conflict", "graph_id": graph_id},
            )
        record = self.store.get_run(graph_id)
        if record is not None:
            record.status = RUN_STATUS_RUNNING
            record.claim = claim
            record.metadata.update(metadata)
            self.store.save_run(record)
        # #395 §7.1: how the graph asks whether it has been cancelled. Injected
        # rather than imported -- `task_graph` importing this module at scope
        # would reinstate CIRC-001 (#103), whose lazy-import fix CLAUDE.md says
        # not to undo. A bare `run_graph` never gets one and is unaffected.
        graph.cancel_check = lambda: self.run_is_cancelled(graph_id)
        try:
            result = run_task_graph(vm, graph)
            status, last_error = _result_status(result)
            record = self.store.get_run(graph_id)
            if record is not None:
                # A cancelled run keeps its status. The graph stops mid-flight, so
                # `_result_status` reads it as failed or completed depending on
                # what had settled -- and writing that back would un-cancel the
                # run in the record, losing the one fact an operator asked for.
                if record.status == RUN_STATUS_CANCELLED:
                    record.claim = None
                    self.store.save_run(record)
                    return result
                record.status = status
                record.last_error = last_error
                record.current_checkpoint = _current_checkpoint_label(result)
                if status == RUN_STATUS_COMPLETED:
                    record.metadata.pop("retry", None)
                elif status == RUN_STATUS_FAILED:
                    _mark_terminal_retry_from_result(record, result)
                    # #577/D7.6: a compensated run is terminal. Recorded in
                    # metadata rather than as an eighth run status -- the
                    # lifecycle vocabulary is deliberately closed, and this is a
                    # property of a failed run rather than a state beside it.
                    # Both recording sites are covered: a *resumed* run that
                    # transitions to failed compensates too, so marking only the
                    # first would leave that one resumable.
                    if isinstance(result, dict) and result.get("compensation"):
                        record.metadata["compensated"] = True
                self.store.save_run(record)
            if status == RUN_STATUS_WAITING:
                _mark_wait_from_result(self, graph_id, result)
            if status == RUN_STATUS_RETRY_SCHEDULED:
                _mark_retry_from_result(self, graph_id, result)
            return result
        finally:
            self.store.release_claim(graph_id, claim.token)

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
        if record is None:
            # #425: say the run does not exist, rather than blaming a claim.
            #
            # Every check below is guarded on `record is not None`, so an unknown
            # graph_id used to fall through all of them to `claim_run`, which
            # returns None both for "someone else holds the claim" and for "there
            # is nothing to claim". Reporting the first for the second sent readers
            # looking for a concurrent run that was never there — and a typo'd id
            # is far likelier than a claim conflict.
            #
            # #476: and when the run's *graph state* is sitting right there,
            # "not found" is the same class of misleading answer. A run is split
            # across two stores; if the record was removed while the state
            # survived (rm -rf on the store's runs directory, an asymmetric
            # cleanup), name that instead of sending the reader to check the id.
            if load_graph_state(graph_id) is not None:
                return {
                    "ok": False,
                    "error": (
                        f"Workflow run '{graph_id}' has graph state under "
                        f".nodus/graphs but no run record in the workflow "
                        f"store — the two halves of the run were cleaned "
                        f"independently, and the state alone cannot be "
                        f"resumed. Remove the orphaned state with "
                        f"`nodus workflow cleanup --force`."
                    ),
                    "graph_id": graph_id,
                    "category": "run_record_missing",
                }
            return {"ok": False, "error": f"Workflow run '{graph_id}' not found"}
        if record is not None and record.status == RUN_STATUS_DEAD_LETTERED:
            return {"ok": False, "error": record.last_error or f"Workflow run '{graph_id}' is dead-lettered"}
        if record is not None and record.status == RUN_STATUS_RETRY_SCHEDULED and not self.store.retry_due(graph_id, now_ms=now_ms):
            retry = record.metadata.get("retry")
            next_attempt_at = retry.get("next_attempt_at") if isinstance(retry, dict) else None
            return {"ok": False, "error": f"Retry not due for '{graph_id}'", "next_attempt_at": next_attempt_at}
        # #577/D7.6: a compensated run cannot be resumed. Its completed work has
        # been undone, so re-entering would re-execute steps against a remote
        # that has already been refunded -- and a resume *does* re-execute
        # (#494 / I-WFLOW-06). Refused with the reason, the shape #482 used for a
        # checkpoint resume of a waiting run.
        if record is not None and record.metadata.get("compensated"):
            return {
                "ok": False,
                "error": (
                    f"Workflow run '{graph_id}' was compensated: its completed "
                    f"work has been undone, so it cannot be resumed. Start a new "
                    f"run."
                ),
            }
        if record is not None and record.status == RUN_STATUS_WAITING:
            if event_type is not None and (record.wait is None or record.wait.event_type != event_type):
                return {"ok": False, "error": f"Wait event type mismatch for '{graph_id}'"}
            if correlation_key is not None and (record.wait is None or record.wait.correlation_key != correlation_key):
                return {"ok": False, "error": f"Wait correlation mismatch for '{graph_id}'"}
            # #472: the declared payload shape, checked here — before the run is
            # claimed and before the step re-runs — so the failure lands on the
            # caller that sent the wrong thing rather than inside the step that
            # trusted it. Same refusal shape as the two mismatches above.
            schema_error = _wait_payload_schema_error(record, resume_payload)
            if schema_error is not None:
                return {"ok": False, "error": schema_error}
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
            # A same-process resume can skip the rebuild entirely (registry hit),
            # so clear the drift flag here or a previous resume's answer leaks
            # into this result.
            vm._last_resume_source_drift = False
            state = load_graph_state(graph_id)
            if state is None:
                return {"ok": False, "error": "Graph state not found"}
            # #482: `resume_workflow(id, "checkpoint")` on a genuinely waiting run
            # re-enters the waiting step, which hits its `workflow_wait` again --
            # the run goes straight back to `waiting` and the result looks
            # healthy, so a caller checking for an error sees success while
            # nothing happened. With a payload it is worse: the rollback re-arms
            # the wait and the payload is silently discarded (a wait is a
            # sentinel the engine pauses on; nothing consults the pending payload
            # when a re-run step re-arms it). The call that advances a waiting
            # run delivers a payload *without* a checkpoint. Refuse both no-op
            # combinations with the real reason, the way #399 and #425 replaced
            # misleading answers on this same path.
            #
            # "Genuinely" is the persisted graph state agreeing the run is
            # waiting. A record marked waiting administratively
            # (`mark_waiting`) over a graph that ran past the wait -- a stale
            # registration -- resumes fine and clears the mark, and must keep
            # doing so.
            if (
                checkpoint is not None
                and event_type is None
                and record is not None
                and record.status == RUN_STATUS_WAITING
                and isinstance(state, dict)
                and state.get("status") == "waiting"
            ):
                wait_event = record.wait.event_type if record.wait is not None else None
                if resume_payload is None:
                    detail = (
                        f"pass a payload to satisfy it -- "
                        f"resume_workflow(graph_id, {{...}}) -- and the run "
                        f"will advance. Resuming from checkpoint "
                        f"'{checkpoint}' alone re-enters the waiting step, "
                        f"which waits again."
                    )
                else:
                    detail = (
                        f"drop the checkpoint argument -- "
                        f"resume_workflow(graph_id, {{...}}) -- and the payload "
                        f"will satisfy it. Rolling back to checkpoint "
                        f"'{checkpoint}' re-enters the waiting step, which "
                        f"re-arms the wait and discards the payload."
                    )
                return {
                    "ok": False,
                    "error": (
                        f"Workflow run '{graph_id}' is waiting on event "
                        f"'{wait_event}'; {detail}"
                    ),
                    "graph_id": graph_id,
                    "category": "waiting_run_checkpoint_resume",
                }
            graph = get_registered_graph(graph_id)
            registered_vm = get_registered_vm(graph_id)
            if graph is None or (registered_vm is not None and registered_vm is not vm):
                try:
                    graph = rebuild_graph(graph_id, state)
                except WorkflowRebuildError as err:
                    # #399: report why, not "Unknown graph". The run exists — it is
                    # in the store and its state is on disk — so claiming otherwise
                    # sends the reader looking in the wrong place entirely.
                    return {
                        "ok": False,
                        "error": f"Could not rebuild run '{graph_id}': {err.describe()}",
                        "graph_id": graph_id,
                        "category": "workflow_rebuild_failed",
                    }
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
                # #486: prefer the rollback base over the observation snapshot.
                # `state` includes the checkpointing step's pending fold
                # contributions; re-entering that step from the top re-derives
                # them, so restoring `state` would count each one twice.
                # `resume_state` is the committed base without them. Older
                # persisted checkpoints have only `state`, and keep the old
                # behaviour.
                if "resume_state" in entry:
                    state["workflow_state"] = entry.get("resume_state")
                elif "state" in entry:
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
            # #497: drift is warned on stderr and emitted as an event, but a
            # program reacting to it needs it where the answer lands. Present
            # only when true -- an absent key means the pinned source still
            # matches the file (or there was no rebuild to compare).
            if isinstance(result, dict) and getattr(vm, "_last_resume_source_drift", False):
                result["source_drift"] = True
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
                    # #577/D7.6: a compensated run is terminal. Recorded in
                    # metadata rather than as an eighth run status -- the
                    # lifecycle vocabulary is deliberately closed, and this is a
                    # property of a failed run rather than a state beside it.
                    # Both recording sites are covered: a *resumed* run that
                    # transitions to failed compensates too, so marking only the
                    # first would leave that one resumable.
                    if isinstance(result, dict) and result.get("compensation"):
                        record.metadata["compensated"] = True
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


def default_store_root() -> str:
    """Root directory for the default local workflow store.

    ``NODUS_WORKFLOW_STORE_ROOT`` overrides the CWD-relative default. Without it,
    every process that runs a workflow writes into `.nodus/workflow_framework`
    under whatever its working directory happens to be — which is how the test
    suite came to accumulate hundreds of run files inside the repo and slow its
    own later runs (#380). Also useful when the working directory is read-only or
    ephemeral and run state needs to outlive it.
    """
    # #585: both halves of a run move together under `NODUS_RUN_STATE_ROOT`;
    # `NODUS_WORKFLOW_STORE_ROOT` still wins here, and still moves only this half.
    return workflow_store_root()


def get_default_workflow_runner() -> WorkflowFrameworkRunner:
    global _DEFAULT_RUNNER, _DEFAULT_RUNNER_ROOT, _DEFAULT_SWEEP_THREAD, _DEFAULT_SWEEP_STOP
    with _DEFAULT_RUNNER_LOCK:
        root = os.path.abspath(os.getcwd())
        if _DEFAULT_RUNNER is None or _DEFAULT_RUNNER_ROOT != root:
            # Stop the sweep thread bound to the previous runner BEFORE swapping in
            # a new store instance for this root — otherwise the stale thread races
            # the new store on the same files (see _stop_default_sweep_locked).
            _stop_default_sweep_locked()
            # #174: built through the same factory and the same environment
            # overrides `nodus serve` honours. This used to hardcode
            # `LocalWorkflowStore`, so an embedder calling `run_workflow()`
            # without configuring a runner got the non-crash-safe JSON store with
            # no way to say otherwise short of `configure_default_workflow_runner`
            # — while `NODUS_WORKFLOW_STORE_BACKEND` sat there working for the
            # server and doing nothing here.
            #
            # The default is still `local`. Flipping it is a 6.0.0 change, not
            # because the file location moves but because runs already recorded
            # in the JSON store are invisible to a SQLite one: an in-flight
            # waiting run would silently become unresumable, and there is no
            # backend migration today (`nodus workflow migrate-state` migrates
            # graph *snapshots*, not stores).
            _DEFAULT_RUNNER = WorkflowFrameworkRunner(
                create_workflow_store(
                    backend=workflow_store_backend_from_env(),
                    root=default_store_root(),
                    path=workflow_store_path_from_env(),
                )
            )
            _DEFAULT_RUNNER_ROOT = root
            # Auto-start a daemon thread that expires wait-timeouts periodically so
            # embedders who don't call sweep() still get deadline enforcement.
            # Full retry/rehydration still requires the host to provide a vm_factory
            # and call sweep() explicitly. Bound to this runner; replaced on rebuild.
            _start_default_sweep_locked(_DEFAULT_RUNNER)
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
        # Stop the sweep thread bound to the previous runner before swapping so it
        # cannot race the newly configured store on shared files.
        _stop_default_sweep_locked()
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
