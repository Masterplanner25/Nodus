# AGENTS.md

## Project intent
This repository contains a small educational scripting language implemented in Python using:
- tokenizer
- parser
- AST
- bytecode compiler
- stack VM

## Coding rules
- Preserve existing behavior unless explicitly extending it.
- Prefer minimal, local changes over broad rewrites.
- Keep parser, compiler, and VM responsibilities separate.
- Add tests for each new language feature.
- Keep language behavior consistent and script-friendly.

## Style
- Favor readability over cleverness.
- Use small helper functions where they simplify the VM/compiler.
- Avoid unnecessary dependencies.

## Output expectations
When finishing a task, summarize:
- files changed
- features completed
- tests added or updated
- known limitations