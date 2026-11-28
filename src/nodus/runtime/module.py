"""Runtime module representation for Nodus."""

from __future__ import annotations

import operator
import threading
import weakref
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from nodus.compiler.compiler import FunctionInfo


# The one definition; the compiler and the CLI read it from here.
#   4: v1.0, finally blocks (FINALLY_END).
#   5: #969, the optimizer's fused instructions LOAD_LOCAL_FIELD,
#      JUMP_IF_LOCAL_NE_CONST and ENTER.
NODUS_BYTECODE_VERSION = 5


@dataclass
class ModuleBytecode:
    code: Any
    functions: dict[str, "FunctionInfo"]
    constants: list[object] = field(default_factory=list)
    code_locs: list[tuple[str | None, int | None, int | None]] = field(default_factory=list)
    symbol_table: dict[str, object] = field(default_factory=dict)
    module_metadata: dict[str, Any] = field(default_factory=dict)

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
                    # #394: the step mark must survive the cache. Guarding only
                    # the compilation path left the bypass reachable on the
                    # *second* run of any script -- the same sibling-path shape
                    # as #521 and #400, where the bytecode cache was a third
                    # route to a question two other places already answered.
                    "step_owner": fn.step_owner,
                }
                for name, fn in self.functions.items()
            },
            "constants": list(self.constants),
            "code_locs": [list(loc) for loc in self.code_locs],
            "symbol_table": dict(self.symbol_table),
            "module_metadata": dict(self.module_metadata),
        }

    @classmethod
    def from_cache_payload(cls, payload: dict[str, Any]) -> "ModuleBytecode":
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
                    step_owner=(raw["step_owner"]
                                if isinstance(raw.get("step_owner"), str) else None),
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
    bytecode: Any
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
        from nodus.runtime.diagnostics import LangRuntimeError
        from nodus.vm.types import Closure, _ClosureProxy
        from nodus.vm.vm import VM
        fn_info = self.functions[name]
        expected = len(fn_info.params)
        if len(args) > expected:
            raise LangRuntimeError(
                "call",
                f"{name} expected {expected} args, got {len(args)}",
                path=None, stack=[],
            )
        # Pad missing args with None (nil) to support optional parameters.
        # Module functions may inspect missing params via `== nil` guards.
        if len(args) < expected:
            args = list(args) + [None] * (expected - len(args))

        # Everything the child's construction depends on: the pool's key too.
        construction: dict[str, Any] = dict(
            allowed_paths=caller_vm.allowed_paths if caller_vm is not None else None,
            fs_root=caller_vm.fs_root if caller_vm is not None else None,
            allow_subprocess=getattr(caller_vm, "allow_subprocess", True) if caller_vm is not None else True,
            allow_network=getattr(caller_vm, "allow_network", True) if caller_vm is not None else True,
            allow_env=getattr(caller_vm, "allow_env", True) if caller_vm is not None else True,
            allowed_commands=getattr(caller_vm, "allowed_commands", None) if caller_vm is not None else None,
            allowed_hosts=getattr(caller_vm, "allowed_hosts", None) if caller_vm is not None else None,
        )
        pool = ChildVMPool.of(caller_vm, self, construction)
        vm = pool.acquire() if pool is not None else None
        if vm is None:
            vm = VM(
                self.bytecode,
                self.functions,
                code_locs=self.code_locs,
                module_globals=self.globals,
                host_globals=self.host_globals,
                source_path=self.path,
                **construction,
            )
            if pool is not None:
                pool.adopt(vm)
        # #405: authority must not be shed by crossing into a module or a tool
        # handler. A policy that applied only to the top-level VM would be
        # bypassed by `import "std:subprocess"`, which is how everyone calls it.
        #
        # #868: the host wiring is inherited too. This was seven attributes
        # copied by hand, and `agent_registry` was missing: a module function's
        # `agent_call` resolved against the process-global registry while the
        # same call at top level used the runtime's own.
        #
        # And the run's bounds. Without them every module function -- the whole
        # stdlib included -- ran with no step budget and no deadline, and its
        # instructions were never counted against the caller's.
        from nodus.runtime.capability import charge_run_bounds, derive_child_vm  # noqa: E402

        derive_child_vm(vm, caller_vm)
        if self.host_builtins:
            vm.builtins.update(self.host_builtins)

        # When a caller VM is provided:
        # 1. Replace any Closure arguments with _ClosureProxy objects so that
        #    CALL_VALUE dispatches them back through the caller's bytecode context.
        # 2. Store a reference to the caller VM so that reflection builtins
        #    (stack_frame, fn_module, etc.) can access the caller's context.
        if caller_vm is not None:
            setattr(vm, "_caller_vm", caller_vm)
            # ASYNC-MOD-003 (#339): share the caller's scheduler. This VM is
            # detached, and its own scheduler never runs once the call returns
            # (the VM is dropped, or pooled and reset, #987), so anything spawned
            # on its own scheduler is never run — `worker_pool` and `pipeline`
            # spawn workers and hand the channel back for the *caller* to drive,
            # and every job was silently dropped.
            #
            # Sharing the scheduler is only half of it: the coroutines still have
            # to run on THIS VM, which owns their code, builtins and `functions`
            # table. `spawn` tags each with `owner_vm` and the scheduler resumes
            # it there (see `Scheduler._owner`). Resuming them on the caller's VM
            # instead is what an earlier attempt did, and it corrupts execution —
            # builtins close over the VM that registered them.
            vm.scheduler = caller_vm.scheduler
            args = [
                _ClosureProxy(arg, caller_vm) if isinstance(arg, Closure) and not isinstance(arg, _ClosureProxy) else arg
                for arg in args
            ]

        closure = Closure(self.functions[name], [])
        returned = False
        try:
            result = vm.run_closure(closure, args)
            returned = True
            return result
        finally:
            # In `finally`, so a call that raises is charged too: an uncharged
            # failure would be a free retry.
            charge_run_bounds(vm, caller_vm)
            if pool is not None:
                pool.release(vm, reusable=returned)


class ChildVMPool:
    """Idle child VMs for one caller VM's calls into one module (#987).

    A call into a module function ran on a new VM, and building one costs about
    1.4 ms: every builtin is registered again, paths are resolved and the
    dispatch table is rebuilt. A loop calling `s.starts_with` 48,000 times spent
    50 s doing it. The builtins close over the VM that registered them, so the
    construction cannot be shared; the VM can be reused.

    **A reused VM must be indistinguishable from a new one.** The construction
    arguments are part of the key, so a reused VM was built exactly as a new one
    would be, the capability groups withheld at registration included. Before
    each call `reset` returns it to the state it had straight after
    construction; `invoke_function` then derives it from the caller (authority,
    host state, what is left of the run's bounds) and sets up the call, the same
    steps in the same order as for a new VM. The reset works from a snapshot of
    every attribute, not from a list of the ones a call changes, so an attribute
    added to `VM` later is covered without anyone remembering it here:

    - an attribute rebound since is bound back, and one added since is deleted;
    - a list, dict or set the VM built itself is restored in place. One it was
      handed -- the module's code, functions and globals -- is shared with the
      module and left alone: module state outlives a call by design.

    **Not reused**: a VM that is running (a call that re-enters the same module
    gets a new one), one whose call raised, and one that owns a coroutine, which
    must stay with it (#339). Without a caller VM nothing is pooled.

    **Nothing here is stored on a VM.** The pools and the set of coroutine
    owners are weak maps in this module. A `VM` instance must stay under PyPy's
    80-attribute map limit (#702, `tests/test_vm_attribute_budget.py`), and an
    attribute set on the caller, or on whichever VM spawns a coroutine, would
    push every program that calls a module or spawns one past it.
    """

    #: The most idle VMs kept per caller and module.
    LIMIT = 4

    def __init__(self, module: "NodusModule", key: tuple) -> None:
        self.module = module  # held, so `id(module)` in the caller's map stays valid
        self.key = key
        self.idle: list = []
        self._snapshots: dict = {}

    @classmethod
    def of(cls, caller_vm, module: "NodusModule", construction: dict) -> "ChildVMPool | None":
        if caller_vm is None:
            return None
        with _POOLS_LOCK:
            pools = _POOLS.get(caller_vm)
            if pools is None:
                pools = _POOLS[caller_vm] = {}
        try:
            # In the dict's own order: `invoke_function` builds it the same way
            # every time, so no sort is needed.
            key = tuple((name, tuple(value) if type(value) is list else value)
                        for name, value in construction.items())
            hash(key)
        except TypeError:
            return None  # an unhashable construction argument: never pooled
        pool = pools.get(id(module))
        if pool is None or pool.module is not module or pool.key != key:
            pool = cls(module, key)
            pools[id(module)] = pool
        return pool

    def adopt(self, vm) -> None:
        """Record new `vm`'s state straight after construction."""
        module = self.module
        shared = {id(module.bytecode), id(module.functions), id(module.code_locs),
                  id(module.globals), id(module.host_globals)}
        state = vars(vm)
        # Its own containers: empty when built (the stack, the frames...), or
        # built with contents (the builtins, the dispatch table).
        empty = [value for value in state.values()
                 if id(value) not in shared and type(value) in _CONTAINERS and not value]
        full = [(value, type(value)(value)) for value in state.values()
                if id(value) not in shared and type(value) in _CONTAINERS and value]
        self._snapshots[id(vm)] = _Snapshot(dict(state), tuple(state.values()), empty, full)

    def acquire(self):
        """An idle VM, reset, or None."""
        if not self.idle:
            return None
        vm = self.idle.pop()
        self.reset(vm)
        return vm

    def release(self, vm, *, reusable: bool) -> None:
        if (reusable and len(self.idle) < self.LIMIT
                and vm not in _COROUTINE_OWNERS
                and id(vm) in self._snapshots):
            # Drop what the call left referenced: the caller (an idle VM must
            # not keep it alive, its pool is keyed weakly on it), its host
            # objects, the call's values. `acquire` does the full reset.
            self._rebind(vm)
            self.idle.append(vm)
        else:
            self._snapshots.pop(id(vm), None)

    def reset(self, vm) -> None:
        """Return `vm` to its state straight after construction.

        The one full reset a call gets, in `acquire`, so it also covers a VM
        that something touched while idle. Each part costs what it must, and
        no more (#987): together these were half of a module call.
        """
        self._rebind(vm)
        for value, copy in self._snapshots[id(vm)].full:
            if type(value) is dict:
                # Cheaper restored than compared: a dict compares by lookup.
                value.clear()
                value.update(copy)
            elif value != copy:
                # A list or set that is unchanged compares equal in C, on the
                # identity shortcut.
                if type(value) is list:
                    value[:] = copy
                else:
                    value.clear()
                    value.update(copy)

    def _rebind(self, vm) -> None:
        """Every attribute back to the very object it held when built, nothing
        added, and the VM's own empty containers emptied again."""
        snapshot = self._snapshots[id(vm)]
        state = vars(vm)
        # Untouched is the case after `release`, and checking it in C is a
        # fraction of the loop below: the same objects, in the same order.
        # Strictly by identity, never by equality: an equal object is not the
        # same one.
        if not (len(state) == len(snapshot.values)
                and all(map(operator.is_, state.values(), snapshot.values))):
            attributes = snapshot.attributes
            for name in [n for n in state if n not in attributes]:
                del state[name]
            for name, value in attributes.items():
                if state.get(name, _ABSENT) is not value:
                    state[name] = value
        for value in snapshot.empty:
            if value:
                value.clear()


_ABSENT = object()
_CONTAINERS = (list, dict, set)


@dataclass(frozen=True)
class _Snapshot:
    """A pooled VM straight after construction (`ChildVMPool.adopt`)."""
    attributes: dict  # name -> the object it held
    values: tuple     # the same objects, in attribute order, for the fast check
    empty: list       # its own containers that were empty
    full: list        # (container, copy) for its own containers with contents

#: Caller VM -> {id(module): ChildVMPool}. Weak, so a pool lives exactly as long
#: as its caller; the lock covers concurrent runtimes on other threads.
_POOLS: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()
_POOLS_LOCK = threading.Lock()
#: VMs that own a coroutine, which never go back into a pool.
_COROUTINE_OWNERS: "weakref.WeakSet" = weakref.WeakSet()


def mark_coroutine_owner(vm) -> None:
    """Record that `vm` owns a coroutine (#987). Called wherever `owner_vm` is
    assigned; `tests/test_module_call_vm_pool.py` holds every such site to it."""
    _COROUTINE_OWNERS.add(vm)


@dataclass(frozen=True)
class ModuleFunction:
    module: NodusModule
    name: str

    def __call__(self, *args):
        return self.module.invoke_function(self.name, list(args))
