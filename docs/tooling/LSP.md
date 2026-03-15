# Nodus Language Server

Nodus includes a minimal Language Server Protocol implementation for editor integration in the `0.7.0` developer-tooling milestone.

## Capabilities

The current server supports:

- `initialize`
- `shutdown`
- `exit`
- `textDocument/didOpen`
- `textDocument/didChange`
- `textDocument/completion`
- `textDocument/hover`
- `textDocument/definition`

Diagnostics are produced from the existing parser and compiler pipeline, so syntax and compile failures keep the same line and column information used by the CLI.

Completions currently include:

- Nodus keywords
- local variables
- function names
- imported module aliases and imported symbols

Hover currently shows:

- variable types when they can be inferred from annotations or simple expressions
- function signatures
- module names for import aliases

Definition lookup currently supports:

- local variables and function names
- imported symbols
- module members accessed through import aliases

## Starting The Server

Run the server over stdio:

```bash
nodus lsp
```

The server speaks standard JSON-RPC with `Content-Length` framing on stdin/stdout.

## VS Code Example

You can wire the server into VS Code with a local language client extension or a generic LSP client. A minimal `settings.json` example for clients that support direct stdio configuration looks like this:

```json
{
  "nodus.languageServer.command": "nodus",
  "nodus.languageServer.args": ["lsp"]
}
```

If you are using `tasks.json` or a custom client launcher, the equivalent command is:

```json
{
  "command": "nodus",
  "args": ["lsp"]
}
```

## Design Notes

- The implementation reuses the existing lexer, parser, compiler, import resolver, and lightweight type analysis helpers.
- The server keeps open documents in memory and reparses on each `didOpen` and `didChange`.
- Text synchronization is currently full-document sync.

## Current Limitations

- Diagnostics are document-focused and may reference imported files in the error message rather than publishing to those files directly.
- Scope analysis is intentionally lightweight, so some completion and definition cases in deeply nested code may be approximate.
- Hover type information is best-effort and does not attempt full semantic inference across module boundaries.
