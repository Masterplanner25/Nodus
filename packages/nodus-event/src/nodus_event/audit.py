from __future__ import annotations

from .models import EventAuditRecord


class InMemoryAuditStore:
    def __init__(self) -> None:
        self._records: dict[str, EventAuditRecord] = {}

    def create_record(self, record: EventAuditRecord) -> EventAuditRecord:
        self._records[record.event_id] = record
        return record

    def update_record(self, record: EventAuditRecord) -> EventAuditRecord:
        self._records[record.event_id] = record
        return record

    def get_record(self, event_id: str) -> EventAuditRecord | None:
        return self._records.get(event_id)

    def list_records(self) -> list[EventAuditRecord]:
        return list(self._records.values())


class InMemoryWebhookDispatcher:
    def __init__(self) -> None:
        self.deliveries: list[dict[str, object]] = []

    def dispatch(self, subscription, envelope, headers):
        outcome = {
            "subscription_id": subscription.subscription_id,
            "target_url": subscription.target_url,
            "event_id": envelope.event_id,
            "headers": headers,
            "accepted": True,
        }
        self.deliveries.append(outcome)
        return outcome
