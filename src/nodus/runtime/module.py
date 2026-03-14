"""Runtime module representation for Nodus."""

from __future__ import annotations

from dataclasses import dataclass, field

from nodus.vm.vm import Record


@dataclass
class NodusModule:
    name: str
    bytecode: dict
    functions: dict
    code_locs: list
    globals: dict = field(default_factory=dict)
    exports: dict = field(default_factory=dict)
    initialized: bool = False

    def to_record(self) -> Record:
        return Record(dict(self.exports), kind="module")
