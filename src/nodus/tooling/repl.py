"""REPL support for Nodus."""

from __future__ import annotations

from dataclasses import dataclass
import os

from nodus.builtins.nodus_builtins import BUILTIN_NAMES
from nodus.compiler.compiler import Compiler, format_bytecode, wrap_bytecode
from nodus.frontend.ast.ast_nodes import (
    Attr,
    Bin,
    Bool,
    Call,
    ExprStmt,
    FnDef,
    Index,
    ListLit,
    MapLit,
    Nil,
    Num,
    Str,
    Unary,
    Var,
)
from nodus.frontend.lexer import tokenize
from nodus.frontend.parser import Parser
from nodus.orchestration.task_graph import TaskGraph, TaskNode
from nodus.runtime.coroutine import Coroutine
from nodus.runtime.channel import Channel
from nodus.runtime.diagnostics import format_error
from nodus.tooling.loader import set_module_on_tree
from nodus.runtime.module_loader import ModuleLoader
from nodus.vm.vm import Closure, Record, VM

try:
    import readline
except ImportError:  # pragma: no cover - platform dependent
    readline = None


HISTORY_FILE = os.path.expanduser("~/.nodus_history")
HELP_TEXT = "\n".join(
    [
        "Nodus REPL Commands",
        "",
        ":ast <expr>    show AST",
        ":dis <expr>    show bytecode",
        ":type <expr>   show inferred type",
        ":help          show commands",
        ":quit          exit REPL",
    ]
)
TYPE_TEMP_NAME = "__repl_type_value__"


@dataclass
class ReplState:
    globals: dict
    fn_defs: dict[str, FnDef]
    import_state: dict


@dataclass
class ReplCommand:
    name: str
    arg: str


def split_fn_defs(stmts: list):
    fn_defs = {}
    non_fn = []
    for stmt in stmts:
        if isinstance(stmt, FnDef):
            fn_defs[stmt.name] = stmt
        else:
            non_fn.append(stmt)
    return fn_defs, non_fn


def is_complete_chunk(lines: list[str]) -> bool:
    depth = 0
    for line in lines:
        depth += line.count("{")
        depth -= line.count("}")
    return depth <= 0


def parse_repl_command(src: str) -> ReplCommand | None:
    stripped = src.strip()
    if not stripped.startswith(":"):
        return None
    body = stripped[1:].strip()
    if not body:
        raise ValueError("Empty REPL command. Use :help for available commands.")
    name, _, arg = body.partition(" ")
    return ReplCommand(name=name.lower(), arg=arg.strip())


def _setup_history() -> None:
    if readline is None:
        return
    try:
        readline.read_history_file(HISTORY_FILE)
    except FileNotFoundError:
        pass
    readline.set_history_length(1000)


def _save_history() -> None:
    if readline is None:
        return
    try:
        readline.write_history_file(HISTORY_FILE)
    except OSError:
        pass


def _parse_repl_ast(src: str):
    stmts = Parser(tokenize(src)).parse()
    set_module_on_tree(stmts, "<repl>")
    return stmts


def _parse_repl_expression(src: str):
    stmts = _parse_repl_ast(src)
    if len(stmts) != 1 or not isinstance(stmts[0], ExprStmt):
        raise ValueError("Expected a single expression.")
    return stmts[0].expr


def format_expression_ast(src: str) -> str:
    expr = _parse_repl_expression(src)
    lines: list[str] = []
    _format_expr_node(expr, 0, lines)
    return "\n".join(lines)


def _format_expr_node(node, indent: int, lines: list[str]) -> None:
    prefix = "  " * indent
    if isinstance(node, Num):
        value = node.raw if node.raw is not None else str(node.v)
        lines.append(f"{prefix}Number({value})")
        return
    if isinstance(node, Bool):
        lines.append(f"{prefix}Bool({str(node.v).lower()})")
        return
    if isinstance(node, Str):
        lines.append(f'{prefix}String("{node.v}")')
        return
    if isinstance(node, Nil):
        lines.append(f"{prefix}Nil")
        return
    if isinstance(node, Var):
        lines.append(f"{prefix}Identifier({node.name})")
        return
    if isinstance(node, Unary):
        lines.append(f"{prefix}Unary({node.op})")
        _format_expr_node(node.expr, indent + 1, lines)
        return
    if isinstance(node, Bin):
        lines.append(f"{prefix}Binary({node.op})")
        _format_expr_node(node.a, indent + 1, lines)
        _format_expr_node(node.b, indent + 1, lines)
        return
    if isinstance(node, ListLit):
        lines.append(f"{prefix}List")
        for item in node.items:
            _format_expr_node(item, indent + 1, lines)
        return
    if isinstance(node, MapLit):
        lines.append(f"{prefix}Map")
        for key, value in node.items:
            lines.append(f"{prefix}  Entry")
            _format_expr_node(key, indent + 2, lines)
            _format_expr_node(value, indent + 2, lines)
        return
    if isinstance(node, Attr):
        lines.append(f"{prefix}Attr({node.name})")
        _format_expr_node(node.obj, indent + 1, lines)
        return
    if isinstance(node, Index):
        lines.append(f"{prefix}Index")
        _format_expr_node(node.seq, indent + 1, lines)
        _format_expr_node(node.index, indent + 1, lines)
        return
    if isinstance(node, Call):
        lines.append(f"{prefix}Call")
        _format_expr_node(node.callee, indent + 1, lines)
        for arg in node.args:
            _format_expr_node(arg, indent + 1, lines)
        return
    lines.append(f"{prefix}{type(node).__name__}")


def _build_compiler() -> Compiler:
    return Compiler(module_infos={"<repl>": None}, module_defs_index={}, builtin_names=BUILTIN_NAMES)


def _compile_repl_program(state: ReplState, stmts: list):
    program = list(state.fn_defs.values()) + stmts
    compiler = Compiler(module_infos={"<repl>": None}, module_defs_index={}, builtin_names=BUILTIN_NAMES)
    code, functions, code_locs = compiler.compile_program(program)
    return wrap_bytecode(code, module_name="<repl>"), functions, code_locs


def _compile_repl_expression(state: ReplState, src: str):
    expr = _parse_repl_expression(src)
    compiler = _build_compiler()
    jump_to_main = compiler.emit("JUMP", None)
    compiler.current_module = "<repl>"
    fn_defs = list(state.fn_defs.values())
    compiler.predeclare_module_scopes(fn_defs)
    for fn in fn_defs:
        compiler.compile_fn_def(fn)
    main_addr = len(compiler.code)
    compiler.patch(jump_to_main, "JUMP", main_addr)
    compiler.compile_expr(expr)
    compiler.emit("RETURN")
    return compiler.code, compiler.functions, compiler.code_locs, main_addr


def disassemble_expression(state: ReplState, src: str) -> str:
    code, functions, code_locs, main_addr = _compile_repl_expression(state, src)
    text = format_bytecode(code, code_locs, functions)
    lines = []
    in_main = False
    for line in text.splitlines():
        if line == "Function main:":
            in_main = True
            continue
        if in_main and line.startswith("Function "):
            break
        if not in_main:
            continue
        body = line.strip()
        if ": " in body:
            body = body.split(": ", 1)[1]
        if "  (" in body and body.endswith(")"):
            body = body.rsplit("  (", 1)[0]
        if body.endswith("HALT"):
            continue
        lines.append(body)
    if not lines:
        for instr in code[main_addr:]:
            op = instr[0]
            if op == "HALT":
                continue
            operands = " ".join(repr(value) if not isinstance(value, str) else value for value in instr[1:])
            lines.append(f"{op} {operands}".strip())
    return "\n".join(lines)


def infer_expression_type(state: ReplState, src: str) -> str:
    expr = _parse_repl_expression(src)
    temp_stmt = Parser(tokenize(f"let {TYPE_TEMP_NAME} = 0")).parse()[0]
    temp_stmt.expr = expr
    set_module_on_tree([temp_stmt], "<repl>")
    bytecode, functions, code_locs = _compile_repl_program(state, [temp_stmt])
    vm = VM(
        bytecode,
        functions,
        code_locs=code_locs,
        module_globals=state.globals,
        source_path="<repl>",
    )
    vm.run()
    try:
        return describe_runtime_type(vm.module_globals.get(TYPE_TEMP_NAME))
    finally:
        vm.module_globals.pop(TYPE_TEMP_NAME, None)


def describe_runtime_type(value) -> str:
    if value is None:
        return "nil"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        inner = _merge_types(describe_runtime_type(item) for item in value)
        return f"List<{inner}>"
    if isinstance(value, dict):
        key_type = _merge_types(describe_runtime_type(item) for item in value.keys())
        value_type = _merge_types(describe_runtime_type(item) for item in value.values())
        return f"Map<{key_type},{value_type}>"
    if isinstance(value, Record):
        return value.kind
    if isinstance(value, Closure):
        return "function"
    if isinstance(value, Coroutine):
        return "coroutine"
    if isinstance(value, Channel):
        return "channel"
    if isinstance(value, TaskNode):
        return "task"
    if isinstance(value, TaskGraph):
        return "graph"
    return "unknown"


def _merge_types(values) -> str:
    types = sorted(set(values))
    if not types:
        return "any"
    if len(types) == 1:
        return types[0]
    return "mixed"


def execute_repl_command(state: ReplState, src: str) -> tuple[bool, str | None, bool]:
    command = parse_repl_command(src)
    if command is None:
        return False, None, False
    if command.name == "help":
        return True, HELP_TEXT, False
    if command.name == "quit":
        return True, None, True
    if command.name == "ast":
        if not command.arg:
            raise ValueError("Usage: :ast <expr>")
        return True, format_expression_ast(command.arg), False
    if command.name == "dis":
        if not command.arg:
            raise ValueError("Usage: :dis <expr>")
        return True, disassemble_expression(state, command.arg), False
    if command.name == "type":
        if not command.arg:
            raise ValueError("Usage: :type <expr>")
        return True, infer_expression_type(state, command.arg), False
    raise ValueError(f"Unknown REPL command: :{command.name}")


def _execute_source(state: ReplState, loader: ModuleLoader, src: str) -> None:
    stmts = _parse_repl_ast(src)
    metadata = loader._build_metadata("<repl>", base_dir=os.getcwd(), source=src, source_path=None)
    bindings, _deps = loader._resolve_import_bindings(metadata)
    state.globals.update(bindings)
    new_defs, non_fn = split_fn_defs(stmts)
    merged_defs = dict(state.fn_defs)
    merged_defs.update(new_defs)

    bytecode, functions, code_locs = _compile_repl_program(
        ReplState(globals=state.globals, fn_defs=merged_defs, import_state=state.import_state),
        non_fn,
    )
    vm = VM(
        bytecode,
        functions,
        code_locs=code_locs,
        module_globals=state.globals,
        source_path="<repl>",
    )
    vm.run()
    state.globals = vm.module_globals
    state.fn_defs = merged_defs


def run_repl(version: str):
    state = ReplState(
        globals={},
        fn_defs={},
        import_state={"loaded": set(), "loading": set(), "exports": {}, "modules": {}, "module_ids": {}, "project_root": None},
    )
    loader = ModuleLoader(project_root=os.getcwd())
    _setup_history()
    print(f"{version} REPL (type 'exit', 'quit', or ':quit' to quit)")

    try:
        while True:
            lines = []
            prompt = "> "

            while True:
                try:
                    line = input(prompt)
                except EOFError:
                    print()
                    return

                if not lines and line.strip() in {"exit", "quit"}:
                    return

                lines.append(line)
                if is_complete_chunk(lines):
                    break
                prompt = "... "

            src = "\n".join(lines).strip()
            if not src:
                continue

            try:
                handled, output, should_exit = execute_repl_command(state, src)
                if handled:
                    if output:
                        print(output)
                    if should_exit:
                        return
                    continue
                _execute_source(state, loader, src)
            except Exception as err:
                print(format_error(err))
    finally:
        _save_history()
