# Nodus v4.0 — Design Doc 09: IEEE 754 Float Division

**Phase:** 1 (design docs)
**Status:** Locked
**Implements:** Decision 10 (IEEE 754 Float Division) from `00-phase-0-decisions.md`
**Date:** 2026-05-26
**Maintainer:** Shawn Knight (Masterplanner25)

---

## Problem statement

v4.0 changes float division-by-zero behavior from throwing a runtime
error to returning IEEE 754 infinity. Decision 10 (Phase 0) locked the
high-level shape; this doc specifies the implementation, the math
function additions, the integer division behavior, and the migration
story.

This is the simplest of the four v4.0 breaking changes. The user-facing
change is small (one operator behavior, three new constants, three new
helpers) but the conceptual shift matters: Nodus aligns with the IEEE
754 consensus that the rest of the modern language ecosystem follows
(JavaScript, C, Rust, Go, Java, Swift). Python is the outlier.

---

## What Phase 0 already settled

From Decision 10:

- `1.0 / 0.0` returns `inf` (positive infinity)
- `0.0 / 0.0` returns `nan`
- `-1.0 / 0.0` returns `-inf` (negative infinity)
- New stdlib functions: `math.is_nan(x)`, `math.is_inf(x)`,
  `math.is_finite(x)`
- New stdlib constants: `math.nan`, `math.infinity`,
  `math.neg_infinity`
- Breaking: code catching the previous throw will silently get inf/nan

This doc resolves:

- Integer division-by-zero behavior (different from float)
- Float and integer modulo by zero
- Math function behavior outside division (sqrt, log, pow — unchanged)
- Migration story
- Bytecode impact (none)

---

## Bytecode impact

**No new opcodes required. `BYTECODE_VERSION` stays at 4.**

Float division is the existing arithmetic opcode (DIV or whatever it's
named in the current VM). The semantic change is in the opcode's
implementation: it stops checking for zero divisor and lets IEEE 754
semantics produce inf/nan naturally. No bytecode shape changes; existing
v3.x `.ndbc` files load and run in the v4.0 VM (with the new division
semantics applying to all float divisions, including those in pre-v4.0
bytecode).

The new math functions (`is_nan`, `is_inf`, `is_finite`) and constants
are registered as standard stdlib entries through the existing builtin
registry. User code accesses them via the existing `CALL_BUILTIN` and
load-module opcodes.

---

## Float division specification

### Division-by-zero behavior

```nodus
1.0 / 0.0    // inf
-1.0 / 0.0   // -inf
0.0 / 0.0    // nan
2.5 / 0.0    // inf
-3.7 / 0.0   // -inf
```

The sign of infinity follows IEEE 754 rules:
- Positive numerator / +0.0 → +inf
- Positive numerator / -0.0 → -inf
- Negative numerator / +0.0 → -inf
- Negative numerator / -0.0 → +inf
- Zero / Zero → nan (regardless of zero signs)

Nodus's existing float representation supports signed zero per IEEE 754;
the division operator respects the signs.

### Float modulo by zero

```nodus
5.0 % 0.0    // nan
0.0 % 0.0    // nan
-5.0 % 0.0   // nan
```

IEEE 754 specifies remainder of any value by zero is nan. Nodus follows
this.

### Other arithmetic with inf/nan

Standard IEEE 754 propagation:

```nodus
math.infinity + 1.0           // inf
math.infinity * 2.0           // inf
math.infinity * 0.0           // nan
math.infinity - math.infinity // nan
math.nan + 1.0                // nan (nan propagates)
math.nan == math.nan          // false (nan never equals anything, including itself)
math.nan != math.nan          // true (the only way to test for nan)
```

The last point is critical: `nan == nan` is `false` per IEEE 754. This is
why `math.is_nan(x)` is necessary; users cannot check for nan with
ordinary equality.

### Float comparison with inf/nan

```nodus
math.infinity > 1000000000.0  // true
math.infinity > math.infinity // false
math.infinity == math.infinity // true
math.nan > 1.0                 // false
math.nan < 1.0                 // false
math.nan == 1.0                // false
```

Any comparison involving nan returns false (except `!=`, which returns
true). Infinity compares normally.

---

## Integer division specification

Integer division by zero behaves **differently** from float division.

### Why the difference

Integers have no representation of infinity or NaN. IEEE 754 defines
floating-point semantics; integer arithmetic has no analogous standard.
Producing inf/nan for integer division would either require integers to
have inf/nan values (a massive change to the type system) or coerce the
result to float silently (surprising, hides bugs).

The simpler, more correct choice: integer division by zero produces an
err record.

### Integer division-by-zero behavior

```nodus
let x = 1i / 0i   // err record returned
let y = 5i / 0i   // err record returned
```

The err record:

```nodus
err {
    kind: "math_error",
    message: "Integer division by zero",
    path: ...,
    line: ...,
    column: ...,
    stack: ...,
    origin: "vm",
    payload: {
        category: "division_by_zero",
        operation: "div",
        numerator: 1,
        denominator: 0
    }
}
```

### Integer modulo by zero

Same behavior:

```nodus
let r = 5i % 0i   // err record with category: "division_by_zero"
```

### Mixed-type division (int by float-zero or float by int-zero)

```nodus
1i / 0.0    // The int is coerced to float; result is inf (IEEE 754 path)
1.0 / 0i    // The int 0 is coerced to float 0.0; result is inf (IEEE 754 path)
```

Mixed-type arithmetic follows existing v3.x coercion rules (int promotes
to float). Once both operands are floats, IEEE 754 applies. This means
users CAN get inf/nan from integer-zero division by writing `1i / 0.0`
explicitly — though this is unusual and probably unintentional.

The asymmetry is documented: `int / int` is strict (errs on zero); any
mixed or pure-float division is IEEE 754. Users who want IEEE 754 for
integer-style code can write `float(x) / float(y)` to opt in.

---

## New math functions and constants

### Functions

```nodus
math.is_nan(x)       // true if x is nan; false otherwise
math.is_inf(x)       // true if x is +inf or -inf; false otherwise
math.is_finite(x)    // true if x is neither nan nor inf; false otherwise
```

All three accept any numeric type. For integers, they always return
appropriate values: `is_nan(5i)` is false (integers can't be nan);
`is_inf(5i)` is false; `is_finite(5i)` is true.

For floats:

```nodus
math.is_nan(0.0 / 0.0)         // true
math.is_nan(1.0)               // false
math.is_inf(1.0 / 0.0)          // true
math.is_inf(-1.0 / 0.0)         // true
math.is_finite(1.0)             // true
math.is_finite(1.0 / 0.0)       // false
math.is_finite(0.0 / 0.0)       // false
```

### Constants

```nodus
math.nan              // float, the IEEE 754 NaN value
math.infinity         // float, positive infinity
math.neg_infinity     // float, negative infinity
```

These are module-level constants in `std:math`. Users import the module
(or alias it) and access via `math.infinity` etc.

Equality semantics:

```nodus
math.nan == math.nan          // false (correct per IEEE 754)
math.infinity == math.infinity // true
math.neg_infinity == -math.infinity // true
```

To test for nan, use `math.is_nan(x)`. To test for any non-finite value,
use `!math.is_finite(x)`.

---

## Math functions outside division — unchanged behavior

Decision 10 specifically addresses division. Other math functions that
could produce IEEE 754 special values keep their current v3.x behavior:

| Function | Input | v3.x and v4.0 behavior |
|---|---|---|
| `math.sqrt(-1.0)` | negative | err record (`category: "value_error"`) |
| `math.log(0.0)` | zero | err record (`category: "value_error"`) |
| `math.log(-1.0)` | negative | err record (`category: "value_error"`) |
| `math.pow(0, -1)` | undefined | err record (`category: "math_error"`) |

Rationale: these functions have a clear domain (positive reals for sqrt
and log, etc.). Returning nan for out-of-domain inputs would silently
propagate through subsequent calculations and hide bugs. Returning err
forces the caller to handle the case explicitly.

The asymmetry is intentional: division-by-zero is a single common case
where IEEE 754 inf/nan is genuinely useful (representing limits, slopes,
infinities in calculations). Other out-of-domain math operations are
better caught as errs.

This was the v3.0.2 eval's observation: division-by-zero was the only
arithmetic that threw instead of returning a value. The fix aligns
division with the rest of the float operations. Other math functions
were already correct.

---

## Migration impact

### Breaking change

Code that caught `Runtime error: Division by zero` silently changes
behavior in v4.0:

```nodus
// v3.x — works as expected (the try-catch handles the throw)
let result = try {
    let ratio = numerator / denominator
    return ratio
} catch (e) {
    return 0.0
}

// v4.0 — silently returns inf/nan when denominator is 0.0
let result = try {
    let ratio = numerator / denominator
    return ratio   // returns inf or nan; never throws
} catch (e) {
    return 0.0     // unreachable; the catch never fires for float division
}
```

The migration: explicitly check for non-finite values:

```nodus
// v4.0 idiomatic
let ratio = numerator / denominator
if !math.is_finite(ratio) {
    // handle the inf/nan case
    return 0.0
}
return ratio
```

### Migration patterns

The migration guide includes these patterns:

| v3.x | v4.0 |
|---|---|
| `try { x / y } catch { default }` | `let r = x / y; if !math.is_finite(r) { default } else { r }` |
| Float division known-safe (denominator validated upstream) | Unchanged; works the same |
| Integer division `5i / 0i` (was throw) | Still returns err; migration is only for FLOAT division |
| Defensive `if y == 0 { error_path }` before division | Unchanged; still works, and is actually more idiomatic now |

The third row matters: integer division by zero is unchanged in semantics
(still err). Users with integer-division code don't need to migrate.

### Documentation

`docs/migration/v3-to-v4.md` (Phase 4 deliverable) gets a section:

> ### Float division by zero now returns IEEE 754 infinity
>
> In v3.x, `1.0 / 0.0` threw a runtime error. In v4.0, it returns
> `math.infinity`. Code that wrapped float division in try-catch to
> handle the throw no longer triggers the catch; results silently
> propagate inf/nan through subsequent calculations.
>
> Use `math.is_finite(result)` to detect non-finite values:
> [pattern example]
>
> Integer division by zero (e.g., `5i / 0i`) is UNCHANGED; it still
> returns an err record.

---

## Implementation outline

### VM arithmetic opcode change

The VM's float-division opcode currently checks for zero divisor and
throws. The v4.0 change:

```python
# Before (v3.x)
def op_float_div(stack):
    b = stack.pop()
    a = stack.pop()
    if b == 0.0:
        raise RuntimeError("Division by zero")
    stack.push(a / b)

# After (v4.0)
def op_float_div(stack):
    b = stack.pop()
    a = stack.pop()
    stack.push(a / b)   # Python float division produces inf/nan per IEEE 754
```

Python's float division natively produces inf/nan. The change is removing
the check, not adding new logic.

### Integer division opcode

The integer-division opcode keeps the zero check but returns an err
record instead of a raw throw:

```python
def op_int_div(stack):
    b = stack.pop()
    a = stack.pop()
    if b == 0:
        return err_record(
            kind="math_error",
            message="Integer division by zero",
            category="division_by_zero",
            operation="div",
            numerator=a,
            denominator=b
        )
    stack.push(a // b)
```

The current v3.x behavior may have been a runtime throw; v4.0 converts
this to an err record per the broader v4.0 pattern (stdlib and runtime
errs as records, not throws). Verify current implementation during Phase
3B; adjust as needed.

### Math functions

`is_nan`, `is_inf`, `is_finite` map directly to Python's
`math.isnan`, `math.isinf`, `math.isfinite`. Constants `math.nan`,
`math.infinity`, `math.neg_infinity` are exported from Python's `math`
module (`math.nan`, `math.inf`, `-math.inf`).

### Test surface

Phase 3B test cases:

- All four corner cases of float div-by-zero (pos/0, neg/0, 0/0,
  +pos/-0)
- Modulo: float by zero, integer by zero
- Integer div-by-zero produces err record
- Mixed-type division (int/0.0 produces float inf via coercion)
- `is_nan`, `is_inf`, `is_finite` correctness for finite/infinite/nan
  inputs
- Constants `math.nan`, `math.infinity`, `math.neg_infinity` are correct
  values
- IEEE 754 arithmetic: nan propagates, inf arithmetic works
- nan != nan; infinity == infinity
- Comparison with nan returns false for `<`, `>`, `==`; true for `!=`

---

## Open implementation questions for Phase 3B

1. **Current integer division throw vs err.** Verify current v3.x
   integer div-by-zero behavior. If it throws, this doc's spec
   converts it to err record (consistent with v4.0 patterns). If it
   already errs, no change needed for integer path.

2. **Performance regression check.** Removing the zero-check in float
   division saves a comparison per division. Verify no performance
   regression elsewhere (Python's IEEE 754 path is implemented in C
   and should be as fast or faster than the explicit check).

3. **Bytecode disassembly output.** The disassembler should print `DIV`
   the same way; no opcode change. Verify disassembly tests don't
   need updates.

4. **Embedding API impact.** Python host code that catches Nodus's
   division-by-zero exception via the embedding API no longer sees it
   (because the exception isn't thrown). Document this in the
   embedding API migration notes.

---

## Cross-references

- `docs/design/v4/00-phase-0-decisions.md` Decision 10 (IEEE 754 float
  division)
- `docs/design/v4/13-err-record-location-fields.md` (sibling; the err
  records emitted by integer division benefit from the location fields
  that doc adds)
- `docs/language/LANGUAGE_SPEC.md` (Phase 4 update: division operator
  section gets IEEE 754 semantics; math module gains new functions and
  constants)
- `docs/migration/v3-to-v4.md` (Phase 4 deliverable: migration patterns
  for float division)
- `docs/governance/TECH_DEBT.md` (Phase 3B open questions appended)

---

**Phase 1 doc 09-ieee-754-division.md: COMPLETE.**
