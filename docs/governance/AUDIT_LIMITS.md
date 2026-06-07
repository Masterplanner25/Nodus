# System Limits and Leverage Boundary Audit

**Objective:** Define the precise boundary where this language runtime stops being
useful — in terms of workload size, program complexity, concurrent users, and
automation depth — and identify the single most actionable path to extending it.

Applies to: any language runtime where real workloads are being considered.

---

## Rules

- Every limit must be either measured or derivable from source code inspection.
- "It depends" is acceptable only when followed by: depends on what, and what are the two extremes.
- Each section ends with: **hard boundary**, **root cause**, and **upgrade path**.

---

## 1. Maximum Workload

What is the largest single program execution the runtime can handle before it
degrades or fails?

Measure or estimate:
- Maximum source file size before the compiler slows meaningfully
- Maximum number of instructions before timeout mechanisms fire
- Maximum data structure size (list, map) before the VM slows
- Maximum recursion depth before stack overflow

| Metric | Measured value or estimate | Failure mode |
|--------|---------------------------|--------------|
| Source file size | | |
| Instruction count | | |
| Max list/map size | | |
| Max recursion depth | | |

**Hard boundary:** ___  
**Root cause:** ___  
**Upgrade path:** ___

---

## 2. Maximum Program Complexity

At what point does program structure become unmanageable in this language?

- Maximum number of modules before import resolution degrades
- Maximum number of functions before symbol resolution becomes a bottleneck
- Are there syntax or semantic limits on program structure (e.g. max nesting depth,
  max function parameters, max closure capture count)?
- Is there a maximum number of workflow steps? Workflow graph size?

| Metric | Limit | Behavior at limit |
|--------|-------|------------------|
| Module count | | |
| Functions per module | | |
| Nesting depth | | |
| Workflow step count | | |

**Hard boundary:** ___  
**Root cause:** ___  
**Upgrade path:** ___

---

## 3. Maximum Concurrent Users / Scripts

What is the concurrency ceiling, both within a single runtime instance and across
multiple instances?

- Maximum coroutines schedulable concurrently in a single runtime
- Maximum concurrent runtime instances in a single process
- What happens when concurrency exceeds the limit — silent degradation, error, crash?
- Is the runtime thread-safe across multiple instances? (e.g. shared global state)

| Metric | Limit | Behavior at limit |
|--------|-------|------------------|
| Coroutines per runtime | | |
| Runtime instances per process | | |
| Thread safety | Thread-safe / Unsafe / Not tested | |

**Hard boundary:** ___  
**Root cause:** ___  
**Upgrade path:** ___

---

## 4. Maximum Automation Depth

How far can automation go before it requires the host to take over?

- Can a script run, complete, and trigger a follow-on script without host involvement?
- Can the runtime self-schedule work across time (e.g. "run this in 30 minutes")?
- Can the runtime persist state across process restarts without application code?
- Is there a durable event queue, or does event handling require the host?
- What is the maximum duration of a single workflow from start to completion?

| Capability | Available in language | Requires host code |
|------------|----------------------|-------------------|
| Self-scheduling | | |
| Cross-restart persistence | | |
| Event-driven resumption | | |
| Long-duration workflows | | |
| Autonomous retry on failure | | |

**Hard boundary:** ___  
**Root cause:** ___  
**Upgrade path:** ___

---

## 5. Leverage Boundary

At what point does using this language stop saving time compared to writing the
equivalent in the host language directly?

Consider:
- Simple scripting: what is the minimum program complexity where the language adds value?
- Moderate complexity: does the language continue to add value as program complexity grows?
- High complexity: at what point is the language overhead (learning, debugging, tooling)
  greater than the benefit?

**Where the language adds the most leverage:** (one sentence)

**Where the language stops adding leverage:** (one sentence)

**The program type that is hardest to write in this language despite being within its
stated scope:** (one sentence)

---

## Summary: Hard Limits Table

| Dimension | Hard Limit | Root Cause | Upgrade Path |
|-----------|-----------|------------|--------------|
| Workload | | | |
| Complexity | | | |
| Concurrency | | | |
| Automation depth | | | |
| Leverage ceiling | | | |

---

## Single Most Actionable Upgrade

If one change could raise the most limits simultaneously, what is it?

Name: the specific limit it removes, the specific mechanism that currently causes
the limit, and the specific change that would remove it.

Do not list multiple options. Identify the one highest-leverage change.

---

**Rules:**
- All limits must be grounded in code, measurement, or a specific design decision —
  not general expectations for this class of system.
- If a limit has not been measured, say "estimated from inspection of [file/mechanism]."
- If a limit is configurable, state the default and the maximum configurable value.
