"""REPL support for Nodus."""

from dataclasses import dataclass
import os

from nodus.compiler.compiler import Compiler, wrap_bytecode
from nodus.runtime.diagnostics import format_error
from nodus.frontend.lexer import tokenize
from nodus.frontend.parser import Parser
from nodus.tooling.loader import set_module_on_tree
from nodus.runtime.module_loader import ModuleLoader
from nodus.vm.vm import VM
from nodus.frontend.ast.ast_nodes import FnDef
from nodus.builtins.nodus_builtins import BUILTIN_NAMES


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
    loader = ModuleLoader(project_root=os.getcwd())
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
            set_module_on_tree(stmts, "<repl>")
            metadata = loader._build_metadata("<repl>", base_dir=os.getcwd(), source=src, source_path=None)
            bindings, _deps = loader._resolve_import_bindings(metadata)
            state.globals.update(bindings)
            new_defs, non_fn = split_fn_defs(stmts)

            merged_defs = dict(state.fn_defs)
            merged_defs.update(new_defs)
            program = list(merged_defs.values()) + non_fn

            module_info = metadata.module_info
            module_info.imports = {name: name for name in metadata.import_names}
            module_info.qualified = {name: name for name in module_info.defs}
            compiler = Compiler(module_infos={"<repl>": module_info}, module_defs_index={}, builtin_names=BUILTIN_NAMES)
            code, functions, code_locs = compiler.compile_program(program)
            vm = VM(
                wrap_bytecode(code, module_name="<repl>"),
                functions,
                code_locs=code_locs,
                module_globals=state.globals,
                source_path="<repl>",
            )
            vm.run()

            state.globals = vm.module_globals
            state.fn_defs = merged_defs
        except Exception as err:
            print(format_error(err))
