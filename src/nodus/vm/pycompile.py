"""Compile eligible Nodus functions to Python functions (#173, phase 1).

Design: `docs/design/throughput/01-compile-to-python.md`. Opt-in.
`NodusRuntime(compile_functions=True)`, `nodus run --compile`, or
`NODUS_COMPILE_FUNCTIONS=1` switch it on. `NODUS_COMPILE_FUNCTIONS=always`
compiles every eligible function on its first call, which is what the
differential CI job runs the suite under.

A compiled function must be indistinguishable from the interpreter except in
speed. So it uses the interpreter's own machinery wherever the interpreter
decides something:
- `VM.build_call_frame` makes the frames, so stack traces and `max_frames`
  agree;
- `VM.invoke_builtin` runs builtins, so the capability check has one copy;
- `read_field`, `read_index`, `_nodus_eq`, `is_truthy` and the type-error
  helpers do the semantics;
- any operation without an inlined fast path calls the VM's handler on
  `vm.stack`, so it is exact by construction.

Counting replays the interpreter's fast loop exactly (`_count`). Before anything
that can raise, `vm.ip` is set to that instruction's address, so an error's
location is the interpreter's.

**Eligibility is a closed set.** A function compiles only if:
- every opcode is supported;
- it has no cells or closures and no `try`;
- every call is to a builtin in `COMPILABLE_BUILTINS` (synchronous, no
  authority, never suspending) or to another eligible function in the same
  chunk, with the right arity.

So compiled code never suspends, and never calls an interpreted function except
past the depth cap (`call_interpreted`).
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field

from nodus.runtime.capability import NO_AUTHORITY_BUILTINS
from nodus.runtime.channel import ChannelRecvRequest
from nodus.runtime.scheduler import CheckpointRequest, SleepRequest
from nodus.vm.types import Record

#: The `NO_AUTHORITY_BUILTINS` categories whose builtins compiled code may call:
#: synchronous, touching nothing, never suspending. Named by category so the
#: classification in `capability.py` stays the one place a builtin is sorted.
#: Deliberately not here: "in-process concurrency" (`sleep`, `recv`, `wait`,
#: `run_loop`...), "orchestration of work that is itself governed"
#: (`__workflow_checkpoint`, `workflow_wait`, `retry_call`, `run_workflow`...),
#: and introspection, discovery, registry, tool and test-harness builtins.
#: `tests/test_pycompile.py` pins this against the categories.
COMPILABLE_BUILTIN_CATEGORIES = (
    "pure computation",
    "hashing of values already in hand",
    "path strings, touching no filesystem",
    "process-local clock and randomness",
    "host-mediated console i/o",
)
COMPILABLE_BUILTINS = frozenset(
    name for category in COMPILABLE_BUILTIN_CATEGORIES
    for name in NO_AUTHORITY_BUILTINS[category]
)

#: Calls before a function without a loop is compiled. A function with a loop
#: compiles on its first call: a function called once can hold a program's
#: hottest loop (`tokenize`), and a call count never reaches it. Measured on the
#: self-hosted frontend, 2026-11-21: threshold 0 ran in 1.24 s, and 8, 32, 128
#: and 512 in 1.72-1.82 s, because the once-called loops stayed interpreted.
#: Compiling costs about 1.8 ms per function.
DEFAULT_THRESHOLD = 32
#: Compiled activations allowed on the Python stack at once. Past it, calls go
#: to the interpreter, whose own calls do not recurse in Python. Each compiled
#: level costs about two Python frames; from a plain `run_source`, 450 survived
#: 3,000-deep recursion and 500 hit Python's default limit of 1,000. So the cap
#: is this, or a fifth of the current recursion limit if that is lower.
DEFAULT_DEPTH_CAP = 200

ENV_VAR = "NODUS_COMPILE_FUNCTIONS"

JUMP_TARGET = {"JUMP": 1, "JUMP_IF_FALSE": 1, "JUMP_IF_TRUE": 1, "JUMP_IF_LOCAL_NE_CONST": 3,
               "ITER_NEXT": 1}

# Operations run by the VM's own handler on `vm.stack`: (pops, pushes) per instruction.
_DELEGATED = {
    "MUL": lambda i: (2, 1),
    "DIV": lambda i: (2, 1),
    "MOD": lambda i: (2, 1),
    "NEG": lambda i: (1, 1),
    "GET_ITER": lambda i: (1, 1),
    "INDEX_SET": lambda i: (3, 1),
    "BUILD_LIST": lambda i: (i[1], 1),
    "BUILD_MAP": lambda i: (2 * i[1], 1),
    "BUILD_RECORD": lambda i: (2 * i[1], 1),
    "THROW": lambda i: (1, 0),
}
_INLINE_EFFECT = {
    "PUSH_CONST": 1, "LOAD": 1, "LOAD_LOCAL_IDX": 1, "LOAD_LOCAL_FIELD": 1,
    "STORE": -1, "STORE_LOCAL_IDX": -1, "POP": -1, "STORE_FIELD": -1,
    "LOAD_FIELD": 0, "NOT": 0, "TO_BOOL": 0, "RESET_LOCAL_IDX": 0, "ENTER": 0,
    "FRAME_SIZE": 0, "JUMP": 0, "JUMP_IF_LOCAL_NE_CONST": 0,
    "EQ": -1, "NE": -1, "ADD": -1, "SUB": -1, "LT": -1, "GT": -1, "LE": -1, "GE": -1,
    "INDEX": -1, "JUMP_IF_FALSE": -1, "JUMP_IF_TRUE": -1, "RETURN": -1,
}
SUPPORTED = frozenset(_INLINE_EFFECT) | frozenset(_DELEGATED) | {"CALL", "ITER_NEXT"}
_TERMINAL = {"RETURN", "THROW", "JUMP"}


class Ineligible(Exception):
    """Why a function stays interpreted."""


def _effect(instr) -> int:
    op = instr[0]
    if op in _INLINE_EFFECT:
        return _INLINE_EFFECT[op]
    if op in _DELEGATED:
        pops, pushes = _DELEGATED[op](instr)
        return pushes - pops
    if op == "CALL":
        return 1 - instr[2]
    if op == "ITER_NEXT":
        return 1  # the fall-through edge; the exit edge is handled in _stack_depths
    raise Ineligible(f"opcode {op}")


# --- eligibility --------------------------------------------------------------

def function_bodies(code: list, functions: dict) -> dict:
    """name -> (start, end): each function's instructions in the chunk."""
    starts = sorted({fn.addr for fn in functions.values()})
    main = code[0][1] if code and code[0][0] == "JUMP" else len(code)
    bounds = sorted(set(starts) | {main, len(code)})
    out = {}
    for name, fn in functions.items():
        later = [b for b in bounds if b > fn.addr]
        out[name] = (fn.addr, later[0] if later else len(code))
    return out


def eligible_functions(code: list, functions: dict, builtins: dict) -> dict:
    """name -> reason it is ineligible, or None if eligible. A greatest fixed
    point: start from every function that passes the local checks, then drop any
    that calls a function no longer in the set."""
    bodies = function_bodies(code, functions)
    reasons: dict = {}
    calls: dict = {}
    for name, fn in functions.items():
        start, end = bodies[name]
        try:
            if fn.upvalues:
                raise Ineligible("captures upvalues")
            if getattr(fn, "step_owner", None) is not None:
                raise Ineligible("a workflow step body")
            if not (0 <= start < end <= len(code)):
                raise Ineligible("no body in this chunk")
            callees = set()
            for instr in code[start:end]:
                op = instr[0]
                if op not in SUPPORTED:
                    raise Ineligible(f"opcode {op}")
                if op == "CALL":
                    callee, argc = instr[1], instr[2]
                    if callee in functions:
                        if argc != len(functions[callee].params) or functions[callee].upvalues:
                            raise Ineligible(f"call to {callee}: arity or closure")
                        callees.add(callee)
                    elif callee in builtins and callee in COMPILABLE_BUILTINS:
                        pass
                    else:
                        raise Ineligible(f"call to {callee}")
            _ = _stack_depths(code, start, end)
            reasons[name] = None
            calls[name] = callees
        except Ineligible as why:
            reasons[name] = str(why)
    changed = True
    while changed:
        changed = False
        for name, callees in calls.items():
            if reasons[name] is None:
                bad = next((c for c in callees if reasons.get(c) is not None), None)
                if bad is not None:
                    reasons[name] = f"calls {bad}, which stays interpreted"
                    changed = True
    return reasons


def _leaders(code: list, start: int, end: int) -> list:
    leaders = {start}
    for i in range(start, end):
        instr = code[i]
        if instr[0] in JUMP_TARGET:
            leaders.add(instr[JUMP_TARGET[instr[0]]])
            leaders.add(i + 1)
        elif instr[0] in ("RETURN", "THROW"):
            leaders.add(i + 1)
    return sorted(x for x in leaders if start <= x < end)


def _stack_depths(code: list, start: int, end: int) -> dict:
    depth = {start: 0}
    work = [start]
    while work:
        i = work.pop()
        instr = code[i]
        op = instr[0]
        after = depth[i] + _effect(instr)
        if op in ("RETURN", "THROW"):
            edges = []
        elif op == "JUMP":
            edges = [(instr[1], after)]
        elif op == "ITER_NEXT":
            # Exhausted: the iterator is popped and control jumps. Otherwise the
            # item is pushed on top of the iterator.
            edges = [(instr[1], depth[i] - 1), (i + 1, after)]
        elif op in JUMP_TARGET:
            edges = [(instr[JUMP_TARGET[op]], after), (i + 1, after)]
        else:
            edges = [(i + 1, after)]
        for j, after in edges:
            if not (start <= j < end):
                raise Ineligible("control leaves the function")
            if j in depth:
                if depth[j] != after:
                    raise Ineligible("inconsistent stack depth")
            else:
                depth[j] = after
                work.append(j)
    return depth


# --- code generation ----------------------------------------------------------

def generate(name: str, fn, code: list, start: int, end: int, py_name: str) -> str:
    """Python source for one eligible function."""
    depth = _stack_depths(code, start, end)
    leaders = [b for b in _leaders(code, start, end) if b in depth]
    first = code[start]
    nslots = first[1] if first[0] in ("ENTER", "FRAME_SIZE") else 0
    params = list(fn.params)
    out = [f"def {py_name}(vm{''.join(', a' + str(k) for k in range(len(params)))}):"]
    for slot in range(nslots):
        out.append(f"    l{slot} = None")
    for k, param in enumerate(params):
        slot = fn.local_slots.get(param)
        if slot is not None:
            out.append(f"    l{slot} = a{k}")
    out.append(f"    pc = {start}")
    # A block is counted when it is entered. If something in it raises, the
    # interpreter would have counted only up to the failing instruction, so the
    # rest of the block is taken back: `be` is the current block's end, `h` the
    # address of the last instruction that could raise. `be` is None while the
    # block is being counted, because `count` is exact on its own errors.
    out.append("    be = None")
    out.append(f"    h = {start}")
    out.append("    try:")
    out.append("        while True:")
    for bi, b0 in enumerate(leaders):
        b1 = leaders[bi + 1] if bi + 1 < len(leaders) else end
        out.append(f"            {'if' if bi == 0 else 'elif'} pc == {b0}:")
        ind = " " * 16
        out.append(f"{ind}be = None")
        out.append(f"{ind}c = vm.instructions_executed")
        out.append(f"{ind}if c + {b1 - b0} <= vm._next_check: vm.instructions_executed = c + {b1 - b0}")
        out.append(f"{ind}else: count(vm, {b1 - b0}, {b0})")
        out.append(f"{ind}be = {b1}")
        d = depth[b0]
        ended = False
        for i in range(b0, b1):
            instr = code[i]
            ended = _emit(out, ind, instr, i, d)
            d += _effect(instr)
            if ended:
                break
        if not ended:
            out.append(f"{ind}pc = {b1}")
    out.append("    except BaseException:")
    out.append("        if be is not None:")
    out.append("            vm.instructions_executed -= be - h - 1")
    out.append("        raise")
    return "\n".join(out) + "\n"


def _field_read(obj: str, name: str) -> str:
    return f"{obj}.fields[{name}] if type({obj}) is Record and {name} in {obj}.fields else vm.read_field({obj}, {name})"


def _emit(out: list, ind: str, instr: tuple, addr: int, d: int) -> bool:
    """Append the code for one instruction; True if it ends the block."""
    op = instr[0]
    s = lambda k: f"s{k}"  # noqa: E731
    at = f"{ind}vm.ip = h = {addr}"

    def truthy(c: str) -> str:
        return f"({c} is True or ({c} is not False and {c} is not None and vm.is_truthy({c})))"

    if op in ("ENTER", "FRAME_SIZE", "RESET_LOCAL_IDX", "POP"):
        # Locals are Python locals and no slot holds a Cell (no closures), so
        # these have nothing to do; POP's operand is simply not used again.
        return False
    if op == "PUSH_CONST":
        out.append(f"{ind}{s(d)} = CONSTS[{addr}]")
    elif op == "LOAD_LOCAL_IDX":
        out.append(f"{ind}{s(d)} = l{instr[1]}")
    elif op == "STORE_LOCAL_IDX":
        out.append(f"{ind}l{instr[1]} = {s(d - 1)}")
    elif op == "LOAD":
        out.append(at)
        out.append(f"{ind}{s(d)} = vm.load_name({instr[1]!r})")
    elif op == "STORE":
        out.append(at)
        out.append(f"{ind}vm.store_name({instr[1]!r}, {s(d - 1)})")
    elif op == "LOAD_LOCAL_FIELD":
        out.append(at)
        out.append(f"{ind}o = l{instr[1]}")
        out.append(f"{ind}{s(d)} = {_field_read('o', repr(instr[2]))}")
    elif op == "LOAD_FIELD":
        out.append(at)
        out.append(f"{ind}o = {s(d - 1)}")
        out.append(f"{ind}{s(d - 1)} = {_field_read('o', repr(instr[1]))}")
    elif op == "STORE_FIELD":
        o, v = s(d - 2), s(d - 1)
        out.append(at)
        out.append(f"{ind}if type({o}) is Record: {o}.fields[{instr[1]!r}] = {v}")
        out.append(f"{ind}else: {v} = delegate(vm, INSTRS[{addr}], [{o}, {v}])")
        out.append(f"{ind}{o} = {v}")
    elif op in ("EQ", "NE"):
        a, b = s(d - 2), s(d - 1)
        neg = "not " if op == "NE" else ""
        out.append(f"{ind}{a} = {neg}(({a} == {b}) if type({a}) is str and type({b}) is str else vm._nodus_eq({a}, {b}))")
    elif op in ("ADD", "SUB"):
        a, b = s(d - 2), s(d - 1)
        pyop, word = ("+", "add") if op == "ADD" else ("-", "subtract")
        out.append(at)
        out.append(f"{ind}try: {a} = {a} {pyop} {b}")
        out.append(f"{ind}except TypeError: vm._binary_type_error({word!r}, {a}, {b})")
    elif op in ("LT", "GT", "LE", "GE"):
        a, b = s(d - 2), s(d - 1)
        pyop = {"LT": "<", "GT": ">", "LE": "<=", "GE": ">="}[op]
        out.append(at)
        out.append(f"{ind}try: {a} = {a} {pyop} {b}")
        out.append(f"{ind}except TypeError: vm._compare_type_error({a}, {b})")
    elif op == "INDEX":
        out.append(at)
        out.append(f"{ind}{s(d - 2)} = vm.read_index({s(d - 2)}, {s(d - 1)})")
    elif op == "NOT":
        out.append(f"{ind}{s(d - 1)} = not {truthy(s(d - 1))}")
    elif op == "TO_BOOL":
        out.append(f"{ind}{s(d - 1)} = {truthy(s(d - 1))}")
    elif op in _DELEGATED:
        pops, pushes = _DELEGATED[op](instr)
        args = ", ".join(s(k) for k in range(d - pops, d))
        out.append(at)
        if op == "THROW":
            out.append(f"{ind}delegate(vm, INSTRS[{addr}], [{args}])")
            return True
        out.append(f"{ind}{s(d - pops)} = delegate(vm, INSTRS[{addr}], [{args}])")
    elif op == "CALL":
        argc = instr[2]
        args = ", ".join(s(k) for k in range(d - argc, d))
        out.append(at)
        out.append(f"{ind}{s(d - argc)} = CALLS[{addr}](vm, [{args}])")
    elif op == "RETURN":
        out.append(f"{ind}return {s(d - 1)}")
        return True
    elif op == "JUMP":
        out.append(f"{ind}pc = {instr[1]}")
        out.append(f"{ind}continue")
        return True
    elif op in ("JUMP_IF_FALSE", "JUMP_IF_TRUE"):
        cond = truthy(s(d - 1))
        if op == "JUMP_IF_FALSE":
            cond = f"not {cond}"
        out.append(f"{ind}if {cond}:")
        out.append(f"{ind}    pc = {instr[1]}")
        out.append(f"{ind}    continue")
        out.append(f"{ind}pc = {addr + 1}")
        out.append(f"{ind}continue")
        return True
    elif op == "ITER_NEXT":
        it = s(d - 1)
        out.append(at)
        out.append(f"{ind}if not isinstance({it}, Iterator): vm.runtime_error('type', 'Iterator is not supported')")
        out.append(f"{ind}item, exhausted = {it}.advance()")
        out.append(f"{ind}if exhausted:")
        out.append(f"{ind}    pc = {instr[1]}")
        out.append(f"{ind}    continue")
        out.append(f"{ind}{s(d)} = item")
        out.append(f"{ind}pc = {addr + 1}")
        out.append(f"{ind}continue")
        return True
    elif op == "JUMP_IF_LOCAL_NE_CONST":
        v = f"l{instr[1]}"
        out.append(f"{ind}k = CONSTS[{addr}]")
        out.append(f"{ind}if not (({v} == k) if type({v}) is str and type(k) is str else vm._nodus_eq({v}, k)):")
        out.append(f"{ind}    pc = {instr[3]}")
        out.append(f"{ind}    continue")
        out.append(f"{ind}pc = {addr + 1}")
        out.append(f"{ind}continue")
        return True
    else:  # pragma: no cover - eligibility refuses anything else
        raise Ineligible(f"opcode {op}")
    return False


# --- runtime helpers the generated code calls ----------------------------------

def count(vm, k: int, addr: int) -> None:
    """Count `k` instructions starting at `addr` exactly as `execute`'s fast loop
    would: increment, or call `record_instruction` once the count reaches
    `_next_check`. `vm.ip` is set first, so a limit error is located where the
    interpreter would locate it."""
    i = 0
    while i < k:
        c = vm.instructions_executed
        nc = vm._next_check
        if c >= nc:
            vm.ip = addr + i
            vm.record_instruction()
            i += 1
        else:
            step = min(k - i, nc - c)
            vm.instructions_executed = c + step
            i += step


def delegate(vm, instr: tuple, operands: list):
    """Run the VM's own handler for `instr` on `operands`; return what it pushed."""
    stack = vm.stack
    base = len(stack)
    stack.extend(operands)
    ip = vm.ip
    vm._dispatch[instr[0]](instr)
    vm.ip = ip
    result = stack[base] if len(stack) > base else None
    del stack[base:]
    return result


_SUSPEND = (SleepRequest, ChannelRecvRequest, CheckpointRequest)


def make_builtin_call(name: str):
    def call(vm, args):
        vm.record_vm_call(name, "call", raw=True)
        vm.check_builtin_arity(name, len(args))
        result = vm.invoke_builtin(name, args)
        if isinstance(result, _SUSPEND):
            # Eligibility admits only builtins that cannot suspend. This is the
            # net under that rule: a loud failure, never a silent misbehaviour.
            vm.runtime_error("runtime", f"internal: {name} suspended inside compiled code (#173)")
        return vm.finish_builtin_value(result)
    return call


# --- per-VM state ---------------------------------------------------------------

@dataclass
class _Chunk:
    code: list
    reasons: dict
    loops: set = field(default_factory=set)
    compiled: dict = field(default_factory=dict)
    sources: dict = field(default_factory=dict)


def functions_with_loops(code: list, functions: dict) -> set:
    """Names of the functions whose body has a backward jump: a loop."""
    out = set()
    for name, (start, end) in function_bodies(code, functions).items():
        for i in range(max(start, 0), min(end, len(code))):
            instr = code[i]
            pos = JUMP_TARGET.get(instr[0])
            if pos is not None and isinstance(instr[pos], int) and instr[pos] <= i:
                out.add(name)
                break
    return out


class CompileState:
    """Whether, what and when to compile, for one VM."""

    def __init__(self, *, threshold: int | None = None, depth_cap: int | None = None):
        # Resolved here, not as parameter defaults, so the module constants are
        # read when a state is made (and can be patched by a test).
        self.threshold = DEFAULT_THRESHOLD if threshold is None else threshold
        self.depth_cap = (min(DEFAULT_DEPTH_CAP, max(10, sys.getrecursionlimit() // 5))
                          if depth_cap is None else depth_cap)
        self.depth = 0
        self.calls: dict = {}
        self._chunks: dict = {}
        self.compiled_count = 0

    # The chunk is the VM's current code list; analysis is per chunk.
    def _chunk(self, vm) -> _Chunk:
        key = id(vm.code)
        chunk = self._chunks.get(key)
        if chunk is None or chunk.code is not vm.code:
            chunk = _Chunk(vm.code, eligible_functions(vm.code, vm.functions, vm.builtins),
                           functions_with_loops(vm.code, vm.functions))
            self._chunks[key] = chunk
        return chunk

    def may_run(self, vm) -> bool:
        return (self.depth < self.depth_cap
                and vm.task_step_budget is None
                and not vm._instrumented())

    def target(self, vm, name: str, fn):
        """The compiled function to run for this call, or None for the interpreter."""
        chunk = self._chunk(vm)
        compiled = chunk.compiled.get(name)
        if compiled is None:
            if chunk.reasons.get(name) is not None:
                return None
            n = self.calls.get(name, 0) + 1
            self.calls[name] = n
            if n < self.threshold and name not in chunk.loops:
                return None
            compiled = self._compile(vm, chunk, name)
        if not self.may_run(vm):
            return None
        return compiled

    def _compile(self, vm, chunk: _Chunk, name: str):
        """Compile `name` and, on demand, everything it calls."""
        if name in chunk.compiled:
            return chunk.compiled[name]
        bodies = function_bodies(chunk.code, vm.functions)
        start, end = bodies[name]
        fn = vm.functions[name]
        py_name = "nd_" + "".join(ch if ch.isalnum() else "_" for ch in name)
        source = generate(name, fn, chunk.code, start, end, py_name)
        from nodus.vm.vm import Iterator  # here, not at import: vm.py imports this module

        calls: dict = {}
        namespace = {
            "Record": Record, "Iterator": Iterator, "count": count, "delegate": delegate,
            "CONSTS": {i: chunk.code[i][1] for i in range(start, end)
                       if chunk.code[i][0] in ("PUSH_CONST",)} | {
                i: chunk.code[i][2] for i in range(start, end)
                if chunk.code[i][0] == "JUMP_IF_LOCAL_NE_CONST"},
            "INSTRS": {i: chunk.code[i] for i in range(start, end)},
            "CALLS": calls,
        }
        exec(compile(source, f"<nodus compiled {name}>", "exec"), namespace)  # noqa: S102
        compiled = namespace[py_name]
        chunk.compiled[name] = compiled
        chunk.sources[name] = source
        self.compiled_count += 1
        for i in range(start, end):
            instr = chunk.code[i]
            if instr[0] == "CALL":
                callee = instr[1]
                calls[i] = (self._user_call(vm, chunk, callee) if callee in vm.functions
                            else make_builtin_call(callee))
        return compiled

    def _user_call(self, vm, chunk: _Chunk, callee: str):
        """A call from compiled code to an eligible function."""
        state = self

        def call(vm, args):
            fn = vm.functions[callee]
            vm.record_vm_call(callee, "call", raw=True)
            compiled = chunk.compiled.get(callee) or state._compile(vm, chunk, callee)
            if state.depth >= state.depth_cap or not state.may_run(vm):
                return call_interpreted(vm, callee, fn, args)
            frame = vm.build_call_frame(callee, fn, 0)
            for param, value in zip(fn.params, args):
                frame.locals[param] = value
            vm.frames.append(frame)
            state.depth += 1
            try:
                result = compiled(vm, *args)
            finally:
                state.depth -= 1
            vm.frames.pop()
            vm.record_vm_return(callee, raw=True)
            return result
        return call

    def invoke(self, vm, compiled, name: str, fn, arg_count: int):
        """`CALL` from the interpreter to a compiled function."""
        call_ip = vm.ip
        frame = vm.build_call_frame(name, fn, arg_count)
        stack = vm.stack
        if arg_count:
            args = stack[-arg_count:]
            del stack[-arg_count:]
        else:
            args = []
        for param, value in zip(fn.params, args):
            frame.locals[param] = value
        vm.frames.append(frame)
        self.depth += 1
        try:
            result = compiled(vm, *args)
        finally:
            self.depth -= 1
        vm.frames.pop()
        vm.record_vm_return(name, raw=True)
        stack.append(result)
        vm.ip = call_ip + 1
        return None


def call_interpreted(vm, name: str, fn, args: list):
    """Run `name` in the interpreter from inside compiled code, synchronously.

    Used past the depth cap, and if an observer attached during a compiled call.
    The callee is eligible, so nothing it reaches has a `try`: hiding
    `handler_stack` loses nothing, and stops an error inside from jumping to a
    `catch` outside this call. Its `RETURN` targets one past the end of the code,
    which ends the nested `execute()` with the result on the stack.
    """
    saved_ip = vm.ip
    saved_handlers = vm.handler_stack
    vm.handler_stack = []
    stack = vm.stack
    base = len(stack)
    stack.extend(args)
    frame = vm.build_call_frame(name, fn, len(args))
    frame.return_ip = len(vm.code)
    vm.frames.append(frame)
    vm.ip = fn.addr
    try:
        status, _ = vm.execute()
        if status != "halt" or len(stack) != base + 1:  # pragma: no cover - defensive
            vm.runtime_error("runtime", f"internal: {name} did not return normally (#173)")
        return stack.pop()
    finally:
        # On an error the frames stay for handle_exception to unwind, as the
        # interpreter leaves them.
        vm.handler_stack = saved_handlers
        vm.ip = saved_ip


def from_environment() -> CompileState | None:
    """The state `NODUS_COMPILE_FUNCTIONS` asks for, or None.

    `always` compiles every eligible function on its first call; any value the
    runtime already reads as true (`runtime_events._TRUTHY`) uses the default
    threshold; anything else leaves compilation off.
    """
    from nodus.runtime.runtime_events import _TRUTHY

    value = os.environ.get(ENV_VAR, "").strip().lower()
    if value == "always":
        return CompileState(threshold=0)
    if value in _TRUTHY:
        return CompileState()
    return None


def enable(vm, *, threshold: int | None = None, depth_cap: int | None = None) -> CompileState:
    """Switch compilation on for `vm`."""
    state = CompileState(threshold=threshold, depth_cap=depth_cap)
    vm._pycompile = state
    return state
