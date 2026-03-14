"""Runtime module representation for Nodus."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nodus.vm.vm import FunctionInfo


@dataclass
class NodusModule:
    name: str
    bytecode: dict
    functions: dict[str, "FunctionInfo"]
    code_locs: list
    globals: dict = field(default_factory=dict)
    exports: dict = field(default_factory=dict)
    host_globals: dict = field(default_factory=dict)
    host_builtins: dict = field(default_factory=dict)
    initialized: bool = False

    def to_record(self) -> Record:
        from nodus.vm.vm import Record

        return Record(dict(self.exports), kind="module")

    def invoke_function(self, name: str, args: list[object]) -> object:
        if name not in self.functions:
            raise ValueError(f"Unknown module function: {name}")
        from nodus.vm.vm import VM, Closure

        vm = VM(
            self.bytecode,
            self.functions,
            code_locs=self.code_locs,
            module_globals=self.globals,
            host_globals=self.host_globals,
            source_path=self.name,
        )
        if self.host_builtins:
            vm.builtins.update(self.host_builtins)
        closure = Closure(self.functions[name], [])
        return vm.run_closure(closure, args)


@dataclass(frozen=True)
class ModuleFunction:
    module: NodusModule
    name: str

    def __call__(self, *args):
        return self.module.invoke_function(self.name, list(args))
