"""AST node definitions for Nodus."""

from dataclasses import dataclass, field


# Forward reference for Tok (populated by parser; avoids circular import)
# Tok is defined in nodus.frontend.lexer; we use a string annotation here.

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
    _tok: object = field(default=None, repr=False, compare=False)
    _module: str | None = field(default=None, repr=False, compare=False)


@dataclass
class Num(Base):
    v: float
    raw: str | None = None


@dataclass
class Bool(Base):
    v: bool


@dataclass
class Str(Base):
    v: str


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
    body: object
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
    body: object
    options: object | None = None


@dataclass
class GoalDef(Base):
    name: str
    states: list[WorkflowStateDecl]
    steps: list[GoalStep]


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
    then_branch: object
    else_branch: object | None


@dataclass
class While(Base):
    cond: object
    body: object


@dataclass
class For(Base):
    init: object | None
    cond: object | None
    inc: object | None
    body: object


@dataclass
class ForEach(Base):
    name: str
    iterable: object
    body: object


@dataclass
class FnDef(Base):
    name: str
    params: list[Param]
    body: object
    return_type: str | None = None
    exported: bool = False


@dataclass
class FnExpr(Base):
    params: list[Param]
    body: object
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
    try_block: object
    catch_var: str
    catch_block: object
    finally_block: object = None


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
