# Nodus

```bash
pip install nodus-lang
nodus init
nodus run
nodus repl
```

Nodus is a scripting language runtime with a packaged CLI for project execution, standalone scripts, and interactive use.

## Install

```bash
pip install nodus-lang
```

For the optional FastAPI/Uvicorn server stack:

```bash
pip install "nodus-lang[server]"
```

## Quick Start

Create a project:

```bash
mkdir my-app
cd my-app
nodus init
nodus run
```

`nodus init` creates `nodus.toml` and `src/main.nd`.

`nodus run` executes the current project's `src/main.nd` when run inside a project root.

Start the REPL:

```bash
nodus repl
```

Useful REPL commands:

- `:help` shows REPL commands.
- `:quit` exits the REPL.

## Run A File

Create `hello.nd`:

```nd
print("hello")
```

Run it explicitly:

```bash
nodus run hello.nd
```

When you provide a file path, Nodus runs only that file. When you run `nodus run` with no file inside a project, Nodus runs only `src/main.nd`.

## Common Commands

- `nodus --version`
- `nodus run hello.nd`
- `nodus run`
- `nodus repl`
- `nodus check hello.nd`
- `nodus check`
- `nodus fmt hello.nd`

## Standard Library

Import standard library modules with the `std:` prefix:

```nd
import "std:math" as math
print(math.abs(-4))
```
