# Standard Library Reference

This file covers every built-in function and every `std:` module available
in Nodus v4.0. Built-ins require no import. Standard modules are imported
with `import "std:<name>" as <alias>`.

If you haven't read [types-and-values.md](types-and-values.md) yet, do that
first — every return type and error condition here assumes you understand the
record/map distinction and the two numeric kinds (`number` and `int`).

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
| `type(x)` | `string` | Type name: `"nil"`, `"bool"`, `"float"`, `"int"`, `"string"`, `"list"`, `"map"`, `"record"`, `"function"`, `"error"` |
| `str(x)` | `string` | String representation of any value |
| `len(x)` | `number` | Length of a list or string (returns a float) |

```nd
print(type(42))
print(type(42i))
print(type("hello"))
print(type([1, 2, 3]))
print(str(3.14))
print(str(42i))
print(len([10, 20, 30]))
print(len("hello"))
```

Output:

```
float
int
string
list
3.14
42
3.0
5.0
```

`type(x)` returns `"float"` for floating-point values and `"int"` for integer values.
`type(x)` returns `"error"` for err records returned by stdlib functions.

`len` always returns a float (e.g., `len([1, 2, 3])` → `3.0`). This is a
known inconsistency; returning an `int` is tracked for a future release. `str(42i)` returns `"42"` (no `.0`);
`str(10.0)` returns `"10.0"`. Use integer literals or `math.to_int` to get
whole-number output without the `.0`.

`print(42i)` displays `42` (not `42i` — the `i` suffix is source syntax only,
not part of the runtime representation).

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
| `is_blank` | `(s)` | `bool` | `true` if the string is empty or contains only whitespace |

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
true
```

`is_blank` returns `true` for empty strings and whitespace-only strings (spaces, tabs, newlines).

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
| `parse` | `(s)` | `map`, `list`, or err record | Parse a JSON string; returns `parse_error` err record on invalid JSON |
| `stringify` | `(value)` | `string` or err record | Serialize a value to JSON; returns `type_error` err record for non-serializable values. `int` values are serialized as JSON numbers (e.g., `42i` → `42`). |
| `parse_int` | `(s)` | `int` or err record | Parse a decimal string as an arbitrary-precision integer |

`json.parse` always returns a **map** when the JSON root is an object, and a
**list** when the JSON root is an array. In v2.0.0, `parse` returned a record;
v2.1.0+ changed this to a map (breaking change). Code using dot-access on parsed
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
[1, 2, 3]
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

### json.parse errors

`json.parse` returns a `parse_error` err record on invalid JSON (it does not
throw). The error message is in Nodus voice with line and column:

```nd
import "std:json" as json

let r = json.parse("{bad json}")
print(type(r))
print(r.kind)
print(r.message)
```

Output:

```
error
parse_error
invalid JSON at line 1 column 2: expected property name
```

### json.parse_int — large integers without precision loss

`json.parse_int` parses a decimal integer string into an arbitrary-precision
`int`. Use it when you need to read JSON integer values that exceed float
precision (> 2^53):

```nd
import "std:json" as json

print(json.parse_int("9007199254740993"))
print(type(json.parse_int("42")))
```

Output:

```
9007199254740993
int
```

`json.parse_int` returns a `parse_error` err record for non-integer strings:

```nd
import "std:json" as json

let r = json.parse_int("1e9")
print(r.kind)
print(r.message)
```

Output:

```
parse_error
not an integer (scientific notation): "1e9"
```

---

## 5. std:math

```nd
import "std:math" as math
```

### Float operations

| Function | Signature | Returns | Description |
|----------|-----------|---------|-------------|
| `abs` | `(n)` | `number` | Absolute value |
| `min` | `(a, b)` | `number` | Smaller of two numbers |
| `max` | `(a, b)` | `number` | Larger of two numbers |
| `floor` | `(n)` | `number` | Round down to nearest integer-valued float |
| `ceil` | `(n)` | `number` | Round up to nearest integer-valued float |
| `sqrt` | `(n)` | `number` | Square root; returns `value_error` err if `n < 0` |
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

All float operations return `number`. `floor` and `ceil` return whole-number
floats (`3.0`, `4.0`), not strings.

### Integer operations

| Function | Signature | Returns | Description |
|----------|-----------|---------|-------------|
| `parse_int` | `(s)` | `int` or err | Parse a decimal string as arbitrary-precision integer |
| `to_int` | `(n)` | `int` | Truncate a float to integer (toward zero) |
| `to_float` | `(n)` | `number` | Convert an integer to float |
| `is_int` | `(x)` | `bool` | `true` if `x` is an `int` value |
| `idiv` | `(a, b)` | `int` or err | Integer division, truncating toward zero; both args must be `int` |

```nd
import "std:math" as math

print(math.parse_int("42"))       // 42
print(math.parse_int("-100"))     // -100
print(type(math.parse_int("5"))) // int
print(math.to_int(3.7))          // 3   (truncates toward zero)
print(math.to_int(-3.7))         // -3
print(math.to_float(5i))         // 5.0
print(math.is_int(3i))           // true
print(math.is_int(3.0))          // false
print(math.idiv(7i, 2i))         // 3
print(math.idiv(-7i, 2i))        // -3  (truncates toward zero, not floor)
```

Output:

```
42
-100
int
3
-3
5.0
true
false
3
-3
```

`math.parse_int` returns a `parse_error` err record when the string is not a
valid integer (including decimal strings or scientific notation). `math.idiv`
returns a `type_error` err if either argument is not an `int`, and a
`math_error` err for division by zero.

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
Operations outside the allowed path raise a `sandbox` runtime error (thrown,
not returned as an err record).

### fs error records

When a filesystem operation fails for an I/O reason, the function **returns**
an `io_error` err record. It does not throw. The message is in Nodus voice:

| Failure | err.message |
|---------|------------|
| File does not exist | `file not found: "/path"` |
| Permission denied | `permission denied: "/path"` |
| Path is a directory, not a file | `expected a file, got a directory: "/path"` |
| File is not valid UTF-8 | `file is not valid UTF-8: "/path"` |
| Directory does not exist | `directory not found: "/path"` |
| Path is a file, not a directory | `expected a directory, got a file: "/path"` |
| Parent directory missing on write | `cannot write file, parent directory does not exist: "/path"` |

```nd
import "std:fs" as fs

let content = fs.read("/missing/file.txt")
print(type(content))    // error
print(content.kind)     // io_error
print(content.message)  // file not found: "/missing/file.txt"
```

---

## 7. std:path

```nd
import "std:path" as path
```

| Function | Signature | Returns | Description |
|----------|-----------|---------|-------------|
| `join` | `(parts)` | `string` | Join a list of path segments using the OS separator |
| `dirname` | `(path)` | `string` | Parent directory portion |
| `basename` | `(path)` | `string` | Filename including extension |
| `ext` | `(path)` | `string` | Extension including the leading dot (e.g. `".nd"`); `""` if none |
| `stem` | `(path)` | `string` | Filename without extension |

```nd
import "std:path" as path

let p = "docs/guide/getting-started.md"
print(path.dirname(p))
print(path.basename(p))
print(path.ext(p))
print(path.stem(p))
print(path.join(["src", "main.nd"]))
print(path.join(["a", "b", "c"]))
```

Output:

```
docs/guide
getting-started.md
.md
getting-started
src\main.nd
a\b\c
```

One thing to note: `path.join` uses the OS path separator — backslash on
Windows, forward slash elsewhere.

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
| `coalesce` | `(a, b)` | value | Return `a` if it is not `nil`, otherwise `b` |
| `get` | `(map, key, default)` | value | Return `map[key]` if the key exists, otherwise `default` |

```nd
import "std:utils" as utils

print(utils.clamp(5, 0, 10))
print(utils.clamp(-3, 0, 10))
print(utils.clamp(15, 0, 10))

print(utils.coalesce(nil, "found"))
print(utils.coalesce(nil, nil))
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

**Tip:** `coalesce` evaluates both arguments eagerly — if the first argument is a map access for a key that may not exist, it raises before `coalesce` is ever called. Use `utils.get` to safely read from a map with a default:

```nd
import "std:utils" as utils
import "std:json" as json

let data = json.parse("{\"host\": \"prod.example.com\"}")
let host = utils.get(data, "host", "localhost")
let port = utils.get(data, "port", 8080)
print(host)
print(port)
```

Output:

```
prod.example.com
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

| Value | `type(x)` | `rt.typeof(x)` | Notes |
|-------|-----------|----------------|-------|
| `42` (float) | `"float"` | `"float"` | Plain number literals are floats |
| `3.14` (float) | `"float"` | `"float"` | |
| `42i` (integer) | `"int"` | `"int"` | Integer literals have `i` suffix |
| `"hello"` | `"string"` | `"string"` | |
| `true` | `"bool"` | `"bool"` | |
| `nil` | `"nil"` | `"nil"` | |
| `[1, 2]` | `"list"` | `"list"` | |
| `{ "a": 1 }` | `"map"` | `"map"` | |

Both `type()` and `rt.typeof()` return `"float"` for floats and `"int"` for
integer values. The main difference is that `rt.typeof()` can additionally
return `"module"` for runtime module objects, which `type()` cannot.

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

The following modules are classified as **experimental** in the
[stability policy](../governance/STABILITY.md). Their APIs may change
before they are stabilized.

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

**Note:** `channel()`, `send()`, `recv()`, `close()`, `spawn()`, and
`coroutine()` are **VM builtins**, not exports of `std:async`. Use them
directly without an import — `async.channel()` will fail with "Missing module
export: channel". This is intentional: these primitives are always available
regardless of whether `std:async` is imported.

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
F7: strings.is_blank now checks whitespace-only strings via trim (fixed BUG-035).
F8: std:collections.has_key is now O(1) via map_has_key alias (fixed BUG-033).
F9: path.join now accepts a list of segments: path.join(["a","b","c"]) (fixed BUG-036).
F10: path.ext now returns extension with leading dot (".nd" not "nd") (fixed BUG-037).
F11: path.join uses OS separator (backslash on Windows).
F12: rt.typeof returns "int" for whole-number floats, "float" for fractional.
     The builtin type() always returns "number" for all floats.
F13: list_push mutates in place. col.push wraps list_push (same semantics).
F14: coalesce evaluates both args eagerly. Use utils.get(map, key, default) for
     safe map access with a default (fixed BUG-034: get() added to std:utils).
F15: std:utils is not documented in LANGUAGE_SPEC.md.
-->

---

## 12. v4.0 Standard Library (New in 4.0.0)

The following modules ship with nodus-lang 4.0.0 and are not covered in the
v3.0 sections above. For all modules, import with `import "std:<name>" as <alias>`.

> **Note:** The standard-library.md was written for v3.0. The key API shapes and non-obvious behaviors
> are documented here; the machine-readable index in `llms.txt` covers the rest.

---

### std:http

HTTP client (sync and async). Returns `http_response` records on success,
`error` records on failure — never throws.

```nd
import "std:http" as http

let resp = http.get("https://example.com/api/data")
if (type(resp) == "error") {
    print(resp.message)
} else {
    print(resp.status)      // integer status code
    print(resp.body)        // response body as string
}
```

Key functions: `http.get(url)`, `http.post(url, body)`, `http.put(url, body)`,
`http.delete(url)`, `http.patch(url, body)`. Each accepts an optional options map:
`{headers: {"Authorization": "Bearer tok"}, timeout_ms: 5000}`.

---

### std:hash

Hashing (SHA-256, SHA-512, BLAKE2b, SHA-1, MD5), HMAC, constant-time comparison.
**Important:** `hash.sha256(data)` returns a **hash record**, not a hex string.
Call `.to_hex()` on the result:

```nd
import "std:hash" as hash

let digest = hash.sha256("hello world")
// digest is a hash record — NOT a plain string
print(digest.to_hex())          // lowercase hex
print(digest.to_hex_upper())    // uppercase hex
print(digest.to_base64())       // base64
print(digest.algorithm)         // "sha256"
print(digest.length)            // 32  (bytes)
```

Other functions: `hash.sha512(data)`, `hash.blake2b(data)`, `hash.sha1(data)`,
`hash.md5(data)`, `hash.hmac_sha256(key, message)`, `hash.compare(a, b)`.

---

### std:encoding

Base64, hex, and URL encoding.

```nd
import "std:encoding" as enc

let b64 = enc.base64_encode("hello world")   // "aGVsbG8gd29ybGQ="
let raw = enc.base64_decode(b64)             // "hello world"
let hex = enc.hex_encode("AB")               // "4142"
let url = enc.url_encode("hello world")      // "hello+world"
```

---

### std:secrets

Cryptographically secure random values.

```nd
import "std:secrets" as secrets

let tok = secrets.token_hex(16)      // 32-char hex string (16 random bytes)
let b64 = secrets.token_base64(16)   // base64url random token
let n   = secrets.randbelow(100)     // secure random int [0, 100)
```

---

### std:subprocess

Process execution. No shell by default; opt in with `shell_run`.

```nd
import "std:subprocess" as sp

let result = sp.run(["echo", "hello"])
print(result.stdout)      // "hello\n"
print(result.exit_code)   // 0

// With shell (opt-in):
let r2 = sp.shell("echo hello && echo world")
print(r2.stdout)
```

Returns a record with `stdout`, `stderr`, `exit_code`. Errors (process not found,
permission denied) return an error record instead of throwing.

---

### std:env

Environment variables.

```nd
import "std:env" as env

let home = env.get("HOME")           // nil if not set
let path = env.get_or("PATH", "")    // default if not set
env.set("MY_VAR", "value")
env.delete("MY_VAR")
let all = env.list()                 // map of all env vars
```

---

### std:time

Datetime, durations, and timezones.

```nd
import "std:time" as time

let now = time.now()                  // datetime record
print(now.year)
print(now.month)
print(now.day)
print(now.hour)
print(now.unix)                       // Unix timestamp (float)

let dt = time.parse("2026-01-15", "YYYY-MM-DD")
let diff = time.diff(dt, now)         // duration in ms
```

---

### std:tool

Dynamic tool registry. AI/MCP adapter pattern. **Tool names must use dotted
namespacing** — `"myapp.tool_name"`, not `"tool_name"` — or `register` returns
an error record.

```nd
import "std:tool" as tool

let reg = tool.register({
    name: "myapp.greet",
    description: "Greet someone",
    handler: fn(args) { return "Hello " + args.name }
})
if (type(reg) == "error") {
    print(reg.message)    // e.g., "tool name must use dotted namespacing"
}

print(tool.has("myapp.greet"))          // true
let result = tool.invoke("myapp.greet", {name: "World"})
print(result)                           // "Hello World"
let all = tool.list_tools({})           // list of tool records
```

---

### std:test

Test framework. Test files must end in `_test.nd`. Run with `nodus test <path>`.

```nd
import "std:test" as test

test.suite("my feature", fn() {
    test.case("basic addition", fn() {
        test.assert_eq(1 + 1, 2)
    })
    test.case("string interpolation", fn() {
        let x = 42i
        test.assert_eq("\(x)", "42")
    })
})
```

11 assertions: `assert`, `assert_eq`, `assert_neq`, `assert_err`, `assert_ok`,
`assert_kind`, `assert_throws`, `assert_close`, `assert_contains`,
`assert_has_key`, `assert_in_range`.

CLI: `nodus test [path] [--filter pattern] [--coverage] [--bail]`.


---

### std:bool

Boolean helpers for strict equality comparisons.

```nd
import "std:bool" as b

// In v4.0, 0i == false is false (equality coercion narrowed).
// Use bool.equal() for explicit bool checks:
let is_true = b.equal(some_value, true)
let is_false = b.equal(some_value, false)
```

Also available as the top-level `bool_equal(value, bool_value)` builtin.

---

### Python-side: NodusRuntime.tool_registry

When embedding Nodus in Python, register tools via `runtime.tool_registry`:

```python
from nodus import NodusRuntime

runtime = NodusRuntime()
runtime.tool_registry.register({
    "name": "myapp.greet",          # dotted namespace required
    "description": "Greet someone",
    "handler": lambda args: f"Hello, {args.get('name', 'world')}!",
})
```

`tool_registry` methods: `register({...})`, `unregister(name)`, `invoke(name, args)`,
`lookup(name)`, `list_tools(filter?)`, `has(name)`.
