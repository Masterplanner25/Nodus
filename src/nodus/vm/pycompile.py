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
- every call is to a builtin in `COMPILABLE_BUILTINS` (one that never
  suspends: five no-authority categories, plus every capability-bearing builtin
  outside `MAY_SUSPEND_BUILTINS`) or to another eligible function in the same
  chunk, with the right arity.

So compiled code never suspends, and never calls an interpreted function except
past the depth cap (`call_interpreted`).
"""

from __future__ import annotations

import os
import sys
import threading
from collections import OrderedDict
from dataclasses import dataclass, field

from nodus.runtime.capability import BUILTIN_CAPABILITIES, MAY_SUSPEND_BUILTINS, NO_AUTHORITY_BUILTINS
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
#: Phase 2 adds every capability-bearing builtin that cannot suspend: the
#: synchronous `http`, `subprocess`, file, environment, memory, tool, agent and
#: `syscall` builtins. Compiled code calls them through `VM.invoke_builtin`, the
#: same capability check, approval and rebuild-effect handling the interpreter
#: uses, so a denial in compiled code is the same denial at the same location.
COMPILABLE_BUILTINS = frozenset(
    name for category in COMPILABLE_BUILTIN_CATEGORIES
    for name in NO_AUTHORITY_BUILTINS[category]
) | (frozenset(BUILTIN_CAPABILITIES) - MAY_SUSPEND_BUILTINS)

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
    "EQ": -1, "NE": -1, "ADD": -1, "SUB": -1, "MUL": -1, "NEG": 0, "LT": -1,
    # Inline for two non-zero ints; anything else runs the VM's own handler.
    "DIV": -1, "MOD": -1, "GT": -1, "LE": -1, "GE": -1,
    "INDEX": -1, "JUMP_IF_FALSE": -1, "JUMP_IF_TRUE": -1, "RETURN": -1,
    # phase 3 (#173): closures
    "MAKE_CLOSURE": 1, "LOAD_UPVALUE": 1, "STORE_UPVALUE": -1,
}
SUPPORTED = (frozenset(_INLINE_EFFECT) | frozenset(_DELEGATED)
             | {"CALL", "ITER_NEXT", "CALL_VALUE", "CALL_METHOD"})
#: Calls whose target is only known at run time: they make a function dynamic.
DYNAMIC_CALLS = frozenset({"CALL_VALUE", "CALL_METHOD"})
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
    if op == "CALL_VALUE":
        return -instr[1]  # the callee and its arguments, replaced by the result
    if op == "CALL_METHOD":
        return -instr[2]  # the receiver and its arguments, replaced by the result
    if op == "ITER_NEXT":
        return 1  # the fall-through edge; the exit edge is handled in _stack_depths
    raise Ineligible(f"opcode {op}")


# --- eligibility --------------------------------------------------------------

def reachable(code: list, start: int) -> set:
    """The instructions control can reach from `start`, following jumps,
    branches and iterator exits, and stopping at RETURN, THROW and HALT.

    A function's body is this set, not an address range: a closure's body is
    compiled inline in its parent, behind a JUMP over it, so the parent's range
    contains code that is not the parent's, and the closure's own body ends at
    its RETURN, in the middle of the parent.
    """
    seen: set = set()
    work = [start]
    while work:
        i = work.pop()
        if i in seen or not (0 <= i < len(code)):
            continue
        seen.add(i)
        instr = code[i]
        op = instr[0]
        if op in ("RETURN", "THROW", "HALT"):
            continue
        if op == "JUMP":
            work.append(instr[1])
            continue
        pos = JUMP_TARGET.get(op)
        if pos is not None and isinstance(instr[pos], int):
            work.append(instr[pos])
        work.append(i + 1)
    return seen


def function_bodies(code: list, functions: dict) -> dict:
    """name -> (start, end): the span from a function's entry to the last
    instruction it can reach. Only the reachable instructions in it are the
    function's own; see `reachable`."""
    out = {}
    for name, fn in functions.items():
        own = reachable(code, fn.addr)
        out[name] = (fn.addr, (max(own) + 1) if own else fn.addr)
    return out


def eligible_functions(code: list, functions: dict, builtins: dict) -> dict:
    """name -> reason it is ineligible, or None if eligible."""
    return analyze(code, functions, builtins)[0]


def analyze(code: list, functions: dict, builtins: dict) -> tuple[dict, set]:
    """(reasons, dynamic) for every function in the chunk.

    `reasons` maps a name to why it stays interpreted, or None if it is
    eligible: a greatest fixed point, starting from every function that passes
    the local checks and dropping any that calls one no longer in the set.

    `dynamic` holds the eligible functions that can reach a `CALL_VALUE` or a
    `CALL_METHOD` (`DYNAMIC_CALLS`), whose target is only known at run time and
    may be anything, including code that would suspend. They run compiled only
    outside a coroutine, where nothing can suspend: `sleep`, `recv` and `yield`
    refuse there with their own errors (phase 3).
    """
    bodies = function_bodies(code, functions)
    reasons: dict = {}
    calls: dict = {}
    dynamic: set = set()
    for name, fn in functions.items():
        start, end = bodies[name]
        try:
            if getattr(fn, "step_owner", None) is not None:
                raise Ineligible("a workflow step body")
            if not (0 <= start < end <= len(code)):
                raise Ineligible("no body in this chunk")
            callees = set()
            for i in sorted(reachable(code, start)):
                instr = code[i]
                op = instr[0]
                if op not in SUPPORTED:
                    raise Ineligible(f"opcode {op}")
                if op in DYNAMIC_CALLS:
                    dynamic.add(name)
                elif op == "MAKE_CLOSURE":
                    target = functions.get(instr[1])
                    if target is None:
                        raise Ineligible(f"closure of unknown function {instr[1]}")
                    for upvalue in target.upvalues:
                        if upvalue.is_local and upvalue.index is None:
                            raise Ineligible("a capture without a slot")
                        if not upvalue.is_local and not (
                                isinstance(upvalue.index, int) and upvalue.index < len(fn.upvalues)):
                            raise Ineligible("a capture of an upvalue this function lacks")
                elif op in ("LOAD_UPVALUE", "STORE_UPVALUE"):
                    if not (isinstance(instr[1], int) and instr[1] < len(fn.upvalues)):
                        raise Ineligible("an upvalue out of range")
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
    # A function that calls a dynamic one is dynamic too.
    changed = True
    while changed:
        changed = False
        for name, callees in calls.items():
            if name not in dynamic and callees & dynamic:
                dynamic.add(name)
                changed = True
    return reasons, {name for name in dynamic if reasons.get(name) is None}


def cell_slots(code: list, start: int, end: int, functions: dict) -> frozenset:
    """The local slots a closure made in this body captures: the only ones that
    can hold a `Cell`, so the only ones that need Cell-aware code."""
    out = set()
    for i in reachable(code, start):
        if code[i][0] == "MAKE_CLOSURE":
            for upvalue in functions[code[i][1]].upvalues:
                if upvalue.is_local:
                    out.add(upvalue.index)
    return frozenset(out)


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

def generate(name: str, fn, code: list, start: int, end: int, py_name: str,
             functions: dict | None = None, dynamic: frozenset = frozenset()) -> str:
    """Python source for one eligible function. `up` is the closure's upvalue
    list, or None for a named function. A call to a function in `dynamic` is
    not inlined (see `_emit_user_call`)."""
    functions = functions or {}
    cells = cell_slots(code, start, end, functions) if functions else frozenset()
    depth = _stack_depths(code, start, end)
    all_leaders = _leaders(code, start, end)
    leaders = [b for b in all_leaders if b in depth]
    first = code[start]
    nslots = first[1] if first[0] in ("ENTER", "FRAME_SIZE") else 0
    params = list(fn.params)
    out = [f"def {py_name}(vm, up{''.join(', a' + str(k) for k in range(len(params)))}):"]
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
        # The block ends at the next block start of any kind. Taking it from the
        # reachable starts only would stretch a block over unreachable code after
        # it (a nested closure's body, or `--no-opt`'s epilogue after a return)
        # and count instructions that never run.
        later = [b for b in all_leaders if b > b0]
        b1 = later[0] if later else end
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
            ended = _emit(out, ind, instr, i, d, cells, functions, dynamic)
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


def _local(slot: int, cells: frozenset) -> str:
    """An expression for local `slot`'s value: unwrapped when it may be a Cell."""
    if slot in cells:
        return f"(l{slot}.value if type(l{slot}) is Cell else l{slot})"
    return f"l{slot}"


def _emit_user_call(out: list, ind: str, addr: int, d: int, callee: str, params: list) -> None:
    """A call from compiled code to an eligible user function, inline.

    The same steps as `CompileState._user_call`, which stays the slow path, in
    the same order: count the call, build the frame (through the site's
    `VM.call_frame_maker`, the same frame `build_call_frame` makes, so stack
    traces and the frame limit are the interpreter's), run the compiled callee,
    pop, count the return. What
    inlining removes is the helper's own call, the argument list, the `zip`, and
    the `record_vm_call` / `record_vm_return` calls when nothing is listening;
    the counters they keep are kept here.

    The fast path needs the callee already compiled and the same conditions as
    `CompileState.may_run`. Otherwise the helper decides: it compiles the
    callee, or runs it interpreted past the depth cap or under an observer.
    """
    argc = len(params)
    s = lambda k: f"s{k}"  # noqa: E731
    args = [s(k) for k in range(d - argc, d)]
    out.append(f"{ind}f = COMPILED.get({callee!r})")
    out.append(f"{ind}if (f is not None and ST.depth < ST.depth_cap and vm.task_step_budget is None"
               f" and not vm._instrumented()):")
    i2 = ind + "    "
    out.append(f"{i2}if vm.event_bus.wants('vm_call'): vm.record_vm_call({callee!r}, 'call', raw=True)")
    out.append(f"{i2}else: vm.function_calls += 1")
    params_dict = "{" + ", ".join(f"{p!r}: {a}" for p, a in zip(params, args)) + "}"
    out.append(f"{i2}vm.frames.append(MK{addr}(len(vm.stack), {params_dict}))")
    out.append(f"{i2}ST.depth += 1")
    out.append(f"{i2}try: {s(d - argc)} = f(vm, None{''.join(', ' + a for a in args)})")
    out.append(f"{i2}finally: ST.depth -= 1")
    out.append(f"{i2}vm.frames.pop()")
    out.append(f"{i2}if vm.event_bus.wants('vm_return'): vm.record_vm_return({callee!r}, raw=True)")
    out.append(f"{i2}else: vm.returns += 1")
    out.append(f"{ind}else:")
    out.append(f"{i2}{s(d - argc)} = CALLS[{addr}](vm, [{', '.join(args)}])")


def _emit_value_call(out: list, ind: str, d: int, argc: int) -> None:
    """A call through a value from compiled code, inline when it can be.

    The fast path is `CompileState._value_call`'s, which stays the slow path, in
    the same order: a closure over this chunk's own, already compiled function,
    under the conditions of `CompileState.allowed`, is counted, gets its frame
    from `VM.build_closure_frame` (so the arity check, the #394 step-entry
    guard and the frame limit are the interpreter's, in one copy), and runs
    compiled. Anything else -- a module function, a builtin, another chunk's
    closure, one not compiled yet, or a call under an observer -- goes through
    the helper, which hands what it cannot run to the VM's own handler.
    """
    s = lambda k: f"s{k}"  # noqa: E731
    args = [s(k) for k in range(d - argc, d)]
    target = s(d - argc - 1)
    i2 = ind + "    "
    out.append(f"{ind}cv = {target}")
    out.append(f"{ind}if type(cv) is Closure:")
    out.append(f"{i2}fn = cv.function")
    out.append(f"{i2}f = COMPILED.get(fn.name)")
    out.append(f"{ind}else: f = None")
    out.append(f"{ind}if (f is not None and vm.functions.get(fn.name) is fn and ST.depth < ST.depth_cap"
               f" and vm.task_step_budget is None and not vm._instrumented()"
               f" and (fn.name not in DYN or vm.current_coroutine is None)):")
    out.append(f"{i2}if vm.event_bus.wants('vm_call'): vm.record_vm_call(fn.display_name, 'call_value')")
    out.append(f"{i2}else: vm.function_calls += 1")
    out.append(f"{i2}fr = vm.build_closure_frame(cv, {argc}, args_on_stack=False)")
    if argc:
        out.append(f"{i2}p = fn.params")
        out.append(f"{i2}lc = fr.locals")
        for k, a in enumerate(args):
            out.append(f"{i2}lc[p[{k}]] = {a}")
    out.append(f"{i2}vm.frames.append(fr)")
    out.append(f"{i2}ST.depth += 1")
    out.append(f"{i2}try: {target} = f(vm, cv.upvalues{''.join(', ' + a for a in args)})")
    out.append(f"{i2}finally: ST.depth -= 1")
    out.append(f"{i2}vm.frames.pop()")
    out.append(f"{i2}if vm.event_bus.wants('vm_return'): vm.record_vm_return(fn.name, raw=True)")
    out.append(f"{i2}else: vm.returns += 1")
    out.append(f"{ind}else:")
    out.append(f"{i2}{target} = CALL_VALUE(vm, cv, [{', '.join(args)}])")


def _emit(out: list, ind: str, instr: tuple, addr: int, d: int,
          cells: frozenset = frozenset(), functions: dict | None = None,
          dynamic: frozenset = frozenset()) -> bool:
    """Append the code for one instruction; True if it ends the block."""
    op = instr[0]
    s = lambda k: f"s{k}"  # noqa: E731
    at = f"{ind}vm.ip = h = {addr}"
    functions = functions or {}

    def truthy(c: str) -> str:
        return f"({c} is True or ({c} is not False and {c} is not None and vm.is_truthy({c})))"

    if op == "RESET_LOCAL_IDX" and instr[1] in cells:
        # Detach the Cell, so the next capture makes a fresh one (per-iteration
        # binding), exactly as the interpreter's handler does.
        out.append(f"{ind}l{instr[1]} = None")
        return False
    if op in ("ENTER", "FRAME_SIZE", "RESET_LOCAL_IDX", "POP"):
        # Locals are Python locals, and a slot no closure captures never holds
        # a Cell, so these have nothing to do; POP's operand is not used again.
        return False
    if op == "PUSH_CONST":
        out.append(f"{ind}{s(d)} = CONSTS[{addr}]")
    elif op == "LOAD_LOCAL_IDX":
        out.append(f"{ind}{s(d)} = {_local(instr[1], cells)}")
    elif op == "STORE_LOCAL_IDX":
        slot = instr[1]
        if slot in cells:
            out.append(f"{ind}if type(l{slot}) is Cell: l{slot}.value = {s(d - 1)}")
            out.append(f"{ind}else: l{slot} = {s(d - 1)}")
        else:
            out.append(f"{ind}l{slot} = {s(d - 1)}")
    elif op == "LOAD_UPVALUE":
        out.append(f"{ind}{s(d)} = up[{instr[1]}].value")
    elif op == "STORE_UPVALUE":
        out.append(f"{ind}up[{instr[1]}].value = {s(d - 1)}")
    elif op == "MAKE_CLOSURE":
        # VM._op_make_closure and capture_local: reuse a slot's Cell, or box its
        # value in a new one and record it in the frame's locals dict too.
        captured = []
        for upvalue in functions[instr[1]].upvalues:
            if upvalue.is_local:
                slot = upvalue.index
                out.append(f"{ind}if type(l{slot}) is not Cell:")
                out.append(f"{ind}    l{slot} = Cell(l{slot})")
                out.append(f"{ind}    vm.frames[-1].locals[{upvalue.name!r}] = l{slot}")
                captured.append(f"l{slot}")
            else:
                captured.append(f"up[{upvalue.index}]")
        out.append(f"{ind}{s(d)} = Closure(vm.functions[{instr[1]!r}], [{', '.join(captured)}])")
    elif op == "CALL_VALUE":
        out.append(at)
        _emit_value_call(out, ind, d, instr[1])
    elif op == "CALL_METHOD":
        # The VM's own handler decides everything: a module export, a module
        # function, a record's builtin method or closure (`call_handler_interpreted`).
        argc = instr[2]
        args = ", ".join(s(k) for k in range(d - argc, d))
        out.append(at)
        out.append(f"{ind}{s(d - argc - 1)} = CALL_METHOD(vm, INSTRS[{addr}], [{s(d - argc - 1)}, {args}])")
    elif op == "LOAD":
        out.append(at)
        out.append(f"{ind}{s(d)} = vm.load_name({instr[1]!r})")
    elif op == "STORE":
        out.append(at)
        out.append(f"{ind}vm.store_name({instr[1]!r}, {s(d - 1)})")
    elif op == "LOAD_LOCAL_FIELD":
        out.append(at)
        out.append(f"{ind}o = {_local(instr[1], cells)}")
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
    elif op in ("ADD", "SUB", "MUL"):
        # `VM._op_add`, `_op_sub` and `_op_mul` are exactly this.
        a, b = s(d - 2), s(d - 1)
        pyop, word = {"ADD": ("+", "add"), "SUB": ("-", "subtract"), "MUL": ("*", "multiply")}[op]
        out.append(at)
        out.append(f"{ind}try: {a} = {a} {pyop} {b}")
        out.append(f"{ind}except TypeError: vm._binary_type_error({word!r}, {a}, {b})")
    elif op == "NEG":
        # `VM._op_neg`.
        v = s(d - 1)
        out.append(at)
        out.append(f"{ind}try: {v} = -{v}")
        out.append(f"{ind}except TypeError: vm._unary_type_error('negate', {v})")
    elif op in ("DIV", "MOD"):
        # `VM._op_div` / `_op_mod` for their commonest case, two ints (not
        # bools) and a non-zero divisor: floor division and Python's `%`. Every
        # other case -- a float, a zero, a type error -- runs the handler, so
        # its float rules and its error messages keep one copy.
        a, b = s(d - 2), s(d - 1)
        pyop = "//" if op == "DIV" else "%"
        out.append(at)
        out.append(f"{ind}if type({a}) is int and type({b}) is int and {b}: {a} = {a} {pyop} {b}")
        out.append(f"{ind}else: {a} = delegate(vm, INSTRS[{addr}], [{a}, {b}])")
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
        callee = instr[1]
        if callee in functions and callee not in dynamic:
            _emit_user_call(out, ind, addr, d, callee, list(functions[callee].params))
        elif callee in functions:
            # A dynamic callee, whose compiled form may only run outside a
            # coroutine: the helper checks that.
            out.append(f"{ind}{s(d - argc)} = CALLS[{addr}](vm, [{args}])")
        else:
            # A builtin. `BI{addr}` is bound per VM by `plain_builtin`: the
            # function itself when the call can skip `invoke_builtin`, else None.
            out.append(f"{ind}b = BI{addr}")
            out.append(f"{ind}if b is not None and vm.profiler is None:")
            out.append(f"{ind}    if vm.event_bus.wants('vm_call'): vm.record_vm_call({callee!r}, 'call', raw=True)")
            out.append(f"{ind}    else: vm.function_calls += 1")
            out.append(f"{ind}    r = b({args})")
            out.append(f"{ind}    {s(d - argc)} = vm._augment_stdlib_err(r) "
                       f"if isinstance(r, Record) and r.kind == 'error' else r")
            out.append(f"{ind}else:")
            out.append(f"{ind}    {s(d - argc)} = CALLS[{addr}](vm, [{args}])")
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
        v = "lv"
        out.append(f"{ind}lv = {_local(instr[1], cells)}")
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


def plain_builtin(vm, name: str, argc: int):
    """The function behind builtin `name`, if a call with `argc` arguments can
    skip `VM.invoke_builtin` and `make_builtin_call`; otherwise None.

    It can when the call carries no authority (not in `BUILTIN_CAPABILITIES`,
    so there is no capability check or rebuild-effect report to make), cannot
    suspend (not in `MAY_SUSPEND_BUILTINS`), and has the right number of
    arguments, which is fixed at the call site. Everything else the slow path
    does, the inline code does too: count the call, emit its event if one is
    wanted, and turn an error record into the interpreter's. With a profiler
    present it takes the slow path, which reports the call to it.
    """
    builtin = vm.builtins.get(name)
    if builtin is None or name in BUILTIN_CAPABILITIES or name in MAY_SUSPEND_BUILTINS:
        return None
    expected = builtin.arity
    if (argc not in expected) if isinstance(expected, tuple) else (argc != expected):
        return None  # the slow path raises the interpreter's arity error
    return builtin.fn


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


# --- the code cache ---------------------------------------------------------------

#: Generated code, shared across VMs in the process, keyed by the function's
#: exact bytecode. Python's `compile()` is about 85% of the cost of compiling a
#: function (96 ms of 113 for the frontend's 75), and an embedder running a
#: program many times builds a new VM, and so a new CompileState, each time:
#: without this, the self-hosted check's 190 short runs parsed slower compiled
#: than interpreted on CI (3.4 s against 2.5 s). Generation is deterministic, so
#: equal bytecode means equal code; each VM binds its own namespace with `exec`,
#: about 2.5 microseconds a function. Bounded, oldest out first.
_CODE_CACHE: "OrderedDict[tuple, tuple]" = OrderedDict()
_CODE_CACHE_LIMIT = 4096
_CODE_CACHE_LOCK = threading.Lock()


def _cached_code(name: str, fn, code: list, start: int, end: int, py_name: str,
                 functions: dict | None = None, dynamic: frozenset = frozenset()) -> tuple:
    """(source, code object) for one function, from the cache when possible."""
    functions = functions or {}
    try:
        # What a MAKE_CLOSURE captures shapes the generated code, and it lives
        # on the target FunctionInfo, not in this body's instructions.
        captures = tuple(
            (code[i][1], tuple((u.name, u.is_local, u.index) for u in functions[code[i][1]].upvalues))
            for i in range(start, end) if code[i][0] == "MAKE_CLOSURE" and code[i][1] in functions)
        # An inlined call spells out its callee's parameter names, and a
        # dynamic callee is not inlined: both shape the code.
        callees = tuple(
            (code[i][1], tuple(functions[code[i][1]].params), code[i][1] in dynamic)
            for i in range(start, end) if code[i][0] == "CALL" and code[i][1] in functions)
        key = (name, start, end, tuple(code[start:end]), captures, callees)
        hash(key)
    except TypeError:  # an unhashable constant: compile without caching
        key = None
    if key is not None:
        with _CODE_CACHE_LOCK:
            hit = _CODE_CACHE.get(key)
            if hit is not None:
                _CODE_CACHE.move_to_end(key)
                return hit
    source = generate(name, fn, code, start, end, py_name, functions, dynamic)
    entry = (source, compile(source, f"<nodus compiled {name}>", "exec"))
    if key is not None:
        with _CODE_CACHE_LOCK:
            _CODE_CACHE[key] = entry
            while len(_CODE_CACHE) > _CODE_CACHE_LIMIT:
                _CODE_CACHE.popitem(last=False)
    return entry


# --- per-VM state ---------------------------------------------------------------

@dataclass
class _Chunk:
    code: list
    reasons: dict
    loops: set = field(default_factory=set)
    dynamic: set = field(default_factory=set)
    # Calls so far, per function, toward the threshold. Per chunk: one state is
    # shared by a VM and the child VMs that run its imported modules, and two
    # modules can each have a `peek`.
    calls: dict = field(default_factory=dict)
    compiled: dict = field(default_factory=dict)
    sources: dict = field(default_factory=dict)


def functions_with_loops(code: list, functions: dict) -> set:
    """Names of the functions whose body has a backward jump: a loop."""
    out = set()
    for name, (start, end) in function_bodies(code, functions).items():
        for i in sorted(reachable(code, start)):
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
        self._chunks: dict = {}
        self.compiled_count = 0

    # The chunk is the VM's current code list; analysis is per chunk.
    def _chunk(self, vm) -> _Chunk:
        key = id(vm.code)
        chunk = self._chunks.get(key)
        if chunk is None or chunk.code is not vm.code:
            reasons, dynamic = analyze(vm.code, vm.functions, vm.builtins)
            chunk = _Chunk(vm.code, reasons, functions_with_loops(vm.code, vm.functions), dynamic)
            self._chunks[key] = chunk
        return chunk

    def may_run(self, vm) -> bool:
        return (self.depth < self.depth_cap
                and vm.task_step_budget is None
                and not vm._instrumented())

    def allowed(self, vm, chunk: _Chunk, name: str) -> bool:
        """Whether `name`, compiled, may run now. A dynamic function (one that can
        reach a CALL_VALUE) only outside a coroutine, where nothing suspends."""
        return self.may_run(vm) and (name not in chunk.dynamic or vm.current_coroutine is None)

    def target(self, vm, name: str, fn):
        """The compiled function to run for this call, or None for the interpreter."""
        chunk = self._chunk(vm)
        compiled = chunk.compiled.get(name)
        if compiled is None:
            if chunk.reasons.get(name) is not None:
                return None
            n = chunk.calls.get(name, 0) + 1
            chunk.calls[name] = n
            if n < self.threshold and name not in chunk.loops:
                return None
            compiled = self._compile(vm, chunk, name)
        if not self.allowed(vm, chunk, name):
            return None
        return compiled

    def target_closure(self, vm, callee):
        """The compiled function for a call to local closure `callee`, or None."""
        fn = callee.function
        if vm.functions.get(fn.name) is not fn:
            return None  # another chunk's closure: the interpreter knows its context
        return self.target(vm, fn.name, fn)

    def run_entry(self, vm, closure, frame, args: list):
        """Run `closure` compiled as the entry of `VM.run_closure`, or return
        `_NOT_COMPILED` for the interpreter.

        `run_closure` starts a module function's call (each one runs on a child
        VM), a builtin's callback and the iterator protocol. It jumps straight to
        `fn.addr`, past the `CALL` hook, so without this the function a module
        call enters always ran interpreted, however hot: the self-hosted lexer's
        whole `tokenize` loop did. `frame` is already pushed; the interpreter's
        `RETURN` would record the return, so this does too.
        """
        fn = closure.function
        if len(args) != len(fn.params):
            return _NOT_COMPILED  # the interpreter decides what a mismatch means
        compiled = self.target_closure(vm, closure)
        if compiled is None:
            return _NOT_COMPILED
        for param, value in zip(fn.params, args):
            frame.locals[param] = value
        self.depth += 1
        try:
            result = compiled(vm, closure.upvalues, *args)
        finally:
            self.depth -= 1
        vm.frames.pop()
        vm.record_vm_return(fn.name, raw=True)
        return result

    def invoke_closure(self, vm, compiled, callee, args: list):
        """`CALL_VALUE` from the interpreter to a compiled closure. The handler
        has already recorded the call."""
        call_ip = vm.ip
        fn = callee.function
        frame = vm.build_closure_frame(callee, len(args), args_on_stack=False)
        for param, value in zip(fn.params, args):
            frame.locals[param] = value
        vm.frames.append(frame)
        self.depth += 1
        try:
            result = compiled(vm, callee.upvalues, *args)
        finally:
            self.depth -= 1
        vm.frames.pop()
        vm.record_vm_return(fn.name, raw=True)
        vm.stack.append(result)
        vm.ip = call_ip + 1
        return None

    def _compile(self, vm, chunk: _Chunk, name: str):
        """Compile `name` and, on demand, everything it calls."""
        if name in chunk.compiled:
            return chunk.compiled[name]
        bodies = function_bodies(chunk.code, vm.functions)
        start, end = bodies[name]
        fn = vm.functions[name]
        py_name = "nd_" + "".join(ch if ch.isalnum() else "_" for ch in name)
        source, code_object = _cached_code(name, fn, chunk.code, start, end, py_name, vm.functions,
                                           frozenset(chunk.dynamic))
        from nodus.vm.types import Cell, Closure
        from nodus.vm.vm import Iterator  # here, not at import: vm.py imports this module

        calls: dict = {}
        namespace = {
            "Record": Record, "Iterator": Iterator, "count": count, "delegate": delegate,
            "Cell": Cell, "Closure": Closure, "CALL_VALUE": self._value_call(vm, chunk),
            "CALL_METHOD": call_method_interpreted,
            "CONSTS": {i: chunk.code[i][1] for i in range(start, end)
                       if chunk.code[i][0] in ("PUSH_CONST",)} | {
                i: chunk.code[i][2] for i in range(start, end)
                if chunk.code[i][0] == "JUMP_IF_LOCAL_NE_CONST"},
            "INSTRS": {i: chunk.code[i] for i in range(start, end)},
            "CALLS": calls,
            "COMPILED": chunk.compiled, "ST": self, "DYN": chunk.dynamic,
        }
        for i in range(start, end):
            instr = chunk.code[i]
            if instr[0] != "CALL":
                continue
            if instr[1] in vm.functions:
                if instr[1] not in chunk.dynamic:
                    namespace[f"MK{i}"] = vm.call_frame_maker(instr[1], vm.functions[instr[1]], i)
            else:
                namespace[f"BI{i}"] = plain_builtin(vm, instr[1], instr[2])
        exec(code_object, namespace)  # noqa: S102
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
            if not state.allowed(vm, chunk, callee):
                return call_interpreted(vm, callee, fn, args)
            frame = vm.build_call_frame(callee, fn, 0)
            for param, value in zip(fn.params, args):
                frame.locals[param] = value
            vm.frames.append(frame)
            state.depth += 1
            try:
                result = compiled(vm, None, *args)
            finally:
                state.depth -= 1
            vm.frames.pop()
            vm.record_vm_return(callee, raw=True)
            return result
        return call

    def _value_call(self, vm, chunk: _Chunk):
        """`CALL_VALUE` from compiled code. A local closure whose function is
        eligible is called directly; anything else goes through the VM's own
        `CALL_VALUE` handler, synchronously (`call_value_interpreted`)."""
        state = self
        from nodus.vm.types import Closure

        def call(vm, callee, args):
            if type(callee) is Closure:
                fn = callee.function
                if (vm.functions.get(fn.name) is fn and chunk.reasons.get(fn.name) is None
                        and state.allowed(vm, chunk, fn.name)):
                    vm.record_vm_call(fn.display_name, "call_value")
                    compiled = chunk.compiled.get(fn.name) or state._compile(vm, chunk, fn.name)
                    frame = vm.build_closure_frame(callee, len(args), args_on_stack=False)
                    for param, value in zip(fn.params, args):
                        frame.locals[param] = value
                    vm.frames.append(frame)
                    state.depth += 1
                    try:
                        result = compiled(vm, callee.upvalues, *args)
                    finally:
                        state.depth -= 1
                    vm.frames.pop()
                    vm.record_vm_return(fn.name, raw=True)
                    return result
            return call_value_interpreted(vm, callee, args)
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
            result = compiled(vm, None, *args)
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


#: `CompileState.run_entry`'s answer when the interpreter should run the call.
_NOT_COMPILED = object()


def call_value_interpreted(vm, callee, args: list):
    """Call value `callee` through the VM's own `CALL_VALUE` handler, from
    compiled code, synchronously (`call_handler_interpreted`). The handler
    decides everything: a module function, a proxy for another VM's closure, a
    closure from another chunk, or a local one."""
    return call_handler_interpreted(vm, ("CALL_VALUE", len(args)), [callee, *args])


def call_method_interpreted(vm, instr: tuple, operands: list):
    """`CALL_METHOD` from compiled code: the receiver, then the arguments.
    The handler decides everything: a missing export or field, a module
    function (on a child VM, outside a coroutine), a record's builtin method or
    closure."""
    return call_handler_interpreted(vm, instr, operands)


def call_handler_interpreted(vm, instr: tuple, operands: list):
    """Run the VM's own handler for call `instr` (`CALL_VALUE` or
    `CALL_METHOD`) on `operands`, from compiled code, synchronously.

    The handler decides what is called. If it pushes a frame,
    that frame's return address becomes one past the end of the calling chunk,
    which ends a nested `execute()` once the call returns, after any module
    context the handler switched is restored. If it answers directly, the result
    is already on the stack.

    The calling function is dynamic, so it only runs compiled outside a
    coroutine, where nothing the callee does can suspend. `handler_stack` is
    hidden for the duration, so an error inside cannot jump to a `catch`
    outside this call; a `try` inside works on its own entries.
    """
    saved_ip = vm.ip
    saved_handlers = vm.handler_stack
    vm.handler_stack = []
    stack = vm.stack
    base = len(stack)
    frames_before = len(vm.frames)
    code_len = len(vm.code)
    stack.extend(operands)
    try:
        status = vm._dispatch[instr[0]](instr)
        if status is not None:  # pragma: no cover - cannot suspend outside a coroutine
            vm.runtime_error("runtime", "internal: a call suspended inside compiled code (#173)")
        if len(vm.frames) > frames_before:
            vm.frames[frames_before].return_ip = code_len
            status, _ = vm.execute()
            if status != "halt":  # pragma: no cover - defensive
                vm.runtime_error("runtime", "internal: a call did not return normally (#173)")
        if len(stack) != base + 1:  # pragma: no cover - defensive
            vm.runtime_error("runtime", "internal: a call left the stack unbalanced (#173)")
        return stack.pop()
    finally:
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
