# Nodus v4.0 — Design Doc 10: type() Naming Reconciliation

**Phase:** 1 (design docs)
**Status:** Locked
**Implements:** Decision 11 (type() naming reconciliation) from `00-phase-0-decisions.md`
**Date:** 2026-05-26
**Maintainer:** Shawn Knight (Masterplanner25)

---

## Problem statement

In v3.x, `type(1.0)` returns `"number"` — a legacy string from before
Nodus distinguished int from float at the type level. v4.0 corrects this:
`type(1.0)` returns `"float"`. This is the only row that changes in the
full type() enumeration table. This doc specifies the exact change, the
new math helpers for type introspection, and the migration story.

---

## What Phase 0 already settled

From Decision 11:

- `type(1.0)` returns `"float"` (was `"number"`)
- `type(1i)` returns `"int"` (unchanged)
- New stdlib helpers: `math.is_numeric(x)`, `math.is_int(x)`, `math.is_float(x)`
- Breaking: code that compared `type(x) == "number"` breaks silently

This doc resolves:

- Full type() enumeration table (all types, not just float)
- Exact behavior of the three new math helpers
- Migration patterns for the `"number"` string comparison
- Bytecode impact (none)

---

## Bytecode impact

**No new opcodes required. `BYTECODE_VERSION` stays at 4.**

`type()` is a builtin function called via the existing `CALL_BUILTIN`
opcode. The change is in the return value for float operands: the
implementation changes one string constant from `"number"` to `"float"`.
No opcode shape changes. No new VM machinery.

The three new math helpers (`is_numeric`, `is_int`, `is_float`) are
registered as standard stdlib entries through the existing builtin
registry. User code accesses them via the existing `CALL_BUILTIN` opcode.

---

## type() enumeration table

Complete specification of `type()` return values in v4.0:

| Value | v3.x return | v4.0 return | Changed? |
|---|---|---|---|
| `1i` | `"int"` | `"int"` | No |
| `1.0` | `"number"` | `"float"` | **YES** |
| `"hello"` | `"string"` | `"string"` | No |
| `true` | `"bool"` | `"bool"` | No |
| `false` | `"bool"` | `"bool"` | No |
| `nil` | `"nil"` | `"nil"` | No |
| `[1, 2]` | `"list"` | `"list"` | No |
| `{a: 1}` | `"record"` | `"record"` | No |
| `err { ... }` | `"err"` | `"err"` | No |
| a function | `"function"` | `"function"` | No |
| a closure | `"function"` | `"function"` | No |
| an iterator | `"iterator"` | `"iterator"` | No |

The only change is the float row. Everything else is stable.

### Examples

```nodus
type(1i)        // "int"
type(1.0)       // "float"   ← changed from "number"
type(2.5)       // "float"
type("hi")      // "string"
type(true)      // "bool"
type(nil)       // "nil"
type([])        // "list"
type({})        // "record"
```

---

## New math helpers

Three new functions in `std:math` for numeric type introspection:

### math.is_numeric(x)

Returns `true` if `x` is any numeric type (int or float); `false`
otherwise.

```nodus
math.is_numeric(1i)      // true
math.is_numeric(1.0)     // true
math.is_numeric(2.5)     // true
math.is_numeric("1")     // false
math.is_numeric(true)    // false
math.is_numeric(nil)     // false
```

This is the replacement for the v3.x pattern `type(x) == "number"`. Users
who want to accept either int or float use `math.is_numeric(x)`.

### math.is_int(x)

Returns `true` if `x` is an integer; `false` otherwise.

```nodus
math.is_int(1i)          // true
math.is_int(1.0)         // false
math.is_int(1)           // true  (unadorned integer literal is int)
math.is_int("1")         // false
```

### math.is_float(x)

Returns `true` if `x` is a float; `false` otherwise.

```nodus
math.is_float(1.0)       // true
math.is_float(2.5)       // true
math.is_float(1i)        // false
math.is_float(math.nan)  // true  (nan is a float)
math.is_float(math.infinity) // true
```

### Relationship to type()

These are convenience wrappers. They are equivalent to:

```nodus
math.is_numeric(x)  ⟺  type(x) == "int" or type(x) == "float"
math.is_int(x)      ⟺  type(x) == "int"
math.is_float(x)    ⟺  type(x) == "float"
```

The helpers exist because `math.is_numeric(x)` is more readable than
the two-part type check, and because the v3.x idiom `type(x) == "number"`
needs a clean migration target.

---

## Migration impact

### Breaking change

Code that inspects the type of float values by comparing the string
`"number"`:

```nodus
// v3.x — works (type(x) == "number" for floats)
if type(x) == "number" {
    compute_with_float(x)
}

// v4.0 — broken ("number" never matches anything; the branch never fires)
if type(x) == "number" {
    compute_with_float(x)   // unreachable
}
```

### Migration patterns

| v3.x | v4.0 |
|---|---|
| `type(x) == "number"` | `math.is_float(x)` |
| `type(x) == "number" or type(x) == "int"` | `math.is_numeric(x)` |
| `type(x) != "number"` | `!math.is_float(x)` |
| `match type(x) { "number" → ... }` | `match type(x) { "float" → ... }` |

The last row (match/switch on type strings) requires a literal string
change: `"number"` → `"float"`.

### How the failure manifests

The breaking change is **silent in most cases**: code that was checking
`type(x) == "number"` simply never matches. The branch that was meant to
handle floats never fires; the code falls through to whatever else
follows. There is no runtime error, only incorrect behavior.

The migration guide will emphasize this: grep for `"number"` in type
comparisons and update them.

### Grep pattern for migration

```
"number"
```

Search source files for the literal string `"number"`. Any occurrence in
a type comparison context needs updating to `"float"` or `math.is_float`.

---

## Implementation outline

### type() builtin change

The `type()` builtin implementation maps Python type to Nodus type string.
The change is one line:

```python
# Before (v3.x)
if isinstance(value, float):
    return "number"

# After (v4.0)
if isinstance(value, float):
    return "float"
```

### New math helpers

```python
def builtin_is_numeric(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)

def builtin_is_int(x):
    return isinstance(x, int) and not isinstance(x, bool)

def builtin_is_float(x):
    return isinstance(x, float)
```

Note: Python's `bool` is a subclass of `int`; the `isinstance(x, bool)`
exclusion prevents `true`/`false` from registering as numeric. This
matches Nodus's type semantics where booleans are not numbers.

### Test surface

Phase 3B test cases:

- `type(1.0)` returns `"float"` (not `"number"`)
- `type(1i)` returns `"int"` (unchanged)
- All other type() rows unchanged (spot-check each)
- `math.is_numeric(1i)` → true
- `math.is_numeric(1.0)` → true
- `math.is_numeric(true)` → false
- `math.is_numeric("1")` → false
- `math.is_int(1i)` → true; `math.is_int(1.0)` → false
- `math.is_float(1.0)` → true; `math.is_float(1i)` → false
- `math.is_float(math.nan)` → true
- `math.is_float(true)` → false
- bool is NOT numeric (both is_int and is_numeric return false for booleans)

---

## Open implementation questions for Phase 3B

1. **Integer literals without suffix.** Verify that unadorned integer
   literals (e.g., `1`, `42`) are represented as Python `int` in the VM
   and that `type(42)` returns `"int"` and `type(42.0)` returns `"float"`.
   The type dispatch must be clean between the two.

2. **nan and infinity type.** Verify `type(math.nan)` returns `"float"`
   and `type(math.infinity)` returns `"float"`. These are Python floats;
   the type() implementation should naturally return `"float"` without
   special-casing.

3. **Grep tooling for migration.** Decide whether the migration guide
   should include a recommended `rg`/grep pattern for user codebases, or
   whether a `nodus migrate` subcommand is in scope for Phase 4. The
   grep pattern is low-effort; the subcommand is out of scope for v4.0.

4. **Type string stability contract.** Decide whether type() return
   strings are part of the stable public API (i.e., will never change
   again). If yes, document this in `LANGUAGE_SPEC.md` as a stability
   guarantee. Recommendation: yes, lock them as stable with v4.0.

---

## Cross-references

- `docs/design/v4/00-phase-0-decisions.md` Decision 11 (type() naming
  reconciliation)
- `docs/design/v4/09-ieee-754-division.md` (sibling; `math.is_float(x)`
  is particularly useful for distinguishing nan/infinity results, which
  are floats)
- `docs/design/v4/11-equality-coercion.md` (sibling; equality coercion
  uses the same int/float distinction — the two docs are coherent)
- `docs/language/LANGUAGE_SPEC.md` (Phase 4 update: type() section gets
  the full enumeration table; math module gains new helpers)
- `docs/migration/v3-to-v4.md` (Phase 4 deliverable: grep pattern +
  migration table for "number" → "float")
- `docs/governance/TECH_DEBT.md` (Phase 3B open questions appended)

---

**Phase 1 doc 10-type-naming-reconciliation.md: COMPLETE.**
