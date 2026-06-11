# Migrating from Nodus v3.x to v4.0

v4.0 is a breaking-change release. This guide covers every change that
requires updates to existing v3.x code.

---

## Two most common silent breaks

These two changes affect virtually every v3 program and produce **no error** —
the code runs but behaves differently. Fix these first before anything else.

### 0a. Bare numeric literals are now floats — add the `i` suffix for integers

**What changed:** In v3, `3` behaved like an integer in most contexts.
In v4, `3` is a `float` (`3.0`). Integer arithmetic requires the `i` suffix.

```nd
// v3.x — worked
let count = 3
let doubled = count * 2   // 6

// v4.0 — silent behavior change
print(type(3))      // float  (not "int")
print(3 / 2)        // 1.5   (not 1)
print(type(3))      // float

// v4.0 — correct
let count = 3i
let doubled = count * 2i  // 6i  (int)
print(3i / 2i)            // 1i  (integer division)
```

**How to find it:** grep for bare integer literals in arithmetic expressions.
Any `count + 1`, `i < 10`, loop counters, list indices using plain numbers.

**How to fix:** Add the `i` suffix to all integer literals: `3` → `3i`,
`0` → `0i`, `100` → `100i`. Mixed `int + float` promotes to float.

---

### 0b. `json.parse()` returns a map — use bracket notation, not dot

**What changed:** `json.parse()` returns a **map** (`{"key": val}` style),
not a record. Maps require bracket notation; dot notation throws.

```nd
import "std:json" as json

let data = json.parse("{\"name\": \"Alice\", \"age\": 30}")

// v3.x — worked
print(data.name)   // Alice

// v4.0 — throws: "Field access is only supported on records"
print(data.name)

// v4.0 — correct
print(data["name"])   // Alice
print(data["age"])    // 30.0
```

**How to find it:** grep for `.fieldname` accesses on values that come from
`json.parse`, any HTTP response body, or any other API that returns a map.

**How to fix:** Replace dot access with bracket access on parsed JSON:
`data.field` → `data["field"]`.

---

## Breaking changes

### 1. `type(float)` returns `"float"` not `"number"`

**What changed:** `type(1.0)` and `type(42)` (unadorned numeric literals)
now return `"float"`. In v3.x they returned `"number"`.

**How to find it:** grep your code for `"number"` in type comparison
contexts.

```
rg '"number"'
```

**How to fix:**

| v3.x | v4.0 |
|---|---|
| `type(x) == "number"` | `math.is_float(x)` |
| `type(x) == "number" or type(x) == "int"` | `math.is_numeric(x)` |
| `type(x) != "number"` | `!math.is_float(x)` |
| `match type(x) { "number" → ... }` | `match type(x) { "float" → ... }` |

`math.is_numeric(x)` accepts both int and float values.
`math.is_float(x)` tests specifically for float.
`math.is_int(x)` tests specifically for int (unchanged from v3.x).

---

### 2. `==` no longer coerces across type families

**What changed:** Cross-family comparisons (number ↔ bool, number ↔ string,
string ↔ bool) now return `false`. Number-family coercion (`int == float`) is
preserved.

**Specific changes:**

| Expression | v3.x | v4.0 |
|---|---|---|
| `0i == false` | `true` | `false` |
| `1i == true` | `true` | `false` |
| `"" == false` | `true` | `false` |
| `"1" == 1i` | `true` | `false` |
| `nil == false` | `false` | `false` (unchanged) |
| `1i == 1.0` | `true` | `true` (preserved) |

**How to find it:** grep for `== false`, `== true`, `!= false`, `!= true`
and review whether the comparison was relying on cross-family coercion.

**How to fix:**

When you need to check if a value is `true` (the bool):
```nodus
import "std:bool" as b

// v3.x (may have relied on coercion):
if x == true { ... }

// v4.0 — choose based on intent:
if bool.equal(x, true) { ... }   // x must be literally the bool true
if x == 1i { ... }                // x must be the integer 1
if x { ... }                      // x is truthy (unchanged semantics)
```

New helpers:
- `type_eq(a, b)` — strict same-type equality; `type_eq(1i, 1.0)` is `false`
- `bool.equal(x, true/false)` — test for a specific bool value

---

### 3. `index_of()` and `last_index_of()` return `nil` for not-found

**What changed:** When the element is not in the collection, these functions
return `nil` instead of `-1`.

**How to fix:**

```nodus
// v3.x
let i = index_of(lst, item)
if i != -1 { use(lst[i]) }

// v4.0
let i = index_of(lst, item)
if i != nil { use(lst[i]) }
```

---

### 4. Division and modulo by zero raise `runtime_error("math", ...)`

**What changed in v4.0.0:** Float division by zero returned `inf`/`nan`.
Integer division by zero returned err records.

**What changed in v4.0.1 (reverted):** All division and modulo by zero now
raise `runtime_error("math", ...)` — integers and floats alike. The `inf`/`nan`
return behavior from 4.0.0 is gone.

**If you are upgrading from v3.x directly to v4.0.1+:**

v3.x threw a runtime error → v4.0.1+ throws a runtime error. No change needed.

**If you are on v4.0.0 and added `math.is_nan` / `math.is_inf` guards:**

Remove them — division by zero now throws instead of returning IEEE 754 values:

```nodus
// v4.0.0 pattern — no longer needed in v4.0.1+
let result = a / b
if math.is_nan(result) or math.is_inf(result) { ... }

// v4.0.1+ — use try/catch or guard the divisor
try {
    let result = a / b
    // use result
} catch err {
    if err.kind == "math" { ... }
}
```

---

### 5. Cyclic workflow returns err record

**What changed:** When a workflow contains a cycle, `run_workflow` returns
an err record instead of a plain dict.

**How to fix:**

```nodus
// v4.0
let result = run_workflow(my_workflow)
if type(result) == "error" {
    let payload = result.payload
    if payload["category"] == "cyclic_workflow" {
        print("cycle: " + str(payload["cycle"]))
    }
}
```

The err record has `kind: "workflow_error"`, `payload.category: "cyclic_workflow"`,
and `payload.cycle` (the list of steps forming the cycle).

---

### 6. Err records now carry location fields

**What changed:** Every err record now includes `path`, `line`, `column`,
`stack`, and `origin` fields. In v3.x, err records had only `kind`, `message`,
and `payload`.

**How this affects you:** Code that checks for specific err record fields
by key or destructures err records should be aware of the new fields.
Pattern matching on err records should allow for extra fields (not check
for exact field set).

---

## New features (opt-in)

### String interpolation

```nodus
let name = "world"
print("Hello, \(name)!")        // Hello, world!
print("1 + 1 = \(1i + 1i)")    // 1 + 1 = 2
```

Use `\\(` to produce a literal `\(` in a string.

### New stdlib namespaces

All new in v4.0; no migration required for existing code:

| Namespace | Import |
|---|---|
| `std:env` | `import "std:env" as env` |
| `std:time` | `import "std:time" as time` |
| `std:hash` | `import "std:hash" as hash` |
| `std:encoding` | `import "std:encoding" as encoding` |
| `std:secrets` | `import "std:secrets" as secrets` |
| `std:http` | `import "std:http" as http` |
| `std:subprocess` | `import "std:subprocess" as subprocess` |
| `std:tool` | `import "std:tool" as tool` |
| `std:test` | `import "std:test" as test` |
| `std:bool` | `import "std:bool" as bool` |

### Test framework

Use `nodus test` to run test files matching `*_test.nd`. See
`docs/guide/standard-library.md` for the full `std:test` API.

---

## Quick migration checklist

0. [ ] **Add `i` suffix to all integer literals** (`3` → `3i`, `0` → `0i`) —
       bare numbers are floats and will silently change arithmetic results
0. [ ] **Replace dot access on `json.parse()` results with bracket access**
       (`data.field` → `data["field"]`) — json.parse returns a map, not a record
1. [ ] Grep for `"number"` in type comparisons → update to `"float"` or
       `math.is_float(x)`
2. [ ] Grep for `== false`, `== true`, `!= false`, `!= true` → review for
       cross-family coercion reliance
3. [ ] Grep for `== -1` after `index_of` / `last_index_of` → update to
       `== nil`
4. [ ] Division by zero: in v4.0.1+ all division/modulo by zero throws
       `runtime_error("math", ...)`. If upgrading from v4.0.0, remove any
       `math.is_nan` / `math.is_inf` guards added for float div-by-zero.
5. [ ] Check any workflow error handling → update to check for err record
       with `category: "cyclic_workflow"`
