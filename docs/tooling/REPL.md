# Nodus REPL

The Nodus REPL is an interactive shell for quick experiments, bytecode inspection, and small development loops.

Start it with:

```bash
nodus repl
```

## Multiline Editing

The REPL keeps reading when `{` and `}` braces are unbalanced.

Example:

```text
nodus> fn add(a, b) {
...     return a + b
... }
```

The primary prompt is `nodus> `. Inside a project — a directory containing
`nodus.toml` — it includes the project name: `nodus (myproject)> `. Continued
input uses `... `.

The REPL prints a banner on start:

```text
4.1.1 REPL (type 'exit', 'quit', or ':quit' to quit)
```

That version comes from the **installed** distribution (`importlib.metadata`),
while `nodus --version` reports the version of the **source** being executed.
They agree for a normal `pip install`; they diverge only in a development
checkout that shadows an older installed package via `PYTHONPATH`.

## Command History

When Python `readline` is available, the REPL loads persistent history from:

```text
~/.nodus_history
```

Behavior:

- history loads at startup
- history saves on exit
- arrow keys navigate command history

## Inspection Commands

REPL commands start with `:` and are handled by the shell instead of the VM.

```text
:ast <expr>    show AST
:dis <expr>    show bytecode
:type <expr>   show inferred type
:modules       list imported modules
:reload        restart REPL session
:help          show commands
:quit          exit REPL
```

Examples:

```text
nodus> :ast 1 + 2 * 3
Binary(+)
  Number(1)
  Binary(*)
    Number(2)
    Number(3)
```

```text
nodus> :dis 1 + 2
PUSH_CONST 1.0
PUSH_CONST 2.0
ADD
RETURN
```

```text
nodus> :type [1, 2, 3]
List<number>
```
