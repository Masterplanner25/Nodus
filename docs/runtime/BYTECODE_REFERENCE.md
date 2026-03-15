# Nodus Bytecode Reference

## 1. Executive Summary
Nodus uses bytecode as the execution contract between the parser/compiler front-end and the stack VM runtime (`compiler.py` -> `optimizer.py` -> `vm.py`). The compiler lowers AST nodes into tuple instructions, the optimizer rewrites bytecode without changing semantics, and the VM dispatch loop executes the optimized instruction stream with a value stack plus call frames. The current instruction set is **small-to-medium and maturing**: still compact, but now broad enough to support control flow, functions, short-circuit logic, mutable collections, and runtime services through builtins.

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
  - Raises runtime name error if undefined.
  - Names may be module-qualified (e.g., `__mod0__name`) after compile-time resolution.

### LOAD_LOCAL
- Category: variable access (fast path)
- Stack behavior: pushes local variable value
- Operands: variable name (string)
- Emitted by compiler: yes
- Purpose: fast local variable read inside functions, bypassing the 4-dict probe in `load_name()`
- Notes / edge cases:
  - Only emitted when the compiler has confirmed the symbol is `scope == "local"` and the access is inside a function scope (`in_function_scope()`).
  - Reads directly from `frame.locals[name]`, unwrapping `Cell` / `LiveBinding` as needed.
  - Must not be emitted for block-level locals at module scope (those still use `LOAD`).

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
- Notes / edge cases: VM errors if no active call frame.

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
- Purpose: numeric addition and string concatenation (host-language behavior)
- Notes / edge cases: type behavior inherits Python `+` semantics at runtime.

### SUB
- Category: arithmetic
- Stack behavior: pops two, pushes difference
- Operands: none
- Emitted by compiler: yes (via `op_map`)
- Purpose: subtraction
- Notes / edge cases: unary minus uses dedicated `NEG` opcode rather than `SUB`.

### MUL
- Category: arithmetic
- Stack behavior: pops two, pushes product
- Operands: none
- Emitted by compiler: yes (via `op_map`)
- Purpose: multiplication
- Notes / edge cases: standard numeric multiplication semantics from host runtime.

### DIV
- Category: arithmetic
- Stack behavior: pops two, pushes quotient
- Operands: none
- Emitted by compiler: yes (via `op_map`)
- Purpose: division
- Notes / edge cases: host float division behavior.

### EQ
- Category: comparisons
- Stack behavior: pops two, pushes boolean equality
- Operands: none
- Emitted by compiler: yes (via `op_map`)
- Purpose: `==`
- Notes / edge cases: Python value equality semantics.

### NE
- Category: comparisons
- Stack behavior: pops two, pushes boolean inequality
- Operands: none
- Emitted by compiler: yes (via `op_map`)
- Purpose: `!=`
- Notes / edge cases: Python value inequality semantics.

### LT
- Category: comparisons
- Stack behavior: pops two, pushes `a < b`
- Operands: none
- Emitted by compiler: yes (via `op_map`)
- Purpose: `<`
- Notes / edge cases: type mismatch errors come from host comparisons.

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
- Notes / edge cases: uses VM truthiness function.

### JUMP_IF_TRUE
- Category: boolean / logical flow
- Stack behavior: pops condition; jumps if truthy
- Operands: absolute target IP
- Emitted by compiler: yes
- Purpose: `||` short-circuit path
- Notes / edge cases: only needed for logical-OR lowering.

### GET_ITER
- Category: iteration
- Stack behavior: pops iterable, pushes iterator
- Operands: none
- Emitted by compiler: yes
- Purpose: obtain an iterator for `for name in iterable` loops
- Notes / edge cases:
  - Lists are iterable by default.
  - Records can provide `__iter__` (returns list or record with `__next__`) or `__next__` directly.
  - Runtime error if value is not iterable.

### ITER_NEXT
- Category: iteration
- Stack behavior: pushes next value or jumps if finished
- Operands: end target IP
- Emitted by compiler: yes
- Purpose: advance iterator and load next item
- Notes / edge cases:
  - For list iterators, end is reached when index exceeds length.
  - For record iterators, `__next__` should return `nil` to signal completion.
  - Runtime error if iterator is unsupported.

### SETUP_TRY
- Category: exceptions
- Stack behavior: no stack change
- Operands: handler IP (absolute)
- Emitted by compiler: yes
- Purpose: push an exception handler for the current frame
- Notes / edge cases: runtime error if handler IP is invalid.

### POP_TRY
- Category: exceptions
- Stack behavior: no stack change
- Operands: none
- Emitted by compiler: yes
- Purpose: remove the most recent exception handler
- Notes / edge cases: runtime error if no handler exists.

### TO_BOOL
- Category: boolean / logical flow
- Stack behavior: pops value, pushes normalized boolean
- Operands: none
- Emitted by compiler: yes
- Purpose: ensure `&&`/`||` yield boolean values
- Notes / edge cases: central to current “real boolean semantics” behavior.

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
- Notes / edge cases: expects a numeric value; host-language numeric negation errors will surface if applied to non-numbers.

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
- Notes / edge cases: key type validated (string/number); ordering preserved by reverse pass.

### BUILD_RECORD
- Category: records
- Stack behavior: pops key/value pairs, pushes record
- Operands: field count
- Emitted by compiler: yes
- Purpose: record literal construction
- Notes / edge cases: keys must be strings.

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
- Notes / edge cases: runtime error if not a record or field missing.

### STORE_FIELD
- Category: records
- Stack behavior: pops value and record, pushes assigned value
- Operands: field name
- Emitted by compiler: yes
- Purpose: field assignment (`record.field = value`)
- Notes / edge cases: runtime error if not a record or field missing.

### CALL
- Category: calls / returns
- Stack behavior: user fn path creates frame and transfers control; builtin path pops args and pushes return
- Operands: function name, arg count
- Emitted by compiler: yes
- Purpose: user-defined and builtin function invocation
- Notes / edge cases: no first-class function values in bytecode; callee resolved to name at compile time.

### CALL_VALUE
- Category: calls / returns
- Stack behavior: pops callee value; arguments already on stack; invokes closure or errors
- Operands: arg count
- Emitted by compiler: yes
- Purpose: call closures and other runtime function values
- Notes / edge cases: runtime error if callee is not a closure or if arity mismatches.

### CALL_METHOD
- Category: records / calls
- Stack behavior: pops record and args; injects record as self; invokes method
- Operands: field name, arg count
- Emitted by compiler: yes
- Purpose: call record methods with implicit `self`
- Notes / edge cases: runtime error if not a record, missing field, or non-function.

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
- Purpose: raise a runtime error with a user-provided value
- Notes / edge cases: if uncaught, error propagates to host with stack trace.

### YIELD
- Category: coroutines
- Stack behavior: pops yielded value; suspends current coroutine; returns value to resumer
- Operands: none
- Emitted by compiler: yes
- Purpose: pause coroutine execution and preserve its stack/frame state
- Notes / edge cases: runtime error if executed outside a resumed coroutine.

### RETURN
- Category: calls / returns
- Stack behavior: pops return value; restores caller; pushes return value to caller stack
- Operands: none
- Emitted by compiler: yes
- Purpose: function return transfer
- Notes / edge cases: runtime error if executed outside a frame.

### HALT
- Category: control flow
- Stack behavior: none
- Operands: none
- Emitted by compiler: yes
- Purpose: terminate VM execution
- Notes / edge cases: program epilogue only.

Unused/transitional/suspicious opcode notes:
- No dispatched opcode appears unused in current compiler output.
- There is **no dedicated `PRINT` opcode** in current VM; `print(...)` lowers to `CALL "print", 1` then `POP`.
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
  - `SETUP_TRY`, `POP_TRY`, `THROW`
- Arithmetic/comparison core:
  - `ADD`, `SUB`, `MUL`, `DIV`, `NEG`, `EQ`, `NE`, `LT`, `GT`, `LE`, `GE`
- Collection construction/indexing/mutation:
  - `BUILD_LIST`, `BUILD_MAP`, `BUILD_RECORD`, `INDEX`, `INDEX_SET`, `LOAD_FIELD`, `STORE_FIELD`
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
  - `SETUP_TRY` and `POP_TRY` manage a handler stack.
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
- Estimated opcode count (exact from VM dispatch): **42**.
- Current maturity of instruction set: **maturing and still disciplined**.
- Structural status: VM feels **largely complete for early practical scripting**, not rapidly chaotic; next pressure point is less “new core opcodes” and more modular/runtime refactoring around loader, diagnostics, and call semantics.

## Appendix: Quick Opcode Table
| Opcode | Category | Stack effect (conceptual) | Emitted by compiler? |
|---|---|---|---|
| PUSH_CONST | constants | `... -> ..., v` | yes |
| LOAD | variable access | `... -> ..., value` | yes |
| LOAD_LOCAL | variable access (fast path) | `... -> ..., value` | yes |
| LOAD_UPVALUE | closure access | `... -> ..., value` | yes |
| STORE | variable access | `..., v -> ...` | yes |
| STORE_UPVALUE | closure access | `..., v -> ...` | yes |
| STORE_ARG | calls | `..., arg -> ...` | yes |
| POP | stack/control | `..., v -> ...` | yes |
| ADD | arithmetic | `..., a, b -> ..., a+b` | yes |
| SUB | arithmetic | `..., a, b -> ..., a-b` | yes |
| MUL | arithmetic | `..., a, b -> ..., a*b` | yes |
| DIV | arithmetic | `..., a, b -> ..., a/b` | yes |
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
| TO_BOOL | logical | `..., v -> ..., bool` | yes |
| NOT | logical | `..., v -> ..., bool` | yes |
| NEG | arithmetic | `..., v -> ..., -v` | yes |
| BUILD_LIST | collections | `..., items[n] -> ..., list` | yes |
| BUILD_MAP | collections | `..., k1,v1,... -> ..., map` | yes |
| BUILD_RECORD | records | `..., k1,v1,... -> ..., record` | yes |
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
- Instruction-set classification: **maturing**.
- VM lifecycle placement: closest to **prototype VM language transitioning into early real scripting runtime**.
- Most load-bearing opcode families/opcodes today:
1. `CALL`/`RETURN`/`STORE_ARG` (function model, builtins, recursion)
2. `JUMP` + `JUMP_IF_FALSE` + `JUMP_IF_TRUE` (all structured control flow + short-circuit logic)
3. `LOAD`/`STORE` (globals/locals variable semantics)
4. `BUILD_LIST`/`BUILD_MAP` + `INDEX`/`INDEX_SET` (core collection scripting workflows)
5. `PUSH_CONST` + arithmetic/comparison core (`ADD`..`GE`) (expression engine foundation)

