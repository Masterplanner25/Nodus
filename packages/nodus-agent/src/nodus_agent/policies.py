from __future__ import annotations

from typing import Protocol

from .models import AgentPlan, AgentRun


class PlannerBackend(Protocol):
    def plan(self, objective: str, *, user_id: str, available_tools: list[dict[str, object]]) -> AgentPlan: ...


class ApprovalPolicy(Protocol):
    def requires_approval(self, plan: AgentPlan, *, user_id: str) -> bool: ...


class CapabilityPolicy(Protocol):
    def mint(self, plan: AgentPlan, *, user_id: str) -> dict[str, object]: ...

    def check(self, tool_name: str, capability_token: dict[str, object] | None) -> bool: ...


class DelegationPolicy(Protocol):
    def allow(
        self,
        parent_run: AgentRun,
        *,
        target_agent: str,
        ancestor_chain: list[str],
    ) -> tuple[bool, str | None]: ...


class RecoveryPolicy(Protocol):
    def can_recover(self, run: AgentRun) -> bool: ...


class RuntimeLocalPlanner:
    name = "runtime_local"

    def plan(self, objective: str, *, user_id: str, available_tools: list[dict[str, object]]) -> AgentPlan:
        _ = user_id
        if not available_tools:
            raise ValueError("RuntimeLocalPlanner requires at least one registered tool.")
        first = available_tools[0]
        return AgentPlan(
            executive_summary=f"Execute a minimal plan for: {objective}",
            steps=[
                __import__("nodus_agent.models").models.AgentPlanStep(
                    tool_name=str(first["name"]),
                    args={"objective": objective},
                    risk_level=str(first["risk_level"]),
                    description=f"Run {first['name']} against the requested objective.",
                )
            ],
            overall_risk=str(first["risk_level"]),
            planner_name=self.name,
            planner_metadata={},
        )


class DefaultApprovalPolicy:
    def requires_approval(self, plan: AgentPlan, *, user_id: str) -> bool:
        _ = user_id
        return plan.overall_risk in {"medium", "high"}


class DefaultCapabilityPolicy:
    def mint(self, plan: AgentPlan, *, user_id: str) -> dict[str, object]:
        _ = user_id
        return {
            "allowed_tools": [step.tool_name for step in plan.steps],
        }

    def check(self, tool_name: str, capability_token: dict[str, object] | None) -> bool:
        if capability_token is None:
            return False
        allowed = capability_token.get("allowed_tools") or []
        return tool_name in allowed


class DefaultDelegationPolicy:
    def __init__(self, *, max_depth: int = 3) -> None:
        self.max_depth = max_depth

    def allow(
        self,
        parent_run: AgentRun,
        *,
        target_agent: str,
        ancestor_chain: list[str],
    ) -> tuple[bool, str | None]:
        if target_agent in ancestor_chain:
            return False, "delegation_loop_detected"
        if len(ancestor_chain) >= self.max_depth:
            return False, "delegation_depth_exceeded"
        _ = parent_run
        return True, None


class DefaultRecoveryPolicy:
    def can_recover(self, run: AgentRun) -> bool:
        return run.status == "stuck"
