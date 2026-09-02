"""Workflow framework data models."""

from __future__ import annotations

from dataclasses import dataclass, field

from nodus.orchestration.workflow_state import WAIT_TIMEOUT_POLICIES


RUN_STATUS_PENDING = "pending"
RUN_STATUS_RUNNING = "running"
RUN_STATUS_WAITING = "waiting"
RUN_STATUS_RETRY_SCHEDULED = "retry_scheduled"
RUN_STATUS_COMPLETED = "completed"
RUN_STATUS_FAILED = "failed"
RUN_STATUS_DEAD_LETTERED = "dead_lettered"
# #395 §7.3: a cancelled run is not a failed one. It did not fail, it was
# stopped, and reporting it as `failed` would corrupt every failure rate an
# operator computes. Terminal, and deliberately NOT rehydratable -- a cancelled
# run that resurrects on the next sweep has un-cancelled itself.
RUN_STATUS_CANCELLED = "cancelled"

# The run-status vocabulary, named once (#395 §7.3).
#
# It was named three times before: `REHYDRATABLE_RUN_STATUSES` in `store.py` and
# `_REHYDRATABLE_STATUSES` in `runner.py` were two independent definitions of one
# equal set, plus `_KNOWN_RUN_STATUSES` listing the members again. Adding an
# eighth status is exactly when that costs something -- four edits, and the one
# you miss is silent.
#
# `nodus_gate --shapes` did not catch it: its species-B detector looks for one
# literal collection being a strict *subset* of another, and these were equal.
# Worth knowing about the detector, not a reason to leave the duplication.
#
# Partitioned deliberately: every status is terminal or not, and the two sets
# below must stay disjoint. `tests/test_run_status_vocabulary.py` drives off this
# tuple, so a ninth status fails the suite until it is classified.
RUN_STATUSES: tuple[str, ...] = (
    RUN_STATUS_PENDING,
    RUN_STATUS_RUNNING,
    RUN_STATUS_WAITING,
    RUN_STATUS_RETRY_SCHEDULED,
    RUN_STATUS_COMPLETED,
    RUN_STATUS_FAILED,
    RUN_STATUS_DEAD_LETTERED,
    RUN_STATUS_CANCELLED,
)

#: A run in one of these states can be picked up and continued after a restart.
REHYDRATABLE_RUN_STATUSES = frozenset({
    RUN_STATUS_WAITING,
    RUN_STATUS_RUNNING,
    RUN_STATUS_RETRY_SCHEDULED,
})

#: A run in one of these states is done, and `workflow cleanup` may retire it.
#: `cancelled` belongs here or cancelled runs accumulate forever.
TERMINAL_RUN_STATUSES = frozenset({
    RUN_STATUS_COMPLETED,
    RUN_STATUS_FAILED,
    RUN_STATUS_DEAD_LETTERED,
    RUN_STATUS_CANCELLED,
})


@dataclass
class WorkflowClaim:
    token: str
    owner: str
    claimed_at: float
    expires_at: float | None = None

    def to_dict(self) -> dict:
        return {
            "token": self.token,
            "owner": self.owner,
            "claimed_at": self.claimed_at,
            "expires_at": self.expires_at,
        }

    @classmethod
    def from_dict(cls, payload: dict | None) -> "WorkflowClaim | None":
        if not isinstance(payload, dict):
            return None
        token = payload.get("token")
        owner = payload.get("owner")
        claimed_at = payload.get("claimed_at")
        if not isinstance(token, str) or not isinstance(owner, str):
            return None
        if not isinstance(claimed_at, (int, float)):
            return None
        expires_at = payload.get("expires_at")
        if not isinstance(expires_at, (int, float)):
            expires_at = None
        return cls(token=token, owner=owner, claimed_at=float(claimed_at), expires_at=expires_at)


@dataclass
class WorkflowWaitRecord:
    event_type: str
    correlation_key: str | None = None
    payload: dict[str, object] | None = None
    registered_at: float | None = None
    deadline_ms: float | None = None
    # #472: the declared shape of the payload a resume must deliver. Normalised
    # at the wait site, so what is persisted is already a plain JSON-safe dict.
    # None means "accept anything", which is what every wait written before this
    # existed means.
    schema: dict[str, object] | None = None
    #: What a passed `deadline_ms` means (#176). `"fail"` -- the long-standing
    #: behaviour and still the default -- dead-letters the run: the event did not
    #: arrive and that is an error. `"resume"` makes the deadline a *schedule*:
    #: the wait clears and the run carries on, which is what lets a workflow park
    #: itself and be picked up by a later process.
    on_timeout: str = "fail"

    def to_dict(self) -> dict:
        record = {
            "event_type": self.event_type,
            "correlation_key": self.correlation_key,
            "payload": dict(self.payload or {}),
            "registered_at": self.registered_at,
            "deadline_ms": self.deadline_ms,
        }
        if self.on_timeout != "fail":
            # Omitted at the default so a run recorded before #176 round-trips
            # byte-identically -- the same rule `schema` follows.
            record["on_timeout"] = self.on_timeout
        if self.schema:
            # Omitted when absent so a run recorded before #472 round-trips
            # byte-identically.
            record["schema"] = dict(self.schema)
        return record

    @classmethod
    def from_dict(cls, payload: dict | None) -> "WorkflowWaitRecord | None":
        if not isinstance(payload, dict):
            return None
        event_type = payload.get("event_type")
        if not isinstance(event_type, str) or not event_type:
            return None
        correlation_key = payload.get("correlation_key")
        if not isinstance(correlation_key, str):
            correlation_key = None
        body = payload.get("payload")
        if not isinstance(body, dict):
            body = None
        registered_at = payload.get("registered_at")
        if not isinstance(registered_at, (int, float)):
            registered_at = None
        deadline_ms = payload.get("deadline_ms")
        if not isinstance(deadline_ms, (int, float)):
            deadline_ms = None
        schema = payload.get("schema")
        if not isinstance(schema, dict):
            schema = None
        on_timeout = payload.get("on_timeout")
        if on_timeout not in WAIT_TIMEOUT_POLICIES:
            # A record written before #176, or a value nothing wrote. Defaults to
            # the behaviour every such record was created under.
            on_timeout = "fail"
        return cls(
            event_type=event_type,
            correlation_key=correlation_key,
            payload=body,
            registered_at=registered_at,
            deadline_ms=deadline_ms,
            schema=schema,
            on_timeout=on_timeout,
        )


@dataclass
class WorkflowRunRecord:
    run_id: str
    graph_id: str
    workflow_name: str | None = None
    execution_kind: str | None = None
    status: str = RUN_STATUS_PENDING
    created_at: float | None = None
    updated_at: float | None = None
    current_checkpoint: str | None = None
    resume_count: int = 0
    last_error: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)
    claim: WorkflowClaim | None = None
    wait: WorkflowWaitRecord | None = None

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "graph_id": self.graph_id,
            "workflow_name": self.workflow_name,
            "execution_kind": self.execution_kind,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "current_checkpoint": self.current_checkpoint,
            "resume_count": self.resume_count,
            "last_error": self.last_error,
            "metadata": dict(self.metadata),
            "claim": self.claim.to_dict() if self.claim is not None else None,
            "wait": self.wait.to_dict() if self.wait is not None else None,
        }

    @classmethod
    def from_dict(cls, payload: dict | None) -> "WorkflowRunRecord | None":
        if not isinstance(payload, dict):
            return None
        run_id = payload.get("run_id")
        graph_id = payload.get("graph_id")
        if not isinstance(run_id, str) or not isinstance(graph_id, str):
            return None
        metadata = payload.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
        workflow_name = payload.get("workflow_name")
        if not isinstance(workflow_name, str):
            workflow_name = None
        execution_kind = payload.get("execution_kind")
        if not isinstance(execution_kind, str):
            execution_kind = None
        status = payload.get("status")
        if not isinstance(status, str):
            status = RUN_STATUS_PENDING
        created_at = payload.get("created_at")
        if not isinstance(created_at, (int, float)):
            created_at = None
        updated_at = payload.get("updated_at")
        if not isinstance(updated_at, (int, float)):
            updated_at = None
        current_checkpoint = payload.get("current_checkpoint")
        if not isinstance(current_checkpoint, str):
            current_checkpoint = None
        resume_count = payload.get("resume_count")
        if not isinstance(resume_count, int):
            resume_count = 0
        last_error = payload.get("last_error")
        if not isinstance(last_error, str):
            last_error = None
        return cls(
            run_id=run_id,
            graph_id=graph_id,
            workflow_name=workflow_name,
            execution_kind=execution_kind,
            status=status,
            created_at=created_at,
            updated_at=updated_at,
            current_checkpoint=current_checkpoint,
            resume_count=resume_count,
            last_error=last_error,
            metadata=metadata,
            claim=WorkflowClaim.from_dict(payload.get("claim")),
            wait=WorkflowWaitRecord.from_dict(payload.get("wait")),
        )
