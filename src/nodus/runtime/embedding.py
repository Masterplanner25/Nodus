"""Embedding API for hosting the Nodus runtime inside Python apps."""

from __future__ import annotations

import inspect
import os
import threading
from typing import Any

from nodus.builtins.nodus_builtins import BUILTIN_NAMES, BuiltinInfo
from nodus.result import Result, normalize_filename
from nodus.runtime.errors import coerce_error, legacy_error_dict
from nodus.runtime.diagnostics import LangRuntimeError, LangSyntaxError, HostFunctionError
from nodus.support.config import EXECUTION_TIMEOUT_MS, MAX_STDOUT_CHARS, MAX_STEPS
from nodus.runtime.module_loader import ModuleLoader
from nodus.tooling.sandbox import capture_output, configure_vm_limits
from nodus.vm.vm import VM, Record, Closure


class ToolRegistry:
    """Python-side view of the Nodus tool registry for a ``NodusRuntime`` instance.

    Provides register/unregister/invoke/lookup/list_tools/has methods that
    mirror the Nodus ``std:tool`` API.  Python-registered tools persist across
    ``run_source()`` calls; Nodus-registered tools are ephemeral (per VM).
    """

    def __init__(self, runtime: "NodusRuntime") -> None:
        self._runtime = runtime
        self._lock = threading.RLock()

    def register(self, metadata: dict[str, Any]) -> None:
        """Register a Python callable as a tool visible to Nodus scripts.

        Parameters
        ----------
        metadata:
            Dict with required keys ``name``, ``handler``, ``description``
            and optional keys ``schema``, ``version``, ``tags``,
            ``deprecated``, ``metadata``.  ``handler`` must be a Python
            callable.

        Raises
        ------
        ValueError:
            If required fields are missing, the name is already registered,
            or the schema is invalid.
        """
        from nodus.builtins.tool_module import _normalize_schema, _validate_tool_name

        name = metadata.get("name", "")
        name_err = _validate_tool_name(name)
        if name_err:
            raise ValueError(f"tool.register: {name_err}")
        handler = metadata.get("handler")
        if handler is None:
            raise ValueError("tool.register: 'handler' is required")
        if not callable(handler):
            raise ValueError("tool.register: 'handler' must be a callable")
        desc = metadata.get("description")
        if not isinstance(desc, str) or not desc:
            raise ValueError("tool.register: 'description' must be a non-empty string")
        schema_raw = metadata.get("schema") or {}
        schema, schema_err = _normalize_schema(schema_raw)
        if schema_err:
            raise ValueError(f"tool.register: invalid schema: {schema_err}")
        tags_raw = metadata.get("tags")
        tags = list(tags_raw) if isinstance(tags_raw, list) else []
        meta_raw = metadata.get("metadata") or {}
        entry = {
            "name": name,
            "handler": handler,
            "description": desc,
            "schema": schema,
            "version": metadata.get("version") or "1.0.0",
            "tags": tags,
            "deprecated": bool(metadata.get("deprecated", False)),
            "metadata": meta_raw,
        }
        with self._lock:
            if name in self._runtime._python_registered_tools:
                raise ValueError(f"Tool '{name}' is already registered")
            self._runtime._python_registered_tools[name] = entry

    def unregister(self, name: str) -> dict:
        """Remove a Python-registered tool and return its metadata.

        Raises
        ------
        KeyError:
            If the tool is not registered.
        """
        with self._lock:
            entry = self._runtime._python_registered_tools.pop(name, None)
        if entry is None:
            raise KeyError(f"Tool '{name}' is not registered")
        return {k: v for k, v in entry.items() if not k.startswith("_")}

    def invoke(self, name: str, args: dict | None = None) -> object:
        """Invoke a registered tool and return the result as a Python value.

        Prefers the live VM registry (includes Nodus-ephemeral tools) when
        a VM is active; falls back to Python-registered tools otherwise.

        Parameters
        ----------
        name:
            Tool name to invoke.
        args:
            Python dict of arguments (translated to Nodus values before
            the call; result is translated back).

        Raises
        ------
        KeyError:
            If the tool is not registered.
        RuntimeError:
            If a Nodus-closure handler is requested but no VM is active.
        """
        vm = self._runtime.last_vm
        if vm is not None:
            with vm._tool_registry_lock:
                entry = vm.tool_registry.get(name)
            if entry is None:
                raise KeyError(f"Tool '{name}' is not registered")
            handler = entry["handler"]
            if isinstance(handler, Closure):
                # Convert Python dict → Nodus Record so handler can use dot access
                raw = args or {}
                nodus_args = Record({str(k): self._runtime._to_runtime_value(v) for k, v in raw.items()})
                nodus_result = vm.run_closure(handler, [nodus_args])
                return self._runtime._to_host_value(nodus_result)
            if callable(handler):
                return handler(args or {})
            raise RuntimeError(f"Tool '{name}': handler is not callable")
        # No active VM — use Python-registered tools only
        entry = self._runtime._python_registered_tools.get(name)
        if entry is None:
            raise KeyError(f"Tool '{name}' is not registered")
        handler = entry["handler"]
        if not callable(handler):
            raise RuntimeError(f"Tool '{name}': handler is not callable")
        return handler(args or {})

    def lookup(self, name: str) -> dict | None:
        """Return a tool's metadata dict, or ``None`` if not registered."""
        vm = self._runtime.last_vm
        if vm is not None:
            with vm._tool_registry_lock:
                entry = vm.tool_registry.get(name)
            if entry is not None:
                return {k: v for k, v in entry.items() if not k.startswith("_")}
        entry = self._runtime._python_registered_tools.get(name)
        if entry is None:
            return None
        return {k: v for k, v in entry.items() if not k.startswith("_")}

    def list_tools(self) -> list:
        """Return a list of all registered tool metadata dicts.

        Merges persistent Python-registered tools with any Nodus-registered
        tools from the most recent VM run.
        """
        result: dict[str, dict] = {}
        for name, entry in self._runtime._python_registered_tools.items():
            result[name] = {k: v for k, v in entry.items() if not k.startswith("_")}
        vm = self._runtime.last_vm
        if vm is not None:
            with vm._tool_registry_lock:
                vm_entries = dict(vm.tool_registry)
            for name, entry in vm_entries.items():
                result[name] = {k: v for k, v in entry.items() if not k.startswith("_")}
        return list(result.values())

    def has(self, name: str) -> bool:
        """Return ``True`` if a tool with this name is registered."""
        if name in self._runtime._python_registered_tools:
            return True
        vm = self._runtime.last_vm
        if vm is not None:
            with vm._tool_registry_lock:
                return name in vm.tool_registry
        return False


class NodusRuntime:
    """Embedded Nodus runtime for hosting inside Python applications.

    ``NodusRuntime`` is the recommended public API for executing Nodus scripts
    from Python.  It manages the full compile-and-run pipeline (lexer -> parser ->
    module loader -> compiler -> optimizer -> VM) and exposes host integration hooks
    (registered functions, sandbox constraints, execution limits).

    Typical usage::

        runtime = NodusRuntime(max_steps=100_000, allowed_paths=["/data"])
        runtime.register_function("log", my_logger)
        result = runtime.run_source('log("hello")')

    A single ``NodusRuntime`` instance can be reused across multiple script
    executions; each call to ``run_source`` / ``run_file`` creates a fresh VM and
    module loader so state does not leak between runs.  ``last_vm`` is overwritten
    on each call and is available for post-execution inspection.
    """

    def __init__(
        self,
        *,
        max_steps: int | None = MAX_STEPS,
        timeout_ms: int | None = EXECUTION_TIMEOUT_MS,
        max_stdout_chars: int | None = MAX_STDOUT_CHARS,
        project_root: str | None = None,
        allowed_paths: list[str] | None = None,
        allow_input: bool = False,
        max_frames: int | None = None,
    ) -> None:
        """Create a new embedded Nodus runtime.

        Parameters
        ----------
        max_steps:
            Maximum total VM instructions executed per ``run_source`` / ``run_file``
            call.  Raises ``RuntimeLimitExceeded`` when exceeded.  ``None`` means
            unlimited.  Defaults to ``MAX_STEPS`` from ``support/config.py``.
        timeout_ms:
            Wall-clock timeout in milliseconds per execution.  Raises
            ``RuntimeLimitExceeded`` when exceeded.  ``None`` means no timeout.
            Defaults to ``EXECUTION_TIMEOUT_MS`` (200 ms) from ``support/config.py``.

            .. warning::
                The 200 ms default is designed for short, sandboxed script
                executions (the same budget as ``nodus run``).  **Long-lived
                sessions — MCP/A2A servers, workflow hosts, event loops,
                anything that runs coroutines with cumulative sleep > 200 ms —
                must set** ``timeout_ms=None`` **explicitly.**  With the
                default, a coroutine sleeping 4 × 100 ms is killed after the
                200 ms wall-clock budget is consumed, even though it did no
                excessive compute.  See EMBED-001 (#97).
        max_stdout_chars:
            Maximum number of stdout characters captured per execution.  Output
            beyond this limit is silently truncated.  ``None`` means unlimited.
            Defaults to ``MAX_STDOUT_CHARS`` from ``support/config.py``.
        project_root:
            Absolute path to the project root directory.  Used by the module loader
            to resolve non-relative imports.  ``None`` disables multi-module imports.
        allowed_paths:
            List of directory paths the script is allowed to access via filesystem
            builtins (``read_file``, ``write_file``, ``append_file``, ``mkdir``,
            ``list_dir``, ``exists``).  Paths outside this list raise a sandbox error.
            ``None`` means unrestricted filesystem access.
        allow_input:
            If ``False`` (default), the ``input()`` builtin raises a sandbox error.
            Set to ``True`` only when running in interactive/REPL-like contexts where
            stdin is available.
        max_frames:
            Maximum call stack depth.  Raises a sandbox error on overflow.  ``None``
            means the VM default (``MAX_STACK_DEPTH``).
        """
        self.max_steps = max_steps
        self.timeout_ms = timeout_ms
        self.max_stdout_chars = max_stdout_chars
        self.project_root = project_root
        self.allowed_paths = allowed_paths
        self.allow_input = allow_input
        self.max_frames = max_frames
        self._host_functions: dict[str, BuiltinInfo] = {}
        self._python_registered_tools: dict[str, dict] = {}
        self.last_vm: VM | None = None
        self._tool_registry: ToolRegistry = ToolRegistry(self)

    def register_function(self, name: str, fn, *, arity: int | tuple[int, ...] | None = None) -> None:
        """Register a Python callable as a host function available to Nodus scripts.

        The function will be available in every subsequent ``run_source`` /
        ``run_file`` call on this runtime instance.

        Parameters
        ----------
        name:
            The name Nodus scripts use to call the function.  Must be a non-empty
            string and must not shadow any built-in Nodus function name.
        fn:
            The Python callable to invoke.  Arguments are automatically converted
            from Nodus runtime values to Python equivalents before the call, and
            the return value is converted back (see ``_to_host_value`` /
            ``_to_runtime_value``).
        arity:
            Number of positional arguments the function accepts.  Can be an ``int``
            for a fixed arity or a ``tuple[int, ...]`` for variadic arities
            (e.g., ``(1, 2)`` means 1 or 2 arguments).  When ``None``, arity is
            inferred from the callable's signature via ``inspect.signature``.
            Functions with ``*args``, ``**kwargs``, keyword-only, or defaulted
            parameters require an explicit ``arity`` value.

        Raises
        ------
        ValueError:
            If ``name`` is empty, shadows a built-in, or ``arity`` is invalid.
        ValueError:
            If ``arity`` is ``None`` and the signature cannot be inspected
            (e.g., the function uses ``*args``).

        Example::

            runtime.register_function("fetch", my_fetch_fn, arity=1)
        """
        if not isinstance(name, str) or not name:
            raise ValueError("Host function name must be a non-empty string")
        if name in BUILTIN_NAMES:
            raise ValueError(f"Cannot override built-in function: {name}")
        resolved_arity = self._resolve_arity(fn, arity)
        self._host_functions[name] = BuiltinInfo(name, resolved_arity, fn)

    @property
    def tool_registry(self) -> ToolRegistry:
        """The tool registry for this runtime.

        Use this to register Python callables as Nodus-callable tools, invoke
        Nodus-registered tools from Python, or enumerate registered tools.
        Python-registered tools persist across ``run_source()`` calls.
        """
        return self._tool_registry

    def set_effect_store(self, store) -> None:
        """Inject a custom EffectStore for EXACTLY_ONCE idempotency.

        When set, all calls to ``effect_resolve``, ``effect_pending``, and
        ``effect_complete`` from .nd code will use this store instead of the
        default per-VM ``InMemoryEffectStore``.  Must be called before
        ``run_source`` / ``run_file`` to affect that execution.
        """
        self._pending_effect_store = store
        if self.last_vm is not None:
            self.last_vm.effect_store = store

    def set_trace_id(self, trace_id: str) -> None:
        """Inject a distributed trace ID into the next (and current) VM execution.

        When set, ``trace_id`` is included in every ``RuntimeEvent`` emitted
        during the execution and is readable from .nd code via
        ``import "std:identity"`` → ``identity.trace_id()``.

        Must be called before ``run_source`` / ``run_file`` to affect that
        execution.  If a VM is already active (``last_vm`` is set), the ID
        is applied to it immediately.
        """
        self._pending_trace_id: str | None = trace_id
        if self.last_vm is not None:
            self.last_vm.trace_id = trace_id

    def reset(self) -> None:
        """Clear the reference to the last VM instance.

        ``last_vm`` holds a reference to the VM created by the most recent
        ``run_source`` / ``run_file`` call.  Calling ``reset()`` releases that
        reference, allowing the VM (and its associated bytecode, stack, and globals)
        to be garbage-collected.
        """
        self.last_vm = None

    def run_file(
        self,
        path: str,
        *,
        max_steps: int | None = None,
        timeout_ms: int | None = None,
        max_stdout_chars: int | None = None,
        optimize: bool = True,
        debugger=None,
        max_frames: int | None = None,
        initial_globals: dict | None = None,
        host_globals: dict | None = None,
    ) -> dict:
        """Read a ``.nd`` file from disk and execute it.

        Equivalent to ``run_source(open(path).read(), filename=path, ...)``.

        Parameters
        ----------
        path:
            Absolute or relative path to the ``.nd`` source file.
        max_steps:
            Per-call override for ``self.max_steps``.  ``None`` uses the runtime default.
        timeout_ms:
            Per-call override for ``self.timeout_ms``.  ``None`` uses the runtime default.
        max_stdout_chars:
            Per-call override for ``self.max_stdout_chars``.  ``None`` uses the runtime default.
        optimize:
            Whether to run the bytecode optimizer before execution.  Defaults to ``True``.
        debugger:
            Optional DAP-compatible debugger object attached to the VM for this run.
        max_frames:
            Per-call override for ``self.max_frames``.  ``None`` uses the runtime default.

        Returns
        -------
        dict
            Same shape as ``run_source``: ``{"ok": bool, "stdout": str,
            "stderr": str, "stage": "execute", "filename": path, ...}``.

        Raises
        ------
        OSError:
            If the file cannot be opened.
        LangSyntaxError / LangRuntimeError:
            Propagated from the compiler or VM on parse/runtime failure.
        """
        with open(path, "r", encoding="utf-8-sig") as handle:
            source = handle.read()
        return self.run_source(
            source,
            filename=path,
            max_steps=max_steps,
            timeout_ms=timeout_ms,
            max_stdout_chars=max_stdout_chars,
            optimize=optimize,
            debugger=debugger,
            max_frames=max_frames,
            initial_globals=initial_globals,
            host_globals=host_globals,
        )

    def run_source(
        self,
        source: str,
        *,
        filename: str | None = None,
        max_steps: int | None = None,
        timeout_ms: int | None = None,
        max_stdout_chars: int | None = None,
        optimize: bool = True,
        import_state: dict | None = None,
        debugger=None,
        max_frames: int | None = None,
        initial_globals: dict | None = None,
        host_globals: dict | None = None,
    ) -> dict:
        """Compile and execute a Nodus source string.

        This is the primary entry point for embedded execution.  The method runs
        the complete pipeline: lexer -> parser -> import resolution (ModuleLoader) ->
        bytecode compiler -> optimizer -> VM execution.

        Parameters
        ----------
        source:
            Nodus source code as a string.
        filename:
            Optional label used in error messages and the module loader's import
            resolution.  If ``filename`` points to an existing file on disk, the
            module loader reads it directly (allowing relative imports).  Pass
            ``None`` or ``"<memory>"`` for in-memory snippets.
        max_steps:
            Per-call override for ``self.max_steps``.
        timeout_ms:
            Per-call override for ``self.timeout_ms``.
        max_stdout_chars:
            Per-call override for ``self.max_stdout_chars``.
        optimize:
            Whether to run the bytecode optimizer.  Defaults to ``True``.
        import_state:
            Pre-populated module loader state dict (used by the REPL and test
            harnesses to share already-loaded modules across calls).  ``None``
            creates a fresh import state.
        debugger:
            Optional DAP-compatible debugger attached to the VM.
        max_frames:
            Per-call override for ``self.max_frames``.

        Returns
        -------
        dict
            Result dict from ``Result.to_dict()``:
            - ``"ok"`` (bool): ``True`` on success.
            - ``"stdout"`` (str): captured standard output.
            - ``"stderr"`` (str): captured standard error.
            - ``"stage"`` (str): always ``"execute"``.
            - ``"filename"`` (str | None): normalized filename.
            On failure the dict also contains ``"error"`` with structured error info.

        Raises
        ------
        LangSyntaxError:
            On parse or compile error (re-raised via ``coerce_error``).
        LangRuntimeError:
            On uncaught runtime error (re-raised via ``coerce_error``).
        """
        normalized = normalize_filename(filename)
        if import_state is None and self.project_root is not None:
            import_state = {
                "loaded": set(),
                "loading": set(),
                "exports": {},
                "modules": {},
                "module_ids": {},
                "project_root": self.project_root,
            }
        elif import_state is not None and self.project_root is not None:
            import_state["project_root"] = self.project_root

        vm = VM(
            [],
            {},
            code_locs=[],
            source_path=filename,
            allowed_paths=self.allowed_paths,
            module_globals=initial_globals,
            host_globals=host_globals,
        )
        if not self.allow_input:
            vm.input_fn = self._blocked_input
        if debugger is not None:
            vm.debugger = debugger
            vm.debug = True
        if self._python_registered_tools:
            vm.tool_registry.update(self._python_registered_tools)
        pending_trace = getattr(self, "_pending_trace_id", None)
        if pending_trace is not None:
            vm.trace_id = pending_trace
        pending_effect_store = getattr(self, "_pending_effect_store", None)
        if pending_effect_store is not None:
            vm.effect_store = pending_effect_store
        self.last_vm = vm
        host_builtins = {
            name: BuiltinInfo(
                info.name,
                info.arity,
                lambda *args, _fn=info.fn, _vm=vm: self._invoke_host_function(_vm, _fn, *args),
            )
            for name, info in self._host_functions.items()
        }

        resolved_steps = self.max_steps if max_steps is None else max_steps
        resolved_timeout = self.timeout_ms if timeout_ms is None else timeout_ms
        resolved_stdout = self.max_stdout_chars if max_stdout_chars is None else max_stdout_chars
        configure_vm_limits(vm, max_steps=resolved_steps, timeout_ms=resolved_timeout)
        resolved_frames = self.max_frames if max_frames is None else max_frames
        vm.max_frames = resolved_frames

        with capture_output(max_stdout_chars=resolved_stdout) as (stdout, stderr):
            try:
                loader = ModuleLoader(
                    project_root=self.project_root,
                    vm=vm,
                    host_builtins=host_builtins,
                    extra_builtins=set(self._host_functions.keys()),
                    debugger=debugger,
                    host_globals=host_globals,
                )
                if filename and os.path.isfile(filename):
                    loader.load_module_from_path(filename, auto_run_main=True, initial_globals=initial_globals)
                else:
                    loader.load_module_from_source(source, module_name=filename or "<memory>", auto_run_main=True, initial_globals=initial_globals)
            except HostFunctionError as wrapped:
                raise wrapped.cause
            except Exception as err:
                stage = "parse" if isinstance(err, (LangSyntaxError, SyntaxError)) else "execute"
                structured = coerce_error(err, stage=stage, filename=normalized)
                return Result.failure(
                    stage=stage,
                    filename=normalized,
                    stdout=stdout.getvalue(),
                    stderr=stderr.getvalue(),
                    errors=[structured.to_dict()],
                    error=legacy_error_dict(err, filename=normalized),
                ).to_dict()

        return Result.success(
            stage="execute",
            filename=normalized,
            stdout=stdout.getvalue(),
            stderr=stderr.getvalue(),
        ).to_dict()

    def _install_host_functions(self, vm: VM) -> None:
        for name, info in self._host_functions.items():
            vm.builtins[name] = BuiltinInfo(
                info.name,
                info.arity,
                lambda *args, _fn=info.fn, _vm=vm: self._invoke_host_function(_vm, _fn, *args),
            )

    def _resolve_arity(self, fn, arity: int | tuple[int, ...] | None) -> int | tuple[int, ...]:
        if arity is not None:
            if isinstance(arity, int):
                if arity < 0:
                    raise ValueError("Arity must be non-negative")
                return arity
            if isinstance(arity, tuple) and all(isinstance(value, int) and value >= 0 for value in arity):
                return arity
            raise ValueError("Arity must be an int or tuple of ints")

        sig = inspect.signature(fn)
        params = list(sig.parameters.values())
        for param in params:
            if param.kind in {inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD}:
                raise ValueError("Host function uses *args/**kwargs. Provide explicit arity.")
            if param.kind == inspect.Parameter.KEYWORD_ONLY:
                raise ValueError("Host function has keyword-only args. Provide explicit arity.")
            if param.default is not inspect.Parameter.empty:
                raise ValueError("Host function has default args. Provide explicit arity.")
        return len(params)

    def _invoke_host_function(self, vm: VM, fn, *args):
        host_args = [self._to_host_value(arg) for arg in args]
        try:
            result = fn(*host_args)
        except (LangRuntimeError, LangSyntaxError):
            raise
        except Exception as exc:
            raise HostFunctionError(exc) from exc
        return self._to_runtime_value(result)

    def _blocked_input(self, _prompt: str):
        raise LangRuntimeError("sandbox", "input() is not available in embedded mode")

    def _to_host_value(self, value):
        if value is None or isinstance(value, (bool, str)):
            return value
        if isinstance(value, float):
            if value.is_integer():
                return int(value)
            return value
        if isinstance(value, int):
            return value
        if isinstance(value, list):
            return [self._to_host_value(item) for item in value]
        if isinstance(value, dict):
            return {str(key): self._to_host_value(item) for key, item in value.items()}
        if isinstance(value, Record):
            return {str(key): self._to_host_value(item) for key, item in value.fields.items()}
        return value

    def _to_runtime_value(self, value):
        if value is None or isinstance(value, (bool, str)):
            return value
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        if isinstance(value, float):
            return value
        if isinstance(value, list):
            return [self._to_runtime_value(item) for item in value]
        if isinstance(value, dict):
            return {str(key): self._to_runtime_value(item) for key, item in value.items()}
        if isinstance(value, Record):
            return {str(key): self._to_runtime_value(item) for key, item in value.fields.items()}
        return value
