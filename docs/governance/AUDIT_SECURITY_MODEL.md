# Security Model Audit

**Objective:** Establish the factual security posture of this language runtime —
where enforcement lives, how it is applied, whether it can be bypassed, and
what the failure mode is when it is absent.

Applies to: any language runtime that executes untrusted or partially-trusted code.

---

## Rules

- Describe what EXISTS. Do not suggest improvements or redesigns.
- Every enforcement claim must name the module, function, or mechanism that
  enforces it.
- "Partial" requires an explanation of what is enforced and what is not.
- YES / PARTIAL / NO at the end of each section.

---

## Section 1 — Sandbox Inventory

List every enforcement boundary that exists in the runtime. For each:

- What does it prevent?
- Where in the code is it enforced? (file:function or file:line)
- Does it apply in CLI mode, embedded mode, or both?
- Can it be disabled by the script itself?

Common categories (add or remove as appropriate):

| Boundary | What it prevents | Where enforced | CLI / Embedded / Both | Script-bypassable |
|----------|-----------------|----------------|----------------------|-------------------|
| Filesystem access | | | | |
| Network access | | | | |
| Subprocess invocation | | | | |
| Environment variable read | | | | |
| Memory/CPU limits | | | | |
| Import restrictions | | | | |
| Host function access | | | | |

---

## Section 2 — Auth Flow Trace

Trace the path of a request from entry point to execution, for each mode.

### CLI mode

```
nodus run script.nd
→ [step 1: what happens here?]
→ [step 2]
→ [VM begins executing]
→ [first builtin call]
```

At each step: is there any authentication or authorization check? Name it or note its absence.

### Embedded mode

```
NodusRuntime.run_source(code) [or equivalent]
→ [step 1]
→ [VM begins executing]
→ [host function call]
```

At each step: is there any authentication or authorization check? Name it or note its absence.

### Serve / HTTP mode (if applicable)

```
POST /run
→ [authentication layer?]
→ [authorization check?]
→ [code string submitted to VM]
```

Is the HTTP endpoint authenticated by default, or does auth require explicit configuration?

---

## Section 3 — Layer Classification

For each security concern, state where responsibility lives.

| Concern | Language/VM | Stdlib | Embedding API | Host application | Not enforced |
|---------|-------------|--------|---------------|-----------------|--------------|
| Filesystem sandboxing | | | | | |
| Network restrictions | | | | | |
| Request authentication | | | | | |
| Tenant isolation | | | | | |
| Capability escalation prevention | | | | | |
| Audit logging | | | | | |
| Resource exhaustion prevention | | | | | |

---

## Section 4 — Violations and Gaps

For each of the following, state: enforced / bypassable / not present.

If bypassable, describe the bypass path (not to enable it, but to document the gap).

- Can a script read files outside a declared allowed path?
- Can a script open a network connection the host did not configure?
- Can a script invoke arbitrary subprocesses?
- Can a script exhaust memory without the host being able to stop it?
- Can a script run indefinitely without the host being able to stop it?
- Can a script read or modify other scripts' runtime state?
- Can a host function registration be overridden by a script?

For each gap: is it documented? Is there a known workaround?

---

## Section 5 — User / Tenant Context Propagation

How does identity travel through the execution system?

- Is there a concept of a "current user" or "current tenant" in the runtime?
- If so, where is it set and where can it be read?
- Can a script query its own execution context (who am I, what am I allowed)?
- Is identity propagated into async/coroutine execution?
- Can identity be spoofed by a script?

**Summary:** YES (full propagation) / PARTIAL (propagated but escapable) / NO (no identity concept in runtime)

---

## Section 6 — Enforcement Consistency

Is the same enforcement applied uniformly across all entry points?

- Are sandbox rules identical for CLI, embedded, and serve modes?
- Are there any features available in one mode but not another that create a
  privilege difference?
- Does a difference in default configuration between modes create a security gap?
  (e.g. sandbox off by default in embedded, on by default in CLI)

List any inconsistencies found.

---

## Section 7 — Audit and Observability

Can a host reconstruct what happened during a script execution from logs or trace data?

- Is there an execution trace that records which builtins were called?
- Is there a log of which filesystem paths were accessed?
- Is there a record of which host functions were invoked and with what arguments?
- Can the host receive a callback on every capability use (hook pattern)?

**Summary:** YES / PARTIAL / NO

---

## Current State Summary

Answer for each: **YES / PARTIAL / NO**

| Question | Answer |
|----------|--------|
| Safe to run untrusted scripts by default? | |
| Auth required before any code executes (serve mode)? | |
| Filesystem sandbox enforced without host configuration? | |
| Network access restricted without host configuration? | |
| Resource exhaustion (CPU/memory) bounded by default? | |
| Tenant isolation possible with current API? | |
| All enforcement consistent across CLI, embedded, serve? | |
| Security gaps documented publicly? | |

---

## Final Verdict

One sentence: What is the honest security posture of this runtime for an embedder
who follows the documented configuration but does not read the source?

---

**Rules:**
- Do not suggest improvements.
- PARTIAL requires: what is enforced, what is not, and where the gap is.
- Source code locations must be specific enough that a reader can verify them.
