from __future__ import annotations

from .models import AgentDescriptor, DeadLetterRecord, DelegationLease


class InMemoryAgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, AgentDescriptor] = {}

    def upsert(self, agent: AgentDescriptor) -> AgentDescriptor:
        self._agents[agent.agent_id] = agent
        return agent

    def get(self, agent_id: str) -> AgentDescriptor | None:
        return self._agents.get(agent_id)

    def list_agents(self) -> list[AgentDescriptor]:
        return list(self._agents.values())


class InMemoryLeaseStore:
    def __init__(self) -> None:
        self._leases: dict[str, DelegationLease] = {}

    def create(self, lease: DelegationLease) -> DelegationLease:
        self._leases[lease.lease_id] = lease
        return lease

    def update(self, lease: DelegationLease) -> DelegationLease:
        self._leases[lease.lease_id] = lease
        return lease

    def get(self, lease_id: str) -> DelegationLease | None:
        return self._leases.get(lease_id)

    def list_leases(self) -> list[DelegationLease]:
        return list(self._leases.values())


class InMemoryDeadLetterStore:
    def __init__(self) -> None:
        self._records: list[DeadLetterRecord] = []

    def create(self, record: DeadLetterRecord) -> DeadLetterRecord:
        self._records.append(record)
        return record

    def list_records(self) -> list[DeadLetterRecord]:
        return list(self._records)
