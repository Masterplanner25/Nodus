# Nodus — V3.1 Design Items

**Status:** Captured — not yet scheduled  
**Author:** Shawn Knight  
**Last updated:** 2026-05-25  
**Baseline:** v3.0.1

This document records design questions and deferred fixes that were identified
during the v3.0.1 stress-test eval but intentionally left out of the v3.0.1
patch. They are candidates for v3.1, not committed items.

---

## 1. `len()` float return value (BUG-E15 / #67)

**Current behavior:** `len(list)` returns a float (`3.0`), not an integer
(`3`). This is because the VM arithmetic stack uses Python floats for all
Nodus number values, and the builtin returns `float(len(obj))`.

**Why deferred:** Changing `len()` to return an int would be a breaking change
for any code that passes `len()` output to a function expecting a float (e.g.,
equality-comparing to a float literal). With the integer type now available in
v3.0, returning `3i` would be more natural, but callers need time to adapt.

**Proposed v3.1 resolution:**
- `len()` returns an `int` value (e.g., `3i`, type `"int"`).
- A migration note is added to the v3.0 → v3.1 migration guide.
- The change ships with a `# Breaking change` label in the CHANGELOG.

**Documented as:** a known inconsistency in `docs/guide/standard-library.md`
(the `len()` entry notes that it returns a float in v3.x).

---

## 2. `type()` naming inconsistency (BUG-E17 / #69)

**Current behavior:** `type()` returns `"number"` for floats, `"int"` for
integer values. The inconsistency is that float values are named `"number"`
rather than `"float"`.

**Why deferred:** Renaming `"number"` → `"float"` would break every `type(x)
== "number"` guard in user code. This is a significant breaking change for a
cosmetic improvement.

**Proposed v3.1 resolution options (not yet decided):**
1. Keep `"number"` forever; document that it is the canonical float type name.
2. Add `type() == "float"` as an alias in v3.1 and deprecate `"number"` with
   a 2-release warning cycle before removal in v4.0.
3. Accept the inconsistency as a consequence of the integer type addition and
   leave both names documented.

**Decision gate:** Requires an explicit deprecation policy decision before
v3.1 scope is locked. See `docs/governance/COMPATIBILITY.md`.

**Documented as:** a known inconsistency in `docs/guide/types-and-values.md`
(the type name table notes the `"number"` / `"int"` asymmetry).

---

## 3. `finally` skipped when `catch` has `return` (BUG-041, known)

**Current behavior:** If a `catch` block executes a `return` statement,
the `finally` block is skipped. This is a VM-level control flow bug.

**Why deferred:** The fix requires changes to the VM's frame unwinding logic.
This is a non-trivial change with risk of regressions in the try/catch/finally
opcode sequence. It was deferred from v3.0 as a known v3.1 item.

**Proposed v3.1 resolution:**
- Audit the `OP_END_FINALLY` / `OP_SETUP_FINALLY` / `OP_RETURN` opcode
  interaction in `vm.py`.
- Add a targeted fix that ensures `finally` always runs when `catch` returns.
- Cover with tests for all combinations: catch-return, catch-throw, catch-fall-through.

---

## 4. Non-breaking polish candidates

These items are low-risk and could ship in any v3.x patch:

| Item | Description | GitHub issue |
|------|-------------|--------------|
| `type()` docs alignment | Ensure `types-and-values.md` matches actual `type()` behavior for all types | #69 |
| `len()` docs note | Add float-return note to `standard-library.md` entry | #67 |
| `json.stringify` int note | Add note that `json.stringify` accepts int values natively | #74 |
| int display convention | Document that `print(42i)` displays `"2"`, not `"2i"` | #73 |

---

## See also

- [ROADMAP.md](ROADMAP.md) — higher-level feature roadmap
- [COMPATIBILITY.md](COMPATIBILITY.md) — breaking-change policy and deprecation timeline
- [DEPRECATIONS.md](DEPRECATIONS.md) — active deprecation warnings
- [V3_0_PLAN.md](V3_0_PLAN.md) — completed v3.0 work
