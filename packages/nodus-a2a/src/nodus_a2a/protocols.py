from __future__ import annotations

from datetime import datetime
from typing import Protocol

from .models import (
    AgentDescriptor,
    DeadLetterRecord,
    DelegationDecision,
    DelegationLease,
    DelegationRequest,
)


class AgentRegistry(Protocol):
    def upsert(self, agent: AgentDescriptor) -> AgentDescriptor: ...

    def get(self, agent_id: str) -> AgentDescriptor | None: ...

    def list_agents(self) -> list[AgentDescriptor]: ...


class LeaseStore(Protocol):
    def create(self, lease: DelegationLease) -> DelegationLease: ...

    def update(self, lease: DelegationLease) -> DelegationLease: ...

    def get(self, lease_id: str) -> DelegationLease | None: ...

    def list_leases(self) -> list[DelegationLease]: ...


class DeadLetterStore(Protocol):
    def create(self, record: DeadLetterRecord) -> DeadLetterRecord: ...

    def list_records(self) -> list[DeadLetterRecord]: ...


class SelectionPolicy(Protocol):
    def rank(self, candidates: list[AgentDescriptor], request: DelegationRequest) -> list[AgentDescriptor]: ...


class RoutingPolicy(Protocol):
    def decide(self, candidates: list[AgentDescriptor], request: DelegationRequest) -> DelegationDecision: ...


class HealthPolicy(Protocol):
    def is_routable(self, agent: AgentDescriptor) -> bool: ...


class DeadLetterPolicy(Protocol):
    def should_dead_letter(self, lease: DelegationLease, *, error: str | None = None) -> bool: ...


class WatchdogPolicy(Protocol):
    def detect_expired(self, leases: list[DelegationLease], *, now: datetime) -> list[DelegationLease]: ...
