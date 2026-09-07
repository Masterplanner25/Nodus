"""Workflow/goal AST/runtime lowering helpers."""

from __future__ import annotations

from typing import Any

from nodus.builtins.nodus_builtins import BUILTIN_CALL_PREFIX
from nodus.runtime.diagnostics import LangSyntaxError
from nodus.frontend.ast.ast_nodes import (
    builtin_call,
    pattern_names,
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
    MapLit,
    Int,
    Nil,
    Num,
    Param,
    Print,
    RecordLiteral,
    Return,
    Str,
    Throw,
    TryCatch,
    Unary,
    Var,
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
    # #578: readers of this cell wait for every step that writes it. A join
    # written on the data rather than on the step side -- `step d after b, c`
    # says the same thing when the author remembers every writer.
    "barrier",
}


STEP_OPTION_KEYS = {
    # #479: the step's declared output type. Static-only, like every other
    # annotation -- `nodus check` verifies it and the VM stays dynamically typed.
    # In a workflow whose whole point is that steps are separable units run out
    # of order and across processes, this is the boundary most worth typing, and
    # it was the one carrying no contract at all.
    "returns",
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
                    (Str("max_iterations"), pursuit.budget.max_iterations
                     if pursuit.budget.max_iterations is not None else Nil()),
                    (Str("deadline_ms"), pursuit.budget.deadline_ms
                     if pursuit.budget.deadline_ms is not None else Nil()),
                    # #488: host-registered meters. Data, like the rest of the
                    # budget, so the bound is inspectable before the goal runs.
                    (Str("limits"), pursuit.budget.limits
                     if pursuit.budget.limits is not None else MapLit([])),
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


def _barrier_cells(flow) -> set[str]:
    """Cells declaring `barrier: true`, read out of the `with { ... }` literal.

    A literal for the same reason `merge:` is one: it decides at compile time
    whether this program's steps gain edges, so it cannot be computed. A
    computed or non-`true` value is refused where it is written rather than
    silently read as "not a barrier" -- the #490 rule that an accepted-and-
    ignored third state is the worst of the three.
    """
    cells: set[str] = set()
    for state in flow.states:
        options = getattr(state, "options", None)
        if not isinstance(options, MapLit):
            continue
        for key_node, value_node in options.items:
            if not (isinstance(key_node, Str) and key_node.v == "barrier"):
                continue
            if not (isinstance(value_node, Bool) and value_node.v is True):
                raise LangSyntaxError(
                    f"state '{state.name}' barrier: must be the literal `true`. "
                    "It decides at compile time which steps this flow's readers "
                    "wait for, so it cannot be computed, and a cell that is not "
                    "a barrier should omit the key rather than say `false`.",
                    line=_pos(state)[0],
                    col=_pos(state)[1],
                )
            cells.add(state.name)
    return cells


def _writes_unconditionally(step, cell: str) -> bool:
    """Does *step* write *cell* on every pass it runs?

    Deliberately conservative, and the definition is #500's verbatim: a write
    that is a direct statement of an unguarded step body. One nested in an `if`,
    a loop or a `match` arm may not run, and a step carrying `when` may not run
    at all.

    That conservatism is the decision #578 settled. A barrier whose writer takes
    the other branch would deadlock its readers, and a may-write analysis that
    guessed would turn a scheduling accident into a correctness one. Refusing
    the shape is checkable today and mirrors two shipped precedents -- #500's
    unconditional-waypoint check and `merge:` policy validation.
    """
    if getattr(step, "when", None) is not None:
        return False
    body = getattr(step, "body", None)
    stmts = getattr(body, "stmts", None)
    if stmts is None and isinstance(body, list):
        stmts = body
    for stmt in stmts or []:
        target = stmt.expr if isinstance(stmt, ExprStmt) else stmt
        if isinstance(target, (Assign, CompoundAssign)) and getattr(target, "name", None) == cell:
            return True
        if isinstance(target, (IndexAssign, FieldAssign)):
            base = getattr(target, "seq", None) or getattr(target, "obj", None)
            while isinstance(base, (Index, Attr)):
                base = getattr(base, "seq", None) or getattr(base, "obj", None)
            if isinstance(base, Var) and base.name == cell:
                return True
    return False


def _collect_usage(lower_steps):
    """Run the lowering once purely to learn what each step body touches.

    The lowered maps are discarded. Any `LangSyntaxError` a body deserves is
    raised here instead of on the second pass, which changes nothing a caller
    can see -- it is the same error from the same source position.
    """
    usage: dict[str, tuple[frozenset[str], frozenset[str]]] = {}
    lower_steps(usage)
    return usage


def _lower_flow_ast(flow, *, marker: str, execution_kind: str) -> MapLit:
    state_init = _lower_state_init(flow)
    state_names = [state.name for state in flow.states]
    fold_cells = _fold_cells(flow)
    barrier_cells = _barrier_cells(flow)
    param_names = [param.name for param in getattr(flow, "params", []) or []]
    tracked_cells = set(fold_cells) | barrier_cells
    cell_usage: dict[str, tuple[frozenset[str], frozenset[str]]] = {}

    def lower_steps(usage, inferred=None):
        return [
            _lower_step_ast(
                step, state_names, fold_cells,
                flow_name=flow.name, param_names=param_names,
                cell_usage=usage, tracked_cells=tracked_cells,
                extra_deps=(inferred or {}).get(step.name),
            )
            for step in flow.steps
        ]

    # #578: a barrier adds edges, so `step.deps` must be final *before* the
    # steps are lowered -- the lowered map carries `deps` as data and nothing
    # downstream re-reads the AST. Which cells a body touches is only known by
    # walking it, so a flow declaring a barrier is lowered twice: once to learn,
    # once for real. The learning pass is this same function rather than a
    # cheaper bespoke walk, because "what does this step body do with state
    # cells" answered twice is the shape `--shapes` reports, and a second
    # implementation would drift from the rewriter it is meant to mirror.
    #
    # Only barrier flows pay it. A `merge:`-only flow refuses after lowering and
    # never mutates deps, so its single pass is unchanged.
    inferred_edges: dict[str, list[str]] = {}
    if barrier_cells:
        inferred_edges = _apply_barriers(flow, _collect_usage(lower_steps), barrier_cells)

    items: list[tuple[object, object]] = [
        (Str(marker), Str(execution_kind)),
        (Str("name"), Str(flow.name)),
        (Str("execution_kind"), Str(execution_kind)),
        (Str("steps"), ListLit(lower_steps(cell_usage, inferred_edges))),
    ]
    _validate_fold_reads(flow, cell_usage, fold_cells, inferred_edges)
    if inferred_edges:
        # Recorded because an edge nobody wrote should still be visible to
        # whoever asks why a step waited. `graph_topology` (#470) is the
        # precedent for derived structure travelling in the flow map.
        items.append((
            Str("inferred_edges"),
            MapLit([
                (Str(name), ListLit([Str(dep) for dep in deps]))
                for name, deps in sorted(inferred_edges.items())
            ]),
        ))
    # #481: declared, so the runner can refuse an unknown or missing argument
    # rather than leaving a step to read `nil`. Data on the flow map, like
    # `state_keys` -- it has to survive to the runner, which never sees the AST.
    if param_names:
        items.append((Str("params"), ListLit([Str(name) for name in param_names])))
    if state_init is not None:
        items.append((Str("state_init"), state_init))
    if state_names:
        items.append((Str("state_keys"), ListLit([Str(name) for name in state_names])))
        policies = _lower_state_policies(flow)
        if policies is not None:
            items.append((Str("state_policies"), policies))
    return MapLit(items)


def _cell_relation(flow, cell_usage, inferred=None):
    """Who writes each cell, and what is already finished before each step.

    The relation both `merge:` and `barrier:` are asking about, computed once.
    They differ only in the **response** to the answer -- a fold refuses a
    reader that would see a partial value, a barrier gives it the edges instead
    -- and answering "which steps must finish before this reader" in two places
    is the shape `nodus_gate --shapes` reports.

    Two node kinds are deliberately not writers, and the reasoning is #722's:

    - A **compensation** step is excluded from the forward graph by declaration
      (#577), so no forward reader can name it in `after` and its writes land
      during unwinding. Counting it would make every read unsatisfiable.
    - An **`each`-mapped** step needs no special case: `each x in src` implies
      `after src` and the parser adds it, so the writer set stays a set of step
      *names* however many instances run.
    """
    forward = [s for s in flow.steps if getattr(s, "compensates", None) is None]
    writers: dict[str, set[str]] = {}
    for step in forward:
        _reads, writes = cell_usage.get(step.name, (frozenset(), frozenset()))
        for cell in writes:
            writers.setdefault(cell, set()).add(step.name)

    # #578: a barrier's inferred edges count as ordering here. Without them a
    # cell declaring both `merge:` and `barrier:` is refused by the fold check
    # for a join that was just inferred -- which is exactly what composing them
    # is supposed to avoid, and what a stale bytecode cache hid on the first
    # attempt at this.
    inferred = inferred or {}
    direct = {
        s.name: set(s.deps or []) | set(inferred.get(s.name, ()))
        for s in forward
    }
    finished: dict[str, set[str]] = {}

    def upstream(name: str, seen: frozenset[str] = frozenset()) -> set[str]:
        if name in finished:
            return finished[name]
        if name in seen:      # a cycle is #396's error, not this one's
            return set()
        out: set[str] = set()
        for dep in direct.get(name, ()):  # an unknown dep is reported elsewhere
            out.add(dep)
            out |= upstream(dep, seen | {name})
        finished[name] = out
        return out

    return forward, writers, upstream


def _missing_writers(step, cell, writers, upstream) -> list[str]:
    """Writers of *cell* that are not already finished when *step* runs.

    Transitive, because `after b` where `b after a` already orders `a`. The
    reader needs the contributors *finished*, not named directly -- demanding a
    direct edge would refuse (or redundantly re-edge) correct programs. A step
    never waits for itself: a `+=` both reads and writes.
    """
    return sorted(writers.get(cell, set()) - upstream(step.name) - {step.name})


def _apply_barriers(flow, cell_usage, barrier_cells) -> dict[str, list[str]]:
    """Give every reader of a barrier cell an edge to each of its writers (#578).

    The inference half. `step d after b, c` says this already when the author
    remembers every writer; a barrier says it once, on the cell, and cannot
    forget one. Edges are added to `step.deps`, so everything downstream --
    graph construction, `parallel_groups`, resume validation, `graph_topology`
    (#470) -- sees ordinary dependencies and needs no barrier concept.

    Returns the inferred edges per step, for the run metadata: an edge nobody
    wrote should still be visible to someone reading why a step waited.
    """
    if not barrier_cells:
        return {}
    forward, writers, upstream = _cell_relation(flow, cell_usage)

    # The decided rule (#578): a barrier's writers must write unconditionally,
    # refused at declaration. A conditional writer makes the writer set
    # statically unknown, and the two alternatives are worse -- a may-write
    # analysis that guesses, or a deadlock when the other branch is taken.
    for cell in sorted(barrier_cells):
        for name in sorted(writers.get(cell, set())):
            step = next(s for s in forward if s.name == name)
            if _writes_unconditionally(step, cell):
                continue
            guarded = getattr(step, "when", None) is not None
            why = (
                "the step carries a `when` guard, so it may not run at all"
                if guarded else
                "the write is inside an `if`, a loop or a `match` arm, so it "
                "may not happen on a pass the step does run"
            )
            raise LangSyntaxError(
                f"step '{name}' writes state '{cell}', declared barrier: true, "
                f"but not on every pass: {why}. A barrier's readers wait for "
                f"every declared writer, so a writer that may not write leaves "
                f"them waiting for something that never comes. Write '{cell}' "
                f"as a plain statement of the step body -- assign a neutral "
                f"value on the branch that has nothing to say -- or drop "
                f"barrier: true and join the writers with `after`.",
                line=_pos(step)[0],
                col=_pos(step)[1],
            )

    inferred: dict[str, list[str]] = {}
    for step in forward:
        reads, _writes = cell_usage.get(step.name, (frozenset(), frozenset()))
        added: set[str] = set()
        for cell in sorted(reads & barrier_cells):
            added |= set(_missing_writers(step, cell, writers, upstream))
        if not added:
            continue
        # Sorted so the lowered program is deterministic: the same source must
        # produce the same bytecode, which the content-keyed cache (#704) and
        # the golden bytecode fixtures both depend on.
        #
        # Returned rather than written back to `step.deps`. Mutating the AST
        # made lowering **non-idempotent**: a second lowering of the same tree
        # saw the edges already present, inferred nothing, and so ran no cycle
        # check -- the edges survived and the error did not. The CLI lowers
        # twice, so a barrier cycle reached the runtime as `Dependency cycle
        # detected` naming a join nobody wrote. The AST is shared; deriving
        # from it must not change it.
        inferred[step.name] = sorted(added)
    _refuse_inferred_cycle(forward, inferred)
    return inferred


def _refuse_inferred_cycle(forward, inferred) -> None:
    """A cycle an inferred edge created is reported here, not at run time (#578).

    The runtime already detects cycles and says `Dependency cycle detected:
    a -> b -> a` (#396) -- verified, and a barrier-induced cycle reaches it
    identically. That message is the problem: it names a join the author never
    wrote, so the obvious next move is to search the source for `after b` and
    find nothing.

    Only a cycle **containing an inferred edge** is refused here. One the author
    wrote is still the runtime's to report, because reporting it earlier would
    change behaviour for programs this feature has nothing to do with.
    """
    if not inferred:
        return
    deps = {
        s.name: list(s.deps or []) + inferred.get(s.name, [])
        for s in forward
    }
    state: dict[str, int] = {}
    stack: list[str] = []

    def walk(name: str):
        if state.get(name) == 2:
            return None
        if state.get(name) == 1:
            return stack[stack.index(name):] + [name]
        state[name] = 1
        stack.append(name)
        for dep in deps.get(name, ()):
            if dep not in deps:      # an unknown dep is reported elsewhere
                continue
            found = walk(dep)
            if found:
                return found
        stack.pop()
        state[name] = 2
        return None

    for start in sorted(deps):
        cycle = walk(start)
        if not cycle:
            continue
        culprits = [
            (b, a) for a, b in zip(cycle, cycle[1:]) if b in inferred.get(a, ())
        ]
        if not culprits:
            return       # the author wrote this one; the runtime reports it
        writer, reader = culprits[0]
        step = next(s for s in forward if s.name == reader)
        chain = " -> ".join(reversed(cycle))
        raise LangSyntaxError(
            f"barrier cells make step '{reader}' wait for '{writer}', which "
            f"closes a dependency cycle: {chain}. '{reader}' reads a barrier "
            f"cell that '{writer}' writes, and following the same rule back "
            f"again returns here. Two steps cannot each wait for the other's "
            f"value: drop barrier: true from one of the cells and order those "
            f"steps with `after`, or split the cell so each step reads one it "
            f"does not write into.",
            line=_pos(step)[0],
            col=_pos(step)[1],
        )


def _validate_fold_reads(flow, fold_usage, fold_cells, inferred=None) -> None:
    """A reader of a folded cell must join every step that contributes to it (#722).

    `merge:` (#485) fixed *lost* writes -- the final value is right. What it did
    not close is that a reader which does not depend on every contributor
    observes an **intermediate** value, silently, and which one depends on
    scheduling: the same program printed `1` with a slow producer and `3` with a
    fast one. A wrong answer that changes with the machine is worse than a wrong
    answer, because a test can pass on the box that wrote it.

    Refused rather than warned, matching what this rewriter already does to a
    plain `=` on a folded cell, `merge:` policy validation, and #500's
    unconditional-checkpoint check. The reader cannot mean "some of the
    contributions": there is no ordering that makes a partial fold the intended
    value, so there is nothing to preserve by allowing it.

    **This is the refusing response to `_cell_relation`; `_apply_barriers` is
    the inferring one.** A folded cell that also declares `barrier: true` has
    had its edges added before this runs, so it has nothing left to refuse --
    which is the point of composing them (#578).
    """
    if not fold_usage:
        return
    _forward, writers, upstream = _cell_relation(flow, fold_usage, inferred)
    if not writers:
        return

    for step in (s for s in flow.steps if getattr(s, "compensates", None) is None):
        reads, _writes = fold_usage.get(step.name, (frozenset(), frozenset()))
        for cell in sorted(reads & set(fold_cells)):
            missing = _missing_writers(step, cell, writers, upstream)
            if not missing:
                continue
            joined = ", ".join(f"'{n}'" for n in missing)
            plural = "steps" if len(missing) > 1 else "step"
            verb = "contribute" if len(missing) > 1 else "contributes"
            raise LangSyntaxError(
                f"step '{step.name}' reads state '{cell}', declared "
                f"merge: \"{fold_cells.get(cell)}\", but does not run after "
                f"{plural} {joined}, which also {verb} to it. It would read "
                f"a partial fold, and which one depends on scheduling. Add "
                f"{joined} to '{step.name}'s dependencies, declare the cell "
                f"barrier: true so the edges are inferred, or read the cell "
                f"from the run result after the flow completes.",
                line=_pos(step)[0],
                col=_pos(step)[1],
            )


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
    param_names: list[str] | None = None,
    cell_usage: dict[str, tuple[frozenset[str], frozenset[str]]] | None = None,
    tracked_cells: set[str] | None = None,
    extra_deps: list[str] | None = None,
) -> MapLit:
    state_var = "__workflow_state"
    params = list(param_names or [])
    body = step.body
    step_each_var = getattr(step, "each_var", None)
    each_locals: set[str] = {step_each_var} if isinstance(step_each_var, str) else set()
    rewriter = _StateRewriter(
        set(state_names),
        state_var,
        # #481: parameters are locals from the body's first line, so the state
        # rewriter must not mistake a read of one for a state-cell read.
        initial_locals=(
            set(step.deps)
            | set(params)
            # #480: the loop variable is a parameter of the step body, so a read
            # of it is not a state-cell read.
            | each_locals
            | ({state_var} if state_names else set())
        ),
        fold_cells=fold_cells,
        tracked_cells=tracked_cells,
    )
    rewritten_body = rewriter.rewrite_stmt(body)
    if cell_usage is not None:
        # #722. Collected from the walk that just happened, not a second one.
        cell_usage[step.name] = (
            frozenset(rewriter.cell_reads),
            frozenset(rewriter.cell_writes),
        )
    prelude_stmts: list[object] = []
    if state_names:
        prelude_stmts.append(Let(state_var, builtin_call("workflow_state", [])))
    # #481: bound from the run rather than passed as a closure argument. That is
    # what makes a parameter durable by construction -- the value comes from the
    # run record on a resume too, so it cannot be re-derived into something else
    # the way a module-level `let` read inside a step could be.
    for name in params:
        prelude_stmts.append(Let(name, builtin_call("workflow_arg", [Str(name)])))
    if prelude_stmts:
        body_stmts = rewritten_body.stmts if isinstance(rewritten_body, Block) else [rewritten_body]
        rewritten_body = Block(prelude_stmts + body_stmts)
    body = _return_last_action(rewritten_body)
    # #480: a mapped step's body is called once per item, so the producer's
    # parameter slot carries the *item* rather than the list. Substituting in
    # place keeps arity and ordering identical to a plain step, which is what
    # lets the existing arity check and the runner's positional dependency
    # passing work unchanged.
    each_var = getattr(step, "each_var", None)
    each_source = getattr(step, "each_source", None)
    fn_params = [
        each_var if (each_var is not None and dep == each_source) else dep
        for dep in step.deps
    ]
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
                [Param(name) for name in fn_params],
                body,
                return_type=None,
                step_owner=f"{flow_name}.{step.name}" if flow_name else step.name,
            ),
        ),
        (Str("options"), step.options if step.options is not None else MapLit([])),
    ]
    if extra_deps:
        # #578: barrier edges are ordering **only**, and deliberately not `deps`.
        # A dep is also a parameter -- `step d after b, c` binds b and c as
        # locals and the arity check requires one per dep -- so an inferred edge
        # in `deps` would change the step's signature and reject a body the
        # author wrote correctly. A barrier reader takes its value from the cell,
        # not from an upstream return, so it needs the edge and nothing else.
        #
        # Appended only when there is something to say, like `each` and
        # `compensates` below. A key on every step would change the lowered
        # shape -- and the emitted bytecode -- of every workflow ever written,
        # including the ones with no barrier in them; three golden fixtures said
        # so. A feature nobody used should cost nothing.
        items.append((
            Str("order_after"),
            ListLit([Str(dep) for dep in extra_deps]),
        ))
    if each_var is not None:
        # Data on the step map, like `when` and `deps` -- the runner never sees
        # the AST, and `plan_workflow` should be able to show that this node
        # fans out before anything runs.
        items.append((Str("each"), MapLit([
            (Str("var"), Str(each_var)),
            (Str("source"), Str(each_source or "")),
        ])))
    compensates = getattr(step, "compensates", None)
    if compensates is not None:
        # #577: data on the step map, like `each` and `when`. The runner never
        # sees the AST, and `plan_workflow` should be able to show that this node
        # is a compensation handler -- excluded from the forward graph -- before
        # anything runs.
        items.append((Str("compensates"), Str(compensates)))
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


def workflow_to_graph(vm, workflow_value, *, init_state: bool = False, task_ids_by_step: dict[str, str] | None = None, args=None, prebound_args: dict | None = None, require_args: bool = True) -> TaskGraph:
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
    # #577: compensation handlers, by handler name. Kept off the forward graph
    # and carried on the TaskGraph so the unwind can reach them.
    handlers: dict[str, Any] = {}
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
        # #577: a compensation handler is reachable only as a handler, so it is
        # not a node in the forward graph. Excluded here rather than filtered
        # later, so nothing downstream has to know the difference -- `deps`,
        # readiness and the run's verdict all see the forward graph only.
        if isinstance(step.get("compensates"), str):
            handlers[step_name] = step
            continue
        each_raw = step.get("each") if isinstance(step.get("each"), dict) else None
        each_source_name = None
        if each_raw is not None:
            each_source_name = each_raw.get("source")
            if not isinstance(each_source_name, str) or not each_source_name:
                vm.runtime_error("type", f"Workflow step '{step_name}' has an invalid `each` source")
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
            each_source=each_source_name,
        )
        tasks.append(task)
        resolved[step_name] = task
        step_to_task[step_name] = task_id

    for step_name, step in ordered:
        if step_name in handlers:
            continue
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
        # #578: ordering-only edges, appended after the arity-bearing deps so a
        # step's parameters still line up with `deps` alone.
        order_after = step.get("order_after", []) or []
        if not isinstance(order_after, list):
            vm.runtime_error("type", f"Workflow step '{step_name}' order_after must be a list")
        for dep in order_after:
            dep_task = resolved.get(dep) if isinstance(dep, str) else None
            if dep_task is None:
                vm.runtime_error(
                    "runtime",
                    f"Workflow step '{step_name}' waits on unknown step '{dep}'",
                )
            if dep_task not in dep_nodes:
                dep_nodes.append(dep_task)
        resolved[step_name].dependencies = dep_nodes

    # #499: the stored source is the cross-process rebuild handle -- and a
    # verbatim copy of the whole module, persisted under `.nodus/graphs/`. An
    # embedder running code it did not author can opt out
    # (`NodusRuntime(persist_workflow_source=False)`); the marker below keeps
    # the rebuild's explanation accurate when it later reads from disk.
    _persist_source = getattr(vm, "persist_workflow_source", True)
    # #481: a rebuild reads the arguments back from the run record rather
    # than re-binding them -- that is what makes a parameter durable, and it
    # is also why a resume does not need the caller to pass them again.
    if prebound_args is not None:
        bound_args = dict(prebound_args)
    else:
        bound_args = _bind_flow_args(
            vm, workflow_value, name, kind, args, require=require_args
        )
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
        # #481: part of run identity, next to `workflow_topology` and for the
        # same reason -- a run resumed with different arguments is as wrong as
        # one resumed against different source.
        "workflow_args": bound_args,
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

    return TaskGraph(tasks, metadata=metadata, compensation_handlers=handlers)


def _bind_flow_args(vm, workflow_value, flow_name: str, kind: str | None, args, *, require: bool = True) -> dict:
    """Check the caller's arguments against the declared parameters (#481).

    Refused where they are written rather than left to a step reading `nil`.
    That is the whole point of declaring them: the module-global workaround this
    replaces failed silently, and its worst property was that the *spelling*
    silently decided whether the value survived a resume.
    """
    from nodus.vm.types import Record

    declared = workflow_value.get("params")
    declared_names = [n for n in declared if isinstance(n, str)] if isinstance(declared, list) else []
    entry = "run_goal" if kind == "goal" else "run_workflow"

    if args is None:
        # `plan_workflow` asks about shape, not values, so a parameterised flow
        # stays plannable without arguments (#481).
        if declared_names and require:
            vm.runtime_error(
                "call",
                f"{kind} '{flow_name}' declares parameter(s) "
                f"{', '.join(repr(n) for n in declared_names)} but none were given. "
                f"Pass them as a map: {entry}({flow_name}, {{{declared_names[0]}: ...}})",
            )
        return {}

    # `{mode: "lite"}` is a *record* (unquoted keys) and `{"mode": "lite"}` is a
    # map. Named arguments read naturally as the first, and `with { ... }` on a
    # step already uses that spelling, so both are accepted -- but a record is
    # normalised to a plain map here, because the bound arguments go into run
    # metadata and a Record is not JSON serializable (the persist-time failure
    # that makes `state` reject records).
    if isinstance(args, Record):
        args = dict(args.fields)
    if not isinstance(args, dict):
        vm.runtime_error(
            "type",
            f"{entry}({flow_name}, args) expects args as a map or record, "
            f'e.g. {{{declared_names[0] if declared_names else "name"}: value}}',
        )
    if not declared_names:
        vm.runtime_error(
            "call",
            f"{kind} '{flow_name}' declares no parameters, so it takes no "
            f"arguments. Declare them: `{kind} {flow_name}(name) {{ ... }}`",
        )

    given = set(args)
    expected = set(declared_names)
    unknown = sorted(given - expected)
    if unknown:
        vm.runtime_error(
            "call",
            f"{kind} '{flow_name}' has no parameter(s) "
            f"{', '.join(repr(n) for n in unknown)}. It declares: "
            f"{', '.join(repr(n) for n in declared_names)}",
        )
    missing = sorted(expected - given)
    if missing:
        vm.runtime_error(
            "call",
            f"{kind} '{flow_name}' is missing argument(s) "
            f"{', '.join(repr(n) for n in missing)}",
        )
    return {name: args[name] for name in declared_names}


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
        tracked_cells: set[str] | None = None,
    ):
        self.state_names = set(state_names)
        self.state_var = state_var
        self.scopes: list[set[str]] = [set(initial_locals or set())]
        # cell -> its fold policy, for cells declaring `merge: "sum"` / `"append"`.
        # A fold changes what a write *means*, so `=` and `+=` lower differently
        # for these and the difference is decided here, at compile time, rather
        # than by a runtime branch inside the write.
        self.fold_cells = dict(fold_cells or {})
        # #722: which folded cells this step body reads and which it contributes
        # to. Recorded here rather than by a second walk because this rewriter
        # already visits every reference -- a `Var` naming a cell is the read
        # site and `CompoundAssign` is the contribution site, and it already
        # tells folded cells from plain ones. A separate analysis pass would be
        # two implementations of "what does this step body do with state cells",
        # which is the shape `nodus_gate --shapes` reports.
        # #578: which cells' accesses are recorded at all. A superset of the
        # fold cells -- a `barrier:` cell needs the same reader/writer relation
        # without folding. Kept as one set because "what does this body do with
        # state cells" is one question; what *differs* is the response to the
        # answer, which lives in `_relate_cell_access`.
        self.tracked_cells: set[str] = set(tracked_cells or ()) | set(self.fold_cells)
        self.cell_reads: set[str] = set()
        self.cell_writes: set[str] = set()

    def _is_fold(self, name: str) -> bool:
        return name in self.fold_cells and not self._is_local(name)

    def _is_tracked(self, name: str) -> bool:
        return name in self.tracked_cells and not self._is_local(name)

    def _record_container_write(self, target) -> None:
        """`x["k"] = v` and `x.f = v` mutate the cell `x`, so they are writes.

        #518 is the reason this is a method rather than a line in one branch:
        that bug was an enumeration of assignment forms missing a member, and
        `ASSIGNMENT_FORMS` in `ast_nodes` names all four. `Assign` and
        `CompoundAssign` record at their own sites because they also decide how
        the write lowers; these two only need recording, and recording them in
        one place is what keeps a third container form from being forgotten.

        Rewriting the base separately records the *read* -- mutating a map means
        reading the cell to reach it -- so only the write is added here.
        """
        while isinstance(target, (Index, Attr)):
            target = getattr(target, "seq", None) or getattr(target, "obj", None)
        if isinstance(target, Var) and self._is_tracked(target.name):
            self.cell_writes.add(target.name)

    def _rewrite_mutation_target(self, target):
        """Rewrite the base of `cell[i] = v` / `cell.f = v` into a tracked write (#822).

        `rewrite_expr` turns a cell reference into `Index(Var(__state), name)`,
        which is a *read*. For an ordinary reference that is right. For the base
        of a container mutation it is not: the mutation then changes the object
        the cell holds without `TrackedState.__setitem__` ever being called, so
        nothing records that this step wrote the cell. Two concurrent indexed
        writes lost one silently -- no conflict warning, no `merge:` policy, and
        nothing for #547's staged error to fire on -- while the plain
        `cell = v` spelling one line away had all three.

        `_record_container_write` already treats these as writes for #578's
        barrier inference, which is compile-time. This is the runtime half.

        The chain is rewritten from the root outwards so `cell["a"][0] = v`
        works at any depth: only the innermost cell read is replaced, and every
        index expression along the way is rewritten normally.
        """
        if (
            isinstance(target, Var)
            and target.name in self.state_names
            and not self._is_local(target.name)
        ):
            return _mark_from(
                builtin_call("state_open_for_write", [Str(target.name)]), target
            )
        if isinstance(target, Index):
            return _mark_from(
                Index(
                    self._rewrite_mutation_target(target.seq),
                    self.rewrite_expr(target.index),
                ),
                target,
            )
        if isinstance(target, Attr):
            return _mark_from(
                Attr(self._rewrite_mutation_target(target.obj), target.name), target
            )
        return self.rewrite_expr(target)

    def _refuse_container_write_to_fold_cell(self, target, expr) -> None:
        """A fold cell cannot be set, whichever spelling is used.

        `acc = [1i]` on a `merge: "append"` cell is refused at declaration --
        a final value cannot be combined with another branch's contribution.
        `acc[0] = 1i` was accepted and silently set it, which is the same hole
        the rest of this fix closes, one level up.
        """
        root = target
        while isinstance(root, (Index, Attr)):
            root = getattr(root, "seq", None) or getattr(root, "obj", None)
        if isinstance(root, Var) and root.name in self.state_names and not self._is_local(root.name):
            if self._is_fold(root.name):
                raise LangSyntaxError(
                    f"state '{root.name}' is declared merge: "
                    f"\"{self.fold_cells[root.name]}\", so it is written by "
                    f"contribution, not by mutation. "
                    f"'{root.name}[...] = ...' would set the cell behind the "
                    f"fold; use '{root.name} += ...' to contribute a value that "
                    f"is combined at the join.",
                    line=_pos(expr)[0],
                    col=_pos(expr)[1],
                )

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
            for name in pattern_names(stmt.pattern):
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
                if self._is_tracked(expr.name):
                    self.cell_reads.add(expr.name)
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
                # #578: a plain `=` is how a barrier cell is written. A fold
                # cell never reaches here -- the branch above refuses it -- so
                # this records exactly the non-fold tracked writes.
                if self._is_tracked(expr.name):
                    self.cell_writes.add(expr.name)
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
                    # window two concurrent branches lose an update through --
                    # and is why this is recorded as a write and not also a read
                    # (#722).
                    self.cell_writes.add(expr.name)
                    return _mark_from(
                        builtin_call("state_contribute", [Str(expr.name), value]),
                        expr,
                    )
                # `x += e` is `x = x + e` everywhere else in the language, so it
                # lowers to the shape the `Assign` case above already produces.
                # Without this it reached the compiler untouched, resolved as an
                # undeclared local, and read nil (#518).
                #
                # #578: for a tracked cell this is a write *and* a read -- it
                # reads the cell to fold the operand in. Both are recorded; a
                # step that reads what it writes is excluded from its own
                # barrier edges rather than being left out of the sets.
                if self._is_tracked(expr.name):
                    self.cell_writes.add(expr.name)
                    self.cell_reads.add(expr.name)
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
            self._refuse_container_write_to_fold_cell(expr.seq, expr)
            self._record_container_write(expr.seq)
            return _mark_from(IndexAssign(self._rewrite_mutation_target(expr.seq), self.rewrite_expr(expr.index), self.rewrite_expr(expr.value)), expr)
        if isinstance(expr, Attr):
            return _mark_from(Attr(self.rewrite_expr(expr.obj), expr.name), expr)
        if isinstance(expr, FieldAssign):
            self._refuse_container_write_to_fold_cell(expr.obj, expr)
            self._record_container_write(expr.obj)
            return _mark_from(FieldAssign(self._rewrite_mutation_target(expr.obj), expr.name, self.rewrite_expr(expr.value)), expr)
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
