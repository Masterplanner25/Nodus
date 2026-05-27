# Nodus v4.0 — Design Doc 14: len() Returns int

**Phase:** 1 (design docs)
**Status:** Locked
**Implements:** V4_0_PLAN.md Tier 1 breaking change (Phase 3A item)
**Date:** 2026-05-27
**Maintainer:** Shawn Knight (Masterplanner25)

---

## Problem statement

In v3.x, `len()` returns a `float` because v3.x only had a single
numeric type. v3.0.0's integer type addition exposed this as a
misalignment: `len()` returns a count, counts are conceptually
integers, but `len()` returns a float.

v4.0 fixes this by making `len()` return `int`. This was on the
original V4_0_PLAN.md Tier 1 breaking change list but was omitted
from the initial 13 Phase 1 design docs. This doc closes that gap.

The change is small (one return-type change) but the migration
implications affect any code doing arithmetic on `len()` results.
Doing this as a deliberate breaking change with a design doc is the
right discipline.

This doc was added to Phase 1 retroactively (on 2026-05-27) when the
gap was identified during Phase 3 planning. Phase 1 is now 15 docs
total.

---

## What V4_0_PLAN.md already settled

From the Tier 1 breaking change list:

- `len()` should return `int` in v4.0 (instead of `float`)

This was placed in Phase 3A (Tier 1 breaking changes) alongside IEEE
754 division, cyclic workflow err records, and stdlib err record
location fields.

This doc resolves:

- Scope: which functions get the int treatment besides `len()`
- Return type for related count/position functions (`count`,
  `index_of`, etc.)
- Migration impact for arithmetic patterns
- Edge case handling
- Bytecode impact (none)

---

## Bytecode impact

**No new opcodes required. `BYTECODE_VERSION` stays at 4.**

`len()`, `count()`, `index_of()`, and related count-or-position
functions are stdlib builtins called via `CALL_BUILTIN`. The semantic
change is in the Python-side implementation: each function returns
`int` instead of `float`. The value-translation layer (Python int →
Nodus int) already exists and is used by other builtins.

No bytecode shape changes; existing v3.x `.ndbc` files load and run
in the v4.0 VM (with the new return types applying everywhere
including pre-v4.0 bytecode that calls `len()`).

The frozen-bytecode contract from v1.0 is preserved.

---

## Scope

### Functions changed to return int

The following stdlib functions return `int` in v4.0:

| Function | Returns | Description |
|---|---|---|
| `len(x)` | int | Length of string, list, map, or bytes |
| `count(string, substring)` | int | Count occurrences of substring |
| `count(list, item)` | int | Count occurrences of item in list |
| `index_of(string, substring)` | int (or nil) | Index of substring; nil if not found |
| `index_of(list, item)` | int (or nil) | Index of item in list |
| `last_index_of(string, substring)` | int (or nil) | Last index |
| `last_index_of(list, item)` | int (or nil) | Last index |
| `range(n)` | iterable of ints | Range producing int values |
| `range(start, end)` | iterable of ints | Range producing int values |
| `range(start, end, step)` | iterable of ints | Range producing int values |

The change is consistent: every function that conceptually returns a
count, index, position, or boundary value returns `int`.

### Functions NOT changed

Functions that return measurements continue to return their natural
type:

| Function | Returns | Reason |
|---|---|---|
| `time.duration_*()` | duration | Duration is its own type |
| `byte_size(x)` | int | Already int (or becomes int by this change if currently float) |
| `math.floor(f)` | int | Already int (or becomes int by this change) |
| `math.ceil(f)` | int | Same |
| `math.round(f)` | int | Same |

The pattern: count/index/position → `int`. Measurement of size or
time → the natural type. Numeric operations producing whole numbers
(`floor`, `ceil`, `round`) → `int` since they conceptually produce
integers.

### Edge cases

**`len(nil)`** — returns err record with `kind: "type_error"`. Same
as current v3.x behavior; not changing.

**`len(int)`, `len(float)`, `len(bool)`** — return err record with
`kind: "type_error"`. These types don't have a length.

**`index_of` when not found** — returns `nil` per the idiomatic
"absence is nil" pattern used elsewhere in v3.x stdlib. Code using
`if index_of(...) == -1` migrates to `if index_of(...) == nil`.

This is a SECONDARY breaking change beyond just the int return type.
Documented prominently in the migration guide.

**`count(s, "")`** — counting empty substring. Returns the length of
the string plus 1 (standard convention: an empty substring appears
between every character and at both ends). Same behavior as v3.x;
just the return type changes.

---

## Migration impact

### Direct migration

The most common case is no change required:

```nodus
// v3.x and v4.0 both work
let n = len(items)
for i in range(n) {
    print(items[i])
}
```

Both versions iterate correctly. The return type change is
transparent because `range()` also returns ints in v4.0.

### Arithmetic on `len()` results

The breaking case is float arithmetic with literal int operands:

```nodus
// v3.x
let half = len(items) / 2     // both float; result is float
// e.g., len(items) = 5 → half = 2.5

// v4.0
let half = len(items) / 2     // 2 is parsed as float literal; result is float
// e.g., len(items) = 5 → half = 2.5

// v4.0 with explicit int literal
let half = len(items) / 2i    // both int; result is int (floor division)
// e.g., len(items) = 5 → half = 2
```

The third case is the one to watch: code that uses suffixed int
literals (`2i`, `3i`) with `len()` in arithmetic. In v3.x, the int
literal would coerce to float for the operation; in v4.0, both are
int and integer (floor) division applies.

The migration is mechanical: if the code expected float division,
write `2.0` instead of `2i`. If the code expected floor division,
keep `2i` (the v4.0 behavior is now what was probably intended).

### `index_of` return value change

The secondary change (returning `nil` instead of `-1` when not
found) requires updating:

```nodus
// v3.x
if index_of(items, target) == -1 {
    print("not found")
}

// v4.0
if index_of(items, target) == nil {
    print("not found")
}
```

The migration guide includes both this and the int return type
change as a single section on `index_of` migration.

### Documentation impact

`docs/language/LANGUAGE_SPEC.md` (Phase 4 update):

- `len()` and related function reference: return type updated to `int`
- `index_of` and `last_index_of`: return value updated to `nil` when
  not found

`docs/migration/v3-to-v4.md` (Phase 4 deliverable): full migration
section on the `len()` and `index_of` changes.

---

## Implementation outline

### `len()` builtin

```python
# Before (v3.x)
def builtin_len(value):
    if isinstance(value, str):
        return float(len(value))     # changes
    elif isinstance(value, list):
        return float(len(value))     # changes
    elif isinstance(value, dict):
        return float(len(value))     # changes
    elif isinstance(value, bytes):
        return float(len(value))     # changes
    else:
        return err_record(kind="type_error", ...)

# After (v4.0)
def builtin_len(value):
    if isinstance(value, str):
        return NodusInt(len(value))
    elif isinstance(value, list):
        return NodusInt(len(value))
    elif isinstance(value, dict):
        return NodusInt(len(value))
    elif isinstance(value, bytes):
        return NodusInt(len(value))
    else:
        return err_record(kind="type_error", ...)
```

### Other affected builtins

Same pattern for `count`, `index_of`, `last_index_of`, `range`.
Each returns `NodusInt` instead of `float`. The Python-side
implementation is a one-line change per function.

### `index_of` "not found" return

```python
# v4.0
def builtin_index_of(haystack, needle):
    if isinstance(haystack, str):
        idx = haystack.find(needle)
    elif isinstance(haystack, list):
        idx = haystack.index(needle) if needle in haystack else -1
    else:
        return err_record(kind="type_error", ...)
    return NodusInt(idx) if idx >= 0 else None  # None → nil in Nodus
```

The `None` return value is translated to Nodus `nil` by the
value-translation layer.

### Test surface

Phase 3A test cases:

- `len("hello")` returns int 5 (was float 5.0)
- `len([1, 2, 3])` returns int 3
- `len({})` returns int 0
- `len(b"bytes")` returns int 5
- `len(nil)` returns err record
- `len(42i)` returns err record (int has no length)
- `count("hello world", "o")` returns int 2
- `count([1, 2, 1, 1], 1)` returns int 3
- `index_of("hello", "ll")` returns int 2
- `index_of("hello", "xyz")` returns nil (not -1)
- `last_index_of("hello", "l")` returns int 3
- `index_of([1, 2, 3], 2)` returns int 1
- `index_of([1, 2, 3], 99)` returns nil
- `range(5)` iterates through ints 0, 1, 2, 3, 4
- `range(2, 5)` iterates through ints 2, 3, 4
- `range(0, 10, 2)` iterates through ints 0, 2, 4, 6, 8
- Arithmetic: `len(items) / 2i` produces int (floor division)
- Arithmetic: `len(items) / 2.0` produces float
- Arithmetic: `len(items) + 1i` produces int
- Documentation examples in LANGUAGE_SPEC verified by `nodus_gate
  --runtime` after Phase 4

---

## Open implementation questions for Phase 3B

1. **Existing v3.x tests assuming float return.** Audit the test
   suite for tests that compare `len(x) == 5.0` (using float
   equality) versus `len(x) == 5i`. Update test assertions to use
   int.

2. **`range` boundary behavior with negative steps.** `range(10, 0,
   -1)` should produce ints 10, 9, ..., 1. Verify Python's `range`
   produces this naturally; if not, adjust the Nodus wrapper.

3. **`index_of` and `last_index_of` consistency.** Both should
   return `nil` for "not found"; verify no current code returns -1
   from one and nil from the other.

4. **`count(s, "")` edge case.** Counting empty substring in a
   string. Python's `str.count("")` returns `len(s) + 1` for non-
   empty strings and 1 for empty strings. Document this; users
   sometimes find it surprising.

5. **`range(0)` and `range(5, 5)`.** Both should produce empty
   iterables. Verify.

6. **Performance impact.** Returning `NodusInt` instead of `float`
   has a marginally different value-translation path. Verify no
   regression in hot loops using `len()` heavily.

---

## Capability surface ceiling

Per the capabilities-not-orchestration principle, NOT included:

- **Custom `len`-like methods on user-defined records.** v4.0 does
  not standardize a `Countable` interface. Users can define
  `record.length` or `record.size` returning whatever type they
  want, but there's no protocol that `len()` dispatches to. Future
  v5.x may add a `Countable` convention if real demand surfaces.

- **`size()` vs `len()` distinction.** Some languages have both
  (`size()` for byte/memory size, `len()` for element count). v4.0
  doesn't add `size()`. The `len()` returning int + `byte_size()`
  for raw bytes covers the use cases.

- **Lazy iteration support.** `range()` returns an iterable, not a
  fully-materialized list. This is already v3.x behavior; not
  changing.

### Reconsideration triggers

Scope expands if:

- A v4.0 library requires count/index primitives not in this list
- Real user demand for `Countable` protocol (10+ issues)
- Performance profiling shows the int return type is a bottleneck
  (unlikely)

---

## MCP and A2A consumer validation

`nodus-mcp` and `nodus-a2a` libraries use `len()` and related
functions in internal logic (counting tools registered, counting
arguments, etc.). The int return type is what they actually need:

- `len(mcp_tool_list) > 0` works the same way (int comparison)
- `count(args, "-") == 1i` for flag detection works correctly
- `index_of(path, "/") == nil` for path validation works correctly

Both libraries' internal use of these functions is straightforward
int arithmetic, which v4.0 makes more natural by aligning the return
type with the conceptual operation.

---

## Cross-references

- `docs/governance/V4_0_PLAN.md` (original Tier 1 breaking change
  list)
- `docs/design/v4/09-ieee-754-division.md` (sibling; integer
  arithmetic semantics)
- `docs/design/v4/10-type-naming-reconciliation.md` (sibling; type()
  changes for floats)
- `docs/language/LANGUAGE_SPEC.md` (Phase 4 update: stdlib reference)
- `docs/migration/v3-to-v4.md` (Phase 4 deliverable: migration
  patterns)
- `docs/governance/TECH_DEBT.md` (Phase 3B open questions appended)

---

## Phase 3A implementation handoff

When Phase 3A implements this:

1. Update `len()`, `count()`, `index_of()`, `last_index_of()`,
   `range()` to return int
2. Change `index_of` and `last_index_of` "not found" return from
   `-1` to `nil`
3. Update LANGUAGE_SPEC.md and stdlib reference docs
4. Update existing tests that assume float returns
5. Add tests for all int return cases and `nil` not-found cases
6. Verify migration guide has the changes documented

Estimated effort: half a day. The implementation is mechanical; the
test audit is where time goes.

---

**Phase 1 doc 14-len-returns-int.md: COMPLETE.**
