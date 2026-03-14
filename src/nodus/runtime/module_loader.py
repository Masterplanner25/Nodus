"""Runtime module loader for Nodus."""

from __future__ import annotations

import os
from dataclasses import dataclass

from nodus.builtins.nodus_builtins import BUILTIN_NAMES, BuiltinInfo
from nodus.compiler.compiler import Compiler, wrap_bytecode
from nodus.frontend.lexer import Tok, tokenize
from nodus.frontend.parser import Parser
from nodus.frontend.ast.ast_nodes import (
    Assign,
    Attr,
    Bin,
    Block,
    Call,
    Comment,
    ExportFrom,
    ExportList,
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
    ModuleInfo,
    WorkflowDef,
    Unary,
    While,
    For,
)
from nodus.runtime.diagnostics import LangRuntimeError, LangSyntaxError
from nodus.runtime.module import NodusModule
from nodus.tooling.project import find_project_root
from nodus.vm.vm import VM


@dataclass
class ImportSpec:
    stmt: Import
    resolved_path: str


@dataclass
class ExportFromSpec:
    stmt: ExportFrom
    resolved_path: str


@dataclass
class ParsedModule:
    module_id: str
    source: str
    ast: list
    module_info: ModuleInfo
    imports: list[Import]
    export_from: list[ExportFrom]
    base_dir: str


@dataclass
class ModuleMetadata:
    module_id: str
    exports: set[str]
    import_names: set[str]
    import_specs: list[ImportSpec]
    export_from_specs: list[ExportFromSpec]
    module_info: ModuleInfo
    parsed: ParsedModule


class ModuleLoader:
    def __init__(
        self,
        *,
        project_root: str | None = None,
        host_globals: dict | None = None,
        host_builtins: dict[str, BuiltinInfo] | None = None,
        extra_builtins: set[str] | None = None,
        vm: VM | None = None,
    ) -> None:
        self.project_root = project_root
        self.host_globals = host_globals or {}
        self.host_builtins = host_builtins or {}
        self.extra_builtins = set(extra_builtins or [])
        self._modules: dict[str, NodusModule] = {}
        self._metadata: dict[str, ModuleMetadata] = {}
        self._parsed: dict[str, ParsedModule] = {}
        self._loading: set[str] = set()
        self._import_state: dict = {
            "loaded": set(),
            "loading": set(),
            "exports": {},
            "modules": {},
            "module_ids": {},
            "project_root": project_root,
        }
        self._vm = vm

    def resolve_import(self, import_path: str, base_dir: str, tok: Tok | None, module_id: str) -> str:
        if "project_root" not in self._import_state:
            self._import_state["project_root"] = self.project_root
        return resolve_import_path(import_path, base_dir, self._import_state, tok, module_id)

    def load_module_from_path(self, path: str, *, initial_globals: dict | None = None) -> NodusModule:
        module_id = os.path.abspath(path)
        base_dir = os.path.dirname(module_id)
        return self._load_module(module_id, base_dir=base_dir, source_path=module_id, initial_globals=initial_globals)

    def load_module_from_source(
        self,
        source: str,
        *,
        module_name: str = "<memory>",
        base_dir: str | None = None,
        initial_globals: dict | None = None,
    ) -> NodusModule:
        module_id = module_name
        base_dir = base_dir or os.getcwd()
        return self._load_module(
            module_id,
            base_dir=base_dir,
            source=source,
            source_path=None,
            initial_globals=initial_globals,
        )

    def compile_only(self, source: str, *, module_name: str, base_dir: str | None = None) -> tuple[dict, dict, list]:
        base_dir = base_dir or os.getcwd()
        module_id = module_name
        metadata = self._build_metadata(module_id, base_dir=base_dir, source=source)
        bytecode, functions, code_locs = self._compile_module(metadata)
        return bytecode, functions, code_locs

    def _load_module(
        self,
        module_id: str,
        *,
        base_dir: str,
        source: str | None = None,
        source_path: str | None = None,
        initial_globals: dict | None = None,
    ) -> NodusModule:
        if module_id in self._modules:
            return self._modules[module_id]
        if module_id in self._loading:
            raise LangRuntimeError("import", f"Cyclic import detected: {module_id}", path=module_id)

        self._loading.add(module_id)
        try:
            metadata = self._build_metadata(module_id, base_dir=base_dir, source=source, source_path=source_path)
            bytecode, functions, code_locs = self._compile_module(metadata)
            module = NodusModule(
                name=module_id,
                bytecode=bytecode,
                functions=functions,
                code_locs=code_locs,
                globals={},
                exports={},
                initialized=False,
            )
            self._modules[module_id] = module

            import_bindings, dep_modules = self._resolve_import_bindings(metadata)
            module.globals.update(import_bindings)
            if initial_globals:
                module.globals.update(initial_globals)
            self._execute_module(module, source_path=source_path)
            module.exports = self._build_exports(metadata, module, dep_modules)
            module.initialized = True
            return module
        finally:
            self._loading.discard(module_id)

    def _execute_module(self, module: NodusModule, *, source_path: str | None) -> None:
        vm = self._vm
        if vm is None:
            vm = VM(
                module.bytecode,
                module.functions,
                code_locs=module.code_locs,
                module_globals=module.globals,
                host_globals=self.host_globals,
                source_path=source_path,
            )
            self._vm = vm
        else:
            vm.reset_program(
                module.bytecode,
                module.functions,
                code_locs=module.code_locs,
                source_path=source_path,
                module_globals=module.globals,
                host_globals=self.host_globals,
            )
        if self.host_builtins:
            vm.builtins.update(self.host_builtins)
        vm.run()

    def _build_metadata(
        self,
        module_id: str,
        *,
        base_dir: str,
        source: str | None = None,
        source_path: str | None = None,
    ) -> ModuleMetadata:
        if module_id in self._metadata:
            return self._metadata[module_id]

        if "project_root" not in self._import_state or self._import_state["project_root"] is None:
            ensure_project_root(self._import_state, base_dir, source_path)
            self.project_root = self._import_state.get("project_root")

        parsed = self._parse_module(module_id, base_dir=base_dir, source=source, source_path=source_path)
        import_specs: list[ImportSpec] = []
        export_from_specs: list[ExportFromSpec] = []
        import_names: set[str] = set()

        for stmt in parsed.imports:
            tok = getattr(stmt, "_tok", None)
            resolved = self.resolve_import(stmt.path, parsed.base_dir, tok, parsed.module_id)
            import_specs.append(ImportSpec(stmt=stmt, resolved_path=resolved))

        for stmt in parsed.export_from:
            tok = getattr(stmt, "_tok", None)
            resolved = self.resolve_import(stmt.path, parsed.base_dir, tok, parsed.module_id)
            export_from_specs.append(ExportFromSpec(stmt=stmt, resolved_path=resolved))

        for spec in import_specs:
            dep_meta = self._build_metadata(spec.resolved_path, base_dir=os.path.dirname(spec.resolved_path), source_path=spec.resolved_path)
            if spec.stmt.names:
                missing = [name for name in spec.stmt.names if name not in dep_meta.exports]
                if missing:
                    tok = getattr(spec.stmt, "_tok", None)
                    line = tok.line if tok is not None else None
                    col = tok.col if tok is not None else None
                    raise LangRuntimeError(
                        "import",
                        f"Import failed: {spec.resolved_path} does not export {', '.join(missing)}",
                        line=line,
                        col=col,
                        path=spec.resolved_path,
                    )
                import_names.update(spec.stmt.names)
            elif spec.stmt.alias:
                import_names.add(spec.stmt.alias)
            else:
                import_names.update(dep_meta.exports)

        for spec in export_from_specs:
            dep_meta = self._build_metadata(spec.resolved_path, base_dir=os.path.dirname(spec.resolved_path), source_path=spec.resolved_path)
            missing = [name for name in spec.stmt.names if name not in dep_meta.exports]
            if missing:
                tok = getattr(spec.stmt, "_tok", None)
                line = tok.line if tok is not None else None
                col = tok.col if tok is not None else None
                raise LangRuntimeError(
                    "import",
                    f"Re-export failed: {spec.resolved_path} does not export {', '.join(missing)}",
                    line=line,
                    col=col,
                    path=spec.resolved_path,
                )

        metadata = ModuleMetadata(
            module_id=module_id,
            exports=set(parsed.module_info.exports),
            import_names=import_names,
            import_specs=import_specs,
            export_from_specs=export_from_specs,
            module_info=parsed.module_info,
            parsed=parsed,
        )
        self._metadata[module_id] = metadata
        return metadata

    def _parse_module(
        self,
        module_id: str,
        *,
        base_dir: str,
        source: str | None = None,
        source_path: str | None = None,
    ) -> ParsedModule:
        if module_id in self._parsed:
            return self._parsed[module_id]
        if source is None:
            with open(module_id, "r", encoding="utf-8") as handle:
                source = handle.read()
        toks = tokenize(source)
        ast = Parser(toks).parse()
        set_module_on_tree(ast, module_id)
        module_info = collect_module_info(ast, module_id, "")
        imports = [stmt for stmt in ast if isinstance(stmt, Import)]
        export_from = [stmt for stmt in ast if isinstance(stmt, ExportFrom)]
        parsed = ParsedModule(
            module_id=module_id,
            source=source,
            ast=ast,
            module_info=module_info,
            imports=imports,
            export_from=export_from,
            base_dir=base_dir,
        )
        self._parsed[module_id] = parsed
        return parsed

    def _compile_module(self, metadata: ModuleMetadata) -> tuple[dict, dict, list]:
        module_info = metadata.module_info
        module_info.imports = {name: name for name in metadata.import_names}
        module_info.qualified = {name: name for name in module_info.defs}
        builtin_names = set(BUILTIN_NAMES)
        if self.extra_builtins:
            builtin_names.update(self.extra_builtins)
        compiler = Compiler(module_infos={metadata.module_id: module_info}, module_defs_index={}, builtin_names=builtin_names)
        code, functions, code_locs = compiler.compile_program(metadata.parsed.ast)
        bytecode = wrap_bytecode(
            code,
            module_name=metadata.module_id,
            exports=sorted(metadata.exports),
        )
        return bytecode, functions, code_locs

    def _resolve_import_bindings(self, metadata: ModuleMetadata) -> tuple[dict[str, object], dict[str, NodusModule]]:
        bindings: dict[str, object] = {}
        modules: dict[str, NodusModule] = {}
        for spec in metadata.import_specs:
            module = self._load_module(spec.resolved_path, base_dir=os.path.dirname(spec.resolved_path), source_path=spec.resolved_path)
            modules[spec.resolved_path] = module
            if spec.stmt.names:
                for name in spec.stmt.names:
                    bindings[name] = module.exports[name]
            elif spec.stmt.alias:
                bindings[spec.stmt.alias] = module.to_record()
            else:
                for name, value in module.exports.items():
                    bindings[name] = value
        return bindings, modules

    def _build_exports(
        self,
        metadata: ModuleMetadata,
        module: NodusModule,
        dep_modules: dict[str, NodusModule],
    ) -> dict[str, object]:
        exports: dict[str, object] = {}
        for name in metadata.exports:
            if name in module.globals:
                exports[name] = module.globals[name]
                continue
            resolved = None
            for spec in metadata.export_from_specs:
                if name in spec.stmt.names:
                    dep = dep_modules.get(spec.resolved_path)
                    if dep is None:
                        dep = self._load_module(spec.resolved_path, base_dir=os.path.dirname(spec.resolved_path), source_path=spec.resolved_path)
                    resolved = dep.exports.get(name)
                    break
            if resolved is not None:
                exports[name] = resolved
        return exports


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
    if ":" in import_path and not import_path.startswith("std:"):
        package_name, package_path = import_path.split(":", 1)
        if not package_name or not package_path:
            import_error("Invalid package import: use package:module", tok, module_id)
        if package_name.startswith(".") or package_name.startswith(("/", "\\")):
            import_error("Invalid package import: package name is invalid", tok, module_id)
        project_root = import_state.get("project_root") or base_dir
        deps_dir = os.path.join(project_root, "deps")
        package_base = os.path.normpath(os.path.join(deps_dir, package_name, package_path.replace("/", os.sep).replace("\\", os.sep)))
        package_root = os.path.normpath(os.path.join(deps_dir, package_name))
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
        project_root = import_state.get("project_root") or base_dir
        base = os.path.join(project_root, import_path)

    base = os.path.normpath(base)
    resolved = try_resolve_with_extensions(base)
    if resolved is not None:
        return resolved

    deps_base = os.path.normpath(os.path.join(import_state.get("project_root") or base_dir, "deps", import_path))
    resolved = try_resolve_with_extensions(deps_base)
    if resolved is not None:
        return resolved

    return resolve_with_extensions(base, import_path, tok, module_id)


def import_error(message: str, tok: Tok | None, module_id: str):
    line = tok.line if tok is not None else None
    col = tok.col if tok is not None else None
    raise LangRuntimeError("import", message, line=line, col=col, path=module_id)


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
