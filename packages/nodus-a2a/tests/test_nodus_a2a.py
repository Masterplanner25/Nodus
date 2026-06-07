from __future__ import annotations

from datetime import timedelta

from nodus_a2a import (
    A2AFramework,
    A2AFrameworkConfig,
    AgentCapability,
    AgentDescriptor,
    AgentHealth,
    AgentLoad,
    DelegationRequest,
    utcnow,
)


def build_agent(
    agent_id: str,
    *,
    capabilities: list[str],
    status: str = "healthy",
    availability: float = 1.0,
    utilization_score: float = 0.1,
    active_tasks: int = 0,
    queue_depth: int = 0,
    supported_modes: list[str] | None = None,
) -> AgentDescriptor:
    return AgentDescriptor(
        agent_id=agent_id,
        agent_kind="worker",
        endpoint=f"https://{agent_id}.test",
        capabilities=[
            AgentCapability(
                name=name,
                version="1.0",
                cost_hint=1.0,
                risk_hint="low",
                max_concurrency=4,
            )
            for name in capabilities
        ],
        supported_modes=supported_modes or ["queued"],
        health=AgentHealth(
            status=status,
            heartbeat_at=utcnow(),
            error_rate=0.0,
            availability=availability,
        ),
        load=AgentLoad(
            active_tasks=active_tasks,
            queue_depth=queue_depth,
            utilization_score=utilization_score,
            updated_at=utcnow(),
        ),
    )


def build_request(task_id: str = "task-1") -> DelegationRequest:
    return DelegationRequest(
        task_id=task_id,
        objective="process document",
        required_capabilities=["extract.text"],
        preferred_mode="queued",
        trace_id="trace-1",
        correlation_id="corr-1",
        deadline_at=None,
        payload={"document_id": "doc-1"},
    )


def test_register_agent_and_lookup() -> None:
    framework = A2AFramework()
    agent = build_agent("agent-a", capabilities=["extract.text"])
    framework.register_agent(agent)
    assert framework.get_agent("agent-a") == agent


def test_load_aware_selection_prefers_less_loaded_agent() -> None:
    framework = A2AFramework()
    framework.register_agent(build_agent("agent-a", capabilities=["extract.text"], utilization_score=0.8))
    framework.register_agent(build_agent("agent-b", capabilities=["extract.text"], utilization_score=0.2))
    decision = framework.route_request(build_request())
    assert decision.selected_agent_id == "agent-b"
    assert decision.fallback_agent_ids == ["agent-a"]


def test_unhealthy_agent_is_not_routable() -> None:
    framework = A2AFramework()
    framework.register_agent(build_agent("agent-a", capabilities=["extract.text"], status="degraded", availability=1.0))
    framework.register_agent(build_agent("agent-b", capabilities=["extract.text"], utilization_score=0.2))
    decision = framework.route_request(build_request())
    assert decision.selected_agent_id == "agent-b"


def test_no_candidate_routes_to_dead_letter() -> None:
    framework = A2AFramework()
    decision = framework.route_request(build_request())
    assert decision.selected_agent_id is None
    assert framework.list_dead_letters()[0].reason == "no_routable_agent"


def test_lease_claim_and_complete_lifecycle() -> None:
    framework = A2AFramework()
    framework.register_agent(build_agent("agent-a", capabilities=["extract.text"]))
    decision = framework.route_request(build_request())
    lease = framework.create_lease(build_request(), decision)
    assert lease is not None
    claimed = framework.claim_lease(lease.lease_id)
    assert claimed.status == "claimed"
    completed = framework.record_result(lease.lease_id, success=True)
    assert completed is not None
    assert completed.status == "completed"


def test_failure_reroutes_to_fallback_agent() -> None:
    framework = A2AFramework()
    framework.register_agent(build_agent("agent-a", capabilities=["extract.text"], utilization_score=0.1))
    framework.register_agent(build_agent("agent-b", capabilities=["extract.text"], utilization_score=0.3))
    request = build_request()
    decision = framework.route_request(request)
    lease = framework.create_lease(request, decision)
    assert lease is not None
    framework.claim_lease(lease.lease_id)
    rerouted = framework.record_result(lease.lease_id, success=False, error="temporary_failure")
    assert rerouted is not None
    assert rerouted.agent_id == "agent-b"
    assert rerouted.status == "pending"


def test_terminal_failure_dead_letters_request() -> None:
    framework = A2AFramework()
    framework.register_agent(build_agent("agent-a", capabilities=["extract.text"]))
    request = build_request()
    decision = framework.route_request(request)
    lease = framework.create_lease(request, decision)
    assert lease is not None
    framework.claim_lease(lease.lease_id)
    framework.claim_lease(lease.lease_id)
    outcome = framework.record_result(lease.lease_id, success=False, error="terminal_failure")
    assert outcome is None
    assert framework.list_dead_letters()[0].reason == "terminal_failure"


def test_watchdog_detects_expired_lease_and_records_recovery() -> None:
    framework = A2AFramework(config=A2AFrameworkConfig(lease_ttl_seconds=1))
    framework.register_agent(build_agent("agent-a", capabilities=["extract.text"], utilization_score=0.1))
    framework.register_agent(build_agent("agent-b", capabilities=["extract.text"], utilization_score=0.3))
    request = build_request()
    decision = framework.route_request(request)
    lease = framework.create_lease(request, decision)
    assert lease is not None
    framework.claim_lease(lease.lease_id)
    lease.expires_at = utcnow() - timedelta(seconds=1)
    recoveries = framework.scan_stuck_delegations()
    assert recoveries[0].action_taken == "reroute"
    updated = framework.lease_store.get(lease.lease_id)
    assert updated is not None
    assert updated.agent_id == "agent-b"


def test_event_timeline_contains_coordination_entries() -> None:
    framework = A2AFramework()
    framework.register_agent(build_agent("agent-a", capabilities=["extract.text"]))
    request = build_request()
    decision = framework.route_request(request)
    lease = framework.create_lease(request, decision)
    assert lease is not None
    framework.claim_lease(lease.lease_id)
    framework.record_result(lease.lease_id, success=True)
    event_types = [event.event_type for event in framework.list_events()]
    assert "a2a.agent.registered" in event_types
    assert "a2a.request.routed" in event_types
    assert "a2a.lease.created" in event_types
    assert "a2a.lease.claimed" in event_types
    assert "a2a.lease.completed" in event_types
