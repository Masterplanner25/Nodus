# Editor Support

Nodus ships a small TextMate grammar and VS Code language configuration so `.nd` files get baseline syntax highlighting and file association.

## VS Code

Files live under `tools/vscode/`:
- `tools/vscode/package.json`
- `tools/vscode/language-configuration.json`
- `tools/vscode/syntaxes/nodus.tmLanguage.json`
- `tools/vscode/snippets/nodus.json`

To use locally:
1. Open the `tools/vscode/` folder in VS Code.
2. Use the command palette: `Developer: Install Extension from Location...` and select `tools/vscode/`.
3. Open any `.nd` file and confirm the language mode is `Nodus`.

## Highlighting Coverage

The grammar highlights:
- Keywords: `let`, `fn`, `return`, `if`, `else`, `while`, `for`, `import`, `export`, `from`, `as`
- Literals: `true`, `false`, `nil`
- Numbers: integers and floats
- Strings: double-quoted with escape sequences
- Comments: `#` and `//` line comments
- Operators and punctuation
- Member access like `mod.name`

Sample file:
- `examples/editor_support.nd` includes imports/exports, control flow, lists/maps, strings, and comments for quick validation.

## Snippets

VS Code snippets include common constructs for:
- imports (plain, alias, named)
- functions (plain/export)
- loops (`for`, `while`) and `if/else`

## Language Configuration

The VS Code configuration sets:
- line comment: `//`
- brackets: `{}`, `[]`, `()`
- auto-closing pairs: braces, brackets, parentheses, double quotes

## Language Server

For diagnostics, completion, hover, and go-to-definition support, use the Nodus LSP server:

- Start it with `nodus lsp`
- Documentation: `docs/tooling/LSP.md`

The current implementation uses stdio JSON-RPC and reuses the existing parser/compiler pipeline for diagnostics.

## Limitations

- VS Code only supports a single line-comment token in language configuration, so `//` is used there. The grammar still highlights `#` comments.
- The grammar is intentionally simple and does not attempt full parsing or semantic highlighting.

## Future Ideas

- Distribute as a standalone VS Code extension.
- Add snippets for common constructs (imports, functions, loops).
- Expand the LSP with richer semantic analysis and editor-specific packaging.
