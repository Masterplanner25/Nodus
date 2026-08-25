"""Render a planned task graph as Mermaid or Graphviz DOT.

Nodus already reifies both halves of its execution structure: the static
topology (`plan_workflow` / `plan_graph` return a nodes-and-edges object) and
the dynamic trace (`nodus workflow runs | inspect | replay`).  What it could
not do was *emit* the static half in a form anything else reads, so a plan was
inspectable only as JSON.

This module is the projection.  It adds no new information -- everything here
comes out of the plan dict `plan_graph()` already builds -- it just writes it
in two formats other tools understand.

An edge is drawn conditional when the plan says it is, and never guessed at.
Two different things make one conditional:

* **`with { on: [...] }`** -- which dependency outcomes let the step run.  The
  plan reports non-default sets in `edge_conditions`, and the edge carries them
  as a label (`build -->|failed| notify`).  The default, `completed` alone, is
  deliberately *not* labelled: writing "completed" on every arrow would be
  noise, so an unlabelled arrow means the default (#537).
* **`when <predicate>`** -- a guard on the step itself.  The plan reports these
  in `conditional_edges`, and the edge is drawn dashed, because the step may not
  run at all (#471).

Both were previously plain arrows.  An unconditional arrow for a conditional
edge is a lie a diagram tells convincingly, which is worse than no diagram, so
this module refused to guess until the plan carried the answer.  It does now.
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


def _edge_styling(
    plan: Mapping[str, Any],
) -> tuple[set[tuple[str, str]], dict[tuple[str, str], str]]:
    """What makes each edge conditional, read from the plan and never inferred.

    Returns the `when`-guarded edges and the non-default `on:` labels. A plan
    from before these keys existed yields neither, so an older stored plan still
    renders -- as plain arrows, which is exactly what it knows.
    """
    guarded: set[tuple[str, str]] = set()
    raw_guarded = plan.get("conditional_edges")
    if isinstance(raw_guarded, list):
        for edge in raw_guarded:
            if isinstance(edge, (list, tuple)) and len(edge) == 2:
                guarded.add((str(edge[0]), str(edge[1])))

    labels: dict[tuple[str, str], str] = {}
    raw_conditions = plan.get("edge_conditions")
    if isinstance(raw_conditions, Mapping):
        for key, value in raw_conditions.items():
            source, separator, target = str(key).partition("->")
            if not separator:
                continue
            if isinstance(value, (list, tuple)) and value:
                labels[(source, target)] = ", ".join(str(item) for item in value)
    return guarded, labels


def to_mermaid(plan: Mapping[str, Any]) -> str:
    """A `flowchart TD` block, renderable by anything that speaks Mermaid."""
    nodes, edges = _nodes_and_edges(plan)
    ids = _ids(nodes)
    lines = ["flowchart TD"]
    title = _title(plan)
    lines.append(f"    %% {title}")
    for name in nodes:
        lines.append(f'    {ids[name]}["{_mermaid_label(name)}"]')
    guarded, labels = _edge_styling(plan)
    for source, target in edges:
        if source not in ids or target not in ids:
            raise GraphRenderError(f"edge references unknown node: {source!r} -> {target!r}")
        arrow = "-.->" if (source, target) in guarded else "-->"
        label = labels.get((source, target))
        middle = f"|{_mermaid_label(label)}|" if label else ""
        lines.append(f"    {ids[source]} {arrow}{middle} {ids[target]}")
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
    guarded, labels = _edge_styling(plan)
    for source, target in edges:
        if source not in ids or target not in ids:
            raise GraphRenderError(f"edge references unknown node: {source!r} -> {target!r}")
        attributes = []
        label = labels.get((source, target))
        if label:
            attributes.append(f'label="{_dot_label(label)}"')
        if (source, target) in guarded:
            attributes.append("style=dashed")
        suffix = f" [{', '.join(attributes)}]" if attributes else ""
        lines.append(f"    {ids[source]} -> {ids[target]}{suffix};")
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
