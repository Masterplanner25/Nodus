# AGENTS.md

## Language

This project uses **Nodus** (`nodus-lang 5.7.1`).

Install: `pip install nodus-lang`

Run `nodus docs` for the guide, the machine-readable index and the language
skill, pinned to the version actually installed.

**Embedding defaults changed in 5.0.0.** `NodusRuntime()` denies subprocess,
network and env access unless granted (`allow_subprocess=True`, …). Any advice
written against the older permissive default is backwards. `timeout_ms` defaults
to `None` — the old 200 ms trap is gone, so passing `timeout_ms=None` is
redundant rather than required.

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
- `break` and `continue` work in all loop forms (4.1.0+), but cannot cross a `try`/`catch`/`finally` boundary.
- `match` is an expression for value dispatch (4.1.0+): `match x { "a" => 1i, _ => 0i }`. `_` must be last; no binding patterns.
- Bare numbers are floats. Use `i` suffix for counters, indices, loop bounds, and workflow state.
- Imports must be top-level only.
- Assigning to a **module-top-level** `let` from inside a function or closure silently writes a frame-local; the top-level value never changes (#671). A `let` declared inside a function is captured and mutated normally. Use a map for state shared across functions at module scope.
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
