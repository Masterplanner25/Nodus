"""Workflow/goal AST/runtime lowering helpers."""

from __future__ import annotations

from typing import Any

from nodus.builtins.nodus_builtins import BUILTIN_CALL_PREFIX
from nodus.runtime.diagnostics import LangSyntaxError
from nodus.frontend.ast.ast_nodes import (
    builtin_call,
    ActionStmt,
    Assign,
    Attr,
    Bin,
    Block,
    Bool,
    Call,
    CheckpointStmt,
    Comment,
    CompoundAssign,
    DestructureLet,
    ExprStmt,
    FieldAssign,
    FnDef,
    FnExpr,
    For,
    ForEach,
    GoalDef,
    GoalStep,
    If,
    Import,
    Index,
    IndexAssign,
    InterpolatedString,
    InterpolationPart,
    Let,
    ListLit,
    ListPattern,
    MapLit,
    Int,
    Nil,
    Num,
    Param,
    Print,
    RecordLiteral,
    RecordPattern,
    Return,
    Str,
    Throw,
    TryCatch,
    Unary,
    Var,
    VarPattern,
    While,
    WorkflowDef,
    WorkflowStep,
)
from nodus.orchestration.workflow_state import (
    FOLD_STATE_MERGE_POLICIES,
    STATE_MERGE_POLICIES,
)
from nodus.orchestration.task_graph import (
    DEFAULT_JOIN_ON,
    JOIN_ON_STATES,
    TaskGraph,
    TaskNode,
)


WORKFLOW_MARKER = "__workflow__"
GOAL_MARKER = "__goal__"
GOAL_PURSUIT_MARKER = "__goal_pursuit__"
# Policies a `state` cell may declare (#485, #498). Two axes, deliberately not
# three: an earlier framing had typing here too, but #479 is about step outputs
# and tool schemas and never mentions state -- so the `: type` slot stays free.
STATE_OPTION_KEYS = {
    "merge",
    "durable",
}


STEP_OPTION_KEYS = {
    "timeout_ms",
    "retries",
    "retry_delay_ms",
    "cache",
    "cache_key",
    "worker",
    "worker_timeout_ms",
    "on",
    "allow_failure",
}


def lower_workflow_ast(workflow: WorkflowDef) -> MapLit:
    return _lower_flow_ast(workflow, marker=WORKFLOW_MARKER, execution_kind="workflow")


def lower_goal_ast(goal: GoalDef) -> MapLit:
    return _lower_flow_ast(goal, marker=GOAL_MARKER, execution_kind="goal")


def lower_goal_pursuit_ast(pursuit) -> MapLit:
    """Lower `goal NAME over WORKFLOW { until ... budget ... }` (#409 Part A).

    The predicate becomes **data**, not code: a nested map the runtime walks
    against the set of checkpoints reached so far. That keeps a goal's stopping
    condition inspectable before it runs, which is the property the whole feature
    exists for — a compiled-away predicate would be no better than a callback.
    """
    items: list[tuple[object, object]] = [
        (Str(GOAL_PURSUIT_MARKER), Str("goal_pursuit")),
        (Str("name"), Str(pursuit.name)),
        (Str("execution_kind"), Str("goal")),
        (Str("workflow"), Str(pursuit.workflow_name)),
        (Str("until"), _lower_predicate(pursuit.until)),
        (
            Str("budget"),
            MapLit(
                [
                    (Str("max_iterations"), pursuit.budget.max_iterations),
                    (Str("deadline_ms"), pursuit.budget.deadline_ms),
                ]
            ),
        ),
    ]
    if pursuit.retry_from is not None:
        items.append((Str("retry_from"), pursuit.retry_from))
    return MapLit(items)


def _lower_predicate(node) -> MapLit:
    kind = type(node).__name__
    if kind == "Reached":
        return MapLit([(Str("op"), Str("reached")), (Str("label"), node.label)])
    if kind == "PredicateNot":
        return MapLit(
            [(Str("op"), Str("not")), (Str("operand"), _lower_predicate(node.operand))]
        )
    if kind == "PredicateAnd":
        return MapLit(
            [
                (Str("op"), Str("and")),
                (Str("left"), _lower_predicate(node.left)),
                (Str("right"), _lower_predicate(node.right)),
            ]
        )
    if kind == "PredicateOr":
        return MapLit(
            [
                (Str("op"), Str("or")),
                (Str("left"), _lower_predicate(node.left)),
                (Str("right"), _lower_predicate(node.right)),
            ]
        )
    raise ValueError(f"Unsupported goal predicate node: {kind}")


def is_goal_pursuit_value(value) -> bool:
    return isinstance(value, dict) and value.get(GOAL_PURSUIT_MARKER) == "goal_pursuit"


def _pos(node) -> tuple[int, int]:
    """Line/col from a node's source token, for a lowering-time refusal.

    Nodes carry position on `_tok`, not as `line`/`col` attributes, so reading
    the latter silently yields 0:0 and the error points at the top of the file.
    """
    tok = getattr(node, "_tok", None)
    if tok is None:
        return 0, 0
    return getattr(tok, "line", 0) or 0, getattr(tok, "col", 0) or 0


def _fold_cells(flow) -> dict[str, str]:
    """Cells declaring a fold policy, read out of the `with { ... }` literal.

    Read statically because a fold changes what `=` and `+=` *mean* for that
    cell, and the refusal of `=` is a compile-time error -- `nodus check` catches
    the typo rather than the first concurrent run. That requires the policy to be
    known before the program runs, so `merge:` must be a string literal.

    A computed `merge:` is refused where it is written rather than silently
    treated as no policy. Everything else in `with { ... }` stays an ordinary
    expression: `durable:` does not change the meaning of any code, so it has no
    reason to be pinned.
    """
    cells: dict[str, str] = {}
    for state in flow.states:
        options = getattr(state, "options", None)
        if not isinstance(options, MapLit):
            continue
        for key_node, value_node in options.items:
            if not (isinstance(key_node, Str) and key_node.v == "merge"):
                continue
            if not isinstance(value_node, Str):
                raise LangSyntaxError(
                    f"state '{state.name}' merge: must be a literal policy name. "
                    "It decides at compile time whether a write to this cell is a "
                    "contribution, so it cannot be computed.",
                    line=_pos(state)[0],
                    col=_pos(state)[1],
                )
            if value_node.v in FOLD_STATE_MERGE_POLICIES:
                cells[state.name] = value_node.v
    return cells


def _lower_flow_ast(flow, *, marker: str, execution_kind: str) -> MapLit:
    state_init = _lower_state_init(flow)
    state_names = [state.name for state in flow.states]
    fold_cells = _fold_cells(flow)
    items: list[tuple[object, object]] = [
        (Str(marker), Str(execution_kind)),
        (Str("name"), Str(flow.name)),
        (Str("execution_kind"), Str(execution_kind)),
        (
            Str("steps"),
            ListLit([
                _lower_step_ast(step, state_names, fold_cells, flow_name=flow.name)
                for step in flow.steps
            ]),
        ),
    ]
    if state_init is not None:
        items.append((Str("state_init"), state_init))
    if state_names:
        items.append((Str("state_keys"), ListLit([Str(name) for name in state_names])))
        policies = _lower_state_policies(flow)
        if policies is not None:
            items.append((Str("state_policies"), policies))
    return MapLit(items)


def _lower_state_policies(flow) -> MapLit | None:
    """Per-cell `merge` / `durable` declarations, as data.

    Emitted only when a cell actually declares something, so a workflow that says
    nothing carries nothing -- the defaults live in one place at the runtime rather
    than being baked into every lowered program.
    """
    entries: list[tuple[object, object]] = []
    for state in flow.states:
        options = getattr(state, "options", None)
        if options is None:
            continue
        entries.append((Str(state.name), options))
    return MapLit(entries) if entries else None


def _lower_state_init(flow: WorkflowDef | GoalDef) -> FnExpr | None:
    if not flow.states:
        return None
    state_var = "__workflow_state"
    state_names = {state.name for state in flow.states}
    rewriter = _StateRewriter(state_names, state_var, initial_locals={state_var})
    stmts: list[Any] = [Let(state_var, MapLit([]))]
    for state in flow.states:
        expr = rewriter.rewrite_expr(state.value)
        assign = IndexAssign(Var(state_var), Str(state.name), expr)
        stmts.append(ExprStmt(assign))
    stmts.append(Return(Var(state_var)))
    return FnExpr([], Block(stmts), return_type=None)


def _lower_step_ast(
    step: WorkflowStep | GoalStep,
    state_names: list[str],
    fold_cells: dict[str, str] | None = None,
    *,
    flow_name: str = "",
) -> MapLit:
    state_var = "__workflow_state"
    body = step.body
    rewriter = _StateRewriter(
        set(state_names),
        state_var,
        initial_locals=set(step.deps) | ({state_var} if state_names else set()),
        fold_cells=fold_cells,
    )
    rewritten_body = rewriter.rewrite_stmt(body)
    if state_names:
        prelude = Let(state_var, builtin_call("workflow_state", []))
        body_stmts = rewritten_body.stmts if isinstance(rewritten_body, Block) else [rewritten_body]
        rewritten_body = Block([prelude] + body_stmts)
    body = _return_last_action(rewritten_body)
    items: list[tuple[object, object]] = [
        (Str("name"), Str(step.name)),
        (Str("deps"), ListLit([Str(dep) for dep in step.deps])),
        # #394: the closure is marked with the step it belongs to, and the mark
        # rides on the compiled FunctionInfo rather than on this map -- because
        # the map is guest-reachable and the FunctionInfo is not. Ordering was a
        # default rather than an invariant precisely because this value is an
        # ordinary map whose "fn" slot is an ordinary callable; the mark is what
        # lets `VM.guard_step_entry` tell a runner-driven entry from a guest one.
        (
            Str("fn"),
            FnExpr(
                [Param(dep) for dep in step.deps],
                body,
                return_type=None,
                step_owner=f"{flow_name}.{step.name}" if flow_name else step.name,
            ),
        ),
        (Str("options"), step.options if step.options is not None else MapLit([])),
    ]
    when = getattr(step, "when", None)
    if when is not None:
        # Data, not a compiled closure -- the same treatment a goal's `until` gets,
        # so the condition stays readable before the run and `nodus check` can
        # verify the labels it names.
        items.append((Str("when"), _lower_predicate(when)))
    return MapLit(items)


def _return_last_action(body: object) -> Block:
    if not isinstance(body, Block) or not body.stmts:
        return body if isinstance(body, Block) else Block([body])
    last = body.stmts[-1]
    if isinstance(last, ExprStmt) and isinstance(last.expr, Call) and _is_action_builtin(last.expr):
        stmts = list(body.stmts[:-1]) + [Return(last.expr)]
        return _mark_from(Block(stmts), body)
    return body


ACTION_BUILTINS = frozenset({
    "__action_tool",
    "__action_agent",
    "__action_memory_put",
    "__action_memory_get",
    "__action_emit",
})


def _is_action_builtin(expr: Call) -> bool:
    """Is this the action call a step body ends with?

    Must strip `BUILTIN_CALL_PREFIX` first (#411). The lowering emits these through
    `builtin_call()` so a program cannot shadow them, and this matcher runs *after*
    that rewrite — so comparing the raw callee name silently stopped matching, the
    trailing action was no longer turned into a `Return`, and every step ending in
    an action returned nil instead of its result.

    That is the same defect as #411 in miniature: a name-based decision broken by a
    rename. Strip rather than compare against both spellings, so this keeps working
    if a lowering is ever changed back or a new prefix is introduced.
    """
    if not isinstance(expr.callee, Var):
        return False
    name = expr.callee.name
    if name.startswith(BUILTIN_CALL_PREFIX):
        name = name[len(BUILTIN_CALL_PREFIX):]
    return name in ACTION_BUILTINS


def runtime_flow_kind(value) -> str | None:
    if not isinstance(value, dict):
        return None
    if value.get(WORKFLOW_MARKER) == "workflow":
        return "workflow"
    if value.get(GOAL_MARKER) == "goal":
        return "goal"
    return None


def is_workflow_value(value) -> bool:
    return runtime_flow_kind(value) == "workflow"


def is_goal_value(value) -> bool:
    return runtime_flow_kind(value) == "goal"


def unwrap_runtime_value(value):
    if hasattr(value, "value"):
        return value.value
    return value


def _find_flow_value(globals_dict: dict[str, object], flow_name: str | None, *, kind: str):
    matches = {}
    for name, value in globals_dict.items():
        unwrapped = unwrap_runtime_value(value)
        if runtime_flow_kind(unwrapped) == kind:
            matches[name] = unwrapped
    if flow_name is not None:
        direct = matches.get(flow_name)
        if direct is not None:
            return direct
        for value in matches.values():
            if value.get("name") == flow_name:
                return value
        return None
    if len(matches) == 1:
        return next(iter(matches.values()))
    return None


def find_workflow_value(globals_dict: dict[str, object], workflow_name: str | None = None):
    return _find_flow_value(globals_dict, workflow_name, kind="workflow")


def find_goal_value(globals_dict: dict[str, object], goal_name: str | None = None):
    return _find_flow_value(globals_dict, goal_name, kind="goal")


def _flow_name_candidates(globals_dict: dict[str, object], *, kind: str) -> list[str]:
    names = []
    for name, value in globals_dict.items():
        unwrapped = unwrap_runtime_value(value)
        if runtime_flow_kind(unwrapped) == kind:
            flow_name = unwrapped.get("name")
            names.append(flow_name if isinstance(flow_name, str) else name)
    names.sort()
    return names


def workflow_name_candidates(globals_dict: dict[str, object]) -> list[str]:
    return _flow_name_candidates(globals_dict, kind="workflow")


def goal_name_candidates(globals_dict: dict[str, object]) -> list[str]:
    return _flow_name_candidates(globals_dict, kind="goal")


def graph_topology(tasks) -> dict:
    """A graph's shape as comparable data: step names and dependency edges.

    Deliberately structure only -- no bodies, no `when` guards, no `on:` filters,
    no options. A body or guard edit is recoverable on resume and usually
    intentional; a renamed, added, removed or re-wired step is not, because the
    persisted per-task state is keyed to the planned shape. Sorted so the same
    graph always serialises to the same value regardless of declaration order,
    matching the byte-stable discipline `_persist_graph_state` already uses.
    """
    steps = sorted(
        task.step_name for task in tasks if isinstance(task.step_name, str)
    )
    edges = sorted(
        [dep.step_name, task.step_name]
        for task in tasks
        for dep in task.dependencies
        if isinstance(task.step_name, str) and isinstance(dep.step_name, str)
    )
    return {"steps": steps, "edges": edges}


def workflow_to_graph(vm, workflow_value, *, init_state: bool = False, task_ids_by_step: dict[str, str] | None = None) -> TaskGraph:
    kind = runtime_flow_kind(workflow_value)
    if kind not in {"workflow", "goal"}:
        vm.runtime_error("type", "workflow value expected")
    name = workflow_value.get("name")
    if not isinstance(name, str) or not name:
        vm.runtime_error("type", "workflow name must be a non-empty string")
    steps = workflow_value.get("steps")
    if not isinstance(steps, list) or not steps:
        vm.runtime_error("type", "workflow must define at least one step")

    by_name: dict[str, TaskNode] = {}
    ordered: list[tuple[str, dict]] = []
    for step in steps:
        if not isinstance(step, dict):
            vm.runtime_error("type", "workflow steps must be maps")
        step_name = step.get("name")
        if not isinstance(step_name, str) or not step_name:
            vm.runtime_error("type", "workflow step name must be a non-empty string")
        if step_name in by_name:
            vm.runtime_error("type", f"Duplicate workflow step: {step_name}")
        ordered.append((step_name, step))
        by_name[step_name] = None  # type: ignore[assignment]

    tasks: list[TaskNode] = []
    resolved: dict[str, TaskNode] = {}
    step_to_task: dict[str, str] = {}
    for step_name, step in ordered:
        fn = step.get("fn")
        closure = vm.ensure_function(fn, f"workflow step '{step_name}'")
        expected_arity = len(step.get("deps", [])) if isinstance(step.get("deps", []), list) else None
        if expected_arity is not None and len(closure.function.params) != expected_arity:
            vm.runtime_error(
                "call",
                f"Workflow step '{step_name}' expects {expected_arity} dependency input(s) but defines {len(closure.function.params)} parameter(s)",
            )
        options = step.get("options", {})
        if options is None:
            options = {}
        if not isinstance(options, dict):
            vm.runtime_error("type", f"Workflow step '{step_name}' options must be a map")
        task_id = None
        if isinstance(task_ids_by_step, dict):
            preserved_task_id = task_ids_by_step.get(step_name)
            if isinstance(preserved_task_id, str) and preserved_task_id:
                task_id = preserved_task_id
        if task_id is None:
            vm._task_counter += 1
            task_id = f"task_{vm._task_counter}"
        task = TaskNode(
            task_id=task_id,
            function=closure,
            dependencies=[],
            timeout_ms=_number_option(vm, options, "timeout_ms", step_name),
            max_retries=int(_number_option(vm, options, "retries", step_name, default=0) or 0),
            retry_delay_ms=float(_number_option(vm, options, "retry_delay_ms", step_name, default=0.0) or 0.0),
            cache=bool(options.get("cache", False)),
            cache_key=options.get("cache_key"),
            worker=_string_option(vm, options, "worker", step_name),
            worker_timeout_ms=_number_option(vm, options, "worker_timeout_ms", step_name),
            on_states=_on_option(vm, options, step_name),
            when=step.get("when"),
            step_name=step_name,
            allow_failure=bool(options.get("allow_failure", False)),
        )
        tasks.append(task)
        resolved[step_name] = task
        step_to_task[step_name] = task_id

    for step_name, step in ordered:
        deps = step.get("deps", [])
        if not isinstance(deps, list):
            vm.runtime_error("type", f"Workflow step '{step_name}' deps must be a list")
        dep_nodes: list[Any] = []
        for dep in deps:
            if not isinstance(dep, str):
                vm.runtime_error("type", f"Workflow step '{step_name}' dependency names must be strings")
            dep_task = resolved.get(dep)
            if dep_task is None:
                vm.runtime_error("runtime", f"Workflow step '{step_name}' references unknown dependency '{dep}'")
            dep_nodes.append(dep_task)
        resolved[step_name].dependencies = dep_nodes

    # #499: the stored source is the cross-process rebuild handle -- and a
    # verbatim copy of the whole module, persisted under `.nodus/graphs/`. An
    # embedder running code it did not author can opt out
    # (`NodusRuntime(persist_workflow_source=False)`); the marker below keeps
    # the rebuild's explanation accurate when it later reads from disk.
    _persist_source = getattr(vm, "persist_workflow_source", True)
    metadata = {
        "workflow_name": name,
        "execution_kind": kind,
        "step_to_task": step_to_task,
        "task_to_step": {task_id: step for step, task_id in step_to_task.items()},
        "workflow_source_path": getattr(vm, "source_path", None),
        "workflow_source_code": getattr(vm, "source_code", None) if _persist_source else None,
        # #470: the shape the run was planned against, as data. A resume rebuilds
        # the graph by re-executing source; if the rebuilt shape differs, applying
        # the persisted per-task state manufactures false diagnoses (a "dependency
        # cycle" in acyclic source). Recording the topology lets the rebuild refuse
        # with the real cause instead.
        "workflow_topology": graph_topology(tasks),
        "state_policies": _state_policies(vm, workflow_value, name),
    }
    if not _persist_source:
        metadata["workflow_source_persisted"] = False
    if kind == "goal":
        metadata["goal_name"] = name
    if init_state:
        state_init = workflow_value.get("state_init")
        if state_init is not None:
            closure = vm.ensure_function(state_init, "workflow state initializer")
            state = vm.run_closure(closure, [])
            if not isinstance(state, dict):
                vm.runtime_error("type", "workflow state initializer must return a map")
            metadata["workflow_state"] = state
        else:
            metadata["workflow_state"] = {}
        metadata["checkpoints"] = []

    return TaskGraph(tasks, metadata=metadata)


def _state_policies(vm, workflow_value, flow_name: str) -> dict:
    """Validate and normalise the per-cell `with { ... }` declarations.

    Refused where they are written, not ignored: a cell declaring
    `merge: "sum"` -- a policy the runtime cannot yet honour -- would otherwise
    read as a fold and behave as last-write-wins, which is the failure this whole
    area is about.
    """
    raw = workflow_value.get("state_policies")
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        vm.runtime_error("type", f"workflow '{flow_name}' state policies must be a map")
    policies: dict[str, dict] = {}
    for cell, options in raw.items():
        if not isinstance(options, dict):
            vm.runtime_error(
                "type", f"state '{cell}' options must be a map"
            )
        entry: dict = {}
        if "merge" in options:
            merge = options["merge"]
            if merge not in STATE_MERGE_POLICIES:
                vm.runtime_error(
                    "type",
                    f"state '{cell}' merge: unknown policy {merge!r}. "
                    f"Valid policies are {', '.join(STATE_MERGE_POLICIES)}. "
                    f"`union` is deliberately absent: it needs an element-equality "
                    f"story Nodus does not have -- see issue #485.",
                )
            entry["merge"] = merge
        if "durable" in options:
            durable = options["durable"]
            if not isinstance(durable, bool):
                vm.runtime_error(
                    "type", f"state '{cell}' durable expects true or false"
                )
            entry["durable"] = durable
        if entry:
            policies[str(cell)] = entry
    return policies


def _number_option(vm, options: dict, key: str, step_name: str, default=None):
    value = options.get(key, default)
    if value is None:
        return None
    return vm.ensure_number(value, f"workflow step '{step_name}' option {key}")


def _on_option(vm, options: dict, step_name: str) -> frozenset[str]:
    """Read `with { on: [...] }` -- which dependency outcomes satisfy this join.

    A list for now. The per-dependency form (a map of dependency name to accepted
    states) is the natural extension and can be added on this key without breaking
    the list form, which is why the value shape is checked here rather than
    assumed at the use site.

    Unknown state names are refused rather than ignored: a step declaring
    `on: ["suceeded"]` would otherwise be silently unsatisfiable, which is the
    "declared but not enforced" failure this codebase has five other instances of.
    """
    value = options.get("on")
    if value is None:
        return DEFAULT_JOIN_ON
    if not isinstance(value, list):
        vm.runtime_error(
            "type",
            f"workflow step '{step_name}' option on expects a list of dependency "
            f"outcomes, e.g. [\"completed\", \"failed\"]",
        )
    states = set()
    for entry in value:
        if not isinstance(entry, str):
            vm.runtime_error(
                "type",
                f"workflow step '{step_name}' option on expects strings, got {type(entry).__name__}",
            )
        if entry not in JOIN_ON_STATES:
            vm.runtime_error(
                "type",
                f"workflow step '{step_name}' option on: unknown outcome '{entry}'. "
                f"Valid outcomes are {', '.join(JOIN_ON_STATES)}.",
            )
        states.add(entry)
    if not states:
        vm.runtime_error(
            "type",
            f"workflow step '{step_name}' option on is empty, so the step could never run. "
            f"Omit it to accept the default, [\"completed\"].",
        )
    return frozenset(states)


def _string_option(vm, options: dict, key: str, step_name: str):
    value = options.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        vm.runtime_error("type", f"workflow step '{step_name}' option {key} expects a string")
    return value


def _mark_from(node, original):
    tok = getattr(original, "_tok", None)
    if tok is not None:
        setattr(node, "_tok", tok)
    return node


def _collect_pattern_names(pattern) -> list[str]:
    names: list[str] = []
    if isinstance(pattern, VarPattern):
        names.append(pattern.name)
    elif isinstance(pattern, ListPattern):
        for item in pattern.elements:
            names.extend(_collect_pattern_names(item))
    elif isinstance(pattern, RecordPattern):
        for _key, value in pattern.fields:
            names.extend(_collect_pattern_names(value))
    return names


def _lower_action_expr(expr: ActionStmt):
    target = Str(expr.target) if expr.target is not None else Nil()
    if expr.kind == "tool":
        return _mark_from(builtin_call("__action_tool", [target, expr.payload if expr.payload is not None else MapLit([])]), expr)
    if expr.kind == "agent":
        return _mark_from(builtin_call("__action_agent", [target, expr.payload if expr.payload is not None else MapLit([])]), expr)
    if expr.kind == "memory_put":
        return _mark_from(builtin_call("__action_memory_put", [target, expr.payload if expr.payload is not None else Nil()]), expr)
    if expr.kind == "memory_get":
        return _mark_from(builtin_call("__action_memory_get", [target]), expr)
    if expr.kind == "emit":
        return _mark_from(builtin_call("__action_emit", [target, expr.payload if expr.payload is not None else MapLit([])]), expr)
    return expr


class _StateRewriter:
    """Rewrites workflow/goal step bodies to reference shared state via a map variable.

    **What it does:**
    Transforms AST nodes inside workflow and goal step bodies so that any
    reference to a workflow state variable (e.g. ``version`` declared with
    ``state version = "0.1.0"``) is replaced with an index expression into
    a shared state map (e.g. ``__state["version"]``).  Assignments to state
    variables similarly become index-assign expressions on the state map.

    **Why at compile time (workflow lowering), not at runtime:**
    Workflows and goals are lowered from their AST representation to
    ``MapLit`` nodes by ``lower_workflow_ast`` / ``lower_goal_ast`` before
    bytecode compilation.  This lowering phase runs inside the compiler's
    ``compile_stmt`` for ``WorkflowDef`` / ``GoalDef`` nodes.  Doing the
    rewrite at compile time means the bytecode emitted for each step function
    is already in the flat, state-map form — no runtime introspection or
    special VM opcodes are needed for state access.

    **Inputs:**
    - ``state_names`` — the set of state variable names declared in the
      workflow/goal (from ``WorkflowStateDecl`` nodes).
    - ``state_var`` — the name of the hidden local variable holding the
      state map (e.g. ``"__state"``).
    - ``initial_locals`` — names already in scope at the entry of the step
      body (used to avoid incorrectly rewriting shadowing locals).

    **Outputs:**
    A rewritten AST subtree where state variable references have been
    replaced with ``Index(Var(state_var), Str(name))`` expressions and
    state variable assignments have been replaced with
    ``IndexAssign(Var(state_var), Str(name), value)`` expressions.

    **Transformation rules (before → after):**

    Read access::

        version                    →  __state["version"]

    Write access (let / assign)::

        let version = "1.0"        →  let version = "1.0"  (first definition
                                       also writes to __state["version"])
        version = expr             →  __state["version"] = expr

    Scope shadowing::

        let version = ...          shadows version — further refs in that
                                   scope use the local, not the state map.

    Nested function bodies are treated as separate scopes; state references
    inside them are NOT rewritten (they would need an explicit capture of
    the state map to access it, which is not currently supported).
    """

    def __init__(
        self,
        state_names: set[str],
        state_var: str,
        initial_locals: set[str] | None = None,
        fold_cells: dict[str, str] | None = None,
    ):
        self.state_names = set(state_names)
        self.state_var = state_var
        self.scopes: list[set[str]] = [set(initial_locals or set())]
        # cell -> its fold policy, for cells declaring `merge: "sum"` / `"append"`.
        # A fold changes what a write *means*, so `=` and `+=` lower differently
        # for these and the difference is decided here, at compile time, rather
        # than by a runtime branch inside the write.
        self.fold_cells = dict(fold_cells or {})

    def _is_fold(self, name: str) -> bool:
        return name in self.fold_cells and not self._is_local(name)

    def _is_local(self, name: str) -> bool:
        return any(name in scope for scope in self.scopes)

    def _define(self, name: str) -> None:
        self.scopes[-1].add(name)

    def _enter_scope(self) -> None:
        self.scopes.append(set())

    def _exit_scope(self) -> None:
        self.scopes.pop()

    def rewrite_stmt(self, stmt):
        if isinstance(stmt, Block):
            self._enter_scope()
            out = Block([self.rewrite_stmt(s) for s in stmt.stmts])
            self._exit_scope()
            return _mark_from(out, stmt)
        if isinstance(stmt, Comment):
            return stmt
        if isinstance(stmt, ExprStmt):
            return _mark_from(ExprStmt(self.rewrite_expr(stmt.expr)), stmt)
        if isinstance(stmt, Let):
            expr = self.rewrite_expr(stmt.expr)
            out = Let(stmt.name, expr, type_hint=stmt.type_hint, exported=stmt.exported)
            self._define(stmt.name)
            return _mark_from(out, stmt)
        if isinstance(stmt, DestructureLet):
            expr = self.rewrite_expr(stmt.expr)
            out = DestructureLet(stmt.pattern, expr)
            for name in _collect_pattern_names(stmt.pattern):
                self._define(name)
            return _mark_from(out, stmt)
        if isinstance(stmt, Print):
            return _mark_from(Print(self.rewrite_expr(stmt.expr)), stmt)
        if isinstance(stmt, If):
            cond = self.rewrite_expr(stmt.cond)
            then_branch = self.rewrite_stmt(stmt.then_branch)
            else_branch = self.rewrite_stmt(stmt.else_branch) if stmt.else_branch is not None else None
            return _mark_from(If(cond, then_branch, else_branch), stmt)
        if isinstance(stmt, While):
            return _mark_from(While(self.rewrite_expr(stmt.cond), self.rewrite_stmt(stmt.body)), stmt)
        if isinstance(stmt, For):
            self._enter_scope()
            init = self.rewrite_stmt(stmt.init) if stmt.init is not None else None
            cond = self.rewrite_expr(stmt.cond) if stmt.cond is not None else None
            inc = self.rewrite_expr(stmt.inc) if stmt.inc is not None else None
            body = self.rewrite_stmt(stmt.body)
            self._exit_scope()
            return _mark_from(For(init, cond, inc, body), stmt)
        if isinstance(stmt, ForEach):
            iterable = self.rewrite_expr(stmt.iterable)
            self._enter_scope()
            self._define(stmt.name)
            body = self.rewrite_stmt(stmt.body)
            self._exit_scope()
            return _mark_from(ForEach(stmt.name, iterable, body), stmt)
        if isinstance(stmt, Return):
            expr = self.rewrite_expr(stmt.expr) if stmt.expr is not None else None
            return _mark_from(Return(expr), stmt)
        if isinstance(stmt, TryCatch):
            try_block = self.rewrite_stmt(stmt.try_block)
            catch_block = None
            if stmt.catch_block is not None:
                self._enter_scope()
                self._define(stmt.catch_var)
                catch_block = self.rewrite_stmt(stmt.catch_block)
                self._exit_scope()
            finally_block = self.rewrite_stmt(stmt.finally_block) if stmt.finally_block is not None else None
            return _mark_from(TryCatch(try_block, stmt.catch_var, catch_block, finally_block), stmt)
        if isinstance(stmt, Throw):
            return _mark_from(Throw(self.rewrite_expr(stmt.expr)), stmt)
        if isinstance(stmt, FnDef):
            self._define(stmt.name)
            self._enter_scope()
            for param in stmt.params:
                self._define(param.name)
            body = self.rewrite_stmt(stmt.body)
            self._exit_scope()
            return _mark_from(FnDef(stmt.name, stmt.params, body, return_type=stmt.return_type, exported=stmt.exported), stmt)
        if isinstance(stmt, Import):
            return stmt
        if isinstance(stmt, CheckpointStmt):
            return stmt
        return stmt

    def rewrite_expr(self, expr):
        if expr is None:
            return None
        if isinstance(expr, ActionStmt):
            lowered = _lower_action_expr(expr)
            return self.rewrite_expr(lowered)
        if isinstance(expr, (Int, Num, Bool, Str, Nil)):
            return expr
        if isinstance(expr, Var):
            if expr.name in self.state_names and not self._is_local(expr.name):
                return _mark_from(Index(Var(self.state_var), Str(expr.name)), expr)
            return expr
        if isinstance(expr, Assign):
            value = self.rewrite_expr(expr.expr)
            if expr.name in self.state_names and not self._is_local(expr.name):
                if self._is_fold(expr.name):
                    # Refused at compile time, not reinterpreted. `=` names a
                    # final value; a folded cell needs a contribution, and there
                    # is no reading of `counter = seen + 1i` that means "add one"
                    # -- folding final values double-counts (#485).
                    raise LangSyntaxError(
                        f"state '{expr.name}' is declared merge: "
                        f"\"{self.fold_cells[expr.name]}\", so it is written with "
                        f"'{expr.name} += ...' which contributes a value to be "
                        f"folded at the join. A plain '{expr.name} = ...' sets a "
                        f"final value, which cannot be combined with another "
                        f"branch's.",
                        line=_pos(expr)[0],
                        col=_pos(expr)[1],
                    )
                return _mark_from(IndexAssign(Var(self.state_var), Str(expr.name), value), expr)
            return _mark_from(Assign(expr.name, value), expr)
        if isinstance(expr, CompoundAssign):
            value = self.rewrite_expr(expr.expr)
            if expr.name in self.state_names and not self._is_local(expr.name):
                if self._is_fold(expr.name):
                    if expr.op != "+":
                        raise LangSyntaxError(
                            f"state '{expr.name}' is declared merge: "
                            f"\"{self.fold_cells[expr.name]}\", which folds with "
                            f"'+'. '{expr.op}=' has no meaning as a contribution.",
                            line=_pos(expr)[0],
                            col=_pos(expr)[1],
                        )
                    # The contribution is the right-hand side alone. It never
                    # reads the cell, which is what closes the read-modify-write
                    # window two concurrent branches lose an update through.
                    return _mark_from(
                        builtin_call("state_contribute", [Str(expr.name), value]),
                        expr,
                    )
                # `x += e` is `x = x + e` everywhere else in the language, so it
                # lowers to the shape the `Assign` case above already produces.
                # Without this it reached the compiler untouched, resolved as an
                # undeclared local, and read nil (#518).
                cell = _mark_from(Index(Var(self.state_var), Str(expr.name)), expr)
                folded = _mark_from(Bin(expr.op, cell, value), expr)
                return _mark_from(IndexAssign(Var(self.state_var), Str(expr.name), folded), expr)
            return _mark_from(CompoundAssign(expr.name, expr.op, value), expr)
        if isinstance(expr, Unary):
            return _mark_from(Unary(expr.op, self.rewrite_expr(expr.expr)), expr)
        if isinstance(expr, Bin):
            return _mark_from(Bin(expr.op, self.rewrite_expr(expr.a), self.rewrite_expr(expr.b)), expr)
        if isinstance(expr, ListLit):
            return _mark_from(ListLit([self.rewrite_expr(item) for item in expr.items]), expr)
        if isinstance(expr, MapLit):
            return _mark_from(MapLit([(self.rewrite_expr(k), self.rewrite_expr(v)) for k, v in expr.items]), expr)
        if isinstance(expr, RecordLiteral):
            return _mark_from(RecordLiteral([(key, self.rewrite_expr(value)) for key, value in expr.fields]), expr)
        if isinstance(expr, Index):
            return _mark_from(Index(self.rewrite_expr(expr.seq), self.rewrite_expr(expr.index)), expr)
        if isinstance(expr, IndexAssign):
            return _mark_from(IndexAssign(self.rewrite_expr(expr.seq), self.rewrite_expr(expr.index), self.rewrite_expr(expr.value)), expr)
        if isinstance(expr, Attr):
            return _mark_from(Attr(self.rewrite_expr(expr.obj), expr.name), expr)
        if isinstance(expr, FieldAssign):
            return _mark_from(FieldAssign(self.rewrite_expr(expr.obj), expr.name, self.rewrite_expr(expr.value)), expr)
        if isinstance(expr, Call):
            return _mark_from(Call(self.rewrite_expr(expr.callee), [self.rewrite_expr(arg) for arg in expr.args]), expr)
        if isinstance(expr, FnExpr):
            self._enter_scope()
            for param in expr.params:
                self._define(param.name)
            body = self.rewrite_stmt(expr.body)
            self._exit_scope()
            return _mark_from(FnExpr(expr.params, body, return_type=expr.return_type), expr)
        if isinstance(expr, InterpolatedString):
            new_parts = []
            for part in expr.parts:
                if isinstance(part, InterpolationPart):
                    new_parts.append(InterpolationPart(self.rewrite_expr(part.expression)))
                else:
                    new_parts.append(part)
            return _mark_from(InterpolatedString(new_parts), expr)
        return expr
