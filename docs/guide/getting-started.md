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

Expected output: `nodus 2.1.0`.

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

All numbers in Nodus are floats. `2` stores and prints as `2.0`. See
[types-and-values.md — Numbers are floats](types-and-values.md#numbers-are-floats)
for what this means in practice.

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

Nodus does not have `else if`. Use a nested `if` inside the `else` block.

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
[modules-and-imports.md](modules-and-imports.md) (coming soon).

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
[error-handling.md](error-handling.md) (coming soon).

---

## 7. Where to Go Next

These guide files are the natural next steps:

- **[types-and-values.md](types-and-values.md)** — the foundation
  everything else builds on. Covers records vs maps, float-only numbers,
  nil semantics, and functions as values. Read this before anything else.

- **[LANGUAGE_SPEC.md](../language/LANGUAGE_SPEC.md)** — the authoritative
  reference for every operator, form, and builtin. The guide explains usage;
  the spec defines behavior.

Coming soon:

- `modules-and-imports.md` — project layout, bare vs relative paths, re-exports
- `standard-library.md` — complete function reference for all `std:` modules
- `working-with-json.md` — json.parse, stringify, the v2.1.0 map behavior
- `error-handling.md` — try/catch/finally, err.kind values, throw patterns
- `working-with-maps.md` — map creation, has_key, accumulation patterns
- `debugging.md` — --trace, --strict, nodus check limitations

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

BEHAVIORAL FINDINGS (bugs or surprises discovered during testing)
F1: 'else if' is not valid syntax — parser error: "Expected '{', got 'if'".
    Must use nested 'if' inside 'else {}'. Not documented in LANGUAGE_SPEC.
    Worked around in guide by showing nested form.
F2: {} literal with unquoted identifier keys tries to evaluate identifiers
    as variable expressions, not string keys. { name: "Alice" } fails with
    "Undefined variable: name". Map literals require quoted string keys:
    { "name": "Alice" }. LANGUAGE_SPEC shows { key: value } which implies
    bare identifiers work — this is misleading. Filed for review.
F3: imports inside function bodies fail with "Undefined variable: <module>"
    at call time. Imports must be at module top level. Workaround: shown in
    math_utils.nd example with top-level import.
-->
