# Working with Maps

Maps are Nodus's flexible key-value structure for data whose shape is
discovered at runtime. This file covers building and manipulating maps in
your own code. For the record/map distinction see
[types-and-values.md — Records vs Maps](types-and-values.md#6-records-vs-maps--the-distinction).
For maps from `json.parse` see [working-with-json.md](working-with-json.md).

---

## 1. Building a map

Map literals require **quoted string keys**. `{}` creates an empty map.

```nd
let scores = { "alice": 92, "bob": 87 }
print(type(scores))

let empty = {}
print(type(empty))
print(len(keys(empty)))
```

Output:

```
map
map
0.0
```

**Multi-line literals** work as long as each value starts on the same
line as its key. Putting `[` or `{` on the line *after* the key causes
a parse error:

```nd
// Works — value starts on same line as key
let cfg = {
    "host": "localhost",
    "items": ["a", "b", "c"]
}

// BREAKS — "Unexpected end of statement" at the [
let bad = {
    "items":
        ["a", "b"]
}
```

---

## 2. Adding and updating entries

`m["key"] = value` adds or updates a key in place:

```nd
let m = { "x": 1 }
m["y"] = 2
m["x"] = 99
print(keys(m))
print(m["x"])
```

Output:

```
["x", "y"]
99.0
```

---

## 3. Reading from a map

Bracket access is the only valid form. Accessing a missing key raises a
`Key error` — it does not return `nil`. Guard with `has_key`:

```nd
let m = { "host": "localhost" }

if (has_key(m, "host")) {
    print(m["host"])
}

if (has_key(m, "port")) {
    print(m["port"])
} else {
    print("using default port")
}
```

Output:

```
localhost
using default port
```

Missing-key error for reference:

```
Key error at script.nd:2:9: Missing map key: "missing"
```

---

## 4. Iterating a map

`keys(m)` and `values(m)` return lists in **insertion order**:

```nd
let m = { "c": 3, "a": 1, "b": 2 }
for k in keys(m) {
    print(k + " = " + str(m[k]))
}
```

Output:

```
c = 3.0
a = 1.0
b = 2.0
```

---

## 5. Removing entries

There is no `delete` operator. Setting a key to `nil` keeps it
present — `has_key` still returns `true` and it still appears in `keys`.
To exclude a key, rebuild the map by iterating `keys` and copying only
what you want to keep.

---

## 6. Common patterns

### Counting occurrences

```nd
let words = ["apple", "banana", "apple", "cherry", "banana", "apple"]
let counts = {}
for w in words {
    if (has_key(counts, w)) {
        counts[w] = counts[w] + 1
    } else {
        counts[w] = 1
    }
}
print(counts["apple"])
print(counts["banana"])
```

Output:

```
3.0
2.0
```

### Lookup table with fallback

```nd
let labels = { "ok": "Success", "err": "Error", "pending": "In Progress" }

fn label_for(code) {
    if (has_key(labels, code)) { return labels[code] }
    return "Unknown"
}

print(label_for("ok"))
print(label_for("missing"))
```

Output:

```
Success
Unknown
```

### Safe default helper

`utils.coalesce` doesn't work for map access (see [Section 7](#7-footguns)).
Use a small helper instead:

```nd
fn get_or(m, key, default_val) {
    if (has_key(m, key)) { return m[key] }
    return default_val
}

let cfg = { "host": "prod.example.com" }
print(get_or(cfg, "host", "localhost"))
print(get_or(cfg, "port", 8080))
```

Output:

```
prod.example.com
8080.0
```

---

## 7. Footguns

### Bare identifier keys create a record, not a map

`{ name: "Alice" }` with a bare (unquoted) identifier key is a
**record literal** in v3.0 — not a map. To create a map with a
literal string key, always quote it:

```nd
let m = { "name": "Alice" }  // map — bracket access: m["name"]
let r = { name: "Alice" }    // record — dot access: r.name
```

To use a variable's value as a map key, wrap it in parentheses:

```nd
let field = "score"
let m = { (field): 99 }     // map with key "score"
print(keys(m))              // ["score"]
```

Using a bare identifier where a map key is expected (e.g. inside
`json.parse` result manipulation) is a parse error in v3.0, with a
message naming the two correct forms.

---

## 8. Maps vs records — quick rule

Use a **map** when keys are discovered at runtime (JSON, config, user
input, accumulation). Use a **record** when keys are fixed at design
time. Full treatment in
[types-and-values.md](types-and-values.md#6-records-vs-maps--the-distinction).

---

## 9. See also

- [types-and-values.md — Records vs Maps](types-and-values.md#6-records-vs-maps--the-distinction)
- [working-with-json.md](working-with-json.md) — maps from `json.parse`
- [standard-library.md](standard-library.md#1-built-in-functions) — `has_key`, `keys`, `values`
- [error-handling.md](error-handling.md) — `try/catch` for map access, `has_key` guard patterns

---

<!--
TESTED EXAMPLES (13 total — files in /tmp/maps-tests/)
1.  construct.nd — {quoted keys} → map, {} → empty map confirmed
2.  multiline_map.nd — multi-line with simple values works confirmed
3.  multiline_list_inline.nd — list value on same line as key works confirmed
4.  multiline_nested.nd — list value on new line → syntax error confirmed
5.  mutate.nd — add and update in-place confirmed
6.  access_missing.nd — "Key error: Missing map key: "missing"" confirmed
7.  iteration.nd — insertion-order iteration confirmed
8.  delete_key.nd — nil assignment keeps key; no true delete confirmed
9.  pattern_count.nd — counting pattern confirmed
10. pattern_lookup.nd — lookup table with fallback confirmed
11. pattern_default.nd — get_or helper confirmed
12. dynamic_key.nd — bare identifier uses variable VALUE as key confirmed
13. nonstring_key_access.nd — non-string keys via dynamic syntax accessible confirmed

BEHAVIORAL FINDINGS (historical — tested against v2.1.1; resolved in v3.0):
F19: Multi-line map literals failed when a value ([, {) started on a line after
     its key. RESOLVED in v3.0 (BUG-039 fix).
F20: Bare identifier map keys used the variable's runtime VALUE as the key.
     CHANGED in v3.0: bare identifier keys now create a record literal, not a map.
     Using a bare identifier where a quoted key is expected is a parse error.

v2.2/v3.0 fixes merged:
- BUG-030 (#31): bare identifier map key disambiguation — now a parse error with hint
- BUG-033 (#34): collections.has_key O(n) shadow — fixed, builtin now used
- BUG-034 (#35): coalesce eager evaluation — fixed, now lazy
- BUG-034 (#35): coalesce eager evaluation
-->
