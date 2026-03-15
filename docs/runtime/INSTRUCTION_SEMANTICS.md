Nodus Instruction Semantics

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

⚠️ Deprecated since v0.8.0. The compiler now emits LOAD_LOCAL_IDX for all
local variable accesses inside functions. LOAD_LOCAL is retained as a
compatibility fallback only and will be removed at v1.0. See DEPRECATIONS.md.

[] → [value]

Operation:

value = frame.locals[name]  // direct dict lookup, no fallback probes
stack.push(value)

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

[collection] → [iterator]

Operation depends on the runtime type of *collection*:

- **List:** A `ListIterator` wrapping the list is pushed. ip advances normally.
- **Record with `__next__` field:** The record itself acts as a stateful iterator and
  is pushed as-is. ip advances normally. `ITER_NEXT` will call `__next__` on it.
- **Record with `__iter__` field (closure):** The `__iter__` closure must be called to
  obtain the iterator. Because closure calls redirect the instruction pointer through
  the full call/return cycle, GET_ITER cannot return the iterator synchronously.
  Instead:
  1. `pending_get_iter` is set to `True` on the VM.
  2. `call_closure(__iter__, receiver)` is invoked — ip now points inside the
     `__iter__` function body.
  3. `_NO_PENDING` is returned from the handler (ip is *not* advanced past GET_ITER).
  4. When the `__iter__` closure executes `RETURN`, the RETURN handler checks
     `pending_get_iter`, clears it, and converts the returned value to a
     `ListIterator` (if a list) or passes through the record (if it has `__next__`).
     The resulting iterator is pushed onto the stack and execution continues past
     the original GET_ITER site.

  This means GET_ITER with a closure `__iter__` spans at least one full call/return
  cycle before the iterator is available on the stack. The flag is saved and restored
  as part of coroutine context so a coroutine may be suspended between the GET_ITER
  dispatch and the RETURN post-processing.

⚠️ **Provisional:** the `pending_get_iter` mechanism is a known architectural smell
(two observably different code paths for the same opcode). The v0.9 decision deferred
cleanup to v1.0 — the mechanism works correctly and the architectural smell does not
affect observable behavior for correct programs. See `TECH_DEBT.md §
"GET_ITER pending_get_iter cleanup"` and `FREEZE_PROPOSAL.md § "v0.9 Opcode Decisions"`.

ITER_NEXT

Retrieves the next value from an iterator, or jumps to *end_ip* when exhausted.

Operand: end_ip (absolute) — address to jump to when the iterator is done.

[iterator] → [value]   (advances; ip += 1)
[iterator] →           (exhausted; iterator popped, ip = end_ip)

Operation depends on the runtime type of *iterator*:

- **`ListIterator`:** If `iterator.index >= len(iterator.values)`, pops the iterator
  and sets ip = end_ip. Otherwise pushes `iterator.values[iterator.index]`, increments
  `iterator.index`, and advances ip normally.
- **Record with `__next__` field (closure):** The `__next__` closure must be called to
  get the next value. Because closure calls redirect ip through the call/return cycle,
  ITER_NEXT cannot return the value synchronously. Instead:
  1. `pending_iter_next` is set to *end_ip* on the VM.
  2. `call_closure(__next__, receiver)` is invoked — ip now points inside `__next__`.
  3. `_NO_PENDING` is returned from the handler.
  4. When the `__next__` closure executes `RETURN`, the RETURN handler checks
     `pending_iter_next`, clears it, and inspects the returned value:
     - If the value is `None` (iterator signals exhaustion): pops the iterator from
       the stack and sets ip = end_ip.
     - Otherwise: pushes the value and advances ip past the ITER_NEXT site.

  `pending_iter_next` stores the end_ip so the RETURN handler can perform the
  exhaustion check without any additional operand. The flag is saved and restored as
  part of coroutine context.

⚠️ **Provisional:** shares the same architectural concern as GET_ITER regarding the
two-path closure mechanism. See GET_ITER notes above and `TECH_DEBT.md §
"GET_ITER pending_get_iter cleanup"`.

If iteration ends, the VM triggers loop termination behavior.

15. Exception Handling
SETUP_TRY

Registers an exception handler.

push exception frame
POP_TRY

Removes the exception handler.

THROW

Raises an exception.

Operation:

search call frames for handler
restore stack
jump to handler
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