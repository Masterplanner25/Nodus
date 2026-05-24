# Modules and Imports

A Nodus module is any `.nd` file. The import system lets you split a project
across files, share helpers, and use the standard library. For the formal
grammar see [LANGUAGE_SPEC.md — Imports](../language/LANGUAGE_SPEC.md#imports).

---

## 1. Your first multi-file project

Project layout:

```
myproject/
├── greet.nd
└── main.nd
```

**`greet.nd`:**

```nd
export fn hello(name) {
    return "Hello, " + name + "!"
}
```

**`main.nd`:**

```nd
import "./greet" as g

print(g.hello("Nodus"))
print(g.hello("world"))
```

```bash
nodus run main.nd
```

Output:

```
Hello, Nodus!
Hello, world!
```

- `export fn` makes a function visible to importers. Without `export`, a
  function is private to its module.
- `import "./greet" as g` — `./` means relative to the current file; `.nd`
  extension is optional.
- `g.hello(...)` — all access goes through the alias you gave the module.

---

## 2. Import syntax

### Namespace import (the standard form)

```nd
import "./path/to/module" as alias
```

The `as alias` clause is required for access. An import without `as` loads
the module (running any top-level code) but does not bind any name — you
cannot access it afterward.

### Named imports

Pull specific names directly into scope:

```nd
import { add, PI } from "./math"

print(add(3, 4))    // 7.0
print(PI)           // 3.14159
```

### Stdlib imports

```nd
import "std:strings" as strings
import "std:json" as json
import "std:fs" as fs
```

The `std:` prefix routes to built-in modules. No path or extension.
See [standard-library.md](standard-library.md) for every available module.

---

## 3. Exports

### `export fn` and `export let`

```nd
// config.nd
export let ENV = "production"
export let MAX_RETRIES = 3

let _secret = "internal"          // private — not accessible from outside

export fn get_url() { return "https://api.example.com" }
```

```nd
// main.nd
import "./config" as cfg
print(cfg.ENV)           // production
print(cfg.MAX_RETRIES)   // 3.0
print(cfg.get_url())     // https://api.example.com
```

Output:

```
production
3.0
https://api.example.com
```

Accessing a private name raises a key error:

```
Key error at main.nd:5:7: Missing module export: _secret
```

### Privacy model

If a module uses **any** `export` declaration, **only** explicitly exported
names are visible. If a module uses **no** `export` declarations, all
top-level names are visible (legacy compatibility). For new code, always
export explicitly.

### Re-exports

```nd
// facade.nd
export { greet, VERSION } from "./base"
```

Re-exported names must already be exported by the source module.

---

## 4. Path resolution

| Path form | Resolves to |
|-----------|-------------|
| `"./sibling"` | Same directory as the importing file |
| `"./subdir/file"` | Nested subdirectory |
| `"./utils"` | `./utils.nd`, then `./utils/index.nd` |
| `"./helpers.nd"` | Explicit `.nd` extension — also works |
| `"std:strings"` | Built-in standard library |
| `"helpers"` | (bare) project root, then packages, then stdlib |

**Directory (index) modules** — importing a directory path loads `index.nd`
inside it:

```
myproject/
├── main.nd
└── utils/
    └── index.nd
```

```nd
import "./utils" as utils    // loads ./utils/index.nd
```

**`../` (parent directory)** — only usable when a `nodus.toml` manifest
defines the project root. Without a manifest, the project root is the entry
file's directory, so `../` escapes it:

```
Import error: Invalid import: path '../shared' escapes the project root.
```

**When a path doesn't resolve**, the error lists every path tried:

```
Import error: Import not found: './no_such_file'
  (tried ./no_such_file.nd, ./no_such_file.tl,
         ./no_such_file/index.nd, ./no_such_file/index.tl, ...)
```

---

## 5. Project structure patterns

### Flat — small projects

All files at one level. Simplest to maintain:

```
project/
├── main.nd
├── utils.nd
└── config.nd
```

### Lib — medium projects

```
project/
├── main.nd
└── lib/
    ├── utils.nd
    └── config.nd
```

### Shared config across files

A config module imported by both entry point and helpers. Modules are cached —
even when imported by multiple files, `config.nd` runs only once:

```
project/
├── main.nd
├── config.nd
└── utils.nd
```

**`config.nd`:**

```nd
export let ENV = "production"
export let MAX_ITEMS = 100
```

**`utils.nd`:**

```nd
import "./config" as cfg

export fn clamp(n) {
    if (n > cfg.MAX_ITEMS) { return cfg.MAX_ITEMS }
    return n
}
```

**`main.nd`:**

```nd
import "./config" as cfg
import "./utils" as utils

print(cfg.ENV)                        // production
print(utils.clamp(150))               // 100.0
```

Output:

```
production
100.0
```

---

## 6. Constraints

> These are the import rules that produce non-obvious errors. Read them before
> writing your first multi-file project.

### Imports must be literal top-level statements

An import must appear at the top level of a file, not inside any block —
not a function, not a `try/catch`, not an `if/else`.

**Function body** — fails at call time with a misleading "Undefined variable"
error ([BUG-031, #32](https://github.com/Masterplanner25/Nodus/issues/32)):

```nd
// WRONG — import inside a function
fn do_work() {
    import "./helpers" as h
    return h.ping()
}
print(do_work())
```

Output:

```
Name error at main.nd:3:12: Undefined variable: h
```

The fix: move the import to the top of the file.

**`if`/`else` block** — same failure, even at the file's top level:

```nd
// WRONG — import inside an if block
if (flag) {
    import "./helpers" as h
    print(h.ping())    // Name error: Undefined variable: h
}
```

### Imports inside `try/catch` are silently swallowed

([BUG-042, #43](https://github.com/Masterplanner25/Nodus/issues/43)) — the
import failure is not raised to the `catch` block. The alias is simply left
undefined, and accessing it later raises a `"name"` error:

```nd
try {
    import "./helpers" as h
    print(h.ping())
} catch err {
    print(err.kind)       // name
    print(err.message)    // Undefined variable: h
}
```

Output:

```
name
Undefined variable: h
```

There is no way to detect a failed import from inside a script. See
[error-handling.md §6](error-handling.md#6-what-is-not-catchable).

### Cyclic imports are an error

Modules are fully loaded before main runs. A → B → A is detected immediately:

```
Import error: Circular import detected:
  a.nd -> b.nd -> a.nd
```

Break cycles by extracting shared code into a third module that both import.

---

## 7. Working with the standard library

Some functions need no import — `print`, `len`, `str`, `type`, `has_key`,
`keys`, `values`, and others are built-in. See
[standard-library.md §1](standard-library.md#1-built-in-functions).

Everything else needs an explicit import:

```nd
import "std:strings" as strings
import "std:json" as json
import "std:fs" as fs
import "std:math" as math
import "std:collections" as col
```

Convention: use the module name as the alias (`strings`, `json`, `fs`).

---

## 8. What's not supported

**No dynamic imports.** Import paths must be string literals — you cannot
compute a path at runtime and load it. The module graph is fully resolved at
startup.

**No conditional imports.** Imports in `if` blocks and `try/catch` do not
work (see Section 6). All imports are unconditional.

**No safe-import wrapping.** There is no way to check whether a module exists
before importing it. If a module is missing, the program fails to start.

**No renaming individual exports.** `import { add as plus } from "./math"` is
not supported. Use a namespace import instead:

```nd
import "./math" as m
let plus = m.add
```

---

## 9. See also

- [getting-started.md §5](getting-started.md#5-a-two-file-project) — the
  simpler two-file intro this file builds on
- [standard-library.md](standard-library.md) — every stdlib module and function
- [error-handling.md §6](error-handling.md#6-what-is-not-catchable) — import
  errors and why try/catch wrapping doesn't work
- [LANGUAGE_SPEC.md — Imports](../language/LANGUAGE_SPEC.md#imports) —
  formal grammar, resolution algorithm, re-export syntax

---

<!--
TESTED EXAMPLE PROJECTS (13 total in /tmp/imports-tests/)
01-basic/            — relative import + alias: "Hello, world!" confirmed
02-alias/main2.nd    — same module two aliases: both work (module cached, one execution)
02-alias/main.nd     — import without 'as': module loads but no name bound; "Undefined variable: helpers"
03-stdlib/           — std:strings: trim, upper confirmed
04-exports/          — named imports: { add, PI } from "./lib" → 7.0, 3.14159
05-transitive/       — A→B→C: b.doubled() = "from c + from c"
06-path-ext/         — explicit .nd extension: works same as without
07-dir-index/        — directory index: import "./utils" → ./utils/index.nd confirmed
08-bare/             — bare import: resolves at project root (file's dir without manifest)
09-in-function/      — import in function: "Name error: Undefined variable: h" at call time
10-in-try/           — import in try: err.kind="name", err.message="Undefined variable: h"
11-in-if/            — import in if block: same "Undefined variable: h" behavior as in function
12-no-export/        — no-export module: all top-level names visible (x=42.0, fn accessible)
13-export-let/       — export let + privacy: _internal raises "Missing module export: _internal"
14-reexport/         — re-export from "./base": both greet and VERSION accessible through facade
15-cycle/            — cyclic: "Circular import detected: a.nd -> b.nd -> a.nd"
17-threefiles/       — 3-file project with shared config dep: output confirmed

VERBATIM ERROR MESSAGES:
- "Name error at main.nd:3:12: Undefined variable: h" (import in function)
- "Name error at main.nd:4:11: Undefined variable: h" (import in if block)
- err.kind="name", err.message="Undefined variable: h" (import in try/catch)
- "Import error: Circular import detected: a.nd -> b.nd -> a.nd"
- "Import error: Import not found: './no_such_file' (tried ./no_such_file.nd, ...)"
- "Import error: Invalid import: path '../shared' escapes the project root."
- "Key error at main.nd:6:7: Missing module export: _internal"

BEHAVIORAL FINDINGS (to file as v2.2 issues):
F26: import inside an if/else block at top level silently fails — binding never created.
     Same behavior as in functions and try/catch. LANGUAGE_SPEC says "top-level" but
     doesn't explicitly exclude if/else blocks. Error is "Undefined variable" with no
     hint about the import placement.

F27: --trace-imports produces no output when bytecode is cached. _import_trace_fn is only
     called in ModuleLoader.resolve_import(), but _build_metadata() skips resolve_import()
     on cache hits (uses _build_metadata_from_cached_bytecode instead). Practical effect:
     flag only works on first run after cache is cold.

F28: import "./path" without 'as' clause: module executes (side effects run) but no name
     is bound. Silently succeeds with no name. Undocumented in LANGUAGE_SPEC.
-->
