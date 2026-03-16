"""Runtime module representation for Nodus."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nodus.compiler.compiler import FunctionInfo


NODUS_BYTECODE_VERSION = 3  # v1.0: LOAD_LOCAL removed from VM dispatch table


@dataclass
class ModuleBytecode:
    code: dict
    functions: dict[str, "FunctionInfo"]
    constants: list[object] = field(default_factory=list)
    code_locs: list[tuple[str | None, int | None, int | None]] = field(default_factory=list)
    symbol_table: dict[str, object] = field(default_factory=dict)
    module_metadata: dict[str, object] = field(default_factory=dict)

    def to_cache_payload(self) -> dict[str, object]:
        return {
            "code": self.code,
            "functions": {
                name: {
                    "name": fn.name,
                    "params": list(fn.params),
                    "addr": fn.addr,
                    "upvalues": [
                        {
                            "name": upvalue.name,
                            "is_local": upvalue.is_local,
                            "index": upvalue.index,
                        }
                        for upvalue in fn.upvalues
                    ],
                    "display_name": fn.display_name,
                    "local_slots": dict(fn.local_slots) if fn.local_slots else {},
                }
                for name, fn in self.functions.items()
            },
            "constants": list(self.constants),
            "code_locs": [list(loc) for loc in self.code_locs],
            "symbol_table": dict(self.symbol_table),
            "module_metadata": dict(self.module_metadata),
        }

    @classmethod
    def from_cache_payload(cls, payload: dict[str, object]) -> "ModuleBytecode":
        from nodus.compiler.compiler import FunctionInfo
        from nodus.compiler.symbol_table import Upvalue

        raw_functions = payload.get("functions", {})
        functions: dict[str, FunctionInfo] = {}
        if isinstance(raw_functions, dict):
            for key, raw in raw_functions.items():
                if not isinstance(key, str) or not isinstance(raw, dict):
                    continue
                raw_upvalues = raw.get("upvalues", [])
                upvalues: list[Upvalue] = []
                if isinstance(raw_upvalues, list):
                    for item in raw_upvalues:
                        if not isinstance(item, dict):
                            continue
                        upvalues.append(
                            Upvalue(
                                name=str(item.get("name", "")),
                                is_local=bool(item.get("is_local", False)),
                                index=item.get("index"),
                            )
                        )
                raw_local_slots = raw.get("local_slots", {})
                local_slots: dict[str, int] = {}
                if isinstance(raw_local_slots, dict):
                    for sname, sidx in raw_local_slots.items():
                        if isinstance(sname, str) and isinstance(sidx, int):
                            local_slots[sname] = sidx
                functions[key] = FunctionInfo(
                    name=str(raw.get("name", key)),
                    params=[str(param) for param in raw.get("params", []) if isinstance(param, str)],
                    addr=int(raw.get("addr", 0)),
                    upvalues=upvalues,
                    display_name=str(raw.get("display_name", key)),
                    local_slots=local_slots,
                )

        raw_code_locs = payload.get("code_locs", [])
        code_locs: list[tuple[str | None, int | None, int | None]] = []
        if isinstance(raw_code_locs, list):
            for entry in raw_code_locs:
                if not isinstance(entry, (list, tuple)) or len(entry) != 3:
                    continue
                path, line, col = entry
                code_locs.append((path, line, col))

        code = payload.get("code", {})
        return cls(
            code=code if isinstance(code, dict) else {},
            functions=functions,
            constants=list(payload.get("constants", [])),
            code_locs=code_locs,
            symbol_table=dict(payload.get("symbol_table", {})),
            module_metadata=dict(payload.get("module_metadata", {})),
        )


class LiveBinding:
    def __init__(self, module: "NodusModule", name: str):
        self.module = module
        self.name = name

    def get(self) -> object:
        return self.module.get_export(self.name)

    def set(self, value: object) -> object:
        return self.module.set_export(self.name, value)


@dataclass
class NodusModule:
    name: str
    path: str
    bytecode: dict
    functions: dict[str, "FunctionInfo"]
    code_locs: list
    bytecode_unit: ModuleBytecode | None = None
    globals: dict = field(default_factory=dict)
    exports: dict = field(default_factory=dict)
    host_globals: dict = field(default_factory=dict)
    host_builtins: dict = field(default_factory=dict)
    initialized: bool = False
    kind: str = field(init=False, default="module")

    @property
    def fields(self) -> dict[str, object]:
        return {name: self.get_export(name) for name in self.exports}

    def export_names(self) -> list[str]:
        return list(self.exports.keys())

    def has_export(self, name: str) -> bool:
        return name in self.exports

    def export_binding(self, name: str) -> object:
        if name not in self.exports:
            raise KeyError(name)
        return self.exports[name]

    def get_export(self, name: str) -> object:
        if name not in self.exports:
            raise KeyError(name)
        value = self.exports[name]
        if isinstance(value, LiveBinding):
            if value.module is self and value.name == name:
                if name in self.globals:
                    return self.globals[name]
                if name in self.functions:
                    return ModuleFunction(self, name)
                return None
            return value.get()
        return value

    def set_export(self, name: str, value: object) -> object:
        if name not in self.exports:
            raise KeyError(name)
        binding = self.exports[name]
        if isinstance(binding, LiveBinding):
            if binding.module is self and binding.name == name:
                self.globals[name] = value
                return value
            return binding.set(value)
        self.exports[name] = value
        return value

    def invoke_function(self, name: str, args: list[object], caller_vm=None) -> object:
        if name not in self.functions:
            raise ValueError(f"Unknown module function: {name}")
        from nodus.vm.vm import Closure, _ClosureProxy, VM

        vm = VM(
            self.bytecode,
            self.functions,
            code_locs=self.code_locs,
            module_globals=self.globals,
            host_globals=self.host_globals,
            source_path=self.path,
        )
        if self.host_builtins:
            vm.builtins.update(self.host_builtins)

        # When a caller VM is provided:
        # 1. Replace any Closure arguments with _ClosureProxy objects so that
        #    CALL_VALUE dispatches them back through the caller's bytecode context.
        # 2. Store a reference to the caller VM so that reflection builtins
        #    (stack_frame, fn_module, etc.) can access the caller's context.
        if caller_vm is not None:
            vm._caller_vm = caller_vm
            args = [
                _ClosureProxy(arg, caller_vm) if isinstance(arg, Closure) and not isinstance(arg, _ClosureProxy) else arg
                for arg in args
            ]

        closure = Closure(self.functions[name], [])
        return vm.run_closure(closure, args)


@dataclass(frozen=True)
class ModuleFunction:
    module: NodusModule
    name: str

    def __call__(self, *args):
        return self.module.invoke_function(self.name, list(args))
