from __future__ import annotations

from uuid import uuid4

from .errors import ApprovalRequiredError, CapabilityViolationError, DelegationBlockedError
from .models import AgentEvent, AgentFrameworkConfig, AgentPlan, AgentRun, utcnow
from .policies import (
    ApprovalPolicy,
    CapabilityPolicy,
    DefaultApprovalPolicy,
    DefaultCapabilityPolicy,
    DefaultDelegationPolicy,
    DefaultRecoveryPolicy,
    DelegationPolicy,
    PlannerBackend,
    RecoveryPolicy,
    RuntimeLocalPlanner,
)
from .registry import ToolRegistry


class AgentFramework:
    def __init__(
        self,
        *,
        config: AgentFrameworkConfig | None = None,
        planner: PlannerBackend | None = None,
        tools: ToolRegistry | None = None,
        approval_policy: ApprovalPolicy | None = None,
        capability_policy: CapabilityPolicy | None = None,
        delegation_policy: DelegationPolicy | None = None,
        recovery_policy: RecoveryPolicy | None = None,
    ) -> None:
        self.config = config or AgentFrameworkConfig()
        self.planner = planner or RuntimeLocalPlanner()
        self.tools = tools or ToolRegistry()
        self.approval_policy = approval_policy or DefaultApprovalPolicy()
        self.capability_policy = capability_policy or DefaultCapabilityPolicy()
        self.delegation_policy = delegation_policy or DefaultDelegationPolicy(
            max_depth=self.config.max_delegation_depth
        )
        self.recovery_policy = recovery_policy or DefaultRecoveryPolicy()
        self._runs: dict[str, AgentRun] = {}
        self._events: list[AgentEvent] = []
        self._ancestor_chains: dict[str, list[str]] = {}

    def create_run(self, *, objective: str, user_id: str, trace_id: str | None = None) -> AgentRun:
        plan = self._validate_plan(self.planner.plan(objective, user_id=user_id, available_tools=self.tools.list_tools()))
        now = utcnow()
        status = "pending_approval" if self.approval_policy.requires_approval(plan, user_id=user_id) else "approved"
        run = AgentRun(
            run_id=str(uuid4()),
            objective=objective,
            user_id=user_id,
            status=status,
            plan=plan,
            capability_token=None,
            trace_id=trace_id,
            correlation_id=trace_id,
            parent_run_id=None,
            delegated_to=None,
            steps_completed=0,
            created_at=now,
            updated_at=now,
        )
        self._runs[run.run_id] = run
        self._ancestor_chains[run.run_id] = [run.run_id]
        self._emit(run.run_id, "agent.run.created", {"status": status})
        return run

    def approve_run(self, run_id: str) -> AgentRun:
        run = self._runs[run_id]
        run.status = "approved"
        run.capability_token = self.capability_policy.mint(run.plan, user_id=run.user_id)
        run.updated_at = utcnow()
        self._emit(run.run_id, "agent.run.approved", {})
        return run

    def reject_run(self, run_id: str, *, reason: str) -> AgentRun:
        run = self._runs[run_id]
        run.status = "rejected"
        run.error = reason
        run.completed_at = utcnow()
        run.updated_at = run.completed_at
        self._emit(run.run_id, "agent.run.rejected", {"reason": reason})
        return run

    def execute_run(self, run_id: str) -> AgentRun:
        run = self._runs[run_id]
        if run.status == "pending_approval":
            raise ApprovalRequiredError(f"Run {run_id!r} requires approval.")
        if run.status not in {"approved", "stuck"}:
            return run
        if run.capability_token is None:
            run.capability_token = self.capability_policy.mint(run.plan, user_id=run.user_id)

        run.status = "executing"
        run.started_at = run.started_at or utcnow()
        run.updated_at = utcnow()
        self._emit(run.run_id, "agent.run.started", {})

        for index in range(run.steps_completed, len(run.plan.steps)):
            step = run.plan.steps[index]
            self._emit(run.run_id, "agent.step.started", {"index": index, "tool_name": step.tool_name})
            if not self.capability_policy.check(step.tool_name, run.capability_token):
                run.status = "failed"
                run.error = f"capability_denied:{step.tool_name}"
                run.completed_at = utcnow()
                run.updated_at = run.completed_at
                self._emit(run.run_id, "agent.step.failed", {"index": index, "tool_name": step.tool_name})
                self._emit(run.run_id, "agent.run.failed", {"error": run.error})
                raise CapabilityViolationError(run.error)

            handler = self.tools.resolve(step.tool_name)
            try:
                result = handler(step.args)
            except Exception as exc:
                run.status = "failed"
                run.error = str(exc)
                run.completed_at = utcnow()
                run.updated_at = run.completed_at
                self._emit(run.run_id, "agent.step.failed", {"index": index, "tool_name": step.tool_name})
                self._emit(run.run_id, "agent.run.failed", {"error": run.error})
                return run

            run.steps_completed = index + 1
            run.result = run.result or {"steps": []}
            step_results = run.result.setdefault("steps", [])
            if isinstance(step_results, list):
                step_results.append({"tool_name": step.tool_name, "result": result})
            run.updated_at = utcnow()
            self._emit(run.run_id, "agent.step.completed", {"index": index, "tool_name": step.tool_name})

        run.status = "completed"
        run.completed_at = utcnow()
        run.updated_at = run.completed_at
        self._emit(run.run_id, "agent.run.completed", {})
        return run

    def delegate_run(self, run_id: str, *, target_agent: str) -> AgentRun:
        parent = self._runs[run_id]
        ancestor_chain = list(self._ancestor_chains.get(run_id, [run_id]))
        allowed, reason = self.delegation_policy.allow(
            parent,
            target_agent=target_agent,
            ancestor_chain=ancestor_chain,
        )
        if not allowed:
            raise DelegationBlockedError(reason or "delegation_blocked")
        child = self.create_run(objective=parent.objective, user_id=parent.user_id, trace_id=parent.trace_id)
        child.parent_run_id = parent.run_id
        child.delegated_to = target_agent
        self._ancestor_chains[child.run_id] = ancestor_chain + [target_agent]
        parent.status = "delegated"
        parent.delegated_to = target_agent
        parent.updated_at = utcnow()
        self._emit(parent.run_id, "agent.run.delegated", {"child_run_id": child.run_id, "target_agent": target_agent})
        return child

    def mark_stuck(self, run_id: str) -> AgentRun:
        run = self._runs[run_id]
        run.status = "stuck"
        run.updated_at = utcnow()
        self._emit(run.run_id, "agent.run.stuck", {})
        return run

    def recover_run(self, run_id: str) -> AgentRun:
        run = self._runs[run_id]
        if not self.recovery_policy.can_recover(run):
            return run
        self._emit(run.run_id, "agent.run.recovered", {"steps_completed": run.steps_completed})
        return self.execute_run(run_id)

    def replay_run(self, run_id: str) -> AgentRun:
        source = self._runs[run_id]
        now = utcnow()
        replay = AgentRun(
            run_id=str(uuid4()),
            objective=source.objective,
            user_id=source.user_id,
            status="pending",
            plan=source.plan,
            capability_token=None,
            trace_id=source.trace_id,
            correlation_id=source.correlation_id,
            parent_run_id=source.run_id,
            delegated_to=None,
            steps_completed=0,
            created_at=now,
            updated_at=now,
        )
        self._runs[replay.run_id] = replay
        self._ancestor_chains[replay.run_id] = [replay.run_id]
        self._emit(replay.run_id, "agent.run.replayed", {"source_run_id": source.run_id})
        return replay

    def get_run(self, run_id: str) -> AgentRun | None:
        return self._runs.get(run_id)

    def list_events(self, run_id: str) -> list[AgentEvent]:
        return [event for event in self._events if event.run_id == run_id]

    def _emit(self, run_id: str, event_type: str, payload: dict[str, object]) -> None:
        self._events.append(
            AgentEvent(
                event_id=str(uuid4()),
                run_id=run_id,
                event_type=event_type,
                payload=payload,
                created_at=utcnow(),
            )
        )

    @staticmethod
    def _validate_plan(plan: AgentPlan) -> AgentPlan:
        if not plan.steps:
            raise ValueError("AgentPlan must contain at least one step.")
        if plan.overall_risk not in {"low", "medium", "high"}:
            raise ValueError("AgentPlan.overall_risk must be low, medium, or high.")
        for step in plan.steps:
            if step.risk_level not in {"low", "medium", "high"}:
                raise ValueError("AgentPlanStep.risk_level must be low, medium, or high.")
        return plan
