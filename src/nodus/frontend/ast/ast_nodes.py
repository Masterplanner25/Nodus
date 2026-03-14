"""AST node definitions for Nodus."""

from dataclasses import dataclass


@dataclass
class Num:
    v: float
    raw: str | None = None


@dataclass
class Bool:
    v: bool


@dataclass
class Str:
    v: str


@dataclass
class Nil:
    pass


@dataclass
class Var:
    name: str


@dataclass
class Unary:
    op: str
    expr: object


@dataclass
class Bin:
    op: str
    a: object
    b: object


@dataclass
class Assign:
    name: str
    expr: object


@dataclass
class ListLit:
    items: list


@dataclass
class MapLit:
    items: list[tuple[object, object]]


@dataclass
class VarPattern:
    name: str


@dataclass
class ListPattern:
    elements: list[object]


@dataclass
class RecordPattern:
    fields: list[tuple[str, object]]


@dataclass
class DestructureLet:
    pattern: object
    expr: object


@dataclass
class RecordLiteral:
    fields: list[tuple[str, object]]


@dataclass
class Index:
    seq: object
    index: object


@dataclass
class IndexAssign:
    seq: object
    index: object
    value: object


@dataclass
class Attr:
    obj: object
    name: str


@dataclass
class FieldAssign:
    obj: object
    name: str
    value: object


@dataclass
class WorkflowStep:
    name: str
    deps: list[str]
    body: object
    options: object | None = None


@dataclass
class WorkflowStateDecl:
    name: str
    value: object


@dataclass
class CheckpointStmt:
    label: object


@dataclass
class WorkflowDef:
    name: str
    states: list[WorkflowStateDecl]
    steps: list[WorkflowStep]


@dataclass
class ActionStmt:
    kind: str
    target: str | None
    payload: object | None = None


@dataclass
class GoalStep:
    name: str
    deps: list[str]
    body: object
    options: object | None = None


@dataclass
class GoalDef:
    name: str
    states: list[WorkflowStateDecl]
    steps: list[GoalStep]


@dataclass
class Call:
    callee: object
    args: list


@dataclass
class Param:
    name: str
    type_hint: str | None = None


@dataclass
class Let:
    name: str
    expr: object
    type_hint: str | None = None
    exported: bool = False


@dataclass
class Print:
    expr: object


@dataclass
class ExprStmt:
    expr: object


@dataclass
class Block:
    stmts: list


@dataclass
class Comment:
    text: str


@dataclass
class If:
    cond: object
    then_branch: object
    else_branch: object | None


@dataclass
class While:
    cond: object
    body: object


@dataclass
class For:
    init: object | None
    cond: object | None
    inc: object | None
    body: object


@dataclass
class ForEach:
    name: str
    iterable: object
    body: object


@dataclass
class FnDef:
    name: str
    params: list[Param]
    body: object
    return_type: str | None = None
    exported: bool = False


@dataclass
class FnExpr:
    params: list[Param]
    body: object
    return_type: str | None = None


@dataclass
class Return:
    expr: object | None


@dataclass
class Yield:
    expr: object | None


@dataclass
class Import:
    path: str
    alias: str | None = None
    names: list[str] | None = None


@dataclass
class ExportList:
    names: list[str]


@dataclass
class ExportFrom:
    names: list[str]
    path: str


@dataclass
class ModuleAlias:
    alias: str
    exports: dict[str, str]


@dataclass
class TryCatch:
    try_block: object
    catch_var: str
    catch_block: object


@dataclass
class Throw:
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
