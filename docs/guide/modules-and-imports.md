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

### Import placement — top level only

An `import` must be at the **top level of the file**. Anywhere else — inside a
function body, an `if`/`else` block, or a `try`/`catch` — is a **syntax error**,
caught before the program runs:

```
Syntax error at main.nd:2:5: import statements must be at the top level of a
module; move this import to the top of the file
```

**Correct:**

```nd
import "./helpers" as h

fn do_work() {
    return h.ping()
}
```

**Rejected at parse time** — all three of these fail with the message above:

```nd
fn do_work() {
    import "./helpers" as h     // syntax error
}

if (ready) {
    import "./helpers" as h     // syntax error
}

try {
    import "./helpers" as h     // syntax error
} catch err { }
```

> **Changed since v3.0.** Older versions of this guide said imports "work
> inside function bodies and `if`/`else` blocks", and described a `try`/`catch`
> import as failing later with a `"name"` error (`Undefined variable: h`).
> Neither is true now: the parser rejects all of them up front with an
> actionable message. If you have code following the old advice, it will no
> longer compile — move the import to the top of the file.

Because placement is now a parse error, there is nothing to catch: you cannot
wrap an import in `try`/`catch` to handle a missing module. Guard on the
imported value at the call site instead.

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

BEHAVIORAL FINDINGS — re-verified 2026-08-05 against 4.1.1

F26: RESOLVED. Was "import inside an if/else block silently fails — binding
     never created". Misplaced imports are now a SYNTAX ERROR caught before
     execution, with an actionable message:
       "import statements must be at the top level of a module; move this
        import to the top of the file"
     Confirmed for all three placements: function body, if/else block, and
     try/catch. This also invalidated two whole subsections of §6, which told
     readers imports "work inside function bodies and if/else blocks (fixed in
     v3.0)" and documented a try/catch import failing later with a "name"
     error. Both rewritten; error-handling.md §6 carried the same stale claim
     and was corrected to match.

F27: RESOLVED 2026-08-15 (#348). --trace-imports emitted nothing once the
     ON-DISK bytecode cache (.nodus/) was warm; it fired only on the first run
     after a cold cache. _build_metadata() returns early on a disk-cache hit,
     before the loop that calls resolve_import(), which is the only site
     emitting the trace. The early-return path now replays what the cached unit
     recorded, marked "Resolved (from bytecode cache)" so provenance is visible.
     NOT the same as #51 (closed/completed) — that was the in-memory cache
     within a single run, and that fix works: a cold run correctly prints both
     "Resolved" and "Cache hit".

F28: STILL PRESENT. import "./path" with no 'as' clause executes the module
     (side effects run) but binds no name, and reports nothing. Verified on
     4.1.1. Unfiled — arguably intentional for side-effect-only imports, but
     undocumented in LANGUAGE_SPEC either way.

Error messages re-confirmed verbatim on 4.1.1 (all now carry ABSOLUTE paths,
see #342):
- "Import error at <abs>/a.nd: Circular import detected: <abs>/a.nd ->
   <abs>/b.nd -> <abs>/a.nd"
- "Import error at <abs>/main.nd:1:1: Import not found: './no_such_file'
   (tried ...)" — the candidate list includes .nd, .tl, index.nd, index.tl,
   .nodus/modules/, the stdlib dir, and the nodus.nd entry-point
- "Key error at <abs>/main.nd:2:7: Missing module export: _internal"
-->
