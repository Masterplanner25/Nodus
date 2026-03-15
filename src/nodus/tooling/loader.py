"""Import resolution and compilation pipeline for Nodus."""

# =============================================================================
# COMPILATION PIPELINES
# =============================================================================
# Two compilation pipelines exist in this module:
#
#   ModuleLoader (runtime/module_loader.py) — CANONICAL pipeline
#       Used by: nodus run (via run_source in this module)
#       Preferred for all new code and embeddings.
#
# The module_prefix scheme (__modN__) is used to qualify names from imported
# modules, avoiding collisions when multiple modules are flattened into a
# single bytecode unit during compilation.
# =============================================================================

import os
import warnings

from nodus.tooling.analyzer import analyze_program
from nodus.frontend.visitor import NodeVisitor
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


class ModuleStamper(NodeVisitor):
    """Stamps every AST node in a tree with its originating module path.

    Extends NodeVisitor with a generic visit_default that recurses into all
    child nodes and sets _module on each, rather than requiring an explicit
    visit method per node type.
    """

    def __init__(self, module_id: str) -> None:
        self.module_id = module_id

    def stamp(self, node) -> None:
        """Recursively stamp *node* and all its descendants."""
        if node is None:
            return
        if isinstance(node, list):
            for item in node:
                self.stamp(item)
            return
        if hasattr(node, "__dict__"):
            self.visit(node)

    def visit_default(self, node) -> None:
        """Generic stamp: set _module on *node* then recurse into children."""
        node._module = self.module_id
        for key, value in node.__dict__.items():
            if key in {"_tok", "_module"}:
                continue
            if isinstance(value, Tok):
                continue
            if isinstance(value, list):
                for item in value:
                    if item is not None and hasattr(item, "__dict__"):
                        self.visit(item)
            elif value is not None and hasattr(value, "__dict__"):
                self.visit(value)


def set_module_on_tree(node, module_id: str):
    """Recursively stamp every AST node in *node* with *module_id*.

    Delegates to :class:`ModuleStamper`.  Call sites may also use
    ``ModuleStamper(module_id).stamp(node)`` directly.
    """
    ModuleStamper(module_id).stamp(node)


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
        base_norm = os.path.normcase(os.path.normpath(base))
        root_norm = os.path.normcase(os.path.normpath(project_root))
        try:
            if os.path.commonpath([base_norm, root_norm]) != root_norm:
                import_error("Invalid import: path escapes project root", tok, module_id)
        except ValueError:
            import_error("Invalid import: path escapes project root", tok, module_id)
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


class InfoCollector(NodeVisitor):
    """Collects module definition and export information from an AST.

    Extends NodeVisitor to walk statement and expression nodes, recording
    which names are defined and exported in the module.
    """

    def __init__(self, module_id: str, prefix: str) -> None:
        self.module_id = module_id
        self.prefix = prefix
        self.defs: set[str] = set()
        self.explicit_exports = False
        self.explicit: set[str] = set()
        self.reexports: set[str] = set()

    def collect(self, stmts: list) -> "ModuleInfo":
        for stmt in stmts:
            self.visit(stmt)
        exports = (self.explicit | self.reexports) if self.explicit_exports else set(self.defs)
        if self.explicit_exports:
            missing = [name for name in self.explicit if name not in self.defs]
            if missing:
                line = None
                col = None
                for stmt in stmts:
                    if isinstance(stmt, ExportList):
                        tok = stmt._tok
                        if tok is not None:
                            line = tok.line
                            col = tok.col
                            break
                raise LangSyntaxError(
                    f"Exported name(s) not defined in module: {', '.join(missing)}",
                    line=line,
                    col=col,
                    path=self.module_id,
                )
        qualified = {name: f"{self.prefix}{name}" for name in self.defs}
        return ModuleInfo(
            path=self.module_id,
            defs=self.defs,
            exports=exports,
            imports={},
            aliases={},
            explicit_exports=self.explicit_exports,
            qualified=qualified,
        )

    # --- Statement visitors ---

    def visit_Comment(self, stmt): pass
    def visit_Import(self, stmt): pass
    def visit_ModuleAlias(self, stmt): pass

    def visit_ExportFrom(self, stmt):
        self.explicit_exports = True
        self.reexports.update(stmt.names)

    def visit_Let(self, stmt):
        self.defs.add(stmt.name)
        if stmt.exported:
            self.explicit_exports = True
            self.explicit.add(stmt.name)
        self.visit(stmt.expr)

    def visit_WorkflowDef(self, stmt):
        self.defs.add(stmt.name)

    def visit_GoalDef(self, stmt):
        self.defs.add(stmt.name)

    def visit_FnDef(self, stmt):
        self.defs.add(stmt.name)
        if stmt.exported:
            self.explicit_exports = True
            self.explicit.add(stmt.name)

    def visit_ExportList(self, stmt):
        self.explicit_exports = True
        self.explicit.update(stmt.names)

    def visit_ExprStmt(self, stmt):
        self.visit(stmt.expr)

    def visit_If(self, stmt):
        self.visit(stmt.cond)
        self.visit(stmt.then_branch)
        if stmt.else_branch is not None:
            self.visit(stmt.else_branch)

    def visit_While(self, stmt):
        self.visit(stmt.cond)
        self.visit(stmt.body)

    def visit_For(self, stmt):
        self.visit(stmt.init)
        self.visit(stmt.cond)
        self.visit(stmt.inc)
        self.visit(stmt.body)

    def visit_Block(self, stmt):
        for inner in stmt.stmts:
            self.visit(inner)

    # --- Expression visitors (return nothing; only walk sub-expressions) ---

    def visit_Assign(self, expr):
        self.defs.add(expr.name)
        self.visit(expr.expr)

    def visit_Unary(self, expr):
        self.visit(expr.expr)

    def visit_Bin(self, expr):
        self.visit(expr.a)
        self.visit(expr.b)

    def visit_ListLit(self, expr):
        for item in expr.items:
            self.visit(item)

    def visit_MapLit(self, expr):
        for k, v in expr.items:
            self.visit(k)
            self.visit(v)

    def visit_Index(self, expr):
        self.visit(expr.seq)
        self.visit(expr.index)

    def visit_IndexAssign(self, expr):
        self.visit(expr.seq)
        self.visit(expr.index)
        self.visit(expr.value)

    def visit_Attr(self, expr):
        self.visit(expr.obj)

    def visit_Call(self, expr):
        self.visit(expr.callee)
        for arg in expr.args:
            self.visit(arg)

    # Leaf nodes (no children to walk)
    def visit_Num(self, expr): pass
    def visit_Bool(self, expr): pass
    def visit_Str(self, expr): pass
    def visit_Nil(self, expr): pass
    def visit_Var(self, expr): pass
    def visit_FnExpr(self, expr): pass
    def visit_RecordLiteral(self, expr): pass
    def visit_DestructureLet(self, stmt): pass
    def visit_CheckpointStmt(self, stmt): pass
    def visit_WorkflowStep(self, node): pass
    def visit_GoalStep(self, node): pass
    def visit_WorkflowStateDecl(self, node): pass
    def visit_ActionStmt(self, expr): pass
    def visit_Return(self, stmt): pass
    def visit_Throw(self, stmt): pass
    def visit_TryCatch(self, stmt): pass
    def visit_ForEach(self, stmt): pass
    def visit_Print(self, stmt): pass
    def visit_Yield(self, stmt): pass
    def visit_FieldAssign(self, expr): pass
    def visit_ListPattern(self, node): pass
    def visit_RecordPattern(self, node): pass
    def visit_VarPattern(self, node): pass

    def visit_default(self, node):
        # Silently skip unknown node types (e.g. future additions)
        pass


def collect_module_info(stmts: list, module_id: str, prefix: str) -> ModuleInfo:
    """Collect definition and export information from *stmts*.

    Delegates to :class:`InfoCollector`.
    """
    return InfoCollector(module_id, prefix).collect(stmts)


def apply_import_to_module(
    module_info: ModuleInfo,
    import_stmt: Import,
    imported_module: ModuleInfo,
    full_path: str,
):
    if import_stmt.names is not None:
        missing = [name for name in import_stmt.names if name not in imported_module.exports]
        if missing:
            tok = import_stmt._tok
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


# Maximum import chain depth before raising a clean error instead of a
# Python RecursionError.  Override with the NODUS_MAX_IMPORT_DEPTH env var.
_DEFAULT_MAX_IMPORT_DEPTH = 100


def _max_import_depth() -> int:
    try:
        return int(os.environ.get("NODUS_MAX_IMPORT_DEPTH", _DEFAULT_MAX_IMPORT_DEPTH))
    except (TypeError, ValueError):
        return _DEFAULT_MAX_IMPORT_DEPTH


def resolve_imports(
    stmts: list,
    base_dir: str,
    import_state: dict,
    module_id: str,
    _depth: int = 0,
) -> list:
    """Recursively resolve imports for *stmts* belonging to *module_id*.

    *_depth* tracks the current import chain depth.  When it exceeds the
    configured limit (default 100, overridable via NODUS_MAX_IMPORT_DEPTH)
    a ``LangSyntaxError`` is raised instead of letting Python hit its own
    recursion limit with an unhelpful ``RecursionError``.
    """
    limit = _max_import_depth()
    if _depth > limit:
        raise LangSyntaxError(
            f"Import depth limit exceeded ({limit}). "
            "Check for unusually deep or near-cyclic import chains.",
            path=module_id,
        )

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
        tok = stmt._tok
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
                alias_stmt._tok = stmt._tok
                alias_stmt._module = module_id
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

            nested = resolve_imports(
                imported_stmts,
                os.path.dirname(full_path),
                import_state,
                full_path,
                _depth + 1,
            )
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
                    alias_stmt._tok = stmt._tok
                    alias_stmt._module = module_id
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
        tok = export_stmt._tok
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
        tok = export_stmt._tok
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


# compile_source() was removed in v1.0.
# Internal callers were migrated to ModuleLoader in v0.8.0.
# The public re-export was removed from nodus.__init__ in v0.9.0.
# The last test caller (test_import_containment.py) was migrated in v1.0.
# See docs/governance/DEPRECATIONS.md for full history.


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
