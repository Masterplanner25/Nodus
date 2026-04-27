# Nodus

Nodus is a scripting language runtime with a small CLI for running files, starting projects, and using an interactive REPL.

## Install

```bash
pip install nodus-lang
```

For the optional FastAPI/Uvicorn HTTP server path:

```bash
pip install "nodus-lang[server]"
```

Plain `pip install nodus-lang` still works for the CLI, REPL, project commands,
and `nodus serve`. Without the `server` extra, `nodus serve` uses the built-in
fallback HTTP server instead of the FastAPI/Uvicorn path.

## Canonical User Flow

Start a new project:

```bash
nodus init
nodus run
nodus repl
```

`nodus init` creates a new Nodus project in your current directory.

`nodus run` runs the project entry file created by `nodus init`.

`nodus repl` starts an interactive prompt.

## Example 1: Standalone File

Create `hello.nd`:

```nd
print("hello")
```

Run it:

```bash
nodus run hello.nd
```

## Example 2: Project Flow

Create a directory for your project and move into it:

```bash
mkdir my-app
cd my-app
```

Initialize the project:

```bash
nodus init
```

Run the project:

```bash
nodus run
```

## REPL

Start the REPL:

```bash
nodus repl
```

The REPL lets you run code interactively, one line or block at a time.

Useful commands inside the REPL:

- `:help` shows REPL commands.
- `exit`, `quit`, or `:quit` leaves the REPL.

## Common Commands

- `nodus run hello.nd` runs a file.
- `nodus run` runs the current project.
- `nodus repl` starts the interactive REPL.
- `nodus check hello.nd` validates a file without running it.
- `nodus check` validates the current project's default entry file when run from a project directory.
- `nodus fmt hello.nd` formats a file.

## Getting Started

See [docs/onboarding/GETTING_STARTED.md](/abs/path/C:/dev/Coding%20Language/docs/onboarding/GETTING_STARTED.md) for the same first-time setup in a step-by-step form.
