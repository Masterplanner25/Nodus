# Nodus Bytecode Reference

> **The Nodus opcode set was frozen at v1.0 (2026-03-15).**
> All 49 active opcodes are **stable**. Zero provisional opcodes remain.
> Post-freeze additions follow the extension process in
> [`docs/governance/FREEZE_PROPOSAL.md`](../governance/FREEZE_PROPOSAL.md) — though
> two of the 49 did not follow it; see §3.1.

## 1. Executive Summary
Nodus uses bytecode as the execution contract between the parser/compiler front-end and the stack VM runtime (`compiler.py` -> `optimizer.py` -> `vm.py`). The compiler lowers AST nodes into tuple instructions, the optimizer rewrites bytecode without changing semantics, and the VM dispatch loop executes the optimized instruction stream with a value stack plus call frames. The instruction set is **frozen at v1.0**: 49 active stable opcodes, `BYTECODE_VERSION = 4`.

**Opcode stability classifications** (stable / removed) and the v1.0 freeze declaration are documented in [`docs/governance/FREEZE_PROPOSAL.md`](../governance/FREEZE_PROPOSAL.md). As of v1.0: **47 stable**, 0 provisional, 1 removed (`LOAD_LOCAL`). Two further opcodes were added after the freeze (`MOD`, `RESET_LOCAL_IDX`), bringing the total active opcodes in the dispatch table to **49** — see §3.1.

## 2. VM Model Overview
- Stack model:
  - Primary operand stack (`self.stack`) for expression evaluation.
  - Most binary ops pop two values and push one result.
  - Statement expressions are explicitly discarded with `POP`.
- Variable storage model:
  - Globals in `self.globals`.
  - Function locals in top call frame (`Frame.locals`).
  - Name lookup checks locals first, then globals.
- Call/frame model:
  - User calls use `CALL` with function name + arity.
  - New `Frame` stores return IP, local scope, function name, and call-site location.
  - Arguments are pushed before call; callee prologue uses `STORE_ARG` to bind parameters.
  - `RETURN` pops one value and resumes caller.
  - Stack traces display demangled function names even if internal names are module-qualified.
- Control flow model:
  - Absolute jumps (`JUMP`) and conditional pops (`JUMP_IF_FALSE`, `JUMP_IF_TRUE`).
  - `if`/`while`/short-circuit logic are compiler-lowered with patches.
- Collection/indexing model:
  - `BUILD_LIST` and `BUILD_MAP` construct aggregate values from stack items.
  - `INDEX` and `INDEX_SET` route through VM helpers with type/range/key checks.
- Import/module-related runtime behavior:
  - Imports are resolved pre-bytecode (`resolve_imports`), not by VM opcodes.
  - Module boundaries are enforced in loader/compiler; names are rewritten to module-qualified globals.
  - Namespaced import access (`mod.name`) is compiler-resolved to qualified global symbols.
- Optimization pipeline:
  - The optimizer runs after bytecode generation and before execution by default.
  - Current passes include constant folding, unreachable instruction removal, jump-target simplification, constant canonicalization, and trivial stack cleanup (`PUSH_CONST` followed by `POP`).
  - `nodus run --no-opt ...` disables optimization.
- Dispatch model:
  - `VM.execute()` uses a dict dispatch table (`self._dispatch`) built once at `VM.__init__`
    time by `_build_dispatch_table()`. Each opcode string maps to a bound `_op_XXX` method.
    This replaced the previous `if/elif` chain in Phase 3, yielding a ~33% speedup on
    compute-heavy benchmarks (388 ms → 260 ms). Adding a new opcode requires: (a) a new
    `_op_<name>` method, and (b) a corresponding entry in `_build_dispatch_table()`.

## 3. Opcode Inventory
Complete opcode set implemented by VM dispatch (`VM.run`):

### PUSH_CONST
- Category: constants / literals
- Stack behavior: pushes one constant value
- Operands: literal value
- Emitted by compiler: yes
- Purpose: load numbers, booleans, strings, nil/default returns, synthesized booleans
- Notes / edge cases: also used for function default `nil` return and short-circuit fallbacks.

### LOAD
- Category: variable access
- Stack behavior: pushes resolved variable value
- Operands: variable name (string)
- Emitted by compiler: yes
- Purpose: variable and resolved namespace member access
- Notes / edge cases:
  - Resolution order, first match wins: `frame.locals` → `module_globals` →
    `functions` → `host_globals`. A name found in `functions` is pushed as a
    **zero-upvalue `Closure`**, not as a `FunctionInfo`, which is what makes
    `let f = g` produce something `CALL_VALUE` can call.
  - `Cell` (captured-variable boxing) and `LiveBinding` (a re-export) are
    unwrapped, so what is pushed is always the value.
  - Raises runtime name error if undefined.
  - Names may be module-qualified (e.g., `__mod0__name`) after compile-time resolution.

### FRAME_SIZE
- Category: frame setup
- Stack behavior: none (stack effect: 0)
- Operands: n (integer) — number of local variable slots required by the function
- Emitted by compiler: yes (first instruction of every compiled function body)
- Purpose: pre-allocates the frame's slot-indexed locals array (`frame.locals_array = [None] * n`)
- Notes / edge cases:
  - Emitted before any `STORE_ARG` instructions in the function prologue.
  - The operand is patched at the end of function compilation once the total slot count is known.
  - Slot count includes parameters and all locals from nested block scopes within the function.
  - No-op at module top-level (never emitted outside function bodies).

### LOAD_LOCAL
- Category: variable access (fast path, name-keyed) — **⛔ Removed in v1.0**
- Status: **Removed**. No longer in the VM dispatch table. Attempting to execute a `LOAD_LOCAL`
  instruction raises a `RuntimeError` tombstone directing the user to recompile.
- History: Deprecated since v0.8.0 when `LOAD_LOCAL_IDX` (slot-indexed) was introduced.
  The compiler retained three fallback paths (formerly at lines 584, 619, 731) that emitted
  `LOAD_LOCAL` when `symbol.index is None`. Audit in v1.0 confirmed all three were unreachable
  (`SymbolTable.define()` always assigns a slot index when inside a function scope). The fallbacks
  were replaced with `assert` guards and `BYTECODE_VERSION` was bumped to 3.
- Migration: Recompile any source that was cached with `BYTECODE_VERSION = 2`. The version bump
  invalidates caches automatically.

### LOAD_LOCAL_IDX
- Category: variable access (fast path, slot-indexed)
- Stack behavior: pushes local variable value (`→ value`)
- Operands: slot (integer) — index into `frame.locals_array`
- Emitted by compiler: yes (primary path for all function-local variable reads)
- Purpose: slot-indexed fast path for confirmed function-local variables. Reads `frame.locals_array[slot]`, bypassing both the 4-dict probe in `load_name()` and the hash computation in the dict-keyed `LOAD_LOCAL`. Supersedes `LOAD_LOCAL`.
- Notes / edge cases:
  - Requires `FRAME_SIZE` to have been executed first (initializes `frame.locals_array`).
  - Unwraps `Cell` (captured upvalue boxing) and `LiveBinding` values transparently.
  - Parameters synced to `locals_array` by `STORE_ARG`; block-scope locals written by `STORE_LOCAL_IDX`.
  - Slot assignments are stable within a single compilation — not preserved across cache invalidation.

### STORE_LOCAL_IDX
- Category: variable access (fast path, slot-indexed)
- Stack behavior: pops value, writes to `frame.locals_array[slot]` (`value →`)
- Operands: slot (integer) — index into `frame.locals_array`
- Emitted by compiler: yes (for all local `let` bindings, assignments, destructuring, `for`/`foreach` loop vars, and `try`/`catch` vars in function scope)
- Purpose: slot-indexed local variable store. Eliminates the dict hash computation of the `STORE` opcode for known function-local variables. Handles Cell boxing on write for captured variables.
- Notes / edge cases:
  - If the existing array entry is a `Cell` (captured upvalue), updates `cell.value` in-place to preserve shared-mutable closure semantics.
  - The `STORE_ARG` opcode syncs parameters to both `frame.locals` (dict) and `frame.locals_array` so parameters are accessible via both paths.
  - Does not write to `frame.locals` (dict); the dict is only updated by `STORE_ARG` and by `capture_local` when a Cell is first created.

### RESET_LOCAL_IDX
- Category: variable access (fast path, slot-indexed)
- Stack behavior: none (no stack effect)
- Operands: slot (integer) — index into `frame.locals_array`
- Emitted by compiler: yes — at the start of each `for`-loop iteration for the loop
  variable, and before each `let` binding for any variable inside a loop body
- Purpose: detach any `Cell` at a local slot by replacing it with a plain `None`, so
  that `MAKE_CLOSURE` creates a fresh per-iteration `Cell` rather than reusing the one
  from the previous iteration. This is what makes closures captured in a loop see their
  own iteration's value.
- Notes / edge cases: **Added post-freeze** in `53da7f7` (2026-06-10, PR #244) without
  the extension process required by `FREEZE_PROPOSAL.md` §"What Freeze Means" — no
  `BYTECODE_VERSION` bump, no entry here, no amendment. Documented retroactively
  2026-08-07. See §3.1.

### LOAD_UPVALUE
- Category: closure / upvalue access
- Stack behavior: pushes captured variable value
- Operands: upvalue index (integer)
- Emitted by compiler: yes
- Purpose: read captured values from a closure
- Notes / edge cases: runtime error if no closure frame or index out of range.

### STORE
- Category: variable access
- Stack behavior: pops value, stores into name
- Operands: variable name (string)
- Emitted by compiler: yes
- Purpose: `let` binding and reassignment
- Notes / edge cases:
  - The target namespace is chosen by `VM.binding_namespace`, not by "the
    current frame": if the name is bound in `frame.locals` the write goes there,
    else if it is bound in `module_globals` it goes there. A function assigning
    a module-level `let` therefore updates the global (#671); before that fix the
    write landed in a fresh frame-local and the global silently kept its value.
  - An **unbound** name is defined where execution currently is — a new local
    inside a frame, a new global at module level.
  - An existing `Cell` is updated in place rather than replaced, so closures
    sharing the variable keep seeing each other's writes.
  - Assignment expressions then issue `LOAD` to return assigned value.
  - Names may be module-qualified after compile-time resolution.

### STORE_UPVALUE
- Category: closure / upvalue access
- Stack behavior: pops value, stores into captured slot
- Operands: upvalue index (integer)
- Emitted by compiler: yes
- Purpose: write captured values inside closures
- Notes / edge cases: runtime error if no closure frame or index out of range.

### STORE_ARG
- Category: calls / returns
- Stack behavior: pops one argument value into current frame locals
- Operands: parameter name
- Emitted by compiler: yes (function prologue)
- Purpose: bind positional call arguments to function params
- Notes / edge cases:
  - **Two writes, not one.** It sets `frame.locals[name]` *and* syncs the value
    into `frame.locals_array` at the parameter's slot, so the parameter reads
    correctly through both `LOAD` (dict) and `LOAD_LOCAL_IDX` (slot). A
    parameter with no slot entry gets the dict write only.
  - An existing `Cell` at the name is updated in place.
  - VM errors if no active call frame.

### POP
- Category: control flow / stack housekeeping
- Stack behavior: pops top value, discards
- Operands: none
- Emitted by compiler: yes
- Purpose: discard expression-statement results and builtin-print return value
- Notes / edge cases: explicit stack-discipline anchor.

### ADD
- Category: arithmetic
- Stack behavior: pops `b`, `a`; pushes `a + b`
- Operands: none
- Emitted by compiler: yes (via `op_map`)
- Purpose: numeric addition, string concatenation, list concatenation
- Notes / edge cases:
  - Operand order: `b` is popped first, so the deeper value is `a` and the
    result is `a + b`.
  - The **success** cases follow Python `+`; the **failure** case does not. A
    host `TypeError` is converted to a Nodus `type` error reading
    `Cannot add <type> and <type>` — which is the message a program sees when an
    uninitialised value reaches arithmetic.

### SUB
- Category: arithmetic
- Stack behavior: pops two, pushes difference
- Operands: none
- Emitted by compiler: yes (via `op_map`)
- Purpose: subtraction
- Notes / edge cases:
  - Unary minus uses the dedicated `NEG` opcode rather than `SUB`.
  - A host `TypeError` becomes `Cannot subtract <type> and <type>`.

### MUL
- Category: arithmetic
- Stack behavior: pops two, pushes product
- Operands: none
- Emitted by compiler: yes (via `op_map`)
- Purpose: multiplication
- Notes / edge cases:
  - Inherited from the host and reachable from Nodus source: `"ab" * 3` is
    string repetition, and `[0] * 3` list repetition. Neither is an error.
  - A host `TypeError` becomes `Cannot multiply <type> and <type>`.

### DIV
- Category: arithmetic
- Stack behavior: pops two, pushes quotient
- Operands: none
- Emitted by compiler: yes (via `op_map`)
- Purpose: division
- Notes / edge cases:
  - **Three branches, and none of them is plain host division.**
    1. both operands `int` (and **not** `bool`) → **floor** division `a // b`,
       so `7 / 2` is `3` and `-7 / 2` is `-4`;
    2. either operand `float` → true division, so `7 / 2.0` is `3.5`;
    3. either operand non-numeric → `Cannot divide <type> and <type>`.
  - `bool` is deliberately excluded from the int path even though
    `isinstance(True, int)` holds in Python, so `4 / true` takes the float
    branch and yields `4.0`.
  - Division by zero raises a Nodus `math` error, not a host
    `ZeroDivisionError`, and the two branches have **different messages**:
    `Integer division by zero` and `Float division by zero`.

### MOD
- Category: arithmetic
- Stack behavior: pops two, pushes remainder
- Operands: none
- Emitted by compiler: yes (via `op_map`)
- Purpose: `%`
- Notes / edge cases:
  - Same three-branch shape as `DIV`, including the exclusion of `bool` from the
    int path and the two distinct zero errors (`Integer modulo by zero`,
    `Float modulo by zero`).
  - Sign follows the host: `-7 % 3` is `2`, not `-1` as in C. A reader arriving
    from another language will assume the other answer.
  - **Added post-freeze** in `7520fc3` (2026-05-24, BUG-010) without the
    extension process required by `FREEZE_PROPOSAL.md` §"What Freeze Means" — no
    `BYTECODE_VERSION` bump, no entry here, no amendment. Documented
    retroactively 2026-08-07. See §3.1.

### EQ
- Category: comparisons
- Stack behavior: pops two, pushes boolean equality
- Operands: none
- Emitted by compiler: yes (via `op_map`)
- Purpose: `==`
- Notes / edge cases:
  - **Not Python equality.** `VM._nodus_eq` coerces `int` and `float` to each
    other and refuses to coerce `bool` to either, so `1 == 1.0` is **true** and
    `1 == true` is **false** — the opposite of Python in the second case.
  - Lists and maps compare structurally. **Records compare by identity**: two
    distinct records with equal fields are not equal (#545, staged to become
    structural at 6.0.0).

### NE
- Category: comparisons
- Stack behavior: pops two, pushes boolean inequality
- Operands: none
- Emitted by compiler: yes (via `op_map`)
- Purpose: `!=`
- Notes / edge cases: the exact negation of `EQ`, including its int/float
  coercion, its refusal to coerce `bool`, and record identity.

### LT
- Category: comparisons
- Stack behavior: pops two, pushes `a < b`
- Operands: none
- Emitted by compiler: yes (via `op_map`)
- Purpose: `<`
- Notes / edge cases: operand order is `a < b` with `b` popped first. A
  mismatched pair raises a Nodus `type` error `Cannot compare <type> and
  <type>`, **not** the host `TypeError`; `int` and `float` are comparable.

### GT
- Category: comparisons
- Stack behavior: pops two, pushes `a > b`
- Operands: none
- Emitted by compiler: yes (via `op_map`)
- Purpose: `>`
- Notes / edge cases: same host semantics caveat.

### LE
- Category: comparisons
- Stack behavior: pops two, pushes `a <= b`
- Operands: none
- Emitted by compiler: yes (via `op_map`)
- Purpose: `<=`
- Notes / edge cases: same host semantics caveat.

### GE
- Category: comparisons
- Stack behavior: pops two, pushes `a >= b`
- Operands: none
- Emitted by compiler: yes (via `op_map`)
- Purpose: `>=`
- Notes / edge cases: same host semantics caveat.

### JUMP
- Category: control flow
- Stack behavior: no stack change
- Operands: absolute target IP
- Emitted by compiler: yes
- Purpose: unconditional branching; skip function section at startup; loop back-edges
- Notes / edge cases: patched after code generation where needed.

### JUMP_IF_FALSE
- Category: boolean / logical flow
- Stack behavior: pops condition; jumps if falsey
- Operands: absolute target IP
- Emitted by compiler: yes
- Purpose: `if`/`while` and `&&` short-circuit path
- Notes / edge cases: uses the VM truthiness function (see `TO_BOOL`), and pops
  the condition **whether or not it jumps** — popping only on the taken branch
  would leave the stack unbalanced on the other.

### JUMP_IF_TRUE
- Category: boolean / logical flow
- Stack behavior: pops condition; jumps if truthy
- Operands: absolute target IP
- Emitted by compiler: yes
- Purpose: `||` short-circuit path
- Notes / edge cases: only needed for logical-OR lowering; pops the condition
  whether or not it jumps, as `JUMP_IF_FALSE` does.

### GET_ITER
- Category: iteration
- Stack behavior: pops iterable, pushes iterator
- Operands: none
- Emitted by compiler: yes
- Purpose: obtain an iterator for `for name in iterable` loops
- Notes / edge cases:
  - Lists are iterable by default.
  - Records can provide `__iter__` (returns list or record with `__next__`) or `__next__` directly.
    When a record has **both**, `__iter__` wins. `__next__` is called with the
    record itself as its one argument.
  - `__iter__` returning neither a list nor a record with `__next__` raises
    `__iter__ must return a list or a record with __next__`.
  - A **map** gets its own message rather than the generic one, because `for k
    in m` is the natural first attempt: `maps are not directly iterable; use
    'for k in keys(m)' ... or 'for v in values(m)' ...`. Anything else is
    `Value is not iterable`.

### ITER_NEXT
- Category: iteration
- Stack behavior: **differs by branch.** The iterator stays on the stack and is
  not consumed on the common path: on an item it is `iter → iter item` with
  `ip += 1`; on exhaustion it is `iter →` (the iterator *is* popped) with
  `ip = end`.
- Operands: end target IP
- Emitted by compiler: yes
- Purpose: advance iterator and load next item
- Notes / edge cases:
  - For list iterators, end is reached when index exceeds length. A list
    *containing* `nil` yields it as an ordinary element — only the record
    protocol reads `nil` as completion.
  - For record iterators, `__next__` should return `nil` to signal completion.
  - Runtime error `ITER_NEXT without iterator` on an empty stack, and
    `Iterator is not supported` if the top of stack is not an `Iterator`.

### SETUP_TRY
- Category: exceptions
- Stack behavior: no stack change
- Operands: `handler_ip` (absolute); optional `finally_ip` (absolute, 0 = no finally)
- Emitted by compiler: yes
- **Status: stable** (frozen at v1.0)
- Purpose: push an exception handler (and optional finally target) for the current frame. Pushes 4-tuple `(handler_ip, finally_ip, stack_depth, frame_depth)` onto `handler_stack`.
- Notes / edge cases: when `finally_ip` is non-zero, `POP_TRY` on normal exit redirects to the finally block.

### POP_TRY
- Category: exceptions
- Stack behavior: no stack change
- Operands: none
- Emitted by compiler: yes
- **Status: stable** (frozen at v1.0)
- Purpose: remove the most recent exception handler; if `finally_ip` is non-zero, redirect execution to the finally block
- Notes / edge cases: runtime error if no handler exists.

### FINALLY_END
- Category: exceptions
- Stack behavior: no stack change (or full return if deferred return is pending)
- Operands: none
- Emitted by compiler: yes (at end of every finally block)
- **Status: stable** (added and frozen at v1.0)
- Purpose: complete a finally block, taking whichever of three exits applies
- Notes / edge cases:
  - **Three exits, checked in this order** (#412 phase 2 — this entry named only
    the second until then):
    1. a **deferred error** is pending — the catch block raised and this finally
       ran on the way out (#361). Propagation resumes: the error goes to the
       enclosing handler, or is re-raised if there is none.
    2. a **deferred return** is pending — set by RETURN executing while a
       finally-bearing handler was active. The frame is popped, the value
       pushed, and handlers recorded at a now-dead frame depth are dropped.
    3. neither — `ip` advances by one.
  - On exits 2 and 3 it also pops a **finally-gate sentinel**
    (`handler_ip == -1`) left by `handle_exception` on the normal catch-exit
    path, and only that sentinel — a real handler entry on top is left alone.
  - **Exit 1 must be checked before the gate pop**, because
    `handle_exception` has already consumed this region's gate: a gate still on
    top belongs to an *enclosing* catch, and popping it here would skip that
    region's finally.
  - Semantics pinned by `tests/test_opcode_semantics.py`.

### TO_BOOL
- Category: boolean / logical flow
- Stack behavior: pops value, pushes normalized boolean
- Operands: none
- Emitted by compiler: yes
- Purpose: ensure `&&`/`||` yield boolean values
- Notes / edge cases:
  - Truthiness: `nil` is false, a `bool` is itself, everything else is host
    `bool()` — so `0`, `0.0`, `""`, `[]` and `{}` are false.
  - **An empty record is true** while the empty map beside it is false: a
    `Record` has no `__len__` for `bool()` to consult. Central to current
    “real boolean semantics” behavior.

### NOT
- Category: boolean / logical flow
- Stack behavior: pops value, pushes logical negation
- Operands: none
- Emitted by compiler: yes
- Purpose: unary `!`
- Notes / edge cases: negates truthiness, not strict boolean only.

### NEG
- Category: arithmetic
- Stack behavior: pops value, pushes numeric negation
- Operands: none
- Emitted by compiler: yes
- Purpose: unary `-`
- Notes / edge cases: expects a numeric value. A non-numeric operand raises a
  Nodus `type` error `Cannot negate <type>`; the host `TypeError` is converted,
  not surfaced.

Example source:

```
let x = -5
```

Possible bytecode:

```
PUSH_CONST 5
NEG
STORE x
```

### BUILD_LIST
- Category: collections
- Stack behavior: pops `count` items, pushes list in source order
- Operands: item count
- Emitted by compiler: yes
- Purpose: list literal construction
- Notes / edge cases: pops reverse then reverses to preserve source order.

### BUILD_MAP
- Category: collections
- Stack behavior: pops key/value pairs, pushes dict
- Operands: pair count
- Emitted by compiler: yes
- Purpose: map literal construction
- Notes / edge cases:
  - Key type validated: strings and numbers only. **`bool` is refused** despite
    being an `int` in Python, as is `nil` — `Map keys must be strings or numbers`.
  - Ordering is preserved by the reverse pass, which is what makes "the later
    duplicate key wins" well defined.

### BUILD_RECORD
- Category: records
- Stack behavior: pops key/value pairs, pushes record
- Operands: field count
- Emitted by compiler: yes
- Purpose: record literal construction
- Notes / edge cases: keys must be strings — stricter than `BUILD_MAP`, which
  also accepts numbers. The result has `kind="record"`; `BUILD_MODULE` is the
  same opcode with `kind="module"`.

### BUILD_MODULE
- Category: collections / module construction
- Stack behavior: pops `count` key/value pairs, pushes a Record with `kind="module"`
- Operands: field count (int)
- Emitted by compiler: **in principle only — measured never** (see below)
- Purpose: construct a runtime module record that exposes named exports
- Notes / edge cases:
  - Keys must be strings; non-string keys raise a runtime type error.
  - The resulting Record has `kind="module"`, which causes LOAD_FIELD and CALL_METHOD
    to use module-export semantics rather than plain record-field semantics.
  - Not the same as importing a module: this opcode constructs the module value that
    the module loader stores and makes available to importers.
  - **It is the one opcode of the frozen 49 that nothing executes (#412).** The
    execution census — every dispatch entry counted across the full suite,
    **895,076 executions** — records 48 of 49 opcodes running and this one at
    **zero**. Not a coverage gap in the ordinary sense: it is not *emitted*
    either. Its single emit site is `compiler.py`'s `ModuleAlias` case, and
    `ModuleAlias` is constructed only by `tooling/loader.py`, which the runtime's
    `runtime/module_loader.py` superseded. Checked rather than inferred: an
    aliased `std:` import, an aliased local-file import, `run_source` and
    `run_file` all execute it zero times, and it does not appear in the
    disassembly of an aliased import at all.
  - Left in place rather than removed: the instruction set is **frozen**, and
    removing an opcode is a bytecode-format change. What is corrected here is the
    documentation, which claimed it is emitted.

### INDEX
- Category: collections
- Stack behavior: pops index/key then sequence/map; pushes selected value
- Operands: none
- Emitted by compiler: yes
- Purpose: indexing read (`xs[i]`, `m[k]`)
- Notes / edge cases: list bounds/type checked; map key existence/type checked.

### INDEX_SET
- Category: assignment/mutation
- Stack behavior: pops value, index/key, container; pushes assigned value
- Operands: none
- Emitted by compiler: yes
- Purpose: indexing write for list/map
- Notes / edge cases: list bounds/type checks; map key type checks; non-list/map errors.

### LOAD_FIELD
- Category: records
- Stack behavior: pops record, pushes field value
- Operands: field name
- Emitted by compiler: yes
- Purpose: field access (`record.field`)
- Notes / edge cases:
  - **A record is not the only valid receiver.** A `NodusModule` is one too, and
    resolves through its export table: a missing name is
    `Missing module export: <name>` rather than `Missing record field: <name>`.
    (The same omission phase 2 corrected in `CALL_METHOD`, in the sibling
    opcode.)
  - Any other receiver — a map included — is
    `Field access is only supported on records`. Maps take `[key]`, records take
    `.field`; the two are not interchangeable.

### STORE_FIELD
- Category: records
- Stack behavior: pops value and record, pushes assigned value (net **-1**, not
  -2 — the push is what makes `r.f = v` usable as an expression)
- Operands: field name
- Emitted by compiler: yes
- Purpose: field assignment (`record.field = value`)
- Notes / edge cases:
  - **A missing field is created, not an error.** The earlier "field missing"
    note was true only of a module receiver: a module's surface is declared, so
    a name it does not export is `Missing module export: <name>`, while a record
    gains the field.
  - A `NodusModule` is a valid receiver here too, and the write goes through
    `set_export`.
  - Any other receiver is `Field assignment is only supported on records`.

### CALL
- Category: calls / returns
- Stack behavior: user fn path creates frame and transfers control; builtin path pops args and pushes return
- Operands: function name, arg count
- Emitted by compiler: yes
- Purpose: user-defined and builtin function invocation
- Notes / edge cases:
  - **Five resolution paths, in precedence order.** (1) A compiler-emitted
    builtin call site — a name carrying `BUILTIN_CALL_PREFIX` — resolves
    straight to the builtin, checked **first** so a program cannot shadow
    machinery a lowering injected into its own code (#411). (2) `functions`:
    pushes a frame and transfers control, pushing nothing. (3) `builtins`: pops
    the arguments and pushes the result, with no frame. (4) A local or global
    holding a callable, delegated to `call_closure` — or a `ModuleFunction`,
    invoked with its result pushed. (5) Otherwise `Undefined function: <name>`.
  - A user function is resolved **before** a builtin of the same name.
  - A function whose `FunctionInfo` declares upvalues cannot be called this way
    — `CALL` has no closure to draw them from, and the compiler emits
    `MAKE_CLOSURE` + `CALL_VALUE` instead. Refused as `requires a closure`.
  - The frame's `return_ip` is the call site **+ 1**. The `max_frames` cap is
    checked *before* the frame is appended, so a refused call leaves the frame
    stack as it was.
  - No first-class function values in bytecode; callee resolved to name at compile time.

### CALL_VALUE
- Category: calls / returns
- Stack behavior: pops callee value; arguments already on stack; invokes closure or errors
- Operands: arg count
- Emitted by compiler: yes
- Purpose: call closures and other runtime function values
- Notes / edge cases:
  - Arguments are popped and **re-ordered back into source order** before being
    re-pushed, because the compiler pushes them left to right.
  - For a `Closure` it **transfers control** — pushes a frame and sets `ip` to
    the function's address — rather than pushing a result. A `ModuleFunction` or
    a `_ClosureProxy` is invoked and its result pushed instead.
  - A bare Python callable is **not** a valid callee: it is refused as
    `Cannot call non-function`, the same as any non-function value (#412 phase
    2). Only closures and the two wrapper types above are callable.
  - Runtime error if the callee is not callable or if arity mismatches.

### CALL_METHOD
- Category: records / calls
- Stack behavior: pops record and args; injects record as self; invokes method
- Operands: field name, arg count
- Emitted by compiler: yes
- Purpose: call record methods with implicit `self`
- Notes / edge cases:
  - **A module is also a valid receiver**, not only a record — the export is
    resolved and called, with no `self` injected (#412 phase 2; this entry read
    "runtime error if not a record", which is true of every *other* receiver).
  - `self` is injected only when the receiver's `kind` is not `"module"`.
  - A `BuiltinMethod` field is invoked directly and its result pushed; a
    suspend sentinel it returns propagates as a yield rather than being pushed
    as a value.
  - **Strings, lists and maps are not receivers.** `"Value".to_upper()` is a
    type error in Nodus, not a method call.
  - Arguments are re-ordered back into source order, as for `CALL_VALUE`.
  - Runtime error if the receiver is neither record nor module, if the field is
    missing, or if the field is not callable.

### MAKE_CLOSURE
- Category: closure / function creation
- Stack behavior: pushes closure value
- Operands: function name (string)
- Emitted by compiler: yes (nested `fn` only)
- Purpose: create a closure capturing upvalues for a nested function
- Notes / edge cases: runtime error if capture context missing.

### THROW
- Category: exceptions
- Stack behavior: pops error value; transfers control to handler
- Operands: none
- Emitted by compiler: yes
- **Status: stable** (frozen at v1.0)
- Purpose: raise a runtime error with a user-provided value. Non-string values preserved as structured payload (`err.kind="thrown"`, `err.payload=<original value>`). String values become `err.message` directly.
- Notes / edge cases:
  - **`err` here is the record a `catch` block receives**, not the exception the
    opcode raises. `handle_exception` builds that record — `message`, `payload`,
    `kind`, `origin`, `line`, `column`, `stack` — from the raised
    `LangRuntimeError`, which itself has no `message` attribute (#412 phase 2).
  - **The transfer of control happens one level up.** THROW always raises; the
    handler stack is consulted by `execute()`'s except clause, so a THROW
    executed in isolation propagates rather than jumping.
  - `origin` is `"user"`, which is what separates a program's own `throw` from a
    VM fault in error reporting.
  - Ints, floats and bools are stringified into the message and carry **no**
    payload; records and lists carry the original value.
  - If uncaught, the error propagates to the host with a stack trace.

### YIELD
- Category: coroutines
- Stack behavior: pops yielded value; suspends current coroutine; returns value to resumer
- Operands: none
- Emitted by compiler: yes
- Purpose: pause coroutine execution and preserve its stack/frame state
- Notes / edge cases: runtime error if executed outside a resumed coroutine.

### RETURN
- Category: calls / returns
- Stack behavior: **depends which of three exits is taken** — see below. The
  ordinary one pops the return value, restores the caller, and pushes the value
  onto the caller's stack.
- Operands: none
- Emitted by compiler: yes
- Purpose: function return transfer
- Notes / edge cases:
  - **Three exits, in precedence order.**
    1. **Deferred by a `finally`** — when the top `handler_stack` entry belongs
       to *this* frame (`frame_depth == len(frames)`) and carries a non-zero
       `finally_ip`. The value is parked in `_deferred_return`, `ip` goes to the
       finally block, and **no frame is popped**: the finally body runs in it.
       A handler recorded at an *outer* frame depth must not capture this
       return, or a `finally` one level out would swallow it (#361).
    2. **Coroutine completion** — the frame is a coroutine's outermost
       (`return_ip is None`). The coroutine is marked `finished`, its state
       cleared, and `("return", value)` is returned to the scheduler. **Nothing
       is pushed.**
    3. **Ordinary** — pop the frame, push the value, `ip = frame.return_ip`.
  - Exits 2 and 3 restore a `cross_module_ctx` the frame carried, so a call that
    swapped the running chunk swaps it back (ASYNC-MOD-001, and the mechanism
    #691's fix installs on the way in).
  - Handler-stack entries belonging to the popped frame are discarded.
  - Runtime error `RETURN outside function` if executed outside a frame.

### HALT
- Category: control flow
- Stack behavior: none
- Operands: none
- Emitted by compiler: yes
- Purpose: terminate VM execution
- Notes / edge cases: program epilogue only. Returns `("halt", None)` and
  **does not advance `ip`**, which is what lets `execute()` tell a halted
  program from one that ran off the end of its code.

Unused/transitional/suspicious opcode notes:
- No dispatched opcode appears unused in current compiler output.
- There is **no dedicated `PRINT` opcode** in current VM; `print(...)` lowers to `CALL "print", 1` then `POP`.

### 3.1 Two opcodes were added after the freeze without the extension process

`FREEZE_PROPOSAL.md` §"What Freeze Means" requires three things of any post-freeze
opcode addition: a `BYTECODE_VERSION` bump, a new entry in this file, and an amendment
to that document. Two additions got none of the three:

| Opcode | Added | Commit |
|---|---|---|
| `MOD` | 2026-05-24 | `7520fc3` — modulo operator (BUG-010) |
| `RESET_LOCAL_IDX` | 2026-06-10 | `53da7f7` — per-iteration closure capture (PR #244) |

Both are real, reachable, and correct; the defect is in the record, not the runtime.
They are documented above and in `FREEZE_PROPOSAL.md` as of 2026-08-07.

`BYTECODE_VERSION` remains **4**, and was not bumped for either addition. The practical
consequence is narrow but real: the bytecode cache (`.nodus/cache/`) is keyed on that
version, so bytecode compiled by a newer nodus containing `MOD` or `RESET_LOCAL_IDX` is
accepted by an older 4.x nodus that has no handler for them. The failure surfaces as
`Unknown opcode: MOD` rather than the clean version-mismatch message the handshake
exists to produce. Deleting `.nodus/cache/` resolves it.

Tracked as [#366](https://github.com/Masterplanner25/Nodus/issues/366).
- Import/module behavior is intentionally non-opcode (compile/load phase), which is a deliberate design choice rather than missing VM feature.

## 4. Opcode Families
- Value loading:
  - `PUSH_CONST`, `LOAD`, `TO_BOOL`, `NOT`
- Storage:
  - `STORE`, `STORE_ARG`, plus expression cleanup via `POP`
- Branching:
  - `JUMP`, `JUMP_IF_FALSE`, `JUMP_IF_TRUE`, `HALT`
- Iteration:
  - `GET_ITER`, `ITER_NEXT`
- Function calls:
  - `CALL`, `CALL_VALUE`, `CALL_METHOD`, `RETURN`, `STORE_ARG`, `YIELD`
- Exceptions:
  - `SETUP_TRY`, `POP_TRY`, `FINALLY_END`, `THROW`
- Arithmetic/comparison core:
  - `ADD`, `SUB`, `MUL`, `DIV`, `NEG`, `EQ`, `NE`, `LT`, `GT`, `LE`, `GE`
- Collection construction/indexing/mutation:
  - `BUILD_LIST`, `BUILD_MAP`, `BUILD_RECORD`, `BUILD_MODULE`, `INDEX`, `INDEX_SET`, `LOAD_FIELD`, `STORE_FIELD`
- Module-related behavior:
  - no module opcode family; import and namespace aliasing are compiler/loader responsibilities.

Design characterization:
- Bytecode stays intentionally small by pushing some semantics into compiler lowering (for loops, imports, namespaced access).
- Families are coherent and orthogonal enough for current language scope.

## 5. Compiler-to-VM Mapping
High-level construct to opcode shape (actual lowering patterns):

- `let x = expr`
  - `expr...` then `STORE x`

- Arithmetic expression `a + b * c`
  - load/const for operands in evaluation order
  - `MUL` then `ADD`

- `if / else`
  - `cond...`
  - `JUMP_IF_FALSE else_target`
  - then-branch
  - `JUMP end`
  - else-branch

- `while`
  - loop_start:
  - `cond...`
  - `JUMP_IF_FALSE loop_end`
  - body
  - `JUMP loop_start`

- `for (init; cond; inc) { body }`
  - parser lowers to AST equivalent of:
    - `init`
    - `while (cond_or_true) { body; inc }`
  - compiler then emits normal `while` pattern.

- `for name in iterable { body }`
  - emit `iterable`, `GET_ITER`
  - loop_start: `ITER_NEXT end`, `STORE name`, body, `JUMP loop_start`

- Function definition / call / return
  - Program starts with bootstrap `JUMP main_start`.
  - Each function body compiled first at fixed address.
  - Function prologue: repeated `STORE_ARG param` (reverse param order).
  - Default epilogue: `PUSH_CONST nil`, `RETURN`.
  - Call site: args pushed left-to-right, then `CALL name, argc`.
  - Closure call site: callee value pushed, args pushed left-to-right, then `CALL_VALUE argc`.
  - Nested function definition emits `MAKE_CLOSURE` then stores into local/global.
  - Return site: `RETURN`.
  - `try/catch` lowers to `SETUP_TRY handler`, body, `POP_TRY`, `JUMP end`, handler block.
  - `try/catch/finally` lowers to `SETUP_TRY handler finally`, body, `POP_TRY`, handler block, `JUMP finally`, finally block, `FINALLY_END`.

- List literal `[a, b, c]`
  - emit `a`, `b`, `c`
  - `BUILD_LIST 3`

- Map literal `{k1: v1, k2: v2}`
  - emit `k1`, `v1`, `k2`, `v2`
  - `BUILD_MAP 2`

- Record literal `record { name: "a", age: 2 }`
  - emit `"name"`, `"a"`, `"age"`, `2`
  - `BUILD_RECORD 2`

- Indexing read `obj[idx]`
  - emit `obj`, emit `idx`, `INDEX`

- Indexing write `obj[idx] = value`
  - emit `obj`, `idx`, `value`, `INDEX_SET`
  - result value remains on stack (assignment expression semantics).

- Field access `rec.name`
  - emit `rec`, `LOAD_FIELD name`

- Field assignment `rec.name = value`
  - emit `rec`, `value`, `STORE_FIELD name`

- Method call `rec.method(...)`
  - emit `rec`, args..., `CALL_METHOD method, argc`

- Logical operators with short-circuiting
  - `a && b`:
    - evaluate `a`
    - `JUMP_IF_FALSE false_branch`
    - evaluate `b`; `TO_BOOL`; `JUMP end`
    - false_branch: `PUSH_CONST false`
  - `a || b`:
    - evaluate `a`
    - `JUMP_IF_TRUE true_branch`
    - evaluate `b`; `TO_BOOL`; `JUMP end`
    - true_branch: `PUSH_CONST true`

- Unary minus
  - `-x`:
    - evaluate `x`
    - `NEG`

- `import "..."` / `import { name } from "..."` / `import "..." as mod`
  - No bytecode emitted directly.
  - Loader resolves imports before compile; imported AST merged.
  - Module names are qualified at compile time to avoid cross-module collisions.
  - Exports are enforced by loader; non-exported imports raise a clear error.

- `import "..." as mod`, `mod.name`, `mod.fn(...)`
  - Alias represented by compiler-only `ModuleAlias` statements.
  - Compiler resolves `mod.member` to qualified global symbol name and emits normal `LOAD` / `CALL`.
  - No dedicated namespace opcode.
- Closures
  - Captured variables are boxed in runtime cells and accessed via `LOAD_UPVALUE` / `STORE_UPVALUE`.
  - Closure values are created with `MAKE_CLOSURE` and invoked with `CALL_VALUE`.
- Exceptions
  - `SETUP_TRY`, `POP_TRY`, and `FINALLY_END` manage a handler stack and finally execution.
  - `THROW` raises a runtime error and jumps to the nearest handler.

## 6. Stack Discipline Assessment
- Overall stack effects are mostly easy to reason about:
  - binary ops and comparisons follow standard 2-pop/1-push pattern.
  - statement-level pops are explicit.
- Highest stack complexity areas:
  - short-circuit lowering (`JUMP_IF_*` + synthesized booleans).
  - function argument/parameter transfer (`CALL` + `STORE_ARG` reversal).
  - collection builders (reverse pop/reverse list/map pair handling).
- Any instruction doing too much:
  - `CALL` is the most overloaded (dispatches both user functions and builtins).
  - `INDEX_SET` multiplexes both list and map mutation semantics.
- Robustness for growth:
  - Good for near-term scripting features.
  - Debuggability remains manageable due to code location tracking and explicit control-flow instructions.

## 7. Architectural Assessment of the Instruction Set
- Coherence:
  - Strongly coherent for current language needs; instructions map cleanly to expression/statement lowering.
- Extensibility:
  - Moderate-to-good: many future language constructs can still be lowered without new opcodes.
- Likely stability:
  - Core arithmetic/flow/call opcodes look stable.
  - Likely change pressure is in module semantics, debugging tooling, and call/index behavior edge policies.
- VM cleanliness:
  - Dispatch remains concise and understandable.
- Future opcode pressure:
  - Practical scripting path may need few new opcodes.
  - Research/debug tooling path may introduce trace/introspection opcodes or richer call variants.

## 8. Risks and Weak Spots
- `CALL` overloading user and builtin paths:
  - Works now, but can blur profiling/debug and capability control concerns.
- Compile-time module alias resolution:
  - No runtime namespace object means limited module introspection and weaker modular boundaries.
  - Module-qualified globals and export enforcement improve predictability without VM changes.
- Host-language semantic leakage:
  - Arithmetic/comparison behavior depends on Python operations for mixed types.
- Implicit import-by-flattening model:
  - No opcode-level module boundary; scaling module semantics may stress compile/load pipeline.
- Stack reasoning around assignment expressions:
  - `STORE` + `LOAD` pattern for assignment values is correct but can become subtle in more complex expression forms.

## 9. Suggested Next Bytecode Moves

### A. If Nodus remains a practical scripting language
- Add optional bytecode dump/debug mode (no semantic change).
  - Improves operability and script debugging.
- Introduce explicit call op variants (`CALL_USER`, `CALL_BUILTIN`) if diagnostics/security needs grow.
  - Reduces `CALL` overloading risk.
- Keep import handling out of VM, but formalize compiler contract for alias/export resolution.
  - Preserves small opcode surface while hardening module behavior.
- Add standardized stack-effect comments/tests per opcode.
  - Prevents subtle regressions as language grows.

### B. If Nodus moves toward VM/language research
- Define opcode metadata table (stack in/out, operand schema, effect tags).
  - Enables analysis, verification, and experiment tooling.
- Consider introducing a typed IR stage before bytecode.
  - Supports optimization and alternative lowering experiments.
- Split call and index opcodes by semantic domain if experimenting with specialization.
  - Improves performance and observability experimentation.
- Add optional trace opcodes/hooks for deterministic step-by-step VM research.
  - Useful for benchmarking and debugging instrumentation.

### C. If Nodus grows a larger module/tooling ecosystem
- Add per-instruction source-file identity alongside line/col (currently mainly one `source_path`).
  - Better imported-module diagnostics.
- Stabilize bytecode format/versioning if cross-tool interoperability matters.
  - Enables external tooling and cached compilation.
- Provide machine-readable execution traces keyed by opcode index.
  - Supports IDE/debugger integration.
- Separate loader/module metadata from compiler core.
  - Keeps bytecode contract stable while module system evolves.

## 10. Final Verdict
- Estimated opcode count (exact from VM dispatch): **49** (47 at the v1.0 freeze, plus the two post-freeze additions `MOD` and `RESET_LOCAL_IDX` — see §3.1).
- Current maturity of instruction set: **maturing and still disciplined**.
- Structural status: VM feels **largely complete for early practical scripting**, not rapidly chaotic; next pressure point is less “new core opcodes” and more modular/runtime refactoring around loader, diagnostics, and call semantics.

## Appendix: Quick Opcode Table
| Opcode | Category | Stack effect (conceptual) | Emitted by compiler? |
|---|---|---|---|
| PUSH_CONST | constants | `... -> ..., v` | yes |
| LOAD | variable access | `... -> ..., value` | yes |
| FRAME_SIZE | frame setup | no stack change | yes |
| LOAD_LOCAL | variable access (name-keyed) | `... -> ..., value` | ⛔ Removed in v1.0 |
| LOAD_LOCAL_IDX | variable access (slot-indexed) | `... -> ..., value` | yes |
| STORE_LOCAL_IDX | variable access (slot-indexed) | `..., v -> ...` | yes |
| RESET_LOCAL_IDX | variable access (slot-indexed) | no stack change | yes |
| LOAD_UPVALUE | closure access | `... -> ..., value` | yes |
| STORE | variable access | `..., v -> ...` | yes |
| STORE_UPVALUE | closure access | `..., v -> ...` | yes |
| STORE_ARG | calls | `..., arg -> ...` | yes |
| POP | stack/control | `..., v -> ...` | yes |
| ADD | arithmetic | `..., a, b -> ..., a+b` | yes |
| SUB | arithmetic | `..., a, b -> ..., a-b` | yes |
| MUL | arithmetic | `..., a, b -> ..., a*b` | yes |
| DIV | arithmetic | `..., a, b -> ..., a/b` | yes |
| MOD | arithmetic | `..., a, b -> ..., a%b` | yes |
| EQ | comparisons | `..., a, b -> ..., bool` | yes |
| NE | comparisons | `..., a, b -> ..., bool` | yes |
| LT | comparisons | `..., a, b -> ..., bool` | yes |
| GT | comparisons | `..., a, b -> ..., bool` | yes |
| LE | comparisons | `..., a, b -> ..., bool` | yes |
| GE | comparisons | `..., a, b -> ..., bool` | yes |
| JUMP | control flow | no stack change | yes |
| JUMP_IF_FALSE | control flow | `..., cond -> ...` | yes |
| JUMP_IF_TRUE | control flow | `..., cond -> ...` | yes |
| GET_ITER | iteration | `..., iterable -> ..., iter` | yes |
| ITER_NEXT | iteration | `..., iter -> ..., value` | yes |
| SETUP_TRY | exceptions | no stack change | yes |
| POP_TRY | exceptions | no stack change | yes |
| FINALLY_END | exceptions | no stack change (or full return) | yes |
| TO_BOOL | logical | `..., v -> ..., bool` | yes |
| NOT | logical | `..., v -> ..., bool` | yes |
| NEG | arithmetic | `..., v -> ..., -v` | yes |
| BUILD_LIST | collections | `..., items[n] -> ..., list` | yes |
| BUILD_MAP | collections | `..., k1,v1,... -> ..., map` | yes |
| BUILD_RECORD | records | `..., k1,v1,... -> ..., record` | yes |
| BUILD_MODULE | module construction | `..., k1,v1,... -> ..., module_record` | yes |
| INDEX | collections | `..., seq, idx -> ..., value` | yes |
| INDEX_SET | mutation | `..., seq, idx, v -> ..., v` | yes |
| LOAD_FIELD | records | `..., rec -> ..., value` | yes |
| STORE_FIELD | records | `..., rec, v -> ..., v` | yes |
| CALL | calls | args consumed; return pushed | yes |
| CALL_VALUE | calls | args consumed; return pushed | yes |
| CALL_METHOD | records/calls | args consumed; return pushed | yes |
| THROW | exceptions | `..., err -> ...` | yes |
| YIELD | coroutines | yielded value returned to resumer | yes |
| RETURN | calls | return value passed to caller | yes |
| MAKE_CLOSURE | closures | `... -> ..., closure` | yes |
| HALT | control flow | terminate VM | yes |

## Opcode Maturity Snapshot
- Instruction-set classification: **frozen at v1.0**.
- All 49 active opcodes are **stable**. Zero provisional opcodes remain.
- `BYTECODE_VERSION = 4`. Future opcodes require a version bump and FREEZE_PROPOSAL.md amendment.
- Most load-bearing opcode families/opcodes:
1. `CALL`/`RETURN`/`STORE_ARG` (function model, builtins, recursion)
2. `JUMP` + `JUMP_IF_FALSE` + `JUMP_IF_TRUE` (all structured control flow + short-circuit logic)
3. `LOAD`/`STORE` (globals/locals variable semantics)
4. `BUILD_LIST`/`BUILD_MAP` + `INDEX`/`INDEX_SET` (core collection scripting workflows)
5. `PUSH_CONST` + arithmetic/comparison core (`ADD`..`GE`) (expression engine foundation)

## Removed Opcodes

### LOAD_LOCAL
- **Deprecated in:** v0.8.0
- **Removed in:** v1.0
- **Replaced by:** `LOAD_LOCAL_IDX`
- **Reason:** Name-keyed local variable access replaced by slot-indexed access
  (`LOAD_LOCAL_IDX`). The compiler now always emits `LOAD_LOCAL_IDX` for
  function-local variables. The `_op_load_local` VM handler was replaced with a
  `RuntimeError` tombstone directing users to recompile.
- Any bytecode containing `LOAD_LOCAL` will raise:
  `RuntimeError: LOAD_LOCAL opcode encountered ... Recompile your source ...`

