# Capability Policy — design input for #405

Extraction spec for the policy layer that belongs at Nodus's host-function
chokepoint, drawn from three systems that have built one: **Codex**
(`openai/codex`), **Hermes Agent** (Nous Research), and **Claude Code**.

Source audits live outside this repo; verdicts on their claims about *Nodus* are
in [EXTERNAL_AUDIT_LEDGER.md](EXTERNAL_AUDIT_LEDGER.md). This document is about
their claims about *themselves*, used as design input.

**Status:** design input, not a plan. #405 needs a proposal; this is the material
to write one from. Nothing here is committed to.

---

## 1. What #405 has, and what it lacks

Every host-function call passes through eight lines
(`src/nodus/runtime/embedding.py:878`):

```python
def _invoke_host_function(self, vm: VM, fn, *args):
    host_args = [self._to_host_value(arg) for arg in args]
    try:
        result = fn(*host_args)
    except (LangRuntimeError, LangSyntaxError):
        raise
    except Exception as exc:
        raise HostFunctionError(exc) from exc
    return self._to_runtime_value(result)
```

Guest code cannot route around it — Nodus has no imports into the host, no
`eval`, no cross-boundary attribute access. It performs no authorisation.
`register_function(name, fn, *, arity)` carries no permission metadata, and
`allow_subprocess` / `allow_network` / `allow_env` all default `True`.

So the chokepoint exists and the policy does not. All three systems below have
built the policy; none of them has a chokepoint this clean.

---

## 2. Nodus's structural advantage, stated first

The three reference systems gate **shell command strings**. That decision costs
them enormously:

- Hermes: `tools/approval.py` is **4,557 lines**, much of it deobfuscation —
  `_deobfuscate_shell_word_for_detection`, `_replace_simple_command_substitutions`,
  `_mask_quoted_newlines`, home-path folding. Its own audit calls this *"an arms
  race by construction."*
- Codex: `ExecPolicyManager` must parse argv into segments and unwrap `bash -lc`
  and `powershell -Command` before it can classify anything.
- Claude Code: `bashSecurity.ts` is **13,963 lines**.

**Nodus does not have this problem.** The thing being authorised at
`_invoke_host_function` is already `(name: str, args: tuple)` — structured,
typed, and produced by the compiler rather than by string concatenation. There is
no command line to parse, no quoting to unwrap, no obfuscation to detect.

This is the argument for doing it here rather than anywhere else, and it should
be the headline of any proposal: **the same guarantee costs three orders of
magnitude less code, because the boundary is a function call rather than a
string.**

It does *not* remove the need to gate what a host function subsequently does —
if a host function shells out, the shell problem is back on the host's side of
the boundary. What it removes is the need for Nodus to reason about shell syntax.

---

## 3. What all three converge on

Three independent designs, one shape. Each element below appears in all three.

### 3.1 A three-valued decision, not a boolean

| System | Values |
|---|---|
| Codex | `Skip { bypass_sandbox } \| NeedsApproval { reason, proposed_amendment } \| Forbidden { reason }` |
| Claude Code | `allow \| ask \| deny` |
| Hermes | allowlist-pass \| approval-required \| hardline-block |

The middle value is the load-bearing one. A boolean policy forces every
uncertain case to be classified as one of the two extremes; a three-valued one
lets uncertainty route to a human. Codex additionally carries a
`proposed_amendment` on `NeedsApproval` — the decision suggests the rule that
would make it unnecessary next time, which is what makes approval persistence
usable rather than nagging.

### 3.2 An ordered cascade with an unbypassable floor

**This is the single most valuable thing to extract.** All three place certain
checks *before* the bypass switch, by construction.

Hermes (`check_all_command_guards`), abridged:

```
1. container fast-path skip
2. HARDLINE FLOOR (rm -rf /, mkfs, dd to device, fork bomb, kill -1)  ← unconditional, before yolo
3. sudo-stdin guard                                                   ← unconditional
4. user deny rules                                                    ← unconditional
5. yolo / approvals.mode=off / session yolo                           ← the bypass
6. permanent allowlist
7. non-interactive contexts (cron)
8. content scan
9. auxiliary-LLM auto-approve
10. human approval
```

Claude Code's nine-step cascade does the same thing: steps `1f` (content-specific
ask rules) and `1g` (`.git/`, `.claude/`, shell configs) run **before** step `2a`
(`bypassPermissions`). Its audit states the consequence plainly: *"editing `.git/`
or a shell rc file prompts even in bypass mode, by construction."*

Codex: `Decision::Forbidden` short-circuits before any attempt, and — the sharper
version — `Decision::Prompt` under `AskForApproval::Never` becomes **`Forbidden`,
not "run anyway."** A policy that cannot ask does not silently permit; it denies.

**Why this matters for Nodus now:** Nodus has no bypass mode yet. Every one of
these systems added one under pressure and then had to retrofit a floor beneath
it. Designing the floor *before* the bypass exists is free; retrofitting it is
not. If a proposal introduces anything like `allow_everything=True`, the floor
must land in the same change.

### 3.3 A fixed approval precedence

| System | Precedence |
|---|---|
| Codex | hooks → guardian (model) → user |
| Claude Code | deny rules → tool check → hooks → interactive dialog |
| Hermes | deny rules → allowlist → smart approval (model) → human |

Fixed order, not first-responder-wins. Nodus has `nodus-approvals`
(`ApprovalGate`, `ApprovalPolicy` fnmatch rules, `PairingStore`) which supplies
the *human* tier but no precedence chain above it.

### 3.4 Approval caching on a canonical key

Codex caches on `(environment, argv, cwd, permissions)` — canonicalised. Without
this, an approved-once action re-prompts on every occurrence and users learn to
approve reflexively, which destroys the value of asking. Nodus's equivalent key
is roughly `(function_name, arg_shape, capability_set)`.

### 3.5 Hooks that can block *or rewrite*

Codex's tool dispatch funnel (`registry.rs:473`):

```
notify_tool_start → PreToolUse hooks (may block or rewrite input)
                  → handle_any_tool
                  → PostToolUse hooks (may block or replace the model-visible result)
                  → lifecycle notification
```

Claude Code: **14 hook events, 4 executor kinds** (command, prompt, agent, http),
gated by `isSourceAdminTrusted()` so untrusted sources cannot register hooks at
all.

Rewrite, not just veto, is what makes hooks useful for redaction and for
capability attenuation. `nodus-extension`'s `HookRunner` has phase hooks; the
lifecycle *points* are what's missing.

---

## 4. Lifecycle points, mapped to Nodus

Codex and Claude Code agree on the useful set. Nodus's equivalents:

| Point | Codex | Nodus site |
|---|---|---|
| Session start | `run_pending_session_start_hooks()` | `NodusRuntime.__init__` / first `run_source` |
| Pre-call | `run_pre_tool_use_hooks` — may block or rewrite args | **`_invoke_host_function`, before `fn(*host_args)`** |
| Permission request | `Session::request_approval` | new — the approval tier |
| Post-call | `run_post_tool_use_hooks` — may rewrite the result | **`_invoke_host_function`, before `_to_runtime_value`** |
| Stop | `run_turn_stop_hooks` — may force continuation | `run_task_graph` completion |
| Denial | *(none of the three emits a structured denial event)* | new — see §6 |

The pre- and post-call points are both inside the eight lines already quoted.
That is the whole reason this is tractable.

**Second chokepoint:** builtins do not pass through `_invoke_host_function` —
they dispatch inside the VM. Audit 02 (F21) identified that as its own single
site. A complete policy layer needs both; a first cut could take host functions
only, but the proposal must say which it covers, because `subprocess.run` and
`http.get` are **builtins**, not host functions. Gating only host functions would
be a policy that misses the capabilities anyone actually cares about.

---

## 5. Policy declaration — three models

| System | Mechanism | Trade |
|---|---|---|
| Codex | **Starlark** rules in `~/.codex/rules/*.rules`, layered low→high precedence, with `ignore_user_and_project_exec_policy_rules` under managed config | Most expressive; adds a language dependency and its own sandboxing question |
| Claude Code | **8 rule sources** in precedence order: `policySettings`, `flagSettings`, `command` (all read-only — `deletePermissionRule` *throws* on them), then `localSettings`, `projectSettings`, `userSettings`, `session`, `cliArg` | No new language; read-only tiers are the enforcement mechanism |
| Hermes | Config dicts + Python predicates | Simplest; least auditable |

**For Nodus, Claude Code's model is the better fit.** Layered sources with
explicit precedence and *structurally read-only* high-precedence tiers give an
operator-managed policy that a project cannot override, without introducing a
policy language into a runtime whose selling point is a small closed surface.
Adding Starlark to Nodus would widen exactly the surface §2 says is the
advantage.

### 5.1 Decision — the `nodus-governance` seam

**Decided 2026-08-15.** There is no design conflict to resolve; the two answer
different questions and share only the word "policy".

`nodus-governance` is 442 lines across `policy.py` / `scope.py` / `trust.py` /
`audit.py`. Its central type is `PolicyBundle`, whose central method is
`can_manage(operator_id)` — **which operator may manage this bundle**. Nothing in
it evaluates a guest call. It is the operator management plane.

The rules that follow, in priority order:

1. **The enforcement plane must not depend on the management plane.** A bare
   `NodusRuntime()`, in a process with no companion package installed, must still
   enforce. All three Nodus audits identified in-process capability confinement as
   the differentiator; a differentiator cannot be an optional dependency. So the
   decision model — the three-valued verdict, rule matching, and the floor — lives
   **in core**, stdlib-only, alongside the chokepoint it guards.
2. **`nodus-governance` becomes a rule *source*, not the evaluator.** Under the
   layered-sources model above it is one high-precedence, operator-managed tier.
   It supplies rules; core decides. This is the same direction of dependency the
   ecosystem already uses — core never imports a companion.
3. **`audit.py` is the sink for the denial events, not their producer.** Core
   emits `capability_denied` on the event bus it already has (§6);
   `nodus-governance` persists it tamper-evidently for operators who want that.
   Core does not require it to have been persisted.
4. **Rename to remove the collision.** Core's type should be
   `CapabilityPolicy` / `CapabilityDecision`, never `Policy` — two things named
   `Policy` in one ecosystem, meaning "operator authority" and "guest authority",
   is a NAME-COL-001 repeat waiting to happen.
5. **Scope and trust stay where they are.** `scope.py` and `trust.py` are about
   operators and channel peers. Neither belongs at the VM boundary.

The seam in one line: **governance declares who may set the rules; core decides
whether a call proceeds.** Neither needs the other to function.

---

## 6. What none of the three does well — Nodus's opportunities

**Structured denial events.** None of the three emits a first-class denial record
on an event bus. Codex has telemetry, Claude Code has `denialTracking.ts`
(a counter) and an OTel `tool_decision` event; neither is an audit trail you could
reconstruct a session from. Audit 01 §19 listed "no audit trail of denials" as a
Nodus gap — but it is an industry gap. Nodus already has a typed event bus and
`nodus-governance.audit`; emitting `capability_denied` with the policy source,
the rule that matched, and the decision tier would be ahead of all three.

**Attenuation / delegation.** No system reviewed can run a sub-computation under
*reduced* authority. Codex has depth and thread limits; Hermes has
`max_spawn_depth: 1` and role degradation to leaf; neither reduces *capability*.
For Nodus this is unusually cheap — a child VM already exists (`vm.py:1179`), so
attenuation is a narrower capability set on construction rather than a new
mechanism.

**Deny-by-default.** All three default permissive and rely on the cascade. Audit
03 asked (Q7) whether Nodus could flip this; it is a compatibility question, not a
technical one, and it is the difference between "can be gated" and "is gated."

---

## 7. What not to copy

**Model-in-the-loop authorisation.** Codex's `guardian/` is a second model
instance that authorises actions; Hermes's `_smart_approve` is an auxiliary LLM
that auto-approves "low-risk" commands. Hermes's own audit flags this with a
warning: *"A model judging whether another model's command is dangerous."*

If Nodus ever does this, Codex's guardrails are the minimum bar: **fails closed**
on timeout (90s), execution failure, or malformed output, plus a
`GuardianRejectionCircuitBreaker` that interrupts after 3 consecutive or 10 recent
denials. Note that this sits precisely on the wrong side of Nodus's own
architectural line — the runtime declines semantic judgement everywhere else, and
all three Nodus audits identified that restraint as its cleanest property.
Delegating *authorisation* to inference would be the one place it breaks that.

**Fail-open scanners.** Hermes's tirith scanner defaults to
`security.tirith_fail_open: true`. A scanner that fails open is decoration.

**Configuration mistaken for enforcement.** Codex sets `CODEX_SANDBOX=seatbelt`
and `CODEX_SANDBOX_NETWORK_DISABLED=1` in the child environment; its audit is
blunt that these are *"hints to well-behaved programs, not controls."* Nodus's
`allow_network=False` must be enforcement at the builtin, never a flag a host
function is trusted to respect.

**Heuristic string classification.** Per §2, do not import the deobfuscation
machinery. It exists to solve a problem Nodus does not have, and importing it
would create the problem.

---

## 8. Suggested staging

Not a commitment — an ordering that keeps each step independently shippable.

1. **Emit before enforcing.** Add the pre/post-call hook points and a
   `capability_denied` / `capability_invoked` event, with policy always allowing.
   Purely additive, breaks nobody, and produces the data needed to choose defaults.
2. **Permission metadata on registration.** `register_function(..., requires=...)`,
   defaulting to today's behaviour. Makes authority a property of the function.
3. **The cascade, with the floor first.** Three-valued decision, layered
   read-only-tiered sources, canonical-key approval caching, fixed precedence to
   `nodus-approvals`. **The unbypassable floor lands in this step, before any
   bypass switch exists.**
4. **Builtins.** Extend to the VM dispatch site so `subprocess`/`http`/`fs` are
   covered — without this the layer misses the capabilities that matter.
5. **Attenuation**, then **deny-by-default** as a separate compatibility decision.

Steps 1–2 are additive. Step 3 is where the design questions are. Step 5 is a
product decision, not an engineering one.

---

## 9. Why this is the convergent finding

All three audits *of Nodus* independently named the ungoverned chokepoint the
highest-leverage change available — the only unanimous convergence in that series,
and the only one that turned out to be true (see the ledger's structural-vs-
behavioural split). Both audit 01 §8 and audit 03 §8 separately concluded that
in-process capability confinement of untrusted code is one of only **two** things
Nodus offers that Python structurally cannot.

And the three audits *of other systems* converge on the same place from the
opposite direction: each built this layer, each paid heavily to build it against
shell strings, and each has a chokepoint less clean than the one Nodus already
has and does not use.

Related: **#394** (step ordering is bypassable) is the other place a claimed
invariant is not one, and **D1** in the ledger — the positioning decision — turns
on this: *"run untrusted, model-generated orchestration in-process under a
capability jail"* is only worth leading with once the jail is closed.
