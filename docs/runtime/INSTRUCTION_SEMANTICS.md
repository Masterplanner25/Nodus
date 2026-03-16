Nodus Instruction Semantics

> The opcode semantics in this document are frozen at v1.0 (2026-03-15).
> All 47 active opcodes are stable. See docs/governance/FREEZE_PROPOSAL.md
> for the freeze declaration and post-freeze extension process.

This document defines the precise behavior of each Nodus bytecode instruction.

While BYTECODE.md describes the instruction set, this document specifies how each instruction transforms the runtime state.

The goal is to provide an unambiguous reference for:

VM implementation

compiler correctness

debugging

tooling

future optimizations

1. Runtime State Model

At any point during execution, the VM state consists of:

Instruction Pointer (IP)
Value Stack
Call Frame Stack
Global Environment
Closure Environments
Constant Table

Each instruction may modify one or more of these components.

Note: Opcode dispatch uses a dict-based table (_dispatch) built at VM
construction time by _build_dispatch_table(). This is O(1) per instruction
rather than O(n) for the previous if/elif chain. Each opcode is handled by
a dedicated _op_XXX method on the VM class.

2. Stack Notation

Instruction semantics are described using stack transition notation.

Format:

(before) → (after)

Example:

[a, b] → [a + b]

This means the instruction pops a and b and pushes their sum.

The rightmost element represents the top of the stack.

3. Stack Operations
PUSH_CONST

Pushes a constant value from the constant table.

[] → [value]

Operation:

stack.push(constants[index])
POP

Removes the top value from the stack.

[value] → []

Operation:

stack.pop()
4. Variable Access
FRAME_SIZE

Pre-allocates the frame's slot-indexed locals array. Emitted as the first
instruction of every compiled function body. Must appear before any
LOAD_LOCAL_IDX or STORE_LOCAL_IDX in the same function.

[] → []  (no stack change)

Operand: n (int) — total number of local variable slots in this frame.

Operation:

frame.locals_array = [None] * n

LOAD_LOCAL_IDX

Fast-path slot-indexed local variable read. Emitted for all function-scope
locals where Symbol.index is set (the normal case since v0.8.0).

[] → [value]

Operand: slot (int) — index into frame.locals_array.

Operation:

value = frame.locals_array[slot]
if isinstance(value, Cell): value = value.value
if isinstance(value, LiveBinding): value = value.get()
stack.push(value)

STORE_LOCAL_IDX

Slot-indexed local variable write. Handles Cell boxing in-place for correct
closure capture semantics.

[value] → []

Operand: slot (int) — index into frame.locals_array.

Operation:

value = stack.pop()
existing = frame.locals_array[slot]
if isinstance(existing, Cell):
    existing.value = value  // update in-place (captured closures see the new value)
else:
    frame.locals_array[slot] = value

LOAD

Loads a variable from the current scope (global or module-level lookup).
Probes four sources in order: frame locals, module globals, functions dict, host globals.
Use LOAD_LOCAL_IDX inside functions — LOAD is reserved for global/outer scope access.

[] → [value]

Operation:

value = resolve_variable(name)
stack.push(value)

LOAD_LOCAL

⛔ Removed in v1.0. The compiler emits LOAD_LOCAL_IDX for all local variable
accesses inside functions. LOAD_LOCAL is no longer in the VM dispatch table;
executing it raises a RuntimeError tombstone directing the user to recompile.
See DEPRECATIONS.md.

(No stack semantics — opcode is a tombstone.)

STORE

Stores the top stack value into a variable.

[value] → []

Operation:

value = stack.pop()
set_variable(name, value)
STORE_ARG

Stores a function argument into a local slot. Also syncs to locals_array
via locals_name_to_slot when the frame has a slot-indexed array.

[arg] → []

Operation:

slot = pop()
frame.locals[slot] = stack.pop()
if frame.locals_name_to_slot:
    frame.locals_array[frame.locals_name_to_slot[slot]] = frame.locals[slot]
5. Arithmetic Instructions

All arithmetic operations follow the same pattern.

Operands are popped from the stack and the result is pushed.

ADD
[a, b] → [a + b]

Operation:

b = stack.pop()
a = stack.pop()
stack.push(a + b)
SUB
[a, b] → [a - b]
MUL
[a, b] → [a * b]
DIV
[a, b] → [a / b]
NEG

Unary negation.

[a] → [-a]
6. Comparison Operations

Comparison instructions evaluate relational expressions.

EQ
[a, b] → [a == b]
NE
[a, b] → [a != b]
LT
[a, b] → [a < b]
GT
[a, b] → [a > b]
LE
[a, b] → [a <= b]
GE
[a, b] → [a >= b]
7. Boolean Operations
NOT
[a] → [not a]
TO_BOOL

Converts a value to boolean truthiness.

[a] → [bool(a)]
8. Control Flow

Control flow instructions modify the instruction pointer.

JUMP

Unconditional jump.

IP → target

Operation:

ip = target
JUMP_IF_FALSE

Conditional jump.

[cond] → []

If cond is false:

ip = target

Otherwise execution continues.

JUMP_IF_TRUE
[cond] → []

If cond is true:

ip = target
HALT

Stops execution.

Operation:

terminate VM
9. Function Calls
CALL

Invokes a named function.

Stack transition:

[arg1, arg2, ..., argN] → [result]

Operation:

create new call frame
assign arguments to parameters
execute function body
push return value
CALL_VALUE

Calls a function object stored on the stack.

[func, arg1, arg2] → [result]
CALL_METHOD

Invokes a method on an object.

[obj, arg1, arg2] → [result]
10. Closures
MAKE_CLOSURE

Creates a closure object.

[] → [closure]

Captured variables become upvalues stored in the closure environment.

LOAD_UPVALUE

Loads a captured variable.

[] → [value]
STORE_UPVALUE

Stores a captured variable.

[value] → []
11. Function Return
RETURN

Returns from the current function.

Stack transition:

[result] → []

Operation:

pop current frame
push result to caller stack
12. Coroutine Semantics
YIELD

Suspends execution.

[value] → []

Operation:

store coroutine state
return control to scheduler

Execution resumes later at the same instruction pointer.

13. Collection Operations
BUILD_LIST

Creates a list from stack values.

[a, b, c] → [[a, b, c]]
BUILD_MAP

Creates a dictionary from key/value pairs.

[k1, v1, k2, v2] → [{k1: v1, k2: v2}]
BUILD_RECORD

Creates a structured record object.

INDEX

Accesses an indexed value.

[obj, index] → [value]
INDEX_SET

Updates an indexed value.

[obj, index, value] → []
LOAD_FIELD

Loads a field from a record.

[obj] → [value]
STORE_FIELD

Stores a record field.

[obj, value] → []
14. Iteration Semantics
GET_ITER

Creates an iterator from a collection.

[collection] → [Iterator]

Produces a first-class `Iterator` object (defined in `vm.py`) and pushes it. The
`Iterator` wraps an `advance_fn: () → (value, exhausted)` closure and exposes a
single `advance()` method consumed by `ITER_NEXT`. All paths are synchronous — ip
advances normally in every case.

Operation depends on the runtime type of *collection*:

- **List:** A `ListIterator` (index-based cursor) is wrapped in an `Iterator` whose
  `advance_fn` reads the next element or signals exhaustion.
- **Record with `__iter__` field:** `run_closure(__iter__, receiver)` is called
  synchronously (saves/restores full execution context). The return value is then
  handled as one of the two cases below.
- **Record with `__next__` field (directly iterable):** An `Iterator` is constructed
  whose `advance_fn` calls `run_closure(__next__, record)` on each advance. If
  `__next__` returns `None`, the iterator is considered exhausted.

`run_closure()` executes the closure via a nested `execute()` call, so `__iter__` and
`__next__` are resolved completely before GET_ITER/ITER_NEXT return. The `Iterator`
object is a plain stack value — it is saved and restored as part of coroutine context
automatically. A coroutine may be suspended between any two ITER_NEXT calls with no
special handling.

**Stable** as of v1.0: the `pending_get_iter` / `pending_iter_next` flag mechanism
was replaced by the `Iterator` protocol object in v1.0. See `TECH_DEBT.md §
"GET_ITER pending_get_iter cleanup"` and `FREEZE_PROPOSAL.md § "v1.0 GET_ITER/ITER_NEXT Decision"`.

ITER_NEXT

Retrieves the next value from an iterator, or jumps to *end_ip* when exhausted.

Operand: end_ip (absolute) — address to jump to when the iterator is done.

[Iterator] → [value]   (advances; ip += 1)
[Iterator] →           (exhausted; Iterator popped, ip = end_ip)

Calls `iterator.advance()`, which returns `(value, exhausted)`:

- If exhausted: pops the `Iterator` from the stack and sets ip = end_ip.
- Otherwise: pushes *value* and advances ip normally (ip += 1).

The `Iterator` object remains on the stack between calls, preserving iterator state
across coroutine suspend/resume cycles with no additional bookkeeping.

**Stable** as of v1.0: see GET_ITER notes above.

If iteration ends, the VM triggers loop termination behavior.

15. Exception Handling
SETUP_TRY

Registers an exception handler and optional finally block. Pushes a 4-tuple
(handler_ip, finally_ip, stack_depth, frame_depth) onto the handler stack.
When finally_ip is 0, no finally block is registered.

SETUP_TRY <handler_ip>
SETUP_TRY <handler_ip> <finally_ip>

push exception frame (4-tuple)

**stable** as of v1.0 freeze.

POP_TRY

Removes the exception handler. If the popped entry has a non-zero finally_ip,
redirects execution to the finally block rather than advancing ip by 1.

pop exception frame → if finally_ip != 0: jump to finally_ip; else ip += 1

**stable** as of v1.0 freeze.

FINALLY_END

Signals the end of a finally block. Two behaviors:

- If a deferred return is pending (_deferred_return is set): pop the current
  frame and complete the return with the deferred value.
- Otherwise: ip += 1 (normal continuation after finally).

**stable** as of v1.0.

THROW

Raises a Nodus-level exception with the value on top of the stack.

Non-string thrown values are preserved as structured payload:
  err.kind = "thrown"
  err.payload = <original value>
String thrown values become err.message directly.

Operation:

search call frames for handler
restore stack
jump to handler

**stable** as of v1.0 freeze.
16. Module Construction
BUILD_MODULE

Creates a module record containing exported values.

[k1, v1, k2, v2, ..., kN, vN] → [module_record]

Operation:

pairs = pop count (key, value) pairs in reverse order
module_record = Record(fields, kind="module")
stack.push(module_record)

Keys must be strings. The resulting Record has kind="module", which activates
module-export semantics in LOAD_FIELD and CALL_METHOD (i.e. only exported names
are accessible; missing exports raise a "key" error rather than a generic field
error). This opcode is emitted by the module loader pipeline to construct the
runtime module value; it is not emitted directly from user-authored Nodus source.

Final Principle

Instruction semantics must remain:

deterministic

well-defined

consistent across runtime implementations

If an opcode's behavior cannot be described clearly using stack transitions, its design should be reconsidered.