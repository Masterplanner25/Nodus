# Nodus Language Server

Nodus includes a Language Server Protocol implementation for editor integration in the `0.7.0` developer-tooling milestone.

## Capabilities

The server supports:

- `initialize`
- `shutdown`
- `exit`
- `textDocument/didOpen`
- `textDocument/didChange`
- `textDocument/completion`
- `textDocument/hover`
- `textDocument/definition`

Diagnostics are produced from the existing parser, compiler, and tooling analysis pipeline, so editor errors stay aligned with the runtime/tooling architecture instead of duplicating compiler logic inside the LSP server.

## Diagnostics

Diagnostics are published with `textDocument/publishDiagnostics`.

Each diagnostic includes:

- `message`
- `severity`
- `source`
- `file`
- `line`
- `column`
- optional `relatedInformation`

### Diagnostic Categories

The current server publishes:

- syntax errors
- import/export resolution errors
- undefined variable errors
- undefined import errors
- invalid module member errors
- warnings for unused variables
- warnings for shadowed variables
- warnings for unreachable code

Warnings are editor-only diagnostics and do not change runtime execution semantics.

### Cross-Module Diagnostics

Diagnostics are dependency-aware:

- opening or editing a module analyzes that module plus imported modules reachable from it
- syntax/import failures in imported modules are published to the imported file URI directly
- dependent modules are re-analyzed when one of their dependencies changes

This keeps editor state accurate for multi-file projects without moving compilation logic into the LSP layer.

### Incremental Updates

`textDocument/didChange` uses the existing module dependency graph to limit work.

Instead of re-analyzing the whole project, the server refreshes:

- the changed module
- reverse dependents discovered from `.nodus/deps.json` / in-memory dependency graph updates
- imported modules needed to validate those affected modules

Diagnostics are cleared automatically by publishing an empty list when a previously reported issue is fixed.

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
- Workspace diagnostics are computed in tooling/runtime analysis code; the LSP server only coordinates affected modules and publishes results.
- Text synchronization is currently full-document sync.

## Current Limitations

- Incremental refresh is dependency-aware, but still re-parses each affected module rather than diffing AST nodes.
- Scope analysis is intentionally lightweight, so some completion and definition cases in deeply nested code may be approximate.
- Hover type information is best-effort and does not attempt full semantic inference across module boundaries.
