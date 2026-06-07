from __future__ import annotations

from uuid import uuid4

from .models import (
    A2AEvent,
    A2AFrameworkConfig,
    AgentDescriptor,
    DeadLetterRecord,
    DelegationDecision,
    DelegationLease,
    DelegationRequest,
    RecoveryRecord,
    default_expiry,
    utcnow,
)
from .policies import (
    DefaultDeadLetterPolicy,
    DefaultHealthPolicy,
    DefaultRoutingPolicy,
    DefaultSelectionPolicy,
    DefaultWatchdogPolicy,
)
from .protocols import (
    AgentRegistry,
    DeadLetterPolicy,
    DeadLetterStore,
    HealthPolicy,
    LeaseStore,
    RoutingPolicy,
    SelectionPolicy,
    WatchdogPolicy,
)
from .stores import InMemoryAgentRegistry, InMemoryDeadLetterStore, InMemoryLeaseStore


class A2AFramework:
    def __init__(
        self,
        *,
        config: A2AFrameworkConfig | None = None,
        registry: AgentRegistry | None = None,
        lease_store: LeaseStore | None = None,
        dead_letter_store: DeadLetterStore | None = None,
        selection_policy: SelectionPolicy | None = None,
        routing_policy: RoutingPolicy | None = None,
        health_policy: HealthPolicy | None = None,
        dead_letter_policy: DeadLetterPolicy | None = None,
        watchdog_policy: WatchdogPolicy | None = None,
    ) -> None:
        self.config = config or A2AFrameworkConfig()
        self.registry = registry or InMemoryAgentRegistry()
        self.lease_store = lease_store or InMemoryLeaseStore()
        self.dead_letter_store = dead_letter_store or InMemoryDeadLetterStore()
        self.selection_policy = selection_policy or DefaultSelectionPolicy()
        self.routing_policy = routing_policy or DefaultRoutingPolicy()
        self.health_policy = health_policy or DefaultHealthPolicy()
        self.dead_letter_policy = dead_letter_policy or DefaultDeadLetterPolicy()
        self.watchdog_policy = watchdog_policy or DefaultWatchdogPolicy()
        self._events: list[A2AEvent] = []
        self._recoveries: list[RecoveryRecord] = []
        self._decision_fallbacks: dict[str, list[str]] = {}

    def register_agent(self, agent: AgentDescriptor) -> AgentDescriptor:
        saved = self.registry.upsert(agent)
        self._emit("a2a.agent.registered", task_id=agent.agent_id, payload={"agent_id": agent.agent_id})
        return saved

    def get_agent(self, agent_id: str) -> AgentDescriptor | None:
        return self.registry.get(agent_id)

    def list_agents(self) -> list[AgentDescriptor]:
        return self.registry.list_agents()

    def route_request(self, request: DelegationRequest) -> DelegationDecision:
        candidates = self._eligible_candidates(request)
        ranked = self.selection_policy.rank(candidates, request)
        decision = self.routing_policy.decide(ranked, request)
        self._decision_fallbacks[request.task_id] = list(decision.fallback_agent_ids)
        self._emit(
            "a2a.request.routed",
            task_id=request.task_id,
            payload={
                "selected_agent_id": decision.selected_agent_id,
                "decision_reason": decision.decision_reason,
                "fallback_agent_ids": decision.fallback_agent_ids,
            },
        )
        if decision.selected_agent_id is None:
            self._dead_letter(request, reason=decision.decision_reason, retry_count=0, last_agent_id=None)
        return decision

    def create_lease(self, request: DelegationRequest, decision: DelegationDecision) -> DelegationLease | None:
        if decision.selected_agent_id is None:
            return None
        lease = DelegationLease(
            lease_id=str(uuid4()),
            task_id=request.task_id,
            agent_id=decision.selected_agent_id,
            request=request,
            status="pending",
            expires_at=default_expiry(self.config.lease_ttl_seconds),
            claimed_at=None,
            completed_at=None,
            attempt_count=0,
        )
        self.lease_store.create(lease)
        self._emit(
            "a2a.lease.created",
            task_id=request.task_id,
            payload={"lease_id": lease.lease_id, "agent_id": lease.agent_id},
        )
        return lease

    def claim_lease(self, lease_id: str) -> DelegationLease:
        lease = self.lease_store.get(lease_id)
        assert lease is not None
        lease.status = "claimed"
        lease.claimed_at = utcnow()
        lease.attempt_count += 1
        self.lease_store.update(lease)
        self._emit(
            "a2a.lease.claimed",
            task_id=lease.task_id,
            payload={"lease_id": lease.lease_id, "agent_id": lease.agent_id},
        )
        return lease

    def record_result(self, lease_id: str, *, success: bool, error: str | None = None) -> DelegationLease | None:
        lease = self.lease_store.get(lease_id)
        assert lease is not None
        if success:
            lease.status = "completed"
            lease.completed_at = utcnow()
            self.lease_store.update(lease)
            self._emit(
                "a2a.lease.completed",
                task_id=lease.task_id,
                payload={"lease_id": lease.lease_id, "agent_id": lease.agent_id},
            )
            return lease

        fallback_agents = self._decision_fallbacks.get(lease.task_id, [])
        if fallback_agents and not self.dead_letter_policy.should_dead_letter(lease, error=error):
            rerouted_agent = fallback_agents.pop(0)
            self._decision_fallbacks[lease.task_id] = fallback_agents
            lease.agent_id = rerouted_agent
            lease.status = "pending"
            lease.claimed_at = None
            lease.expires_at = default_expiry(self.config.lease_ttl_seconds)
            self.lease_store.update(lease)
            self._emit(
                "a2a.lease.rerouted",
                task_id=lease.task_id,
                payload={
                    "lease_id": lease.lease_id,
                    "agent_id": rerouted_agent,
                    "error": error,
                },
            )
            return lease

        lease.status = "dead_lettered"
        self.lease_store.update(lease)
        self._dead_letter(
            lease.request,
            reason=error or "delegation_failed",
            retry_count=lease.attempt_count,
            last_agent_id=lease.agent_id,
        )
        self._emit(
            "a2a.lease.dead_lettered",
            task_id=lease.task_id,
            payload={"lease_id": lease.lease_id, "agent_id": lease.agent_id, "error": error},
        )
        return None

    def scan_stuck_delegations(self) -> list[RecoveryRecord]:
        now = utcnow()
        expired = self.watchdog_policy.detect_expired(self.lease_store.list_leases(), now=now)
        records: list[RecoveryRecord] = []
        for lease in expired:
            lease.status = "expired"
            self.lease_store.update(lease)
            action = "dead_letter"
            fallback_agents = self._decision_fallbacks.get(lease.task_id, [])
            if fallback_agents and not self.dead_letter_policy.should_dead_letter(lease, error="expired"):
                rerouted_agent = fallback_agents.pop(0)
                self._decision_fallbacks[lease.task_id] = fallback_agents
                lease.agent_id = rerouted_agent
                lease.status = "pending"
                lease.claimed_at = None
                lease.expires_at = default_expiry(self.config.lease_ttl_seconds)
                self.lease_store.update(lease)
                action = "reroute"
                self._emit(
                    "a2a.lease.rerouted",
                    task_id=lease.task_id,
                    payload={"lease_id": lease.lease_id, "agent_id": rerouted_agent, "error": "expired"},
                )
            else:
                self._dead_letter(
                    lease.request,
                    reason="expired",
                    retry_count=lease.attempt_count,
                    last_agent_id=lease.agent_id,
                )
                self._emit(
                    "a2a.lease.dead_lettered",
                    task_id=lease.task_id,
                    payload={"lease_id": lease.lease_id, "agent_id": lease.agent_id, "error": "expired"},
                )

            recovery = RecoveryRecord(
                task_id=lease.task_id,
                lease_id=lease.lease_id,
                reason="expired",
                action_taken=action,
                created_at=now,
            )
            self._recoveries.append(recovery)
            records.append(recovery)
            self._emit(
                "a2a.lease.recovered",
                task_id=lease.task_id,
                payload={"lease_id": lease.lease_id, "action_taken": action},
            )
        return records

    def list_dead_letters(self) -> list[DeadLetterRecord]:
        return self.dead_letter_store.list_records()

    def list_events(self) -> list[A2AEvent]:
        return list(self._events)

    def list_recoveries(self) -> list[RecoveryRecord]:
        return list(self._recoveries)

    def _eligible_candidates(self, request: DelegationRequest) -> list[AgentDescriptor]:
        required = set(request.required_capabilities)
        candidates: list[AgentDescriptor] = []
        for agent in self.registry.list_agents():
            capability_names = {capability.name for capability in agent.capabilities}
            if not required.issubset(capability_names):
                continue
            if request.preferred_mode not in agent.supported_modes:
                continue
            if not self.health_policy.is_routable(agent):
                continue
            candidates.append(agent)
        return candidates

    def _dead_letter(
        self,
        request: DelegationRequest,
        *,
        reason: str,
        retry_count: int,
        last_agent_id: str | None,
    ) -> DeadLetterRecord:
        record = DeadLetterRecord(
            task_id=request.task_id,
            request=request,
            reason=reason,
            retry_count=retry_count,
            last_agent_id=last_agent_id,
            created_at=utcnow(),
        )
        self.dead_letter_store.create(record)
        return record

    def _emit(self, event_type: str, *, task_id: str, payload: dict[str, object]) -> None:
        self._events.append(
            A2AEvent(
                event_id=str(uuid4()),
                event_type=event_type,
                task_id=task_id,
                payload=payload,
                created_at=utcnow(),
            )
        )
