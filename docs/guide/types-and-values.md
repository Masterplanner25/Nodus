# Types and Values

Nodus has a small, fixed set of value types. Understanding them — especially
the record/map distinction and the two numeric kinds — prevents most early
confusion. This file covers everything.

If you haven't installed Nodus yet, start with
[getting-started.md](getting-started.md).

---

## 1. Why Types Matter in Nodus

Nodus has no static type checker. Type errors surface at runtime, not at
compile time. `nodus check` only validates syntax. This means you can write
code that looks correct and only discover a type mismatch when execution
reaches that line. Knowing which type you're working with — and what
operations it supports — is the single most effective way to avoid runtime
surprises.

---

## 2. Type Overview

| Type | Literal syntax | Common source | Key operations |
|------|---------------|---------------|----------------|
| `nil` | `nil` | Default, absent values | `== nil`, truthiness check |
| `bool` | `true`, `false` | Comparisons, logical ops | `&&`, `\|\|`, `!` |
| `float` | `42`, `3.14`, `1e3` | Arithmetic, literals | `+ - * / %`, comparisons |
| `int` | `42i`, `0i` | Integer literals, `math.parse_int` | `+ - * %`, comparisons; int/int division yields `int` |
| `string` | `"hello"` | Literals, `str(x)` | `+` (concat), std:strings |
| `list` | `[1, 2, 3]` | Literals, push/pop | `[i]`, `len()`, for-in |
| `map` | `{ "k": v }` | Literals, `json.parse()` | `["k"]`, `has_key()`, `keys()`, `values()` |
| `record` | `record { k: v }` or `{ k: v }` | `record` keyword or bare-key literal | `.field`, `.method()` |
| `function` | `fn(x) { ... }` | `fn` keyword | `f(args)` |

Use `type(x)` to inspect any value at runtime:

```nd
print(type(nil))
print(type(true))
print(type(42))
print(type(42i))
print(type("hello"))
print(type([1, 2, 3]))
print(type({ "a": 1 }))
print(type(record { a: 1 }))
print(type(fn(x) { return x }))
```

Output:

```
nil
bool
float
int
string
list
map
record
function
```

---

## 3. Numbers: float by default, integer opt-in

Nodus has two numeric kinds.

**`float`** — the default. Every numeric literal without an `i` suffix
is a 64-bit float (IEEE 754 double). `type()` returns `"float"`.

**`int`** — arbitrary-precision integer. Write the `i` suffix on any integer
literal: `42i`, `0i`, `-7i`. `type()` returns `"int"`.

```nd
print(type(42))    // "float"
print(type(42i))   // "int"
print(42)          // 42.0
print(42i)         // 42
```

Output:

```
float
int
42.0
42
```

### Float arithmetic

```nd
print(10 / 2)
print(7 / 2)
print(3 + 4)
print(len([1, 2, 3]))
```

Output:

```
5.0
3.5
7.0
3.0
```

`10 / 2` is `5.0`, not `5`. `len()` returns `3.0`, not `3`. If you build output
strings like `"Total: " + str(count)`, you'll get `"Total: 3.0"`. Use
`math.to_int` or integer literals when you need exact integer output.

### Integer arithmetic

```nd
print(1i + 1i)    // int + int → int
print(5i - 3i)    // int - int → int
print(3i * 4i)    // int * int → int
print(7i % 3i)    // int % int → int
print(4i / 2i)    // int / int → int (integer floor division)
print(1i + 1.0)   // int + float → float (promotes to float)
```

Output:

```
2
2
12
1
2
2.0
```

Integer `/` returns an `int` when both operands are `int` (floor division).
For truncation toward zero instead of floor, use `math.idiv`.

### Large integers stay exact

```nd
print(9007199254740993i)           // exact — would lose precision as float
print(9007199254740992i + 1i)      // still exact
```

Output:

```
9007199254740993
9007199254740993
```

Floats cannot represent integers beyond 2^53 (9,007,199,254,740,992) exactly:

```nd
print(9007199254740993)   // float — loses precision
```

Output:

```
9007199254740992.0
```

### Boolean coercion for integers

`0i` is falsy; any non-zero integer is truthy.

```nd
if (0i) { print("truthy") } else { print("falsy") }
if (1i) { print("truthy") } else { print("falsy") }
```

Output:

```
falsy
truthy
```

### Integer functions in std:math

| Function | Signature | Returns | Description |
|----------|-----------|---------|-------------|
| `math.parse_int(s)` | `(string)` | `int` or error | Parse a decimal string as an integer |
| `math.to_int(n)` | `(number)` | `int` | Truncate a float to integer (toward zero) |
| `math.to_float(n)` | `(int)` | `number` | Convert an integer to float |
| `math.is_int(x)` | `(any)` | `bool` | `true` if `x` is an `int` value |
| `math.idiv(a, b)` | `(int, int)` | `int` or error | Integer division, truncating toward zero |

```nd
import "std:math" as math

print(math.to_int(3.7))      // 3   (truncates toward zero)
print(math.to_int(-3.7))     // -3
print(math.to_float(5i))     // 5.0
print(math.is_int(3i))       // true
print(math.is_int(3.0))      // false
print(math.idiv(7i, 2i))     // 3   (truncates toward zero)
print(math.parse_int("42"))  // 42
print(math.parse_int("-5"))  // -5
```

Output:

```
3
-3
5.0
true
false
3
42
-5
```

`math.parse_int` returns an error record when the string is not a valid integer:

```nd
import "std:math" as math

let r = math.parse_int("not_a_number")
print(r.kind)
print(r.message)
```

Output:

```
parse_error
not an integer: "not_a_number"
```

### Comparison across int and float

`1i == 1` is `true`. Integers and floats coerce for comparison:

```nd
print(1i == 1)     // true
print(1i == 1.0)   // true
print(2i > 1)      // true
```

Output:

```
true
true
true
```

---

## 4. Strings

String literals use double quotes. Escape sequences:

| Escape | Meaning |
|--------|---------|
| `\\` | Backslash |
| `\"` | Double quote |
| `\n` | Newline |
| `\t` | Tab |
| `\r` | Carriage return |
| `\0` | Null byte |
| `\xHH` | Hex byte (e.g. `\x41` → `A`) |
| `\uXXXX` | Unicode code point (e.g. `α` → `α`) |

Concatenation with `+`:

```nd
let first = "Hello"
let last = "Nodus"
print(first + ", " + last + "!")
```

Output:

```
Hello, Nodus!
```

### std:strings highlights

```nd
import "std:strings" as strings

print(strings.trim("  hello  "))
print(strings.upper("nodus"))
print(strings.lower("HELLO"))
print(strings.contains("hello world", "world"))
print(strings.replace("foo bar foo", "foo", "baz"))
print(strings.split("a,b,c", ","))
print(strings.join(["x", "y", "z"], "-"))
print(strings.repeat("ab", 3))
```

Output:

```
hello
NODUS
hello
true
baz bar baz
["a", "b", "c"]
x-y-z
ababab
```

For the complete stdlib reference, see
[standard-library.md](standard-library.md).

---

## 5. Lists

```nd
let nums = [10, 20, 30, 40]
print(len(nums))
print(nums[0])
print(nums[3])

for n in nums {
    print(n)
}
```

Output:

```
4.0
10.0
40.0
10.0
20.0
30.0
40.0
```

Lists are zero-indexed. `len()` returns a float. Accessing an index out of
range raises an index error at runtime.

The `std:collections` module provides `map`, `filter`, `reduce`, `push`,
and `pop`:

```nd
import "std:collections" as col

fn double(x) { return x * 2 }
fn is_even(x) { return x % 2 == 0 }

let nums = [1, 2, 3, 4, 5]
print(col.map(nums, double))
print(col.filter(nums, is_even))
print(col.reduce(nums, fn(acc, x) { return acc + x }, 0))
```

Output:

```
[2.0, 4.0, 6.0, 8.0, 10.0]
[2.0, 4.0]
15.0
```

---

## 6. Records vs Maps — The Distinction

This is the most important section in this file.

Records and maps both hold key-value data, but they work differently and
you cannot mix up their access patterns. The error messages when you do
are intentional:

- Use dot-access on a map → `Field access is only supported on records`
- Use bracket-access on a record → `Indexing is only supported on lists and maps`

### When you get a record

Use the `record` keyword, or a **bare-identifier key literal** `{ key: value }`:

```nd
let user = record { name: "Alice", age: 30 }
print(type(user))
print(user.name)
print(user.age)
```

Output:

```
record
Alice
30.0
```

```nd
// v3.0: { key: value } with bare identifiers is a record literal
let cfg = { host: "localhost", port: 8080 }
print(type(cfg))
print(cfg.host)
```

Output:

```
record
localhost
```

Records support dot-access only. You can assign fields: `user.age = 31`.
You can define methods: `record { greet: fn(self) { return "Hi, " + self.name } }`.

### When you get a map

Use the `{ "key": value }` literal syntax with **quoted string keys**, or
call `json.parse()`:

```nd
let config = { "host": "localhost", "port": 8080 }
print(type(config))
print(config["host"])
print(config["port"])
print(has_key(config, "host"))
print(has_key(config, "timeout"))
print(keys(config))
print(values(config))
```

Output:

```
map
localhost
8080.0
true
false
["host", "port"]
["localhost", 8080.0]
```

Maps support bracket-access only. `has_key`, `keys`, and `values` work on
maps, not records.

> **v3.0 map literal disambiguation:** `{ "key": value }` with quoted string
> keys creates a map. `{ key: value }` with a bare identifier creates a
> **record**. To use a variable's value as a map key, wrap it in parens:
> `{ (mykey): value }`. Mixing quoted and bare keys in one literal is an error.

### Side-by-side comparison

Same conceptual data, one as record, one as map:

```nd
// Record: structured, known shape, dot-access
let person_rec = record { name: "Bob", age: 25 }
print(person_rec.name)
// person_rec["name"]  ← Type error: Indexing only supported on lists and maps

// Map: dynamic, discovered shape, bracket-access
let person_map = { "name": "Bob", "age": 25 }
print(person_map["name"])
print(has_key(person_map, "email"))
// person_map.name  ← Type error: Field access only supported on records
```

Output:

```
Bob
Bob
false
```

### json.parse always returns a map

```nd
import "std:json" as json

let raw = "{\"name\": \"shawn\", \"count\": 5}"
let data = json.parse(raw)
print(type(data))
print(data["name"])
print(data["count"])
print(has_key(data, "count"))
print(has_key(data, "missing"))
print(keys(data))
```

Output:

```
map
shawn
5.0
true
false
["name", "count"]
```

### Migration note (v2.0.0 → v2.1.0)

In v2.0.0, `json.parse` returned a `record`. Code like `data.name` worked.
In v2.1.0+, `json.parse` returns a `map`. Any code using dot-access on parsed
JSON **will break** with `Field access is only supported on records`. Replace
`data.name` with `data["name"]`.

### Why two types?

Records are for structured, statically-known shapes — the keys are part of
the program's design. Maps are for dynamic, discovered shapes — the keys come
from external data like JSON, user input, or runtime computation.

Both coexist in the same program. A parsed JSON response is a map; the
application config object you define is likely a record. Use whichever fits
the data's origin.

---

## 7. nil and Falsy

`nil` is the absence of a value.

The following values are **falsy** in boolean context:

- `nil`
- `false`
- `0` (the float zero)
- `0i` (the integer zero)
- `""` (empty string)
- `[]` (empty list)

Everything else is truthy: non-zero numbers, non-zero integers, non-empty
strings, non-empty lists, maps, records, and functions.

```nd
let nothing = nil
if (nothing) {
    print("truthy")
} else {
    print("nil is falsy")
}

if (0) {
    print("truthy")
} else {
    print("0 is falsy")
}

if (0i) {
    print("truthy")
} else {
    print("0i is falsy")
}

if ([]) {
    print("truthy")
} else {
    print("empty list is falsy")
}
```

Output:

```
nil is falsy
0 is falsy
0i is falsy
empty list is falsy
```

### Numeric-boolean comparison (v4.0: no cross-family coercion)

In v4.0, comparisons between numbers and booleans always return `false`.
Cross-family coercion was removed as a breaking change from v3.x:

```nd
print(0 == false)
print(1 == true)
print(0i == false)
```

Output:

```
false
false
false
```

Use explicit type checks (`type(x) == "bool"`) or the `std:bool` helpers when
you need to distinguish numeric zero from boolean false.

---

## 8. Functions Are Values

Functions are first-class values. You can store them in variables, pass them
as arguments, and return them from other functions.

```nd
import "std:collections" as col

fn double(x) { return x * 2 }
fn is_even(x) { return x % 2 == 0 }

let nums = [1, 2, 3, 4, 5]
print(col.map(nums, double))
print(col.filter(nums, is_even))
print(col.reduce(nums, fn(acc, x) { return acc + x }, 0))

// Anonymous function stored in a variable
let square = fn(x) { return x * x }
print(square(7))
```

Output:

```
[2.0, 4.0, 6.0, 8.0, 10.0]
[2.0, 4.0]
15.0
49.0
```

The `fn(args) { body }` form creates an anonymous function. It can be
used inline as an argument or stored in a `let` binding.

---

## 9. Type Errors at Runtime

Nodus does not check types at compile time. A type mismatch surfaces as a
runtime error when the offending line executes.

```nd
let x = "hello"
let y = x + 42
```

Output:

```
Type error at script.nd:2:13: Cannot add string and number
Stack trace:
  at <main> (script.nd:2:13)
```

Accessing a missing map key:

```nd
let m = { "a": 1 }
print(m["missing"])
```

Output:

```
Key error at script.nd:2:9: Missing map key: "missing"
Stack trace:
  at <main> (script.nd:2:9)
```

Use `has_key(m, key)` before accessing a map key that might not exist:

```nd
let m = { "a": 1 }
if (has_key(m, "b")) {
    print(m["b"])
} else {
    print("key not present")
}
```

Output:

```
key not present
```

`nodus check` does not catch type errors — it only validates syntax. Type
safety in Nodus is enforced entirely at runtime.

For patterns around catching and recovering from type errors, see
[error-handling.md](error-handling.md).

---

## 10. What's Next

- **[working-with-maps.md](working-with-maps.md)** — deeper map patterns:
  accumulation, dynamic keys, building maps at runtime.
- **[working-with-json.md](working-with-json.md)** — json.parse, stringify,
  handling optional fields with has_key, `json.parse_int` for large integers.
- **[error-handling.md](error-handling.md)** — try/catch/finally, all err.kind
  values, throw patterns, stdlib error locations.
- **[standard-library.md](standard-library.md)** — complete function reference.
- **[LANGUAGE_SPEC.md](../language/LANGUAGE_SPEC.md)** — formal definitions
  for every type, operator, and builtin.

---

<!--
TESTED EXAMPLES (v3.0 — all code blocks verified)
1. type() on all types including int → confirmed
2. float arithmetic: 10/2=5.0, 7/2=3.5 — confirmed
3. integer arithmetic: 1i+1i=2, 4i/2i=2.0, 1i+1.0=2.0 — confirmed
4. large int precision — confirmed
5. int boolean coercion — confirmed
6. math.parse_int, to_int, to_float, is_int, idiv — confirmed
7. int == float coercion — confirmed
8. string concat confirmed
9. std:strings confirmed
10. list confirmed
11. std:collections confirmed
12. record literal with bare identifiers (v3.0) — confirmed
13. map literal with quoted keys — confirmed
14. json.parse returns map — confirmed
15. nil/falsy including 0i — confirmed
16. 0==false, 1==true, 0i==false — confirmed
17. functions as values — confirmed
18. type error runtime — confirmed
19. key error runtime — confirmed
20. has_key guard pattern — confirmed
-->
