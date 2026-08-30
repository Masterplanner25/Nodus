"""Runtime module loader for Nodus."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import NoReturn

try:
    from importlib.metadata import entry_points as _importlib_entry_points
except ImportError:  # Python < 3.9 fallback (not expected but guard anyway)
    _importlib_entry_points = None  # type: ignore[assignment]

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
    ExternDecl,
    FnDef,
    declared_flow_name,
    If,
    Import,
    Index,
    IndexAssign,
    Let,
    ListLit,
    MapLit,
    ModuleInfo,
    Unary,
    Var,
    While,
    For,
)
from nodus.runtime.diagnostics import LangRuntimeError, LangSyntaxError
from nodus.runtime.bytecode_cache import load_cached_bytecode, write_cached_bytecode
from nodus.runtime.dependency_graph import DependencyGraph
from nodus.runtime.module import LiveBinding, ModuleBytecode, NodusModule
from nodus.tooling.project import NODUS_DIRNAME, MODULES_DIRNAME, find_project_root
from nodus.vm.vm import VM
from nodus.vm.types import Closure


@dataclass
class ImportSpec:
    path: str
    names: list[str]
    alias: str | None
    resolved_path: str


@dataclass
class ExportFromSpec:
    path: str
    names: list[str]
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
    parsed: ParsedModule | None
    # Whether the module's top level calls `main()` itself (#453).
    #
    # Must be carried explicitly rather than derived on demand: it is read from the
    # AST, and a module loaded from the bytecode cache has `parsed is None`. Leaving
    # it to be recomputed meant the cached path silently answered "no", so the
    # loader ran `main()` a second time on top of the call the body had already
    # made. `None` means "not yet determined" — the AST is still available.
    has_top_level_main_call: bool | None = None
    # Names the module declares `extern` (#664). Carried for the same reason as
    # the field above: read from the AST, and a cached module has none. `None`
    # means "not yet determined" -- the AST is still available.
    declared_externs: set[str] | None = None


class ModuleLoader:
    def __init__(
        self,
        *,
        project_root: str | None = None,
        host_globals: dict | None = None,
        host_builtins: dict[str, BuiltinInfo] | None = None,
        extra_builtins: set[str] | None = None,
        vm: VM | None = None,
        debugger=None,
        import_trace_fn=None,
        statement_filter=None,
    ) -> None:
        self.project_root = project_root
        self.host_globals = host_globals or {}
        self.host_builtins = host_builtins or {}
        self.extra_builtins = set(extra_builtins or [])
        self._modules: dict[str, NodusModule] = {}
        self._metadata: dict[str, ModuleMetadata] = {}
        self._parsed: dict[str, ParsedModule] = {}
        self._loading: set[str] = set()
        self._loading_stack: list[str] = []
        self._metadata_loading: set[str] = set()
        self._metadata_stack: list[str] = []
        self._import_state: dict = {
            "loaded": set(),
            "loading": set(),
            "exports": {},
            "modules": {},
            "module_ids": {},
            "project_root": project_root,
        }
        self._dependency_graph: DependencyGraph | None = DependencyGraph.load(project_root)
        self._recompiled_modules: set[str] = set()
        self._vm = vm
        self._debugger = debugger
        self._import_trace_fn = import_trace_fn
        # #400: a predicate over top-level statements, applied at parse time.
        # `nodus graph` plans by loading only the flow declarations, so the
        # module's other top-level statements -- imports included -- never
        # compile or run. Statement-level, not expression-level: what survives
        # the filter executes normally. Loaders with a filter never touch the
        # on-disk bytecode cache (guarded in `_source_is_the_file`), because the
        # filtered compile is not the file's program and would poison the entry
        # (#521's cache-write half).
        self._statement_filter = statement_filter

    def resolve_import(self, import_path: str, base_dir: str, tok: Tok | None, module_id: str) -> str:
        if "project_root" not in self._import_state:
            self._import_state["project_root"] = self.project_root
        try:
            resolved = resolve_import_path(
                import_path,
                base_dir,
                self._import_state,
                tok,
                module_id,
            )
        except Exception as _err:
            if self._import_trace_fn is not None:
                self._import_trace_fn(f'[import] Failed "{import_path}" -- {getattr(_err, "message", str(_err))}')
            raise
        if self._import_trace_fn is not None:
            self._import_trace_fn(f'[import] Resolved "{import_path}" -> {resolved}')
        return resolved

    def load_module_from_path(
        self,
        path: str,
        *,
        initial_globals: dict | None = None,
        auto_run_main: bool = False,
    ) -> NodusModule:
        module_id = os.path.abspath(path)
        base_dir = os.path.dirname(module_id)
        return self._load_module(
            module_id,
            base_dir=base_dir,
            source_path=module_id,
            initial_globals=initial_globals,
            auto_run_main=auto_run_main,
        )

    def load_module_from_source(
        self,
        source: str,
        *,
        module_name: str = "<memory>",
        base_dir: str | None = None,
        initial_globals: dict | None = None,
        auto_run_main: bool = False,
    ) -> NodusModule:
        module_id = module_name
        base_dir = base_dir or os.getcwd()
        source_path = None
        if module_name not in {"<memory>"} and os.path.isfile(module_name):
            source_path = os.path.abspath(module_name)
        return self._load_module(
            module_id,
            base_dir=base_dir,
            source=source,
            source_path=source_path,
            initial_globals=initial_globals,
            auto_run_main=auto_run_main,
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
        auto_run_main: bool = False,
    ) -> NodusModule:
        if module_id in self._modules:
            self._refuse_source_mismatch(module_id, source)
            return self._modules[module_id]
        if module_id in self._loading:
            raise self._circular_import_error(module_id, self._loading_stack)

        self._loading.add(module_id)
        self._loading_stack.append(module_id)
        try:
            metadata = self._build_metadata(module_id, base_dir=base_dir, source=source, source_path=source_path)
            bytecode_unit = self._load_or_compile_module_bytecode(metadata, source_path=source_path, source=source)
            module = NodusModule(
                name=os.path.basename(module_id) if module_id not in {"<memory>"} else module_id,
                path=module_id,
                bytecode=bytecode_unit.code,
                functions=bytecode_unit.functions,
                code_locs=bytecode_unit.code_locs,
                bytecode_unit=bytecode_unit,
                globals={},
                exports={},
                host_globals=self.host_globals,
                host_builtins=self.host_builtins,
                initialized=False,
            )
            self._modules[module_id] = module

            import_bindings, dep_modules = self._resolve_import_bindings(metadata)
            module.globals.update(import_bindings)
            if initial_globals:
                module.globals.update(initial_globals)
            should_auto_run_main = auto_run_main and not self._has_top_level_main_call(metadata)
            self._execute_module(
                module,
                source_path=source_path,
                auto_run_main=should_auto_run_main,
                declared_externs=self._declared_externs(metadata),
            )
            module.exports = self._build_exports(metadata, module, dep_modules)
            module.initialized = True
            return module
        finally:
            if self._loading_stack and self._loading_stack[-1] == module_id:
                self._loading_stack.pop()
            elif module_id in self._loading_stack:
                self._loading_stack.remove(module_id)
            self._loading.discard(module_id)

    def _circular_import_error(self, module_id: str, stack: list[str]) -> LangRuntimeError:
        if module_id in stack:
            start = stack.index(module_id)
            cycle = stack[start:] + [module_id]
        else:
            cycle = [module_id, module_id]
        chain = " -> ".join(cycle)
        return LangRuntimeError(
            "import",
            f"Circular import detected: {chain}",
            path=module_id,
            stack=cycle,
        )

    def _source_is_the_file(self, source_path: str | None, source: str | None) -> bool:
        """Is ``source`` what ``source_path`` contains?

        The bytecode cache is keyed on path + mtime (`bytecode_cache.cache_key`),
        which identifies **the file**. It says nothing about a `source` string a
        caller handed us under that file's name -- so without this question, a
        warm entry for `x.nd` substitutes the file's program for the caller's,
        and compiling the caller's source *poisons* that entry for everyone who
        later reads the file. Both directions are #521 at the cache layer, and
        both survive fixing the branch in `embedding.py` on its own.

        Decided by comparing, not by a flag each call site sets. A flag would be
        the wrong question: `tooling/runner.py` legitimately passes the file's own
        text and must keep its cache, so it is not "did the caller supply source"
        but "is it the same source". A call site getting that declaration wrong
        would be silent, and would silently run the wrong program.
        """
        if source_path is None:
            return False
        if self._statement_filter is not None:
            # A filtered parse compiles a subset of the file's program. Neither
            # direction of the cache may participate: a warm entry is not what
            # this loader would compile, and this loader's compile must not be
            # stored as the file's (#400, the #521 cache shape).
            return False
        if source is None:
            # Loaded from the path -- the file *is* the source by construction.
            return True
        try:
            with open(source_path, "r", encoding="utf-8-sig") as handle:
                return handle.read() == source
        except OSError:
            return False

    def _cache_is_authoritative(self, source_path: str | None, source: str | None) -> bool:
        """May the on-disk cache for ``source_path`` stand in for this module?

        Staleness *and* identity: an entry can be fresh with respect to the file
        and still be the wrong program for this call. Both cache-consult sites
        route through here because they used to compute this independently, which
        is exactly how a fix lands on one path and not its sibling.
        """
        if source_path is None or not self._source_is_the_file(source_path, source):
            return False
        return self._can_skip_reprocessing(source_path)

    def _load_or_compile_module_bytecode(
        self,
        metadata: ModuleMetadata,
        *,
        source_path: str | None,
        source: str | None = None,
    ) -> ModuleBytecode:
        can_reuse_cache = self._cache_is_authoritative(source_path, source)
        if can_reuse_cache and source_path is not None:
            cached = load_cached_bytecode(self.project_root, source_path)
            if cached is not None:
                if not cached.module_metadata:
                    cached.module_metadata = self._serialize_module_metadata(metadata)
                    write_cached_bytecode(self.project_root, source_path, cached)
                return cached
        bytecode, functions, code_locs = self._compile_module(metadata)
        bytecode_unit = ModuleBytecode(
            code=bytecode,
            functions=functions,
            constants=list(bytecode.get("constants", [])),
            code_locs=code_locs,
            symbol_table={
                "defs": sorted(metadata.module_info.defs),
                "exports": sorted(metadata.exports),
                "imports": sorted(metadata.import_names),
            },
            module_metadata=self._serialize_module_metadata(metadata),
        )
        # Writing is gated on the same question as reading. A cache entry is
        # keyed by path + mtime, so storing the compile of a *different* source
        # under that key poisons it for everyone who later reads the file --
        # including `run_file`. Guarding only the read leaves that half live.
        if source_path is not None and self._source_is_the_file(source_path, source):
            write_cached_bytecode(self.project_root, source_path, bytecode_unit)
            self._record_dependency_graph(metadata, source_path)
            self._recompiled_modules.add(os.path.abspath(source_path))
        return bytecode_unit

    def _execute_module(
        self,
        module: NodusModule,
        *,
        source_path: str | None,
        auto_run_main: bool = False,
        declared_externs: set[str] | None = None,
    ) -> None:
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
        # #664: accumulated, not replaced. `reset_program` runs once per module
        # and every module executes on this one VM, so an assignment here would
        # leave only the last module's declarations -- and the root module is
        # executed last, after its imports.
        if declared_externs:
            vm.declared_externs.update(declared_externs)
        if self.host_builtins:
            vm.builtins.update(self.host_builtins)
        if self._debugger is not None:
            vm.debugger = self._debugger
            vm.debug = True
        vm.run()
        if auto_run_main and "main" in module.functions:
            vm.run_closure(Closure(module.functions["main"], []), [])

    def _has_top_level_main_call(self, metadata: ModuleMetadata) -> bool:
        """Does the module's own top level call `main()`?

        Used to suppress `auto_run_main`, so a script that calls `main()` itself is
        not run twice.

        The recorded answer wins when present (#453). This used to read only the
        AST and return `False` whenever `parsed is None` — which is exactly the
        state of a module loaded from the bytecode cache. So the guard held on the
        cold path and was bypassed on the warm one: the second and every subsequent
        run of any script ending in `main()` executed it twice, doubling its side
        effects with no error and no output to suggest anything was wrong.

        A correct check that one path went through and a sibling path skipped —
        the shape `CLAUDE.md` documents. The answer now travels with the bytecode
        instead of being recomputed from an AST that is not always there.
        """
        if metadata.has_top_level_main_call is not None:
            return metadata.has_top_level_main_call
        if metadata.parsed is None:
            # Neither a recorded answer nor an AST. Assume the top level *does*
            # call main: running it once too few is a script that appears to do
            # nothing, which is obvious; running it once too many silently repeats
            # every side effect, which is not.
            return True
        result = False
        for stmt in metadata.parsed.ast:
            if not isinstance(stmt, ExprStmt):
                continue
            expr = stmt.expr
            if isinstance(expr, Call) and isinstance(expr.callee, Var) and expr.callee.name == "main":
                result = True
                break
        metadata.has_top_level_main_call = result
        return result

    def _declared_externs(self, metadata: ModuleMetadata) -> set[str]:
        """Names the module declares `extern` (#664).

        Same cold/warm split as `_has_top_level_main_call`: the recorded answer
        wins, the AST is read only when there is one. A cached module has no AST,
        and deriving this from it alone would give the hint on a script's first
        run and drop it on every run after — the bytecode cache as a sibling path,
        which is how #394, #521 and #400 each stayed half-fixed.
        """
        if metadata.declared_externs is not None:
            return metadata.declared_externs
        if metadata.parsed is None:
            return set()
        result = {stmt.name for stmt in metadata.parsed.ast if isinstance(stmt, ExternDecl)}
        metadata.declared_externs = result
        return result

    def _ensure_dependency_graph(self) -> DependencyGraph | None:
        if self.project_root is None:
            return None
        if self._dependency_graph is None:
            self._dependency_graph = DependencyGraph.load(self.project_root)
        return self._dependency_graph

    def _record_dependency_graph(self, metadata: ModuleMetadata, source_path: str) -> None:
        graph = self._ensure_dependency_graph()
        if graph is None:
            return
        graph.update_module(
            source_path,
            [spec.resolved_path for spec in metadata.import_specs] + [spec.resolved_path for spec in metadata.export_from_specs],
            os.stat(source_path).st_mtime_ns,
        )
        graph.save()

    def _can_skip_reprocessing(self, source_path: str) -> bool:
        graph = self._ensure_dependency_graph()
        if graph is None:
            return False
        return not self._is_module_stale(os.path.abspath(source_path), seen=set())

    def _is_module_stale(self, module_path: str, *, seen: set[str]) -> bool:
        normalized = os.path.abspath(module_path)
        if normalized in seen:
            return False
        if normalized in self._recompiled_modules:
            return True
        seen.add(normalized)
        graph = self._ensure_dependency_graph()
        if graph is None:
            return True
        node = graph.get(normalized)
        if node is None or not os.path.isfile(normalized):
            return True
        current_mtime = os.stat(normalized).st_mtime_ns
        if current_mtime != node.last_compiled_mtime:
            return True
        for dependency in node.imported_modules:
            dep_path = os.path.abspath(dependency)
            if dep_path in self._recompiled_modules:
                return True
            if self._is_module_stale(dep_path, seen=seen.copy()):
                return True
        return False

    def _serialize_module_metadata(self, metadata: ModuleMetadata) -> dict[str, object]:
        return {
            "module_id": metadata.module_id,
            # #453: carried through the cache because a cached module is never
            # parsed, and recomputing this from a missing AST answered "no".
            "has_top_level_main_call": bool(self._has_top_level_main_call(metadata)),
            # #664: same reason -- a cached module is never parsed, so an
            # extern-aware error message would appear only on a cold run.
            "declared_externs": sorted(self._declared_externs(metadata)),
            "exports": sorted(metadata.exports),
            "import_names": sorted(metadata.import_names),
            "import_specs": [
                {
                    "path": spec.path,
                    "names": list(spec.names),
                    "alias": spec.alias,
                    "resolved_path": spec.resolved_path,
                }
                for spec in metadata.import_specs
            ],
            "export_from_specs": [
                {
                    "path": spec.path,
                    "names": list(spec.names),
                    "resolved_path": spec.resolved_path,
                }
                for spec in metadata.export_from_specs
            ],
            "module_info": {
                "defs": sorted(metadata.module_info.defs),
                "exports": sorted(metadata.module_info.exports),
                "explicit_exports": metadata.module_info.explicit_exports,
            },
        }

    def _build_metadata_from_cached_bytecode(self, module_id: str, bytecode_unit: ModuleBytecode) -> ModuleMetadata | None:
        payload = bytecode_unit.module_metadata
        if not isinstance(payload, dict):
            return None
        raw_import_specs = payload.get("import_specs", [])
        raw_export_from_specs = payload.get("export_from_specs", [])
        raw_module_info = payload.get("module_info", {})
        if not isinstance(raw_import_specs, list) or not isinstance(raw_export_from_specs, list) or not isinstance(raw_module_info, dict):
            return None
        import_specs: list[ImportSpec] = []
        for item in raw_import_specs:
            if not isinstance(item, dict):
                return None
            import_specs.append(
                ImportSpec(
                    path=str(item.get("path", "")),
                    names=[str(name) for name in item.get("names", []) if isinstance(name, str)],
                    alias=str(item["alias"]) if item.get("alias") is not None else None,
                    resolved_path=str(item.get("resolved_path", "")),
                )
            )
        export_from_specs: list[ExportFromSpec] = []
        for item in raw_export_from_specs:
            if not isinstance(item, dict):
                return None
            export_from_specs.append(
                ExportFromSpec(
                    path=str(item.get("path", "")),
                    names=[str(name) for name in item.get("names", []) if isinstance(name, str)],
                    resolved_path=str(item.get("resolved_path", "")),
                )
            )
        module_info = ModuleInfo(
            path=module_id,
            defs=set(str(name) for name in raw_module_info.get("defs", []) if isinstance(name, str)),
            exports=set(str(name) for name in raw_module_info.get("exports", []) if isinstance(name, str)),
            imports={},
            aliases={},
            explicit_exports=bool(raw_module_info.get("explicit_exports", False)),
            qualified={},
        )
        return ModuleMetadata(
            module_id=module_id,
            exports=set(str(name) for name in payload.get("exports", []) if isinstance(name, str)),
            import_names=set(str(name) for name in payload.get("import_names", []) if isinstance(name, str)),
            import_specs=import_specs,
            export_from_specs=export_from_specs,
            module_info=module_info,
            parsed=None,
            # #453: recovered from the payload. `parsed` is None on this path, so
            # without it the auto-run-main guard has nothing to read and a script
            # ending in `main()` runs it twice on every cached run.
            has_top_level_main_call=(
                bool(payload["has_top_level_main_call"])
                if isinstance(payload.get("has_top_level_main_call"), bool)
                else None
            ),
            # #664: absent in entries written before this field existed, which is
            # only reachable within one nodus-lang version -- the cache refuses
            # entries from another. `None` there falls back to the AST, and there
            # is no AST on this path, so the hint is simply omitted.
            declared_externs=(
                {str(name) for name in payload["declared_externs"] if isinstance(name, str)}
                if isinstance(payload.get("declared_externs"), list)
                else None
            ),
        )

    def _trace_cached_imports(self, metadata: ModuleMetadata) -> None:
        """Report imports recovered from the bytecode cache (#348).

        The resolved paths come from the cached unit rather than the resolver,
        so the line says so: a reader debugging resolution needs to know whether
        a path was resolved on this run or recorded on an earlier one. Nothing is
        re-resolved and nothing is re-parsed — tracing must not change what a run
        does, only what it reports.
        """
        if self._import_trace_fn is None:
            return
        for spec in metadata.import_specs:
            self._import_trace_fn(
                f'[import] Resolved (from bytecode cache) "{spec.path}" -> {spec.resolved_path}'
            )
        for ef_spec in metadata.export_from_specs:
            self._import_trace_fn(
                f'[import] Resolved (from bytecode cache) "{ef_spec.path}" -> {ef_spec.resolved_path}'
            )

    def _build_metadata(
        self,
        module_id: str,
        *,
        base_dir: str,
        source: str | None = None,
        source_path: str | None = None,
    ) -> ModuleMetadata:
        if module_id in self._metadata:
            self._refuse_source_mismatch(module_id, source)
            if self._import_trace_fn is not None:
                self._import_trace_fn(f'[import] Cache hit "{module_id}"')
            return self._metadata[module_id]
        if module_id in self._metadata_loading:
            raise self._circular_import_error(module_id, self._metadata_stack)

        self._metadata_loading.add(module_id)
        self._metadata_stack.append(module_id)
        try:
            if "project_root" not in self._import_state or self._import_state["project_root"] is None:
                ensure_project_root(self._import_state, base_dir, source_path)
                self.project_root = self._import_state.get("project_root")
            self._ensure_dependency_graph()

            if source_path is not None and self._cache_is_authoritative(source_path, source):
                cached = load_cached_bytecode(self.project_root, source_path)
                if cached is not None:
                    cached_metadata = self._build_metadata_from_cached_bytecode(module_id, cached)
                    if cached_metadata is not None:
                        self._metadata[module_id] = cached_metadata
                        # #348: this return skips the loop below, and
                        # `resolve_import` is the only place the import trace is
                        # emitted — so `--trace-imports` printed nothing at all
                        # once the on-disk cache was warm, which is every run
                        # after the first. Replay what the cached unit recorded.
                        self._trace_cached_imports(cached_metadata)
                        return cached_metadata

            parsed = self._parse_module(module_id, base_dir=base_dir, source=source, source_path=source_path)
            import_specs: list[ImportSpec] = []
            export_from_specs: list[ExportFromSpec] = []
            import_names: set[str] = set()

            for stmt in parsed.imports:
                tok = getattr(stmt, "_tok", None)
                resolved = self.resolve_import(stmt.path, parsed.base_dir, tok, parsed.module_id)
                import_specs.append(ImportSpec(path=stmt.path, names=list(stmt.names or []), alias=stmt.alias, resolved_path=resolved))

            for ef_stmt in parsed.export_from:
                tok = getattr(ef_stmt, "_tok", None)
                resolved = self.resolve_import(ef_stmt.path, parsed.base_dir, tok, parsed.module_id)
                export_from_specs.append(ExportFromSpec(path=ef_stmt.path, names=list(ef_stmt.names or []), resolved_path=resolved))

            for stmt, spec in zip(parsed.imports, import_specs):
                dep_meta = self._build_metadata(spec.resolved_path, base_dir=os.path.dirname(spec.resolved_path), source_path=spec.resolved_path)
                if spec.names:
                    # #680: a named import of a builtin name cannot work, and
                    # used to fail silently. `_op_call` resolves `self.builtins`
                    # before locals and globals, so the builtin wins and the
                    # binding this import created is never reached -- the program
                    # then fails with an arity error naming neither the import
                    # nor the shadowing.
                    #
                    # The builtin has to keep winning: `register_function`
                    # refuses to override one precisely so a host can rely on a
                    # builtin name meaning the builtin (a security boundary, see
                    # `tests/test_downstream_contracts.py`). Letting an import
                    # take the name would be the same hole through a second door.
                    #
                    # So this is refused rather than reordered. It cannot break a
                    # working program: the import already did nothing.
                    shadowed = [name for name in spec.names if name in BUILTIN_NAMES]
                    if shadowed:
                        tok = getattr(stmt, "_tok", None)
                        names = ", ".join(f"'{name}'" for name in shadowed)
                        # A usable identifier for the suggestion. The naive form
                        # (last path segment) yields `shadowmod.nd` for a
                        # relative import, which is not a legal alias -- a fix
                        # suggestion that does not parse is worse than none.
                        alias = os.path.basename(spec.path).split(":")[-1]
                        if alias.endswith(".nd"):
                            alias = alias[:-3]
                        alias = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in alias)
                        if not alias or alias[0].isdigit():
                            alias = "mod"
                        raise LangRuntimeError(
                            "import",
                            f"Import failed: {names} is a built-in function name and "
                            f"cannot be imported -- the builtin would win and this "
                            f"binding would never be reached. Import the module "
                            f'instead: `import "{spec.path}" as {alias}` and '
                            f'call `{alias}.{shadowed[0]}(...)`.',
                            line=tok.line if tok is not None else None,
                            col=tok.col if tok is not None else None,
                            path=spec.resolved_path,
                        )
                    missing = [name for name in spec.names if name not in dep_meta.exports]
                    if missing:
                        tok = getattr(stmt, "_tok", None)
                        line = tok.line if tok is not None else None
                        col = tok.col if tok is not None else None
                        raise LangRuntimeError(
                            "import",
                            f"Import failed: {spec.resolved_path} does not export {', '.join(missing)}",
                            line=line,
                            col=col,
                            path=spec.resolved_path,
                        )
                    import_names.update(spec.names)
                elif spec.alias:
                    import_names.add(spec.alias)
                else:
                    import_names.update(dep_meta.exports)

            for ef_stmt, ef_spec in zip(parsed.export_from, export_from_specs):
                dep_meta = self._build_metadata(ef_spec.resolved_path, base_dir=os.path.dirname(ef_spec.resolved_path), source_path=ef_spec.resolved_path)
                missing = [name for name in ef_spec.names if name not in dep_meta.exports]
                if missing:
                    tok = getattr(ef_stmt, "_tok", None)
                    line = tok.line if tok is not None else None
                    col = tok.col if tok is not None else None
                    raise LangRuntimeError(
                        "import",
                        f"Re-export failed: {ef_spec.resolved_path} does not export {', '.join(missing)}",
                        line=line,
                        col=col,
                        path=ef_spec.resolved_path,
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
        finally:
            if self._metadata_stack and self._metadata_stack[-1] == module_id:
                self._metadata_stack.pop()
            elif module_id in self._metadata_stack:
                self._metadata_stack.remove(module_id)
            self._metadata_loading.discard(module_id)

    def _refuse_source_mismatch(self, module_id: str, source: str | None) -> None:
        """Refuse to hand back a memoised module for *different* source (#457).

        The loader memoises by module id, and `"<memory>"` is the default id —
        so a loader reused for several snippets returned the first one's
        bytecode for all of them, silently, and the symptom surfaced somewhere
        else entirely. Three sites consult these memos (`_build_metadata`,
        `_parse_module`, `_load_module`); each calls this rather than deciding
        alone, per the sibling-path rule. `source=None` (load-from-path) is
        exempt: the file is the source by construction.
        """
        if source is None:
            return
        cached = self._parsed.get(module_id)
        if cached is not None and cached.source != source:
            raise LangRuntimeError(
                "compile",
                f"module '{module_id}' was already compiled from different "
                f"source by this loader; a loader memoises by module name. "
                f"Use a fresh ModuleLoader per snippet, or give each snippet "
                f"its own module_name.",
                path=module_id,
            )

    def _parse_module(
        self,
        module_id: str,
        *,
        base_dir: str,
        source: str | None = None,
        source_path: str | None = None,
    ) -> ParsedModule:
        if module_id in self._parsed:
            self._refuse_source_mismatch(module_id, source)
            return self._parsed[module_id]
        if source is None:
            with open(module_id, "r", encoding="utf-8-sig") as handle:
                source = handle.read()
        # #342: stamp the module being parsed onto syntax errors. Without it the
        # error carries no path, and the reporter falls back to the path the CLI
        # was given — so a syntax error inside an imported module was reported
        # against the *entry* file, at the module's line and column. That names a
        # file which does not contain the error, at a position that looks
        # plausible in it.
        try:
            toks = tokenize(source)
            ast = Parser(toks).parse()
        except LangSyntaxError as err:
            if getattr(err, "path", None) is None:
                err.path = module_id
            raise
        if self._statement_filter is not None:
            ast = [stmt for stmt in ast if self._statement_filter(stmt)]
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
        if metadata.parsed is None:
            raise LangRuntimeError("compile", f"Module metadata for {metadata.module_id} is not available for compilation", path=metadata.module_id)
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
            if spec.names:
                for name in spec.names:
                    bindings[name] = module.export_binding(name)
            elif spec.alias:
                bindings[spec.alias] = module
            else:
                for name in module.exports:
                    bindings[name] = module.export_binding(name)
                inferred = spec.path.replace("std:", "").split("/")[-1].split(":")[-1]
                if inferred and self._vm is not None and hasattr(self._vm, "_bare_import_hints"):
                    self._vm._bare_import_hints[inferred] = spec.path
        return bindings, modules

    def _build_exports(
        self,
        metadata: ModuleMetadata,
        module: NodusModule,
        dep_modules: dict[str, NodusModule],
    ) -> dict[str, object]:
        exports: dict[str, object] = {}
        for name in metadata.exports:
            if name in module.globals or name in metadata.module_info.defs:
                exports[name] = LiveBinding(module, name)
                continue
            resolved = None
            for spec in metadata.export_from_specs:
                if name in spec.names:
                    dep = dep_modules.get(spec.resolved_path)
                    if dep is None:
                        dep = self._load_module(spec.resolved_path, base_dir=os.path.dirname(spec.resolved_path), source_path=spec.resolved_path)
                    resolved = dep.export_binding(name)
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


def resolve_import_path(
    import_path: str,
    base_dir: str,
    import_state: dict,
    tok: Tok | None,
    module_id: str,
) -> str:
    project_root = os.path.abspath(import_state.get("project_root") or base_dir)
    modules_dir = os.path.join(project_root, NODUS_DIRNAME, MODULES_DIRNAME)

    # Special-case imports that look like stdlib modules but are actually built-ins.
    _BUILTIN_NOT_MODULES: dict[str, str] = {
        "std:channel": (
            "channel(), send(), recv(), and close() are built-in functions — "
            "no import needed; use them directly without importing"
        ),
    }
    if import_path in _BUILTIN_NOT_MODULES:
        import_error(_BUILTIN_NOT_MODULES[import_path], tok, module_id)

    if ":" in import_path and not import_path.startswith("std:"):
        package_name, package_path = import_path.split(":", 1)
        if not package_name or not package_path:
            import_error("Invalid package import: use package:module", tok, module_id)
        if package_name.startswith(".") or package_name.startswith(("/", "\\")):
            import_error("Invalid package import: package name is invalid", tok, module_id)
        package_path_norm = package_path.replace("/", os.sep).replace("\\", os.sep)
        package_base = os.path.normpath(os.path.join(modules_dir, package_name, package_path_norm))
        package_root = os.path.normpath(os.path.join(modules_dir, package_name))
        if not package_base.startswith(package_root):
            import_error("Invalid package import: path escapes dependency directory", tok, module_id)
        # Try .nodus/modules/ first (local package manager wins over installed).
        resolved = try_resolve_with_extensions(package_base)
        if resolved is not None:
            return resolved
        # Fallback: pip-installed package via nodus.nd entry-point group.
        ep_root = _resolve_installed_package(package_name)
        if ep_root is not None:
            ep_base = os.path.normpath(os.path.join(ep_root, package_path_norm))
            ep_root_norm = os.path.normpath(ep_root)
            if ep_base.startswith(ep_root_norm):  # guard: no path traversal outside ep_root
                resolved = try_resolve_with_extensions(ep_base)
                if resolved is not None:
                    return resolved
        # Build error listing everything tried.
        _pkg_tried: list[str] = []
        for _sfx in (".nd", ".tl"):
            _pkg_tried.append(os.path.abspath(package_base + _sfx))
        _pkg_tried.append(os.path.abspath(os.path.join(package_base, "index.nd")))
        if ep_root is not None:
            _ep_base = os.path.normpath(os.path.join(ep_root, package_path_norm))
            for _sfx in (".nd", ".tl"):
                _pkg_tried.append(os.path.abspath(_ep_base + _sfx))
            _pkg_tried.append(os.path.abspath(os.path.join(_ep_base, "index.nd")))
        else:
            _pkg_tried.append(f"<no nodus.nd entry-point for '{package_name}'>")
        import_error(
            f"Import not found: {import_path} (tried {', '.join(_pkg_tried)})",
            tok, module_id,
        )

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
                import_error(f"Invalid import: path {import_path!r} escapes the project root.", tok, module_id)
        except ValueError:
            import_error(f"Invalid import: path {import_path!r} escapes the project root.", tok, module_id)
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

    std_base = _resolve_std_base(import_path, tok, module_id)
    resolved = try_resolve_with_extensions(std_base)
    if resolved is not None:
        return resolved

    # Fourth lookup: pip-installed packages via nodus.nd entry-point group.
    # Fires only after project-root, .nodus/modules/, and stdlib all miss.
    # Local always wins; installed is last resort before ImportError.
    _ep_root = _resolve_installed_package(import_path)
    if _ep_root is not None:
        _ep_base = os.path.normpath(_ep_root)
        resolved = try_resolve_with_extensions(_ep_base)
        if resolved is not None:
            return resolved

    # Build a comprehensive error listing every path that was attempted.
    _all_tried: list[str] = []
    # 1. Project-root attempts
    _base_noext = base
    if _base_noext.endswith(".nd") or _base_noext.endswith(".tl"):
        _base_noext = _base_noext[:-3]
    for _sfx in (".nd", ".tl"):
        _all_tried.append(os.path.abspath(_base_noext + _sfx))
    _all_tried.append(os.path.abspath(os.path.join(_base_noext, "index.nd")))
    _all_tried.append(os.path.abspath(os.path.join(_base_noext, "index.tl")))
    # 2. .nodus/modules/ attempts (was previously omitted from error output)
    _modules_noext = os.path.normpath(os.path.join(modules_dir, import_path))
    if _modules_noext.endswith(".nd") or _modules_noext.endswith(".tl"):
        _modules_noext = _modules_noext[:-3]
    for _sfx in (".nd", ".tl"):
        _all_tried.append(os.path.abspath(_modules_noext + _sfx))
    _all_tried.append(os.path.abspath(os.path.join(_modules_noext, "index.nd")))
    _all_tried.append(os.path.abspath(os.path.join(_modules_noext, "index.tl")))
    # 3. stdlib attempts
    try:
        _std_b = _resolve_std_base(import_path, tok, module_id)
        if _std_b.endswith(".nd") or _std_b.endswith(".tl"):
            _std_b = _std_b[:-3]
        for _sfx in (".nd", ".tl"):
            _all_tried.append(os.path.abspath(_std_b + _sfx))
    except Exception:
        pass
    # 4. Entry-point attempts
    if _ep_root is not None:
        _ep_noext = os.path.normpath(_ep_root)
        for _sfx in (".nd", ".tl"):
            _all_tried.append(os.path.abspath(_ep_noext + _sfx))
        _all_tried.append(os.path.abspath(os.path.join(_ep_noext, "index.nd")))
        _all_tried.append(os.path.abspath(os.path.join(_ep_noext, "index.tl")))
    else:
        _all_tried.append(f"<no nodus.nd entry-point for '{import_path}'>")
    _line = tok.line if tok is not None else None
    _col = tok.col if tok is not None else None
    raise LangRuntimeError(
        "import",
        f"Import not found: {import_path!r} (tried {', '.join(_all_tried)})",
        line=_line,
        col=_col,
        path=module_id,
    )


def import_error(message: str, tok: Tok | None, module_id: str) -> NoReturn:
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
        flow_name = declared_flow_name(s)
        if flow_name is not None:
            defs.add(flow_name)
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


def _resolve_std_base(import_path: str, tok: Tok | None, module_id: str) -> str:
    if import_path.startswith(("/", "\\")):
        import_error("Invalid std import: std modules cannot start with '/'", tok, module_id)
    std_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "stdlib"))
    name = import_path.replace("/", os.sep).replace("\\", os.sep)
    base = os.path.normpath(os.path.join(std_dir, name))
    if not base.startswith(os.path.normpath(std_dir)):
        import_error("Invalid std import: path escapes std directory", tok, module_id)
    return base


def _resolve_installed_package(name: str) -> str | None:
    """Look up a pip-installed Nodus package via the ``nodus.nd`` entry-point group.

    Third-party packages (e.g. ``nodus-mcp``) declare themselves importable by
    registering an entry point in the ``nodus.nd`` group::

        [project.entry-points."nodus.nd"]
        nodus-mcp = "nodus_mcp.nd:get_nd_root"

    The entry-point value MUST be a ``module:callable`` reference.  The callable
    is invoked with no arguments and MUST return the absolute path to the
    directory that contains the package's ``.nd`` source files (its *nd root*).

    Convention: the nd root directory contains an ``index.nd`` file (the module's
    top-level export, resolved by ``import "nodus-mcp"``) and optionally
    sub-module files (``client.nd`` → ``import "nodus-mcp:client"``).

    The function form is required (not a static string) because the installed
    location is only known at runtime; a static path cannot be computed at
    package-author time.

    Returns the nd root directory path on success, or ``None`` if:
    - no entry point is registered for the name,
    - the callable raises, or
    - the returned path does not exist.

    Callers are responsible for the subsequent ``try_resolve_with_extensions``
    call and for any path-traversal validation in the colon-form case.
    """
    try:
        if _importlib_entry_points is None:
            return None
        import importlib
        importlib.invalidate_caches()
        eps = _importlib_entry_points(group="nodus.nd", name=name)
        for ep in eps:
            fn = ep.load()
            if not callable(fn):
                continue
            path = fn()
            if isinstance(path, str) and os.path.isdir(path):
                return path
    except Exception:
        pass
    return None
