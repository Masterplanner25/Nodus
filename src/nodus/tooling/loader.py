"""Import resolution and compilation pipeline for Nodus."""

import os

from nodus.tooling.analyzer import analyze_program
from nodus.frontend.ast.ast_nodes import (
    Assign,
    Attr,
    Bin,
    Block,
    ExportList,
    ExportFrom,
    ExprStmt,
    FnDef,
    GoalDef,
    If,
    Import,
    Index,
    IndexAssign,
    Let,
    ListLit,
    MapLit,
    ModuleAlias,
    ModuleInfo,
    WorkflowDef,
    Call,
    Comment,
    Unary,
    While,
    For,
)
from nodus.runtime.diagnostics import LangRuntimeError, LangSyntaxError
from nodus.frontend.lexer import Tok, tokenize
from nodus.compiler.optimizer import optimize_bytecode
from nodus.frontend.parser import Parser
from nodus.compiler.compiler import Compiler, wrap_bytecode
from nodus.builtins.nodus_builtins import BUILTIN_NAMES
from nodus.tooling.project import NODUS_DIRNAME, MODULES_DIRNAME, find_project_root
from nodus.vm.vm import VM
from nodus.runtime.module_loader import ModuleLoader


def set_module_on_tree(node, module_id: str):
    if node is None:
        return
    if isinstance(node, list):
        for item in node:
            set_module_on_tree(item, module_id)
        return
    if not hasattr(node, "__dict__"):
        return
    setattr(node, "_module", module_id)
    for key, value in node.__dict__.items():
        if key in {"_tok", "_module"}:
            continue
        if isinstance(value, Tok):
            continue
        if isinstance(value, list):
            for item in value:
                set_module_on_tree(item, module_id)
        else:
            set_module_on_tree(value, module_id)


def get_module_prefix(import_state: dict, module_id: str) -> str:
    if "module_ids" not in import_state:
        import_state["module_ids"] = {}
    module_ids = import_state["module_ids"]
    if module_id not in module_ids:
        module_ids[module_id] = f"__mod{len(module_ids)}__"
    return module_ids[module_id]


def import_error(message: str, tok: Tok | None, module_id: str):
    line = tok.line if tok is not None else None
    col = tok.col if tok is not None else None
    raise LangRuntimeError("import", message, line=line, col=col, path=module_id)


def try_resolve_with_extensions(base_path: str) -> str | None:
    if base_path.endswith(".nd") or base_path.endswith(".tl"):
        full = os.path.abspath(base_path)
        if os.path.exists(full):
            return full
        return None

    candidates = [
        os.path.abspath(base_path + ".nd"),
        os.path.abspath(base_path + ".tl"),
        os.path.abspath(os.path.join(base_path, "index.nd")),
        os.path.abspath(os.path.join(base_path, "index.tl")),
    ]
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    return None


def resolve_with_extensions(base_path: str, import_path: str, tok: Tok | None, module_id: str) -> str:
    if base_path.endswith(".nd") or base_path.endswith(".tl"):
        full = os.path.abspath(base_path)
        if os.path.exists(full):
            return full
        import_error(f"Import not found: {import_path} (tried {full})", tok, module_id)

    candidates = [
        os.path.abspath(base_path + ".nd"),
        os.path.abspath(base_path + ".tl"),
        os.path.abspath(os.path.join(base_path, "index.nd")),
        os.path.abspath(os.path.join(base_path, "index.tl")),
    ]

    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate

    import_error(
        f"Import not found: {import_path} (tried {', '.join(candidates)})",
        tok,
        module_id,
    )


def resolve_import_path(import_path: str, base_dir: str, import_state: dict, tok: Tok | None, module_id: str) -> str:
    project_root = os.path.abspath(import_state.get("project_root") or base_dir)
    modules_dir = os.path.join(project_root, NODUS_DIRNAME, MODULES_DIRNAME)

    if ":" in import_path and not import_path.startswith("std:"):
        package_name, package_path = import_path.split(":", 1)
        if not package_name or not package_path:
            import_error("Invalid package import: use package:module", tok, module_id)
        if package_name.startswith(".") or package_name.startswith(("/", "\\")):
            import_error("Invalid package import: package name is invalid", tok, module_id)
        package_base = os.path.normpath(os.path.join(modules_dir, package_name, package_path.replace("/", os.sep).replace("\\", os.sep)))
        package_root = os.path.normpath(os.path.join(modules_dir, package_name))
        if not package_base.startswith(package_root):
            import_error("Invalid package import: path escapes dependency directory", tok, module_id)
        return resolve_with_extensions(package_base, import_path, tok, module_id)

    if import_path.startswith("std:"):
        name = import_path[4:]
        if not name:
            import_error("Invalid std import: missing module name (use std:strings)", tok, module_id)
        if name.startswith(("/", "\\")):
            import_error("Invalid std import: std modules cannot start with '/'", tok, module_id)
        std_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "stdlib"))
        name = name.replace("/", os.sep).replace("\\", os.sep)
        base = os.path.normpath(os.path.join(std_dir, name))
        std_dir_norm = os.path.normpath(std_dir)
        if not base.startswith(std_dir_norm):
            import_error("Invalid std import: path escapes std directory", tok, module_id)
        return resolve_with_extensions(base, import_path, tok, module_id)

    if os.path.isabs(import_path):
        base = import_path
    elif import_path.startswith("."):
        base = os.path.join(base_dir, import_path)
    else:
        base = os.path.join(project_root, import_path)

    base = os.path.normpath(base)
    resolved = try_resolve_with_extensions(base)
    if resolved is not None:
        return resolved

    modules_base = os.path.normpath(os.path.join(modules_dir, import_path))
    resolved = try_resolve_with_extensions(modules_base)
    if resolved is not None:
        return resolved

    return resolve_with_extensions(base, import_path, tok, module_id)


def collect_module_info(stmts: list, module_id: str, prefix: str) -> ModuleInfo:
    defs: set[str] = set()
    explicit_exports = False
    explicit: set[str] = set()
    reexports: set[str] = set()

    def walk_expr(e):
        if e is None:
            return
        if isinstance(e, Assign):
            defs.add(e.name)
            walk_expr(e.expr)
            return
        if isinstance(e, Unary):
            walk_expr(e.expr)
            return
        if isinstance(e, Bin):
            walk_expr(e.a)
            walk_expr(e.b)
            return
        if isinstance(e, ListLit):
            for item in e.items:
                walk_expr(item)
            return
        if isinstance(e, MapLit):
            for k, v in e.items:
                walk_expr(k)
                walk_expr(v)
            return
        if isinstance(e, Index):
            walk_expr(e.seq)
            walk_expr(e.index)
            return
        if isinstance(e, IndexAssign):
            walk_expr(e.seq)
            walk_expr(e.index)
            walk_expr(e.value)
            return
        if isinstance(e, Attr):
            walk_expr(e.obj)
            return
        if isinstance(e, Call):
            walk_expr(e.callee)
            for arg in e.args:
                walk_expr(arg)
            return

    def walk_stmt(s):
        nonlocal explicit_exports
        if isinstance(s, Comment):
            return
        if isinstance(s, Let):
            defs.add(s.name)
            if s.exported:
                explicit_exports = True
                explicit.add(s.name)
            walk_expr(s.expr)
            return
        if isinstance(s, WorkflowDef):
            defs.add(s.name)
            return
        if isinstance(s, GoalDef):
            defs.add(s.name)
            return
        if isinstance(s, FnDef):
            defs.add(s.name)
            if s.exported:
                explicit_exports = True
                explicit.add(s.name)
            return
        if isinstance(s, ExportList):
            explicit_exports = True
            explicit.update(s.names)
            return
        if isinstance(s, ExportFrom):
            explicit_exports = True
            reexports.update(s.names)
            return
        if isinstance(s, ExprStmt):
            walk_expr(s.expr)
            return
        if isinstance(s, If):
            walk_expr(s.cond)
            walk_stmt(s.then_branch)
            if s.else_branch is not None:
                walk_stmt(s.else_branch)
            return
        if isinstance(s, While):
            walk_expr(s.cond)
            walk_stmt(s.body)
            return
        if isinstance(s, For):
            walk_stmt(s.init)
            walk_expr(s.cond)
            walk_expr(s.inc)
            walk_stmt(s.body)
            return
        if isinstance(s, Block):
            for inner in s.stmts:
                walk_stmt(inner)
            return

    for stmt in stmts:
        walk_stmt(stmt)

    exports = (explicit | reexports) if explicit_exports else set(defs)

    if explicit_exports:
        missing = [name for name in explicit if name not in defs]
        if missing:
            line = None
            col = None
            for stmt in stmts:
                if isinstance(stmt, ExportList):
                    tok = getattr(stmt, "_tok", None)
                    if tok is not None:
                        line = tok.line
                        col = tok.col
                        break
            raise LangSyntaxError(
                f"Exported name(s) not defined in module: {', '.join(missing)}",
                line=line,
                col=col,
                path=module_id,
            )

    qualified = {name: f"{prefix}{name}" for name in defs}

    return ModuleInfo(
        path=module_id,
        defs=defs,
        exports=exports,
        imports={},
        aliases={},
        explicit_exports=explicit_exports,
        qualified=qualified,
    )


def apply_import_to_module(
    module_info: ModuleInfo,
    import_stmt: Import,
    imported_module: ModuleInfo,
    full_path: str,
):
    if import_stmt.names is not None:
        missing = [name for name in import_stmt.names if name not in imported_module.exports]
        if missing:
            tok = getattr(import_stmt, "_tok", None)
            line = tok.line if tok is not None else None
            col = tok.col if tok is not None else None
            raise LangRuntimeError(
                "import",
                f"Import failed: {full_path} does not export {', '.join(missing)}",
                line=line,
                col=col,
                path=full_path,
            )
        for name in import_stmt.names:
            module_info.imports[name] = imported_module.qualified[name]
        return

    if import_stmt.alias is not None:
        module_info.aliases[import_stmt.alias] = {
            name: imported_module.qualified[name]
            for name in imported_module.exports
        }
        return

    for name in imported_module.exports:
        module_info.imports[name] = imported_module.qualified[name]


def resolve_imports(stmts: list, base_dir: str, import_state: dict, module_id: str) -> list:
    if "modules" not in import_state:
        import_state["modules"] = {}

    if module_id not in import_state["modules"]:
        prefix = get_module_prefix(import_state, module_id)
        import_state["modules"][module_id] = collect_module_info(stmts, module_id, prefix)

    set_module_on_tree(stmts, module_id)
    module_info = import_state["modules"][module_id]

    out = []
    for stmt in stmts:
        if not isinstance(stmt, (Import, ExportFrom)):
            out.append(stmt)
            continue

        import_path = stmt.path
        tok = getattr(stmt, "_tok", None)
        full_path = resolve_import_path(import_path, base_dir, import_state, tok, module_id)

        if full_path in import_state["loaded"]:
            imported_module = import_state["modules"][full_path]
            if isinstance(stmt, ExportFrom):
                apply_reexport_to_module(module_info, stmt, imported_module, full_path)
                continue
            apply_import_to_module(module_info, stmt, imported_module, full_path)
            if stmt.alias is not None:
                alias_stmt = ModuleAlias(
                    stmt.alias,
                    {name: imported_module.qualified[name] for name in imported_module.exports},
                )
                setattr(alias_stmt, "_tok", getattr(stmt, "_tok", None))
                setattr(alias_stmt, "_module", module_id)
                out.append(alias_stmt)
            continue
        if full_path in import_state["loading"]:
            import_error(f"Cyclic import detected: {full_path}", tok, module_id)

        import_state["loading"].add(full_path)
        try:
            try:
                with open(full_path, "r", encoding="utf-8") as f:
                    imported_src = f.read()
            except FileNotFoundError:
                import_error(f"Import not found: {import_path} (resolved to {full_path})", tok, module_id)

            try:
                imported_stmts = Parser(tokenize(imported_src)).parse()
            except Exception as err:
                if isinstance(err, LangSyntaxError) and err.path is None:
                    err.path = full_path
                raise

            if full_path not in import_state["modules"]:
                prefix = get_module_prefix(import_state, full_path)
                import_state["modules"][full_path] = collect_module_info(imported_stmts, full_path, prefix)
            imported_module = import_state["modules"][full_path]
            import_state["exports"][full_path] = imported_module.exports

            nested = resolve_imports(imported_stmts, os.path.dirname(full_path), import_state, full_path)
            out.extend(nested)
            if isinstance(stmt, ExportFrom):
                apply_reexport_to_module(module_info, stmt, imported_module, full_path)
            else:
                apply_import_to_module(module_info, stmt, imported_module, full_path)
                if stmt.alias is not None:
                    alias_stmt = ModuleAlias(
                        stmt.alias,
                        {name: imported_module.qualified[name] for name in imported_module.exports},
                    )
                    setattr(alias_stmt, "_tok", getattr(stmt, "_tok", None))
                    setattr(alias_stmt, "_module", module_id)
                    out.append(alias_stmt)
            import_state["loaded"].add(full_path)
        finally:
            import_state["loading"].discard(full_path)

    return out


def ensure_project_root(import_state: dict, base_dir: str, source_path: str | None):
    if "project_root" not in import_state:
        import_state["project_root"] = None
    if import_state["project_root"] is None:
        env_root = os.environ.get("NODUS_PROJECT_ROOT")
        if env_root:
            import_state["project_root"] = env_root

    project_root = import_state.get("project_root")
    if project_root is None:
        discovered_root = find_project_root(base_dir)
        import_state["project_root"] = discovered_root or base_dir
        return

    project_root = os.path.abspath(project_root)
    if not os.path.isdir(project_root):
        raise LangRuntimeError(
            "import",
            f"Invalid project root: {project_root}",
            path=source_path,
        )
    import_state["project_root"] = project_root


def apply_reexport_to_module(
    module_info: ModuleInfo,
    export_stmt: ExportFrom,
    imported_module: ModuleInfo,
    full_path: str,
):
    missing = [name for name in export_stmt.names if name not in imported_module.exports]
    if missing:
        tok = getattr(export_stmt, "_tok", None)
        line = tok.line if tok is not None else None
        col = tok.col if tok is not None else None
        raise LangRuntimeError(
            "import",
            f"Re-export failed: {full_path} does not export {', '.join(missing)}",
            line=line,
            col=col,
            path=full_path,
        )

    conflicts = [name for name in export_stmt.names if name in module_info.defs]
    if conflicts:
        tok = getattr(export_stmt, "_tok", None)
        line = tok.line if tok is not None else None
        col = tok.col if tok is not None else None
        raise LangRuntimeError(
            "import",
            f"Re-export conflicts with local definition(s): {', '.join(conflicts)}",
            line=line,
            col=col,
            path=module_info.path,
        )

    for name in export_stmt.names:
        module_info.imports[name] = imported_module.qualified[name]
        module_info.qualified[name] = imported_module.qualified[name]
        module_info.exports.add(name)


def compile_source(
    src: str,
    source_path: str | None = None,
    import_state: dict | None = None,
    analyze: bool = False,
    optimize: bool = True,
    extra_builtins: set[str] | None = None,
):
    try:
        toks = tokenize(src)
        ast = Parser(toks).parse()
    except Exception as err:
        if isinstance(err, LangSyntaxError) and err.path is None:
            err.path = source_path
        raise
    module_id = os.path.abspath(source_path) if source_path else "<memory>"
    set_module_on_tree(ast, module_id)
    if analyze:
        analyze_program(ast)
    base_dir = os.path.dirname(os.path.abspath(source_path)) if source_path else os.getcwd()
    if import_state is None:
        import_state = {"loaded": set(), "loading": set(), "exports": {}, "modules": {}, "module_ids": {}}
    import_state.setdefault("loaded", set())
    import_state.setdefault("loading", set())
    import_state.setdefault("exports", {})
    import_state.setdefault("modules", {})
    import_state.setdefault("module_ids", {})
    ensure_project_root(import_state, base_dir, source_path)

    resolved_ast = resolve_imports(ast, base_dir, import_state, module_id)
    if module_id not in import_state["modules"]:
        prefix = get_module_prefix(import_state, module_id)
        import_state["modules"][module_id] = collect_module_info(resolved_ast, module_id, prefix)

    module_defs_index: dict[str, set[str]] = {}
    for path, module_info in import_state["modules"].items():
        for name in module_info.defs:
            module_defs_index.setdefault(name, set()).add(path)

    builtin_names = set(BUILTIN_NAMES)
    if extra_builtins:
        builtin_names.update(extra_builtins)
    compiler = Compiler(
        module_infos=import_state["modules"],
        module_defs_index=module_defs_index,
        builtin_names=builtin_names,
    )
    code, functions, code_locs = compiler.compile_program(resolved_ast)
    module_info = import_state["modules"][module_id]
    bytecode = wrap_bytecode(
        code,
        module_name=module_id,
        exports=sorted(module_info.exports),
    )
    if optimize:
        code, functions, code_locs = optimize_bytecode(bytecode.get("instructions", []), functions, code_locs)
        bytecode = wrap_bytecode(
            code,
            module_name=bytecode.get("module_name"),
            exports=bytecode.get("exports", []),
            constants=bytecode.get("constants", []),
            metadata=bytecode.get("metadata", {}),
        )
    return ast, bytecode, functions, code_locs


def run_source(
    src: str,
    initial_globals: dict | None = None,
    input_fn=None,
    source_path: str | None = None,
    import_state: dict | None = None,
):
    project_root = None
    if import_state is not None:
        project_root = import_state.get("project_root")
    vm = VM([], {}, code_locs=[], initial_globals=initial_globals, input_fn=input_fn, source_path=source_path)
    loader = ModuleLoader(project_root=project_root, vm=vm)
    if source_path:
        loader.load_module_from_path(source_path, initial_globals=initial_globals)
    else:
        loader.load_module_from_source(src, initial_globals=initial_globals)
    return vm
