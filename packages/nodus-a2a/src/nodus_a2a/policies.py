from __future__ import annotations

from datetime import datetime

from .models import AgentDescriptor, DelegationDecision, DelegationLease, DelegationRequest


class DefaultSelectionPolicy:
    def rank(self, candidates: list[AgentDescriptor], request: DelegationRequest) -> list[AgentDescriptor]:
        _ = request
        return sorted(
            candidates,
            key=lambda agent: (
                agent.load.utilization_score,
                agent.load.active_tasks,
                agent.load.queue_depth,
                -agent.health.availability,
                agent.agent_id,
            ),
        )


class DefaultRoutingPolicy:
    def decide(self, candidates: list[AgentDescriptor], request: DelegationRequest) -> DelegationDecision:
        if not candidates:
            return DelegationDecision(
                task_id=request.task_id,
                selected_agent_id=None,
                routing_mode=request.preferred_mode,
                decision_reason="no_routable_agent",
                fallback_agent_ids=[],
            )
        selected = candidates[0]
        return DelegationDecision(
            task_id=request.task_id,
            selected_agent_id=selected.agent_id,
            routing_mode=request.preferred_mode,
            decision_reason="selected_lowest_load_healthy_agent",
            fallback_agent_ids=[agent.agent_id for agent in candidates[1:]],
        )


class DefaultHealthPolicy:
    def is_routable(self, agent: AgentDescriptor) -> bool:
        return agent.health.status == "healthy" and agent.health.availability > 0.0


class DefaultDeadLetterPolicy:
    def should_dead_letter(self, lease: DelegationLease, *, error: str | None = None) -> bool:
        _ = error
        return lease.attempt_count >= 2


class DefaultWatchdogPolicy:
    def detect_expired(self, leases: list[DelegationLease], *, now: datetime) -> list[DelegationLease]:
        return [
            lease
            for lease in leases
            if lease.status in {"pending", "claimed"} and lease.expires_at <= now
        ]
