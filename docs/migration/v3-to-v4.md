# Migrating from Nodus v3.x to v4.0

v4.0 is a breaking-change release. This guide covers every change that
requires updates to existing v3.x code.

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

### 4. Float division by zero returns `inf`/`nan`

**What changed:** `1.0 / 0.0` returns `inf`; `0.0 / 0.0` returns `nan`.
In v3.x these threw a runtime error.

**How to fix:**

Code that caught "division by zero" errors will silently get `inf`/`nan`
instead. If you need strict behavior, add explicit checks:

```nodus
import "std:math" as math

let result = a / b
if math.is_nan(result) or math.is_inf(result) {
    // handle the degenerate case
}
```

**Note:** Integer division and modulo by zero still return err records.

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

1. [ ] Grep for `"number"` in type comparisons → update to `"float"` or
       `math.is_float(x)`
2. [ ] Grep for `== false`, `== true`, `!= false`, `!= true` → review for
       cross-family coercion reliance
3. [ ] Grep for `== -1` after `index_of` / `last_index_of` → update to
       `== nil`
4. [ ] Check any code that caught "division by zero" runtime errors →
       add `math.is_nan`/`math.is_inf` guards if needed
5. [ ] Check any workflow error handling → update to check for err record
       with `category: "cyclic_workflow"`
