"""Resolving which graph a request is talking about (#584).

`services/api.py` and `services/server.py` each grew a `_graph_metadata` that
answered the same question, and they had drifted: `server.py` scanned the VM's
own `graph_persist`/`graph_resume` events, `api.py` did not, and so `api.py`
leaned on a `latest_graph_state()` fallback that read the process-global
`.nodus/graphs/` and returned the lexicographically largest uuid4 id.

That fallback was doing two jobs at once. It stood in for request-scoped
resolution (right only while the directory held exactly one graph) *and* it
answered a request that produced no graph at all with **another request's**
graph id, status and full task map, step return values included. Sorting the
directory by time would have picked a different stranger rather than the
caller's own run, so the fix is not a better sort: it is to resolve only from
state belonging to this request, and to say "no graph" when there is none.

One implementation, so the two cannot drift again.
"""

from nodus.orchestration.task_graph import load_graph_state


# Events a run emits about its own graph, newest first when scanned in reverse.
GRAPH_ID_EVENTS = frozenset({"graph_persist", "graph_resume"})


def resolve_request_graph_id(vm, graph_id: str | None = None) -> str | None:
    """The graph *this request* produced, or None.

    Every source consulted here belongs to the request: the id the caller
    supplied, the plan this VM last built, and the events this VM emitted.
    Nothing reads the shared graph directory, which is what made the old
    fallback a cross-request leak rather than merely a wrong answer.
    """
    if graph_id is not None:
        return graph_id
    if vm is None:
        return None
    plan = getattr(vm, "last_graph_plan", None)
    if plan:
        resolved = plan.get("graph_id")
        if resolved is not None:
            return resolved
    # `last_graph_plan` is set by `plan_workflow`, not by `run_workflow`, so a
    # run that executed a workflow is named only by its own events.
    event_bus = getattr(vm, "event_bus", None)
    if event_bus is None:
        return None
    for event in reversed(event_bus.events()):
        if event.type in GRAPH_ID_EVENTS and event.data and "graph_id" in event.data:
            return event.data["graph_id"]
    return None


def graph_metadata(vm, graph_id: str | None = None) -> dict:
    """The `graph_id` / `tasks` / `graph_status` block a graph response carries."""
    resolved_id = resolve_request_graph_id(vm, graph_id)
    state = load_graph_state(resolved_id) if resolved_id is not None else None
    return {
        "graph_id": resolved_id,
        "tasks": state.get("tasks", {}) if state else {},
        "graph_status": state.get("status") if state else None,
    }
