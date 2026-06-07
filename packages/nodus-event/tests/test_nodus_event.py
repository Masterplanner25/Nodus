from __future__ import annotations

from nodus_event import EventCause, EventFramework, EventReplayRequest, WebhookSubscription


class StubDistributedPublisher:
    def __init__(self) -> None:
        self.envelopes = []

    def publish(self, envelope):
        self.envelopes.append(envelope)
        return {"accepted": True, "delivery_mode": "distributed"}


def test_local_handler_dispatch() -> None:
    framework = EventFramework()
    seen: list[str] = []

    def handler(envelope) -> dict[str, object]:
        seen.append(envelope.event_id)
        return {"ok": True}

    framework.register_handler("agent.run.completed", handler)
    record = framework.publish("agent.run.completed", {"run_id": "r1"})
    assert seen == [record.event_id]
    assert record.handler_outcomes[0]["accepted"] is True


def test_sync_and_async_handlers_both_run() -> None:
    framework = EventFramework()
    calls: list[str] = []

    def sync_handler(envelope) -> str:
        calls.append(f"sync:{envelope.event_type}")
        return "sync"

    async def async_handler(envelope) -> str:
        calls.append(f"async:{envelope.event_type}")
        return "async"

    framework.register_handler("agent.run.*", sync_handler)
    framework.register_handler("agent.run.*", async_handler)
    record = framework.publish("agent.run.started", {"run_id": "r1"})
    assert len(record.handler_outcomes) == 2
    assert calls == ["sync:agent.run.started", "async:agent.run.started"]


def test_handler_failure_does_not_block_other_handlers() -> None:
    framework = EventFramework()
    seen: list[str] = []

    def broken_handler(envelope) -> None:
        _ = envelope
        raise RuntimeError("boom")

    def healthy_handler(envelope) -> str:
        seen.append(envelope.event_type)
        return "ok"

    framework.register_handler("agent.run.*", broken_handler)
    framework.register_handler("agent.run.*", healthy_handler)
    record = framework.publish("agent.run.failed", {"run_id": "r1"})
    assert len(record.handler_outcomes) == 2
    assert any(outcome["accepted"] is False for outcome in record.handler_outcomes)
    assert seen == ["agent.run.failed"]


def test_distributed_publisher_is_invoked_when_configured() -> None:
    publisher = StubDistributedPublisher()
    framework = EventFramework(distributed_publisher=publisher)
    record = framework.publish("runtime.event", {"value": 1})
    assert len(publisher.envelopes) == 1
    assert record.distributed_outcome == {"accepted": True, "delivery_mode": "distributed"}


def test_webhook_subscription_dispatches_with_headers() -> None:
    framework = EventFramework()
    framework.register_webhook(
        WebhookSubscription(
            subscription_id="wh1",
            event_pattern="agent.run.*",
            target_url="https://example.test/webhook",
            secret="secret-token",
            headers={"x-custom": "1"},
        )
    )
    record = framework.publish("agent.run.completed", {"run_id": "r1"})
    outcome = record.webhook_outcomes[0]
    assert outcome["subscription_id"] == "wh1"
    assert outcome["headers"]["x-custom"] == "1"
    assert outcome["headers"]["x-nodus-signature"] == "secret-token"


def test_causal_chain_is_attached_to_child_event() -> None:
    framework = EventFramework()
    cause = EventCause(
        parent_event_id="parent-event",
        parent_run_id="run-1",
        parent_step_id="step-2",
        relationship_type="child-of",
    )
    record = framework.publish(
        "agent.step.completed",
        {"step": 2},
        trace_id="trace-1",
        correlation_id="corr-1",
        cause=cause,
    )
    assert record.envelope.cause_chain == [cause]


def test_replay_by_correlation_id_reinvokes_handlers() -> None:
    framework = EventFramework()
    calls: list[str] = []

    def handler(envelope) -> str:
        calls.append(envelope.correlation_id or "")
        return "ok"

    framework.register_handler("agent.run.completed", handler)
    framework.publish("agent.run.completed", {"run_id": "r1"}, correlation_id="corr-1")
    framework.publish("agent.run.completed", {"run_id": "r2"}, correlation_id="corr-2")
    result = framework.replay(EventReplayRequest(correlation_id="corr-1", replay_mode="handlers"))
    assert result.events_replayed == 1
    assert result.handler_invocations == 1
    assert calls == ["corr-1", "corr-2", "corr-1"]


def test_replay_respects_do_not_replay_by_default() -> None:
    framework = EventFramework()
    framework.publish("secret.event", {"value": 1}, correlation_id="corr-1", do_not_replay=True)
    result = framework.replay(EventReplayRequest(correlation_id="corr-1"))
    assert result.events_replayed == 0
