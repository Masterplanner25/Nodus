from __future__ import annotations

from dataclasses import replace

from .models import EventCause, EventEnvelope, WebhookSubscription


class DefaultHandlerPolicy:
    def should_continue_after_error(self, *, event_type: str, handler_name: str, error: Exception) -> bool:
        _ = event_type
        _ = handler_name
        _ = error
        return True


class DefaultDeliveryPolicy:
    def __init__(self, *, publish_distributed: bool = True, dispatch_webhooks: bool = True) -> None:
        self.publish_distributed = publish_distributed
        self.dispatch_webhooks = dispatch_webhooks

    def should_publish_distributed(self, envelope: EventEnvelope) -> bool:
        _ = envelope
        return self.publish_distributed

    def should_dispatch_webhooks(self, envelope: EventEnvelope) -> bool:
        _ = envelope
        return self.dispatch_webhooks


class DefaultWebhookPolicy:
    def build_headers(self, subscription: WebhookSubscription, envelope: EventEnvelope) -> dict[str, str]:
        headers = dict(subscription.headers)
        headers.setdefault("x-nodus-event-id", envelope.event_id)
        headers.setdefault("x-nodus-event-type", envelope.event_type)
        if subscription.secret:
            headers.setdefault("x-nodus-signature", subscription.secret)
        return headers


class DefaultCausalityPolicy:
    def attach(self, envelope: EventEnvelope, *, cause: EventCause | None) -> EventEnvelope:
        if cause is None:
            return envelope
        return replace(envelope, cause_chain=[*envelope.cause_chain, cause])
