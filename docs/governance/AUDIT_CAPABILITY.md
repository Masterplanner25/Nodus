# System Capability Audit

**Objective:** Classify this language runtime along five axes to produce an accurate,
evidence-based picture of what it actually is — not what it aspires to be.

Applies to: any language runtime at a point where the feature set is substantially
defined.

---

## Classification Axes

Score each axis on a 1–5 scale. Evidence must be specific.

---

### Axis 1 — Execution Capability

What class of programs can be expressed and executed?

| Level | Description |
|-------|-------------|
| 1 | Expression evaluation only; no control flow, no state |
| 2 | Scripting: sequential execution, conditionals, loops, functions |
| 3 | Structured programming: modules, imports, error handling, closures |
| 4 | Concurrent / async: coroutines, channels, task scheduling |
| 5 | Distributed / orchestrated: persistent workflows, event-driven resumption, cross-process coordination |

**Score:** ___ / 5

**Evidence:** Name the specific features that justify this score. If the score is
limited by a missing feature, name it.

---

### Axis 2 — Reliability

What are the guarantees around correctness and predictability?

| Level | Description |
|-------|-------------|
| 1 | No guarantees; errors may be silent or cause undefined behavior |
| 2 | Errors surface predictably; no undefined behavior in user code |
| 3 | Resource limits enforceable; execution is bounded; cleanup on error |
| 4 | Persistent execution with durability guarantees; crash recovery |
| 5 | Formal correctness properties; verified invariants; audit trail |

**Score:** ___ / 5

**Evidence:** What is the highest reliability guarantee the runtime makes? What breaks it?

---

### Axis 3 — Autonomy

Can the runtime drive execution with minimal host involvement after setup?

| Level | Description |
|-------|-------------|
| 1 | The host must drive every step |
| 2 | The runtime drives execution of a single script to completion |
| 3 | The runtime manages concurrent tasks and their scheduling |
| 4 | The runtime can suspend, persist, and resume across process restarts |
| 5 | The runtime can orchestrate long-horizon workflows with external event triggers |

**Score:** ___ / 5

**Evidence:**

---

### Axis 4 — Developer Leverage

What is the ratio of capability to complexity for a developer using this runtime?

| Level | Description |
|-------|-------------|
| 1 | High complexity; limited capability over writing host-language code directly |
| 2 | Useful shorthand for simple cases; breaks down at moderate complexity |
| 3 | Clear advantage for its target use case; onboarding friction is low |
| 4 | Significantly reduces time-to-working-system for non-trivial programs |
| 5 | Enables programs that would be substantially harder in the host language |

**Score:** ___ / 5

**Evidence:**

---

### Axis 5 — Bootstrap Readiness

Can the language describe its own toolchain? (See also: `AUDIT_RUNTIME_READINESS.md §Bootstrap Readiness`)

| Level | Description |
|-------|-------------|
| 1 | Cannot yet express a tokenizer for its own syntax |
| 2 | Can express a tokenizer; parser would require missing features |
| 3 | Can express a parser; compiler output requires missing primitives |
| 4 | Can express a compiler; VM loop requires missing features |
| 5 | Full self-hosting is feasible with current feature set |

**Score:** ___ / 5

**Evidence:** Name the one feature that is the hard gate on the next stage.

---

## Overall Capability Profile

```
Execution:    [1][2][3][4][5]
Reliability:  [1][2][3][4][5]
Autonomy:     [1][2][3][4][5]
Dev Leverage: [1][2][3][4][5]
Bootstrap:    [1][2][3][4][5]
```

---

## Ceiling

What is the most complex real program that can be written in this language today?
Describe it in terms of lines of code, concurrency, data complexity, and external
integrations. This is the current ceiling, not the intended ceiling.

---

## Constraint

The single bottleneck limiting capability growth. One sentence. Name the specific
missing feature, behavioral gap, or design decision that, if fixed, would raise the
most axes simultaneously.

---

## System Class

Given the profile above, what is this system most accurately described as?

Pick one:

- **Expression evaluator** — Axes 1–2 only; not a general-purpose language
- **Scripting language** — Axes 1–3; suitable for automation and glue code
- **Embedded DSL** — Optimized for a specific domain; limited general use
- **Orchestration runtime** — Axes 1–4; suitable for agent/workflow coordination
- **General-purpose runtime** — All five axes ≥ 3; usable for arbitrary programs

**Classification:** ___

---

**Rules:**
- Scores must be supported by a specific named feature, file, or behavior.
- A score of 5 requires evidence of the level, not just the absence of obvious gaps.
- Do not score based on roadmap. Score what exists.
