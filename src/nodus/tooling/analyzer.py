"""Static analyzer for optional Nodus type annotations."""

from nodus.frontend.ast.ast_nodes import (
    Assign,
    ActionStmt,
    Attr,
    Bin,
    Block,
    Bool,
    Call,
    Comment,
    ExprStmt,
    FnDef,
    FnExpr,
    For,
    ForEach,
    GoalDef,
    If,
    Import,
    Index,
    IndexAssign,
    Let,
    ListLit,
    MapLit,
    ModuleAlias,
    Nil,
    Num,
    Print,
    RecordLiteral,
    Return,
    Str,
    Throw,
    TryCatch,
    Unary,
    Var,
    WorkflowDef,
    WorkflowStateDecl,
    CheckpointStmt,
    While,
)
from nodus.frontend.type_system import ANY, BOOL, FLOAT, FUNCTION, INT, LIST, NIL, RECORD, STRING, FunctionType, combine_types, is_assignable, parse_type_name


class TypeAnalysisError(TypeError):
    def __init__(self, message: str, line: int | None = None, col: int | None = None, path: str | None = None):
        super().__init__(message)
        self.line = line
        self.col = col
        self.path = path


class Analyzer:
    def __init__(self):
        self.scopes: list[dict[str, object]] = [{}]
        self.current_return: object = ANY
        self.current_module: str | None = None

    def analyze(self, stmts: list) -> None:
        self.collect_functions(stmts)
        for stmt in stmts:
            self.analyze_stmt(stmt)

    def collect_functions(self, stmts: list) -> None:
        for stmt in stmts:
            if isinstance(stmt, FnDef):
                param_types = [parse_type_name(param.type_hint) for param in stmt.params]
                return_type = parse_type_name(stmt.return_type)
                self.scopes[0][stmt.name] = FunctionType(param_types, return_type)

    def analyze_stmt(self, stmt) -> None:
        self.current_module = getattr(stmt, "_module", self.current_module)
        if isinstance(stmt, (Comment, Import, ModuleAlias)):
            return
        if isinstance(stmt, Let):
            value_type = self.infer_expr(stmt.expr)
            expected = parse_type_name(stmt.type_hint)
            if stmt.type_hint is not None and not is_assignable(expected, value_type):
                self.type_error(f"expected {expected.name} but got {value_type.name}", stmt)
            self.bind(stmt.name, expected if stmt.type_hint is not None else value_type)
            return
        if isinstance(stmt, WorkflowDef):
            self.bind(stmt.name, RECORD)
            return
        if isinstance(stmt, GoalDef):
            self.bind(stmt.name, RECORD)
            return
        if isinstance(stmt, WorkflowStateDecl):
            self.infer_expr(stmt.value)
            return
        if isinstance(stmt, CheckpointStmt):
            return
        if isinstance(stmt, ExprStmt):
            self.infer_expr(stmt.expr)
            return
        if isinstance(stmt, Print):
            self.infer_expr(stmt.expr)
            return
        if isinstance(stmt, Block):
            self.push_scope()
            for inner in stmt.stmts:
                self.analyze_stmt(inner)
            self.pop_scope()
            return
        if isinstance(stmt, If):
            self.infer_expr(stmt.cond)
            self.analyze_stmt(stmt.then_branch)
            if stmt.else_branch is not None:
                self.analyze_stmt(stmt.else_branch)
            return
        if isinstance(stmt, While):
            self.infer_expr(stmt.cond)
            self.analyze_stmt(stmt.body)
            return
        if isinstance(stmt, For):
            self.push_scope()
            if stmt.init is not None:
                self.analyze_stmt(stmt.init)
            if stmt.cond is not None:
                self.infer_expr(stmt.cond)
            if stmt.inc is not None:
                self.infer_expr(stmt.inc)
            self.analyze_stmt(stmt.body)
            self.pop_scope()
            return
        if isinstance(stmt, ForEach):
            self.infer_expr(stmt.iterable)
            self.push_scope()
            self.bind(stmt.name, ANY)
            self.analyze_stmt(stmt.body)
            self.pop_scope()
            return
        if isinstance(stmt, FnDef):
            fn_type = self.lookup(stmt.name)
            previous_return = self.current_return
            self.current_return = parse_type_name(stmt.return_type)
            self.push_scope()
            for index, param in enumerate(stmt.params):
                self.bind(param.name, fn_type.params[index] if isinstance(fn_type, FunctionType) else ANY)
            self.analyze_stmt(stmt.body)
            self.pop_scope()
            self.current_return = previous_return
            return
        if isinstance(stmt, Return):
            actual = NIL if stmt.expr is None else self.infer_expr(stmt.expr)
            if self.current_return != ANY and not is_assignable(self.current_return, actual):
                self.type_error(f"expected {self.current_return.name} but got {actual.name}", stmt)
            return
        if isinstance(stmt, TryCatch):
            self.analyze_stmt(stmt.try_block)
            self.push_scope()
            self.bind(stmt.catch_var, STRING)
            self.analyze_stmt(stmt.catch_block)
            self.pop_scope()
            return
        if isinstance(stmt, Throw):
            self.infer_expr(stmt.expr)
            return

    def infer_expr(self, expr):
        if isinstance(expr, Num):
            if expr.raw is not None and "." not in expr.raw:
                return INT
            return FLOAT
        if isinstance(expr, ActionStmt):
            if expr.payload is not None:
                self.infer_expr(expr.payload)
            return ANY
        if isinstance(expr, Bool):
            return BOOL
        if isinstance(expr, Str):
            return STRING
        if isinstance(expr, Nil):
            return NIL
        if isinstance(expr, Var):
            return self.lookup(expr.name)
        if isinstance(expr, Unary):
            inner = self.infer_expr(expr.expr)
            if expr.op == "!":
                return BOOL
            if inner in {INT, FLOAT}:
                return inner
            return ANY
        if isinstance(expr, Bin):
            left = self.infer_expr(expr.a)
            right = self.infer_expr(expr.b)
            if expr.op in {"==", "!=", "<", ">", "<=", ">=", "&&", "||"}:
                return BOOL
            if expr.op == "+" and (left == STRING or right == STRING):
                return STRING
            if expr.op in {"+", "-", "*", "/"}:
                if expr.op == "/" and left in {INT, FLOAT} and right in {INT, FLOAT}:
                    return FLOAT
                return combine_types(left, right)
            return ANY
        if isinstance(expr, ListLit):
            for item in expr.items:
                self.infer_expr(item)
            return LIST
        if isinstance(expr, MapLit):
            for key, value in expr.items:
                self.infer_expr(key)
                self.infer_expr(value)
            return RECORD
        if isinstance(expr, RecordLiteral):
            for _key, value in expr.fields:
                self.infer_expr(value)
            return RECORD
        if isinstance(expr, Index):
            self.infer_expr(expr.seq)
            self.infer_expr(expr.index)
            return ANY
        if isinstance(expr, IndexAssign):
            self.infer_expr(expr.seq)
            self.infer_expr(expr.index)
            value_type = self.infer_expr(expr.value)
            return value_type
        if isinstance(expr, Attr):
            self.infer_expr(expr.obj)
            return ANY
        if isinstance(expr, Assign):
            value_type = self.infer_expr(expr.expr)
            existing = self.lookup(expr.name)
            if existing != ANY and not is_assignable(existing, value_type):
                self.type_error(f"expected {existing.name} but got {value_type.name}", expr)
            self.bind(expr.name, existing if existing != ANY else value_type)
            return value_type
        if isinstance(expr, FnExpr):
            params = [parse_type_name(param.type_hint) for param in expr.params]
            return FunctionType(params, parse_type_name(expr.return_type))
        if isinstance(expr, Call):
            callee_type = self.infer_expr(expr.callee)
            arg_types = [self.infer_expr(arg) for arg in expr.args]
            if isinstance(callee_type, FunctionType):
                for expected, actual, arg in zip(callee_type.params, arg_types, expr.args):
                    if not is_assignable(expected, actual):
                        self.type_error(f"expected {expected.name} but got {actual.name}", arg)
                return callee_type.return_type
            return ANY
        return ANY

    def push_scope(self) -> None:
        self.scopes.append({})

    def pop_scope(self) -> None:
        self.scopes.pop()

    def bind(self, name: str, type_value) -> None:
        self.scopes[-1][name] = type_value

    def lookup(self, name: str):
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        if name == "clock":
            return FunctionType([], FLOAT)
        if name in {"type", "str", "input"}:
            return FunctionType([ANY], STRING)
        if name in {"len"}:
            return FunctionType([ANY], INT)
        if name in {"print"}:
            return FunctionType([ANY], NIL)
        return ANY

    def type_error(self, message: str, node) -> None:
        tok = getattr(node, "_tok", None)
        path = getattr(node, "_module", self.current_module)
        line = tok.line if tok is not None else None
        col = tok.col if tok is not None else None
        raise TypeAnalysisError(message, line=line, col=col, path=path)


def analyze_program(stmts: list) -> None:
    Analyzer().analyze(stmts)
