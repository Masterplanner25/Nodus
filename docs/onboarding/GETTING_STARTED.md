# Getting Started with Nodus

Nodus is a small practical scripting language implemented in Python. This guide takes you from running the first example to a tiny multi-file project.

## Prerequisites

- Python 3.10+ on your `PATH`

## First Run

Run the single-file example:

```bash
nodus run examples/hello.nd
```

Use the REPL:

```bash
python -m nodus.tooling.repl
```

Inside the REPL:

- use multiline input for brace-delimited blocks
- use `:help` to list shell commands
- use `:ast <expr>`, `:dis <expr>`, and `:type <expr>` for inspection
- history is stored in `~/.nodus_history` when Python `readline` is available

## Format and Check

Format a file:

```bash
nodus fmt script.nd
```

Check formatting without rewriting:

```bash
nodus fmt script.nd --check
```

Validate syntax, imports, and compilation without executing:

```bash
nodus check script.nd
```

Notes:
- `nodus fmt` is deterministic and idempotent.
- Integer-looking literals stay integer-looking; float literals keep their decimal form.
- Trailing comments are preserved, but by default they move to their own following line. Use `--keep-trailing` to keep them inline when possible.

## Small Project Layout

A simple Nodus project usually has:

- one entry file such as `main.nd`
- local modules next to it or in subfolders
- `index.nd` when a folder should behave like a package entrypoint

Example layout:

```
project_layout_demo/
  main.nd
  math.nd
  utils/
    index.nd
```

This repository includes that exact example in `examples/project_layout_demo/`.

Run it:

```bash
nodus run examples/project_layout_demo/main.nd
```

Check it:

```bash
nodus check examples/project_layout_demo/main.nd
```

## How the Example Is Organized

`main.nd` imports from a sibling module and a package folder:

```nd
import { sum_list, square } from "./math.nd"
import { format_result } from "./utils"
import { join } from "std:strings"
```

`math.nd` exports reusable functions:

```nd
export fn square(x) {
    return x * x
}
```

`utils/index.nd` acts as the package entrypoint and can use the standard library:

```nd
import { repeat } from "std:strings"

export fn format_result(label, value) {
    return repeat("-", 2) + " " + label + ": " + str(value)
}
```

Notes:
- Relative imports start with `./` or `../`.
- Importing `./utils` resolves to `./utils/index.nd` when there is no `utils.nd`.
- Non-relative imports resolve from the project root.

## Suggested Workflow

1. Edit your `.nd` files.
2. Run `nodus fmt script.nd`.
3. Run `nodus check script.nd`.
4. Run `nodus run script.nd`.

## Contributing and Development

### Running the test suite

```bash
python -m pytest tests/ -v
```

Or with the standard unittest runner:

```bash
python -m unittest discover -s tests -v
```

### Formatting examples before pushing

CI auto-formats `examples/*.nd` and commits back if anything changed. To avoid
that automated commit, run the formatter locally before you push:

```bash
find examples/ -name "*.nd" | sort | while read -r f; do
  python nodus.py fmt "$f"
done
```

Check without rewriting:

```bash
find examples/ -name "*.nd" | xargs -I {} python nodus.py fmt --check {}
```

### Adding a builtin function

Builtin functions are organised by category under `src/nodus/builtins/`:

| File | Category |
|------|----------|
| `io.py` | print, input, filesystem, path |
| `math.py` | numeric / math |
| `coroutine.py` | coroutine, channel, scheduler |
| `collections.py` | list, map, string, JSON |

To add a new builtin:

1. Implement it in the appropriate category module (or create a new one).
2. Call `registry.add(name, arity, fn)` inside that module's `register(vm, registry)` function.
3. Add the name to `BUILTIN_NAMES` in `src/nodus/builtins/nodus_builtins.py`.

The registry is wired into `VM.__init__` automatically — no changes to `vm.py` are needed.

## More Docs

- `TASK_GRAPHS.md`
- `WORKFLOWS.md`
- `RUNTIME_EVENTS.md`
- `DEBUGGING.md`
- `REPL.md`
- `PACKAGE_MANAGER.md`
- `SERVER_MODE.md`
- `TESTING.md`
