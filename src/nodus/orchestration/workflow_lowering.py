"""Workflow/goal AST/runtime lowering helpers."""

from __future__ import annotations

from nodus.frontend.ast.ast_nodes import (
    ActionStmt,
    Assign,
    Attr,
    Bin,
    Block,
    Bool,
    Call,
    CheckpointStmt,
    Comment,
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
    Let,
    ListLit,
    ListPattern,
    MapLit,
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
    WorkflowStateDecl,
    WorkflowStep,
)
from nodus.orchestration.task_graph import TaskGraph, TaskNode


WORKFLOW_MARKER = "__workflow__"
GOAL_MARKER = "__goal__"
STEP_OPTION_KEYS = {
    "timeout_ms",
    "retries",
    "retry_delay_ms",
    "cache",
    "cache_key",
    "worker",
    "worker_timeout_ms",
}


def lower_workflow_ast(workflow: WorkflowDef) -> MapLit:
    return _lower_flow_ast(workflow, marker=WORKFLOW_MARKER, execution_kind="workflow")


def lower_goal_ast(goal: GoalDef) -> MapLit:
    return _lower_flow_ast(goal, marker=GOAL_MARKER, execution_kind="goal")


def _lower_flow_ast(flow, *, marker: str, execution_kind: str) -> MapLit:
    state_init = _lower_state_init(flow)
    state_names = [state.name for state in flow.states]
    items = [
        (Str(marker), Str(execution_kind)),
        (Str("name"), Str(flow.name)),
        (Str("execution_kind"), Str(execution_kind)),
        (
            Str("steps"),
            ListLit([_lower_step_ast(step, state_names) for step in flow.steps]),
        ),
    ]
    if state_init is not None:
        items.append((Str("state_init"), state_init))
    if state_names:
        items.append((Str("state_keys"), ListLit([Str(name) for name in state_names])))
    return MapLit(items)


def _lower_state_init(flow: WorkflowDef | GoalDef) -> FnExpr | None:
    if not flow.states:
        return None
    state_var = "__workflow_state"
    state_names = {state.name for state in flow.states}
    rewriter = _StateRewriter(state_names, state_var, initial_locals={state_var})
    stmts = [Let(state_var, MapLit([]))]
    for state in flow.states:
        expr = rewriter.rewrite_expr(state.value)
        assign = IndexAssign(Var(state_var), Str(state.name), expr)
        stmts.append(ExprStmt(assign))
    stmts.append(Return(Var(state_var)))
    return FnExpr([], Block(stmts), return_type=None)


def _lower_step_ast(step: WorkflowStep | GoalStep, state_names: list[str]) -> MapLit:
    state_var = "__workflow_state"
    body = step.body
    rewriter = _StateRewriter(set(state_names), state_var, initial_locals=set(step.deps) | ({state_var} if state_names else set()))
    rewritten_body = rewriter.rewrite_stmt(body)
    if state_names:
        prelude = Let(state_var, Call(Var("workflow_state"), []))
        body_stmts = rewritten_body.stmts if isinstance(rewritten_body, Block) else [rewritten_body]
        rewritten_body = Block([prelude] + body_stmts)
    body = _return_last_action(rewritten_body)
    return MapLit(
        [
            (Str("name"), Str(step.name)),
            (Str("deps"), ListLit([Str(dep) for dep in step.deps])),
            (Str("fn"), FnExpr([Param(dep) for dep in step.deps], body, return_type=None)),
            (Str("options"), step.options if step.options is not None else MapLit([])),
        ]
    )


def _return_last_action(body: object) -> Block:
    if not isinstance(body, Block) or not body.stmts:
        return body if isinstance(body, Block) else Block([body])
    last = body.stmts[-1]
    if isinstance(last, ExprStmt) and isinstance(last.expr, Call) and _is_action_builtin(last.expr):
        stmts = list(body.stmts[:-1]) + [Return(last.expr)]
        return _mark_from(Block(stmts), body)
    return body


def _is_action_builtin(expr: Call) -> bool:
    return isinstance(expr.callee, Var) and expr.callee.name in {
        "__action_tool",
        "__action_agent",
        "__action_memory_put",
        "__action_memory_get",
        "__action_emit",
    }


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
            step_name=step_name,
        )
        tasks.append(task)
        resolved[step_name] = task
        step_to_task[step_name] = task_id

    for step_name, step in ordered:
        deps = step.get("deps", [])
        if not isinstance(deps, list):
            vm.runtime_error("type", f"Workflow step '{step_name}' deps must be a list")
        dep_nodes = []
        for dep in deps:
            if not isinstance(dep, str):
                vm.runtime_error("type", f"Workflow step '{step_name}' dependency names must be strings")
            dep_task = resolved.get(dep)
            if dep_task is None:
                vm.runtime_error("runtime", f"Workflow step '{step_name}' references unknown dependency '{dep}'")
            dep_nodes.append(dep_task)
        resolved[step_name].dependencies = dep_nodes

    metadata = {
        "workflow_name": name,
        "execution_kind": kind,
        "step_to_task": step_to_task,
        "task_to_step": {task_id: step for step, task_id in step_to_task.items()},
        "workflow_source_path": getattr(vm, "source_path", None),
        "workflow_source_code": getattr(vm, "source_code", None),
    }
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


def _number_option(vm, options: dict, key: str, step_name: str, default=None):
    value = options.get(key, default)
    if value is None:
        return None
    return vm.ensure_number(value, f"workflow step '{step_name}' option {key}")


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
        return _mark_from(Call(Var("__action_tool"), [target, expr.payload if expr.payload is not None else MapLit([])]), expr)
    if expr.kind == "agent":
        return _mark_from(Call(Var("__action_agent"), [target, expr.payload if expr.payload is not None else MapLit([])]), expr)
    if expr.kind == "memory_put":
        return _mark_from(Call(Var("__action_memory_put"), [target, expr.payload if expr.payload is not None else Nil()]), expr)
    if expr.kind == "memory_get":
        return _mark_from(Call(Var("__action_memory_get"), [target]), expr)
    if expr.kind == "emit":
        return _mark_from(Call(Var("__action_emit"), [target, expr.payload if expr.payload is not None else MapLit([])]), expr)
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

    def __init__(self, state_names: set[str], state_var: str, initial_locals: set[str] | None = None):
        self.state_names = set(state_names)
        self.state_var = state_var
        self.scopes: list[set[str]] = [set(initial_locals or set())]

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
            self._enter_scope()
            self._define(stmt.catch_var)
            catch_block = self.rewrite_stmt(stmt.catch_block)
            self._exit_scope()
            return _mark_from(TryCatch(try_block, stmt.catch_var, catch_block), stmt)
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
        if isinstance(expr, (Num, Bool, Str, Nil)):
            return expr
        if isinstance(expr, Var):
            if expr.name in self.state_names and not self._is_local(expr.name):
                return _mark_from(Index(Var(self.state_var), Str(expr.name)), expr)
            return expr
        if isinstance(expr, Assign):
            value = self.rewrite_expr(expr.expr)
            if expr.name in self.state_names and not self._is_local(expr.name):
                return _mark_from(IndexAssign(Var(self.state_var), Str(expr.name), value), expr)
            return _mark_from(Assign(expr.name, value), expr)
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
        return expr
