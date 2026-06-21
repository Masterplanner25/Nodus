# [Your Project Name]

## Language

This project uses **Nodus v4** (`nodus-lang 4.0.6`).

Install: `pip install nodus-lang`

## Running scripts

```bash
nodus run script.nd
nodus run --time-limit 5000 script.nd    # for workflows or anything with sleep
nodus check script.nd                    # syntax check only
nodus fmt script.nd                      # format in place
nodus repl                               # interactive REPL
```

## Critical rules — never violate

**Types and access**
- `{k: v}` is a **record** — use dot access: `r.key`
- `{"k": v}` is a **map** — use bracket access: `m["key"]`
- Never mix. Dot on a map → `"Field access is only supported on records"`.
- `json.parse()` returns a map — always bracket access.

**Operators and syntax**
- `+=`, `-=`, `*=`, `/=` work. `**` does not — use `math.pow()`.
- `print()` is single-argument. Use interpolation: `print("val: \(x)")`.
- Expressions cannot span newlines. Keep list literals and function calls on one line.
- No `break` or `continue`. Structure loops to avoid needing them.

**Numbers**
- Bare numbers are floats: `42` → `type()` = `"float"`, `str(42)` = `"42.0"`.
- Use `i` suffix for integers: `42i` → `type()` = `"int"`, `str(42i)` = `"42"`.
- Use integers for counters, indices, loop bounds, and workflow state.

**Imports**
- All imports must be at the top level of the file — never inside functions or steps.

**Closures**
- Assigning to an outer `let` inside a closure creates a nil local shadow, not a mutation.
- Use a map for shared mutable state: `let s = {"n": 0i}` then `s["n"] = s["n"] + 1i`.

**Coroutines and channels**
- `spawn()` takes a coroutine value, not a function literal.
  Pattern: `let c = coroutine(fn() { ... })` → `spawn(c)` → `run_loop()`.
- Channels are language built-ins — `channel()`, `send()`, `recv()`, `close()`.
  Do not `import "std:channel"` — it does not exist.
- Default execution deadline is 200ms wall-clock (including sleep).
  Override: `nodus run --time-limit N script.nd`.

**Workflows**
- Workflow results are maps. Always bracket notation: `r["steps"]["step_name"]`.
- `checkpoint` is valid inside step bodies only, not at workflow body level.
- Step results must be JSON-serializable — return maps `{"k": v}`, not records `{k: v}`.
- `retry_delay_ms > 0` makes retries async. For synchronous retry, use `try/catch` inside the step body.

## AI coding assistant skill

A Claude Code skill for Nodus v4 is available at
[`skills/nodus.skill`](https://github.com/Masterplanner25/Nodus/raw/main/skills/nodus.skill)
in the Nodus repo.

Drop it in `.claude/commands/nodus.skill` alongside this file for deep Nodus support:
15 verified example programs, 20 Python→Nodus contrast pairs, named error fix classes,
and full stdlib coverage.

## Useful links

- [Nodus on PyPI](https://pypi.org/project/nodus-lang/)
- [GitHub](https://github.com/Masterplanner25/Nodus)
- [Wiki](https://github.com/Masterplanner25/Nodus/wiki)
- [Standard Library reference](https://github.com/Masterplanner25/Nodus/wiki/Standard-Library)
