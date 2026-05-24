# Working with JSON

This file covers parsing JSON, generating JSON, and the v2.1.0 map model
that governs how parsed data is accessed. It is a task-oriented guide; for
the full function reference see [standard-library.md — std:json](standard-library.md#4-stdjson).

**Upgrading from v2.0.x?** Jump to
[Migrating from v2.0.x to v2.1.0](#5-migrating-from-v20x-to-v210) first.

---

## v2.0.x upgraders: three things changed

> **Breaking change in v2.1.0**
>
> 1. `json.parse` now returns a **map**, not a record.
> 2. Dot-access code (`data.name`) **will break** with a type error.
>    Replace it with bracket-access: `data["name"]`.
> 3. `has_key`, `keys`, and `values` now work on parsed JSON.
>
> Full details in [Section 5](#5-migrating-from-v20x-to-v210).

---

## 1. Parsing JSON

```nd
import "std:json" as json
```

`json.parse(s)` decodes a JSON string to a Nodus value:

| JSON type | Nodus type | How to access |
|-----------|-----------|---------------|
| `{...}` | `map` | `m["key"]`, `has_key`, `keys`, `values` |
| `[...]` | `list` | `arr[i]`, `for item in arr` |
| `"string"` | `string` | — |
| `42`, `3.14` | `number` (float) | — |
| `true`/`false` | `bool` | — |
| `null` | `nil` | `== nil` |

### Parsing an object

```nd
import "std:json" as json

let raw = "{\"name\": \"alice\", \"role\": \"admin\", \"score\": 95}"
let user = json.parse(raw)
print(type(user))
print(user["name"])
print(user["score"])
```

Output:

```
map
alice
95.0
```

The result is a `map`. Use `["key"]` for all field access. Numbers parse
as Nodus floats — JSON `95` becomes `95.0`. See
[types-and-values.md — Numbers are floats](types-and-values.md#3-numbers-are-floats).

### Parsing an array

```nd
import "std:json" as json

let arr = json.parse("[1, 2, 3]")
print(type(arr))
print(arr[0])
print(len(arr))
```

Output:

```
list
1.0
3.0
```

### Parsing nested structures

Nested JSON objects become nested maps. Drill down with chained `[]`:

```nd
import "std:json" as json

let raw = "{\"users\": [{\"name\": \"alice\", \"role\": \"admin\"}, {\"name\": \"bob\", \"role\": \"user\"}]}"
let data = json.parse(raw)
let users = data["users"]
print(users[0]["name"])
print(users[1]["role"])
```

Output:

```
alice
user
```

### Parsing primitives

`json.parse("42")` → `42.0` (number). `json.parse("true")` → `true`
(bool). `json.parse("null")` → `nil`. `json.parse("\"hello\"")` →
`"hello"` (string, quotes stripped).

---

## 2. Inspecting parsed data

### Membership: has_key

Accessing a missing key raises a `Key error` — it does not return `nil`.
Always use `has_key` before accessing a key that might be absent:

```nd
import "std:json" as json

let data = json.parse("{\"name\": \"carol\"}")

if (has_key(data, "role")) {
    print("role: " + data["role"])
} else {
    print("no role set")
}
```

Output:

```
no role set
```

`has_key` is a top-level builtin — no import needed. It is O(1). Do not
use `std:collections`'s `has_key` instead — it performs an O(n) linear
scan. See [BUG-033](https://github.com/Masterplanner25/Nodus/issues/34).

### Enumeration: keys and values

`keys(map)` and `values(map)` are top-level builtins:

```nd
import "std:json" as json

let data = json.parse("{\"host\": \"localhost\", \"port\": 8080}")
print(keys(data))
print(values(data))
```

Output:

```
["host", "port"]
["localhost", 8080.0]
```

---

## 3. Generating JSON

`json.stringify(value)` serializes to a JSON string:

```nd
import "std:json" as json

let m = { "name": "bob", "score": 42, "active": true }
print(json.stringify(m))
print(json.stringify([1, 2.5, 3]))
print(json.stringify(nil))
print(json.stringify("hello"))
```

Output:

```
{"name": "bob", "score": 42, "active": true}
[1, 2.5, 3]
null
"hello"
```

Three things worth noting:

1. **Whole-number floats serialize without `.0`**: Nodus's `42.0` becomes
   `42` in JSON output. `str(42.0)` is `"42.0"` but `json.stringify(42.0)`
   is `"42"`. Use `json.stringify` when you need integer-looking JSON output.
2. **Records stringify too**: `json.stringify` accepts both maps and records.
3. **Strings get JSON-encoded**: `json.stringify("hello")` includes the
   surrounding double-quote characters in the output string.

### Writing JSON to a file

```nd
import "std:json" as json
import "std:fs" as fs

let result = { "status": "ok", "items": ["a", "b", "c"] }
fs.write("output.json", json.stringify(result))
```

---

## 4. Common patterns

### Config file with safe defaults

```nd
import "std:json" as json
import "std:fs" as fs

fn load_config(path) {
    let raw = fs.read(path)
    let cfg = json.parse(raw)

    let host = "localhost"
    let port = 8080
    if (has_key(cfg, "host")) { host = cfg["host"] }
    if (has_key(cfg, "port")) { port = cfg["port"] }

    return record { host: host, port: port }
}
```

> **Why not `utils.coalesce`?** Arguments are evaluated before the
> function is called. `utils.coalesce(cfg["port"], 8080)` raises a
> `Key error` before `coalesce` runs if `"port"` is absent. Use
> `has_key` + `if/else` for safe defaults on JSON data. See
> [BUG-034](https://github.com/Masterplanner25/Nodus/issues/35).

### Iterating an array of objects

When you have a JSON array of objects, use `col.map` and `col.filter`
with accessor functions. Pass functions, not string keys — `col.map`
calls `fn(item)`, not a field name:

```nd
fn get_name(e) { return e["name"] }
fn high_scorer(e) { return e["score"] >= 90 }
print(col.map(entries, get_name))
print(col.filter(entries, high_scorer))
```

---

## 5. Migrating from v2.0.x to v2.1.0

### What changed

In **v2.0.0**, `json.parse` returned a **record**. Records support
dot-access only: `data.name`. They do not support `has_key`, `keys`, or
`values`.

In **v2.1.0** (BUG-018), `json.parse` returns a **map**. This enables
`has_key`, `keys`, and `values` on parsed JSON — necessary for generic
JSON processing where field names are not known at write time.

### The error — and the fix

Any v2.0.x code using dot-access on `json.parse` output will fail:

```nd
let data = json.parse("{\"name\": \"shawn\"}")
print(data.name)  // v2.0.0 code
```

```
Type error at script.nd:2:7: Field access is only supported on records
```

Replace every `data.field` with `data["field"]`:

```nd
print(data["name"])  // v2.1.0
```

Search your codebase for `.parse(` and audit every downstream field access.

### Patterns that now work

```nd
import "std:json" as json

let data = json.parse("{\"name\": \"alice\", \"score\": 99}")
print(has_key(data, "score"))
print(has_key(data, "missing"))
print(keys(data))
print(values(data))
```

Output:

```
true
false
["name", "score"]
["alice", 99.0]
```

`has_key`, `keys`, and `values` all failed on the v2.0.0 record output.
They are now the idiomatic way to work with parsed JSON.

### What didn't change

`json.stringify` behavior, file I/O patterns, array → list parsing, and
float number representation are all unchanged from v2.0.0.

### Complete migration walkthrough

**v2.0.0:**

```nd
import "std:json" as json

fn process_user(raw_json) {
    let user = json.parse(raw_json)
    return user.name + " (" + user.role + ")"
}
```

**Fails in v2.1.0** with `Type error: Field access is only supported on records`.

**v2.1.0 rewrite (handles missing fields):**

```nd
import "std:json" as json

fn process_user(raw_json) {
    let user = json.parse(raw_json)
    let name = user["name"]
    let role = "guest"
    if (has_key(user, "role")) {
        role = user["role"]
    }
    return name + " (" + role + ")"
}

print(process_user("{\"name\": \"alice\", \"role\": \"admin\"}"))
print(process_user("{\"name\": \"bob\"}"))
```

Output:

```
alice (admin)
bob (guest)
```

---

## 6. Edge cases and gotchas

### Malformed JSON raises a runtime error

```nd
import "std:json" as json
json.parse("{not valid}")
```

```
Runtime error at script.nd:2:11: json_parse failed: Expecting property name enclosed in double quotes
```

An empty string produces `json_parse failed: Expecting value`. Both errors
come from Python's json module verbatim. Wrap with `try/catch` to handle
bad input — see [error-handling.md](error-handling.md) (coming soon).

### Accessing a missing key raises, not returns nil

`m["missing"]` raises `Key error: Missing map key: "missing"`. Guard with
`has_key`. There is no nil-returning fallback accessor in v2.1.0.

### JSON null → Nodus nil

A JSON `null` field becomes Nodus `nil`. Check with `== nil` or confirm
presence with `has_key` before accessing.

### Stringify removes `.0` from whole-number floats

`str(5.0)` → `"5.0"`. `json.stringify({"count": 5.0})` → `{"count": 5}`.
The output of `json.stringify` follows the JSON spec (integers without
decimal points); `str()` follows Nodus's float display rules.

---

## 7. What's not supported

`json.parse` is a whole-document parser — no streaming or incremental API.
`json.stringify` has no format options (no pretty-printing, no sorted keys,
no indentation). JSON comments (`//`, `/* */`) cause a parse error. Custom
encoders are not supported.

---

## 8. See also

- [standard-library.md — std:json](standard-library.md#4-stdjson) — full
  function reference
- [types-and-values.md — Records vs Maps](types-and-values.md#6-records-vs-maps--the-distinction) —
  the distinction this file depends on
- [error-handling.md](error-handling.md) (coming soon) — wrapping
  `json.parse` in `try/catch` for malformed-input recovery

---

<!--
TESTED EXAMPLES (16 total — files in /tmp/json-tests/)
1.  parse_object.nd — map type, bracket access, has_key, keys, values confirmed
2.  parse_dot_access.nd — "Type error: Field access is only supported on records" confirmed
3.  parse_array.nd — list type, indexing, len confirmed
4.  parse_primitives.nd — number/bool/nil/string from JSON confirmed
5.  parse_nested.nd — nested map+list drill-down confirmed
6.  pattern_missing_field.nd — has_key guard vs Key error confirmed
7.  stringify_map.nd — map/list/nil/bool/number/string stringify confirmed
8.  stringify_record.nd — records stringify to JSON confirmed
9.  error_malformed.nd — "json_parse failed: Expecting property name enclosed in double quotes" confirmed
10. error_partial.nd — "json_parse failed: Expecting value" confirmed
11. error_empty.nd — "json_parse failed: Expecting value" confirmed
12. migration_v20.nd — verbatim migration error confirmed
13. migration_v21.nd — v2.1 bracket access confirmed
14. migration_walkthrough.nd — full walkthrough with has_key guard confirmed
15. roundtrip.nd — float round-trip: stringify removes .0 confirmed
16. pattern_transform.nd — col.map/filter on parsed array confirmed

VERBATIM ERROR MESSAGES CAPTURED (3):
- Migration: "Type error at ...: Field access is only supported on records"
- Malformed: "Runtime error at ...: json_parse failed: Expecting property name enclosed in double quotes"
- Missing key: "Key error at ...: Missing map key: "role""

BEHAVIORAL FINDINGS (new — not filing as bugs, documenting only):
F16: json.stringify removes .0 from whole-number floats (42.0 → 42 in JSON output).
     This is correct JSON spec behavior, not a bug. Documented as a gotcha since
     it differs from Nodus str() behavior.
F17: json.stringify works on records, not just maps. LANGUAGE_SPEC says so but it's
     easy to miss. Confirmed: record { name: "alice", age: 30 } → {"name": "alice", "age": 30}.
F18: Parse error format is "Runtime error: json_parse failed: ..." (Python json
     module message verbatim). Not "JSON error" or "Parse error". Documented.
-->
