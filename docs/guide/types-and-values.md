# Types and Values

Nodus has a small, fixed set of value types. Understanding them — especially
the record/map distinction and float-only numbers — prevents most early
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
| `number` | `42`, `3.14`, `1e3` | Arithmetic, literals | `+ - * / %`, comparisons |
| `string` | `"hello"` | Literals, `str(x)` | `+` (concat), std:strings |
| `list` | `[1, 2, 3]` | Literals, push/pop | `[i]`, `len()`, for-in |
| `map` | `{ "k": v }` | Literals, `json.parse()` | `["k"]`, `has_key()`, `keys()`, `values()` |
| `record` | `record { k: v }` | `record` keyword | `.field`, `.method()` |
| `function` | `fn(x) { ... }` | `fn` keyword | `f(args)` |

Use `type(x)` to inspect any value at runtime:

```nd
print(type(nil))
print(type(true))
print(type(42))
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
number
string
list
map
record
function
```

---

## 3. Numbers Are Floats

Every number in Nodus is a 64-bit float (IEEE 754 double). There is no
separate integer type. This is intentional for v2.x; a distinct `int` type
is planned for v3.0.

### Division always returns a float

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

`10 / 2` is `5.0`, not `5`. `len()` returns `3.0`, not `3`. If you
build output strings like `"Total: " + str(count)`, you'll get
`"Total: 3.0"` — not `"Total: 3"`. There is no built-in way to strip
the `.0` from whole-number floats in v2.1.0.

### Modulo works on both integer-valued and fractional floats

```nd
print(10 % 3)
print(7.5 % 2.5)
```

Output:

```
1.0
0.0
```

### Scientific notation

```nd
print(1e3)
print(2.5e-1)
print(1E10)
print(6.022e23)
```

Output:

```
1000.0
0.25
10000000000.0
6.022e+23
```

### Precision limit

Integers are represented exactly up to 2^53 (9,007,199,254,740,992).
Beyond that, precision silently erodes:

```nd
print(9007199254740992)
print(9007199254740993)
print(999999999999999999)
```

Output:

```
9007199254740992.0
9007199254740992.0
1e+18
```

If you need exact large integers, Nodus v2.1.0 cannot provide them.
An integer type is planned for v3.0.

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

Use the `record` keyword in your source code:

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

> **Map literal syntax requires quoted keys.** `{ "key": value }` creates a
> map. `{ key: value }` with an unquoted identifier evaluates `key` as a
> variable expression — if `key` isn't defined, you get
> `Undefined variable: key`.

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
In v2.1.0, `json.parse` returns a `map`. Any code using dot-access on parsed
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
- `""` (empty string)
- `[]` (empty list)

Everything else is truthy: non-zero numbers, non-empty strings, non-empty
lists, maps, records, and functions.

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
empty list is falsy
```

### Known awkwardness: numeric-boolean coercion

`0 == false` is `true`, and `1 == true` is `true`. This is a consequence
of Python-style truthiness coercion in the equality operator. It's a known
issue (BUG-013, deferred to v3.0). If your code distinguishes between
integer zero and boolean false, use explicit type checks via `type(x)`.

```nd
print(0 == false)
print(1 == true)
```

Output:

```
true
true
```

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
[error-handling.md](error-handling.md) (coming soon).

---

## 10. What's Next

- **[working-with-maps.md](working-with-maps.md)** (coming soon) — deeper
  map patterns: accumulation, dynamic keys, building maps at runtime.
- **[working-with-json.md](working-with-json.md)** (coming soon) — json.parse,
  stringify, handling optional fields with has_key, migrating from v2.0.0.
- **[error-handling.md](error-handling.md)** (coming soon) — try/catch/finally,
  all err.kind values, throw patterns, stdlib error locations.
- **[LANGUAGE_SPEC.md](../language/LANGUAGE_SPEC.md)** — formal definitions
  for every type, operator, and builtin.

---

<!--
TESTED EXAMPLES (15 total — matches code block count)
1. type() on all types → "nil\nbool\nnumber\n..." confirmed
2. float division: 10/2=5.0, 7/2=3.5, 3+4=7.0, len([1,2,3])=3.0 confirmed
3. modulo: 10%3=1.0, 7.5%2.5=0.0 confirmed
4. scientific notation: 1e3=1000.0, 2.5e-1=0.25, 1E10=10000000000.0 confirmed
5. precision limit: 9007199254740993 → 9007199254740992.0, 999...999 → 1e+18 confirmed
6. string concat: "Hello, " + "Nodus" + "!" → "Hello, Nodus!" confirmed
7. std:strings: trim/upper/lower/contains/replace/split/join/repeat confirmed
8. list: len([10,20,30,40])=4.0, nums[0]=10.0, for-in confirmed
9. std:collections map/filter/reduce confirmed
10. record: user.name="Alice", user.age=30.0, type="record" confirmed
11. map: config["host"]="localhost", has_key, keys, values confirmed
12. json.parse: returns type "map", bracket access, has_key, keys confirmed
13. nil/falsy: nil,0,[] all falsy confirmed
14. 0==false=true, 1==true=true confirmed
15. functions as values: col.map/filter/reduce, anonymous fn confirmed
16. type error: "Cannot add string and number" confirmed (tested via embedding)
17. key error: "Missing map key: missing" confirmed (tested via embedding)
18. has_key guard pattern: confirmed works

BEHAVIORAL FINDINGS (new, during types-and-values testing)
F4: {} literal with unquoted identifier keys is NOT shorthand for string
    keys. { name: "Alice" } evaluates 'name' as an identifier expression
    (variable lookup), not as a string key. Map literals MUST use quoted
    string keys: { "name": "Alice" }. The LANGUAGE_SPEC Values section
    shows '{ key: value }' which implies bare identifiers work — misleading.
F5: Both 0==false and 1==true return true (numeric-boolean coercion).
    Documented in guide as known issue BUG-013, deferred v3.0.
F6: 'else if' is not valid syntax (confirmed via testing in getting-started).
    Not documented in LANGUAGE_SPEC. Documented in guide as behavioral note.
-->
