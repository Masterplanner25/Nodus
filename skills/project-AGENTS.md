# AGENTS.md

## Language

This project uses **Nodus v4** (`nodus-lang 4.0.5`).

Install: `pip install nodus-lang`

## Running scripts

```bash
nodus run script.nd
nodus run --time-limit 5000 script.nd
nodus check script.nd
nodus fmt script.nd
nodus repl
```

## Critical rules

- `{k: v}` is a record. Use dot access: `r.key`.
- `{"k": v}` is a map. Use bracket access: `m["key"]`.
- `json.parse()` returns a map. Never use dot access on parsed JSON.
- `+=`, `-=`, `*=`, `/=` work. `**` does not — use `math.pow()`.
- `print()` is single-argument. Use interpolation: `print("value: \(x)")`.
- Expressions cannot span newlines. Keep calls and list literals on one line.
- Bare numbers are floats. Use `i` suffix for counters, indices, loop bounds, and workflow state.
- Imports must be top-level only.
- Assigning to an outer `let` inside a closure creates a nil local shadow. Use a map for shared mutable state.
- `spawn()` takes a coroutine value, not a function literal.
- Channels are built in. Use `channel()`, `send()`, `recv()`, `close()`. Do not import `std:channel`.
- Workflow results are maps. Use `r["steps"]["name"]` and `r["state"]["name"]`.
- `checkpoint` is valid only inside step bodies.
- Step results should be JSON-serializable. Prefer maps, not records.
- Default execution deadline is 200ms wall-clock. Raise it with `nodus run --time-limit N script.nd` when needed.

## Codex skill

A Codex skill for Nodus lives at `skills/nodus/` in the Nodus repo.

Install it by copying that folder to `$CODEX_HOME/skills/nodus` or `~/.codex/skills/nodus`.
Codex can then invoke `$nodus` for deep Nodus-specific guidance.

## Useful links

- Nodus on PyPI: https://pypi.org/project/nodus-lang/
- GitHub: https://github.com/Masterplanner25/Nodus
- Wiki: https://github.com/Masterplanner25/Nodus/wiki
