from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

from .errors import IdempotencyConflictError
from .models import EffectRecord


class IdempotencyStore(Protocol):
    def lookup(self, action_id: str) -> EffectRecord | None: ...

    def begin(self, record: EffectRecord) -> EffectRecord: ...

    def mark_completed(self, action_id: str, result_payload: object) -> EffectRecord: ...

    def mark_failed(self, action_id: str, error_payload: object) -> EffectRecord: ...

    def increment_attempts(self, action_id: str) -> EffectRecord: ...


class InMemoryIdempotencyStore:
    def __init__(self) -> None:
        self._records: dict[str, EffectRecord] = {}

    def lookup(self, action_id: str) -> EffectRecord | None:
        return self._records.get(action_id)

    def begin(self, record: EffectRecord) -> EffectRecord:
        existing = self._records.get(record.action_id)
        if existing is not None and existing.status == "pending":
            raise IdempotencyConflictError(f"Effect {record.action_id!r} is already pending.")
        if existing is None:
            self._records[record.action_id] = record
            return record
        return existing

    def mark_completed(self, action_id: str, result_payload: object) -> EffectRecord:
        record = self._require(action_id)
        now = datetime.now(timezone.utc)
        record.status = "completed"
        record.result_payload = result_payload
        record.error_payload = None
        record.updated_at = now
        record.completed_at = now
        return record

    def mark_failed(self, action_id: str, error_payload: object) -> EffectRecord:
        record = self._require(action_id)
        now = datetime.now(timezone.utc)
        record.status = "failed"
        record.error_payload = error_payload
        record.updated_at = now
        return record

    def increment_attempts(self, action_id: str) -> EffectRecord:
        record = self._require(action_id)
        record.attempt_count += 1
        record.updated_at = datetime.now(timezone.utc)
        return record

    def _require(self, action_id: str) -> EffectRecord:
        try:
            return self._records[action_id]
        except KeyError as exc:
            raise KeyError(f"Unknown effect record {action_id!r}") from exc
