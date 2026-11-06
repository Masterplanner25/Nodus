---
description: "Nodus embedding API traps: NodusRuntime defaults, capabilities, per-runtime state, and what is promised to embedders. Read before changing or embedding NodusRuntime."
---

# Embedding API

> Moved out of the root `CLAUDE.md` on 2026-11-05 so it loads on demand. "This file" in the text
> below may mean the root file as it was. A section it names may now be in another file:
> release rules in `.claude/commands/release-sequence.md`, the bug shape in
> `.claude/commands/recurring-bug-shape.md`, embedding in `.claude/commands/nodus-embedding.md`.

## Embedding API — known blockers and operational traps

These were identified by a raw-path readiness probe and are filed as GitHub issues.
Full analysis: `C:\dev\nodus-mcp\docs\design\06-embedding-runtime-blockers.md`.
All entries are also in `docs/governance/TECH_DEBT.md`.

**`run_source(source, filename=...)` runs `source`. It did not, before 5.1.0** (#521,
present since v0.4.0): if a file of that name existed, the loader read *the file* and
discarded the `source` argument, returning `ok=True` with the other program's output — so
which program ran depended on the process CWD. `filename` is a label; a real path only
decides where relative imports resolve from. Use `run_file` to run a file.

Two things that make this worth remembering rather than just fixed. It was **documented
backwards**: the guide has a section headed *"Passing a filename"* saying it labels errors,
illustrated with `filename="myscript.nd"` — the safe statement and the unsafe example. And
the bytecode cache is keyed on **path + mtime**, so it carried the same defect
independently; fixing the branch in `embedding.py` alone left it reachable through a warm
cache, and guarding the cache *read* alone still let a differing source poison the entry for
the next `run_file`. Three paths, one question.

**EMBED-001 (#97) — FIXED. `timeout_ms` now defaults to `None`.** The old 200ms-default
trap is gone; `NodusRuntime()` applies no wall-clock deadline. Verified 2026-08-07:
`NodusRuntime().timeout_ms is None`. Do not re-add `timeout_ms=None` as a "fix" — it is
already the default. (SCHED-001 also means cooperative sleep no longer consumes the
budget even when a deadline *is* set.)

**`max_frames` (#350, then #387) — FIXED at both layers.** `NodusRuntime` honours
`MAX_STACK_DEPTH` (10,000), and as of 5.0.3 so does a directly constructed `VM()` — #350 fixed
the wrapper and left the engine underneath uncapped, which is the wrapper/sibling shape again.
Runaway recursion now raises `Call stack overflow` instead of growing frames until the OS kills
the process; VM frames are heap-allocated, so Python's own recursion limit never fires.

```python
rt = NodusRuntime(max_steps=None, timeout_ms=None)                  # capped at 10,000
rt = NodusRuntime(max_steps=None, timeout_ms=None, max_frames=1000) # tighter
```

There is no "unlimited" setting — pass a large integer if you genuinely want one. **Only the
call-depth cap defaults on**; `max_steps` and `deadline` stay unbounded on a bare VM because
`EXECUTION_TIMEOUT_MS` is 200 ms and a step budget is host policy. v4.1.1 and earlier are
affected at the runtime layer; anything before 5.0.3 at the VM layer.

**Capability switches deny by default as of v5.0.0 (#405).** `allow_subprocess`,
`allow_network` and `allow_env` are all **`False`**. A bare `NodusRuntime()` cannot shell out,
open sockets, or read the process environment; grant explicitly:

```python
NodusRuntime(allow_subprocess=True, allow_network=True)
```

`allowed_paths` is unchanged — it already defaulted to a CWD jail (`[os.getcwd()]`).

Earlier revisions of this file said these "default to permissive". That was true through
v4.2.0 and is the opposite of current behaviour, so **any advice written against the old
default is now backwards** — including "a bare runtime can shell out", which several docs and
issue comments relied on.

**`nodus run` and the rest of the CLI are deliberately NOT affected.** This is a decision, not
an oversight: the CLI builds a `VM` directly and never constructs a `NodusRuntime`, and a test
pins **both** halves so the "inconsistency" is not tidied away by a later reader. The domain
deny-by-default protects is *work you did not fully author* — a developer running a script they
just wrote is not that.

Three related surfaces, all in `src/nodus/runtime/capability.py`:

- **`CapabilityPolicy`** — optional, consulted at the host boundary; three-valued
  `allow | ask | deny`. `ask` with no `approval_channel` configured denies.
- **The Floor** (`DEFAULT_FLOOR`) — unbypassable; a policy that allows everything **cannot**
  override it. Its one real rule: a Nodus program cannot *write* into `.nodus/` (the workflow
  store, graph state, bytecode cache). Reads are untouched.
- **Two chokepoints, not one** — `_invoke_host_function` (host functions) and
  `VM.call_builtin` (builtins). A guard added to only one of them covers nothing that matters;
  see the recurring bug shape section.

Migration: `docs/migration/v5.0-deny-by-default.md`. Design: `docs/design/v5/02-capability-policy.md`.

**Per-runtime state, and one breaking default (5.0.3+, #185/#390/#424).**

- **Memory is isolated per `NodusRuntime`.** Two runtimes in a process no longer share it — a
  guest script writes memory via `memory_put`, so a shared store was a channel between tenants.
  `share_process_state=True` restores the old sharing; `memory_store=` injects a specific store.
  **A bare `VM` and the CLI keep the process-global store** — single-tenant by construction.
- **Agents are deliberately NOT isolated.** A guest cannot register one: the only agent builtins
  are `agent_call` / `agent_available` / `agent_describe`, and registration is host-only from
  Python. A shared registry holds what the *host* put there, so isolating it by default would
  break `register_agent(...)` → `run_source(...)` — it broke 11 tests when tried — to prevent a
  leak guests cannot cause. `agent_registry=` scopes it for hosts that want per-tenant sets.
- **`agent_timeout_ms=`** bounds a host agent handler. The tightest of the step's `timeout_ms`
  (minus time already spent) and this default wins. It stops the **wait**, not the handler:
  arbitrary Python cannot be preempted, so the handler runs on a daemon thread and is abandoned
  at the deadline. Abandoned handlers are recorded — `abandoned_agent_calls()`,
  `abandoned_agent_call_count()`.
- **`workflow_runner=`** gives a runtime its own runner. Unset keeps the process-global one, so
  nothing that worked before changes.

**Do not store new runtime state under a public attribute name without checking downstream.**
`self.memory_store` collided with a read-only property of the same name on
`nodus_sdk.NodusSDKRuntime` and broke every construction of that subclass in 5.0.3. It is
`self._memory_store` now. A base class adding a public attribute can break any subclass that
made the same name a property.

**What is promised to embedders (5.0.1, #441–#444).** Added after aindy-runtime reported four
places where it was coupled to something we had never published as a surface:

- **`GATED_BUILTINS` / `GATED_BUILTIN_NAMES`** — the registration-time gates as data, flag →
  `GatedBuiltinGroup(flag, capability, description, arity, names)`. `register_all` builds its
  refusing stubs *from* this, so the published list and the enforced gate cannot disagree.
  **This is not `BUILTIN_CAPABILITIES`** — that one is what consults the policy at call time.
  The two differ by exactly one entry (`subprocess_shell_quote`, string manipulation that runs
  nothing) and `tests/test_downstream_contracts.py` pins the relationship, because before that
  they were two hand-maintained lists with nothing checking they agreed.
- **The denial contract is `kind` and the flag name, not the sentence.** `error["kind"]` is
  `"sandbox"`; `error["message"]` contains the granting flag. The wording changed in 5.0.0 and
  turned four downstream confinement tests red **while the guest was fully confined**. If you
  rephrase a denial, keep the flag name in it.
- **`NodusRuntime.active_vm()`** is supported; the `VM` it returns is not. `_get_active_vm()` is
  retained as an alias because downstream pins it — do not "clean it up".
- **Do not add `**kwargs` to `NodusRuntime.__init__`, and keep the confinement flags
  keyword-only.** Both are load-bearing: with a catch-all, a renamed flag is silently swallowed
  and the guest runs unconfined with every mock-based test on the embedder's side still green.
  Pinned by test so it cannot be undone casually.
- **`register_function` refusing to override a builtin is a security boundary**, not a
  convenience check. Because a builtin cannot be aliased, a host can install a fail-loud guard
  under a guest-reachable name (aindy does this for `syscall`) and know the guard is the only
  thing there. Also now pinned.

**SPAWN-001 (#116) and CHAN-001 (#107) — both FIXED.** `wait_async()` suspends properly,
and a `recv()` with no possible sender raises a deadlock error rather than orphaning the
coroutine. History and implementation notes are in `docs/governance/TECH_DEBT.md`.

The one part still worth having here, because it wastes an afternoon: **testing the
deadlock error requires driving the scheduler.** `spawn(c)` alone does not run the
coroutine — without a `run_loop()` the script exits 0 and the coroutine never starts,
which *looks exactly like* the original bug. Use `spawn(c)` then `run_loop()`.

## Capability files

| What | Where |
|------|-------|
| Capability policy design | `docs/governance/CAPABILITY_POLICY_DESIGN.md` — design input for #405, extracted from Codex / Hermes / Claude Code. Read before proposing anything at the host-function chokepoint. **Its staging is not what shipped** — it puts builtins fourth; they had to come first |
