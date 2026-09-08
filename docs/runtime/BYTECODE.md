# Nodus Bytecode Specification

**Last reviewed:** 2026-09-07, against 5.12.0

This document defines the bytecode instruction set used by the Nodus virtual machine.

Bytecode serves as the intermediate representation between the compiler and the runtime VM. The compiler emits bytecode instructions which are executed sequentially by the virtual machine.

This specification exists to ensure consistent behavior between:

- the compiler
- the VM
- debugging tools
- disassemblers
- future optimizers

## 1. Bytecode Overview

Nodus bytecode is currently represented as a sequence of instruction tuples.

Each instruction contains:

```
(opcode, operand1, operand2, ...)
```

Example instruction stream:

```
PUSH_CONST 1
PUSH_CONST 2
ADD
RETURN
```

The VM executes these instructions using a stack-based execution model.

## 2. Instruction Categories

The instruction set is divided into logical groups.

## 3. Stack Operations

These instructions manipulate the VM value stack.

### PUSH_CONST

Pushes a constant value onto the stack.

```
PUSH_CONST <const_index>
```

Example:

```
PUSH_CONST 5
```

Pushes the constant value at index 5 in the constant table.

### POP

Removes the top value from the stack.

```
POP
```

## 4. Variable Access

These instructions load and store variables.

### FRAME_SIZE

Pre-allocates the slot-indexed locals array for the current frame.
Emitted as the first instruction of every function body.

```
FRAME_SIZE <n>
```

where `n` is the total number of local variable slots. Sets `frame.locals_array = [None] * n`.

### LOAD

Loads a variable value and pushes it onto the stack (global/module scope).

```
LOAD <name>
```

### LOAD_LOCAL_IDX

Fast-path slot-indexed local variable read. Emitted by the compiler for all
confirmed function-local variables (`Symbol.index` is set). Bypasses all dict lookups.

```
LOAD_LOCAL_IDX <slot>
```

### LOAD_LOCAL

> ⛔ Removed in v1.0. `LOAD_LOCAL_IDX` is the canonical opcode for all local
> variable loads. The VM dispatch table no longer contains `LOAD_LOCAL`;
> executing this opcode raises a RuntimeError tombstone directing the user
> to recompile. `BYTECODE_VERSION` bumped to 3. See
> [`DEPRECATIONS.md`](../governance/DEPRECATIONS.md).

```
LOAD_LOCAL <name>
```

### STORE

Stores the top stack value into a variable.

```
STORE <name>
```

### STORE_LOCAL_IDX

Slot-indexed local variable write. Complement of `LOAD_LOCAL_IDX`.

```
STORE_LOCAL_IDX <slot>
```

### STORE_ARG

Stores function arguments into local slots. Also syncs to `locals_array` via `locals_name_to_slot`.

```
STORE_ARG <slot>
```

### RESET_LOCAL_IDX

Detaches any `Cell` at a local slot by writing a plain `None` over it, so the
next `MAKE_CLOSURE` boxes a fresh per-iteration `Cell`. Emitted at the start of
each `for`-loop iteration for the loop variable, and before each `let` binding
inside a loop body. No stack effect.

```
RESET_LOCAL_IDX <slot>
```

### LOAD_UPVALUE

Loads a captured variable from a closure.

```
LOAD_UPVALUE <index>
```

### STORE_UPVALUE

Stores a value into a closure variable.

```
STORE_UPVALUE <index>
```

## 5. Arithmetic and Logical Operations

These instructions operate on values from the stack.

Each operation pops its operands and pushes the result.

### ADD

```
a b → (a + b)
```

### SUB

```
a b → (a - b)
```

### MUL

```
a b → (a * b)
```

### DIV

```
a b → (a / b)
```

### MOD

```
a b → (a % b)
```

Remainder. Same three-branch shape as `DIV`, including the exclusion of `bool`
from the int path and two distinct zero errors (`Integer modulo by zero`,
`Float modulo by zero`). The sign follows the host, not C: `-7 % 3` is `2`.

### Comparison Instructions

```
EQ    a b → (a == b)
NE    a b → (a != b)
LT    a b → (a < b)
GT    a b → (a > b)
LE    a b → (a <= b)
GE    a b → (a >= b)
```

Each instruction compares two values and pushes a boolean result.

### Boolean Operations

```
NOT
TO_BOOL
```

### Numeric Negation

```
NEG
```

## 6. Control Flow

Control flow instructions modify the instruction pointer.

### JUMP

Unconditional jump.

```
JUMP <target>
```

### JUMP_IF_FALSE

Jump if the top stack value evaluates to false.

```
JUMP_IF_FALSE <target>
```

### JUMP_IF_TRUE

Jump if the top stack value evaluates to true.

```
JUMP_IF_TRUE <target>
```

### HALT

Stops VM execution.

```
HALT
```

## 7. Iteration

Iteration instructions support looping constructs.

### GET_ITER

Converts a value into an iterator.

```
GET_ITER
```

### ITER_NEXT

Advances an iterator.

```
ITER_NEXT
```

Pushes the next value or signals iteration completion.

## 8. Exception Handling

Exception support allows structured error handling.

### SETUP_TRY

Registers an exception handler, and optionally a finally block.

```
SETUP_TRY <handler_ip>
SETUP_TRY <handler_ip> <finally_ip>
```

When `finally_ip` is present and non-zero, `POP_TRY` on normal exit redirects
to `finally_ip` instead of the next instruction.

### POP_TRY

Removes the current exception handler. If the popped entry has a non-zero
`finally_ip`, redirects execution to the finally block (instead of advancing ip).

```
POP_TRY
```

### FINALLY_END

Signals the end of a finally block. If a deferred return is pending (set by a
`RETURN` instruction executed while a finally was active), completes the return.
Otherwise advances ip by 1.

```
FINALLY_END
```

### THROW

Raises an exception.

```
THROW
```

## 9. Function Calls and Closures

These instructions manage function execution.

### CALL

Calls a named function.

```
CALL <function> <arg_count>
```

### CALL_VALUE

Calls a function value on the stack.

```
CALL_VALUE <arg_count>
```

### CALL_METHOD

Calls an object method.

```
CALL_METHOD <method> <arg_count>
```

### MAKE_CLOSURE

Creates a closure object.

```
MAKE_CLOSURE <function>
```

Captured variables become upvalues.

### RETURN

Returns from the current function.

```
RETURN
```

The top stack value becomes the return value.

### YIELD

Suspends execution for coroutine scheduling.

```
YIELD
```

## 10. Collections and Records

These instructions construct and manipulate structured data.

### BUILD_LIST

Creates a list.

```
BUILD_LIST <count>
```

Consumes `count` stack values.

### BUILD_MAP

Creates a map (dictionary).

```
BUILD_MAP <count>
```

### BUILD_RECORD

Creates a structured record.

```
BUILD_RECORD <count>
```

### BUILD_MODULE

Creates a module object.

```
BUILD_MODULE
```

### INDEX

Accesses an indexed element.

```
INDEX
```

### INDEX_SET

Sets an indexed element.

```
INDEX_SET
```

### LOAD_FIELD

Loads a record field.

```
LOAD_FIELD <name>
```

### STORE_FIELD

Stores a record field value.

```
STORE_FIELD <name>
```

## 11. Constant Table

Compiled programs contain a constant table storing values referenced by instructions.

Examples include:

- numbers
- strings
- function objects
- module objects

Instructions such as `PUSH_CONST` reference this table by index.

## 12. Bytecode Versioning

Two different version numbers meet in this file, and conflating them is easy.

**`BYTECODE_VERSION` — the bytecode format.** Declared in
`src/nodus/compiler/compiler.py` (currently `4`), embedded in every compiled
bytecode dict and checked on load. Frozen at `4` since v1.0 and governed by
[#366](https://github.com/Masterplanner25/Nodus/issues/366), which is also what
freezes the opcode set.

> A second constant, `NODUS_BYTECODE_VERSION` in `src/nodus/runtime/module.py`,
> carries the same number for the disk cache's own check. They agree today and
> nothing compares them, so a bump to one is not a bump to the other.

**The cache container format** — the byte at offset 4 below — is a property of
the file on disk and moves independently of `BYTECODE_VERSION`. It is `0x01`
and has never been bumped.

Disk cache file format (`src/nodus/runtime/bytecode_cache.py`):

```
Bytes 0–3   Magic: NDSC
Byte  4     Container format version: 0x01
Bytes 5–36  SHA-256 of the marshal payload (integrity check)
Bytes 37+   marshal.dumps() of the payload dict
```

The payload uses Python `marshal` (not `pickle`) for serialization: faster for
the primitive types a bytecode payload contains, and it avoids pickle's
arbitrary-code-execution risk.

### What invalidates a cache entry

A cached entry is reused only when **all five** fields match. Any mismatch is a
silent miss and the module is recompiled, so no user action is needed after an
upgrade.

| Field | Guards against |
|---|---|
| `cache_version` | a different bytecode format |
| `compiler_version` | a different nodus-lang — without it, a compiler-level correctness fix silently did not apply to already-cached modules ([#411](https://github.com/Masterplanner25/Nodus/issues/411) follow-up) |
| `module_path` | an entry written for a different file |
| `mtime_ns` | an ordinary edit |
| `source_sha256` | an edit the clock cannot see ([#704](https://github.com/Masterplanner25/Nodus/issues/704)) |

> **An earlier revision of this section said mtime and the format version were
> the whole check.** They are not, and the gap was a real defect. The entry is
> *keyed* on path + mtime, so two edits landing inside the platform's timestamp
> resolution collapse to one key: measured over five rapid rewrites with
> different content each time, CPython 3.11 and PyPy 7.3.23 each produced **2
> distinct keys out of 5** on Windows, and the second run executed the first
> program. Comparing the source hash is what makes the answer depend on the file
> rather than on the clock.

`BYTECODE_VERSION` history (the container format's own introduction is the
v0.7.0 row; every row after it records a bytecode change):

```
0x01 — v0.7.0: initial marshal + NDSC magic format (replaced pickle)
0x02 — v0.8.0: FRAME_SIZE / LOAD_LOCAL_IDX / STORE_LOCAL_IDX opcodes added;
                FunctionInfo.local_slots field added to payload;
                bytecode compiled with version 0x01 is incompatible and is recompiled automatically
0x03 — v1.0:   LOAD_LOCAL removed from VM dispatch table; compiler fallback paths replaced
                with assertions; bytecode compiled with version 0x02 is incompatible and is
                recompiled automatically
0x04 — v1.0:   finally block support added; FINALLY_END opcode added; SETUP_TRY extended
                to two operands (handler_ip, finally_ip); handler_stack tuples extended to
                4-tuple; bytecode compiled with version 0x03 is incompatible and is recompiled
                automatically
```

Tooling compatibility: the compiler, the VM and the disk cache must all agree
on this number, so that a program compiled by one is only executed by the
others when they match. Note the caveat above -- that agreement is currently
maintained by two separate constants holding the same literal, not by one.

## 13. Tooling Support

The bytecode format is used by several developer tools:

- disassembler (`nodus dis`)
- debugger
- runtime trace system
- static analysis tools

Maintaining a stable instruction set helps ensure these tools remain compatible.

## 14. Future Bytecode Evolution

Possible future improvements include:

- improved instruction encoding (compact binary format)
- register-based optimization passes
- specialized opcodes for common operations (e.g. `ADD_NUM`, `ADD_STR`)

These changes should preserve compatibility where possible.

(Note: bytecode version headers are already implemented as of v0.7.0; slot-indexed locals
are implemented as of v0.8.0. See the versioning section above.)

## Final Principle

The bytecode format should remain:

- simple
- inspectable
- stable enough for tooling

Complex optimizations should not compromise clarity of the instruction model.
