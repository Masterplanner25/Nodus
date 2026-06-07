from __future__ import annotations

import asyncio
import fnmatch
import inspect
from collections import defaultdict
from uuid import uuid4

from .audit import InMemoryAuditStore, InMemoryWebhookDispatcher
from .models import (
    EventAuditRecord,
    EventCause,
    EventEnvelope,
    EventReplayRequest,
    EventReplayResult,
    EventRoute,
    WebhookSubscription,
    utcnow,
)
from .policies import (
    DefaultCausalityPolicy,
    DefaultDeliveryPolicy,
    DefaultHandlerPolicy,
    DefaultWebhookPolicy,
)
from .protocols import (
    AuditStore,
    CausalityPolicy,
    DeliveryPolicy,
    DistributedEventPublisher,
    EventHandler,
    HandlerPolicy,
    WebhookDispatcher,
    WebhookPolicy,
)


class EventFramework:
    def __init__(
        self,
        *,
        source_instance_id: str = "local",
        audit_store: AuditStore | None = None,
        handler_policy: HandlerPolicy | None = None,
        delivery_policy: DeliveryPolicy | None = None,
        causality_policy: CausalityPolicy | None = None,
        webhook_policy: WebhookPolicy | None = None,
        distributed_publisher: DistributedEventPublisher | None = None,
        webhook_dispatcher: WebhookDispatcher | None = None,
    ) -> None:
        self.source_instance_id = source_instance_id
        self.audit_store = audit_store or InMemoryAuditStore()
        self.handler_policy = handler_policy or DefaultHandlerPolicy()
        self.delivery_policy = delivery_policy or DefaultDeliveryPolicy()
        self.causality_policy = causality_policy or DefaultCausalityPolicy()
        self.webhook_policy = webhook_policy or DefaultWebhookPolicy()
        self.distributed_publisher = distributed_publisher
        self.webhook_dispatcher = webhook_dispatcher or InMemoryWebhookDispatcher()
        self._handlers: dict[str, list[tuple[str, EventHandler]]] = defaultdict(list)
        self._webhooks: dict[str, WebhookSubscription] = {}
        self._routes: list[EventRoute] = []

    def subscribe(self, event_pattern: str, handler: EventHandler, *, handler_name: str | None = None) -> EventRoute:
        return self.register_handler(event_pattern, handler, handler_name=handler_name)

    def register_handler(
        self,
        event_pattern: str,
        handler: EventHandler,
        *,
        handler_name: str | None = None,
    ) -> EventRoute:
        name = handler_name or getattr(handler, "__name__", "handler")
        self._handlers[event_pattern].append((name, handler))
        route = EventRoute(
            route_id=str(uuid4()),
            event_pattern=event_pattern,
            target_kind="handler",
            delivery_mode="local",
        )
        self._routes.append(route)
        return route

    def register_webhook(self, subscription: WebhookSubscription) -> EventRoute:
        self._webhooks[subscription.subscription_id] = subscription
        route = EventRoute(
            route_id=str(uuid4()),
            event_pattern=subscription.event_pattern,
            target_kind="webhook",
            delivery_mode="webhook",
            metadata={"subscription_id": subscription.subscription_id},
        )
        self._routes.append(route)
        return route

    def publish(
        self,
        event_type: str,
        payload: object,
        *,
        trace_id: str | None = None,
        correlation_id: str | None = None,
        cause: EventCause | None = None,
        metadata: dict[str, object] | None = None,
        do_not_replay: bool = False,
    ) -> EventAuditRecord:
        return asyncio.run(
            self.apublish(
                event_type,
                payload,
                trace_id=trace_id,
                correlation_id=correlation_id,
                cause=cause,
                metadata=metadata,
                do_not_replay=do_not_replay,
            )
        )

    async def apublish(
        self,
        event_type: str,
        payload: object,
        *,
        trace_id: str | None = None,
        correlation_id: str | None = None,
        cause: EventCause | None = None,
        metadata: dict[str, object] | None = None,
        do_not_replay: bool = False,
    ) -> EventAuditRecord:
        envelope = EventEnvelope(
            event_id=str(uuid4()),
            event_type=event_type,
            payload=payload,
            timestamp=utcnow(),
            source_instance_id=self.source_instance_id,
            trace_id=trace_id,
            correlation_id=correlation_id,
            metadata=metadata or {},
            do_not_replay=do_not_replay,
        )
        envelope = self.causality_policy.attach(envelope, cause=cause)
        record = self.audit_store.create_record(
            EventAuditRecord(
                event_id=envelope.event_id,
                envelope=envelope,
                published_at=envelope.timestamp,
            )
        )

        if self.distributed_publisher is not None and self.delivery_policy.should_publish_distributed(envelope):
            record.distributed_outcome = self.distributed_publisher.publish(envelope)

        record.handler_outcomes.extend(await self._dispatch_handlers(envelope))
        if self.delivery_policy.should_dispatch_webhooks(envelope):
            record.webhook_outcomes.extend(await self._dispatch_webhooks(envelope))
        record.completed = True
        return self.audit_store.update_record(record)

    def replay(self, request: EventReplayRequest) -> EventReplayResult:
        return asyncio.run(self.areplay(request))

    async def areplay(self, request: EventReplayRequest) -> EventReplayResult:
        matched = [
            record
            for record in self.audit_store.list_records()
            if self._matches_replay(record.envelope, request)
        ]
        handler_invocations = 0
        webhook_invocations = 0
        replayed_ids: list[str] = []

        for record in matched:
            record.replay_count += 1
            replayed_ids.append(record.event_id)
            if request.replay_mode in {"full", "handlers"}:
                outcomes = await self._dispatch_handlers(record.envelope)
                record.handler_outcomes.extend(outcomes)
                handler_invocations += len(outcomes)
            if request.replay_mode in {"full", "webhooks"}:
                outcomes = await self._dispatch_webhooks(record.envelope)
                record.webhook_outcomes.extend(outcomes)
                webhook_invocations += len(outcomes)
            self.audit_store.update_record(record)

        return EventReplayResult(
            events_replayed=len(matched),
            handler_invocations=handler_invocations,
            webhook_invocations=webhook_invocations,
            event_ids=replayed_ids,
        )

    def list_records(self) -> list[EventAuditRecord]:
        return self.audit_store.list_records()

    def list_routes(self) -> list[EventRoute]:
        return list(self._routes)

    async def _dispatch_handlers(self, envelope: EventEnvelope) -> list[dict[str, object]]:
        outcomes: list[dict[str, object]] = []
        for pattern, handlers in self._handlers.items():
            if not _matches_pattern(envelope.event_type, pattern):
                continue
            for handler_name, handler in handlers:
                try:
                    result = handler(envelope)
                    if inspect.isawaitable(result):
                        result = await result
                    outcomes.append(
                        {
                            "handler_name": handler_name,
                            "event_type": envelope.event_type,
                            "accepted": True,
                            "result": result,
                        }
                    )
                except Exception as exc:
                    outcomes.append(
                        {
                            "handler_name": handler_name,
                            "event_type": envelope.event_type,
                            "accepted": False,
                            "error": str(exc),
                        }
                    )
                    if not self.handler_policy.should_continue_after_error(
                        event_type=envelope.event_type,
                        handler_name=handler_name,
                        error=exc,
                    ):
                        return outcomes
        return outcomes

    async def _dispatch_webhooks(self, envelope: EventEnvelope) -> list[dict[str, object]]:
        outcomes: list[dict[str, object]] = []
        for subscription in self._webhooks.values():
            if not subscription.enabled:
                continue
            if not _matches_pattern(envelope.event_type, subscription.event_pattern):
                continue
            headers = self.webhook_policy.build_headers(subscription, envelope)
            result = self.webhook_dispatcher.dispatch(subscription, envelope, headers)
            if inspect.isawaitable(result):
                result = await result
            outcome = dict(result)
            outcome.setdefault("subscription_id", subscription.subscription_id)
            outcomes.append(outcome)
        return outcomes

    @staticmethod
    def _matches_replay(envelope: EventEnvelope, request: EventReplayRequest) -> bool:
        if envelope.do_not_replay and not request.include_do_not_replay:
            return False
        if request.event_types and envelope.event_type not in request.event_types:
            return False
        if request.correlation_id and envelope.correlation_id != request.correlation_id:
            return False
        if request.trace_id and envelope.trace_id != request.trace_id:
            return False
        return True


def _matches_pattern(event_type: str, pattern: str) -> bool:
    return fnmatch.fnmatchcase(event_type, pattern)
