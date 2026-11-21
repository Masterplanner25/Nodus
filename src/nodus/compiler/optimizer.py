"""Bytecode optimizer for Nodus.

`ModuleLoader._compile_module` runs this on every module it compiles, unless
the run asked for `--no-opt` / `optimize=False` or is being debugged (#964).
It was disconnected from v1.0 until #964 and drifted while nothing ran it, so
three rules now hold it to the VM:

- **A fold runs the VM's own handler** for the opcode, on a scratch VM. What a
  constant expression folds to is, by construction, what the VM would have
  computed; an expression the VM would reject is left for the VM to reject at
  run time, with its location.
- **Every `FunctionInfo` is rebuilt with `dataclasses.replace`**, so a field
  added later is carried without anyone naming it here. The old rebuilds named
  their fields and dropped `local_slots`, `param_types` and `return_type`.
- **Every address operand is remapped**: the jumps, `ITER_NEXT`, and both
  addresses of `SETUP_TRY` (its handler and its `finally`). A jump into code a
  pass removed lands on the next instruction kept.
"""

from __future__ import annotations

import dataclasses
import math
import threading
from typing import Any

from nodus.compiler.compiler import FunctionInfo

Locs = list[tuple[str | None, int | None, int | None]]

# Opcodes whose result depends only on their operands. Each is folded by
# running the VM's handler, never by reimplementing it here.
FOLDABLE_BINARY = {"ADD", "SUB", "MUL", "DIV", "MOD", "EQ", "NE", "LT", "GT", "LE", "GE"}
FOLDABLE_UNARY = {"NEG", "NOT", "TO_BOOL"}

# Constants a fold may consume or produce: immutable scalars. A folded list or
# map would be one object shared by every execution of the instruction.
_SCALARS = (bool, int, float, str, type(None))

TARGETED_OPS = {"JUMP", "JUMP_IF_FALSE", "JUMP_IF_TRUE", "ITER_NEXT", "SETUP_TRY"}
TERMINATORS = {"RETURN", "THROW", "HALT"}


def optimize_bytecode(
    code: list[tuple],
    functions: dict[str, FunctionInfo],
    code_locs: Locs,
) -> tuple[list[tuple], dict[str, FunctionInfo], Locs]:
    changed = True
    current_code = list(code)
    current_locs = list(code_locs)
    current_functions = functions

    while changed:
        changed = False
        jump_targets = collect_jump_targets(current_code)

        canonicalized, did_change = canonicalize_constants(current_code)
        if did_change:
            current_code = canonicalized
            changed = True

        folded_code, folded_functions, folded_locs, did_change = fold_constants(current_code, current_functions, current_locs, jump_targets)
        if did_change:
            current_code = folded_code
            current_functions = folded_functions
            current_locs = folded_locs
            changed = True
            jump_targets = collect_jump_targets(current_code)

        stack_code, stack_functions, stack_locs, did_change = remove_useless_stack_ops(current_code, current_functions, current_locs, jump_targets)
        if did_change:
            current_code = stack_code
            current_functions = stack_functions
            current_locs = stack_locs
            changed = True

        jump_code, did_change = simplify_jumps(current_code)
        if did_change:
            current_code = jump_code
            changed = True

        reachable_code, reachable_functions, reachable_locs, did_change = remove_unreachable(current_code, current_functions, current_locs)
        if did_change:
            current_code = reachable_code
            current_functions = reachable_functions
            current_locs = reachable_locs
            changed = True

    return current_code, current_functions, current_locs


def _constant_key(value: object) -> tuple[str, object]:
    # A float is keyed by its repr: 0.0 == -0.0, and merging them would lose
    # the sign that `1.0 / x` reports.
    if isinstance(value, float):
        return ("float", repr(value))
    return (type(value).__name__, value)


def canonicalize_constants(code: list[tuple]) -> tuple[list[tuple], bool]:
    cache: dict[tuple[str, object], object] = {}
    out: list[tuple] = []
    changed = False
    for instr in code:
        if instr[0] != "PUSH_CONST":
            out.append(instr)
            continue
        value = instr[1]
        if not isinstance(value, _SCALARS):
            out.append(instr)
            continue
        cached = cache.setdefault(_constant_key(value), value)
        if cached is not value:
            changed = True
        out.append(("PUSH_CONST", cached))
    return out, changed


# --- folding by the VM's own handlers ---------------------------------------

_scratch_lock = threading.Lock()
_scratch_vm: Any = None


def _evaluate(op: str, operands: list[object]) -> tuple[bool, object]:
    """(ok, value): run `op`'s VM handler on `operands`.

    One scratch VM per process, built on first use: a VM costs about 10 ms to
    construct, and most modules have nothing to fold. The lock makes it safe to
    compile on several threads.
    """
    global _scratch_vm
    from nodus.runtime.runtime_events import RuntimeEventBus
    from nodus.vm.vm import VM

    with _scratch_lock:
        if _scratch_vm is None:
            # Its event bus is off: a fold that raises would otherwise record
            # an event here for every module compiled in the process.
            _scratch_vm = VM([], {}, code_locs=[], source_path=None,
                             event_bus=RuntimeEventBus(enabled=False))
        vm = _scratch_vm
        vm.stack = list(operands)
        vm.ip = 0
        try:
            vm._dispatch[op]((op,))
        except Exception:
            return False, None
        finally:
            result_stack = vm.stack
            vm.stack = []
        if len(result_stack) != 1 or not isinstance(result_stack[0], _SCALARS):
            return False, None
        value = result_stack[0]
        if isinstance(value, float) and math.isnan(value):
            # NaN is not equal to itself, which canonicalize_constants and any
            # later comparison of instructions would trip over. Rare enough to
            # leave to run time.
            return False, None
        return True, value


def fold_constants(
    code: list[tuple],
    functions: dict[str, FunctionInfo],
    code_locs: Locs,
    jump_targets: set[int] | None = None,
) -> tuple[list[tuple], dict[str, FunctionInfo], Locs, bool]:
    targets = jump_targets if jump_targets is not None else collect_jump_targets(code)
    out_code: list[tuple] = []
    out_locs: Locs = []
    mapping: dict[int, int] = {}
    changed = False
    n = len(code)
    i = 0
    while i < n:
        instr = code[i]
        if instr[0] == "PUSH_CONST" and isinstance(instr[1], _SCALARS):
            if (i + 1 < n and i + 1 not in targets and code[i + 1][0] in FOLDABLE_UNARY):
                ok, value = _evaluate(code[i + 1][0], [instr[1]])
                if ok:
                    mapping[i] = len(out_code)
                    out_code.append(("PUSH_CONST", value))
                    out_locs.append(code_locs[i + 1])
                    changed = True
                    i += 2
                    continue
            if (
                i + 2 < n
                and i + 1 not in targets
                and i + 2 not in targets
                and code[i + 1][0] == "PUSH_CONST"
                and isinstance(code[i + 1][1], _SCALARS)
                and code[i + 2][0] in FOLDABLE_BINARY
            ):
                ok, value = _evaluate(code[i + 2][0], [instr[1], code[i + 1][1]])
                if ok:
                    mapping[i] = len(out_code)
                    out_code.append(("PUSH_CONST", value))
                    out_locs.append(code_locs[i + 2])
                    changed = True
                    i += 3
                    continue
        mapping[i] = len(out_code)
        out_code.append(instr)
        out_locs.append(code_locs[i])
        i += 1

    if not changed:
        return code, functions, code_locs, False
    remapped_code, remapped_functions, remapped_locs = remap_compacted(out_code, functions, out_locs, mapping, n)
    return remapped_code, remapped_functions, remapped_locs, True


# --- stack no-ops -------------------------------------------------------------

def _removable_after(code: list[tuple], i: int, targets: set[int]) -> int:
    """How many instructions from `i` on are a no-op that can go, or 0.

    - `PUSH_CONST v; POP`: a constant evaluated as a statement.
    - `LOAD_LOCAL_IDX n; POP` right after `STORE_LOCAL_IDX n`: an assignment
      statement, which compiles as an expression whose value is then dropped.
      Reading back the slot just written cannot fail or have an effect.

    No instruction after the first may be a jump target: a jump to the `POP`
    alone would pop something else.
    """
    n = len(code)
    if i + 1 >= n or i + 1 in targets or code[i + 1][0] != "POP":
        return 0
    op = code[i][0]
    if op == "PUSH_CONST":
        return 2
    if (op == "LOAD_LOCAL_IDX" and i > 0 and code[i - 1][0] == "STORE_LOCAL_IDX"
            and code[i - 1][1] == code[i][1] and i not in targets):
        return 2
    return 0


def remove_useless_stack_ops(
    code: list[tuple],
    functions: dict[str, FunctionInfo],
    code_locs: Locs,
    jump_targets: set[int] | None = None,
) -> tuple[list[tuple], dict[str, FunctionInfo], Locs, bool]:
    targets = jump_targets if jump_targets is not None else collect_jump_targets(code)
    out_code: list[tuple] = []
    out_locs: Locs = []
    mapping: dict[int, int] = {}
    changed = False
    i = 0
    while i < len(code):
        skip = _removable_after(code, i, targets)
        if skip:
            i += skip
            changed = True
            continue
        mapping[i] = len(out_code)
        out_code.append(code[i])
        out_locs.append(code_locs[i])
        i += 1
    if not changed:
        return code, functions, code_locs, False
    remapped_code, remapped_functions, remapped_locs = remap_compacted(out_code, functions, out_locs, mapping, len(code))
    return remapped_code, remapped_functions, remapped_locs, True


# --- jumps and reachability ---------------------------------------------------

def simplify_jumps(code: list[tuple]) -> tuple[list[tuple], bool]:
    """Point a jump at the end of a chain of unconditional jumps."""
    out = list(code)
    changed = False
    for i, instr in enumerate(out):
        op = instr[0]
        if op not in TARGETED_OPS:
            continue
        target = instr[1]
        final_target = resolve_jump_target(out, target)
        if final_target == target:
            continue
        out[i] = (op, final_target, *instr[2:])
        changed = True
    return out, changed


def resolve_jump_target(code: list[tuple], target: int) -> int:
    seen: set[int] = set()
    current = target
    while 0 <= current < len(code):
        if current in seen:
            break
        seen.add(current)
        instr = code[current]
        if instr[0] != "JUMP":
            break
        current = instr[1]
    return current


def remove_unreachable(
    code: list[tuple],
    functions: dict[str, FunctionInfo],
    code_locs: Locs,
) -> tuple[list[tuple], dict[str, FunctionInfo], Locs, bool]:
    reachable = compute_reachable(code, functions)
    if len(reachable) == len(code):
        return code, functions, code_locs, False
    mapping: dict[int, int] = {}
    new_code: list[tuple] = []
    new_locs: Locs = []
    for old_index, instr in enumerate(code):
        if old_index not in reachable:
            continue
        mapping[old_index] = len(new_code)
        new_code.append(instr)
        new_locs.append(code_locs[old_index])
    remapped_code, remapped_functions, remapped_locs = remap_compacted(new_code, functions, new_locs, mapping, len(code))
    return remapped_code, remapped_functions, remapped_locs, True


def compute_reachable(code: list[tuple], functions: dict[str, FunctionInfo]) -> set[int]:
    if not code:
        return set()
    roots = {0}
    roots.update(info.addr for info in functions.values())
    worklist = [root for root in roots if 0 <= root < len(code)]
    reachable: set[int] = set()
    while worklist:
        ip = worklist.pop()
        if ip in reachable:
            continue
        reachable.add(ip)
        for target in next_ips(ip, code[ip], len(code)):
            if target not in reachable:
                worklist.append(target)
    return reachable


def _addresses(instr: tuple) -> list[int]:
    """Every code address an instruction names."""
    op = instr[0]
    if op not in TARGETED_OPS:
        return []
    out = [instr[1]]
    # SETUP_TRY's second operand is its `finally` block; 0 or None means none.
    if op == "SETUP_TRY" and len(instr) > 2 and instr[2]:
        out.append(instr[2])
    return out


def next_ips(ip: int, instr: tuple, code_len: int) -> list[int]:
    op = instr[0]
    if op == "JUMP":
        return [instr[1]]
    if op in TERMINATORS:
        return []
    out = _addresses(instr)
    if ip + 1 < code_len:
        out.append(ip + 1)
    return out


def collect_jump_targets(code: list[tuple]) -> set[int]:
    targets: set[int] = set()
    for instr in code:
        targets.update(_addresses(instr))
    return targets


# --- remapping ----------------------------------------------------------------

def remap_instruction(instr: tuple, mapping: dict[int, int]) -> tuple:
    op = instr[0]
    if op not in TARGETED_OPS:
        return instr
    if op == "SETUP_TRY" and len(instr) > 2 and instr[2]:
        return (op, mapping[instr[1]], mapping[instr[2]], *instr[3:])
    return (op, mapping[instr[1]], *instr[2:])


def function_addrs(functions: dict[str, FunctionInfo]) -> dict[str, int]:
    return {name: info.addr for name, info in functions.items()}


def _complete_mapping(mapping: dict[int, int], old_len: int, new_len: int) -> dict[int, int]:
    """Give every removed address the address of the next instruction kept."""
    full = dict(mapping)
    full[old_len] = new_len  # a jump to the end of the code stays at the end
    following = new_len
    for old in range(old_len - 1, -1, -1):
        if old in full:
            following = full[old]
        else:
            full[old] = following
    return full


def remap_compacted(
    code: list[tuple],
    functions: dict[str, FunctionInfo],
    code_locs: Locs,
    mapping: dict[int, int],
    old_len: int | None = None,
) -> tuple[list[tuple], dict[str, FunctionInfo], Locs]:
    if old_len is not None:
        mapping = _complete_mapping(mapping, old_len, len(code))
    remapped_code = [remap_instruction(instr, mapping) for instr in code]
    # `replace` carries every field, including ones added after this was
    # written (#964: the field-by-field rebuild dropped local_slots,
    # param_types and return_type). `step_owner` (#394) rides along with them.
    remapped_functions = {
        name: dataclasses.replace(info, addr=mapping[info.addr])
        for name, info in functions.items()
        if info.addr in mapping
    }
    return remapped_code, remapped_functions, code_locs
