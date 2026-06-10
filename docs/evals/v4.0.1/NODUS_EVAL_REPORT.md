# Nodus v4.0.1 — Post-Publish Eval Report

**Eval date:** 2026-06-10  
**Version:** v4.0.1 (PyPI, POST-PUBLISH)  
**Composite score:** 6.1 / 10

---

## TL;DR

v4.0.1 is a mixed release. The mechanical additions — compound assignment,
multiline expressions, and the six `std:math` bit operations — work correctly
and are genuine improvements. However, two of the three headline features ship
with critical defects: `@exactly_once` is completely broken (wrong idempotency
logic and discarded return values), and the `allowed_commands` subprocess sandbox
allowlist is not enforced at all. These are not edge-case failures; they are
first-call failures. Code depending on either feature does not behave as
documented. Roll these findings into v4.0.2 scope.

---

## Findings by severity

### CRITICAL

**BUG-401-002a/b — @exactly_once completely non-functional**

The `@exactly_once` decorator ships broken on two axes:
1. Idempotency is not enforced. A second call with identical arguments re-executes
   the function body. The core purpose of the decorator is defeated.
2. The return value is always `nil`. The function body executes (when it
   executes at all) but its result is discarded. Every `@exactly_once` call
   silently returns `nil`.

This is the most impactful finding. Any application using `@exactly_once` for
idempotent side-effects (email sends, payment submissions, webhook deliveries)
will double-execute silently with no indication of the failure.

**Root cause hypothesis:** The `effect_resolve()` action-ID computation is not
matching across calls (producing a different ID each time, so every call looks
"new"). Additionally, the compiler lowering for the return value does not thread
the function result back through `effect_complete()` to the call site.

**BUG-401-004 — allowed_commands sandbox not enforced**

`NodusRuntime(allowed_commands=["python"])` permits `sub.run(["git"])` to execute
successfully and return real output. The allowlist has no effect. This is a
security regression: any application relying on this flag to sandbox subprocess
access in an embedded context is fully exposed.

`allow_env=False` works correctly, so the pattern of capability-gating is sound
— the `allowed_commands` path specifically is broken.

### HIGH

**BUG-401-001 — @retry silently skips function body when nodus-retry missing**

Without `nodus-retry` installed, a `@retry`-decorated function body executes
zero times and returns a `dependency_error` map. The user gets no compile-time
or import-time indication that the package is missing. The fix is to fail early
with a clear message rather than silently bypassing the function.

### MEDIUM

**BUG-401-003 — Trailing comma in multiline list**

`[1i, 2i,]` is a syntax error. Every mainstream language supports trailing
commas in collection literals. Generated code (from templates or AI systems)
frequently emits trailing commas. This creates friction that compounds as the
language gets used in code-generation pipelines.

**BUG-401-006 — event_sinks captures no events**

The `event_sinks` API accepts callables but they are never invoked — not for
simple scripts, not for workflow execution. The wiring is either connecting to
the wrong bus instance or the event bus is not actually emitting anything.
This makes the API non-functional for observability use cases.

**BUG-401-008 — channel(maxsize=N) notation wrong in docs**

The actual API is positional: `channel(2i)`. The named-argument form
`channel(maxsize: 2i)` is a parse error. All internal documentation should
be updated to use the correct Nodus call syntax.

### LOW

**BUG-401-005** — `allowed_hosts` untestable without optional `[http]` extra.
Error message is good; just a docs gap.

**BUG-401-007** — `_last_vm` is still public despite changelog claim.

---

## What works well

- **Compound assignment (`+=`, `-=`, `*=`, `/=`):** All 7 forms correct across
  variable targets, index targets, record fields, and map entries. Integer/float
  type rules preserved. Error for undefined target is clear.
- **Multiline expressions:** Function calls, list literals, and map literals
  spanning lines work. Nested multiline works. (Trailing comma is the one gap.)
- **std:math bit operations:** All six new functions return correct results for
  all tested inputs. Clean addition.
- **Bounded channels (positional API):** `channel(2i)` enforces capacity.
  Overflow error message includes the maxsize. Negative capacity correctly
  rejected.
- **Unknown annotation at compile time:** `@nonexistent` gives a useful
  `Syntax error: Unknown annotation` at compile time.
- **allow_env=False:** Correctly blocks all env access with a clear
  `SandboxError` message.
- **get_execution_stats():** Returns `{instructions_executed, coroutines_spawned}`.
  Plausible counts.
- **clear_shared_state():** Works as a classmethod. Post-clear runtime
  creation and execution works.
- **v4.0.0 regression:** No regressions found in the core language, type model,
  standard library, workflow DSL, or goal DSL.

---

## Per-audience verdicts

**The AI agent author:** Compound assignment, multiline, and bit ops are solid
additions that an LLM can correctly generate from the docs. `@exactly_once` and
`@retry` are unusable until fixed — any AI-generated code using them will fail
silently. The `allowed_commands` failure means AI-authored embedded scripts have
no subprocess sandbox. Net: do not rely on annotations or `allowed_commands`
in AI-generated code yet.

**The human adopter:** Install experience is clean. The three mechanical features
(compound assignment, multiline, bit ops) add genuine ergonomics. Error messages
are good for known paths. The annotation system looks promising but isn't ready
for production use.

**The embedder:** `get_execution_stats()`, `clear_shared_state()`, and
`coroutine_timeout_ms` work. `event_sinks` is wired but silent. `allowed_commands`
does not work — do not use it to sandbox subprocess access in production. Use
`allow_subprocess=False` as a complete block if subprocess sandboxing is critical.

**The v4.0.0 upgrader:** Drop-in patch. The core language is stable and
no regressions were found. New features are additive. Safe to upgrade if you
don't depend on `@exactly_once`, `@retry`, or `allowed_commands`.

---

## v5 scope recommendations (from this eval)

Priority order:

1. **Fix `@exactly_once`** — both idempotency (action ID matching) and return
   value threading. This is the most impactful broken feature.
2. **Fix `allowed_commands` enforcement** — verify the flag propagates from
   `NodusRuntime.__init__` into the subprocess builtin's invocation path.
3. **Fix `@retry` dependency detection** — fail at annotation compile time or
   provide a no-retry fallback when `nodus-retry` is absent.
4. **Fix `event_sinks`** — verify the bus wiring is connecting to the VM's
   actual event bus, not a separate instance.
5. **Add trailing comma support** in multiline list/map/call literals.
6. **Update `channel()` docs** to show positional API (`channel(2i)` not `channel(maxsize=N)`).
7. **Deprecate `_last_vm`** with a proper warning pointing to `get_execution_stats()`.

Items 1–4 are strong candidates for a v4.0.2 patch release given their severity.
Items 5–7 are polish appropriate for v5 or v4.1.
