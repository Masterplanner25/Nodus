# Editor Support

Nodus ships a small TextMate grammar and VS Code language configuration so `.nd` files get baseline syntax highlighting and file association.

## VS Code

The Nodus VS Code extension (`nodus-vscode`) is published on the VS Code Marketplace
under publisher `MasterplanInfiniteWeave`. Install it by searching for "Nodus" in the
VS Code Extensions panel, or find it at the Marketplace under `MasterplanInfiniteWeave`.

The extension source lives in its own repository,
[`Masterplanner25/nodus-vscode`](https://github.com/Masterplanner25/nodus-vscode)
(local checkout: `C:\dev
odus-vscode`). To install from source:

1. Clone that repository and open it in VS Code.
2. Command palette: `Developer: Install Extension from Location...` and select the folder.
3. Open any `.nd` file and confirm the language mode is `Nodus`.

There used to be a second copy of the grammar in this repository under
`tools/vscode/`. It had drifted — neither copy was a superset of the other, and
the in-repo one was missing 17 of the language's 31 keywords — so it was removed
rather than reconciled ([#357](https://github.com/Masterplanner25/Nodus/issues/357)).
The published repository is the only grammar.

## Highlighting Coverage

The grammar highlights every keyword the language has — all 31 of them,
including the contextual `match`, `break` and `continue` — plus:

- Literals: `true`, `false`, `nil`
- Numbers: integers and floats, including the `42i` integer suffix
- Strings: double-quoted, with `\()` interpolation
- Comments: `#` and `//` line comments
- Operators, punctuation, DSL blocks, built-in functions, and type annotations

The keyword list is not maintained by hand here: `nodus.frontend.lexer.ALL_KEYWORDS`
is the source of truth, and `tests/test_keyword_coverage.py` fails when the
published grammar does not highlight every entry. That test needs both
repositories checked out, so it skips in this repository's CI and runs for
whoever publishes the extension.

> **`match`, `break` and `continue` were not highlighted in nodus-vscode v0.1.0.**
> They shipped in nodus-lang v4.1.0 and rendered as plain identifiers until
> v0.1.1 ([#357](https://github.com/Masterplanner25/Nodus/issues/357)). The code
> was always valid and ran; only the highlighting was missing.

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

The current implementation uses stdio JSON-RPC and reuses the existing parser/compiler/tooling pipeline for diagnostics.

Editor diagnostics now include:

- syntax and import/export failures
- cross-module diagnostics published to imported files
- dependency-aware incremental refresh on change
- warning diagnostics for unused variables, shadowed variables, and unreachable code

Diagnostics clear automatically after fixes when the server republishes an empty diagnostic list for the file.

## IDE Debugging

For IDE debugging support, use the Nodus debug adapter:

- Start it with `nodus dap`
- Documentation: `docs/tooling/DEBUGGING.md`

The adapter reuses the existing runtime debugger for breakpoints, stepping, stack traces, and variable inspection.

## Limitations

- VS Code only supports a single line-comment token in language configuration, so `//` is used there. The grammar still highlights `#` comments.
- The grammar is intentionally simple and does not attempt full parsing or semantic highlighting.

## Future Ideas

- Expand the LSP with richer semantic analysis and editor-specific packaging.
