"""REPL support for Nodus."""

from dataclasses import dataclass
import os

from nodus.compiler.compiler import Compiler, wrap_bytecode
from nodus.runtime.diagnostics import format_error
from nodus.frontend.lexer import tokenize
from nodus.frontend.parser import Parser
from nodus.tooling.loader import resolve_imports
from nodus.vm.vm import VM
from nodus.frontend.ast.ast_nodes import FnDef


@dataclass
class ReplState:
    globals: dict
    fn_defs: dict[str, FnDef]
    import_state: dict


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
        depth += line.count("(") + line.count("[") + line.count("{")
        depth -= line.count(")") + line.count("]") + line.count("}")
    return depth <= 0


def run_repl(version: str):
    state = ReplState(globals={}, fn_defs={}, import_state={"loaded": set(), "loading": set(), "exports": {}, "modules": {}, "module_ids": {}, "project_root": None})
    print(f"{version} REPL (type 'exit' to quit)")

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
            stmts = Parser(tokenize(src)).parse()
            stmts = resolve_imports(stmts, os.getcwd(), state.import_state, "<repl>")
            new_defs, non_fn = split_fn_defs(stmts)

            merged_defs = dict(state.fn_defs)
            merged_defs.update(new_defs)
            program = list(merged_defs.values()) + non_fn

            module_infos = state.import_state.get("modules", {})
            defs_index: dict[str, set[str]] = {}
            for info in module_infos.values():
                for name in info.defs:
                    defs_index.setdefault(name, set()).add(info.path)
            compiler = Compiler(module_infos=module_infos, module_defs_index=defs_index)
            code, functions, code_locs = compiler.compile_program(program)
            vm = VM(wrap_bytecode(code), functions, code_locs=code_locs, initial_globals=dict(state.globals))
            vm.run()

            state.globals = vm.globals
            state.fn_defs = merged_defs
        except Exception as err:
            print(format_error(err))
