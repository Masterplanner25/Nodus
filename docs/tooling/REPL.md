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
> fn add(a, b) {
...   return a + b
... }
```

The primary prompt is `> `. Continued input uses `... `.

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
:help          show commands
:quit          exit REPL
```

Examples:

```text
> :ast 1 + 2 * 3
Binary(+)
  Number(1)
  Binary(*)
    Number(2)
    Number(3)
```

```text
> :dis 1 + 2
PUSH_CONST 1.0
PUSH_CONST 2.0
ADD
RETURN
```

```text
> :type [1, 2, 3]
List<number>
```
