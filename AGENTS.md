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

## When something fails
Before troubleshooting an unfamiliar error, a test that skips, or a gate that disagrees with
CI, search `docs/AGENT_EXPERIENCE.md` for its text. It records problems agents have already
hit in this repository, their causes and verified fixes. When you resolve a new one that
could recur, add an entry in its format: the exact symptom first, then the evidence and a
status. It is evidence, not policy. The project's rules are in `CLAUDE.md`.

## Output expectations
When finishing a task, summarize:
- files changed
- features completed
- tests added or updated
- known limitations