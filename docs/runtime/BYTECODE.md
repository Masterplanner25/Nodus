Nodus Bytecode Specification

This document defines the bytecode instruction set used by the Nodus virtual machine.

Bytecode serves as the intermediate representation between the compiler and the runtime VM. The compiler emits bytecode instructions which are executed sequentially by the virtual machine.

This specification exists to ensure consistent behavior between:

the compiler

the VM

debugging tools

disassemblers

future optimizers

1. Bytecode Overview

Nodus bytecode is currently represented as a sequence of instruction tuples.

Each instruction contains:

(opcode, operand1, operand2, ...)

Example instruction stream:

PUSH_CONST 1
PUSH_CONST 2
ADD
RETURN

The VM executes these instructions using a stack-based execution model.

2. Instruction Categories

The instruction set is divided into logical groups.

3. Stack Operations

These instructions manipulate the VM value stack.

PUSH_CONST

Pushes a constant value onto the stack.

PUSH_CONST <const_index>

Example:

PUSH_CONST 5

Pushes the constant value at index 5 in the constant table.

POP

Removes the top value from the stack.

POP
4. Variable Access

These instructions load and store variables.

LOAD

Loads a variable value and pushes it onto the stack.

LOAD <name>
STORE

Stores the top stack value into a variable.

STORE <name>
STORE_ARG

Stores function arguments in local variable slots.

STORE_ARG <slot>
LOAD_UPVALUE

Loads a captured variable from a closure.

LOAD_UPVALUE <index>
STORE_UPVALUE

Stores a value into a closure variable.

STORE_UPVALUE <index>
5. Arithmetic and Logical Operations

These instructions operate on values from the stack.

Each operation pops its operands and pushes the result.

ADD
a b → (a + b)
SUB
a b → (a - b)
MUL
a b → (a * b)
DIV
a b → (a / b)
Comparison Instructions
EQ
NE
LT
GT
LE
GE

Each instruction compares two values and pushes a boolean result.

Boolean Operations
NOT
TO_BOOL
Numeric Negation
NEG
6. Control Flow

Control flow instructions modify the instruction pointer.

JUMP

Unconditional jump.

JUMP <target>
JUMP_IF_FALSE

Jump if the top stack value evaluates to false.

JUMP_IF_FALSE <target>
JUMP_IF_TRUE

Jump if the top stack value evaluates to true.

JUMP_IF_TRUE <target>
HALT

Stops VM execution.

HALT
7. Iteration

Iteration instructions support looping constructs.

GET_ITER

Converts a value into an iterator.

GET_ITER
ITER_NEXT

Advances an iterator.

ITER_NEXT

Pushes the next value or signals iteration completion.

8. Exception Handling

Exception support allows structured error handling.

SETUP_TRY

Registers an exception handler.

SETUP_TRY <handler_ip>
POP_TRY

Removes the current exception handler.

POP_TRY
THROW

Raises an exception.

THROW
9. Function Calls and Closures

These instructions manage function execution.

CALL

Calls a named function.

CALL <function> <arg_count>
CALL_VALUE

Calls a function value on the stack.

CALL_VALUE <arg_count>
CALL_METHOD

Calls an object method.

CALL_METHOD <method> <arg_count>
MAKE_CLOSURE

Creates a closure object.

MAKE_CLOSURE <function>

Captured variables become upvalues.

RETURN

Returns from the current function.

RETURN

The top stack value becomes the return value.

YIELD

Suspends execution for coroutine scheduling.

YIELD
10. Collections and Records

These instructions construct and manipulate structured data.

BUILD_LIST

Creates a list.

BUILD_LIST <count>

Consumes count stack values.

BUILD_MAP

Creates a map (dictionary).

BUILD_MAP <count>
BUILD_RECORD

Creates a structured record.

BUILD_RECORD <count>
BUILD_MODULE

Creates a module object.

BUILD_MODULE
INDEX

Accesses an indexed element.

INDEX
INDEX_SET

Sets an indexed element.

INDEX_SET
LOAD_FIELD

Loads a record field.

LOAD_FIELD <name>
STORE_FIELD

Stores a record field value.

STORE_FIELD <name>
11. Constant Table

Compiled programs contain a constant table storing values referenced by instructions.

Examples include:

numbers
strings
function objects
module objects

Instructions such as PUSH_CONST reference this table by index.

12. Bytecode Versioning

Bytecode format is not yet versioned.

Future versions of Nodus may introduce bytecode version identifiers to ensure compatibility between:

compiler

VM

tooling

13. Tooling Support

The bytecode format is used by several developer tools:

disassembler (nodus dis)

debugger

runtime trace system

static analysis tools

Maintaining a stable instruction set helps ensure these tools remain compatible.

14. Future Bytecode Evolution

Possible future improvements include:

bytecode version headers

improved instruction encoding

register-based optimization passes

specialized opcodes for common operations

These changes should preserve compatibility where possible.

Final Principle

The bytecode format should remain:

simple

inspectable

stable enough for tooling

Complex optimizations should not compromise clarity of the instruction model.