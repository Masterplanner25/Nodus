# Getting Started with Nodus

This guide takes you from zero to a working two-file project. It covers
install, first script, basic syntax, the REPL, and what to do when things
break. Reading time: ~30 minutes.

---

## 1. Install

Nodus requires **Python 3.10 or later**.

```bash
pip install nodus-lang
nodus --version
```

Expected output: `Nodus 4.0.6`.

For the optional FastAPI/Uvicorn HTTP server:

```bash
pip install "nodus-lang[server]"
```

---

## 2. Your First Script

Create `hello.nd`:

```nd
print("Hello, Nodus!")
```

Run it:

```bash
nodus run hello.nd
```

Output:

```
Hello, Nodus!
```

`nodus run` only shows output from explicit `print()` calls. If you write
`let x = 1 + 2` and run the file, you see nothing — the result isn't
automatically displayed. Everything you want to see must go through `print`.

---

## 3. A Bit of Syntax

### Variables

```nd
let name = "Nodus"
let version = 2
let active = true
print(name)
print(version)
```

Output:

```
Nodus
2.0
```

Plain numeric literals like `2` are floats. `2` stores and prints as `2.0`. See
[types-and-values.md — Numbers are floats](types-and-values.md#numbers-are-floats)
for what this means in practice.

> **v4.0 note:** Nodus also has an integer type. Write `2i` (with the `i` suffix)
> to get an exact integer. `type(2)` returns `"float"`; `type(2i)` returns `"int"`.
> String interpolation lets you embed values inline: `"\(name) \(count)"` — no
> multi-argument `print()` needed.

### Functions

```nd
fn greet(name) {
    return "Hello, " + name + "!"
}

print(greet("Nodus"))
```

Output:

```
Hello, Nodus!
```

Functions are declared with `fn`. The return value of the last expression
is not implicitly returned — use `return` explicitly.

### Conditionals

`if` requires parentheses around the condition:

```nd
let score = 72

if (score >= 90) {
    print("A")
} else {
    if (score >= 70) {
        print("B")
    } else {
        print("C")
    }
}
```

Output:

```
B
```

Nodus supports `else if` directly (added in v3.0). The nested-`if`-in-`else` form shown above also works and is equivalent.

### Loops

`while` also requires parentheses. `for item in list` does not.

```nd
// for-in: no parens needed
let fruits = ["apple", "banana", "cherry"]
for fruit in fruits {
    print(fruit)
}
```

Output:

```
apple
banana
cherry
```

```nd
// while: parens required
let i = 1
while (i <= 3) {
    print(i)
    i = i + 1
}
```

Output:

```
1.0
2.0
3.0
```

For a complete list of every operator and control flow form, see
[LANGUAGE_SPEC.md](../language/LANGUAGE_SPEC.md).

---

## 4. The REPL

```bash
nodus repl
```

The REPL is useful for quick experiments. It keeps reading when `{` and `}`
are unbalanced, so you can define multi-line functions interactively.

A typical session:

```
> print("hello")
hello
> let x = 6 * 7
> print(x)
42.0
> fn double(n) {
...   return n * 2
... }
> print(double(21))
42.0
> :type [1, 2, 3]
List<number>
> :dis 1 + 2
PUSH_CONST 1.0
PUSH_CONST 2.0
ADD
RETURN
> :help
```

REPL commands (all start with `:`):

| Command | What it does |
|---------|-------------|
| `:help` | Show all commands |
| `:ast <expr>` | Print the AST for an expression |
| `:dis <expr>` | Show bytecode for an expression |
| `:type <expr>` | Show the inferred type |
| `:modules` | List all modules imported in this session |
| `:reload` | Restart the session (clears all state) |
| `:quit` | Exit the REPL |

`exit` and `quit` (without the colon) also exit the REPL.

Full REPL documentation: [docs/tooling/REPL.md](../tooling/REPL.md).

---

## 5. A Two-File Project

The module system is one of Nodus's main features. Here's a non-trivial
two-file example that shows exports, imports, and stdlib use.

Project layout:

```
myproject/
├── math_utils.nd
└── main.nd
```

**`math_utils.nd`** — defines and exports two helper functions:

```nd
import "std:collections" as col

export fn average(numbers) {
    let total = col.reduce(numbers, fn(acc, x) { return acc + x }, 0)
    return total / len(numbers)
}

export fn max_of(numbers) {
    let best = numbers[0]
    for n in numbers {
        if (n > best) {
            best = n
        }
    }
    return best
}
```

**`main.nd`** — imports and uses them:

```nd
import "./math_utils" as mu

let scores = [85, 92, 78, 96, 88]
print("Scores: " + str(scores))
print("Average: " + str(mu.average(scores)))
print("Best: " + str(mu.max_of(scores)))
```

Run from inside `myproject/`:

```bash
nodus run main.nd
```

Output:

```
Scores: [85.0, 92.0, 78.0, 96.0, 88.0]
Average: 87.8
Best: 96.0
```

Key things this example demonstrates:

- **`export fn`** makes a function visible to importers. Functions without
  `export` are private to the module.
- **`import "./math_utils" as mu`** — the `./` prefix means relative to the
  current file. The `.nd` extension is optional.
- **`import "std:collections" as col`** — the `std:` prefix loads a stdlib
  module. Imports must be at the top level of a file, not inside functions.
- `str(list)` converts a list to its string representation for printing.

For a full treatment of module resolution, exports, and bare paths, see
[modules-and-imports.md](modules-and-imports.md).

---

## 6. When Things Go Wrong

Nodus errors tell you the error kind, the file, the line, and the column.

This script has a deliberate bug — `y` is never defined:

```nd
let x = 10
print(y)
```

Output:

```
Name error at error_demo.nd:2:7: Undefined variable: y
Stack trace:
  at <main> (error_demo.nd:2:7)
```

The format is `<Kind> error at <file>:<line>:<col>: <message>`. Line 2,
column 7 is exactly where `y` appears. The stack trace shows the call chain
that led there.

**`nodus check` is parse-only.** It validates syntax and catches malformed
code, but it does NOT detect undefined variables or type mismatches. This
means `nodus check error_demo.nd` reports `OK` even though `y` is
undefined — the error only surfaces at runtime when `nodus run` hits that
line.

```bash
nodus check error_demo.nd
# → OK    (parse succeeds; y is not checked)

nodus run error_demo.nd
# → Name error at error_demo.nd:2:7: Undefined variable: y
```

For structured error handling inside your scripts (try/catch/finally), see
[error-handling.md](error-handling.md).

---

## 7. Where to Go Next

Start with the foundation guides, then pick the topic you need:

**Foundation**

- **[types-and-values.md](types-and-values.md)** — records vs maps,
  float-only numbers, nil semantics, functions as values. Read this first.
- **[error-handling.md](error-handling.md)** — try/catch/finally, err.kind
  reference, throw patterns, finally guarantees.
- **[modules-and-imports.md](modules-and-imports.md)** — project layout,
  relative vs bare imports, exports, index modules, how resolution works.

**Standard library and data**

- **[standard-library.md](standard-library.md)** — complete function
  reference for every `std:` module.
- **[working-with-maps.md](working-with-maps.md)** — map creation, bracket
  access, has_key, keys/values, accumulation patterns, map vs record.
- **[working-with-json.md](working-with-json.md)** — json.parse (returns
  maps since v2.1.0), stringify, traversal, working with nested structures.

**AI-native and agentic patterns**

- **[ai-primitives.md](ai-primitives.md)** — std:tool (MCP-compatible tool
  registry), std:identity (trace IDs), std:effects (EXACTLY_ONCE
  idempotency), std:memory, std:retry, std:circuit_breaker.

**Tooling and integration**

- **[debugging.md](debugging.md)** — --trace and filter flags,
  --dump-bytecode, nodus check limitations, the interactive debugger,
  common diagnostic patterns.
- **[embedding-nodus.md](embedding-nodus.md)** — NodusRuntime API,
  allowed_paths sandbox, register_function, on_error hook, shutdown,
  async concurrency, type marshaling.

**Orchestration**

- **[workflows-and-tasks.md](workflows-and-tasks.md)** — workflow/goal DSL,
  step dependencies, state, checkpoints, retries, print visibility.
- **[real-world-integration.md](real-world-integration.md)** — embedding +
  workflows together in a production-shaped app: WAIT/RESUME approval gates,
  host-side event routing, dynamic `.nd` generation, sweep loop, SEC-001/SCHED-001.

**Ecosystem and packages**

- **[ecosystem.md](ecosystem.md)** - the 35 companion packages, what each
  does, install tiers, and the nodus-sdk unified entry point.
- **[library-entry-points.md](library-entry-points.md)** - how third-party
  Nodus libraries expose `.nd` files via the `nodus.nd` entry-point group.

**Language reference**

- **[LANGUAGE_SPEC.md](../language/LANGUAGE_SPEC.md)** — the authoritative
  reference for every operator, form, and builtin.

---

## AI Assistant Setup

If you use an AI coding assistant with Nodus, install the project-level context file plus the matching assistant skill:

- **Claude Code**
  Copy [`skills/project-CLAUDE.md`](../../skills/project-CLAUDE.md) to your project root as `CLAUDE.md`, then place [`skills/nodus.skill`](../../skills/nodus.skill) in `.claude/commands/`.
- **Codex**
  Copy [`skills/project-AGENTS.md`](../../skills/project-AGENTS.md) to your project root as `AGENTS.md`, then copy the [`skills/nodus/`](../../skills/nodus/) folder to `$CODEX_HOME/skills/nodus` or `~/.codex/skills/nodus`.

These assistant assets capture the Nodus-specific rules that general-purpose models commonly miss:

- record vs map access
- closure mutation through maps instead of outer `let`
- `spawn()` plus `coroutine()` plus `run_loop()`
- workflow result bracket notation
- top-level import requirements
- NodusRuntime defaults: no timeout by default; allowed_paths jailed to CWD

---

<!--
TESTED EXAMPLES (10 total — matches code block count)
1. hello.nd — print("Hello, Nodus!") → "Hello, Nodus!"
2. variables — let name/version/active, print → "Nodus\n2.0\n"
3. fn greet — return "Hello, " + name → "Hello, Nodus!"
4. if/else nested — score=72 → "B"
5. for-in — fruits → "apple\nbanana\ncherry\n"
6. while — i=1..3 → "1.0\n2.0\n3.0\n"
7. REPL session — representative commands, not mechanically tested
8. math_utils.nd + main.nd — scores → "Average: 87.8\nBest: 96.0"
9. error_demo.nd — nodus run → "Name error at ...2:7: Undefined variable: y"
10. nodus check error_demo.nd → "OK" (confirms parse-only)

BEHAVIORAL FINDINGS (historical — tested against v2.1.1; resolved in v3.0)
F1: 'else if' was not valid syntax in v2.x. RESOLVED in v3.0: `else if` is
    now supported directly.
F2: In v2.x, `{ name: "Alice" }` tried to evaluate `name` as a variable and
    failed. CHANGED in v3.0: `{ name: "Alice" }` with a bare identifier is
    now a record literal. For maps, quote the key: `{ "name": "Alice" }`.
F3: Imports inside function bodies silently failed in v2.x. RESOLVED in v3.0
    (BUG-031 fix): import errors in function bodies now propagate correctly.
-->

