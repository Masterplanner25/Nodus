"""Render a planned task graph as Mermaid or Graphviz DOT.

Nodus already reifies both halves of its execution structure: the static
topology (`plan_workflow` / `plan_graph` return a nodes-and-edges object) and
the dynamic trace (`nodus workflow runs | inspect | replay`).  What it could
not do was *emit* the static half in a form anything else reads, so a plan was
inspectable only as JSON.

This module is the projection.  It adds no new information -- everything here
comes out of the plan dict `plan_graph()` already builds -- it just writes it
in two formats other tools understand.

Deliberately not rendered, because the plan does not carry it: the `on: [...]`
dependency-outcome filter a step may declare.  An edge here means "compile
depends on fetch", not "compile runs if fetch succeeded".  Drawing an
unconditional arrow for a conditional edge would be a lie the diagram tells
convincingly, so the edge stays unlabelled until the plan carries the
condition -- tracked in **#537**, which is about putting it in the plan rather
than guessing at it here.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

FORMATS: tuple[str, ...] = ("mermaid", "dot")


class GraphRenderError(ValueError):
    """The object handed in is not a graph plan."""


def _nodes_and_edges(plan: Mapping[str, Any]) -> tuple[list[str], list[tuple[str, str]]]:
    nodes = plan.get("nodes")
    edges = plan.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise GraphRenderError(
            "not a graph plan: expected 'nodes' and 'edges' keys "
            f"(got {sorted(plan)[:6]})"
        )
    clean_edges: list[tuple[str, str]] = []
    for edge in edges:
        if not isinstance(edge, (list, tuple)) or len(edge) != 2:
            raise GraphRenderError(f"malformed edge: {edge!r}")
        clean_edges.append((str(edge[0]), str(edge[1])))
    return [str(n) for n in nodes], clean_edges


def _levels(plan: Mapping[str, Any], nodes: Sequence[str]) -> list[list[str]]:
    """Parallel groups, if the plan recorded them.

    `levels` and `parallel_groups` are the same partition in every plan seen so
    far; `levels` wins when both are present.
    """
    for key in ("levels", "parallel_groups"):
        value = plan.get(key)
        if isinstance(value, list) and value:
            groups = []
            for group in value:
                if isinstance(group, (list, tuple)):
                    groups.append([str(item) for item in group])
            if groups:
                return groups
    return []


def _title(plan: Mapping[str, Any]) -> str:
    name = plan.get("workflow") or plan.get("goal")
    if isinstance(name, str) and name:
        return name
    graph_id = plan.get("graph_id")
    return str(graph_id) if isinstance(graph_id, str) and graph_id else "graph"


def _ids(nodes: Iterable[str]) -> dict[str, str]:
    """Map node names to safe identifiers.

    Step names are user-authored and reach here unfiltered, so nothing is
    interpolated into the identifier position -- the name only ever appears
    inside a quoted label.
    """
    return {name: f"n{index}" for index, name in enumerate(nodes)}


def _mermaid_label(text: str) -> str:
    # Mermaid reads `"` inside a `["..."]` label as the terminator; `#quot;` is
    # its documented escape.  Square brackets end the node shape.
    return (
        text.replace("#", "#35;")
        .replace('"', "#quot;")
        .replace("[", "#91;")
        .replace("]", "#93;")
    )


def _dot_label(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def to_mermaid(plan: Mapping[str, Any]) -> str:
    """A `flowchart TD` block, renderable by anything that speaks Mermaid."""
    nodes, edges = _nodes_and_edges(plan)
    ids = _ids(nodes)
    lines = ["flowchart TD"]
    title = _title(plan)
    lines.append(f"    %% {title}")
    for name in nodes:
        lines.append(f'    {ids[name]}["{_mermaid_label(name)}"]')
    for source, target in edges:
        if source not in ids or target not in ids:
            raise GraphRenderError(f"edge references unknown node: {source!r} -> {target!r}")
        lines.append(f"    {ids[source]} --> {ids[target]}")
    return "\n".join(lines)


def to_dot(plan: Mapping[str, Any]) -> str:
    """A `digraph`, with each parallel group pinned to one rank.

    The `rank=same` grouping is the part worth having over Mermaid: it makes
    the levels the scheduler will actually run concurrently line up visually,
    rather than leaving layout to the renderer's guess.
    """
    nodes, edges = _nodes_and_edges(plan)
    ids = _ids(nodes)
    title = _title(plan)
    lines = [
        f'digraph "{_dot_label(title)}" {{',
        "    rankdir=TB;",
        '    node [shape=box, style="rounded,filled", fillcolor="#f5f5f5", fontname="sans-serif"];',
        '    edge [fontname="sans-serif"];',
    ]
    for name in nodes:
        lines.append(f'    {ids[name]} [label="{_dot_label(name)}"];')
    for source, target in edges:
        if source not in ids or target not in ids:
            raise GraphRenderError(f"edge references unknown node: {source!r} -> {target!r}")
        lines.append(f"    {ids[source]} -> {ids[target]};")
    for group in _levels(plan, nodes):
        members = [ids[name] for name in group if name in ids]
        if len(members) > 1:
            lines.append(f"    {{ rank=same; {' '.join(members)} }}")
    lines.append("}")
    return "\n".join(lines)


def render(plan: Mapping[str, Any], fmt: str) -> str:
    """Render `plan` as `fmt`, which must be one of :data:`FORMATS`."""
    if fmt == "mermaid":
        return to_mermaid(plan)
    if fmt == "dot":
        return to_dot(plan)
    raise GraphRenderError(
        f"unknown format {fmt!r}; expected one of {', '.join(FORMATS)}"
    )
