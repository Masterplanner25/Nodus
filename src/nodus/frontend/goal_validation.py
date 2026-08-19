"""Parse-time validation for `goal NAME over WORKFLOW { ... }` (#409 Part A).

The point of putting a goal's stopping condition in the language rather than in a
library is that the compiler can reject a goal whose waypoints do not exist. That
check is **total**, not best-effort, because both halves are literals:

- `checkpoint "label"` is a statement requiring a string literal, so a workflow's
  complete checkpoint set is knowable at parse time;
- `reached("label")` likewise, so a goal's complete dependency set is too.

A Python planner can observe checkpoints at run time. It cannot reject a goal
whose waypoints do not exist, having no parse tree to check them against — which
is the concrete answer to "why is this in the language".
"""

from __future__ import annotations

import dataclasses

from nodus.runtime.diagnostics import LangSyntaxError


def walk(node):
    """Yield every AST node reachable from *node*.

    Generic over dataclass fields rather than a ``NodeVisitor`` subclass. The
    visitor demands a ``visit_<ClassName>`` method per node type and raises when
    one is missing; that is the right trade for a walker that must interpret
    every node, and the wrong one here, where we are looking for two node types
    anywhere in a tree and would otherwise have to extend the visitor every time
    an unrelated node is added.
    """
    if isinstance(node, (list, tuple)):
        for item in node:
            yield from walk(item)
        return
    if not dataclasses.is_dataclass(node) or isinstance(node, type):
        return
    yield node
    for field in dataclasses.fields(node):
        yield from walk(getattr(node, field.name, None))


def _literal(node) -> str | None:
    value = getattr(node, "v", None)
    return value if isinstance(value, str) else None


def checkpoint_labels(flow_def) -> set[str]:
    """Every `checkpoint "..."` label recorded anywhere in *flow_def*."""
    labels: set[str] = set()
    for node in walk(flow_def):
        if type(node).__name__ == "CheckpointStmt":
            label = _literal(node.label)
            if label is not None:
                labels.add(label)
    return labels


def reached_labels(node) -> list[tuple[str, object]]:
    """Every `reached("...")` label in *node*, paired with its AST node."""
    found: list[tuple[str, object]] = []
    for item in walk(node):
        if type(item).__name__ == "Reached":
            label = _literal(item.label)
            if label is not None:
                found.append((label, item))
    return found


def _fail(message: str, node) -> None:
    tok = getattr(node, "_tok", None)
    raise LangSyntaxError(
        message,
        line=getattr(tok, "line", None),
        col=getattr(tok, "col", None),
    )


def validate_step_guards(stmts) -> None:
    """Check every `step ... when reached("...")` against its own workflow (#471).

    Same guarantee as a goal's `until`, and the reason the guard grammar is
    restricted rather than a general expression: a step waiting on a checkpoint
    nothing records would never run, silently, and would look exactly like a step
    whose condition simply did not hold this time.

    The check is local -- a step's guard can only name checkpoints from the flow
    it belongs to -- so unlike `validate_goal_pursuits` there is no
    cannot-see-the-target case to worry about.
    """
    for flow in walk(stmts):
        if type(flow).__name__ not in ("WorkflowDef", "GoalDef"):
            continue
        available = checkpoint_labels(flow)
        for step in getattr(flow, "steps", []) or []:
            guard = getattr(step, "when", None)
            if guard is None:
                continue
            for label, node in reached_labels(guard):
                if label in available:
                    continue
                known = ", ".join(f'"{name}"' for name in sorted(available)) or "none"
                _fail(
                    f"step '{step.name}' waits on checkpoint \"{label}\", which "
                    f"'{flow.name}' never records. It records {known}.",
                    node,
                )


def validate_goal_pursuits(stmts) -> None:
    """Check every `goal ... over ...` in a parsed module.

    Raises ``LangSyntaxError`` on the first problem, like the rest of the parser.
    """
    pursuits = [n for n in walk(stmts) if type(n).__name__ == "GoalPursuit"]
    if not pursuits:
        return

    flows: dict[str, object] = {}
    for node in walk(stmts):
        if type(node).__name__ in ("WorkflowDef", "GoalDef"):
            flows.setdefault(node.name, node)

    for pursuit in pursuits:
        target = flows.get(pursuit.workflow_name)
        if target is None:
            # Deliberately an error rather than a skipped check. Skipping when the
            # target cannot be seen would make the guarantee best-effort and
            # silently so, which is the failure mode this whole feature exists to
            # avoid. The cost is that the first cut requires the pursued workflow
            # to be declared in the same module.
            _fail(
                f"goal '{pursuit.name}' pursues '{pursuit.workflow_name}', which is "
                f"not declared in this file. A goal must name a workflow in the "
                f"same module so its checkpoints can be checked.",
                pursuit,
            )

        available = checkpoint_labels(target)
        wanted = reached_labels(pursuit.until)
        if pursuit.retry_from is not None:
            label = _literal(pursuit.retry_from)
            if label is not None:
                wanted = wanted + [(label, pursuit.retry_from)]

        for label, node in wanted:
            if label not in available:
                known = ", ".join(f'"{name}"' for name in sorted(available))
                detail = f" It records {known}." if known else " It records none."
                _fail(
                    f"goal '{pursuit.name}' waits on checkpoint \"{label}\", which "
                    f"'{pursuit.workflow_name}' never records.{detail}",
                    node,
                )

        if not reached_labels(pursuit.until):
            _fail(
                f"goal '{pursuit.name}' has an `until` that never reads a "
                f"checkpoint, so nothing it observes can ever change.",
                pursuit,
            )
