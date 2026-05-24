# Standard Library Reference

This file covers every built-in function and every `std:` module available
in Nodus v2.1.0. Built-ins require no import. Standard modules are imported
with `import "std:<name>" as <alias>`.

If you haven't read [types-and-values.md](types-and-values.md) yet, do that
first — every return type and error condition here assumes you understand the
record/map distinction and float-only numbers.

---

## Contents

1. [Built-in functions](#1-built-in-functions)
2. [std:strings](#2-stdstrings)
3. [std:collections](#3-stdcollections)
4. [std:json](#4-stdjson)
5. [std:math](#5-stdmath)
6. [std:fs](#6-stdfs)
7. [std:path](#7-stdpath)
8. [std:memory](#8-stdmemory)
9. [std:utils](#9-stdutils)
10. [std:runtime](#10-stdruntime)
11. [Experimental modules](#11-experimental-modules)

---

## 1. Built-in functions

These functions are always available. No import needed.

### Type and conversion

| Function | Returns | Description |
|----------|---------|-------------|
| `type(x)` | `string` | Type name: `"nil"`, `"bool"`, `"number"`, `"string"`, `"list"`, `"map"`, `"record"`, `"function"` |
| `str(x)` | `string` | String representation of any value |
| `len(x)` | `number` | Length of a list or string (returns a float) |

```nd
print(type(42))
print(type("hello"))
print(type([1, 2, 3]))
print(str(3.14))
print(len([10, 20, 30]))
print(len("hello"))
```

Output:

```
number
string
list
3.14
3.0
5.0
```

`len` always returns a float. `str(3.14)` returns `"3.14"`; `str(10.0)` returns
`"10.0"` — there is no way to strip the `.0` in v2.1.0.

### Output

| Function | Returns | Description |
|----------|---------|-------------|
| `print(x)` | `nil` | Prints the string representation of `x` followed by a newline |

`print` accepts exactly one argument. To print multiple values, concatenate
them: `print("x=" + str(x))`.

### Map operations

| Function | Returns | Description |
|----------|---------|-------------|
| `has_key(map, key)` | `bool` | `true` if `key` is present in `map` (O(1)) |
| `keys(map)` | `list` | List of all string keys in `map` |
| `values(map)` | `list` | List of all values in `map` (same order as `keys`) |

```nd
let cfg = { "host": "localhost", "port": 8080 }
print(has_key(cfg, "host"))
print(has_key(cfg, "timeout"))
print(keys(cfg))
print(values(cfg))
```

Output:

```
true
false
["host", "port"]
["localhost", 8080.0]
```

`has_key`, `keys`, and `values` operate on maps only. Calling them on a record
raises a type error at runtime. Use `has_key` before accessing a map key that
might be absent — accessing a missing key raises a `Key error` rather than
returning `nil`.

> `std:collections` also exports a `has_key` function, but it is an O(n)
> linear scan. Always prefer the builtin `has_key` for map lookups.

### List mutation

| Function | Returns | Description |
|----------|---------|-------------|
| `list_push(list, value)` | `list` | Appends `value` to `list` in place; returns the list |
| `list_pop(list)` | value | Removes and returns the last element; error on empty list |

```nd
let nums = [1, 2, 3]
list_push(nums, 4)
print(nums)
let last = list_pop(nums)
print(last)
print(nums)
```

Output:

```
[1.0, 2.0, 3.0, 4.0]
4.0
[1.0, 2.0, 3.0]
```

`list_push` and `list_pop` mutate the list in place. `list_pop` on an empty
list raises `Index error: Cannot pop from an empty list`.

### Timing

| Function | Returns | Description |
|----------|---------|-------------|
| `clock()` | `number` | Milliseconds since epoch |

```nd
let t0 = clock()
let sum = 0
let i = 0
while (i < 1000) {
    sum = sum + i
    i = i + 1
}
let elapsed = clock() - t0
print("elapsed ms: " + str(elapsed))
```

---

## 2. std:strings

```nd
import "std:strings" as strings
```

| Function | Signature | Returns | Description |
|----------|-----------|---------|-------------|
| `upper` | `(s)` | `string` | Uppercase |
| `lower` | `(s)` | `string` | Lowercase |
| `trim` | `(s)` | `string` | Strip leading/trailing whitespace (spaces, tabs, newlines) |
| `split` | `(s, delimiter)` | `list` | Split `s` by `delimiter`; returns list of strings |
| `contains` | `(s, substring)` | `bool` | `true` if `substring` appears in `s` |
| `replace` | `(s, old, new)` | `string` | Replace **all** occurrences of `old` with `new` |
| `join` | `(items, sep)` | `string` | Join list items into a string; each item converted via `str()` |
| `repeat` | `(s, n)` | `string` | Repeat `s` exactly `n` times; `n=0` returns `""` |
| `is_blank` | `(s)` | `bool` | `true` only if `len(s) == 0`; does **not** match whitespace-only strings |

```nd
import "std:strings" as strings

print(strings.upper("hello"))
print(strings.lower("WORLD"))
print(strings.trim("  hi there  "))
print(strings.split("a,b,c", ","))
print(strings.contains("hello world", "world"))
print(strings.replace("foo bar foo", "foo", "baz"))
print(strings.join(["x", "y", "z"], " | "))
print(strings.repeat("ab", 3))
print(strings.is_blank(""))
print(strings.is_blank("   "))
```

Output:

```
HELLO
world
hi there
["a", "b", "c"]
true
baz bar baz
x | y | z
ababab
true
false
```

`is_blank` is equivalent to `len(s) == 0`. If you need to detect a
whitespace-only string, use `strings.trim(s) == ""` instead.

---

## 3. std:collections

```nd
import "std:collections" as col
```

### Higher-order list operations

| Function | Signature | Returns | Description |
|----------|-----------|---------|-------------|
| `map` | `(list, fn)` | `list` | New list: each element transformed by `fn(item)` |
| `filter` | `(list, fn)` | `list` | New list: elements where `fn(item)` is truthy |
| `reduce` | `(list, fn, initial)` | value | Accumulates: `fn(acc, item)` applied left to right starting from `initial` |

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

`map` and `filter` return new lists and do not modify the original.

### Mutating list operations

| Function | Signature | Returns | Description |
|----------|-----------|---------|-------------|
| `push` | `(list, value)` | `list` | Append `value` to `list` in place; returns the list |
| `pop` | `(list)` | value | Remove and return the last element |

Both `push` and `pop` mutate the list in place. They wrap the builtin
`list_push` and `list_pop`.

### List utilities

| Function | Signature | Returns | Description |
|----------|-----------|---------|-------------|
| `first` | `(list)` | value | First element (`list[0]`) |
| `last` | `(list)` | value | Last element |
| `list_sum` | `(list)` | `number` | Sum of all numbers in the list |

```nd
import "std:collections" as col

let nums = [10, 20, 30, 40]
print(col.first(nums))
print(col.last(nums))
print(col.list_sum(nums))
```

Output:

```
10.0
40.0
100.0
```

### Map check (avoid — use builtin instead)

`std:collections` exports a `has_key(map, key)` that performs a linear scan
(O(n)). For map membership tests, use the builtin `has_key` instead — it is
O(1) and requires no import.

---

## 4. std:json

```nd
import "std:json" as json
```

| Function | Signature | Returns | Description |
|----------|-----------|---------|-------------|
| `parse` | `(s)` | `map` or `list` | Parse a JSON string |
| `stringify` | `(value)` | `string` | Serialize a map or list to JSON |

`json.parse` always returns a **map** when the JSON root is an object, and a
**list** when the JSON root is an array. In v2.0.0, `parse` returned a record;
v2.1.0 changed this to a map (breaking change). Code using dot-access on parsed
JSON — e.g. `data.name` — will fail with `Field access is only supported on
records`. Use bracket-access: `data["name"]`.

```nd
import "std:json" as json

let raw = "{\"user\": \"alice\", \"score\": 99}"
let data = json.parse(raw)
print(type(data))
print(data["user"])
print(data["score"])
print(has_key(data, "user"))
print(has_key(data, "missing"))
```

Output:

```
map
alice
99.0
true
false
```

```nd
import "std:json" as json

let m = { "name": "bob", "active": true }
print(json.stringify(m))

let arr = [1, 2, 3]
print(json.stringify(arr))
```

Output:

```
{"name": "bob", "active": true}
[1.0, 2.0, 3.0]
```

For optional field access patterns, use `has_key` before indexing:

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

---

## 5. std:math

```nd
import "std:math" as math
```

| Function | Signature | Returns | Description |
|----------|-----------|---------|-------------|
| `abs` | `(n)` | `number` | Absolute value |
| `min` | `(a, b)` | `number` | Smaller of two numbers |
| `max` | `(a, b)` | `number` | Larger of two numbers |
| `floor` | `(n)` | `number` | Round down to nearest integer-valued float |
| `ceil` | `(n)` | `number` | Round up to nearest integer-valued float |
| `sqrt` | `(n)` | `number` | Square root; runtime error if `n < 0` |
| `random` | `()` | `number` | Pseudo-random float in `[0, 1)` |

```nd
import "std:math" as math

print(math.abs(-7))
print(math.min(3, 9))
print(math.max(3, 9))
print(math.floor(3.9))
print(math.ceil(3.1))
print(math.sqrt(25))
```

Output:

```
7.0
3.0
9.0
3.0
4.0
5.0
```

All functions return floats. `floor` and `ceil` return whole-number floats
(`3.0`, `4.0`), not strings. `math.sqrt(-1)` raises a runtime error.

---

## 6. std:fs

```nd
import "std:fs" as fs
```

| Function | Signature | Returns | Description |
|----------|-----------|---------|-------------|
| `read` | `(path)` | `string` | Read entire file contents as a string |
| `write` | `(path, content)` | `nil` | Write (or overwrite) file with `content` |
| `append` | `(path, content)` | `nil` | Append `content` to file |
| `exists` | `(path)` | `bool` | `true` if path exists (file or directory) |
| `listdir` | `(path)` | `list` | List of filenames in directory |
| `ensure_dir` | `(path)` | `nil` | Create directory if it does not exist |

```nd
import "std:fs" as fs

fs.write("notes.txt", "hello")
print(fs.exists("notes.txt"))
fs.append("notes.txt", " world")
print(fs.read("notes.txt"))

fs.ensure_dir("output")
print(fs.exists("output"))

let files = fs.listdir(".")
print(type(files))
```

Output:

```
true
hello world
true
list
```

All filesystem operations are subject to the VM's path-sandboxing policy.
If the runtime is configured with a restricted path, operations outside
that path raise a runtime error.

---

## 7. std:path

```nd
import "std:path" as path
```

| Function | Signature | Returns | Description |
|----------|-----------|---------|-------------|
| `join` | `(a, b)` | `string` | Join two path segments using the OS separator |
| `dirname` | `(path)` | `string` | Parent directory portion |
| `basename` | `(path)` | `string` | Filename including extension |
| `ext` | `(path)` | `string` | Extension **without** the leading dot |
| `stem` | `(path)` | `string` | Filename without extension |

```nd
import "std:path" as path

let p = "docs/guide/getting-started.md"
print(path.dirname(p))
print(path.basename(p))
print(path.ext(p))
print(path.stem(p))
print(path.join("src", "main.nd"))
```

Output:

```
docs/guide
getting-started.md
md
getting-started
src\main.nd
```

Two things to note:

1. `path.join` takes exactly **two** arguments. To join three or more
   segments, chain calls: `path.join(path.join("a", "b"), "c")`.
2. `path.ext` returns the extension **without** a leading dot. `ext("file.nd")`
   returns `"nd"`, not `".nd"`.
3. `path.join` uses the OS path separator — backslash on Windows, forward
   slash elsewhere.

---

## 8. std:memory

```nd
import "std:memory" as mem
```

`std:memory` is a simple key-value store that persists for the lifetime of
the running script. It is not shared between scripts or persisted to disk.

| Function | Signature | Returns | Description |
|----------|-----------|---------|-------------|
| `put` | `(key, value)` | `nil` | Store `value` under string `key` |
| `get` | `(key)` | value | Retrieve value for `key`; returns `nil` if absent |
| `has` | `(key)` | `bool` | `true` if `key` is set |
| `delete` | `(key)` | `nil` | Remove `key` |
| `keys` | `()` | `list` | List of all stored keys |

```nd
import "std:memory" as mem

mem.put("score", 42)
mem.put("name", "alice")
print(mem.get("score"))
print(mem.has("name"))
print(mem.has("missing"))
print(mem.keys())

mem.delete("score")
print(mem.has("score"))
print(mem.get("score"))
```

Output:

```
42.0
true
false
["score", "name"]
false
nil
```

---

## 9. std:utils

```nd
import "std:utils" as utils
```

| Function | Signature | Returns | Description |
|----------|-----------|---------|-------------|
| `clamp` | `(value, min, max)` | `number` | Clamp `value` to the range `[min, max]` |
| `coalesce` | `(...)` | value | Return the first non-`nil` argument; `nil` if all are `nil` |

```nd
import "std:utils" as utils

print(utils.clamp(5, 0, 10))
print(utils.clamp(-3, 0, 10))
print(utils.clamp(15, 0, 10))

print(utils.coalesce(nil, nil, "found"))
print(utils.coalesce(nil, nil, nil))
print(utils.coalesce("first", "second"))
```

Output:

```
5.0
0.0
10.0
found
nil
first
```

`coalesce` is useful for providing defaults when a value might be absent:

```nd
import "std:utils" as utils
import "std:json" as json

let data = json.parse("{\"host\": \"prod.example.com\"}")
let host = utils.coalesce(data["host"], "localhost")
let port = utils.coalesce(data["port"], 8080)
print(host)
print(port)
```

Wait — the above will raise a `Key error` on `data["port"]` before
`coalesce` can provide the default, because Nodus evaluates arguments
before calling the function. Use `has_key` to guard:

```nd
import "std:utils" as utils
import "std:json" as json

let data = json.parse("{\"host\": \"prod.example.com\"}")
let port_raw = nil
if (has_key(data, "port")) {
    port_raw = data["port"]
}
let port = utils.coalesce(port_raw, 8080)
print(port)
```

Output:

```
8080.0
```

---

## 10. std:runtime

```nd
import "std:runtime" as rt
```

`std:runtime` provides introspection into the running VM — function
metadata, record fields, type details, and timing.

### Function introspection

| Function | Signature | Returns | Description |
|----------|-----------|---------|-------------|
| `fn_name` | `(fn)` | `string` | Name of a function value |
| `fn_arity` | `(fn)` | `number` | Number of declared parameters (as a float) |
| `fn_module` | `(fn)` | `string` or `nil` | Module the function was defined in |

```nd
import "std:runtime" as rt

fn add(a, b) { return a + b }

print(rt.fn_name(add))
print(rt.fn_arity(add))
print(rt.fn_module(add))
```

Output:

```
add
2.0
nil
```

### Record introspection

| Function | Signature | Returns | Description |
|----------|-----------|---------|-------------|
| `fields` | `(record)` | `list` | List of field names for a record |
| `has` | `(record, name)` | `bool` | `true` if record has named field |

```nd
import "std:runtime" as rt

let p = record { name: "alice", age: 30 }
print(rt.fields(p))
print(rt.has(p, "name"))
print(rt.has(p, "email"))
```

Output:

```
["name", "age"]
true
false
```

### Type detail

| Function | Signature | Returns | Description |
|----------|-----------|---------|-------------|
| `typeof` | `(x)` | `string` | Detailed type name |

`rt.typeof` differs from the builtin `type()`:

| Value | `type(x)` | `rt.typeof(x)` |
|-------|-----------|----------------|
| `42` (whole float) | `"number"` | `"int"` |
| `3.14` (fractional float) | `"number"` | `"float"` |
| `"hello"` | `"string"` | `"string"` |
| `true` | `"bool"` | `"bool"` |
| `nil` | `"nil"` | `"nil"` |
| `[1, 2]` | `"list"` | `"list"` |
| `{ "a": 1 }` | `"map"` | `"map"` |

Use `type()` for type checks in application logic. Use `rt.typeof()` when
you need to distinguish whole-number floats from fractional floats.

### Timing and stack

| Function | Signature | Returns | Description |
|----------|-----------|---------|-------------|
| `time_ms` | `()` | `number` | Milliseconds since epoch (same as `clock()`) |
| `stack_depth` | `()` | `number` | Current call stack depth |
| `stack_frame` | `(index)` | `map` | Stack frame info at given index |

### Event and task inspection

| Function | Signature | Returns | Description |
|----------|-----------|---------|-------------|
| `events` | `()` | `list` | Runtime event log |
| `clear_events` | `()` | `nil` | Clear the event log |
| `tasks` | `()` | `list` | All active task graph tasks |
| `task` | `(id)` | `map` | Task info by ID |
| `scheduler` | `()` | `map` | Scheduler statistics |

---

## 11. Experimental modules

The following modules are available in v2.1.0 but are classified as
**experimental** in the [stability policy](../governance/STABILITY.md).
Their APIs may change before they are stabilized.

### std:async

```nd
import "std:async" as async
```

Coroutine and concurrency primitives.

| Function | Description |
|----------|-------------|
| `sleep(ms)` | Suspend current coroutine for `ms` milliseconds |
| `parallel(fns)` | Run a list of zero-arg functions concurrently; returns list of results |
| `series(fns)` | Run a list of zero-arg functions sequentially; returns list of results |
| `queue(fn)` | Queue a function for async execution |
| `worker_pool(n, fns)` | Run `fns` across `n` workers |
| `pipeline(fns)` | Chain functions as a pipeline |

Coroutines and the scheduler are experimental. Do not rely on their behavior
being stable across minor versions.

### std:tools

```nd
import "std:tools" as tools
```

Adapter for registered runtime tool services.

| Function | Description |
|----------|-------------|
| `execute(name, args)` | Call a named tool with the given args map |
| `available(name)` | `true` if the tool is registered in this runtime |
| `describe(name)` | Returns the tool's description string |

Tools are registered by the embedding runtime, not by user scripts. If no
tools are registered, `available` returns `false` and `execute` raises an
error.

### std:agent

```nd
import "std:agent" as agent
```

Adapter for registered runtime agent services.

| Function | Description |
|----------|-------------|
| `call(name, args)` | Call a named agent with the given args map |
| `available(name)` | `true` if the agent is registered in this runtime |
| `describe(name)` | Returns the agent's description string |

---

## Quick reference: which module for what

| Need | Use |
|------|-----|
| Trim whitespace, split, join | `std:strings` |
| Transform or filter a list | `std:collections` |
| Parse / serialize JSON | `std:json` |
| Math operations | `std:math` |
| Read/write files | `std:fs` |
| Build file paths | `std:path` |
| Ephemeral key-value store | `std:memory` |
| Clamp or default a value | `std:utils` |
| Inspect functions or records | `std:runtime` |
| Check if a map key exists | builtin `has_key` (no import) |
| Append to a list | builtin `list_push` (no import) |

---

<!--
TESTED EXAMPLES (all code blocks with nd code verified):
1. type/str/len builtins — confirmed
2. print builtin — confirmed
3. has_key/keys/values — confirmed
4. list_push/list_pop — confirmed
5. clock timing pattern — structure confirmed (clock() returns number, confirmed)
6. std:strings full suite — confirmed (upper/lower/trim/split/contains/replace/join/repeat)
7. strings.is_blank — confirmed: true for "", false for "   " (checks len only)
8. std:collections map/filter/reduce — confirmed
9. std:collections first/last/list_sum — confirmed
10. std:json parse — confirmed (returns map, bracket access)
11. std:json stringify — confirmed
12. std:json has_key guard pattern — confirmed
13. std:math abs/min/max/floor/ceil/sqrt — confirmed
14. std:fs write/exists/append/read/ensure_dir/listdir — confirmed
15. std:path dirname/basename/ext/stem/join — confirmed
16. std:memory put/get/has/delete/keys — confirmed
17. std:utils clamp — confirmed
18. std:utils coalesce — confirmed
19. std:utils coalesce-with-guard pattern — confirmed
20. std:runtime fn_name/fn_arity/fn_module — confirmed
21. std:runtime fields/has — confirmed
22. std:runtime typeof comparison table — confirmed (int vs float vs number)

BEHAVIORAL FINDINGS:
F7: strings.is_blank checks len(s)==0 only. Does NOT match whitespace-only strings.
    "   " → false. Workaround: strings.trim(s) == "".
F8: std:collections.has_key is O(n) linear scan. Builtin has_key is O(1).
F9: path.join takes exactly 2 args. Extra args cause undefined behavior.
F10: path.ext returns extension without leading dot ("nd" not ".nd").
F11: path.join uses OS separator (backslash on Windows).
F12: rt.typeof returns "int" for whole-number floats, "float" for fractional.
     The builtin type() always returns "number" for all floats.
F13: list_push mutates in place. col.push wraps list_push (same semantics).
F14: coalesce evaluates all args before the function is called (eager evaluation).
     Cannot use as a nil-safe accessor; must guard with has_key.
F15: std:utils is not documented in LANGUAGE_SPEC.md.
-->
