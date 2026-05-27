# Nodus v4.0 — Design Doc 11: Equality Coercion Narrowing

**Phase:** 1 (design docs)
**Status:** Locked
**Implements:** Decision 12 (equality coercion narrowing) from `00-phase-0-decisions.md`
**Date:** 2026-05-26
**Maintainer:** Shawn Knight (Masterplanner25)

---

## Problem statement

In v3.x, the `==` operator coerces across type families: `0 == false`
returns `true`, `1 == true` returns `true`, `"" == false` returns `true`.
This is JavaScript-style loose equality — a known footgun that causes
silent bugs. v4.0 narrows `==` to coerce only within the number family
(int ↔ float). Cross-family coercions (number ↔ bool, number ↔ string,
etc.) are removed.

This is one of four v4.0 breaking changes. Unlike float-division or
type() naming, this change has a **large blast radius**: any code that
relied on cross-family equality will silently get a different answer.

---

## What Phase 0 already settled

From Decision 12:

- `1 == 1.0` remains `true` (number-family coercion preserved)
- `0 == false` becomes `false` (breaking)
- `1 == true` becomes `false` (breaking)
- `"" == false` becomes `false` (breaking)
- `"1" == 1` becomes `false` (breaking)
- New helpers: `type_eq(a, b)` and `bool.equal(value, bool_value)`
- No strict-equality operator (e.g., `===`) added to the language

This doc resolves:

- Full equality table across all type pairs
- nan/infinity equality semantics (IEEE 754, covered by doc 09)
- The two new helpers in detail
- Migration patterns
- Bytecode impact (none)

---

## Bytecode impact

**No new opcodes required. `BYTECODE_VERSION` stays at 4.**

`==` is the existing equality opcode. The semantic change is in the
opcode's implementation: the coercion logic is narrowed. No new opcodes.
No `BYTECODE_VERSION` bump. Existing `.ndbc` bytecode runs in the v4.0
VM with the new equality semantics.

The new helpers (`type_eq`, `bool.equal`) are registered as stdlib
entries accessed via the existing `CALL_BUILTIN` opcode.

---

## Equality table

### Number family (preserved coercion)

```nodus
1 == 1           // true  (int == int, exact)
1 == 1.0         // true  (int coerced to float; values equal)
1.0 == 1.0       // true  (float == float, exact)
2 == 2.0         // true
1 == 2.0         // false
```

### Number ↔ Bool (coercion removed)

```nodus
0 == false       // false  ← changed from true
1 == true        // false  ← changed from true
0 == true        // false  (was false; unchanged)
1 == false       // false  (was false; unchanged)
2 == true        // false  (was false; unchanged)
false == 0       // false  ← changed from true
true == 1        // false  ← changed from true
```

### Number ↔ String (coercion removed)

```nodus
"1" == 1         // false  ← changed (was true in some v3.x builds)
"0" == 0         // false
"1.0" == 1.0     // false
```

### Bool ↔ String (coercion removed)

```nodus
"true" == true   // false
"false" == false // false
"" == false      // false  ← changed from true
```

### Bool == Bool (no coercion needed; same type)

```nodus
true == true     // true
false == false   // true
true == false    // false
```

### Nil equality

```nodus
nil == nil       // true
nil == false     // false
nil == 0         // false
nil == ""        // false
```

### nan and infinity (IEEE 754, see doc 09)

```nodus
math.nan == math.nan          // false  (IEEE 754: nan never equals anything)
math.nan == 1.0               // false
math.infinity == math.infinity // true
math.infinity == 1.0          // false
```

### Same-type equality (no change from v3.x)

All same-type equality is unchanged:

```nodus
"hello" == "hello"   // true
"hello" == "world"   // false
[1, 2] == [1, 2]     // true  (element-wise)
{a: 1} == {a: 1}     // true  (field-wise)
```

---

## New helpers

### type_eq(a, b)

Returns `true` only if `a` and `b` have the same type AND are equal in
value — no coercion of any kind.

```nodus
type_eq(1, 1)          // true   (int == int)
type_eq(1, 1.0)        // false  (int vs float; type mismatch)
type_eq(0, false)      // false  (int vs bool; type mismatch)
type_eq(true, true)    // true
type_eq("hi", "hi")   // true
type_eq(nil, nil)      // true
type_eq(nil, false)    // false
```

`type_eq` is the strictest form: equivalent to `type(a) == type(b) and a == b`.
It is useful in pattern-matching contexts where float/int distinction
matters, or when migrating code that needs to verify no cross-type
equality slips through.

For nan: `type_eq(math.nan, math.nan)` returns `false` because
`math.nan == math.nan` is false per IEEE 754. Both are float; the type
test passes; the value test fails.

### bool.equal(value, bool_value)

Tests whether `value` is the specific bool `bool_value`, without any
coercion. The `bool_value` parameter must be a literal `true` or `false`
or a bool variable; passing a non-bool raises an err.

```nodus
bool.equal(x, true)    // true only if x IS the bool true (not 1, not "true")
bool.equal(x, false)   // true only if x IS the bool false (not 0, not nil)
bool.equal(1, true)    // false (int, not bool)
bool.equal(0, false)   // false (int, not bool)
bool.equal(nil, false) // false (nil, not bool)
```

This helper exists because `x == true` (under v4.0 semantics) returns
`false` when `x = 1`, which is correct — but migrating code that relied
on `if x == 1 { ... }` semantics needs an explicit bool check. Using
`bool.equal(x, true)` makes the intent clear.

`bool.equal` is most useful in validation code:

```nodus
// Explicitly verify a value is the bool true, not just truthy
if bool.equal(config.enabled, true) {
    // guaranteed x is actually boolean true, not 1 or "yes"
}
```

---

## What truthiness is NOT changed

This doc covers `==` (equality). Truthiness (how non-bool values behave
in `if` conditions) is a **separate decision not covered here**. In v3.x,
`if 0 { ... }` may or may not fire depending on truthiness rules. Whether
v4.0 changes those rules is out of scope for this doc and Decision 12.

This is an important distinction: removing cross-type `==` coercion does
not automatically make all truthiness strict. Developers who want strict
truthiness in conditions can use `bool.equal(x, true)` explicitly.

---

## Migration impact

### Breaking change severity

**High blast radius.** The `0 == false` and `1 == true` patterns appear
frequently in code that mixes boolean and numeric types — config validation,
feature flags, user input handling. Most occurrences will silently return
`false` instead of `true` in v4.0.

The failure mode is silent: no runtime error, just incorrect behavior
(conditions that should fire don't, or vice versa).

### Migration patterns

| v3.x | v4.0 |
|---|---|
| `x == false` (x is possibly int 0) | `bool.equal(x, false)` or `x == 0` depending on intent |
| `x == true` (x is possibly int 1) | `bool.equal(x, true)` or `x == 1` depending on intent |
| `if x == false` (testing falsiness) | `if !x` (unchanged; truthiness not affected) |
| `"" == false` | `false` always; remove the comparison |
| `type_eq(a, b)` not available | Use `type(a) == type(b) and a == b` |

### The intent split

When migrating `x == false`, the developer must decide intent:

1. **"Is x the boolean false?"** → `bool.equal(x, false)`
2. **"Is x the integer 0?"** → `x == 0`
3. **"Is x falsy?"** → `!x` (if truthiness rules cover the case)

The migration guide will make this split explicit.

### Grep pattern for migration

```
== false
== true
== 0
== 1
```

Search for these patterns. Flag each for review: determine whether the
comparison was relying on cross-family coercion and update accordingly.

---

## Implementation outline

### Equality opcode change

The equality opcode currently implements broad coercion. The v4.0 change
narrows it:

```python
# Before (v3.x) — simplified
def op_eq(stack):
    b = stack.pop()
    a = stack.pop()
    # tries to coerce across types
    stack.push(coerce_equal(a, b))

# After (v4.0) — number-family only
def op_eq(stack):
    b = stack.pop()
    a = stack.pop()
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) \
       and not isinstance(a, bool) and not isinstance(b, bool):
        stack.push(float(a) == float(b))
    else:
        stack.push(a == b)  # Python __eq__; same-type for non-numbers
```

The bool exclusion (`not isinstance(a, bool)`) is required because Python's
`bool` is a subclass of `int` — without the guard, `True == 1` would pass
the isinstance check and coerce.

### type_eq helper

```python
def builtin_type_eq(a, b):
    if type(a) is not type(b):
        return False
    return a == b
```

Uses Python's `type()` (exact type, not isinstance) to avoid bool/int
subclass confusion.

### bool.equal helper

```python
def builtin_bool_equal(value, bool_value):
    if not isinstance(bool_value, bool):
        return err_record(
            kind="type_error",
            message="bool.equal: second argument must be a bool",
            ...
        )
    return isinstance(value, bool) and value == bool_value
```

### Test surface

Phase 3B test cases:

- `1 == 1.0` → true (number coercion preserved)
- `0 == false` → false (cross-family removed)
- `1 == true` → false (cross-family removed)
- `"" == false` → false
- `"1" == 1` → false
- `nil == false` → false; `nil == nil` → true
- `type_eq(1, 1)` → true; `type_eq(1, 1.0)` → false
- `type_eq(0, false)` → false; `type_eq(true, true)` → true
- `bool.equal(true, true)` → true; `bool.equal(1, true)` → false
- `bool.equal(0, false)` → false; `bool.equal(false, false)` → true
- `bool.equal(x, 0)` → err (second arg is not bool)
- nan: `math.nan == math.nan` → false; `type_eq(math.nan, math.nan)` → false
- `!= ` operator: verify `0 != false` → true; `1 != 1.0` → false

---

## Open implementation questions for Phase 3B

1. **Python bool/int subclass guard.** Verify the bool exclusion in the
   equality opcode handles all cases: `True`, `False`, bool variables,
   and bool results of expressions. Python's `isinstance(True, int)` is
   `True` — the guard must be in place or the coercion check fires.

2. **Current v3.x coercion implementation.** Audit `coerce_equal` (or
   equivalent) in the current VM to understand all active cross-type
   coercions. Only number↔number coercion survives; all others are removed.
   Create a test for each removed coercion to verify it's gone.

3. **`!=` operator consistency.** Verify `!=` is implemented as `not (a == b)`
   using the same narrowed equality logic — not as a separate coercion path.
   `0 != false` must return `true` in v4.0.

4. **List and record equality.** List equality (`[1, 2] == [1, 2]`) uses
   element-wise comparison. Verify that element comparisons within a list
   also use the narrowed equality — i.e., `[0] == [false]` is `false` in
   v4.0. The narrowing must propagate into recursive equality checks.

5. **Truthiness unchanged.** Confirm that narrowing `==` does not affect
   the `if` condition evaluation path. `if 0 { ... }` behavior is governed
   by truthiness rules, not the `==` opcode. These are separate code paths;
   verify they don't share the coercion logic being changed.

---

## Cross-references

- `docs/design/v4/00-phase-0-decisions.md` Decision 12 (equality coercion
  narrowing)
- `docs/design/v4/09-ieee-754-division.md` (sibling; nan equality semantics
  — `nan == nan` → false — are a special case of this doc's rules)
- `docs/design/v4/10-type-naming-reconciliation.md` (sibling; both docs
  tighten the distinction between int and float in the type system)
- `docs/language/LANGUAGE_SPEC.md` (Phase 4 update: equality operator section
  gets the new rules; new helpers documented in builtin reference)
- `docs/migration/v3-to-v4.md` (Phase 4 deliverable: the intent-split
  migration pattern for `== false` / `== true`)
- `docs/governance/TECH_DEBT.md` (Phase 3B open questions appended)

---

**Phase 1 doc 11-equality-coercion.md: COMPLETE.**
