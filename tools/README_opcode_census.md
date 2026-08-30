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

## Phase 2 — `tests/test_opcode_semantics.py`

The ten opcodes #412 names have a written spec now, checked by executing one
instruction against a hand-built VM state: `SETUP_TRY`, `POP_TRY`,
`FINALLY_END`, `THROW`, `YIELD`, `MAKE_CLOSURE`, `FRAME_SIZE`,
`RESET_LOCAL_IDX`, `CALL_VALUE`, `CALL_METHOD`.

The shape is what matters. A program that happens to reach an opcode passes as
long as the *program's* output is right — which is how #370 survived — so the
pre-state is constructed rather than arrived at.

**Verified by mutation, not by passing.** Fourteen deliberate defects were
applied to `vm.py` one at a time; all fourteen turned the specs red, none
survived. A spec that cannot fail measures nothing, and the project has written
three such assertions before (CLAUDE.md records them).

Four disagreements between the handler and `BYTECODE_REFERENCE.md §3` were found
and the reference corrected:

- **`FINALLY_END`** documented one exit. It has three — deferred error (#361),
  deferred return, plain advance — and it consumes a finally-gate sentinel on
  two of them, in an order its own comment calls load-bearing.
- **`CALL_METHOD`** said "runtime error if not a record". A **module** is also a
  valid receiver. Strings are not: `"x".to_upper()` is a type error in Nodus.
- **`THROW`**'s `err.message` / `err.payload` describe the record a `catch`
  block receives, not the exception the opcode raises — which has no `message`
  attribute at all. And its "transfers control" happens in `execute()`'s except
  clause, one level up.
- **`CALL_VALUE`** transfers control rather than pushing a result, and refuses a
  bare Python callable.

**`nodus_gate --opcodes` now checks spec coverage as well as inventory**: every
opcode in the reference's `exceptions` category must be specified, and every
specified opcode must still be dispatched. The category is read from the
document, so re-categorising an opcode moves it into or out of coverage in the
same edit.

Phase 3 (stack-discipline verification against the compiler's assumptions) is
still open.
