# Real User Reality Audit

**Objective:** Determine what three categories of user can actually accomplish with
this system today, where they will succeed, and where they will fail.

Applies to: any language runtime at a point where real users could plausibly try it.

---

## Rules

- No vague statements. Every claim must be verifiable by trying it.
- "Mostly works" is not an answer. State exactly what succeeds and exactly what fails.
- Do not describe what the system is *designed* to do. Report what a user can *do*.
- If you cannot determine the answer without trying something, say so.

---

## User Type 1 — Script Author

A developer writing programs in the language directly. They know the syntax.
They want to express logic, call stdlib functions, handle errors, import modules.

### What succeeds today

List specific things the script author can reliably do:
(Examples: write a function, call stdlib X, import from Y, spawn a coroutine,
handle a try/catch, pass data between modules)

### What struggles today

List specific things that work sometimes or require non-obvious workarounds:
(Examples: multiline expressions, closures over mutable state, integer arithmetic,
print with multiple arguments)

### What breaks today

List things that produce incorrect output, a confusing error, or silent failure:
(Examples: a specific type coercion, a specific standard library edge case, a pattern
that parses but produces wrong output)

### First succeeding use case (specific)

The exact program a new user can write and run in under 10 minutes that does
something genuinely useful.

### First blocking failure (specific)

The exact thing a new user will try that will fail without a clear error message.

---

## User Type 2 — Library / Tool Author

A developer writing a reusable library in the language, or writing extensions
that register host functions for other scripts to call.

### What succeeds today

What can a library author reliably publish and have others use?

### What struggles today

What patterns require workarounds, undocumented APIs, or internal knowledge?

### What breaks today

What cannot be done without forking the runtime or using unsupported internals?

### First succeeding use case (specific)

The specific library pattern that a competent user can ship in a reasonable amount of time.

### First blocking failure (specific)

The specific thing a library author will hit that has no solution.

---

## User Type 3 — Embedder

A developer embedding the runtime into a host application (server, agent framework,
data pipeline). They need to start the runtime, execute scripts, pass data in and
out, observe errors, and clean up.

### What succeeds today

What embedding patterns work reliably?

### What struggles today

What embedding patterns require reading source code or working around gaps?

### What breaks today

What patterns fail silently or produce incorrect host-side behavior?

### First succeeding use case (specific)

The exact embedding call sequence that a new embedder can get working in under
an hour from documentation alone.

### First blocking failure (specific)

The exact embedding scenario that fails and cannot be worked around without modifying
the runtime.

---

## Cross-Cutting Findings

Issues that affect all three user types:

- Documentation gaps (things that are true but not written down)
- Error messages that don't point at the source of the problem
- Concepts where the mental model implied by the documentation does not match actual behavior

---

## Summary Table

| | Script Author | Library Author | Embedder |
|---|---|---|---|
| Can reliably do | | | |
| First success | | | |
| First blocker | | | |
| Overall friction | Low / Med / High | Low / Med / High | Low / Med / High |

---

**Rules:**
- All claims in this audit are falsifiable by running code.
- If a user type cannot be meaningfully tested, say why.
- Do not assume the user has read the source code.
