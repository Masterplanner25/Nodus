"""AST node definitions for Nodus."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nodus.frontend.lexer import Tok


@dataclass(kw_only=True)
class Base:
    """Base class for all AST nodes.

    All AST nodes carry two optional metadata fields:

    _tok:    The source token where this node was parsed.  Set by parser.py
             (Parser.mark) immediately after parsing the node.  Used for
             error location reporting (line/col).

    _module: The module path (absolute file path or "<memory>") in which this
             node was defined.  Set by loader.py (set_module_on_tree) during
             import resolution.  Used by the compiler and analyzer for
             module-qualified name resolution and diagnostics.

    Both fields are excluded from __repr__ and __eq__ comparisons so that
    AST equality checks remain structural.
    """
    _tok: Tok | None = field(default=None, repr=False, compare=False)
    _module: str | None = field(default=None, repr=False, compare=False)


@dataclass
class Num(Base):
    v: float
    raw: str | None = None


@dataclass
class Int(Base):
    v: int
    raw: str | None = None


@dataclass
class Bool(Base):
    v: bool


@dataclass
class Str(Base):
    v: str


@dataclass
class StringLiteralPart:
    text: str


@dataclass
class InterpolationPart:
    expression: object


@dataclass
class InterpolatedString(Base):
    parts: list


@dataclass
class Nil(Base):
    pass


@dataclass
class Var(Base):
    name: str


@dataclass
class Unary(Base):
    op: str
    expr: object


@dataclass
class Bin(Base):
    op: str
    a: object
    b: object


@dataclass
class Assign(Base):
    name: str
    expr: object


@dataclass
class CompoundAssign(Base):
    name: str
    op: str  # "+", "-", "*", "/"
    expr: object


@dataclass
class ListLit(Base):
    items: list


@dataclass
class MapLit(Base):
    items: list[tuple[object, object]]


@dataclass
class VarPattern(Base):
    name: str


@dataclass
class ListPattern(Base):
    elements: list[object]


@dataclass
class RecordPattern(Base):
    fields: list[tuple[str, object]]


@dataclass
class DestructureLet(Base):
    pattern: object
    expr: object


@dataclass
class RecordLiteral(Base):
    fields: list[tuple[str, object]]


@dataclass
class Index(Base):
    seq: object
    index: object


@dataclass
class IndexAssign(Base):
    seq: object
    index: object
    value: object


@dataclass
class Attr(Base):
    obj: object
    name: str


@dataclass
class FieldAssign(Base):
    obj: object
    name: str
    value: object


@dataclass
class WorkflowStep(Base):
    name: str
    deps: list[str]
    body: Block
    options: object | None = None
    # `when <predicate>` — a guard on the step itself (#471). The same restricted
    # predicate grammar a goal's `until` uses, and for the same reason: a general
    # expression would be compiled code, invisible to `plan_workflow` and beyond
    # what `nodus check` can verify. Restricted, it stays data.
    when: object | None = None
    # `step process each item in plan { ... }` -- a **mapped node** (#480).
    #
    # The graph never grows: this is one node declared in the source, and only
    # its *cardinality* is discovered at run time, when `plan` produces a list.
    # That is what makes it resumable -- a rebuild reconstructs the declared node
    # and re-derives the count from durable data, rather than needing to restore
    # nodes that exist in the run and not in the source.
    #
    # `each item in plan` implies `after plan`; the parser adds the dependency.
    each_var: str | None = None
    each_source: str | None = None


@dataclass
class WorkflowStateDecl(Base):
    name: str
    value: object
    # `with { merge: ..., durable: ... }` -- how concurrent writes to this cell
    # combine (#485) and whether it is checkpointed (#498). A named map, like a
    # step's options, so the policy stays data the plan can show rather than
    # behaviour hidden in the runtime.
    options: object | None = None


@dataclass
class CheckpointStmt(Base):
    label: object


@dataclass
class WorkflowDef(Base):
    name: str
    states: list[WorkflowStateDecl]
    steps: list[WorkflowStep]
    # `workflow build(mode) { ... }` (#481). Bound at the call --
    # `run_workflow(build, {mode: "lite"})` -- not by calling the flow value,
    # which is an ordinary map. Reuses `Param` so the `type_hint` slot is
    # already there for when annotations reach this surface (#479 D2).
    params: list[Param] = field(default_factory=list)


@dataclass
class ActionStmt(Base):
    kind: str
    target: str | None
    payload: object | None = None


@dataclass
class GoalStep(Base):
    name: str
    deps: list[str]
    body: Block
    options: object | None = None
    when: object | None = None
    # `step process each item in plan { ... }` -- a **mapped node** (#480).
    #
    # The graph never grows: this is one node declared in the source, and only
    # its *cardinality* is discovered at run time, when `plan` produces a list.
    # That is what makes it resumable -- a rebuild reconstructs the declared node
    # and re-derives the count from durable data, rather than needing to restore
    # nodes that exist in the run and not in the source.
    #
    # `each item in plan` implies `after plan`; the parser adds the dependency.
    each_var: str | None = None
    each_source: str | None = None


@dataclass
class GoalDef(Base):
    name: str
    states: list[WorkflowStateDecl]
    steps: list[GoalStep]
    # `workflow build(mode) { ... }` (#481). Bound at the call --
    # `run_workflow(build, {mode: "lite"})` -- not by calling the flow value,
    # which is an ordinary map. Reuses `Param` so the `type_hint` slot is
    # already there for when annotations reach this surface (#479 D2).
    params: list[Param] = field(default_factory=list)


# --- goal-as-stopping-condition (#409 Part A) -------------------------------
# A second, additive form of `goal`. The original `goal g { step ... }` above is
# unchanged and still valid — it is Mostly Stable (graduated v4.0.5) — but since
# #393 unified retries it is a `workflow` with a different event prefix. This
# form gives `goal` a job `workflow` structurally cannot have: it owns the
# *criteria*, and the workflow it names owns the work.


@dataclass
class Reached(Base):
    """`reached("label")` — did the pursued workflow record this checkpoint?

    The label is a `Str`, never an expression, for the same reason `checkpoint`
    requires a literal (`parser.py`): it makes the set of checkpoints a goal
    depends on knowable at parse time, so naming one the workflow never records
    is a compile error rather than a run that quietly never finishes.
    """

    label: object


@dataclass
class PredicateNot(Base):
    operand: object


@dataclass
class PredicateAnd(Base):
    left: object
    right: object


@dataclass
class PredicateOr(Base):
    left: object
    right: object


@dataclass
class GoalBudget(Base):
    """Bounds on the pursuit. At least one — an unbounded goal is a hang.

    `max_iterations` and `deadline_ms` were both mandatory until #488. They are
    optional now, individually, because a third kind of bound exists: `limits`
    is a map of **host-registered meters** (`limits: { tokens: 100000 }`).
    Requiring all of them would force a goal bounded by spend to invent an
    iteration cap it does not want.
    """

    max_iterations: object = None
    deadline_ms: object = None
    limits: object = None


@dataclass
class GoalPursuit(Base):
    """`goal NAME over WORKFLOW { until <pred> budget { ... } }`."""

    name: str
    workflow_name: str
    until: object
    budget: GoalBudget
    retry_from: object | None = None


@dataclass
class Call(Base):
    callee: object
    args: list


@dataclass
class Param(Base):
    name: str
    type_hint: str | None = None


@dataclass
class Let(Base):
    name: str
    expr: object
    type_hint: str | None = None
    exported: bool = False


@dataclass
class Print(Base):
    expr: object


@dataclass
class ExprStmt(Base):
    expr: object


@dataclass
class Block(Base):
    stmts: list


@dataclass
class Comment(Base):
    text: str


@dataclass
class If(Base):
    cond: object
    then_branch: Block
    else_branch: Block | None


@dataclass
class While(Base):
    cond: object
    body: Block


@dataclass
class For(Base):
    init: object | None
    cond: object | None
    inc: object | None
    body: Block


@dataclass
class ForEach(Base):
    name: str
    iterable: object
    body: Block


@dataclass
class Break(Base):
    pass


@dataclass
class Continue(Base):
    pass


@dataclass
class MatchArm:
    # pattern is None for the wildcard arm `_`; otherwise an expression whose
    # value is compared (==) against the scrutinee. body is an expression node
    # or a Block (the block's final expression is the arm's value).
    pattern: object | None
    body: object


@dataclass
class Match(Base):
    scrutinee: object
    arms: list  # list[MatchArm]


@dataclass
class Annotation(Base):
    name: str
    args: list | None = None  # None = bare annotation; list of (str, expr) = parameterised


@dataclass
class FnDef(Base):
    name: str
    params: list[Param]
    body: Block
    return_type: str | None = None
    exported: bool = False
    annotations: list = field(default_factory=list)  # list[Annotation]
    step_owner: str | None = None  # #394, see FnExpr


@dataclass
class ExternDecl(Base):
    """A host function this program requires (#489).

    Reuses `Param` and the `return_type` slot so the declaration is typed by the
    same vocabulary a `fn` is (#609), and so `nodus check` can compare a call
    against it without a second notion of a signature.

    Declaring **any** extern opts the file into strict name resolution: an
    unknown free call becomes an error rather than a possible host function.
    That is per-file, so nothing already written changes.
    """

    name: str
    params: list[Param]
    return_type: str | None = None


@dataclass
class FnExpr(Base):
    params: list[Param]
    body: Block
    return_type: str | None = None
    # #394: propagated to FunctionInfo.step_owner. Set only by the workflow/goal
    # lowering -- no surface syntax produces it.
    step_owner: str | None = None


@dataclass
class Return(Base):
    expr: object | None


@dataclass
class Yield(Base):
    expr: object | None


@dataclass
class Import(Base):
    path: str
    alias: str | None = None
    names: list[str] | None = None


@dataclass
class ExportList(Base):
    names: list[str]


@dataclass
class ExportFrom(Base):
    names: list[str]
    path: str


@dataclass
class ModuleAlias(Base):
    alias: str
    exports: dict[str, str]


@dataclass
class TryCatch(Base):
    try_block: Block
    # #415: `try { } finally { }` needs no catch. A catch-less node carries
    # None in both fields and the compiler lowers it to a rethrowing catch, so
    # the VM's handler machinery is untouched. Every consumer that reads
    # catch_var/catch_block must guard for None -- seven sites at the time of
    # writing, held together by tests/test_try_finally.py rather than by luck.
    catch_var: str | None
    catch_block: Block | None
    finally_block: Block | None = None


@dataclass
class Throw(Base):
    expr: object


@dataclass
class ModuleInfo:
    path: str
    defs: set[str]
    exports: set[str]
    imports: dict[str, str]
    aliases: dict[str, dict[str, str]]
    explicit_exports: bool
    qualified: dict[str, str]


def builtin_call(name: str, args: list) -> "Call":
    """A call that reaches the builtin, whatever the program bound to that name.

    Every call a *lowering* emits must go through this (#411). An ordinary
    ``Call(Var(name), …)`` participates in normal name resolution, and
    ``VM._op_call`` resolves user functions before builtins — so the program can
    supply the machinery the compiler injected into its own code:

        fn effect_resolve(aid) { return {done: true, cached: {result: "FORGED"}} }

        @exactly_once
        fn work() { return "real" }     // body never runs

    The same shape defeated the workflow lowering through ``workflow_state()``,
    which is why this lives here rather than as a private helper on ``Compiler``:
    lowerings are spread across the compiler and ``orchestration/``, and a fix that
    only one of them could reach would have left the other forgeable.

    Prefixing the callee makes the VM dispatch straight to the builtin table,
    ahead of any user lookup. The prefix is reserved — ``Compiler`` rejects any
    source that defines a name beginning with it.

    Covers local bindings, not just globals: a *parameter* named ``effect_resolve``
    forged the envelope as effectively as a top-level ``fn``, so reserving a list
    of global names would not have been sufficient.
    """
    from nodus.builtins.nodus_builtins import BUILTIN_CALL_PREFIX

    return Call(Var(BUILTIN_CALL_PREFIX + name), args)


# Every statement form that declares a flow and, with it, a name the rest of the
# module can reference.
#
# One list because four separate places need this answer -- the compiler's
# hoisting pass, the module loader's def collector, the tooling loader and the
# analyzer -- and each of them used to enumerate the node types itself. They
# agreed on `workflow` and `goal`, and three of the four had never heard of
# `goal ... over ...`, so the name it declares resolved at top level and nowhere
# else (#487). Adding the missing case to each site fixes that instance; keeping
# the set here is what stops the next form drifting the same way.
#
# The sites still do different things with the name -- define a symbol, add to a
# defs set, bind a type -- so this is deliberately the *question* they share and
# not the answer. `tests/test_goal_pursuit_scope.py` holds every site to this
# tuple, so adding a form here fails the suite until each one handles it.
FLOW_DECLARATIONS = (WorkflowDef, GoalDef, GoalPursuit)


def declared_flow_name(stmt) -> str | None:
    """The name a workflow/goal declaration introduces, or None for anything else."""
    if isinstance(stmt, FLOW_DECLARATIONS):
        name = getattr(stmt, "name", None)
        return name if isinstance(name, str) else None
    return None


# The forms that write to a name. Same shape of problem as FLOW_DECLARATIONS
# above, in a different pass: the workflow state rewriter turns writes to a
# `state` cell into writes on a hidden map, and it enumerated three of these
# four. `CompoundAssign` was the one it had never heard of, so `counter += 1i`
# in a step reached the compiler untouched, resolved as an undeclared local and
# read nil (#518).
#
# These genuinely need different rewrites -- the node shapes differ -- so unlike
# FLOW_DECLARATIONS there is no single shared answer to give. What the tuple buys
# is the failure: `tests/test_state_compound_assign.py` demands a worked sample
# per member, so a fifth form fails the suite until somebody has decided what it
# means for state.
ASSIGNMENT_FORMS = (Assign, CompoundAssign, IndexAssign, FieldAssign)


def pattern_names(pattern) -> list[str]:
    """Every name a destructuring pattern binds.

    One implementation, because there were four (#602). The compiler had
    `Compiler.collect_pattern_names`, the workflow lowering had
    `_collect_pattern_names`, `lsp/server.py` grew `_pattern_names` in #597, and
    `tooling/diagnostics.py` was about to grow a fourth — for the very bug that
    file's missing case caused, which would have been the recurring shape
    answering itself.

    Worth noting how three copies survived: `nodus_gate --shapes` keys species A
    on name *and* signature, so `collect_pattern_names` and
    `_collect_pattern_names` never collided. A renamed copy is invisible to it.

    Recursive because patterns nest: `let [a, {x: b}] = …` binds both.
    """
    names: list[str] = []
    if isinstance(pattern, VarPattern):
        names.append(pattern.name)
    elif isinstance(pattern, ListPattern):
        for item in pattern.elements:
            names.extend(pattern_names(item))
    elif isinstance(pattern, RecordPattern):
        for _key, value in pattern.fields:
            names.extend(pattern_names(value))
    return names
