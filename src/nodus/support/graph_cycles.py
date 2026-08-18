"""Cycle detection over a dependency adjacency map.

Extracted so the *parser* and the *runtime* share one implementation (#396).

`orchestration/task_graph.py` has detected cycles since #323, but only once the
graph was built — at run time. `nodus check` therefore reported `OK` for a
workflow whose steps depend on each other in a loop, which is the one structural
property of a workflow that is knowable purely from the source. That is the exact
gap `docs/design/v5/00-domain-statement.md` calls *inspectable*: the plan should be
well-formed and knowable **before** it runs.

Keeping the algorithm here rather than copying it into the frontend follows this
codebase's rule about a check living in one place — see the recurring bug shape in
`CLAUDE.md`. Two implementations of "is this graph cyclic" would be two things to
keep in step, and the runtime copy is the one with test coverage.
"""

from __future__ import annotations


def detect_cycle(adjacency: dict[str, list[str]]) -> list[str] | None:
    """Return one cycle as a list of node names, or ``None`` if the graph is acyclic.

    The returned list starts at the node the cycle closes on and does **not**
    repeat it at the end — callers that want ``a -> b -> a`` append the first
    element themselves.

    Iterative rather than recursive: a workflow with a long dependency chain would
    otherwise be bounded by Python's recursion limit rather than by anything in
    Nodus, and a `RecursionError` surfacing from a syntax check would be a poor
    way to learn that.
    """
    WHITE, GREY, BLACK = 0, 1, 2
    colour: dict[str, int] = {node: WHITE for node in adjacency}
    path: list[str] = []

    for root in adjacency:
        if colour.get(root, WHITE) != WHITE:
            continue
        # (node, iterator over its remaining dependencies)
        stack: list[tuple[str, int]] = [(root, 0)]
        colour[root] = GREY
        path.append(root)
        while stack:
            node, index = stack[-1]
            deps = adjacency.get(node, ())
            if index < len(deps):
                stack[-1] = (node, index + 1)
                dep = deps[index]
                state = colour.get(dep, WHITE)
                if state == GREY:
                    start = path.index(dep)
                    return path[start:]
                if state == WHITE and dep in adjacency:
                    colour[dep] = GREY
                    path.append(dep)
                    stack.append((dep, 0))
            else:
                colour[node] = BLACK
                stack.pop()
                path.pop()
    return None


def format_cycle(cycle: list[str]) -> str:
    """Render a cycle as ``a -> b -> a``, closing the loop for the reader."""
    if not cycle:
        return ""
    return " -> ".join(list(cycle) + [cycle[0]])
