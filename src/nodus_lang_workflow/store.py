"""Workflow framework stores."""

from __future__ import annotations

from abc import ABC, abstractmethod
import json
import os
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager

from nodus.runtime.runtime_stats import runtime_time_ms

from .models import (
    RUN_STATUS_COMPLETED,
    RUN_STATUS_DEAD_LETTERED,
    RUN_STATUS_FAILED,
    RUN_STATUS_PENDING,
    RUN_STATUS_RETRY_SCHEDULED,
    RUN_STATUS_RUNNING,
    RUN_STATUS_WAITING,
    WorkflowClaim,
    WorkflowRunRecord,
    WorkflowWaitRecord,
)


REHYDRATABLE_RUN_STATUSES = {
    RUN_STATUS_WAITING,
    RUN_STATUS_RETRY_SCHEDULED,
    RUN_STATUS_RUNNING,
}
TERMINAL_RUN_STATUSES = {
    RUN_STATUS_COMPLETED,
    RUN_STATUS_FAILED,
    RUN_STATUS_DEAD_LETTERED,
}


class WorkflowStore(ABC):
    @abstractmethod
    def get_run(self, run_id: str) -> WorkflowRunRecord | None:
        raise NotImplementedError

    @abstractmethod
    def save_run(self, record: WorkflowRunRecord) -> WorkflowRunRecord:
        raise NotImplementedError

    @abstractmethod
    def create_run(
        self,
        *,
        run_id: str,
        graph_id: str,
        workflow_name: str | None,
        execution_kind: str | None,
        metadata: dict[str, object] | None = None,
    ) -> WorkflowRunRecord:
        raise NotImplementedError

    def delete_run(self, run_id: str) -> bool:
        """Remove a run record. Returns whether one was removed.

        Concrete with a no-op default rather than abstract (#476): a store is a
        host-implementable surface, and adding an abstract method would break
        every existing implementation to gain a capability only cleanup uses.
        A store that does not override this reports `False` and cleanup leaves
        its records alone.
        """
        return False

    @abstractmethod
    def claim_run(
        self,
        run_id: str,
        *,
        owner: str,
        expected_statuses: tuple[str, ...] = (
            RUN_STATUS_PENDING,
            RUN_STATUS_RUNNING,
            RUN_STATUS_WAITING,
            RUN_STATUS_RETRY_SCHEDULED,
        ),
    ) -> WorkflowClaim | None:
        raise NotImplementedError

    @abstractmethod
    def release_claim(self, run_id: str, token: str | None) -> WorkflowRunRecord | None:
        raise NotImplementedError

    @abstractmethod
    def register_wait(
        self,
        run_id: str,
        *,
        event_type: str,
        correlation_key: str | None = None,
        payload: dict[str, object] | None = None,
        deadline_ms: float | None = None,
    ) -> WorkflowRunRecord | None:
        raise NotImplementedError

    @abstractmethod
    def claim_waiting_run_for_resume(
        self,
        run_id: str,
        *,
        owner: str,
        event_type: str | None = None,
        correlation_key: str | None = None,
    ) -> WorkflowClaim | None:
        raise NotImplementedError

    @abstractmethod
    def clear_wait(self, run_id: str, *, next_status: str = RUN_STATUS_RUNNING) -> WorkflowRunRecord | None:
        raise NotImplementedError

    @abstractmethod
    def schedule_retry(
        self,
        run_id: str,
        *,
        task_id: str | None,
        step_name: str | None,
        attempt: float | None,
        max_retries: float | None,
        delay_ms: float | None,
        next_attempt_at: float | None,
        classification: str | None,
        last_error: str | None,
    ) -> WorkflowRunRecord | None:
        raise NotImplementedError

    @abstractmethod
    def clear_retry(self, run_id: str, *, next_status: str = RUN_STATUS_RUNNING) -> WorkflowRunRecord | None:
        raise NotImplementedError

    @abstractmethod
    def retry_due(self, run_id: str, *, now_ms: float | None = None) -> bool:
        raise NotImplementedError

    @abstractmethod
    def list_due_retry_runs(self, *, now_ms: float | None = None) -> list[WorkflowRunRecord]:
        raise NotImplementedError

    @abstractmethod
    def expire_wait_timeout(
        self,
        run_id: str,
        *,
        now_ms: float | None = None,
        next_status: str = RUN_STATUS_DEAD_LETTERED,
    ) -> WorkflowRunRecord | None:
        raise NotImplementedError

    @abstractmethod
    def expire_wait_timeouts(self, *, now_ms: float | None = None) -> list[WorkflowRunRecord]:
        raise NotImplementedError

    @abstractmethod
    def list_runs(self) -> list[WorkflowRunRecord]:
        raise NotImplementedError

    @abstractmethod
    def list_rehydratable_runs(self) -> list[WorkflowRunRecord]:
        raise NotImplementedError

    @abstractmethod
    def list_terminal_runs(self) -> list[WorkflowRunRecord]:
        raise NotImplementedError

    @abstractmethod
    def store_info(self) -> dict[str, object]:
        raise NotImplementedError


def _serialize_record(record: WorkflowRunRecord) -> tuple:
    return (
        record.run_id,
        record.graph_id,
        record.workflow_name,
        record.execution_kind,
        record.status,
        record.created_at,
        record.updated_at,
        record.current_checkpoint,
        record.resume_count,
        record.last_error,
        json.dumps(record.metadata, sort_keys=True, separators=(",", ":")),
        json.dumps(record.claim.to_dict() if record.claim is not None else None, sort_keys=True, separators=(",", ":")),
        json.dumps(record.wait.to_dict() if record.wait is not None else None, sort_keys=True, separators=(",", ":")),
    )


def _record_from_row(row) -> WorkflowRunRecord | None:
    if row is None:
        return None
    payload = {
        "run_id": row["run_id"],
        "graph_id": row["graph_id"],
        "workflow_name": row["workflow_name"],
        "execution_kind": row["execution_kind"],
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "current_checkpoint": row["current_checkpoint"],
        "resume_count": row["resume_count"],
        "last_error": row["last_error"],
        "metadata": json.loads(row["metadata_json"] or "{}"),
        "claim": json.loads(row["claim_json"] or "null"),
        "wait": json.loads(row["wait_json"] or "null"),
    }
    return WorkflowRunRecord.from_dict(payload)


def _sorted_run_records(records: list[WorkflowRunRecord]) -> list[WorkflowRunRecord]:
    records.sort(key=lambda item: ((item.updated_at or 0.0), item.run_id))
    return records


def _retry_metadata(
    *,
    task_id: str | None,
    step_name: str | None,
    attempt: float | None,
    max_retries: float | None,
    delay_ms: float | None,
    next_attempt_at: float | None,
    classification: str | None,
    last_error: str | None,
) -> dict[str, object | None]:
    return {
        "task_id": task_id,
        "step": step_name,
        "attempt": attempt,
        "max_retries": max_retries,
        "delay_ms": delay_ms,
        "next_attempt_at": next_attempt_at,
        "classification": classification or "retryable",
        "last_error": last_error,
    }


def _schedule_retry_on_record(
    record: WorkflowRunRecord,
    *,
    task_id: str | None,
    step_name: str | None,
    attempt: float | None,
    max_retries: float | None,
    delay_ms: float | None,
    next_attempt_at: float | None,
    classification: str | None,
    last_error: str | None,
) -> WorkflowRunRecord:
    record.status = RUN_STATUS_RETRY_SCHEDULED
    record.wait = None
    record.last_error = last_error
    record.metadata["retry"] = _retry_metadata(
        task_id=task_id,
        step_name=step_name,
        attempt=attempt,
        max_retries=max_retries,
        delay_ms=delay_ms,
        next_attempt_at=next_attempt_at,
        classification=classification,
        last_error=last_error,
    )
    return record


def _retry_due_for_record(record: WorkflowRunRecord, *, now_ms: float | None = None) -> bool:
    if record.status != RUN_STATUS_RETRY_SCHEDULED:
        return False
    retry = record.metadata.get("retry")
    if not isinstance(retry, dict):
        return True
    next_attempt_at = retry.get("next_attempt_at")
    if not isinstance(next_attempt_at, (int, float)):
        return True
    if now_ms is None:
        now_ms = runtime_time_ms()
    return float(now_ms) >= float(next_attempt_at)


def _clear_retry_on_record(record: WorkflowRunRecord, *, next_status: str = RUN_STATUS_RUNNING) -> WorkflowRunRecord:
    record.metadata.pop("retry", None)
    record.status = next_status
    return record


def _register_wait_on_record(
    record: WorkflowRunRecord,
    *,
    event_type: str,
    correlation_key: str | None = None,
    payload: dict[str, object] | None = None,
    deadline_ms: float | None = None,
) -> WorkflowRunRecord:
    record.status = RUN_STATUS_WAITING
    record.wait = WorkflowWaitRecord(
        event_type=event_type,
        correlation_key=correlation_key,
        payload=payload,
        registered_at=runtime_time_ms(),
        deadline_ms=deadline_ms,
    )
    return record


def _clear_wait_on_record(record: WorkflowRunRecord, *, next_status: str = RUN_STATUS_RUNNING) -> WorkflowRunRecord:
    record.wait = None
    record.status = next_status
    return record


def _expire_wait_timeout_on_record(
    record: WorkflowRunRecord,
    *,
    now_ms: float | None = None,
    next_status: str = RUN_STATUS_DEAD_LETTERED,
) -> WorkflowRunRecord | None:
    if record.status != RUN_STATUS_WAITING or record.wait is None:
        return None
    deadline_ms = record.wait.deadline_ms
    registered_at = record.wait.registered_at
    if deadline_ms is None or registered_at is None:
        return None
    if now_ms is None:
        now_ms = runtime_time_ms()
    expires_at = float(registered_at) + float(deadline_ms)
    if float(now_ms) < expires_at:
        return None
    record.status = next_status
    record.claim = None
    record.last_error = f"Wait timeout expired for '{record.run_id}'"
    record.metadata["wait_timeout"] = {
        "expired_at": float(now_ms),
        "registered_at": float(registered_at),
        "deadline_ms": float(deadline_ms),
        "event_type": record.wait.event_type,
        "correlation_key": record.wait.correlation_key,
    }
    return record


def _rehydratable_run_records(records: list[WorkflowRunRecord]) -> list[WorkflowRunRecord]:
    return _sorted_run_records(
        [record for record in records if record.status in REHYDRATABLE_RUN_STATUSES]
    )


def _terminal_run_records(records: list[WorkflowRunRecord]) -> list[WorkflowRunRecord]:
    return [record for record in records if record.status in TERMINAL_RUN_STATUSES]


class LocalWorkflowStore(WorkflowStore):
    """File-backed local store for workflow runs and claims.

    Warning: intended for development and single-process use only.
    ``list_runs()`` reads every run file on every call, so cost is linear in the
    number of accumulated runs — roughly 60 ms per 300 runs, 3.8 s per 10,000
    (measured 2026-08-15, after #380 removed the per-record ``mkdir`` and
    ``stat``). A sweeper calling it on a timer is the usual way this bites.

    Two knobs bound it:

    - ``terminal_max_age_days`` (default 30) skips files not modified in that
      many days without parsing them. It bounds the *scan*, not the directory.
      Note the edge: a non-terminal run left un-updated for longer is skipped
      too, so it drops out of sweeper queries.
    - ``max_terminal_runs`` (default ``None``, off) caps how many finished runs
      are kept, deleting the oldest first as new ones complete. Off by default
      because run records are history a host may rely on. Live runs are never
      pruned.

    Use ``SQLiteWorkflowStore`` for long-lived or production deployments.
    """

    def __init__(
        self,
        root: str | None = None,
        *,
        claim_ttl_ms: float = 30_000.0,
        terminal_max_age_days: float = 30.0,
        max_terminal_runs: int | None = None,
    ) -> None:
        resolved = root or os.path.join(".nodus", "workflow_framework")
        self.root = os.path.abspath(resolved)
        self.claim_ttl_ms = claim_ttl_ms
        self.terminal_max_age_days = terminal_max_age_days
        self.max_terminal_runs = max_terminal_runs
        self._lock = threading.Lock()
        self._runs_root_cache: str | None = None

    def _ensure_root(self) -> str:
        try:
            os.makedirs(self.root, exist_ok=True)
        except FileExistsError:
            if not os.path.isdir(self.root):
                raise
        return self.root

    def _runs_root(self) -> str:
        """The runs directory, created once per store instance.

        #380: this used to `makedirs` both the root and the runs directory on
        every call, and it is called once per record via `_run_path` — so
        listing 3,000 runs made 6,000 mkdir syscalls and spent 1.7 of its 4.2
        seconds there. The directory cannot stop existing under a live store
        that already created it; `_runs_root_uncached` restores the guarantee if
        something removes it.
        """
        if self._runs_root_cache is None:
            self._runs_root_cache = self._runs_root_uncached()
        return self._runs_root_cache

    def _runs_root_uncached(self) -> str:
        root = os.path.join(self._ensure_root(), "runs")
        try:
            os.makedirs(root, exist_ok=True)
        except FileExistsError:
            if not os.path.isdir(root):
                raise
        return root

    def _run_path(self, run_id: str) -> str:
        return os.path.join(self._runs_root(), f"{run_id}.json")

    def _atomic_write_json(self, path: str, data: dict) -> None:
        tmp_path = f"{path}.{uuid.uuid4().hex}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, sort_keys=True, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        self._replace_with_retry(tmp_path, path)

    @staticmethod
    def _replace_with_retry(tmp_path: str, path: str, *, attempts: int = 5) -> None:
        """`os.replace`, retried briefly on Windows sharing violations (#376).

        On Windows the replace fails with `[WinError 5] Access is denied` while
        any handle to the destination is open. In-process readers now hold the
        store lock, which removes the case this repo hit — but a virus scanner,
        an indexer or another process reading the store can hold a handle for a
        few milliseconds, and losing a run record to that is not acceptable when
        waiting is enough. POSIX never takes this path.
        """
        for attempt in range(attempts):
            try:
                os.replace(tmp_path, path)
                return
            except PermissionError:
                if attempt == attempts - 1:
                    raise
                time.sleep(0.02 * (attempt + 1))

    def _load_run_unlocked(self, run_id: str) -> WorkflowRunRecord | None:
        # #380: no `os.path.exists` pre-check — the open below already reports a
        # missing file, and the extra stat doubled the syscalls per record in
        # list_runs(). It was also a race: the file could vanish between the two.
        try:
            with open(self._run_path(run_id), "r", encoding="utf-8") as handle:
                return WorkflowRunRecord.from_dict(json.load(handle))
        except FileNotFoundError:
            return None

    def get_run(self, run_id: str) -> WorkflowRunRecord | None:
        with self._lock:
            return self._load_run_unlocked(run_id)

    def delete_run(self, run_id: str) -> bool:
        with self._lock:
            try:
                os.remove(self._run_path(run_id))
                return True
            except OSError:
                return False

    def save_run(self, record: WorkflowRunRecord) -> WorkflowRunRecord:
        record.updated_at = runtime_time_ms()
        with self._lock:
            if record.created_at is None:
                record.created_at = record.updated_at
            self._atomic_write_json(self._run_path(record.run_id), record.to_dict())
        if record.status in TERMINAL_RUN_STATUSES:
            self._prune_terminal_runs()
        return record

    def _prune_terminal_runs(self) -> None:
        """Keep at most ``max_terminal_runs`` finished runs, oldest deleted first.

        Opt-in, and off by default: run records are a history a host may be
        relying on, and silently deleting them is not a decision this store
        should make on anyone's behalf. Age-based retention
        (``terminal_max_age_days``) bounds the *scan* cost but not the directory,
        so a host that keeps a store for years and wants a hard ceiling sets this
        (#380).

        Only terminal runs are ever removed — a waiting or retrying run is live
        state, whatever the count.
        """
        limit = self.max_terminal_runs
        if limit is None or limit < 0:
            return
        with self._lock:
            terminal = sorted(
                (r for r in self._list_runs_unlocked() if r.status in TERMINAL_RUN_STATUSES),
                key=lambda r: (r.updated_at or 0, r.run_id),
            )
            for stale in terminal[: max(0, len(terminal) - limit)]:
                try:
                    os.remove(self._run_path(stale.run_id))
                except OSError:
                    continue
                # #476: the record's other half. A run is split across this
                # store and `.nodus/graphs/`; a host that opts into a record
                # cap wants the run gone, not half of it, so the graph snapshot
                # and checkpoint go with the record. The graph root is
                # CWD-relative while this store's root was made absolute at
                # construction, so the pair lines up when both were created
                # from the same working directory -- which is every in-process
                # path that writes both.
                from nodus.orchestration.task_graph import delete_checkpoint, delete_graph_state

                delete_graph_state(stale.run_id)
                delete_checkpoint(stale.run_id)

    def create_run(
        self,
        *,
        run_id: str,
        graph_id: str,
        workflow_name: str | None,
        execution_kind: str | None,
        metadata: dict[str, object] | None = None,
    ) -> WorkflowRunRecord:
        now = runtime_time_ms()
        existing = self.get_run(run_id)
        if existing is not None:
            return existing
        record = WorkflowRunRecord(
            run_id=run_id,
            graph_id=graph_id,
            workflow_name=workflow_name,
            execution_kind=execution_kind,
            status=RUN_STATUS_PENDING,
            created_at=now,
            updated_at=now,
            metadata=dict(metadata or {}),
        )
        return self.save_run(record)

    def claim_run(
        self,
        run_id: str,
        *,
        owner: str,
        expected_statuses: tuple[str, ...] = (
            RUN_STATUS_PENDING,
            RUN_STATUS_RUNNING,
            RUN_STATUS_WAITING,
            RUN_STATUS_RETRY_SCHEDULED,
        ),
    ) -> WorkflowClaim | None:
        now = runtime_time_ms()
        with self._lock:
            record = self._load_run_unlocked(run_id)
            if record is None or record.status not in expected_statuses:
                return None
            claim = record.claim
            if claim is not None and claim.expires_at is not None and claim.expires_at > now:
                return None
            fresh = WorkflowClaim(
                token=f"claim_{uuid.uuid4().hex[:12]}",
                owner=owner,
                claimed_at=now,
                expires_at=now + self.claim_ttl_ms,
            )
            record.claim = fresh
            record.updated_at = now
            self._atomic_write_json(self._run_path(run_id), record.to_dict())
            return fresh

    def release_claim(self, run_id: str, token: str | None) -> WorkflowRunRecord | None:
        with self._lock:
            record = self._load_run_unlocked(run_id)
            if record is None:
                return None
            if token is None or record.claim is None or record.claim.token == token:
                record.claim = None
                record.updated_at = runtime_time_ms()
                self._atomic_write_json(self._run_path(run_id), record.to_dict())
            return record

    def register_wait(
        self,
        run_id: str,
        *,
        event_type: str,
        correlation_key: str | None = None,
        payload: dict[str, object] | None = None,
        deadline_ms: float | None = None,
    ) -> WorkflowRunRecord | None:
        record = self.get_run(run_id)
        if record is None:
            return None
        _register_wait_on_record(
            record,
            event_type=event_type,
            correlation_key=correlation_key,
            payload=payload,
            deadline_ms=deadline_ms,
        )
        return self.save_run(record)

    def claim_waiting_run_for_resume(
        self,
        run_id: str,
        *,
        owner: str,
        event_type: str | None = None,
        correlation_key: str | None = None,
    ) -> WorkflowClaim | None:
        record = self.get_run(run_id)
        if record is None or record.wait is None or record.status != RUN_STATUS_WAITING:
            return None
        if event_type is not None and record.wait.event_type != event_type:
            return None
        if correlation_key is not None and record.wait.correlation_key != correlation_key:
            return None
        return self.claim_run(run_id, owner=owner, expected_statuses=(RUN_STATUS_WAITING,))

    def clear_wait(
        self,
        run_id: str,
        *,
        next_status: str = RUN_STATUS_RUNNING,
    ) -> WorkflowRunRecord | None:
        record = self.get_run(run_id)
        if record is None:
            return None
        _clear_wait_on_record(record, next_status=next_status)
        return self.save_run(record)

    def schedule_retry(
        self,
        run_id: str,
        *,
        task_id: str | None,
        step_name: str | None,
        attempt: float | None,
        max_retries: float | None,
        delay_ms: float | None,
        next_attempt_at: float | None,
        classification: str | None,
        last_error: str | None,
    ) -> WorkflowRunRecord | None:
        record = self.get_run(run_id)
        if record is None:
            return None
        _schedule_retry_on_record(
            record,
            task_id=task_id,
            step_name=step_name,
            attempt=attempt,
            max_retries=max_retries,
            delay_ms=delay_ms,
            next_attempt_at=next_attempt_at,
            classification=classification,
            last_error=last_error,
        )
        return self.save_run(record)

    def clear_retry(
        self,
        run_id: str,
        *,
        next_status: str = RUN_STATUS_RUNNING,
    ) -> WorkflowRunRecord | None:
        record = self.get_run(run_id)
        if record is None:
            return None
        _clear_retry_on_record(record, next_status=next_status)
        return self.save_run(record)

    def retry_due(self, run_id: str, *, now_ms: float | None = None) -> bool:
        record = self.get_run(run_id)
        if record is None:
            return False
        return _retry_due_for_record(record, now_ms=now_ms)

    def list_due_retry_runs(self, *, now_ms: float | None = None) -> list[WorkflowRunRecord]:
        due: list[WorkflowRunRecord] = []
        for record in self.list_runs():
            if _retry_due_for_record(record, now_ms=now_ms):
                due.append(record)
        return _sorted_run_records(due)

    def expire_wait_timeout(
        self,
        run_id: str,
        *,
        now_ms: float | None = None,
        next_status: str = RUN_STATUS_DEAD_LETTERED,
    ) -> WorkflowRunRecord | None:
        record = self.get_run(run_id)
        if record is None:
            return None
        expired = _expire_wait_timeout_on_record(record, now_ms=now_ms, next_status=next_status)
        if expired is None:
            return None
        return self.save_run(expired)

    def expire_wait_timeouts(self, *, now_ms: float | None = None) -> list[WorkflowRunRecord]:
        # #380: only runs that are actually waiting can expire. This used to call
        # expire_wait_timeout() for every run, and that re-reads the file it was
        # just handed — two full reads of the whole directory per sweep, on a
        # background timer. Filtering first makes the common case (nothing
        # waiting) cost one pass instead of two.
        expired: list[WorkflowRunRecord] = []
        for record in self.list_runs():
            if record.status != RUN_STATUS_WAITING:
                continue
            updated = self.expire_wait_timeout(record.run_id, now_ms=now_ms)
            if updated is not None:
                expired.append(updated)
        return _sorted_run_records(expired)

    def list_runs(self) -> list[WorkflowRunRecord]:
        # #376: hold the lock while scanning. Reads were lock-free, so a scan
        # could have a run file open exactly while another thread replaced it —
        # and on Windows `os.replace` onto a path someone else has open fails
        # with "[WinError 5] Access is denied", surfacing as a LangRuntimeError
        # out of a workflow that did nothing wrong. POSIX allows the replace, so
        # this is invisible on Linux and reproducible here.
        #
        # `_prune_terminal_runs` already holds the lock and must keep calling the
        # unlocked variant: threading.Lock is not reentrant.
        with self._lock:
            return self._list_runs_unlocked()

    def _list_runs_unlocked(self) -> list[WorkflowRunRecord]:
        root = self._runs_root()
        records: list[WorkflowRunRecord] = []
        cutoff_s: float | None = None
        if self.terminal_max_age_days > 0:
            cutoff_s = time.time() - self.terminal_max_age_days * 86_400.0
        for entry in os.scandir(root):
            if not entry.name.endswith(".json") or entry.name.endswith(".tmp"):
                continue
            if cutoff_s is not None and entry.stat().st_mtime < cutoff_s:
                continue  # skip files not touched in terminal_max_age_days (old completed runs)
            run_id = entry.name[:-5]
            record = self._load_run_unlocked(run_id)
            if record is not None:
                records.append(record)
        return _sorted_run_records(records)

    def list_rehydratable_runs(self) -> list[WorkflowRunRecord]:
        return _rehydratable_run_records(self.list_runs())

    def list_terminal_runs(self) -> list[WorkflowRunRecord]:
        return _terminal_run_records(self.list_runs())

    def store_info(self) -> dict[str, object]:
        return {
            "backend": "local",
            "root": self.root,
            "coordination_mode": "local_only",
        }



def _exec(conn: sqlite3.Connection, sql: str, params=()) -> None:
    """Run a statement and close its cursor.

    `conn.execute(...)` returns a cursor. Left unreferenced, CPython's refcounting
    frees it at once, which finalises the statement; a runtime without refcounting
    keeps it alive until the next GC, and the statement is still open when the
    enclosing block commits:

        sqlite3.OperationalError: cannot commit transaction - SQL statements in progress

    So the store was depending on *when CPython happens to free an object* for
    correctness (#516). These three helpers exist rather than a `close()` at each
    of the twelve call sites, because twelve places remembering is twelve places
    to forget and the thirteenth will.
    """
    _run(conn, sql, params, None)


def _fetchone(conn: sqlite3.Connection, sql: str, params=()):
    return _run(conn, sql, params, "one")


def _fetchall(conn: sqlite3.Connection, sql: str, params=()) -> list:
    return _run(conn, sql, params, "all") or []


def _exec_rowcount(conn: sqlite3.Connection, sql: str, params=()) -> int:
    return _run(conn, sql, params, "rowcount") or 0


def _run(conn: sqlite3.Connection, sql: str, params, fetch):
    """Own the cursor from creation so it closes even when the statement fails.

    `cur = conn.execute(...)` would create the cursor *inside* the call, so a
    statement that raises never returns one and there is nothing to close -- the
    failure path would be back to relying on refcounting, which is the whole bug.
    Taking the cursor first and executing on it puts every exit through the same
    `finally`.
    """
    cur = conn.cursor()
    try:
        cur.execute(sql, params)
        if fetch == "one":
            return cur.fetchone()
        if fetch == "all":
            return cur.fetchall()
        if fetch == "rowcount":
            return cur.rowcount
        return None
    finally:
        cur.close()


class SQLiteWorkflowStore(WorkflowStore):
    """SQLite-backed workflow store for cross-process coordination."""

    def __init__(self, path: str | None = None, *, claim_ttl_ms: float = 30_000.0) -> None:
        resolved = path or os.path.join(".nodus", "workflow_framework.sqlite3")
        self.path = os.path.abspath(resolved)
        self.claim_ttl_ms = claim_ttl_ms
        self._lock = threading.Lock()
        self._ensure_db()

    def _ensure_parent(self) -> None:
        parent = os.path.dirname(self.path)
        if parent:
            os.makedirs(parent, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        self._ensure_parent()
        conn = sqlite3.connect(self.path, timeout=5.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        _exec(conn, "PRAGMA journal_mode=WAL")
        _exec(conn, "PRAGMA synchronous=NORMAL")
        return conn

    @contextmanager
    def _managed_conn(self):
        conn = self._connect()
        try:
            yield conn
        finally:
            conn.close()

    def _ensure_db(self) -> None:
        with self._managed_conn() as conn:
            _exec(
                conn,
                """
                CREATE TABLE IF NOT EXISTS workflow_runs (
                    run_id TEXT PRIMARY KEY,
                    graph_id TEXT NOT NULL,
                    workflow_name TEXT,
                    execution_kind TEXT,
                    status TEXT NOT NULL,
                    created_at REAL,
                    updated_at REAL,
                    current_checkpoint TEXT,
                    resume_count INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    metadata_json TEXT NOT NULL,
                    claim_json TEXT,
                    wait_json TEXT
                )
                """
            )
            _exec(
                conn,
                "CREATE INDEX IF NOT EXISTS idx_workflow_runs_status ON workflow_runs(status)",
            )

    def _get_run_with_conn(self, conn: sqlite3.Connection, run_id: str) -> WorkflowRunRecord | None:
        row = _fetchone(
            conn,
            """
            SELECT run_id, graph_id, workflow_name, execution_kind, status, created_at, updated_at,
                   current_checkpoint, resume_count, last_error, metadata_json, claim_json, wait_json
            FROM workflow_runs
            WHERE run_id = ?
            """,
            (run_id,),
        )
        return _record_from_row(row)

    def get_run(self, run_id: str) -> WorkflowRunRecord | None:
        with self._managed_conn() as conn:
            return self._get_run_with_conn(conn, run_id)

    def delete_run(self, run_id: str) -> bool:
        with self._managed_conn() as conn:
            return bool(
                _exec_rowcount(conn, "DELETE FROM workflow_runs WHERE run_id = ?", (run_id,))
            )

    def save_run(self, record: WorkflowRunRecord) -> WorkflowRunRecord:
        record.updated_at = runtime_time_ms()
        if record.created_at is None:
            record.created_at = record.updated_at
        with self._managed_conn() as conn:
            _exec(
                conn,
                """
                INSERT INTO workflow_runs (
                    run_id, graph_id, workflow_name, execution_kind, status, created_at, updated_at,
                    current_checkpoint, resume_count, last_error, metadata_json, claim_json, wait_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    graph_id=excluded.graph_id,
                    workflow_name=excluded.workflow_name,
                    execution_kind=excluded.execution_kind,
                    status=excluded.status,
                    created_at=excluded.created_at,
                    updated_at=excluded.updated_at,
                    current_checkpoint=excluded.current_checkpoint,
                    resume_count=excluded.resume_count,
                    last_error=excluded.last_error,
                    metadata_json=excluded.metadata_json,
                    claim_json=excluded.claim_json,
                    wait_json=excluded.wait_json
                """,
                _serialize_record(record),
            )
        return record

    def create_run(
        self,
        *,
        run_id: str,
        graph_id: str,
        workflow_name: str | None,
        execution_kind: str | None,
        metadata: dict[str, object] | None = None,
    ) -> WorkflowRunRecord:
        now = runtime_time_ms()
        record = WorkflowRunRecord(
            run_id=run_id,
            graph_id=graph_id,
            workflow_name=workflow_name,
            execution_kind=execution_kind,
            status=RUN_STATUS_PENDING,
            created_at=now,
            updated_at=now,
            metadata=dict(metadata or {}),
        )
        with self._managed_conn() as conn:
            existing = self._get_run_with_conn(conn, run_id)
            if existing is not None:
                return existing
            _exec(
                conn,
                """
                INSERT INTO workflow_runs (
                    run_id, graph_id, workflow_name, execution_kind, status, created_at, updated_at,
                    current_checkpoint, resume_count, last_error, metadata_json, claim_json, wait_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                _serialize_record(record),
            )
        return record

    def claim_run(
        self,
        run_id: str,
        *,
        owner: str,
        expected_statuses: tuple[str, ...] = (
            RUN_STATUS_PENDING,
            RUN_STATUS_RUNNING,
            RUN_STATUS_WAITING,
            RUN_STATUS_RETRY_SCHEDULED,
        ),
    ) -> WorkflowClaim | None:
        now = runtime_time_ms()
        with self._lock, self._managed_conn() as conn:
            _exec(conn, "BEGIN IMMEDIATE")
            record = self._get_run_with_conn(conn, run_id)
            if record is None or record.status not in expected_statuses:
                conn.rollback()
                return None
            claim = record.claim
            if claim is not None and claim.expires_at is not None and claim.expires_at > now:
                conn.rollback()
                return None
            fresh = WorkflowClaim(
                token=f"claim_{uuid.uuid4().hex[:12]}",
                owner=owner,
                claimed_at=now,
                expires_at=now + self.claim_ttl_ms,
            )
            record.claim = fresh
            record.updated_at = now
            _exec(
                conn,
                "UPDATE workflow_runs SET updated_at = ?, claim_json = ? WHERE run_id = ?",
                (
                    record.updated_at,
                    json.dumps(fresh.to_dict(), sort_keys=True, separators=(",", ":")),
                    run_id,
                ),
            )
            conn.commit()
            return fresh

    def release_claim(self, run_id: str, token: str | None) -> WorkflowRunRecord | None:
        with self._lock, self._managed_conn() as conn:
            _exec(conn, "BEGIN IMMEDIATE")
            record = self._get_run_with_conn(conn, run_id)
            if record is None:
                conn.rollback()
                return None
            if token is None or record.claim is None or record.claim.token == token:
                record.claim = None
                record.updated_at = runtime_time_ms()
                _exec(
                    conn,
                    "UPDATE workflow_runs SET updated_at = ?, claim_json = NULL WHERE run_id = ?",
                    (record.updated_at, run_id),
                )
            conn.commit()
            return record

    def register_wait(
        self,
        run_id: str,
        *,
        event_type: str,
        correlation_key: str | None = None,
        payload: dict[str, object] | None = None,
        deadline_ms: float | None = None,
    ) -> WorkflowRunRecord | None:
        record = self.get_run(run_id)
        if record is None:
            return None
        _register_wait_on_record(
            record,
            event_type=event_type,
            correlation_key=correlation_key,
            payload=payload,
            deadline_ms=deadline_ms,
        )
        return self.save_run(record)

    def claim_waiting_run_for_resume(
        self,
        run_id: str,
        *,
        owner: str,
        event_type: str | None = None,
        correlation_key: str | None = None,
    ) -> WorkflowClaim | None:
        record = self.get_run(run_id)
        if record is None or record.wait is None or record.status != RUN_STATUS_WAITING:
            return None
        if event_type is not None and record.wait.event_type != event_type:
            return None
        if correlation_key is not None and record.wait.correlation_key != correlation_key:
            return None
        return self.claim_run(run_id, owner=owner, expected_statuses=(RUN_STATUS_WAITING,))

    def clear_wait(self, run_id: str, *, next_status: str = RUN_STATUS_RUNNING) -> WorkflowRunRecord | None:
        record = self.get_run(run_id)
        if record is None:
            return None
        _clear_wait_on_record(record, next_status=next_status)
        return self.save_run(record)

    def schedule_retry(
        self,
        run_id: str,
        *,
        task_id: str | None,
        step_name: str | None,
        attempt: float | None,
        max_retries: float | None,
        delay_ms: float | None,
        next_attempt_at: float | None,
        classification: str | None,
        last_error: str | None,
    ) -> WorkflowRunRecord | None:
        record = self.get_run(run_id)
        if record is None:
            return None
        _schedule_retry_on_record(
            record,
            task_id=task_id,
            step_name=step_name,
            attempt=attempt,
            max_retries=max_retries,
            delay_ms=delay_ms,
            next_attempt_at=next_attempt_at,
            classification=classification,
            last_error=last_error,
        )
        return self.save_run(record)

    def clear_retry(self, run_id: str, *, next_status: str = RUN_STATUS_RUNNING) -> WorkflowRunRecord | None:
        record = self.get_run(run_id)
        if record is None:
            return None
        _clear_retry_on_record(record, next_status=next_status)
        return self.save_run(record)

    def retry_due(self, run_id: str, *, now_ms: float | None = None) -> bool:
        record = self.get_run(run_id)
        if record is None:
            return False
        return _retry_due_for_record(record, now_ms=now_ms)

    def list_due_retry_runs(self, *, now_ms: float | None = None) -> list[WorkflowRunRecord]:
        due: list[WorkflowRunRecord] = []
        for record in self.list_runs():
            if _retry_due_for_record(record, now_ms=now_ms):
                due.append(record)
        return _sorted_run_records(due)

    def expire_wait_timeout(
        self,
        run_id: str,
        *,
        now_ms: float | None = None,
        next_status: str = RUN_STATUS_DEAD_LETTERED,
    ) -> WorkflowRunRecord | None:
        record = self.get_run(run_id)
        if record is None:
            return None
        expired = _expire_wait_timeout_on_record(record, now_ms=now_ms, next_status=next_status)
        if expired is None:
            return None
        return self.save_run(expired)

    def expire_wait_timeouts(self, *, now_ms: float | None = None) -> list[WorkflowRunRecord]:
        # #380: only runs that are actually waiting can expire. This used to call
        # expire_wait_timeout() for every run, and that re-reads the file it was
        # just handed — two full reads of the whole directory per sweep, on a
        # background timer. Filtering first makes the common case (nothing
        # waiting) cost one pass instead of two.
        expired: list[WorkflowRunRecord] = []
        for record in self.list_runs():
            if record.status != RUN_STATUS_WAITING:
                continue
            updated = self.expire_wait_timeout(record.run_id, now_ms=now_ms)
            if updated is not None:
                expired.append(updated)
        return _sorted_run_records(expired)

    def list_runs(self) -> list[WorkflowRunRecord]:
        with self._managed_conn() as conn:
            rows = _fetchall(
                conn,
                """
                SELECT run_id, graph_id, workflow_name, execution_kind, status, created_at, updated_at,
                       current_checkpoint, resume_count, last_error, metadata_json, claim_json, wait_json
                FROM workflow_runs
                """,
            )
        records = [record for record in (_record_from_row(row) for row in rows) if record is not None]
        return _sorted_run_records(records)

    def list_rehydratable_runs(self) -> list[WorkflowRunRecord]:
        return _rehydratable_run_records(self.list_runs())

    def list_terminal_runs(self) -> list[WorkflowRunRecord]:
        return _terminal_run_records(self.list_runs())

    def store_info(self) -> dict[str, object]:
        return {
            "backend": "sqlite",
            "path": self.path,
            "coordination_mode": "sqlite",
        }


def create_workflow_store(
    *,
    backend: str | None = None,
    root: str | None = None,
    path: str | None = None,
    claim_ttl_ms: float = 30_000.0,
    terminal_max_age_days: float = 30.0,
) -> WorkflowStore:
    backend_name = str(backend or "local").strip().lower()
    if backend_name == "local":
        return LocalWorkflowStore(root=root, claim_ttl_ms=claim_ttl_ms, terminal_max_age_days=terminal_max_age_days)
    if backend_name == "sqlite":
        return SQLiteWorkflowStore(path=path, claim_ttl_ms=claim_ttl_ms)
    raise ValueError(f"Unknown workflow store backend: {backend}")
