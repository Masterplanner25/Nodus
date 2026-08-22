# Outcome ambiguity — design input, unfiled

**Status: proposal, no issue yet.** Nothing here is implemented. §10 records what
already exists in the nodus-lang tree, verified against `main` at `f7ab7ff`; §14 is the
runtime side's reply, verified against `aindy-runtime` at `f06f5b3`. §11 is proposal and
**not a work order** — the ordering is §14.9's. §12 is open **except its third bullet**,
which §14.5 answers. **★ marks a cross-reference added after the passage it sits under
was written** — follow it before acting on the text above it.

**The first work item is not a browser.** §14.9's closing observation, promoted here because
it changes what anyone would do first: the vocabulary gap this document is about is **already
reachable from an ordinary outbound POST**. There is no honest `execution_guarantee` for a
non-transactional action to declare, and no effect status to record an unobserved outcome in,
and both are true of an HTTP call made today. A browser does not create the gap — it removes
the option of ignoring it. So the first items in §14.9's ordering are runtime vocabulary work
with no browser in them at all, and the browser framing below is motivational rather than
necessary.

**Provenance.** This started as a scoping question about a companion note —
`OneDrive/Masterplan Infinite Weave Ecosystem/AI Tech And Development/Designs/NOTE_browser_automation_feasibility.md`,
written against the `C:\codev` sweep of 2026-08-19/20 and aimed at `aindy-runtime`,
not at nodus-lang. The question asked here is the language one: **does browser
automation fit the domain statement in `00-domain-statement.md`, or widen it?**

It does fit — §2. But answering it surfaced something larger, which is why this is
its own document rather than a paragraph on the note: **browser automation is the
first surface in the ecosystem where the guarantee provably cannot be complete**,
and the language has no vocabulary for a partial one.

The reasoning is kept in the order it happened, questions included, because the
questions did more work than the answers.

---

## 1. The question chain

Five questions, each of which changed the answer to the one before it.

| # | Question | Where |
|---|---|---|
| Q0 | Is Nodus for *automation*, given "orchestration" and "workflow" collapse? | §1.1 |
| Q1 | Does browser automation fit the domain, or widen it? | §2–§4 |
| Q2 | What is knowable on timeout? | §5–§6 |
| Q3 | Why is the residue irreducible? | §7 |
| Q4 | So do you need two worlds, and choose between them? | §8–§9 |

### 1.1 Q0, briefly — automation is an application, not the domain

The three words name different things and that is why they collapse into each
other in conversation:

- **Automation** names a *motive* — no human does this each time.
- **Orchestration** names a *shape* — several parties, coordinated.
- **Workflow** names a *unit* — a durable, named plan with steps.

Nodus has a construct for the second and third. At the first it is simply true and
uninformative: Nodus automates things the way Python automates things, because §3
of `00-domain-statement.md` explicitly licenses general computation *inside* a
bounded unit as "the payload, not a widening of the domain."

The domain statement's test is sharper than the word. Most automation fails it in
the healthy direction — a script that renames files runs for 200ms, you wrote every
line, nothing survives it, and `@exactly_once` has nothing to protect.

**The codebase already draws this line deliberately.** `nodus run` is exempt from
deny-by-default because the domain deny-by-default protects is *work you did not
fully author*, and "a developer running a script they just wrote is not that."
That is a decision that says plain automation is the case we chose **not** to
protect. Supported use, not target.

So: automation is an application, exactly as "agentic" is. The accurate phrasing
is *automation that will be interrupted, that you did not fully write, and whose
side effects matter if they fire twice* — a much smaller set, and the smallness is
the value of the claim.

---

## 2. Q1 — browser automation passes the domain test clause by clause

The domain is *"work that will be interrupted, that you did not fully author, and
that touches the world."*

| clause | browser action |
|---|---|
| will be interrupted | session, cookies and page state all die with the process |
| you did not fully author | the click sequence is generated |
| touches the world | submit / send / purchase / post — irreversible, non-transactional |

Compare the row that **fell out** of §4 of the domain statement: memory, rejected
because "a MAS path typo is a correctness bug, not a bound or a survival property."
Browser fails that exclusion in every direction. It is not a marginal admission —
on the three clauses it is the cleanest instance in the ecosystem.

---

## 3. Test 2 resolves through the split rule already written

A browser driver is a host function. It executes outside the instruction stream, so
the VM cannot preempt it — the same structural limit as #405's chokepoint and
#424's agent handler, and the reason every VM-level bound misses it.

That puts it on the rule from `00-domain-statement.md` §4.1:

> When a guarantee must hold across the host boundary, the language owns the
> **declaration** and the runtime owns the **enforcement**. The compiler's job is
> that you cannot forget to declare the bound.

A browser action registered behind a syscall with a *declared* execution property
is that rule applied.

**Worth recording: the note derived this independently.** It reached
reserve → call → reconcile from LiteLLM's spend governor, for money, without
reference to §4.1. Two derivations converging on the same declaration/enforcement
split is evidence the domain statement is doing work rather than ratifying what
already exists — which is the specific weakness §7 of that document admits about
itself.

> **★ Three derivations, not two — see §14.6.** The same shape was reached earlier again in
> `aindy-runtime`, from Aider's Git discipline, and filed as `EFFECT-PRECONDITION-1`. Money,
> distributed-systems theory and version control all converged on *plant an attributable trace
> before you act* — and §14.6 records that a browser is the external mutable resource that
> deferral was waiting on.

---

## 4. The inconsistency the domain test catches

The note contains two claims that are not the same claim:

- §3: the achievable guarantee is **at-most-once dispatch with recorded outcome**.
- §6.1: **`EXACTLY_ONCE` on the mutating ones only**.

§3 is right and §6.1 is the failure mode this codebase spent the 5.0.x cycle
removing. An `EXACTLY_ONCE` label on an action whose outcome is *definitionally
unknowable on timeout* is success-shaped: the ledger reports a guarantee the world
never agreed to.

The rhyme with #411 is close but not identical, and the difference is the
interesting part:

| | #411 | here |
|---|---|---|
| the guarantee | `@exactly_once` envelope | `EXACTLY_ONCE` on a mutating browser action |
| who could invalidate it | **the program's author**, by shadowing a name | **the remote site**, by not being transactional |
| what it degrades to | a convention | a wish |

#411's lesson generalises: *a compiler-applied guarantee is only as strong as the
name resolution of the calls it emits.* The version needed here is one level out:
**a declared guarantee is only as strong as the weakest party required to honour
it**, and for a browser action that party is a website that has never heard of you.

**So the language-level contribution is not the syscall.** It is that browser
automation forces the guarantee vocabulary to grow a value for *"dispatched,
outcome unobserved."*

---

## 5. Q2 — what is knowable on timeout

This is the question the rest of the design hangs off, and it has a precise answer.

### 5.1 The frame

> **A timeout is a fact about the caller. Never about the callee.**

It means *"I stopped waiting."* It asserts nothing about the remote system. Most
bugs in this class come from code reading a timeout as a statement about the world
— `except TimeoutError: return failed` — when it is a statement about your own
patience.

Hold that line and the knowable set is larger than "nothing."

### 5.2 Three things always knowable

1. **Your local prefix.** Everything durably recorded before dispatch. That an
   action with key K, target T, payload P was *intended* is local state, and it is
   certain. This is the real reason intent-before-dispatch is the whole design —
   not because it makes the action safe, but because it is the only part of the
   record that survives with full confidence.
2. **The time you quit.** Which is what preserves **bounded**. A timeout is a
   trade: durability's certainty for boundedness. The trade is fine as long as it
   is recorded *as* a trade.
3. **The dispatch phase reached.** The actionable one, and the one everyone throws
   away.

### 5.3 The phase ladder

The ambiguity window is narrower than "did it work?" implies. It sits strictly
between *bytes left the process* and *outcome observed*. Outside that window there
is certainty:

| what fired | knowable? |
|---|---|
| DNS failure, connection refused, TLS handshake failure | **definitely not dispatched** |
| connect timeout | almost certainly not dispatched — a SYN may have landed, nothing above it did |
| request write incomplete | not dispatched as a complete request |
| **read timeout after a full request write** | **genuinely ambiguous — the only true unknown** |
| explicit ack or observed result | **definitely landed** |

**This maps directly onto the browser case**, which is the most immediately useful
result here:

- `page.click()` timing out because *the selector never appeared* is
  **knowably not dispatched**. No click was issued.
- `page.click()` returning and then `waitForNavigation` timing out is the
  **ambiguous** one.

Playwright preserves that distinction in the exception type. A syscall surface
returning only `ok | timeout` **destroys** it — and that distinction is precisely
what decides whether a human has to look.

> **Consequence: the return of a mutating browser syscall must carry the phase
> reached, not an outcome verdict.**

---

## 6. The reframe — knowability is arranged, not discovered

> Knowability is not a property of the timeout. It is a property of what you
> arranged, in advance, to be able to ask afterwards.

The timeout need not be the last word. Ambiguity is resolvable by **read-back** — a
second, non-mutating observation of the world. Did the order appear? Is it in the
sent folder? Is the draft still a draft?

Read-back only works if the action left an **observable, uniquely attributable
trace**. A remote that honours an idempotency key hands you one. A website does
not, so it has to be manufactured: a nonce in a form field, a unique subject line,
a timestamp in the body.

Which means most unknowability in practice is **not a physics limit — it is
manufactured by never asking the question in advance.** That converts it from
something you suffer into something you design, and design discipline is exactly
what a compiler can require the declaration of.

**This changes what the mandatory key should be.** Not `execution_guarantee` —
that is a claim about a website's behaviour, which you are not entitled to make.
The declarable thing is the **reconciliation**: *how would I find out?*

- An action that declares one can be resolved after a crash.
- An action that declares `none` is one you have stated up front can only ever
  terminate at a human.

Both are honest. The compiler's job is that you cannot omit the choice. Same split
rule, better key — because it is a claim about your own code.

---

## 7. Q3 — why the residue is irreducible

Asked because the previous section's honest floor deserves a reason, not an
appeal to authority.

### 7.1 The proof

Two generals must attack simultaneously; messengers can be captured. Suppose a
protocol reaches agreement in a finite number of messages, and take the *shortest*
one, with N messages.

Message N can be lost. The protocol must still work, so the receiver's decision
cannot depend on receiving it — and the sender must act regardless, being unable to
know whether it arrived. So no one's behaviour depends on message N. Delete it:
an (N−1)-message protocol works, contradicting minimality.

Induct down. No finite protocol works, including zero.

### 7.2 What is behind the proof

**The acknowledgment has the same problem as the message.** An ack is a message; it
can be lost; so it needs an ack; which can be lost. There is no bottom to the stack.

Agreement formally requires *common knowledge* — I know, you know that I know, and
so on without bound. Each round of messaging buys exactly one level. Unreliable
asynchronous channels supply them one at a time, forever.

This is not a paradox in ordinary life only because common knowledge normally
arrives free from elsewhere: shared clocks, physical co-presence, a broadcast
everyone can see everyone else seeing. Remove those and it is gone.

### 7.3 The epistemic half, which is ours

The relevant case is not the coordination half but the observation half, and there
it is starker. On a read timeout you are in one of two worlds:

- **World A** — the request never arrived.
- **World B** — it arrived, executed, and the *response* was lost.

These produce **byte-identical observations at the caller.** Not hard to
distinguish — identical. No available measurement differs between them, because
everything that would differ is exactly what was lost.

> You are trying to learn a channel's contents through that channel.

### 7.4 Which is why there are exactly two escapes

Both work by moving the distinguishing evidence out of the lost message into
somewhere re-readable:

1. **A second channel.** Do not ask the broken path; ask the world. Query the DB,
   check the sent folder, reload the page.
2. **A pre-arranged trace.** Plant something before dispatch so the two worlds
   differ in the world's *durable state* rather than in a message. World A leaves
   no record bearing key K; World B leaves one.

Stripe's idempotency keys, transaction logs queryable by ID, LiteLLM's reconcile —
every real solution is one or both. There is no third.

### 7.5 And why the hard case is hard

It is the case where **neither escape is available**: no read-back path, or a
read-back that cannot *attribute* what it sees. That is the real content of "no
unique trace" — seeing one comment reading "+1" tells you nothing when four hundred
other people also posted "+1". Uniqueness buys attribution; attribution is what
makes read-back mean anything.

**The decisive detail: uniqueness must be arranged before dispatch.** It cannot be
added afterwards. Once the ambiguous timeout has happened, whatever was not planted
is not there.

So the browser is not harder physics than payments. It is the same physics with an
uncooperative counterparty — a website will not offer an idempotency key, so one
has to be smuggled into a field the site happens to echo back.

---

## 8. Q4 — two worlds, and what you actually do with them

The framing the question arrived at: *model the world where it did not arrive and
the world where it did, then choose.*

**Right instinct, one correction, and the correction is the design.**

> You do not choose. You **defer**.

Choosing requires evidence and at timeout there is none. Pick arbitrarily and you
have silently selected at-most-once or at-least-once while writing a fact into the
ledger you cannot support. Carry both worlds forward as a live state; let something
later collapse them.

### 8.1 Three strategies, ranked

1. **Collapse the worlds — make them the same world.** The strongest, and why
   idempotency is the industry's real answer. Idempotency is not *"I know it
   happened once"*; it is *"one and two are indistinguishable end states, so I no
   longer care which world I am in."* The ambiguity is not resolved, it is made not
   to matter. Retry becomes free. Where this can be engineered, everything below is
   unnecessary.
2. **Resolve the worlds — find out which one you are in.** Read-back through a
   second channel with an attributable trace. Costs a planted key and a query path,
   and works only when both exist.
3. **Defer — carry both until something resolves them, possibly a human.** The
   honest fallback: `unknown` as a terminal state, and an approval inbox.

Most systems implement only 3, badly — they retry blindly, which is assuming world
A while behaving as though they had confirmed it.

### 8.2 Where "choose" is legitimate

You choose the **policy**, in advance; not the **fact**, afterwards.

*"This action prefers a double-post to a lost post"* is a real, declarable,
per-action decision. It does not dissolve the at-most-once / at-least-once
trade — there is no third option — but it makes the trade explicit and attributable
to the person who declared it, rather than implicit in whoever wrote the retry loop.

And the ledger entry must match:

| written | verdict |
|---|---|
| *"I chose to assume it did not land"* | truthful |
| *"it did not land"* | a lie |

Identical behaviour; only one survives an audit. This is exactly the
`abandoned`-vs-`failed` distinction the codebase already draws — see §10.

---

## 9. Where the two-worlds framing leads

If a run carries a **set** of possible states rather than one state, a new question
becomes askable, and it is static:

> **Is this downstream step sound in both worlds?**

Some steps are **world-independent** — screenshot the page, read the order list,
anything non-mutating, anything whose own effect is idempotent — and can proceed
safely under an unresolved ambiguity. Others are not: *click submit again* is
correct in world A and catastrophic in world B.

That is a declarable property of a step, and the compiler can enforce that it was
declared. Which satisfies test 2 of the domain statement without needing the VM to
preempt anything.

**It is also strictly better than what exists today.** Right now `abandoned` is not
in `JOIN_ON_STATES` at all, so *no* step may proceed on it. That is the crude, safe
version of the same rule: everything is treated as world-dependent. The refinement
is letting a step earn the right to continue by declaring that it does not care
which world it is in.

An orchestration language that can say that would be doing something unusual. It is
also the part of this document least supported by existing code, which is why §12
lists it as open rather than §11 proposing it.

---

## 10. What already exists in the tree

Verified against `main` at `f7ab7ff`. This section is the reason the proposal is
small: most of the vocabulary is already present and already honest.

| thing | where | why it matters here |
|---|---|---|
| `abandoned` as a first-class task status | `src/nodus/orchestration/task_graph.py:81`, in `TASK_STATUSES` | this *is* `outcome: unobserved`, already named |
| `abandoned` absent from `JOIN_ON_STATES` | `task_graph.py:70` | no step can wait on it — an unresolved ambiguity structurally cannot be routed around; it terminates and reaches a human |
| `abandoned_agent_calls()` / `abandoned_agent_call_count()` | `src/nodus/services/agent_runtime.py:84`, `:90` | a bounded record (ring of 100 + total) of "we stopped waiting" |
| the #424 comment | `agent_runtime.py:59-63` | *"there is no reliable moment to observe such a thread finishing — that is the whole reason it had to be abandoned"* — §5.1's frame, already written down |
| `action` kind set closed at parse time | `src/nodus/frontend/parser.py:1194` | `Unsupported action kind: …` |
| `action` payload keys **unvalidated** | `parser.py:1180`, `:1192` — bare `parse_named_map_literal()` | the enforcement hook, still open |
| the same mechanism *with* an allowlist | `parser.py:740` — `error_keys=STEP_OPTION_KEYS` | making a payload key mandatory is a one-argument change |

**The naming is already epistemically honest at the point where it would be easiest
to lie.** `failed` is a claim about the callee. `abandoned` is a claim about the
caller. Nothing in the vocabulary currently overstates what the caller can know —
and adding `EXACTLY_ONCE` next to it would be the first thing that did.

---

## 11. Proposed shape

**This is not a work order.** The list is ordered by *confidence* — how sure this document is
that each item is right — not by sequence, and nothing below is implemented. The sequence is
§14.9's, and it puts three runtime-vocabulary gaps ahead of everything here. Items 1, 2 and 3
are further qualified by §14; read the pointer under each before acting on it.

1. **Do not declare `EXACTLY_ONCE` on a mutating browser action.** §4. The note's
   own §3 already says the achievable guarantee is at-most-once dispatch with
   recorded outcome; §6.1 should be corrected to match rather than the reverse.

   > **★ §14.1: the remedy is not available.** There is no honest label to substitute.
   > `register_syscall` validates against `{AT_LEAST_ONCE, EXACTLY_ONCE}` and `AT_MOST_ONCE`
   > has no occurrence in code. The corrected instruction is **declare no guarantee until the
   > vocabulary lands** — which is what the note has now been amended to, rather than to §3's
   > wording.
2. **Make a mutating action's return carry the dispatch phase**, not an outcome
   verdict. §5.3. The driver knows more than `ok | timeout` can express, and the
   distinction it knows is the one that decides whether a human is needed.

   > **★ §14.2: the runtime is currently the counter-example, and that makes this cheaper
   > than it reads.** `outbound_http.py:88-101` catches `httpx.HTTPError` — the base class —
   > collapsing `ConnectError` (knowably not dispatched) and `ReadTimeout` (the true
   > ambiguity) into one retry path. The library already preserves the distinction; the
   > boundary discards it. The fix is **narrowing an existing catch**, not building a phase
   > ladder.
3. **Make the declared, non-omittable key the reconciliation — "how would I find
   out?" — not the guarantee.** §6. `none` is a legal and honest answer; omission
   is not. Enforced at `parser.py:1180`/`:1192` with the mechanism already used at
   `:740`.

   > **★ §14.3: blocked, and blocked cheaply.** `unknown` has nowhere to be written —
   > `EffectRecord.status` is `pending | success | failed`, and parking an ambiguity at
   > `pending` would page an operator (`scheduler_service.py:565-577`). The column is
   > `String(32)` with no CHECK, so a fourth value needs no migration; filed as
   > `EFFECT-OUTCOME-UNKNOWN-1`. **The language cannot declare a reconciliation the runtime
   > cannot record**, so this item is downstream of that one — the two ends of one wire.
4. **If browser outcomes gain a tri-state, name the tuple once**, next to
   `TASK_STATUSES`, and drive a test off it. Three-of-four enumerations are this
   codebase's signature defect (#487, #518) and the fix that generalises is naming
   the set, not adding the case.
5. **Refuse the driver into the language, permanently.** The note's recommendation
   1 is right and the domain statement is the reason — "everything else is a
   library." Playwright/CDP session handling belongs behind the plugin ABI. The
   moment browser knowledge is in the compiler, the thesis is gone.
6. **Downgrade the note's §4 competitive claim.** *"The only browser automation in
   the field with effect semantics attached"* is an inferred result of one sweep;
   write it as *"this sweep found none."* Over-reach in exactly this register is
   what all three external audits caught last time.

---

## 12. What this does not settle

- **Whether world-independence is really declarable.** §9 is the most interesting
  idea here and the least supported. It needs a worked example where a step is
  provably sound in both worlds, and an answer to what happens when a
  world-independent step is followed by a world-dependent one — does the ambiguity
  propagate, and how far?
- **Whether the tri-state belongs in `TASK_STATUSES` or beside it.** `abandoned`
  is an *end-of-run conclusion* about a task. An unresolved browser outcome is a
  property of an *effect*, and a run may hold several. Reusing the tuple may be
  the right economy or a category error; this document does not decide it.
- **Where any of it lives.** The note targets `aindy-runtime`; the domain test
  applied here is nodus-lang's. The split rule says the language owns the
  declaration and the runtime owns the enforcement, which suggests the declaration
  vocabulary is nodus-lang's and the ledger, driver and sandbox tiers are not — but
  that is an inference from the rule, not a decision anyone has made.
  **★ Answered from the runtime side 2026-08-22 — see §14.5 for the allocation, and
  §14.3 for the constraint that decides the ordering: the language cannot declare a
  reconciliation the runtime cannot record, and the runtime currently cannot.**
- **Whether this is worth doing before #424's remaining half.** §5.1's frame is
  already written in `agent_runtime.py`; the abandonment mechanism it describes
  covers agent handlers only. A browser syscall is the second host-boundary surface
  with the same shape, and there is an argument for generalising the existing one
  before adding a consumer for it.
  **★ §14.9 offers an ordering and does not settle this.** It puts three runtime-vocabulary
  gaps first and the declaration fifth; #424's remaining half appears nowhere in it. Whether
  generalising the existing abandonment mechanism belongs before or alongside those three is
  still open.
- **Nothing here has been tested against a real browser.** Every claim about
  Playwright's exception types in §5.3 is from documentation and recollection, not
  from a run. That is the first thing to verify if any of this proceeds, and per
  the repo's own standard it should be verified before it is relied on.

---

## 13. The reason to build it, which the note undersells

The note calls browser automation *"the test case for the substrate."* That is
true and too small.

`00-domain-statement.md` §7 admits its own weakness:

> *"It is derived from what already works, which is a good way to be
> self-consistent and a poor way to be ambitious."*

Browser automation is the first candidate where the guarantee **provably cannot be
complete**. So it is the case that tests whether the domain statement can describe
a *partial* guarantee honestly, rather than only ratifying the complete ones that
already hold. Every surface admitted so far could be enforced fully or not at all.
This one cannot, and the vocabulary has never had to say so.

That is a better reason to build it than the feature.

---

## 14. The runtime side's answer

**Added 2026-08-22, written from `aindy-runtime` at `0a63719`, against source rather than
against either note.** §12 asks *"where does any of it live"* and says the split rule suggests
an answer nobody has made. This section makes the runtime half of it, and reports three things
that change §11.

Everything below is verified in `aindy-runtime` unless marked otherwise. Nothing here decides
a nodus-internal question — §12's first, second and fourth bullets are yours, and this section
does not touch them.

**Re-verified from this side 2026-08-22**, against `aindy-runtime` at `f06f5b3` — two docs-only
commits ahead of the `0a63719` this section was written from. Every file:line anchor above holds;
`syscall_registry.py:1923`, `effect_record.py:70-71`, `outbound_http.py:88-101` (base-class
`httpx.HTTPError` catch, `_RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}`, `max_retries=2`,
no method guard) and `compute_action_id` at `execution_gate.py:70` all read as described, and
`outbound_request` still has no caller under `AINDY/`.

Two anchors drifted and are corrected above: the stale-pending block is `scheduler_service.py:565-577`,
and `AT_MOST_ONCE` now has **11 repo-wide occurrences — all prose**, in `CLAUDE.md`,
`TECH_DEBT.md`, `IDEMPOTENCY_AUDIT.md` and one transcript. It is still **zero in Python**, which is
the claim that carries the argument. Worth noting how it moved: the commit that falsified
*"zero occurrences repo-wide"* is `f06f5b3`, the one that **files `EFFECT-OUTCOME-UNKNOWN-1`** — a
count going stale by being acted on, which is the failure mode this repo's own docs keep hitting.
State the claim as *"no occurrence in code"* and it survives being fixed.

### 14.1 §11.1 is right, and its remedy is not available

You caught the note contradicting itself: its §3 says the achievable guarantee is at-most-once
with a recorded outcome, its §6.1 says declare `EXACTLY_ONCE`. Correct. But the remedy —
*"§6.1 should be corrected to match §3"* — cannot be applied, because the runtime has no label
for §3's guarantee.

| vocabulary | where | values | missing |
|---|---|---|---|
| execution guarantee | `kernel/syscall_registry.py:1923` | `frozenset({"AT_LEAST_ONCE", "EXACTLY_ONCE"})` | **`AT_MOST_ONCE` — no occurrence in code** |
| effect outcome | `db/models/effect_record.py:70-71` | `pending` / `success` / `failed` | **no `unknown` — zero in the effect layer** |

`register_syscall` validates against that frozenset. So for a mutating browser action, one
label over-claims and the other under-claims, and **the honest one is unregisterable**. The
vocabulary gap is a level below where either document placed it: not *"the note picked the
wrong value"* but *"the set has no right value in it."*

★ Sharper than your §4 argues, too. You say an `EXACTLY_ONCE` label is success-shaped because
the website never agreed to it. **It is also not true of our own gate.** Measured in
`aindy-runtime` on 2026-08-19: under contention, 8 concurrent identical calls ran the handler
**twice**, degrading to `AT_LEAST_ONCE` with a warning. The label would misdescribe the
counterparty *and* the runtime. That is a third **column** for the §4 table, not a third row:
a party who can invalidate the label from *inside*, which neither #411 nor the website covers.

### 14.2 §11.2 lands cleanly — and the same defect already exists one layer down

*"Make a mutating action's return carry the dispatch phase, not an outcome verdict"* is
correct, and the runtime is currently the counter-example rather than the enforcer.

`platform_layer/outbound_http.py:88-101` catches **`httpx.HTTPError`** — the base class. That
one clause covers `ConnectError` (§5.3: **knowably not dispatched**) and `ReadTimeout` (§5.3:
**the only true ambiguity**) identically, wraps both in `TransientHTTPError`, and retries:
`max_retries=2` by default, **no method guard**, and `_RETRYABLE_STATUS` also retries
500/502/503/504 — which a POST may have committed before returning. That is §8.1's *"retry
blindly, which is assuming world A while behaving as though they had confirmed it"*, in
shipped code.

**This makes your §5.3 point twice over, and that is the useful part.** You observe that
Playwright preserves the phase distinction in its exception type and a `ok | timeout` surface
destroys it. httpx preserves the same distinction in *its* exception hierarchy, and our
boundary destroys it with a base-class catch. **Two libraries, both of which already know the
answer; two boundaries, both of which throw it away.** The fix in each case is *narrowing*,
not adding — which is a much cheaper claim than "add a phase ladder."

*Scope note, so this is not read as worse than it is:* `outbound_request` has **no caller in
`AINDY/`** — only its own tests. Email and registered connectors call
`authorized_external_call` directly, which does not retry. It is a documented client for
consumers, latent in-tree.

### 14.3 §11.3 is the best idea in the document, and the runtime cannot record its answer yet

*"Make the declared, non-omittable key the reconciliation — how would I find out? — not the
guarantee"* is right for the reason you give: it is a claim about your own code rather than
about a website's behaviour. Two things from this side.

**First, `unknown` has nowhere to be written.** The obvious shortcut — park the effect at
`pending` — is closed by code that already exists: the cleanup job warns on **any** pending row
older than an hour as *"may indicate stuck handlers; investigate action_ids"*
(`platform_layer/scheduler_service.py:565-577`). A correctly-recorded ambiguity would be
indistinguishable from a malfunction and would page someone. Your §10 observation that the
nodus vocabulary is *"already epistemically honest at the point where it would be easiest to
lie"* has an exact mirror here: ours is honest about `pending` meaning **in flight**, and
overloading it would be the first thing that lied.

**Second, fixing it is cheap.** `EffectRecord.status` is `String(32)` with no CHECK and no
Enum, and the completion helper assigns the string unvalidated — **a fourth value needs no
migration.** It is filed in `aindy-runtime` as `EFFECT-OUTCOME-UNKNOWN-1`, tied to an existing
entry (`EFFECT-PARTIAL-1`) that needs the same column widened for a different reason. One
change, two entries.

### 14.4 §11.5 is agreed without reservation, and §11.6 was already right

*"Refuse the driver into the language, permanently"* — agreed, and the runtime side has the
matching seam: a driver belongs behind `register_tool(..., isolation=<class>)`, which since
2026-08-19 can run a declared tool **out of process** with no fallback. The note's §2
"registration" row is the one row that needs no argument.

§11.6's instruction to downgrade the competitive claim to *"this sweep found none"* is correct
and should be applied to the note. This side has no evidence for the stronger claim either.

### 14.5 The answer to §12's "where does any of it live"

The split rule holds, and the allocation it implies is:

| piece | owner | why |
|---|---|---|
| *"how would I find out?"* as a **non-omittable declaration** | **nodus-lang** | §11.3. It is a property of the program, checked where the program is parsed. The compiler's job is that you cannot omit the choice. |
| **world-independence of a step** (§9) | **nodus-lang**, if it proves declarable | static, per-step, and enforceable without the VM preempting anything — your §12 rightly lists it as open |
| the **guarantee value** a syscall may declare | **runtime** | `register_syscall` validates it; the set is a runtime constant |
| the **outcome value** an effect may hold | **runtime** | it is a column in the runtime's ledger |
| **phase-preserving returns** at the host boundary | **runtime** | it is our exception handling that currently destroys the distinction (§14.2) |
| driver, sandbox tier, ledger, reconciliation surface | **runtime** | §11.5 |

**The load-bearing consequence: the language cannot declare a reconciliation the runtime
cannot record.** §11.3's key and `EFFECT-OUTCOME-UNKNOWN-1` are the two ends of one wire, and
the runtime end is the one that must exist first — a declaration whose only honest value is
unrepresentable downstream is `#411`'s failure mode again, one layer out. **The ordering that
falls out: runtime vocabulary first, language declaration second, driver last.**

### 14.6 Three derivations, not two

Your §3 records it as evidence that the domain statement is doing work that
reserve → call → reconcile was reached twice independently — from LiteLLM's spend governor and
from `00-domain-statement.md` §4.1.

It was reached a **third** time, earlier, in `aindy-runtime`, from Aider's Git discipline, and
filed as `EFFECT-PRECONDITION-1`. Its recorded conclusion:

> *the version identity is whatever the external system's own mechanism produces — record it,
> carry it, refuse on mismatch, **never reimplement it**.*

That is §7.4's pre-arranged trace, with the same warning attached. Money, distributed-systems
theory and version control converged on *plant an attributable trace before you act*.

★ **And the browser un-defers it.** That entry was deferred for one stated reason — *"it needs
an external mutable resource the runtime actually mutates, and there is no filesystem syscall
and no `sys.v1.repo.*`, correctly."* A browser is exactly that resource. So §13's argument
(browser automation is worth building because it tests whether the domain statement can
describe a *partial* guarantee) has a runtime-side twin: it is the first candidate that
supplies the precondition an existing deferral was waiting on.

### 14.7 Two corrections to the note that this side owes you

**The note's *"which is what an approval inbox is for, and you already have one"* is half
true, and the missing half is the relevant one.** `pending_approval` lives on `AgentRun`:
**pre-dispatch, run-level, whole-plan**. Reconciling an unknown outcome is **post-dispatch,
effect-level**. Different surface, different time, different granularity. Your §8.1 strategy 3
("defer — carry both until something resolves them, possibly a human") needs a surface that
does not exist here yet.

**The note's §5 emphasises the wrong row as achievable.** It calls `release_..._on_cancel`
*"the path most implementations skip — and the one that matters most here"*, and it is right
that it matters most — but the runtime cannot do it. `CANCEL-REACH-1` (open): cancellation is
durable and **never reaches an in-flight effect**. The four-phase LiteLLM pattern is three
phases here, and the missing one is the one the note singles out.

### 14.8 One constraint neither document states

`compute_action_id(action_type, input_payload, scope)` (`core/execution_gate.py:70-77`) is a
SHA-256 of the **request**. So a nonce planted to make an action attributable — §7.4's
manufactured trace, §7.5's "uniqueness must be arranged before dispatch" — must live *inside*
the payload, and therefore **changes the idempotency key**.

Consequence: the nonce must be minted **once**, before the first dispatch, and reused across
every retry. Mint it per attempt and dedup breaks silently while read-back still appears to
work. This is consistent with intent-record-first, but it rules out the obvious
implementation, and it is the kind of detail that is discovered by a duplicate post rather
than by review.

### 14.9 What this side thinks the ordering is

Three of the four blockers are runtime gaps that exist now, and a driver written today would
meet all three on its first mutating call:

1. **Effect status vocabulary** — no migration; settle with `EFFECT-PARTIAL-1`.
2. **Guarantee vocabulary** — `AT_MOST_ONCE`; the two must land together or a syscall can hold
   a status it may not declare.
3. **`CANCEL-REACH-1`** — the release phase.
4. **An effect-level reconciliation surface** — §8.1 strategy 3's missing home.
5. *Then* the declaration (§11.3), which is yours.
6. *Then* the driver, which is a library (§11.5).

§13 says the reason to build it is that it is the first surface where the guarantee provably
cannot be complete. Agreed — and from this side the sharper version is that **you do not need
a browser to start.** The vocabulary gap is already reachable from an ordinary outbound POST;
the browser only makes it unavoidable.
