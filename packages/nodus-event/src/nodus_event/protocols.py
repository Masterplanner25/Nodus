from __future__ import annotations

from typing import Protocol

from .models import EventAuditRecord, EventCause, EventEnvelope, WebhookSubscription


class EventHandler(Protocol):
    def __call__(self, envelope: EventEnvelope) -> object: ...


class HandlerPolicy(Protocol):
    def should_continue_after_error(self, *, event_type: str, handler_name: str, error: Exception) -> bool: ...


class DeliveryPolicy(Protocol):
    def should_publish_distributed(self, envelope: EventEnvelope) -> bool: ...

    def should_dispatch_webhooks(self, envelope: EventEnvelope) -> bool: ...


class WebhookPolicy(Protocol):
    def build_headers(self, subscription: WebhookSubscription, envelope: EventEnvelope) -> dict[str, str]: ...


class CausalityPolicy(Protocol):
    def attach(self, envelope: EventEnvelope, *, cause: EventCause | None) -> EventEnvelope: ...


class AuditStore(Protocol):
    def create_record(self, record: EventAuditRecord) -> EventAuditRecord: ...

    def update_record(self, record: EventAuditRecord) -> EventAuditRecord: ...

    def get_record(self, event_id: str) -> EventAuditRecord | None: ...

    def list_records(self) -> list[EventAuditRecord]: ...


class DistributedEventPublisher(Protocol):
    def publish(self, envelope: EventEnvelope) -> dict[str, object]: ...


class WebhookDispatcher(Protocol):
    def dispatch(
        self,
        subscription: WebhookSubscription,
        envelope: EventEnvelope,
        headers: dict[str, str],
    ) -> dict[str, object]: ...
