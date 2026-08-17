# Capability policy at the host boundary — #405, stages 1–3

**Status: stages 1–3 implemented, Experimental.** The design input this builds on
is [`CAPABILITY_POLICY_DESIGN.md`](../../governance/CAPABILITY_POLICY_DESIGN.md),
extracted from Codex, Hermes and Claude Code; the seam against `nodus-governance`
was decided there on 2026-08-15 and is unchanged. This document records what
shipped, one correction to that document's staging, and what is deliberately not
built.

All three external architecture audits independently identified this boundary as
the highest-leverage change available. That level of convergence occurred on no
other finding in the series.

---

## 1. The correction: two chokepoints, not one

`CAPABILITY_POLICY_DESIGN.md` §8 stages *"Builtins"* fourth, after host
functions. Measured against `main` before writing any code, that ordering would
have produced a policy layer and an audit trail covering **nothing anyone cares
about**:

| Surface | Where it dispatches | Passes `_invoke_host_function`? |
|---|---|---|
| `register_function` host functions | `embedding.py:_invoke_host_function` | yes |
| `subprocess_run`, `subprocess_shell`, … | `VM.call_builtin` | **no** |
| `http_get`, `http_post`, … | `VM.call_builtin` | **no** |
| `env_get`, `env_set`, … | `VM.call_builtin` | **no** |

Every capability the issue names — shell out, open sockets, read the environment
— is a **builtin**, registered through `BuiltinRegistry.register_all` and
dispatched by `VM.call_builtin`. The issue's own comment flagged this; the
staging did not reflect it. **Both sites are covered from the start.** Neither is
routable around: Nodus has no imports into the host, no `eval`, and no attribute
access across the boundary.

## 2. What the existing mechanism actually was

Worth stating precisely, because it is easy to read `allow_subprocess=False` as a
capability system and conclude the work is half done.

It is **registration-time, not call-time**. With `allow_subprocess=False` the
subprocess module is never registered; blocked stubs are registered in its place
(`registry.py`). Consequences, all measured:

- **Binary, per category.** Three booleans — subprocess, network, env. There is
  no way to permit `http_get` and refuse `http_post`, or to decide on the URL.
- **Fixed at VM construction.** No per-call, per-script or per-step authority.
- **Invisible.** A denial raised `SandboxError` and emitted nothing structured.
  Event types on a denied run were `runtime_error`, `vm_call`, `vm_exception` —
  nothing an operator could filter for. *"What did this program try to do that it
  was not allowed to?"* had no answer.
- **Host functions had no gating at all.** A registered function was callable by
  any guest code, unconditionally. Verified: `register_function("danger", …)`
  then `danger()` returns its value with every default in place.

So the chokepoint was built and the policy was absent, exactly as #405 says.

## 3. What shipped

`src/nodus/runtime/capability.py` — stdlib-only, in core, per the decided seam: a
bare `NodusRuntime()` in a process with no companion installed must still
enforce, because a differentiator cannot be an optional dependency.

```python
from nodus.runtime.capability import DenyList, SUBPROCESS

rt = NodusRuntime(capability_policy=DenyList(SUBPROCESS))
```

- **`CapabilityPolicy`** — one method, `check(request) -> CapabilityDecision`.
  Named `Capability*` and never `Policy`, because `nodus-governance` already has
  a `PolicyBundle` meaning *operator* authority; two things named `Policy` in one
  ecosystem is a NAME-COL-001 repeat waiting to happen.
- **Consulted at both chokepoints**, and the policy travels with the VM, so it is
  not shed by crossing into a module or a tool handler (§5).
- **`capability_denied` on the event bus**, including for the pre-existing
  `allow_subprocess=False` gates, which were the oldest capability mechanism in
  the runtime and the least visible.
- **`register_function(..., requires=…)`** — authority as a property of the
  function rather than of the runtime. An unknown capability name raises at
  registration; a typo must not silently grant what the caller believed they had
  restricted.
- **The request carries `args`**, so a policy can decide on *what* and not only
  *whether*: `http_get("https://internal/…")` is a different request from a
  public one. A test pins that a policy can permit `sp.run(["echo", …])` and
  refuse `sp.run(["hostname"])`.

Default is `None` — no policy, no behaviour change. That is what keeps this
additive.

## 4. Only capability-bearing builtins consult the policy

`BUILTIN_CAPABILITIES` maps builtin name → capability, and `call_builtin` looks
up that dict and skips the policy entirely when the entry is absent.

This is a performance decision and a design one. `len`, `push` and `str` carry no
authority, and making the interpreter's hottest path pay a policy call for them
would cost real time for nothing. It also means **that mapping is the capability
surface of the language, in one readable place** — which is the *inspectable*
property [`00-domain-statement.md`](00-domain-statement.md) asks of anything in
the domain.

`subprocess_shell_quote` is deliberately absent: it is string manipulation and
runs nothing. Gating it would teach readers the list is approximate.

**Cost, stated honestly:** one dict miss per builtin call. A benchmark was
attempted and is *not* reported, because run-to-run variance on this machine was
about 2× — enough to make the "before" runs come out slower than the "after"
ones. That measurement cannot resolve an effect this small, so the claim here is
the mechanism, not a number.

## 5. Authority is not shed by crossing a boundary

The first working version failed exactly one case, and it was the one that
matters: `import "std:subprocess"` — the documented way to call subprocess — runs
on a **child VM**, which did not inherit the policy. So the jail was in place and
the only call anyone makes walked around it.

The policy now propagates wherever the capability flags already did:
`ModuleLoader` (`module.py`) and tool handlers (`tool_module.py`). This is the
same shape as #392's `inline_retries` and #399's rebuild guard — a check that
lives on one path while a sibling path bypasses it — and it is worth expecting at
every new boundary rather than rediscovering.

A test reverting only `module.py` fails five cases, so the guard is guarded.

## 5b. Stage 3 — the three-valued decision and the floor

### The decision is `allow | ask | deny`

`ask` means *this needs a human*, and what happens when there is nobody to ask is
the decision that matters: **`ask` with no approval channel is `deny`, never "run
anyway."** Codex reaches the same answer — `Prompt` under `AskForApproval::Never`
becomes `Forbidden` — and the alternative silently converts an unanswered
question into permission. `CapabilityDecision.allowed` stays true only for an
outright allow, so existing callers reading it cannot mistake `ask` for a yes.

An embedder supplies an `ApprovalChannel` to make `ask` mean something. It is
told what it is approving — capability, target and reason — not merely asked.

Routing `ask` to the durable `workflow_wait` pause, which audit 02 correctly
noted is already approval-shaped, is **not** built. It only exists inside a
workflow step, and a capability check can happen anywhere; a top-level script
calling `http_get` has nothing to suspend into. That is a later increment, not a
hole in this one — the synchronous channel is the general case and the durable
pause is the specialisation.

### The floor is consulted first and can only restrict

`Floor.check` returns a decision to impose or `None` to abstain. **There is no
way for a floor to return `allow`** — one that could grant would override a
policy's refusal, which is the opposite of a floor. It can only make the answer
stricter.

**Why now:** all three reference systems added a bypass mode under pressure and
retrofitted a floor beneath it afterwards. Nodus has no bypass mode, so building
the floor first is free.

**The default floor refuses guest writes into `.nodus/`** — the workflow store,
graph state and bytecode cache. This is deliberately not an empty mechanism: a
floor that never fires is itself the "check that cannot fail" this codebase keeps
finding. Verified before building it, with every default in place:

```
ok: True   stdout: overwrote run state
file now: {"forged": true}
```

A guest script overwrote a workflow run record and the run reported success. That
is forging durable state, and it is Nodus's equivalent of the paths Claude Code
protects even under `bypassPermissions`. Reads are untouched; only writes are
refused, and matching is on normalised path *segments*, so `my.nodus-notes.txt`
is not caught and `../.nodus/x` is.

**This is the one part of #405 that is not purely additive.** A program that
wrote into `.nodus/` now fails. That is the intended behaviour change and the
only one in stages 1–3.

## 6. Deliberately not built

Each of these is where the design questions are, and shipping a stub of any of
them would be worse than shipping none: a placeholder that always resolves one
way is indistinguishable from the decision having been made, which is the failure
this whole issue is about.

- **Routing `ask` to `workflow_wait`**, so an approval is durable rather than a
  blocking callback. See §5b for why the synchronous channel came first.
- **Layered rule sources with fixed precedence**, and approval caching on a
  canonical key.
- **Attenuation** — running a sub-computation under reduced authority. Nothing
  exists for this today.
- **Deny-by-default.** A compatibility decision rather than an engineering one,
  and the one that changes the story from *"can be gated"* to *"is gated"*. It
  needs its own decision with its own migration note.

Also not copied, per §7 of the design input: model-in-the-loop authorisation,
fail-open scanners, and configuration mistaken for enforcement.

## 7. What this does and does not license saying

**Can now be said:** a host can refuse a capability per call, decide on the
call's arguments, and get a structured record of every refusal — in-process,
against code it did not write, with no way for that code to route around the
decision.

**Can now also be said, since stage 5:** that an *embedded* Nodus runtime is
capability-jailed by default. `allow_subprocess`, `allow_network` and `allow_env`
default to `False`; a bare `NodusRuntime()` refuses all three. Audit 03's framing
— *"the chokepoint is built; the door is propped open by registering subprocess
and http by default"* — no longer describes the embedding API.

**Still cannot be said:** that *Nodus* is capability-jailed by default, without
the qualifier. `nodus run` is unchanged and intentionally so (§7.1), so the
accurate sentence names the surface: **embedded runtimes deny by default; the CLI
does not.** Dropping the qualifier would be the same error the positioning fix
corrected in `649a2ed` — a true claim about one surface stated as a claim about
the project.

### 7.1 Why the CLI is exempt

The domain is *work you did not fully author*. A developer running a script they
just wrote is not that, and a CLI that refused to shell out would be like
`python` refusing to open sockets — friction with no threat model behind it.

This is a boundary rather than a special case: `nodus run` builds a `VM` directly
and never constructs a `NodusRuntime`, so the two defaults live in different
places by construction. Both halves are pinned by tests, including one asserting
the CLI does not route through `NodusRuntime` — because the obvious "fix" for the
apparent inconsistency is to make them the same, and that would sandbox every
script anyone runs.

The one control that spans both is the floor: neither surface may write into
`.nodus/`.
