"""Embedding API for hosting the Nodus runtime inside Python apps."""

from __future__ import annotations

import inspect
import os

from nodus.builtins.nodus_builtins import BUILTIN_NAMES, BuiltinInfo
from nodus.result import Result, normalize_filename
from nodus.runtime.errors import coerce_error
from nodus.runtime.diagnostics import LangRuntimeError
from nodus.support.config import EXECUTION_TIMEOUT_MS, MAX_STDOUT_CHARS, MAX_STEPS
from nodus.runtime.module_loader import ModuleLoader
from nodus.tooling.sandbox import capture_output, configure_vm_limits
from nodus.vm.vm import VM, Record


class NodusRuntime:
    """Embedded Nodus runtime for hosting inside Python applications.

    ``NodusRuntime`` is the recommended public API for executing Nodus scripts
    from Python.  It manages the full compile-and-run pipeline (lexer → parser →
    module loader → compiler → optimizer → VM) and exposes host integration hooks
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
            Defaults to ``EXECUTION_TIMEOUT_MS`` from ``support/config.py``.
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
        self.last_vm: VM | None = None

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
        with open(path, "r", encoding="utf-8") as handle:
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
    ) -> dict:
        """Compile and execute a Nodus source string.

        This is the primary entry point for embedded execution.  The method runs
        the complete pipeline: lexer → parser → import resolution (ModuleLoader) →
        bytecode compiler → optimizer → VM execution.

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
        )
        if not self.allow_input:
            vm.input_fn = self._blocked_input
        if debugger is not None:
            vm.debugger = debugger
            vm.debug = True
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
                )
                if filename and os.path.isfile(filename):
                    loader.load_module_from_path(filename)
                else:
                    loader.load_module_from_source(source, module_name=filename or "<memory>")
            except Exception as err:
                raise coerce_error(err, stage="execute", filename=normalized) from err

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
        result = fn(*host_args)
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
