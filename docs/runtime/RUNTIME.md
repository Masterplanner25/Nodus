Nodus Runtime Specification

This document describes the internal runtime model of Nodus.

While other documents describe language design and architecture, this file defines the execution behavior of the virtual machine, including:

memory model

stack layout

calling conventions

object representations

runtime value handling

This information is particularly important for:

debugging the VM

implementing new opcodes

extending the runtime

future FFI integrations

1. Runtime Overview

The Nodus runtime is a stack-based virtual machine implemented in Python.

Programs are compiled into bytecode and executed by the VM.

Execution state includes:

value stack
call frames
globals table
closure environments
builtin registry

The runtime executes instructions sequentially unless control-flow instructions modify the instruction pointer.

2. Memory Model

Nodus currently relies on Python’s memory management for object allocation and garbage collection.

All runtime values are Python objects wrapped by Nodus runtime abstractions.

Examples include:

numbers

strings

lists

maps

records

function objects

module records

Because Python manages memory automatically, Nodus does not implement a custom garbage collector.

However, runtime structures are designed so that a future custom memory system could replace Python-managed objects if necessary.

3. Runtime Values

Runtime values are defined in:

runtime_values.py

The value system provides representations for:

numbers
booleans
strings
lists
maps
records
functions
modules
iterators

Values are dynamically typed.

The VM performs runtime checks when executing instructions that require specific value types.

4. Value Stack

The value stack is the central execution structure of the VM.

The stack stores intermediate values produced by instructions.

Example operations:

PUSH_CONST
POP
CALL
RETURN
ADD

Example stack evolution:

Initial stack: []

PUSH_CONST 2
Stack: [2]

PUSH_CONST 3
Stack: [2, 3]

ADD
Stack: [5]

The stack grows and shrinks as instructions execute.

5. Call Frames

Function execution is tracked using call frames.

Each frame contains:

instruction pointer
local variable storage
closure references
return address

When a function is called:

a new frame is created

arguments are assigned to local slots

execution begins at the function’s entry instruction

When a function returns:

the frame is removed

the return value is pushed onto the previous stack

6. Calling Convention

Nodus uses a stack-based calling convention.

Example:

push argument1
push argument2
CALL function

The VM then:

pops the arguments

creates a new frame

assigns arguments to parameter slots

executes the function

The return value is pushed back onto the caller’s stack.

7. Closures and Upvalues

Closures allow functions to capture variables from outer scopes.

Captured variables are stored as upvalues.

Upvalues allow nested functions to reference values defined outside their local scope.

Example structure:

outer function
   variable x
       ↓
inner function captures x

The VM supports this behavior through instructions such as:

LOAD_UPVALUE
STORE_UPVALUE
MAKE_CLOSURE

This mechanism ensures that captured variables remain accessible even after the outer function returns.

8. Object Model

Nodus uses a dynamic object model.

Runtime values represent different object types.

Examples include:

string
list
map
record
module
function

Records represent structured objects with named fields.

Example:

user = {name: "Alice", age: 30}

Field access is implemented using:

LOAD_FIELD
STORE_FIELD

This model keeps object semantics simple while supporting structured data.

9. String Representation

Strings are immutable runtime values.

They are represented internally as Python strings.

Operations such as concatenation and slicing create new string values.

This design simplifies memory management and avoids mutation-related bugs.

10. Lists and Arrays

Lists are ordered collections.

Internally they map to Python list objects.

Example list operations:

BUILD_LIST
INDEX
INDEX_SET

Lists support:

indexing

iteration

mutation

Because they rely on Python lists, resizing and memory allocation are handled automatically.

11. Maps and Records

Maps are key-value dictionaries.

Internally they map to Python dictionary objects.

Example instructions:

BUILD_MAP
INDEX
INDEX_SET

Records are structured objects implemented as dictionaries with field-style access.

Example:

record = {x: 10, y: 20}

Records support:

named fields

field lookup

field mutation

12. Iterators

Iteration is supported through the iterator protocol.

Relevant instructions:

GET_ITER
ITER_NEXT

`GET_ITER` produces a first-class `Iterator` object (added in v1.0) wrapping an
`advance_fn: () → (value, exhausted)` callable. All GET_ITER paths (list, `__iter__`
closure, `__next__` closure) resolve synchronously via `run_closure()`. `ITER_NEXT`
calls `iterator.advance()` and either pushes the next value or jumps to the end
target on exhaustion.

Lists and records with `__iter__`/`__next__` are iterable. The `pending_get_iter`
and `pending_iter_next` VM flags were removed in v1.0 when the first-class `Iterator`
class replaced the deferred-flag mechanism.

13. Exception Handling

Exception support is implemented through a handler stack.

Instructions include:

SETUP_TRY
POP_TRY
FINALLY_END
THROW

`SETUP_TRY handler_ip [finally_ip]` pushes a 4-tuple
`(handler_ip, finally_ip, stack_depth, frame_depth)` onto `handler_stack`.
When `finally_ip` is non-zero, `POP_TRY` on normal try exit redirects execution
to the finally block instead of advancing ip.

`FINALLY_END` marks the end of a finally block. If a deferred return is pending
(set by `RETURN` executing while a finally-bearing handler is active), it completes
the return. Otherwise it advances ip.

`THROW` pops an error value. Non-string values are preserved as `err.payload` with
`err.kind="thrown"`. Strings become `err.message` directly.

When an exception occurs:

the VM searches for the nearest handler on `handler_stack`

control jumps to `handler_ip`; the stack is restored to `stack_depth`

the error record is pushed for the catch variable binding

finally blocks run on all exit paths (normal, caught exception, return)

14. Module Objects

Modules currently exist as compile-time constructs.

During compilation:

imported modules are flattened

exported names are mapped into global scope

The VM does not currently load modules dynamically.

Future versions may introduce runtime module objects.

15. Scheduler and Coroutines

Nodus includes runtime support for asynchronous execution.

Relevant modules:

coroutine.py
scheduler.py
channel.py

These components support:

cooperative scheduling

message passing

asynchronous workflows

Coroutines may yield control using the YIELD instruction.

Channel waiting queues (`waiting_receivers`, `waiting_senders`) use `collections.deque` for O(1) enqueue and dequeue. Prior list-based `pop(0)` was O(n).

The scheduler resumes suspended coroutines when work becomes available.

16. Event System

Runtime execution events are emitted through:

runtime_events.py

Events may include:

function call
task execution
workflow transition
error

Host systems may subscribe to these events for monitoring or debugging.

16a. Optimizer Constant Folding Semantics

The optimizer folds constant arithmetic expressions (PUSH_CONST + PUSH_CONST + ADD etc.)
at compile time.

Boolean normalization: because Python's bool subclasses int, expressions such as
`true + 1` would fold to a Python bool-arithmetic result.  To keep optimizer output
consistent with VM numeric semantics, the optimizer converts bool operands to int
before applying arithmetic folds (ADD, SUB, MUL, DIV, NEG).  Comparison and logical
operations (EQ, NE, LT, GT, LE, GE, NOT, TO_BOOL) retain their Python bool results
unchanged, since those are the correct Nodus boolean values.

Optimizer fixed-point loop: `collect_jump_targets()` is called once per outer
fixed-point iteration and the result is passed to both `fold_constants()` and
`remove_useless_stack_ops()` rather than being recomputed inside each function.
If `fold_constants` compacts code (changes addresses), `jump_targets` is recomputed
before `remove_useless_stack_ops` runs to ensure correctness. The dirty flag is a
boolean set to True whenever any instruction is transformed; the former O(n) list
equality fallback check has been removed.

17. Future Runtime Evolution

Potential runtime improvements include:

runtime module objects (currently compile-time flattening)

optional custom memory manager

improved scheduler isolation

optimized bytecode execution

structured event sinks for host embedding

These changes should preserve the existing runtime semantics wherever possible.

Note: Bytecode versioning is complete as of v1.0 (`BYTECODE_VERSION = 4`, frozen).
The embedding API is stable (`NodusRuntime` in `nodus.__all__`).

Final Principle

The Nodus runtime is designed to remain predictable and inspectable.

While performance improvements may occur over time, the system should remain easy to reason about for contributors and users.