from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Callable
from itertools import count

from .errors import EventDeliveryError
from .models import BufferPolicy, DeliveryResult, EventEnvelope, Subscription
from .protocols import AuditStore, DeliveryBackend

EventHandler = Callable[[EventEnvelope], None]


class EventBus:
    def __init__(
        self,
        *,
        source_instance_id: str,
        buffer_policy: BufferPolicy | None = None,
        backend: DeliveryBackend | None = None,
        audit_store: AuditStore | None = None,
    ) -> None:
        self.source_instance_id = source_instance_id
        self.buffer_policy = buffer_policy or BufferPolicy(mode="disabled", max_events=0)
        self.backend = backend
        self.audit_store = audit_store
        self._paused = False
        self._buffer: deque[EventEnvelope] = deque()
        self._subscriptions: dict[str, list[tuple[str, EventHandler]]] = defaultdict(list)
        self._id_counter = count(1)

    def subscribe(self, event_type: str, handler: EventHandler) -> Subscription:
        subscription_id = f"sub-{next(self._id_counter)}"
        self._subscriptions[event_type].append((subscription_id, handler))
        return Subscription(
            subscription_id=subscription_id,
            event_type=event_type,
            handler_name=getattr(handler, "__name__", repr(handler)),
        )

    def publish(self, envelope: EventEnvelope) -> DeliveryResult:
        audit_recorded = False
        if self.audit_store is not None:
            self.audit_store.record_publish_started(envelope)
            audit_recorded = True

        try:
            if self._paused:
                result = self._handle_buffered_publish(envelope, audit_recorded=audit_recorded)
            else:
                self._dispatch_local(envelope)
                if self.backend is not None:
                    self.backend.publish(envelope)
                result = DeliveryResult(
                    accepted=True,
                    delivery_mode="backend" if self.backend is not None else "local",
                    buffered=False,
                    audit_recorded=audit_recorded,
                )

            if self.audit_store is not None:
                self.audit_store.record_publish_completed(envelope, result)
            return result
        except Exception as exc:
            if self.audit_store is not None:
                self.audit_store.record_publish_failed(envelope, exc)
            raise EventDeliveryError(str(exc)) from exc

    def pause_delivery(self) -> None:
        self._paused = True

    def resume_delivery(self) -> None:
        self._paused = False

    def drain_buffer(self) -> int:
        if self._paused:
            return 0
        drained = 0
        while self._buffer:
            envelope = self._buffer.popleft()
            self._dispatch_local(envelope)
            if self.backend is not None:
                self.backend.publish(envelope)
            drained += 1
        return drained

    def handle_backend_envelope(self, envelope: EventEnvelope) -> bool:
        if envelope.source_instance_id == self.source_instance_id:
            return False
        self._dispatch_local(envelope)
        return True

    def _dispatch_local(self, envelope: EventEnvelope) -> None:
        handlers = list(self._subscriptions.get(envelope.event_type, []))
        for _, handler in handlers:
            try:
                handler(envelope)
            except Exception:
                continue

    def _handle_buffered_publish(self, envelope: EventEnvelope, *, audit_recorded: bool) -> DeliveryResult:
        if self.buffer_policy.mode == "disabled":
            return DeliveryResult(
                accepted=False,
                delivery_mode="paused",
                buffered=False,
                audit_recorded=audit_recorded,
                detail="delivery_paused",
            )
        if self.buffer_policy.max_events < 1:
            return DeliveryResult(
                accepted=False,
                delivery_mode="paused",
                buffered=False,
                audit_recorded=audit_recorded,
                detail="buffer_unavailable",
            )
        if len(self._buffer) >= self.buffer_policy.max_events:
            if self.buffer_policy.mode == "bounded_drop_new":
                return DeliveryResult(
                    accepted=False,
                    delivery_mode="buffer_drop_new",
                    buffered=False,
                    audit_recorded=audit_recorded,
                    detail="buffer_full",
                )
            if self.buffer_policy.mode == "bounded_drop_oldest":
                self._buffer.popleft()
            else:
                raise ValueError(f"Unsupported buffer mode: {self.buffer_policy.mode}")
        self._buffer.append(envelope)
        return DeliveryResult(
            accepted=True,
            delivery_mode="buffered",
            buffered=True,
            audit_recorded=audit_recorded,
        )
