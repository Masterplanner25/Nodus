"""Workspace diagnostics collection for tooling and editor integrations."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from nodus.builtins.nodus_builtins import BUILTIN_NAMES
from nodus.compiler.compiler import Compiler
from nodus.frontend.ast.ast_nodes import (
    Assign,
    Attr,
    Bin,
    Block,
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
    MapLit,
    ModuleInfo,
    Nil,
    Print,
    RecordLiteral,
    Return,
    Str,
    Throw,
    TryCatch,
    Unary,
    Var,
    While,
    WorkflowDef,
    WorkflowStateDecl,
    Yield,
)
from nodus.frontend.lexer import Tok, tokenize
from nodus.frontend.parser import Parser
from nodus.runtime.dependency_graph import DependencyGraph
from nodus.runtime.diagnostics import (
    ERROR_SEVERITY,
    WARNING_SEVERITY,
    DiagnosticRelatedInformation,
    RuntimeDiagnostic,
    diagnostic_from_error,
)
from nodus.runtime.errors import coerce_error
from nodus.tooling.loader import collect_module_info, ensure_project_root, resolve_import_path, set_module_on_tree


@dataclass
class ParsedDiagnosticModule:
    path: str
    source: str
    ast: list | None = None
    module_info: ModuleInfo | None = None
    imports: list[Import] = field(default_factory=list)
    resolved_imports: dict[int, str] = field(default_factory=dict)


@dataclass
class WorkspaceDiagnosticsResult:
    diagnostics_by_file: dict[str, list[RuntimeDiagnostic]]
    dependency_graph: DependencyGraph | None = None


@dataclass
class _Binding:
    name: str
    kind: str
    line: int | None
    column: int | None
    used: bool = False
    source_file: str | None = None


class _SemanticAnalyzer:
    def __init__(
        self,
        *,
        module: ParsedDiagnosticModule,
        module_cache: dict[str, ParsedDiagnosticModule],
        diagnostics_by_file: dict[str, list[RuntimeDiagnostic]],
        builtin_names: set[str],
    ) -> None:
        self.module = module
        self.module_cache = module_cache
        self.diagnostics_by_file = diagnostics_by_file
        self.builtin_names = builtin_names
        self.module_aliases: dict[str, str] = {}
        self.scopes: list[dict[str, _Binding]] = []

    def analyze(self) -> None:
        if self.module.ast is None:
            return
        self._push_scope()
        self._predeclare(self.module.ast)
        for stmt in self.module.ast:
            self._walk_stmt(stmt)
        self._pop_scope()

    def _diag(
        self,
        message: str,
        *,
        severity: str,
        tok: Tok | None = None,
        file: str | None = None,
        related_information: list[DiagnosticRelatedInformation] | None = None,
    ) -> None:
        target = os.path.abspath(file or self.module.path)
        self.diagnostics_by_file.setdefault(target, []).append(
            RuntimeDiagnostic(
                message=message,
                severity=severity,
                source="nodus",
                file=target,
                line=getattr(tok, "line", None),
                column=getattr(tok, "col", None),
                end_column=(getattr(tok, "col", None) or 0) + 1 if tok is not None else None,
                related_information=related_information or [],
            )
        )

    def _push_scope(self) -> None:
        self.scopes.append({})

    def _pop_scope(self) -> None:
        scope = self.scopes.pop()
        for binding in scope.values():
            if binding.kind in {"variable", "param", "catch"} and not binding.used and not binding.name.startswith("_"):
                self.diagnostics_by_file.setdefault(self.module.path, []).append(
                    RuntimeDiagnostic(
                        message=f"Unused {binding.kind}: {binding.name}",
                        severity=WARNING_SEVERITY,
                        source="nodus",
                        file=self.module.path,
                        line=binding.line,
                        column=binding.column,
                        end_column=(binding.column + len(binding.name)) if binding.column is not None else None,
                    )
                )

    def _bind(self, name: str, *, kind: str, tok: Tok | None = None, source_file: str | None = None) -> None:
        for scope in reversed(self.scopes[:-1]):
            if name in scope and not name.startswith("_"):
                self._diag(f"Shadowed variable: {name}", severity=WARNING_SEVERITY, tok=tok)
                break
        self.scopes[-1][name] = _Binding(
            name=name,
            kind=kind,
            line=getattr(tok, "line", None),
            column=getattr(tok, "col", None),
            source_file=source_file or self.module.path,
        )

    def _resolve(self, name: str) -> _Binding | None:
        for scope in reversed(self.scopes):
            binding = scope.get(name)
            if binding is not None:
                return binding
        return None

    def _mark_used(self, name: str) -> None:
        binding = self._resolve(name)
        if binding is not None:
            binding.used = True

    def _predeclare(self, stmts: list) -> None:
        for stmt in stmts:
            tok = getattr(stmt, "_tok", None)
            if isinstance(stmt, Let):
                self._bind(stmt.name, kind="variable", tok=tok)
            elif isinstance(stmt, FnDef):
                self._bind(stmt.name, kind="function", tok=tok)
            elif isinstance(stmt, (WorkflowDef, GoalDef)):
                self._bind(stmt.name, kind="variable", tok=tok)
        for stmt in stmts:
            if not isinstance(stmt, Import):
                continue
            resolved = self.module.resolved_imports.get(id(stmt))
            if resolved is None:
                continue
            imported = self.module_cache.get(resolved)
            if stmt.alias is not None:
                self._bind(stmt.alias, kind="module", tok=getattr(stmt, "_tok", None), source_file=resolved)
                self.module_aliases[stmt.alias] = resolved
            elif stmt.names:
                exports = imported.module_info.exports if imported and imported.module_info is not None else set()
                for name in stmt.names:
                    if name in exports:
                        self._bind(name, kind="import", tok=getattr(stmt, "_tok", None), source_file=resolved)
            elif imported and imported.module_info is not None:
                for name in imported.module_info.exports:
                    self._bind(name, kind="import", tok=getattr(stmt, "_tok", None), source_file=resolved)

    def _walk_stmt(self, stmt) -> bool:
        if isinstance(stmt, Comment):
            return False
        if isinstance(stmt, Import):
            return False
        if isinstance(stmt, Let):
            self._walk_expr(stmt.expr)
            return False
        if isinstance(stmt, FnDef):
            self._push_scope()
            for param in stmt.params:
                self._bind(param.name, kind="param", tok=getattr(param, "_tok", None))
            terminated = self._walk_stmt(stmt.body)
            self._pop_scope()
            return terminated
        if isinstance(stmt, Block):
            self._push_scope()
            terminated = False
            for inner in stmt.stmts:
                if terminated:
                    self._diag("Unreachable code", severity=WARNING_SEVERITY, tok=getattr(inner, "_tok", None))
                    continue
                terminated = self._walk_stmt(inner)
            self._pop_scope()
            return terminated
        if isinstance(stmt, ExprStmt):
            self._walk_expr(stmt.expr)
            return False
        if isinstance(stmt, Print):
            self._walk_expr(stmt.expr)
            return False
        if isinstance(stmt, If):
            self._walk_expr(stmt.cond)
            then_terminated = self._walk_stmt(stmt.then_branch)
            else_terminated = self._walk_stmt(stmt.else_branch) if stmt.else_branch is not None else False
            return then_terminated and else_terminated
        if isinstance(stmt, While):
            self._walk_expr(stmt.cond)
            self._walk_stmt(stmt.body)
            return False
        if isinstance(stmt, For):
            self._push_scope()
            if stmt.init is not None:
                self._walk_stmt(stmt.init)
            if stmt.cond is not None:
                self._walk_expr(stmt.cond)
            if stmt.inc is not None:
                self._walk_expr(stmt.inc)
            self._walk_stmt(stmt.body)
            self._pop_scope()
            return False
        if isinstance(stmt, ForEach):
            self._walk_expr(stmt.iterable)
            self._push_scope()
            self._bind(stmt.name, kind="variable", tok=getattr(stmt, "_tok", None))
            self._walk_stmt(stmt.body)
            self._pop_scope()
            return False
        if isinstance(stmt, Return):
            if stmt.expr is not None:
                self._walk_expr(stmt.expr)
            return True
        if isinstance(stmt, Yield):
            if stmt.expr is not None:
                self._walk_expr(stmt.expr)
            return True
        if isinstance(stmt, WorkflowStateDecl):
            self._walk_expr(stmt.value)
            return False
        if isinstance(stmt, TryCatch):
            self._walk_stmt(stmt.try_block)
            self._push_scope()
            self._bind(stmt.catch_var, kind="catch", tok=getattr(stmt, "_tok", None))
            self._walk_stmt(stmt.catch_block)
            self._pop_scope()
            if stmt.finally_block is not None:
                self._walk_stmt(stmt.finally_block)
            return False
        if isinstance(stmt, Throw):
            self._walk_expr(stmt.expr)
            return True
        return False

    def _walk_expr(self, expr) -> None:
        if expr is None or isinstance(expr, (Str, Nil)):
            return
        if isinstance(expr, Var):
            binding = self._resolve(expr.name)
            if binding is not None:
                binding.used = True
                return
            if expr.name in self.builtin_names:
                return
            self._diag(f"Undefined variable: {expr.name}", severity=ERROR_SEVERITY, tok=getattr(expr, "_tok", None))
            return
        if isinstance(expr, Assign):
            if self._resolve(expr.name) is None and expr.name not in self.builtin_names:
                self._diag(f"Undefined variable: {expr.name}", severity=ERROR_SEVERITY, tok=getattr(expr, "_tok", None))
            else:
                self._mark_used(expr.name)
            self._walk_expr(expr.expr)
            return
        if isinstance(expr, Unary):
            self._walk_expr(expr.expr)
            return
        if isinstance(expr, Bin):
            self._walk_expr(expr.a)
            self._walk_expr(expr.b)
            return
        if isinstance(expr, Call):
            self._walk_expr(expr.callee)
            for arg in expr.args:
                self._walk_expr(arg)
            return
        if isinstance(expr, Attr):
            self._walk_expr(expr.obj)
            if isinstance(expr.obj, Var) and expr.obj.name in self.module_aliases:
                module_path = self.module_aliases[expr.obj.name]
                imported = self.module_cache.get(module_path)
                exports = imported.module_info.exports if imported and imported.module_info is not None else set()
                if expr.name not in exports:
                    related = [
                        DiagnosticRelatedInformation(
                            message=f"Imported module resolved here: {module_path}",
                            file=module_path,
                            line=1,
                            column=1,
                        )
                    ]
                    self._diag(
                        f"Module '{expr.obj.name}' has no member '{expr.name}'",
                        severity=ERROR_SEVERITY,
                        tok=getattr(expr, "_tok", None),
                        related_information=related,
                    )
            return
        if isinstance(expr, Index):
            self._walk_expr(expr.seq)
            self._walk_expr(expr.index)
            return
        if isinstance(expr, IndexAssign):
            self._walk_expr(expr.seq)
            self._walk_expr(expr.index)
            self._walk_expr(expr.value)
            return
        if isinstance(expr, MapLit):
            for key, value in expr.items:
                self._walk_expr(key)
                self._walk_expr(value)
            return
        if isinstance(expr, RecordLiteral):
            for _key, value in expr.fields:
                self._walk_expr(value)
            return
        if hasattr(expr, "items") and isinstance(getattr(expr, "items"), list):
            for item in expr.items:
                self._walk_expr(item)
            return
        if isinstance(expr, FnExpr):
            self._push_scope()
            for param in expr.params:
                self._bind(param.name, kind="param", tok=getattr(param, "_tok", None))
            self._walk_stmt(expr.body)
            self._pop_scope()


class WorkspaceDiagnosticEngine:
    def __init__(self, *, project_root: str | None = None) -> None:
        self.project_root = os.path.abspath(project_root) if project_root else None
        self.builtin_names = set(BUILTIN_NAMES)

    def analyze(
        self,
        entry_path: str,
        *,
        source: str | None = None,
        overlays: dict[str, str] | None = None,
        affected_paths: set[str] | None = None,
        dependency_graph: DependencyGraph | None = None,
    ) -> WorkspaceDiagnosticsResult:
        normalized_entry = os.path.abspath(entry_path)
        overlay_map = {os.path.abspath(path): text for path, text in (overlays or {}).items()}
        diagnostics_by_file: dict[str, list[RuntimeDiagnostic]] = {}
        module_cache: dict[str, ParsedDiagnosticModule] = {}
        import_state = {"loaded": set(), "loading": set(), "exports": {}, "modules": {}, "module_ids": {}, "project_root": self.project_root}
        ensure_project_root(import_state, os.path.dirname(normalized_entry), normalized_entry)
        graph = dependency_graph or DependencyGraph.load(import_state.get("project_root"))

        self._load_module(
            normalized_entry,
            source=source if source is not None else overlay_map.get(normalized_entry),
            overlays=overlay_map,
            import_state=import_state,
            module_cache=module_cache,
            diagnostics_by_file=diagnostics_by_file,
            dependency_graph=graph,
        )

        compile_targets = set(module_cache)
        if affected_paths is not None:
            compile_targets &= {os.path.abspath(path) for path in affected_paths}

        module_defs_index: dict[str, set[str]] = {}
        for path, module in module_cache.items():
            if module.module_info is None:
                continue
            for name in module.module_info.defs:
                module_defs_index.setdefault(name, set()).add(path)

        for path in sorted(compile_targets):
            module = module_cache[path]
            if module.ast is None or module.module_info is None:
                continue
            self._compile_module(module, module_cache, module_defs_index, diagnostics_by_file)
            _SemanticAnalyzer(
                module=module,
                module_cache=module_cache,
                diagnostics_by_file=diagnostics_by_file,
                builtin_names=self.builtin_names,
            ).analyze()

        for path in module_cache:
            diagnostics_by_file.setdefault(path, [])
        deduped = {path: _dedupe(diags) for path, diags in diagnostics_by_file.items()}
        return WorkspaceDiagnosticsResult(diagnostics_by_file=deduped, dependency_graph=graph)

    def _read_source(self, path: str, overlays: dict[str, str]) -> str:
        if path in overlays:
            return overlays[path]
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()

    def _load_module(
        self,
        path: str,
        *,
        source: str | None,
        overlays: dict[str, str],
        import_state: dict,
        module_cache: dict[str, ParsedDiagnosticModule],
        diagnostics_by_file: dict[str, list[RuntimeDiagnostic]],
        dependency_graph: DependencyGraph | None,
    ) -> ParsedDiagnosticModule:
        normalized = os.path.abspath(path)
        cached = module_cache.get(normalized)
        if cached is not None:
            return cached
        text = source if source is not None else self._read_source(normalized, overlays)
        module = ParsedDiagnosticModule(path=normalized, source=text)
        module_cache[normalized] = module
        try:
            tokens = tokenize(text)
            ast = Parser(tokens).parse()
            set_module_on_tree(ast, normalized)
            module_info = collect_module_info(ast, normalized, "")
            module.ast = ast
            module.module_info = module_info
        except Exception as err:
            diagnostics_by_file.setdefault(normalized, []).append(
                diagnostic_from_error(coerce_error(err, stage="compile", filename=normalized), file=normalized)
            )
            return module

        imported_paths: list[str] = []
        for stmt in module.ast:
            if not isinstance(stmt, Import):
                continue
            module.imports.append(stmt)
            tok = getattr(stmt, "_tok", None)
            try:
                resolved = resolve_import_path(stmt.path, os.path.dirname(normalized), import_state, tok, normalized)
                module.resolved_imports[id(stmt)] = resolved
                imported_paths.append(resolved)
            except Exception as err:
                diagnostics_by_file.setdefault(normalized, []).append(
                    diagnostic_from_error(coerce_error(err, stage="compile", filename=normalized), file=normalized)
                )
                continue

            imported_module = self._load_module(
                resolved,
                source=overlays.get(os.path.abspath(resolved)),
                overlays=overlays,
                import_state=import_state,
                module_cache=module_cache,
                diagnostics_by_file=diagnostics_by_file,
                dependency_graph=dependency_graph,
            )
            if stmt.names and imported_module.module_info is not None:
                missing = [name for name in stmt.names if name not in imported_module.module_info.exports]
                if missing:
                    related = [DiagnosticRelatedInformation(message=f"Imported module: {resolved}", file=resolved, line=1, column=1)]
                    diagnostics_by_file.setdefault(normalized, []).append(
                        RuntimeDiagnostic(
                            message=f"Import failed: {resolved} does not export {', '.join(missing)}",
                            severity=ERROR_SEVERITY,
                            source="nodus",
                            file=normalized,
                            line=getattr(tok, "line", None),
                            column=getattr(tok, "col", None),
                            end_column=(getattr(tok, "col", None) or 0) + 1 if tok is not None else None,
                            related_information=related,
                        )
                    )
        if dependency_graph is not None and normalized not in {"<memory>"}:
            try:
                mtime = os.stat(normalized).st_mtime_ns if os.path.isfile(normalized) else 0
                dependency_graph.update_module(normalized, imported_paths, mtime)
            except OSError:
                pass
        return module

    def _compile_module(
        self,
        module: ParsedDiagnosticModule,
        module_cache: dict[str, ParsedDiagnosticModule],
        module_defs_index: dict[str, set[str]],
        diagnostics_by_file: dict[str, list[RuntimeDiagnostic]],
    ) -> None:
        module_info = module.module_info
        if module_info is None or module.ast is None:
            return
        module_info.imports = {}
        module_info.aliases = {}
        module_info.qualified = {name: name for name in module_info.defs}
        for stmt in module.imports:
            resolved = module.resolved_imports.get(id(stmt))
            imported = module_cache.get(resolved or "")
            exports = imported.module_info.exports if imported and imported.module_info is not None else set()
            if stmt.alias is not None:
                module_info.aliases[stmt.alias] = {name: name for name in exports}
            elif stmt.names:
                for name in stmt.names:
                    if name in exports:
                        module_info.imports[name] = name
            else:
                for name in exports:
                    module_info.imports[name] = name
        try:
            compiler = Compiler(
                module_infos={module.path: module_info},
                module_defs_index=module_defs_index,
                builtin_names=self.builtin_names,
            )
            compiler.compile_program(module.ast)
        except Exception as err:
            payload = coerce_error(err, stage="compile", filename=module.path)
            diagnostics_by_file.setdefault(module.path, []).append(diagnostic_from_error(payload, file=module.path))


def _dedupe(diagnostics: list[RuntimeDiagnostic]) -> list[RuntimeDiagnostic]:
    seen: set[tuple] = set()
    out: list[RuntimeDiagnostic] = []
    for diag in diagnostics:
        key = (
            diag.file,
            diag.line,
            diag.column,
            diag.severity,
            diag.message,
            tuple((item.file, item.line, item.column, item.message) for item in diag.related_information),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(diag)
    out.sort(key=lambda item: ((item.line or 0), (item.column or 0), item.severity != ERROR_SEVERITY, item.message))
    return out
