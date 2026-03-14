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
LOAD

Loads a variable from the current scope.

[] → [value]

Operation:

value = resolve_variable(name)
stack.push(value)
STORE

Stores the top stack value into a variable.

[value] → []

Operation:

value = stack.pop()
set_variable(name, value)
STORE_ARG

Stores a function argument into a local slot.

[arg] → []

Operation:

frame.locals[slot] = stack.pop()
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
ITER_NEXT

Retrieves the next value.

[iterator] → [value]

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

Final Principle

Instruction semantics must remain:

deterministic

well-defined

consistent across runtime implementations

If an opcode's behavior cannot be described clearly using stack transitions, its design should be reconsidered.