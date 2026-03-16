# Nodus Opcode Freeze Proposal — v0.8

## Purpose

This document proposes the stability classification for all 47 opcodes in the
Nodus VM dispatch table as of v0.8.0.  The opcode set will be formally frozen at
v1.0.  After freeze, adding or removing an opcode requires a bytecode version
bump and an RFC-style addition to this document.

The three stability classifications used here:

| Class | Meaning |
|---|---|
| **stable** | Behavior is frozen. No breaking changes permitted after v1.0. |
| **provisional** | Behavior may change before v1.0. Embedders should not depend on this opcode's encoding or exact semantics. |
| **deprecated** | Will be removed at v1.0. Use the replacement opcode listed. |

---

## Freeze Prerequisites

All items below must be resolved before the formal v1.0 freeze can be declared.
Items marked ✅ were completed in v0.8.

- [x] ✅ `LOAD_LOCAL_IDX` migration complete — LOAD_LOCAL_IDX and STORE_LOCAL_IDX are
  now the canonical forms. LOAD_LOCAL removed from VM dispatch table at v1.0;
  replaced with RuntimeError tombstone. BYTECODE_VERSION bumped to 3.
- [x] ✅ `GET_ITER` / `ITER_NEXT` — `pending_get_iter` / `pending_iter_next` flag
  mechanism replaced by a first-class `Iterator` protocol object in v1.0. Both
  opcodes now operate synchronously via `run_closure()`. Promoted to stable at v1.0.
  See `TECH_DEBT.md § "GET_ITER pending_get_iter cleanup"` and v1.0 Decision below.
- [ ] `SETUP_TRY` / `POP_TRY` / `THROW` — decision needed on whether `finally`
  blocks or typed catches will be added before v1.0. If yes, these opcodes must
  be revised before freeze. See TECH_DEBT.md § "Exception model finalization".
- [ ] `BUILD_MODULE` — module-object semantics are still evolving (live bindings,
  re-export, aliasing). Classify stable once the module system is declared
  frozen at v1.0.

---

## Opcode Stability Table

47 total opcodes as of v0.8.0 (`BYTECODE_VERSION = 2`).

### Constants / Literals

| Opcode | Stack effect | Classification | Notes |
|---|---|---|---|
| `PUSH_CONST` | `→ val` | **stable** | Core atom. Operand is any Python primitive. |

### Frame Setup

| Opcode | Stack effect | Classification | Notes |
|---|---|---|---|
| `FRAME_SIZE` | none | **stable** | Added v0.8. Pre-allocates `locals_array`. First instruction of every function body. |

### Variable Access — Globals / Module

| Opcode | Stack effect | Classification | Notes |
|---|---|---|---|
| `LOAD` | `→ val` | **stable** | Walks 4-scope chain (locals→module_globals→functions→host_globals). |
| `STORE` | `val →` | **stable** | Writes to frame locals dict or module_globals. |

### Variable Access — Function Locals (slot-indexed)

| Opcode | Stack effect | Classification | Notes |
|---|---|---|---|
| `LOAD_LOCAL_IDX` | `→ val` | **stable** | Added v0.8. Canonical fast path. Slot-indexed read from `frame.locals_array`. Handles Cell unwrapping. |
| `STORE_LOCAL_IDX` | `val →` | **stable** | Added v0.8. Canonical fast path. Slot-indexed write to `frame.locals_array`. Handles Cell boxing. |
| `LOAD_LOCAL` | `→ val` | ⛔ **removed** | Name-keyed legacy path. Removed from VM dispatch table at v1.0. Handler replaced with RuntimeError tombstone. Replacement: `LOAD_LOCAL_IDX`. |

### Variable Access — Closures

| Opcode | Stack effect | Classification | Notes |
|---|---|---|---|
| `LOAD_UPVALUE` | `→ val` | **stable** | Reads from `frame.closure.upvalues[index]` Cell. |
| `STORE_UPVALUE` | `val →` | **stable** | Writes to `frame.closure.upvalues[index]` Cell. |

### Frame / Call Mechanics

| Opcode | Stack effect | Classification | Notes |
|---|---|---|---|
| `STORE_ARG` | `val →` | **stable** | Initialises one parameter at function entry. Syncs to both locals dict and locals_array. |
| `POP` | `val →` | **stable** | Discards top of stack. Emitted after statement expressions. |

### Arithmetic

| Opcode | Stack effect | Classification | Notes |
|---|---|---|---|
| `ADD` | `a b → a+b` | **stable** | |
| `SUB` | `a b → a-b` | **stable** | |
| `MUL` | `a b → a*b` | **stable** | |
| `DIV` | `a b → a/b` | **stable** | Raises runtime error on division by zero. |

### Comparison

| Opcode | Stack effect | Classification | Notes |
|---|---|---|---|
| `EQ` | `a b → bool` | **stable** | |
| `NE` | `a b → bool` | **stable** | |
| `LT` | `a b → bool` | **stable** | |
| `GT` | `a b → bool` | **stable** | |
| `LE` | `a b → bool` | **stable** | |
| `GE` | `a b → bool` | **stable** | |

### Unary / Boolean

| Opcode | Stack effect | Classification | Notes |
|---|---|---|---|
| `NOT` | `val → bool` | **stable** | Logical negation. |
| `NEG` | `val → -val` | **stable** | Arithmetic negation. |
| `TO_BOOL` | `val → bool` | **stable** | Coerces top of stack to bool. Used in short-circuit tails. |

### Control Flow

| Opcode | Stack effect | Classification | Notes |
|---|---|---|---|
| `JUMP` | none | **stable** | Unconditional absolute jump. |
| `JUMP_IF_FALSE` | `val →` | **stable** | Pops and jumps if falsy. |
| `JUMP_IF_TRUE` | `val →` | **stable** | Pops and jumps if truthy. Used in `\|\|` short-circuit. |

### Iteration

| Opcode | Stack effect | Classification | Notes |
|---|---|---|---|
| `GET_ITER` | `iterable → Iterator` | **stable** | Produces a first-class `Iterator` object. All paths (list, `__iter__`, `__next__`) resolved synchronously via `run_closure()`. `pending_get_iter` flag removed at v1.0. Promoted to stable at v1.0. |
| `ITER_NEXT` | `Iterator → val \| jump` | **stable** | Calls `iterator.advance()` → `(value, exhausted)`. Pops and jumps to operand on exhaustion; pushes value and advances otherwise. `pending_iter_next` flag removed at v1.0. Promoted to stable at v1.0. |

### Function Calls

| Opcode | Stack effect | Classification | Notes |
|---|---|---|---|
| `CALL` | `args… → val` | **stable** | Named function call. Operands: name, arg_count. Handles functions, builtins, closures. |
| `CALL_VALUE` | `callee args… → val` | **stable** | Call a closure value already on the stack. |
| `CALL_METHOD` | `obj args… → val` | **stable** | Method call: pops receiver and args, dispatches by method name. |
| `MAKE_CLOSURE` | `→ closure` | **stable** | Wraps a compiled function with its captured upvalues into a Closure object. |
| `RETURN` | `val →` (frame) | **stable** | Pops return value, restores caller frame. |

### Exceptions

| Opcode | Stack effect | Classification | Notes |
|---|---|---|---|
| `SETUP_TRY` | none | **provisional** | Pushes an exception handler entry. Operand: handler IP. May be revised if `finally` or typed catches are added before v1.0. |
| `POP_TRY` | none | **provisional** | Pops the current exception handler on clean exit from a try block. Same concern as SETUP_TRY. |
| `THROW` | `val →` | **provisional** | Raises a Nodus-level exception. May be revised alongside SETUP_TRY. |

### Collections

| Opcode | Stack effect | Classification | Notes |
|---|---|---|---|
| `BUILD_LIST` | `items… → list` | **stable** | Operand: item count. |
| `BUILD_MAP` | `k v … → map` | **stable** | Operand: pair count. |
| `BUILD_RECORD` | `k v … → record` | **stable** | Operand: field count. |
| `INDEX` | `seq idx → val` | **stable** | Subscript read. |
| `INDEX_SET` | `seq idx val →` | **stable** | Subscript write. Returns value. |

### Field Access

| Opcode | Stack effect | Classification | Notes |
|---|---|---|---|
| `LOAD_FIELD` | `obj → val` | **stable** | Named field read on records and modules. |
| `STORE_FIELD` | `obj val →` | **stable** | Named field write on records. Returns value. |

### Module Construction

| Opcode | Stack effect | Classification | Notes |
|---|---|---|---|
| `BUILD_MODULE` | `k v… → module` | **stable** | Constructs a `Record(fields, kind="module")` from key/value pairs on the stack. Module system (live bindings, re-exports, circular detection) is feature-complete and frozen. Promoted to stable at v1.0. |

### Coroutines / Lifecycle

| Opcode | Stack effect | Classification | Notes |
|---|---|---|---|
| `YIELD` | `val →` (suspend) | **stable** | Suspends the current coroutine and returns a value to the scheduler. No YIELD_VALUE/SEND opcode needed — send-value path is implicit via `builtin_coroutine_resume()`. Promoted to stable at v1.0. |
| `HALT` | none | **stable** | Terminates the VM execution loop. Emitted once at end of module top-level code. |

---

## Summary Counts

| Classification | Count |
|---|---|
| stable | 43 |
| provisional | 3 (`SETUP_TRY`, `POP_TRY`, `THROW`) |
| removed | 1 (`LOAD_LOCAL`) |
| **Total (active)** | **46** |

(Stable count: PUSH_CONST, FRAME_SIZE, LOAD, STORE, LOAD_LOCAL_IDX, STORE_LOCAL_IDX,
LOAD_UPVALUE, STORE_UPVALUE, STORE_ARG, POP, ADD, SUB, MUL, DIV, EQ, NE, LT, GT, LE, GE,
NOT, NEG, TO_BOOL, JUMP, JUMP_IF_FALSE, JUMP_IF_TRUE, CALL, CALL_VALUE, CALL_METHOD,
MAKE_CLOSURE, RETURN, BUILD_LIST, BUILD_MAP, BUILD_RECORD, INDEX, INDEX_SET,
LOAD_FIELD, STORE_FIELD, HALT, BUILD_MODULE, YIELD, GET_ITER, ITER_NEXT = **43 stable**, 3 provisional.)

Totals: **43 stable**, **3 provisional**, **1 removed** = 46 active + 1 removed.
(v1.0 update: YIELD, BUILD_MODULE, GET_ITER, ITER_NEXT promoted from provisional to stable.
 LOAD_LOCAL removed from dispatch table; BYTECODE_VERSION bumped to 3.)

---

## Freeze Risks

1. ✅ **`LOAD_LOCAL` removal** — complete at v1.0. The three compiler fallback paths were
   confirmed unreachable via audit. The opcode was removed from the VM dispatch table and
   the handler replaced with a RuntimeError tombstone. `BYTECODE_VERSION` bumped to 3.

2. ✅ **`GET_ITER` / `ITER_NEXT` pending_get_iter** — resolved at v1.0. The
   `pending_get_iter` / `pending_iter_next` flags were replaced by a first-class
   `Iterator` protocol object. Both opcodes are now synchronous and stable. No
   observable stack/execution behavior change for correct programs.

3. **Exception model gap** — `finally` blocks and typed `catch` are not yet supported.
   If these are added before v1.0, `SETUP_TRY` / `POP_TRY` will need new operands or
   new companion opcodes.

4. **`YIELD` coroutine resume** — the scheduler currently drives coroutines by sending
   values back via `builtin_coroutine_resume`. The protocol is stable in practice but
   the send-value path is implicit. Formalizing it may require a `YIELD_VALUE` or
   `SEND` opcode.

5. **No known duplicate or redundant opcodes.** No merge candidates identified.

---

## v0.9 Opcode Decisions

These decisions were made as part of the v0.9 milestone. All 7 provisional opcodes
remain provisional. Each is targeted for promotion or redesign at v1.0.

### GET_ITER / ITER_NEXT — remains provisional

**v0.9 decision:** Leave `pending_get_iter` / `pending_iter_next` mechanism as-is.
Document the behavior in `INSTRUCTION_SEMANTICS.md`. Cleanup deferred to v1.0.

**Rationale:** The mechanism works correctly. The architectural smell (two execution
paths for the same opcode) does not affect observable behavior for correct programs.
A clean Iterator protocol object (wrapping builtins and closures uniformly, removing
the pending flags and the RETURN handler coupling) is the preferred v1.0 fix.
Estimated v1.0 scope: VM-only change, no compiler or `.nd` source impact.

### GET_ITER / ITER_NEXT — v1.0 Decision

**v1.0 decision:** Iterator protocol cleanup complete. `pending_get_iter` and
`pending_iter_next` VM flags fully removed. Both opcodes promoted to **stable**.

The cleanup introduced a first-class `Iterator` class in `vm.py` wrapping an
`advance_fn: () → (value, exhausted)` callable. All paths (list, `__iter__` closure,
`__next__` closure) produce an `Iterator` object synchronously using `run_closure()`.
The `_op_return` pending-flag post-processing blocks were removed. The `_NO_PENDING`
sentinel and the dead `elif rv is _NO_PENDING` branch in `execute()` were removed.
`Coroutine` dataclass fields `pending_get_iter` and `pending_iter_next` removed.
`save_execution_context()` / `restore_execution_context()` tuples reduced from 7 to 5
fields. 14 pending-flag sites removed across `vm.py`. VM-only change; no compiler or
`.nd` source impact. All 379 tests pass. Coroutine + iteration interaction tests added
(`test_coroutine_iteration_suspend_resume`, `test_coroutine_custom_iterator_suspend_resume`).

**Classification:** → promoted to **stable** at v1.0.

### SETUP_TRY / POP_TRY / THROW — remains provisional

**v0.9 decision:** `finally` blocks are NOT implemented before v1.0. Exception opcodes
remain provisional.

**Current capability:** Basic `try { } catch err { }` is supported and stable in
practice. Multiple catch clauses, `finally` blocks, and typed/pattern-matched catches
are not supported.

**Rationale:** Adding `finally` requires either a new `SETUP_FINALLY` opcode or
extending `SETUP_TRY`'s operand format, which changes the handler stack tuple
structure. The implementation cost is Large and is not justified for v0.9.

**v1.0 scope for exception model:**
- `finally` blocks (new opcode or extended `SETUP_TRY`)
- ✅ Structured value preservation in `throw` — `_op_throw` (vm.py:2142) now preserves
  Records/lists as `err.payload` with `kind="thrown"`. Fixed in v1.0.
- Typed/pattern-matched catches: post-v1.0

### YIELD — remains provisional

**v0.9 decision:** Send-value path is not formalized. `YIELD` remains provisional.

**Current behavior:** `YIELD` suspends the current coroutine and returns a value to the
scheduler. `builtin_coroutine_resume()` can pass a value back into a resumed coroutine
via the stack, but there is no dedicated user-facing opcode for receiving the sent value.

**v1.0 scope:** Evaluate whether a `YIELD_VALUE` / `SEND` opcode is needed for the
coroutine model. If the send-value use case is required before v1.0, a new opcode will
be added via the Post-Freeze Extension Process defined in this document.

**v1.0 Decision:** YIELD frozen as-is. No `YIELD_VALUE` or `SEND` opcode needed.

The send-value mechanism is not user-accessible from `.nd` source. No `.nd` files,
examples, or tests use a `let result = yield expr` pattern. `LANGUAGE_SPEC.md` describes
`yield` only as a suspend mechanism. `builtin_coroutine_resume()` can pass values via the
Python embedding API, but this does not require a new opcode.

Send-value coroutines are deferred post-v1.0. If needed in a future version, a
`YIELD_VALUE` or `SEND` opcode will be added via the Post-Freeze Extension Process.

**Classification:** → promoted to **stable** at v1.0.

### BUILD_MODULE — remains provisional

**v0.9 decision:** Stability classification deferred to v1.0 module system freeze.

**Current behavior:** `BUILD_MODULE` pops `count` key-value pairs, constructs a
`Record(fields, kind="module")`, and pushes it. The `kind="module"` marker activates
module-export semantics in `LOAD_FIELD` and `CALL_METHOD`. The opcode's behavior has
been deterministic and stable since v0.7.

**Rationale:** `BUILD_MODULE`'s stability is coupled to the module system stability
declaration — specifically, whether live bindings, re-exports, or aliasing semantics
will change the Record structure before v1.0. Once the module system is declared
frozen at v1.0, `BUILD_MODULE` will be promoted to stable.

**v1.0 Decision:** BUILD_MODULE promoted to stable. Module system frozen.

The module system is feature-complete:
- ✅ Named exports (`ExportList`, `let x = ... export`)
- ✅ Re-exports (`ExportFrom`)
- ✅ Namespace imports (`import "mod" as ns`)
- ✅ Live bindings (named imports are live references)
- ✅ Circular import detection (`import_state` loading cycle check)
- ✅ `std:` stdlib imports

`BUILD_MODULE` behavior (pop count key-value pairs, construct `Record(fields, kind="module")`)
has been deterministic since v0.7.0. No planned module semantics changes for v1.0 or beyond.
The `Record` structure produced by `BUILD_MODULE` is frozen.

**Classification:** → promoted to **stable** at v1.0.

## Remaining Provisional Opcodes (as of v1.0 planning)

| Opcode | Unblocked by |
|---|---|
| ✅ `GET_ITER`, `ITER_NEXT` | ✅ Iterator protocol cleanup complete at v1.0. Promoted to stable. |
| `SETUP_TRY`, `POP_TRY`, `THROW` | `finally` block implementation (new opcode or extended `SETUP_TRY` operand). THROW remains provisional because it may be revised alongside SETUP_TRY when `finally` is added. |

Three opcodes remain provisional (`SETUP_TRY`, `POP_TRY`, `THROW`), all blocked on
`finally` implementation. `GET_ITER` and `ITER_NEXT` were promoted to stable via the
Iterator protocol cleanup at v1.0. All remaining provisional opcodes are targeted for
stable classification once the `finally` implementation is complete.

---

## Post-Freeze Extension Process

After v1.0 opcode freeze, new opcodes must follow this process:

1. **Open a GitHub issue** proposing the opcode with:
   - Name and proposed encoding
   - Stack effect (operands consumed, values produced)
   - Motivation and example Nodus source that requires it
   - Alternatives considered
2. **Add to `BYTECODE_REFERENCE.md`** as `provisional` with the same fields as
   existing entries.
3. **Bump `BYTECODE_VERSION`** in `compiler.py` and `bytecode_cache.py` so existing
   cached bytecode is invalidated.
4. **Implement the VM handler** (`_op_<name>`) and register it in
   `_build_dispatch_table()`.
5. **Update this document** with the new opcode in the stability table.
6. **After one full release cycle**, promote from `provisional` to `stable`.
7. **Update `BYTECODE_REFERENCE.md`** to reflect the stable classification.

Removing a stable opcode after freeze is not permitted. Deprecated opcodes must
survive at least one full release cycle after deprecation before removal.

---

## Version History

| Version | Event |
|---|---|
| v0.8.0 | Initial freeze proposal drafted. 47 opcodes classified. LOAD_LOCAL_IDX and STORE_LOCAL_IDX added. FRAME_SIZE added. LOAD_LOCAL deprecated. Bytecode version bumped to 2. |
| v1.0 | Formal freeze — stable opcodes are locked. POST-FREEZE process applies. LOAD_LOCAL removed from dispatch table (tombstone handler remains). BYTECODE_VERSION bumped to 3. GET_ITER, ITER_NEXT, BUILD_MODULE, YIELD promoted to stable. 46 active opcodes. |
