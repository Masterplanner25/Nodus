# Opcode execution census (#412 Phase 1)

`nodus_gate --opcodes` verifies the **inventory** — that the docs and the VM
dispatch table name the same 49 opcodes. It says nothing about whether any of
them does what it is documented to do, and the three most severe VM bugs of the
v5 cycle (#361, #370, #371) were opcode-semantics defects on paths nothing
exercised.

    PYTHONPATH="C:/dev/Coding Language/src" python -m tools.opcode_census

Wraps every dispatch entry, runs the suite, and reports executions per opcode to
stdout and `.opcode-census.json`. It measures **executions**, not appearances in
compiled code — an opcode that is emitted but never reached is exactly the case
worth finding, and a static scan would miss it.

## Baseline, 2026-08-29 (suite green, 2,898 tests)

    49 declared · 48 executed · 895,076 total executions

    PUSH_CONST       184,997      most-executed
    LOAD_LOCAL_IDX   140,683
    JUMP_IF_FALSE     91,562
    ...
    JUMP_IF_TRUE           2      least-executed of those that run
    NOT                    2
    STORE_UPVALUE          2
    TO_BOOL                2

    NEVER EXECUTED (1):   BUILD_MODULE

**`BUILD_MODULE` is not merely untested — it is not emitted.** Its one emit site
is `compiler.py`'s `ModuleAlias` case, and `ModuleAlias` is built only by
`tooling/loader.py`, which `runtime/module_loader.py` superseded. See
`BYTECODE_REFERENCE.md §3` for the checks behind that.

## The 16 opcodes under 100 executions

These are the risk register for #412 phases 2–3, and the ordering the issue asks
for — the control-flow and frame-state opcodes are where every VM bug of this
cycle lived:

    2   JUMP_IF_TRUE, NOT, STORE_UPVALUE, TO_BOOL
    6   DIV
    14  STORE_FIELD
    18  POP_TRY
    21  NEG
    22  GET_ITER
    26  GE
    29  MUL
    30  MOD
    60  FINALLY_END
    64  CALL_VALUE
    67  GT
    85  NE

`POP_TRY` at 18 and `FINALLY_END` at 60 are worth the most attention: those two
plus `SETUP_TRY` (109) are the exception-unwind path where #361, #370 and #371
all lived, and 18 executions across the whole suite is not a exercised path.

**A low count is not itself a defect.** `MUL` at 29 means test programs rarely
multiply, not that multiplication is broken. The number tells you where a
semantic bug could hide undetected, which is what phases 2–3 are for.
