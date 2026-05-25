# Design Doc: Integer Type (Model B, Opt-in Literal)

**Doc ID:** `docs/design/v3/01-integer-type.md`
**Status:** Phase 1 design — proposed
**Author:** Shawn Knight
**Decision date:** 2026-05-24
**Closes:** [#15](https://github.com/Masterplanner25/Nodus/issues/15) (BUG-012)
**Phase 0 decision reference:** V3_0_PLAN.md §0a, decision 2

---

## 1. Problem statement

Nodus currently represents all numeric values as IEEE 754 double-precision floats. This works for the majority of numeric code but produces silent precision loss for integers above 2^53 (9,007,199,254,740,992). Concrete failure modes observed in BUG-012:

- Large integer literals (e.g. 64-bit IDs, timestamps in nanoseconds, financial values in smallest units) lose accuracy at the parse step
- JSON round-trip silently corrupts integer values above the float-exact range
- Bitwise operations (if/when added) have no sound substrate
- Indexing operations work by coincidence — `list[1]` and `list[1.0]` both work because the index is coerced, but the language has no clean "this is an index" type

The Phase 0 decision selected **Model B: opt-in integer type via literal suffix.** This doc specifies the implementation.

### What this doc does NOT do

- Re-litigate Model A (default int) vs Model B vs Model C. That decision is locked.
- Specify integer behavior at the VM bytecode level. Implementation outline only; full implementation lives in Phase 3.
- Change the default behavior of any existing numeric literal. `1`, `1.0`, `1e9` all continue to parse as float.

---

## 2. Specification

### 2.1 Literal syntax

Integer literals are denoted by an `i` suffix immediately following the digit sequence:

```nodus
let count = 100i           // int
let big_id = 9007199254740993i  // int, exact (would lose precision as float)
let zero = 0i              // int

let normal = 100           // float (unchanged)
let decimal = 100.0        // float (unchanged)
let scientific = 1e9       // float (unchanged)
```

**Grammar (informal):**

```
integer_literal := DIGIT+ "i"
float_literal   := (DIGIT+ "." DIGIT+) | (DIGIT+ ("." DIGIT+)? ("e" "-"? DIGIT+))
```

**Constraints:**
- The `i` suffix must be lowercase. `1I`, `1Int`, `1_i` are syntax errors.
- No whitespace between digits and suffix. `1 i` is two tokens (literal `1` and identifier `i`).
- Negative integers are written as `-1i`, parsed as unary minus applied to literal `1i`. The lexer does not handle the minus sign.
- No hex/octal/binary integer literals in v3.0. `0x1Fi` is a syntax error. Deferred to v3.1 if needed.
- No digit separators in v3.0. `1_000i` is a syntax error. Deferred to v3.1 if needed.

**Parser ambiguity check:** the `i` suffix cannot collide with any existing identifier because identifiers cannot start with a digit. The lexer reads digits, looks for `i` as the next character, and if present consumes it as part of the literal token. This is unambiguous.

### 2.2 Type representation

Internally, integers are represented as Python `int` (arbitrary precision) inside the VM. No fixed bit width. This:

- Matches Python's host language model — zero marshaling cost
- Avoids decisions about overflow semantics (no overflow possible)
- Defers any "should this be int32/int64?" question to a future doc if performance ever demands it

The type tag exposed to user code via `type()` and `rt.typeof()` is the string `"int"`. The float type tag remains `"float"` or `"number"` — whichever is current (Phase 2 BUG-032 reconciles `type()` vs `rt.typeof()`; the int tag must follow the same reconciled convention).

### 2.3 Arithmetic and comparison

Mixed-type arithmetic promotes to float:

```nodus
1i + 1i       // → 2i   (int)
1i + 1        // → 2.0  (float, int promoted)
1i + 1.5      // → 2.5  (float)
1i * 2i       // → 2i   (int)
1i / 2i       // → 0.5  (float — division always produces float)
1i % 2i       // → 1i   (int — modulo on two ints stays int)
```

**Rationale for division:** integer division (`5i / 2i == 2i`) would surprise users coming from Python 3, JavaScript, and most modern languages. Float division is the safer default. Users who explicitly want truncating integer division can use `math.idiv(5i, 2i)` (new stdlib function, see §2.5).

**Comparison:** equality between int and float follows Phase 0 decision 3 (keep `==` coercing). So `1i == 1` is `true`, `1i == 1.0` is `true`. This is consistent with existing `0 == false` behavior — coercion is the documented contract.

**Comparison between two ints uses integer comparison:** no float conversion happens for `1i < 2i`. This matters for large integers that aren't float-exact.

### 2.4 Boolean coercion

`if 0i` is falsy, `if 1i` is truthy, matching float behavior. No change to existing boolean coercion rules.

### 2.5 Standard library additions

Five new stdlib functions land with v3.0:

```nodus
math.parse_int(s: string) -> int | err
// Parse a string to an int. Returns err if the string is not a valid integer.
// Example: math.parse_int("42") → 42i
// Example: math.parse_int("42.0") → err{kind: "parse_error", message: "not an integer: \"42.0\""}

math.to_int(n: float) -> int
// Truncate a float to int. Always succeeds (no err return).
// Example: math.to_int(3.7) → 3i
// Example: math.to_int(-3.7) → -3i  (truncation toward zero)
// Note: silently returns 0i for nan/inf — documented behavior, not a special case

math.to_float(n: int) -> float
// Convert an int to float. May lose precision for ints above 2^53.
// Example: math.to_float(3i) → 3.0
// No err return — precision loss is the user's responsibility

math.is_int(n: number) -> bool
// True if n is an int (not a float that happens to be whole).
// Example: math.is_int(3i) → true
// Example: math.is_int(3.0) → false
// Example: math.is_int(3) → false

math.idiv(a: int, b: int) -> int | err
// Truncating integer division. Both args must be int.
// Example: math.idiv(7i, 2i) → 3i
// Example: math.idiv(7i, 0i) → err{kind: "math_error", message: "division by zero"}
// Example: math.idiv(7, 2) → err{kind: "type_error", message: "math.idiv requires int args"}
```

**JSON parse helper** lands as a separate stdlib addition since it lives in the `json` namespace:

```nodus
json.parse_int(s: string) -> int | err
// Parse a JSON number string as an int, preserving precision.
// Example: json.parse_int("9007199254740993") → 9007199254740993i (exact)
// Example: json.parse_int("3.14") → err{kind: "parse_error", message: "not an integer"}
//
// Distinct from json.parse, which returns float for all numbers per v2.1 behavior.
```

The existing `json.parse` is **unchanged** — it continues to return float for all numeric values. Users who need integer precision on JSON parsing must:
1. Use `json.parse_int(value)` on the specific field they need as int, OR
2. Parse to a map with `json.parse` and call `math.parse_int` on string-typed fields they expect to be ints

This is a deliberate choice. Auto-detecting "this JSON number looks like an int" inside `json.parse` would either (a) silently change the v2.1 contract, breaking the policy that v3.0 only changes things it explicitly declares breaking, or (b) require a config flag on `json.parse` that adds API surface for the minority case.

### 2.6 Embedding API marshaling

The `NodusRuntime` embedding API gains explicit int/float distinction in argument marshaling and return values.

**Python → Nodus (passing args into a script):**

| Python type | Nodus type |
|-------------|------------|
| `int` | int |
| `float` | float |
| `bool` | bool (unchanged) |
| `str` | string (unchanged) |
| `dict` | map (unchanged) |
| `list` | list (unchanged) |
| `None` | nil (unchanged) |

**Breaking change for embedding callers:** in v2.x, Python `int` values marshaled to Nodus float. In v3.0, Python `int` values marshal to Nodus int. This means:

```python
# v2.x behavior
runtime.run("type(x)", x=5)  # → "float" or "number"

# v3.0 behavior
runtime.run("type(x)", x=5)  # → "int"
```

Embedding code that relies on the v2.x marshaling must convert explicitly:

```python
# Force float marshaling in v3.0
runtime.run("type(x)", x=float(5))  # → "float"
```

The migration guide must call this out explicitly.

**Nodus → Python (script return values):**

| Nodus type | Python type |
|------------|-------------|
| int | `int` |
| float | `float` |
| (others unchanged) | |

Symmetric with the input side. Scripts returning `1i` produce Python `int(1)` in the host. Scripts returning `1.0` produce Python `float(1.0)`.

**Embedding API surface — no new methods.** The change is purely in the type marshaling logic inside the existing `run()` / `run_file()` / similar entry points. The decision 4 scope clarification (embedding API surface raises Python exceptions, not Nodus errs) is unaffected by this doc.

### 2.7 Error cases

The following are runtime errors (Nodus err records, not Python exceptions per decision 4):

| Trigger | err.kind | err.message |
|---------|----------|-------------|
| `math.parse_int("foo")` | `parse_error` | `"not an integer: \"foo\""` |
| `math.parse_int("3.14")` | `parse_error` | `"not an integer: \"3.14\""` (decimal point disqualifies) |
| `math.idiv(7i, 0i)` | `math_error` | `"division by zero"` |
| `math.idiv(7, 2)` | `type_error` | `"math.idiv requires int args, got float"` |
| `math.idiv(7i, 2)` | `type_error` | `"math.idiv requires int args, got int and float"` |
| `json.parse_int("abc")` | `parse_error` | `"not a valid integer: \"abc\""` |
| `json.parse_int("1e9")` | `parse_error` | `"not an integer (scientific notation): \"1e9\""` |

These are also the first concrete err kinds that need to flow through the Phase 1 design doc 2 (Python error replacement taxonomy). Cross-reference: any err kind introduced here is a candidate for the taxonomy.

### 2.8 What int does NOT do in v3.0

Explicitly out of scope:

- **Bitwise operators.** No `&`, `|`, `^`, `~`, `<<`, `>>` in v3.0. Adding them requires defining bit width (Python int is arbitrary precision; bitwise ops on arbitrary-precision int have well-defined semantics but they're surprising). Deferred to a future design doc.
- **Hex/octal/binary literals.** `0x10i`, `0o20i`, `0b1000i` are not supported in v3.0. Deferred to v3.1.
- **Digit separators.** `1_000i` is not supported in v3.0. Deferred to v3.1.
- **Implicit int detection in `json.parse`.** Per §2.5, `json.parse` continues to return float for all numbers. `json.parse_int` is opt-in.
- **Integer literals in records/structures.** Records with integer field types are not specified. Records are untyped in current Nodus; this doc doesn't change that.
- **Performance optimization.** No claim that int arithmetic is faster than float arithmetic in v3.0. Python int operations on small values have similar cost to float operations; for large values they're slower. Optimization is a future concern.

---

## 3. Migration impact

### 3.1 What breaks

**For pure Nodus user code:** nothing. All existing numeric literals continue to parse and behave as float. No existing program changes meaning.

**For embedding callers (Python hosts):** Python `int` arguments now marshal to Nodus int instead of Nodus float. Code paths that:

- Compare incoming values via `type(x) == "float"` will break for `int` arguments
- Pass Python integer constants and rely on float arithmetic on the Nodus side will see int-int arithmetic instead (which still works for `+`, `-`, `*`, `%`, comparison; only `/` differs because it always produces float anyway)

**Mitigation:** explicit `float(x)` in the host call, or update the Nodus script to use `math.to_float(x)` at entry.

### 3.2 What users do

Most users do nothing. The opt-in nature means:

- Code that never writes `1i` is unaffected
- Code that needs integer precision adds the suffix where it matters

Migration guide section will include:

1. "Most code needs no changes"
2. "When to opt in" — large IDs, financial values in cents/satoshis, code that's failing due to float precision today (BUG-012 scenarios)
3. "Embedding API behavior change" — explicit float() in host calls if you depended on the old marshaling
4. "Mixed arithmetic rules" — quick reference table from §2.3
5. "Why opt-in instead of default" — link to V3_0_PLAN.md §0a decision 2 reasoning

---

## 4. Implementation outline

High-level only. Phase 3 produces the concrete PRs.

### 4.1 Lexer

- Add `i` suffix detection after digit sequence. Single character of lookahead.
- New token type: `TOKEN_INT_LITERAL` distinct from `TOKEN_FLOAT_LITERAL`.

### 4.2 Parser

- AST node `IntLiteral(value: int)` distinct from `FloatLiteral(value: float)`.
- No grammar changes beyond accepting the new token type in numeric literal positions.

### 4.3 VM / runtime

- New runtime type tag for int. Python `int` as the underlying representation.
- Arithmetic opcodes branch on operand types:
  - int × int → int (except `/` which is float)
  - int × float or float × int → float (int promoted)
  - float × float → float (unchanged)
- Comparison opcodes follow same promotion rules.
- `type()` and `rt.typeof()` return `"int"` for int values (subject to Phase 2 BUG-032 reconciliation).

### 4.4 Stdlib

- Implement five `math.*` functions and `json.parse_int` per §2.5.
- All functions use the Phase 1 design doc 2 error taxonomy (cross-reference; design doc 2 must enumerate the err kinds introduced here).

### 4.5 Embedding API

- Update `NodusRuntime` marshaling tables (input and output sides) per §2.6.
- No new method signatures. The change is in the implementation of existing `run()` / `run_file()`.

### 4.6 Test coverage

Minimum required tests for Phase 3 exit:

- Lexer: int literal parsing (`1i`, `0i`, large values, edge cases like `9999999999999999i`)
- Lexer: rejection of `1I`, `1 i`, `1_i`, `1ii`
- Parser: int literal in expression positions
- VM: int × int arithmetic for `+`, `-`, `*`, `/`, `%`
- VM: int × float promotion for all operators
- VM: int comparison with int (including large values that aren't float-exact)
- VM: int comparison with float (coercion behavior)
- Stdlib: each new function with success and error cases
- Embedding: Python `int` → Nodus int round-trip
- Embedding: Python `float` → Nodus float (unchanged behavior preserved)
- Embedding: Nodus int → Python int return value
- JSON: `json.parse_int` with various inputs; confirm `json.parse` is unchanged

### 4.7 Documentation impact (Phase 4)

- New section in `types-and-values.md` covering int as opt-in type
- New entries in `standard-library.md` for the five `math.*` functions and `json.parse_int`
- Migration guide section per §3.2
- Embedding API section in `embedding-nodus.md` updated with new marshaling table
- Equality coercion documentation (closes #28 and #16) lives in the same `types-and-values.md` pass

---

## 5. Open implementation questions

These do not gate Phase 1 exit but need answers during Phase 3:

1. **`json.stringify` of int values:** does an int become a JSON number without decimal point (`9007199254740993`), or with (`9007199254740993.0`)? Without is correct for JSON spec and preserves round-trip with `json.parse_int`. Confirm in Phase 3.
2. **`math.idiv` for negative numbers:** truncation toward zero (Python `int(a/b)`) or floor division (Python `a // b`)? Different results for negative dividends. §2.5 says "truncation toward zero" — matches Python's `int()` cast and C/Java behavior. Lock during Phase 3 if user feedback prefers floor.
3. **`type()` vs `rt.typeof()` reconciliation timing:** BUG-032 (#33) is in Phase 2 Batch 2B. The int type tag must follow whatever convention BUG-032 settles on. Phase 3 work on int proceeds after Phase 2 closes the type-function divergence.

---

## 6. Decision summary

| Item | Locked value |
|------|--------------|
| Literal syntax | `1i` lowercase suffix, no whitespace, no separators |
| Internal representation | Python `int`, arbitrary precision |
| Default behavior | Unchanged — `1` is still float |
| Mixed arithmetic | Promotes to float |
| Division | Always float (use `math.idiv` for integer division) |
| Equality | Coerces (per Phase 0 decision 3) |
| New stdlib functions | `math.parse_int`, `math.to_int`, `math.to_float`, `math.is_int`, `math.idiv`, `json.parse_int` |
| Embedding API change | Python `int` ↔ Nodus int (breaking for hosts) |
| Out of scope for v3.0 | Bitwise ops, hex/oct/bin literals, digit separators, implicit int detection in `json.parse` |

---

## 7. Exit checklist

Phase 1 exits this design doc when:

- [ ] Doc reviewed and decisions in §6 confirmed final
- [ ] Doc committed to `docs/design/v3/01-integer-type.md`
- [ ] [#15](https://github.com/Masterplanner25/Nodus/issues/15) updated with link to this doc and converted from `type:design-question` to `phase:3-breaking` implementation issue
- [ ] Cross-reference added to Phase 1 design doc 2 (Python error taxonomy) listing the err kinds introduced here: `parse_error` (math.parse_int, json.parse_int), `math_error` (math.idiv), `type_error` (math.idiv)
- [ ] V3_0_PLAN.md §1.A updated to mark integer type design doc complete