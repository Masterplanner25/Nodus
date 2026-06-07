from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from .models import DeliveryResult, EventEnvelope


class DeliveryBackend(Protocol):
    def publish(self, envelope: EventEnvelope) -> None: ...

    def start(self, handler: Callable[[EventEnvelope], None]) -> None: ...

    def stop(self) -> None: ...

    def is_running(self) -> bool: ...


class AuditStore(Protocol):
    def record_publish_started(self, envelope: EventEnvelope) -> None: ...

    def record_publish_completed(self, envelope: EventEnvelope, result: DeliveryResult) -> None: ...

    def record_publish_failed(self, envelope: EventEnvelope, error: Exception) -> None: ...
