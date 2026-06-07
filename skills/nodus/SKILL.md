---
name: nodus
description: Use when writing, editing, reviewing, or debugging Nodus `.nd` code, workflow DSL programs, stdlib imports, coroutine/channel logic, `nodus` CLI usage, or Python embedding with `NodusRuntime`. Trigger on any direct mention of Nodus or `nodus-lang`, any `.nd` file, requests to convert orchestration code into Nodus, workflow/result-shape questions, or runtime failures such as map-vs-record access, closure mutation, `spawn()` misuse, import resolution, or time-limit issues.
---

# Nodus

Nodus is a workflow-oriented orchestration DSL. Do not treat it like lightweight Python. Favor `workflow { step ... }`, durable state, and explicit coroutine/channel primitives over Python-shaped abstractions.

## Start Here

- Read [references/quickstart.md](references/quickstart.md) first for the rules that cause most failures.
- Read [references/errors.md](references/errors.md) when the user reports an unfamiliar parser, runtime, import, or workflow failure.
- Read [references/examples.md](references/examples.md) before drafting new Nodus code from scratch.
- Read [references/modules.md](references/modules.md) for stdlib imports, package layout, or Python companion-library questions.
- Read [references/idioms.md](references/idioms.md) when translating Python habits into Nodus.

## Non-Negotiable Rules

- Treat `{"k": v}` as a map and access it with `m["k"]`. Treat `{k: v}` as a record and access it with `r.k`. Never mix them.
- Assume `json.parse()` returns a map, not a record.
- Use `i` suffix for integer arithmetic, counters, list indexes, and workflow state. Bare numbers are floats.
- Never use `+=` or `**`. Write `x = x + 1i` and use `math.pow()` when needed.
- Keep function calls, list literals, and interpolated expressions on one line. Newlines terminate expressions.
- Use `print()` with exactly one argument. Prefer interpolation: `print("value: \(x)")`.
- Keep imports at top level only. Never place `import` inside `fn`, `workflow`, `step`, or conditional bodies.
- Use a map for shared mutable state across closures: `let state = {"n": 0i}` then mutate `state["n"]`.
- Call `spawn()` with a coroutine value, not a function literal. Use `let c = coroutine(fn() { ... })`, then `spawn(c)`, then `run_loop()`.
- Treat workflow results from `run_workflow()` as maps: `r["steps"]["name"]`, `r["state"]["counter"]`.
- Use `checkpoint` only inside step bodies.
- Return JSON-serializable values from workflow steps. Prefer maps, lists, strings, bools, ints, floats, and nil.

## Working Style

- Preserve existing behavior unless the user explicitly wants a language change.
- Keep parser, compiler, and VM concerns separate when patching the implementation.
- Add tests for new language features or behavior fixes.
- Verify examples and user-facing snippets with `nodus check` at minimum, and run runtime examples when the task changes behavior.

## Validation

- Run `nodus check <file>.nd` on any edited or newly created script.
- Run targeted tests when changing parser/compiler/runtime behavior.
- If documentation includes runnable blocks changed by the task, verify them with `nodus run` or the repo's doc gate process when practical.

## Local Learning Loop

- Check `.nodus/learnings.md` if it exists in the user workspace. Treat it as local Nodus-specific session memory.
- If a task reveals a new idiom, recurring runtime trap, or skill gap, append a terse dated note there after the task.
