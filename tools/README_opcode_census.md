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

## Phase 3 — `tests/test_stack_discipline.py`

Whether an opcode's behaviour matches what the compiler assumed when it sized
frames and patched jump targets. Two halves, split by what each can soundly
answer.

**Statically**, over every stdlib module: every jump target lands inside the
code, no target survived unpatched (`emit("JUMP", None)` without its `patch`),
every function body opens with `FRAME_SIZE`, and no slot or frame operand is
negative. That last one is the case the runtime does *not* catch — a read past
the end raises `IndexError`, but a negative index silently wraps to the far end
of the frame and returns another variable's value.

**At run time**, for frame sizing — and that split is a finding, not a
convenience. The obvious static check is to attribute each `*_LOCAL_IDX` to the
nearest preceding `FRAME_SIZE`. It does not work: a nested closure's body is
emitted *inside* its parent's code at a higher address, so instructions after
the closure get credited to it. That reports twelve violations in `async.nd`,
all false — `worker_pool` (FRAME_SIZE 6) legitimately uses slot 5, and the
closure at address 105 merely sits between. **A compiled function has no
recorded end**, so there is no sound span to attribute against. At run time the
question does not arise: the frame doing the access is the frame that was sized.

Both halves are shown to detect something rather than merely to pass. The
static checkers are run against synthetic broken input; the runtime check was
verified by under-sizing every frame by one slot, which turns all three of its
corpus tests red.

## Phase 4 — the register was only 3/16 covered

Phases 1–3 left the other 39 opcodes unspecified, deliberately: `ADD` and `POP`
are not where the bugs were, and the census is the ordering. Two things about
that ordering turned out to argue the other way.

**Of the sixteen opcodes under 100 executions above, only three got a spec** —
`POP_TRY`, `FINALLY_END` and `CALL_VALUE`. `JUMP_IF_TRUE`, `NOT`,
`STORE_UPVALUE` and `TO_BOOL` execute **twice** each across the whole suite.
"Simple" and "exercised" are different properties, and this file measures the
second one.

**And phase 2's find rate did not depend on complexity.** It corrected four
reference entries out of ten opcodes; phase 4 corrected more, in opcodes as
plain as `DIV` and `STORE_FIELD`. What drives the rate is the ratio of prose to
behaviour — a one-line entry describing a three-branch handler is the shape that
goes wrong, and the simple opcodes have the shortest entries.

So `tests/test_opcode_semantics_core.py` specifies all 39, and
`nodus_gate --opcodes` now requires a spec for **every dispatched opcode**
rather than for the `exceptions` category. Verified the way phase 2 was: 52
deliberate defects applied to `vm.py` one at a time, all 52 killed by the specs.
Two survived the first pass and both were real gaps — a `LOAD_UPVALUE` spec
using index 0 of a one-element list, where an off-by-one is indistinguishable,
and a `CALL` frame-cap spec that checked the error but not that the refused
frame was gone.
