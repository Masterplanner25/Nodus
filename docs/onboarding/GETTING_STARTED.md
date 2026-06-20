# Getting Started with Nodus

This guide is for first-time users who installed Nodus with `pip`.

## Install

```bash
pip install nodus-lang
```

If you plan to use the optional FastAPI/Uvicorn server stack for `nodus serve`,
install:

```bash
pip install "nodus-lang[server]"
```

With plain `pip install nodus-lang`, the normal CLI still works and `nodus serve`
falls back to the built-in HTTP server implementation.

## First Project

Create a new folder and move into it:

```bash
mkdir my-app
cd my-app
```

Initialize a Nodus project:

```bash
nodus init
```

Run the project:

```bash
nodus run
```

This runs the default project file created by `nodus init`.

## Standalone File

Create `hello.nd`:

```nd
print("hello")
```

Run it:

```bash
nodus run hello.nd
```

## REPL

Start the REPL:

```bash
nodus repl
```

The REPL is for interactive execution. You can type code directly and run it immediately.

Inside the REPL:

- `:help` shows available REPL commands.
- `exit`, `quit`, or `:quit` closes the REPL.

## Minimal Flow

```bash
pip install nodus-lang
nodus init
nodus run
nodus repl
```

## Useful Commands

- `nodus run hello.nd` runs a single file.
- `nodus run` runs the current project.
- `nodus repl` starts the interactive prompt.
- `nodus check hello.nd` checks a file without running it.
- `nodus check` checks the current project's `src/main.nd` when run inside a project directory.
- `nodus fmt hello.nd` formats a file.

## AI Assistant Setup

If you want assistant-specific project context for Nodus:

- For **Claude Code**, copy `skills/project-CLAUDE.md` to your project root as `CLAUDE.md`, then place `skills/nodus.skill` in `.claude/commands/`.
- For **Codex**, copy `skills/project-AGENTS.md` to your project root as `AGENTS.md`, then copy `skills/nodus/` to `$CODEX_HOME/skills/nodus` or `~/.codex/skills/nodus`.

Execution rule:

- `nodus run <file>` runs only the file you provide.
- `nodus run` with no file runs only `src/main.nd` when `nodus.toml` is present.

## Next Steps

- [Nodus Overview](NODUS.md) — project orientation, architecture, capabilities, and ecosystem
- [Getting Started Guide](../guide/getting-started.md) — deeper syntax walkthrough, REPL, debugging, and navigation to all topics
- [AI Primitives](../guide/ai-primitives.md) — std:tool (MCP-compatible tool registry), std:identity, std:effects, std:memory, std:retry, std:circuit_breaker
- [Ecosystem](../guide/ecosystem.md) — the 35 companion packages and nodus-sdk
- [Language Specification](../language/LANGUAGE_SPEC.md) — full syntax, types, operators, builtins, and stdlib modules
- Interactive reference: start the REPL and type `:help` to explore available commands
