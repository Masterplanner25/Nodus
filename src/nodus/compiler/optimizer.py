"""Bytecode optimizer for Nodus."""

from nodus.compiler.compiler import FunctionInfo


PURE_BINARY_OPS = {
    "ADD": lambda a, b: a + b,
    "SUB": lambda a, b: a - b,
    "MUL": lambda a, b: a * b,
    "DIV": lambda a, b: a / b,
    "EQ": lambda a, b: a == b,
    "NE": lambda a, b: a != b,
    "LT": lambda a, b: a < b,
    "GT": lambda a, b: a > b,
    "LE": lambda a, b: a <= b,
    "GE": lambda a, b: a >= b,
}

PURE_UNARY_OPS = {
    "NEG": lambda value: -value,
    "NOT": lambda value: not value,
    "TO_BOOL": lambda value: bool(value),
}

TARGETED_OPS = {"JUMP", "JUMP_IF_FALSE", "JUMP_IF_TRUE", "ITER_NEXT", "SETUP_TRY"}
TERMINATORS = {"RETURN", "THROW", "HALT"}


def optimize_bytecode(
    code: list[tuple],
    functions: dict[str, FunctionInfo],
    code_locs: list[tuple[str | None, int | None, int | None]],
) -> tuple[list[tuple], dict[str, FunctionInfo], list[tuple[str | None, int | None, int | None]]]:
    changed = True
    current_code = list(code)
    current_locs = list(code_locs)
    current_functions = functions

    while changed:
        changed = False

        canonicalized, did_change = canonicalize_constants(current_code)
        if did_change:
            current_code = canonicalized
            changed = True

        folded_code, folded_functions, folded_locs, did_change = fold_constants(current_code, current_functions, current_locs)
        if did_change:
            current_code = folded_code
            current_functions = folded_functions
            current_locs = folded_locs
            changed = True

        stack_code, stack_functions, stack_locs, did_change = remove_useless_stack_ops(current_code, current_functions, current_locs)
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


def canonicalize_constants(code: list[tuple]) -> tuple[list[tuple], bool]:
    cache: dict[tuple[str, object], object] = {}
    out: list[tuple] = []
    changed = False
    for instr in code:
        if instr[0] != "PUSH_CONST":
            out.append(instr)
            continue
        value = instr[1]
        if not isinstance(value, (str, int, float, bool, type(None))):
            out.append(instr)
            continue
        key = (type(value).__name__, value)
        cached = cache.setdefault(key, value)
        if cached is not value:
            changed = True
        out.append(("PUSH_CONST", cached))
    return out, changed


def fold_constants(
    code: list[tuple],
    functions: dict[str, FunctionInfo],
    code_locs: list[tuple[str | None, int | None, int | None]],
) -> tuple[list[tuple], dict[str, FunctionInfo], list[tuple[str | None, int | None, int | None]], bool]:
    targets = collect_jump_targets(code)
    out_code: list[tuple] = []
    out_locs: list[tuple[str | None, int | None, int | None]] = []
    mapping: dict[int, int] = {}
    changed = False
    i = 0
    while i < len(code):
        if i + 1 < len(code) and i + 1 not in targets and code[i][0] == "PUSH_CONST" and code[i + 1][0] in PURE_UNARY_OPS:
            op = code[i + 1][0]
            try:
                value = PURE_UNARY_OPS[op](code[i][1])
            except Exception:
                pass
            else:
                mapping[i] = len(out_code)
                out_code.append(("PUSH_CONST", value))
                out_locs.append(code_locs[i + 1])
                changed = True
                i += 2
                continue

        if (
            i + 2 < len(code)
            and i + 1 not in targets
            and i + 2 not in targets
            and code[i][0] == "PUSH_CONST"
            and code[i + 1][0] == "PUSH_CONST"
            and code[i + 2][0] in PURE_BINARY_OPS
        ):
            op = code[i + 2][0]
            try:
                value = PURE_BINARY_OPS[op](code[i][1], code[i + 1][1])
            except Exception:
                pass
            else:
                mapping[i] = len(out_code)
                out_code.append(("PUSH_CONST", value))
                out_locs.append(code_locs[i + 2])
                changed = True
                i += 3
                continue

        mapping[i] = len(out_code)
        out_code.append(code[i])
        out_locs.append(code_locs[i])
        i += 1

    remapped_code, remapped_functions, remapped_locs = remap_compacted(out_code, functions, out_locs, mapping)
    if not changed:
        if remapped_code != code or remapped_locs != code_locs or function_addrs(remapped_functions) != function_addrs(functions):
            changed = True
    return remapped_code, remapped_functions, remapped_locs, changed


def remove_useless_stack_ops(
    code: list[tuple],
    functions: dict[str, FunctionInfo],
    code_locs: list[tuple[str | None, int | None, int | None]],
) -> tuple[list[tuple], dict[str, FunctionInfo], list[tuple[str | None, int | None, int | None]], bool]:
    targets = collect_jump_targets(code)
    out_code: list[tuple] = []
    out_locs: list[tuple[str | None, int | None, int | None]] = []
    mapping: dict[int, int] = {}
    changed = False
    i = 0
    while i < len(code):
        if i + 1 < len(code) and i + 1 not in targets and code[i][0] == "PUSH_CONST" and code[i + 1][0] == "POP":
            i += 2
            changed = True
            continue
        mapping[i] = len(out_code)
        out_code.append(code[i])
        out_locs.append(code_locs[i])
        i += 1
    remapped_code, remapped_functions, remapped_locs = remap_compacted(out_code, functions, out_locs, mapping)
    if not changed:
        if remapped_code != code or remapped_locs != code_locs or function_addrs(remapped_functions) != function_addrs(functions):
            changed = True
    return remapped_code, remapped_functions, remapped_locs, changed


def simplify_jumps(code: list[tuple]) -> tuple[list[tuple], bool]:
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
        if op in {"JUMP", "JUMP_IF_FALSE", "JUMP_IF_TRUE", "ITER_NEXT", "SETUP_TRY"}:
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
    code_locs: list[tuple[str | None, int | None, int | None]],
) -> tuple[list[tuple], dict[str, FunctionInfo], list[tuple[str | None, int | None, int | None]], bool]:
    reachable = compute_reachable(code, functions)
    mapping: dict[int, int] = {}
    new_code: list[tuple] = []
    new_locs: list[tuple[str | None, int | None, int | None]] = []
    for old_index, instr in enumerate(code):
        if old_index not in reachable:
            continue
        mapping[old_index] = len(new_code)
        new_code.append(instr)
        new_locs.append(code_locs[old_index])

    remapped_code = [remap_instruction(instr, mapping) for instr in new_code]
    remapped_functions = {
        name: FunctionInfo(info.name, list(info.params), mapping[info.addr], list(info.upvalues), info.display_name)
        for name, info in functions.items()
        if info.addr in mapping
    }
    changed = remapped_code != code or new_locs != code_locs or function_addrs(remapped_functions) != function_addrs(functions)
    return remapped_code, remapped_functions, new_locs, changed


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
        instr = code[ip]
        op = instr[0]
        for target in next_ips(ip, instr, len(code)):
            if target not in reachable:
                worklist.append(target)
        if op in TERMINATORS:
            continue

    return reachable


def next_ips(ip: int, instr: tuple, code_len: int) -> list[int]:
    op = instr[0]
    if op == "JUMP":
        return [instr[1]]
    if op in {"JUMP_IF_FALSE", "JUMP_IF_TRUE", "ITER_NEXT", "SETUP_TRY"}:
        out = [instr[1]]
        if ip + 1 < code_len:
            out.append(ip + 1)
        return out
    if op in TERMINATORS:
        return []
    if ip + 1 < code_len:
        return [ip + 1]
    return []


def remap_instruction(instr: tuple, mapping: dict[int, int]) -> tuple:
    op = instr[0]
    if op in TARGETED_OPS:
        return (op, mapping[instr[1]], *instr[2:])
    return instr


def function_addrs(functions: dict[str, FunctionInfo]) -> dict[str, int]:
    return {name: info.addr for name, info in functions.items()}


def collect_jump_targets(code: list[tuple]) -> set[int]:
    targets: set[int] = set()
    for instr in code:
        if instr[0] in TARGETED_OPS:
            targets.add(instr[1])
    return targets


def remap_compacted(
    code: list[tuple],
    functions: dict[str, FunctionInfo],
    code_locs: list[tuple[str | None, int | None, int | None]],
    mapping: dict[int, int],
) -> tuple[list[tuple], dict[str, FunctionInfo], list[tuple[str | None, int | None, int | None]]]:
    remapped_code = [remap_instruction(instr, mapping) for instr in code]
    remapped_functions = {
        name: FunctionInfo(info.name, list(info.params), mapping[info.addr], list(info.upvalues), info.display_name)
        for name, info in functions.items()
        if info.addr in mapping
    }
    return remapped_code, remapped_functions, code_locs
