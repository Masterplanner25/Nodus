"""Bytecode compiler for Nodus."""

from dataclasses import dataclass

from nodus.frontend.ast.ast_nodes import (
    Assign,
    Attr,
    Bin,
    Block,
    Bool,
    Call,
    Comment,
    DestructureLet,
    ExprStmt,
    ExportList,
    ExportFrom,
    FnDef,
    FnExpr,
    GoalDef,
    If,
    Import,
    Index,
    IndexAssign,
    Let,
    ListLit,
    ListPattern,
    MapLit,
    RecordLiteral,
    RecordPattern,
    ModuleAlias,
    ModuleInfo,
    Nil,
    Num,
    Print,
    Return,
    Yield,
    Str,
    Throw,
    TryCatch,
    Unary,
    Var,
    VarPattern,
    While,
    For,
    FieldAssign,
    ForEach,
    Param,
    WorkflowDef,
    CheckpointStmt,
)
from nodus.builtins.nodus_builtins import BUILTIN_NAMES
from nodus.runtime.diagnostics import LangSyntaxError
from nodus.compiler.symbol_table import SymbolTable, Symbol, Upvalue
from nodus.orchestration.workflow_lowering import lower_goal_ast, lower_workflow_ast


@dataclass
class FunctionInfo:
    name: str
    params: list[str]
    addr: int
    upvalues: list[Upvalue]
    display_name: str


class Compiler:
    def __init__(self, module_infos: dict[str, ModuleInfo] | None = None, module_defs_index: dict[str, set[str]] | None = None):
        self.code: list[tuple] = []
        self.code_locs: list[tuple[str | None, int | None, int | None]] = []
        self.functions: dict[str, FunctionInfo] = {}
        self.current_loc: tuple[str | None, int | None, int | None] = (None, None, None)
        self.module_aliases: dict[str, dict[str, dict[str, str]]] = {}
        self.module_infos = module_infos or {}
        self.module_defs_index = module_defs_index or {}
        self.current_module: str | None = None
        self.symbol_tables: dict[str, SymbolTable] = {}
        self.symbols: SymbolTable | None = None
        self.fn_counter = 0
        self.temp_counter = 0

    def new_temp(self) -> str:
        self.temp_counter += 1
        return f"__destruct{self.temp_counter}"

    def resolve_module_name(self, alias: str, name: str, node=None) -> str:
        module = self.current_module
        aliases = self.module_aliases.get(module or "", {})
        if alias not in aliases:
            self.raise_syntax(f"Unknown module alias: {alias}", node=node)
        exports = aliases[alias]
        if name not in exports:
            self.raise_syntax(f"Module '{alias}' has no member '{name}'", node=node)
        return exports[name]

    def set_current_module(self, node) -> None:
        mod = getattr(node, "_module", None)
        if mod is not None:
            self.current_module = mod
            if mod not in self.symbol_tables:
                self.symbol_tables[mod] = SymbolTable()
            self.symbols = self.symbol_tables[mod]

    def current_module_info(self) -> ModuleInfo | None:
        if self.current_module is None:
            return None
        return self.module_infos.get(self.current_module)

    def in_function_scope(self) -> bool:
        if self.symbols is None:
            return False
        scope = self.symbols.current
        while scope:
            if scope.kind == "function":
                return True
            scope = scope.parent
        return False

    def resolve_symbol(self, name: str) -> Symbol | None:
        if self.symbols is None:
            return None
        return self.symbols.resolve(name)

    def raise_syntax(self, message: str, node=None):
        self.set_current_loc(node) if node is not None else None
        _path, line, col = self.current_loc
        err = LangSyntaxError(message, line=line, col=col, path=self.current_module)
        raise err

    def ensure_name_access(self, name: str, node=None) -> None:
        symbol = self.resolve_symbol(name)
        if symbol is not None:
            return
        module_info = self.current_module_info()
        if module_info is None:
            return
        if self.current_module in {"<repl>"}:
            return
        if name in module_info.defs:
            if self.symbols is None or self.symbols.is_defined_in_module(name):
                return
        if name in module_info.imports:
            return
        if name in BUILTIN_NAMES:
            return
        if name in self.module_defs_index:
            owners = sorted(self.module_defs_index[name])
            if module_info.path not in owners:
                owner_list = ", ".join(owners)
                self.raise_syntax(
                    f"Symbol '{name}' is private to module(s): {owner_list}. Import it to use it here.",
                    node=node,
                )

        if self.symbols is not None and self.symbols.is_defined_anywhere(name):
            self.raise_syntax(f"Undefined variable: {name}", node=node)

    def resolve_name(self, name: str) -> str:
        module_info = self.current_module_info()
        symbol = self.resolve_symbol(name)
        if symbol is not None and symbol.scope in {"local", "upvalue"}:
            return name
        if module_info is None:
            return name
        if name in module_info.imports:
            return module_info.imports[name]
        if name in module_info.qualified:
            return module_info.qualified[name]
        return name

    def resolve_store_name(self, name: str) -> str:
        module_info = self.current_module_info()
        symbol = self.resolve_symbol(name)
        if symbol is not None and symbol.scope in {"local", "upvalue"}:
            return name
        if module_info is None:
            return name
        if name in module_info.qualified:
            return module_info.qualified[name]
        return name

    def resolve_def_name(self, name: str) -> str:
        module_info = self.current_module_info()
        if module_info is None:
            return name
        return module_info.qualified.get(name, name)

    def set_current_loc(self, node) -> None:
        tok = getattr(node, "_tok", None)
        if tok is not None:
            self.current_loc = (self.current_module, tok.line, tok.col)

    def emit(self, *instr):
        self.code.append(instr)
        self.code_locs.append(self.current_loc)
        return len(self.code) - 1

    def patch(self, index: int, *instr):
        self.code[index] = instr

    def predeclare_module_scopes(self, stmts: list) -> None:
        for stmt in stmts:
            self.set_current_module(stmt)
            if self.symbols is None:
                continue
            if isinstance(stmt, Let):
                self.symbols.define(stmt.name)
                continue
            if isinstance(stmt, FnDef):
                self.symbols.define_function(stmt.name)
                continue
            if isinstance(stmt, WorkflowDef):
                self.symbols.define(stmt.name)
                continue
            if isinstance(stmt, GoalDef):
                self.symbols.define(stmt.name)
                continue
            if isinstance(stmt, ExprStmt) and isinstance(stmt.expr, Assign):
                self.symbols.define(stmt.expr.name)
                continue

    def predeclare_block(self, block: Block) -> None:
        if self.symbols is None:
            return
        for stmt in block.stmts:
            if isinstance(stmt, Let):
                self.symbols.define(stmt.name)

    def compile_program(self, stmts: list) -> tuple[list[tuple], dict[str, FunctionInfo], list[tuple[str | None, int | None, int | None]]]:
        jump_to_main = self.emit("JUMP", None)

        self.predeclare_module_scopes(stmts)

        for stmt in stmts:
            if isinstance(stmt, ModuleAlias):
                self.set_current_module(stmt)
                module = self.current_module or ""
                self.module_aliases.setdefault(module, {})[stmt.alias] = dict(stmt.exports)

        for stmt in stmts:
            if isinstance(stmt, FnDef):
                self.compile_fn_def(stmt)

        main_addr = len(self.code)
        self.patch(jump_to_main, "JUMP", main_addr)

        for stmt in stmts:
            if not isinstance(stmt, FnDef):
                self.compile_stmt(stmt)

        self.emit("HALT")
        return self.code, self.functions, self.code_locs

    def compile_fn_def(self, stmt: FnDef, *, is_nested: bool = False) -> str:
        self.set_current_module(stmt)
        self.set_current_loc(stmt)
        if is_nested:
            self.fn_counter += 1
            fn_name = f"{self.resolve_def_name(stmt.name)}__fn{self.fn_counter}"
        else:
            fn_name = self.resolve_def_name(stmt.name)
        if fn_name in self.functions:
            self.raise_syntax(f"Function already defined: {stmt.name}", node=stmt)

        fn_addr = len(self.code)
        param_names = self.param_names(stmt.params)
        fn_info = FunctionInfo(fn_name, param_names, fn_addr, upvalues=[], display_name=stmt.name)
        self.functions[fn_name] = fn_info

        if self.symbols is None:
            self.symbols = SymbolTable()
        self.symbols.enter_scope("function")
        for param in param_names:
            self.symbols.define(param)
        for param in reversed(param_names):
            self.emit("STORE_ARG", param)

        self.compile_stmt(stmt.body)
        fn_info.upvalues = self.symbols.current_function_upvalues()
        self.symbols.exit_scope()
        self.emit("PUSH_CONST", None)
        self.emit("RETURN")
        return fn_name

    def compile_stmt(self, stmt):
        self.set_current_module(stmt)
        self.set_current_loc(stmt)
        if isinstance(stmt, Let):
            if self.symbols is not None:
                self.symbols.define(stmt.name)
            self.compile_expr(stmt.expr)
            self.emit("STORE", self.resolve_store_name(stmt.name))
            return

        if isinstance(stmt, WorkflowDef):
            if self.symbols is not None:
                self.symbols.define(stmt.name)
            self.compile_expr(lower_workflow_ast(stmt))
            self.emit("STORE", self.resolve_store_name(stmt.name))
            return

        if isinstance(stmt, GoalDef):
            if self.symbols is not None:
                self.symbols.define(stmt.name)
            self.compile_expr(lower_goal_ast(stmt))
            self.emit("STORE", self.resolve_store_name(stmt.name))
            return

        if isinstance(stmt, DestructureLet):
            if self.symbols is not None:
                for name in self.collect_pattern_names(stmt.pattern):
                    self.symbols.define(name)
            temp = self.new_temp()
            if self.symbols is not None:
                self.symbols.define(temp)
            self.compile_expr(stmt.expr)
            self.emit("STORE", temp)
            self.destructure_from_name(stmt.pattern, temp)
            return

        if isinstance(stmt, Print):
            self.compile_expr(stmt.expr)
            self.emit("CALL", "print", 1)
            self.emit("POP")
            return

        if isinstance(stmt, ExprStmt):
            self.compile_expr(stmt.expr)
            self.emit("POP")
            return
        if isinstance(stmt, CheckpointStmt):
            self.compile_expr(stmt.label)
            self.emit("CALL", "__workflow_checkpoint", 1)
            self.emit("POP")
            return

        if isinstance(stmt, Block):
            if self.symbols is not None:
                self.symbols.enter_scope("block")
                self.predeclare_block(stmt)
            for s in stmt.stmts:
                self.compile_stmt(s)
            if self.symbols is not None:
                self.symbols.exit_scope()
            return

        if isinstance(stmt, If):
            self.compile_expr(stmt.cond)
            jmp_false = self.emit("JUMP_IF_FALSE", None)
            self.compile_stmt(stmt.then_branch)

            if stmt.else_branch is not None:
                jmp_end = self.emit("JUMP", None)
                self.patch(jmp_false, "JUMP_IF_FALSE", len(self.code))
                self.compile_stmt(stmt.else_branch)
                self.patch(jmp_end, "JUMP", len(self.code))
            else:
                self.patch(jmp_false, "JUMP_IF_FALSE", len(self.code))
            return

        if isinstance(stmt, While):
            loop_start = len(self.code)
            self.compile_expr(stmt.cond)
            jmp_false = self.emit("JUMP_IF_FALSE", None)
            self.compile_stmt(stmt.body)
            self.emit("JUMP", loop_start)
            self.patch(jmp_false, "JUMP_IF_FALSE", len(self.code))
            return

        if isinstance(stmt, For):
            if self.symbols is not None:
                self.symbols.enter_scope("block")
            if stmt.init is not None:
                self.compile_stmt(stmt.init)
            loop_start = len(self.code)
            loop_cond = stmt.cond if stmt.cond is not None else Bool(True)
            self.compile_expr(loop_cond)
            jmp_false = self.emit("JUMP_IF_FALSE", None)
            self.compile_stmt(stmt.body)
            if stmt.inc is not None:
                self.compile_expr(stmt.inc)
                self.emit("POP")
            self.emit("JUMP", loop_start)
            self.patch(jmp_false, "JUMP_IF_FALSE", len(self.code))
            if self.symbols is not None:
                self.symbols.exit_scope()
            return

        if isinstance(stmt, ForEach):
            if self.symbols is not None:
                self.symbols.enter_scope("block")
                self.symbols.define(stmt.name)
            self.compile_expr(stmt.iterable)
            self.emit("GET_ITER")
            loop_start = len(self.code)
            iter_next = self.emit("ITER_NEXT", None)
            self.emit("STORE", stmt.name)
            self.compile_stmt(stmt.body)
            self.emit("JUMP", loop_start)
            self.patch(iter_next, "ITER_NEXT", len(self.code))
            if self.symbols is not None:
                self.symbols.exit_scope()
            return

        if isinstance(stmt, Return):
            if stmt.expr is None:
                self.emit("PUSH_CONST", None)
            else:
                self.compile_expr(stmt.expr)
            self.emit("RETURN")
            return

        if isinstance(stmt, Yield):
            if not self.in_function_scope():
                self.raise_syntax("yield outside function", node=stmt)
            if stmt.expr is None:
                self.emit("PUSH_CONST", None)
            else:
                self.compile_expr(stmt.expr)
            self.emit("YIELD")
            return

        if isinstance(stmt, TryCatch):
            setup_idx = self.emit("SETUP_TRY", None)
            self.compile_stmt(stmt.try_block)
            self.emit("POP_TRY")
            jmp_end = self.emit("JUMP", None)
            handler_ip = len(self.code)
            self.patch(setup_idx, "SETUP_TRY", handler_ip)
            if self.symbols is not None:
                self.symbols.enter_scope("block")
                self.symbols.define(stmt.catch_var)
            self.emit("STORE", stmt.catch_var)
            self.compile_stmt(stmt.catch_block)
            if self.symbols is not None:
                self.symbols.exit_scope()
            self.patch(jmp_end, "JUMP", len(self.code))
            return

        if isinstance(stmt, Throw):
            self.compile_expr(stmt.expr)
            self.emit("THROW")
            return

        if isinstance(stmt, Import):
            return

        if isinstance(stmt, Comment):
            return

        if isinstance(stmt, ModuleAlias):
            module = self.current_module or ""
            self.module_aliases.setdefault(module, {})[stmt.alias] = dict(stmt.exports)
            for export_name, qualified_name in stmt.exports.items():
                self.emit("PUSH_CONST", export_name)
                self.emit("LOAD", qualified_name)
            self.emit("BUILD_MODULE", len(stmt.exports))
            self.emit("STORE", stmt.alias)
            return

        if isinstance(stmt, FnDef):
            if self.symbols is not None:
                self.symbols.define_function(stmt.name)
            jump_over = self.emit("JUMP", None)
            internal_name = self.compile_fn_def(stmt, is_nested=True)
            self.patch(jump_over, "JUMP", len(self.code))
            self.set_current_loc(stmt)
            self.emit("MAKE_CLOSURE", internal_name)
            self.emit("STORE", stmt.name)
            return
        if isinstance(stmt, For):
            return
        if isinstance(stmt, ForEach):
            return

        if isinstance(stmt, ExportList):
            return
        if isinstance(stmt, ExportFrom):
            return

        raise TypeError(f"Unknown stmt node: {stmt!r}")

    def compile_expr(self, expr):
        self.set_current_module(expr)
        self.set_current_loc(expr)
        if isinstance(expr, Num):
            self.emit("PUSH_CONST", expr.v)
            return

        if isinstance(expr, Bool):
            self.emit("PUSH_CONST", expr.v)
            return

        if isinstance(expr, Str):
            self.emit("PUSH_CONST", expr.v)
            return

        if isinstance(expr, Nil):
            self.emit("PUSH_CONST", None)
            return

        if isinstance(expr, Var):
            symbol = self.resolve_symbol(expr.name)
            if symbol is not None and symbol.scope == "upvalue":
                self.emit("LOAD_UPVALUE", symbol.index)
                return
            if symbol is not None and symbol.scope == "local":
                self.emit("LOAD", expr.name)
                return
            self.ensure_name_access(expr.name, node=expr)
            self.emit("LOAD", self.resolve_name(expr.name))
            return

        if isinstance(expr, Attr):
            if isinstance(expr.obj, Var):
                module = self.current_module or ""
                aliases = self.module_aliases.get(module, {})
                if expr.obj.name in aliases:
                    resolved = self.resolve_module_name(expr.obj.name, expr.name, node=expr)
                    self.emit("LOAD", resolved)
                    return
            self.compile_expr(expr.obj)
            self.emit("LOAD_FIELD", expr.name)
            return

        if isinstance(expr, Assign):
            symbol = self.resolve_symbol(expr.name)
            if symbol is None and self.symbols is not None:
                self.symbols.define(expr.name)
                symbol = self.resolve_symbol(expr.name)
            self.compile_expr(expr.expr)
            if symbol is not None and symbol.scope == "upvalue":
                self.emit("STORE_UPVALUE", symbol.index)
                self.emit("LOAD_UPVALUE", symbol.index)
                return
            store_name = self.resolve_store_name(expr.name)
            self.emit("STORE", store_name)
            self.emit("LOAD", store_name)
            return

        if isinstance(expr, Unary):
            self.compile_expr(expr.expr)
            if expr.op == "!":
                self.emit("NOT")
                return
            if expr.op == "-":
                self.emit("NEG")
                return
            raise ValueError(f"Unknown unary operator: {expr.op}")

        if isinstance(expr, Bin):
            if expr.op == "&&":
                self.compile_expr(expr.a)
                jmp_false = self.emit("JUMP_IF_FALSE", None)
                self.compile_expr(expr.b)
                self.emit("TO_BOOL")
                jmp_end = self.emit("JUMP", None)
                false_addr = len(self.code)
                self.emit("PUSH_CONST", False)
                self.patch(jmp_false, "JUMP_IF_FALSE", false_addr)
                self.patch(jmp_end, "JUMP", len(self.code))
                return

            if expr.op == "||":
                self.compile_expr(expr.a)
                jmp_true = self.emit("JUMP_IF_TRUE", None)
                self.compile_expr(expr.b)
                self.emit("TO_BOOL")
                jmp_end = self.emit("JUMP", None)
                true_addr = len(self.code)
                self.emit("PUSH_CONST", True)
                self.patch(jmp_true, "JUMP_IF_TRUE", true_addr)
                self.patch(jmp_end, "JUMP", len(self.code))
                return

            self.compile_expr(expr.a)
            self.compile_expr(expr.b)

            op_map = {
                "+": "ADD",
                "-": "SUB",
                "*": "MUL",
                "/": "DIV",
                "==": "EQ",
                "!=": "NE",
                "<": "LT",
                ">": "GT",
                "<=": "LE",
                ">=": "GE",
            }

            if expr.op not in op_map:
                raise ValueError(f"Unknown operator: {expr.op}")

            self.emit(op_map[expr.op])
            return

        if isinstance(expr, ListLit):
            for item in expr.items:
                self.compile_expr(item)
            self.emit("BUILD_LIST", len(expr.items))
            return

        if isinstance(expr, MapLit):
            for key_expr, value_expr in expr.items:
                self.compile_expr(key_expr)
                self.compile_expr(value_expr)
            self.emit("BUILD_MAP", len(expr.items))
            return

        if isinstance(expr, Index):
            self.compile_expr(expr.seq)
            self.compile_expr(expr.index)
            self.emit("INDEX")
            return

        if isinstance(expr, IndexAssign):
            self.compile_expr(expr.seq)
            self.compile_expr(expr.index)
            self.compile_expr(expr.value)
            self.emit("INDEX_SET")
            return

        if isinstance(expr, FieldAssign):
            self.compile_expr(expr.obj)
            self.compile_expr(expr.value)
            self.emit("STORE_FIELD", expr.name)
            return

        if isinstance(expr, RecordLiteral):
            for key, value in expr.fields:
                self.emit("PUSH_CONST", key)
                self.compile_expr(value)
            self.emit("BUILD_RECORD", len(expr.fields))
            return

        if isinstance(expr, Call):
            if isinstance(expr.callee, Var):
                symbol = self.resolve_symbol(expr.callee.name)
                if symbol is not None:
                    if symbol.scope in {"local", "upvalue"} or (symbol.scope == "global" and not symbol.is_function):
                        if symbol.scope == "upvalue":
                            self.emit("LOAD_UPVALUE", symbol.index)
                        elif symbol.scope == "local":
                            self.emit("LOAD", expr.callee.name)
                        else:
                            self.emit("LOAD", self.resolve_name(expr.callee.name))
                        for arg in expr.args:
                            self.compile_expr(arg)
                        self.emit("CALL_VALUE", len(expr.args))
                        return
                for arg in expr.args:
                    self.compile_expr(arg)
                self.ensure_name_access(expr.callee.name, node=expr)
                self.emit("CALL", self.resolve_name(expr.callee.name), len(expr.args))
                return
            if isinstance(expr.callee, Attr) and isinstance(expr.callee.obj, Var):
                module = self.current_module or ""
                aliases = self.module_aliases.get(module, {})
                if expr.callee.obj.name in aliases:
                    for arg in expr.args:
                        self.compile_expr(arg)
                    resolved = self.resolve_module_name(expr.callee.obj.name, expr.callee.name, node=expr)
                    self.emit("CALL", resolved, len(expr.args))
                    return
            if isinstance(expr.callee, Attr):
                self.compile_expr(expr.callee.obj)
                for arg in expr.args:
                    self.compile_expr(arg)
                self.emit("CALL_METHOD", expr.callee.name, len(expr.args))
                return
            self.compile_expr(expr.callee)
            for arg in expr.args:
                self.compile_expr(arg)
            self.emit("CALL_VALUE", len(expr.args))
            return

        if isinstance(expr, FnExpr):
            jump_over = self.emit("JUMP", None)
            anon_name = f"__anon"
            internal_name = self.compile_fn_def(FnDef(anon_name, expr.params, expr.body, return_type=expr.return_type), is_nested=True)
            self.patch(jump_over, "JUMP", len(self.code))
            self.emit("MAKE_CLOSURE", internal_name)
            return

        raise TypeError(f"Unknown expr node: {expr!r}")

    def collect_pattern_names(self, pattern) -> list[str]:
        names: list[str] = []
        if isinstance(pattern, VarPattern):
            names.append(pattern.name)
        elif isinstance(pattern, ListPattern):
            for item in pattern.elements:
                names.extend(self.collect_pattern_names(item))
        elif isinstance(pattern, RecordPattern):
            for _key, value in pattern.fields:
                names.extend(self.collect_pattern_names(value))
        return names

    def destructure_from_name(self, pattern, temp_name: str) -> None:
        self.emit("LOAD", temp_name)
        self.destructure_from_stack(pattern)

    def destructure_from_stack(self, pattern) -> None:
        if isinstance(pattern, VarPattern):
            self.emit("STORE", pattern.name)
            return
        temp = self.new_temp()
        if self.symbols is not None:
            self.symbols.define(temp)
        self.emit("STORE", temp)
        if isinstance(pattern, ListPattern):
            for idx, item in enumerate(pattern.elements):
                self.emit("LOAD", temp)
                self.emit("PUSH_CONST", float(idx))
                self.emit("INDEX")
                self.destructure_from_stack(item)
            return
        if isinstance(pattern, RecordPattern):
            for key, value in pattern.fields:
                self.emit("LOAD", temp)
                self.emit("LOAD_FIELD", key)
                self.destructure_from_stack(value)
            return

    def param_names(self, params: list[Param]) -> list[str]:
        return [param.name for param in params]


def display_name(name: str) -> str:
    if "__fn" in name:
        name = name.split("__fn", 1)[0]
    if name.startswith("__mod") and "__" in name[5:]:
        parts = name.split("__", 2)
        if len(parts) == 3 and parts[2]:
            return parts[2]
    return name


def format_loc(loc: tuple[str | None, int | None, int | None]) -> str | None:
    path, line, col = loc
    if path and line is not None and col is not None:
        return f"{path}:{line}:{col}"
    if path:
        return path
    if line is not None and col is not None:
        return f"{line}:{col}"
    return None


def format_bytecode(
    code: list[tuple],
    code_locs: list[tuple[str | None, int | None, int | None]],
    functions: dict[str, FunctionInfo],
) -> str:
    lines, _structured = _format_bytecode_ranges(code, code_locs, functions, structured=False)
    return "\n".join(lines)


def build_disassembly(
    code: list[tuple],
    code_locs: list[tuple[str | None, int | None, int | None]],
    functions: dict[str, FunctionInfo],
) -> tuple[str, list[str], list[dict]]:
    lines, structured = _format_bytecode_ranges(code, code_locs, functions, structured=True)
    return "\n".join(lines), lines, structured


def _format_bytecode_ranges(
    code: list[tuple],
    code_locs: list[tuple[str | None, int | None, int | None]],
    functions: dict[str, FunctionInfo],
    *,
    structured: bool,
) -> tuple[list[str], list[dict]]:
    lines: list[str] = []
    structured_out: list[dict] = []
    main_addr = 0
    if code and code[0][0] == "JUMP":
        main_addr = code[0][1]

    fn_list = sorted(functions.values(), key=lambda f: f.addr)
    fn_starts = [fn.addr for fn in fn_list]
    fn_ranges: list[tuple[str, int, int]] = []
    for idx, fn in enumerate(fn_list):
        start = fn.addr
        end = fn_list[idx + 1].addr if idx + 1 < len(fn_list) else main_addr
        fn_ranges.append((display_name(fn.name), start, end))

    ranges: list[tuple[str | None, int, int, int]] = []
    if fn_starts:
        init_end = fn_starts[0]
        if init_end > 0:
            lines.append("Program init:")
            ranges.append((None, 0, init_end, 0))

    for name, start, end in fn_ranges:
        lines.append(f"Function {name}:")
        ranges.append((name, start, end, start))

    if main_addr < len(code):
        lines.append("Function main:")
        ranges.append(("main", main_addr, len(code), main_addr))

    for _name, start, end, base in ranges:
        lines.extend(_format_range(code, code_locs, start, end, base=base))
        if structured:
            structured_out.extend(_format_structured_range(code, code_locs, start, end, base=base))

    return lines, structured_out


def _format_structured_range(
    code: list[tuple],
    code_locs: list[tuple[str | None, int | None, int | None]],
    start: int,
    end: int,
    *,
    base: int,
) -> list[dict]:
    out: list[dict] = []
    for ip in range(start, end):
        instr = code[ip]
        op = instr[0]
        operands = instr[1:]
        if len(operands) == 0:
            arg = None
        elif len(operands) == 1:
            arg = operands[0]
        else:
            arg = list(operands)
        entry = {"offset": ip - base, "opcode": op, "arg": arg}
        if ip < len(code_locs):
            _path, line, col = code_locs[ip]
            if line is not None and col is not None:
                entry["line"] = line
                entry["column"] = col
        out.append(entry)
    return out


def _format_range(
    code: list[tuple],
    code_locs: list[tuple[str | None, int | None, int | None]],
    start: int,
    end: int,
    base: int = 0,
) -> list[str]:
    out: list[str] = []
    for ip in range(start, end):
        instr = code[ip]
        op = instr[0]
        operands = instr[1:]
        formatted_ops = []
        for value in operands:
            if isinstance(value, str):
                formatted_ops.append(value)
            else:
                formatted_ops.append(repr(value))
        op_text = " ".join([op] + formatted_ops) if formatted_ops else op
        loc_text = format_loc(code_locs[ip]) if ip < len(code_locs) else None
        if loc_text:
            out.append(f"  {ip - base}: {op_text}  ({loc_text})")
        else:
            out.append(f"  {ip - base}: {op_text}")
    return out
