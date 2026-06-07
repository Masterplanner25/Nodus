from __future__ import annotations

import pytest

from nodus_agent import (
    AgentFramework,
    AgentFrameworkConfig,
    AgentPlan,
    AgentPlanStep,
    ApprovalRequiredError,
    CapabilityViolationError,
    DelegationBlockedError,
    RuntimeLocalPlanner,
    ToolRegistry,
)


def build_tools() -> ToolRegistry:
    tools = ToolRegistry()
    tools.register(
        name="task.echo",
        description="echo task",
        risk_level="low",
        required_capability="task.echo",
        handler=lambda args: {"echo": args["objective"]},
    )
    return tools


def test_create_run_requires_approval_for_medium_plan() -> None:
    class Planner(RuntimeLocalPlanner):
        def plan(self, objective, *, user_id, available_tools):
            _ = objective
            _ = user_id
            _ = available_tools
            return AgentPlan(
                executive_summary="medium risk plan",
                steps=[AgentPlanStep("task.echo", {"objective": "x"}, "medium", "do work")],
                overall_risk="medium",
                planner_name="planner",
            )

    framework = AgentFramework(planner=Planner(), tools=build_tools())
    run = framework.create_run(objective="test", user_id="u1")
    assert run.status == "pending_approval"


def test_approve_then_execute_run() -> None:
    framework = AgentFramework(tools=build_tools())
    run = framework.create_run(objective="ship feature", user_id="u1")
    framework.approve_run(run.run_id)
    executed = framework.execute_run(run.run_id)
    assert executed.status == "completed"
    assert executed.steps_completed == 1


def test_execute_pending_approval_raises() -> None:
    class Planner(RuntimeLocalPlanner):
        def plan(self, objective, *, user_id, available_tools):
            _ = objective
            _ = user_id
            _ = available_tools
            return AgentPlan(
                executive_summary="high risk plan",
                steps=[AgentPlanStep("task.echo", {"objective": "x"}, "high", "do work")],
                overall_risk="high",
                planner_name="planner",
            )

    framework = AgentFramework(planner=Planner(), tools=build_tools())
    run = framework.create_run(objective="test", user_id="u1")
    with pytest.raises(ApprovalRequiredError):
        framework.execute_run(run.run_id)


def test_capability_denial_fails_run() -> None:
    framework = AgentFramework(tools=build_tools())
    run = framework.create_run(objective="test", user_id="u1")
    framework.approve_run(run.run_id)
    run.capability_token = {"allowed_tools": []}
    with pytest.raises(CapabilityViolationError):
        framework.execute_run(run.run_id)
    assert framework.get_run(run.run_id).status == "failed"


def test_delegate_creates_child_and_marks_parent() -> None:
    framework = AgentFramework(tools=build_tools())
    run = framework.create_run(objective="delegate", user_id="u1")
    child = framework.delegate_run(run.run_id, target_agent="agent-b")
    assert child.parent_run_id == run.run_id
    assert framework.get_run(run.run_id).status == "delegated"


def test_delegation_loop_blocked() -> None:
    framework = AgentFramework(
        config=AgentFrameworkConfig(max_delegation_depth=3),
        tools=build_tools(),
    )
    run = framework.create_run(objective="delegate", user_id="u1")
    child = framework.delegate_run(run.run_id, target_agent="agent-b")
    framework._ancestor_chains[child.run_id] = [run.run_id, "agent-b"]
    with pytest.raises(DelegationBlockedError):
        framework.delegate_run(child.run_id, target_agent=run.run_id)


def test_recover_resumes_from_next_incomplete_step() -> None:
    tools = ToolRegistry()
    tools.register(
        name="task.one",
        description="one",
        risk_level="low",
        required_capability="task.one",
        handler=lambda args: {"step": 1, **args},
    )
    tools.register(
        name="task.two",
        description="two",
        risk_level="low",
        required_capability="task.two",
        handler=lambda args: {"step": 2, **args},
    )

    class Planner(RuntimeLocalPlanner):
        def plan(self, objective, *, user_id, available_tools):
            _ = objective
            _ = user_id
            _ = available_tools
            return AgentPlan(
                executive_summary="two step",
                steps=[
                    AgentPlanStep("task.one", {"value": 1}, "low", "first"),
                    AgentPlanStep("task.two", {"value": 2}, "low", "second"),
                ],
                overall_risk="low",
                planner_name="planner",
            )

    framework = AgentFramework(planner=Planner(), tools=tools)
    run = framework.create_run(objective="recover", user_id="u1")
    framework.approve_run(run.run_id)
    run.status = "stuck"
    run.steps_completed = 1
    recovered = framework.recover_run(run.run_id)
    assert recovered.status == "completed"
    assert recovered.steps_completed == 2


def test_replay_clones_plan_into_new_pending_run() -> None:
    framework = AgentFramework(tools=build_tools())
    run = framework.create_run(objective="replay me", user_id="u1")
    replay = framework.replay_run(run.run_id)
    assert replay.run_id != run.run_id
    assert replay.plan == run.plan
    assert replay.status == "pending"


def test_event_timeline_contains_lifecycle_entries() -> None:
    framework = AgentFramework(tools=build_tools())
    run = framework.create_run(objective="events", user_id="u1")
    framework.approve_run(run.run_id)
    framework.execute_run(run.run_id)
    events = framework.list_events(run.run_id)
    assert any(event.event_type == "agent.run.created" for event in events)
    assert any(event.event_type == "agent.run.approved" for event in events)
    assert any(event.event_type == "agent.step.completed" for event in events)
    assert any(event.event_type == "agent.run.completed" for event in events)
