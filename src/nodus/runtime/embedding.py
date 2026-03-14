"""Embedding API for hosting the Nodus runtime inside Python apps."""

from __future__ import annotations

import inspect
import os

from nodus.builtins.nodus_builtins import BUILTIN_NAMES, BuiltinInfo
from nodus.result import Result, normalize_filename
from nodus.runtime.errors import coerce_error
from nodus.support.config import EXECUTION_TIMEOUT_MS, MAX_STDOUT_CHARS, MAX_STEPS
from nodus.runtime.module_loader import ModuleLoader
from nodus.tooling.sandbox import capture_output, configure_vm_limits
from nodus.vm.vm import VM, Record


class NodusRuntime:
    def __init__(
        self,
        *,
        max_steps: int | None = MAX_STEPS,
        timeout_ms: int | None = EXECUTION_TIMEOUT_MS,
        max_stdout_chars: int | None = MAX_STDOUT_CHARS,
        project_root: str | None = None,
    ) -> None:
        self.max_steps = max_steps
        self.timeout_ms = timeout_ms
        self.max_stdout_chars = max_stdout_chars
        self.project_root = project_root
        self._host_functions: dict[str, BuiltinInfo] = {}
        self.last_vm: VM | None = None

    def register_function(self, name: str, fn, *, arity: int | tuple[int, ...] | None = None) -> None:
        if not isinstance(name, str) or not name:
            raise ValueError("Host function name must be a non-empty string")
        if name in BUILTIN_NAMES:
            raise ValueError(f"Cannot override built-in function: {name}")
        resolved_arity = self._resolve_arity(fn, arity)
        self._host_functions[name] = BuiltinInfo(name, resolved_arity, fn)

    def reset(self) -> None:
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
    ) -> dict:
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
    ) -> dict:
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
        )
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
