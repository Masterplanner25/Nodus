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


@dataclass
class WorkflowStateDecl(Base):
    name: str
    value: object


@dataclass
class CheckpointStmt(Base):
    label: object


@dataclass
class WorkflowDef(Base):
    name: str
    states: list[WorkflowStateDecl]
    steps: list[WorkflowStep]


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


@dataclass
class GoalDef(Base):
    name: str
    states: list[WorkflowStateDecl]
    steps: list[GoalStep]


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
    """Bounds on the pursuit. Mandatory — an unbounded goal is a hang."""

    max_iterations: object
    deadline_ms: object


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


@dataclass
class FnExpr(Base):
    params: list[Param]
    body: Block
    return_type: str | None = None


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
    catch_var: str
    catch_block: Block
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
