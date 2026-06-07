# End-to-End Architecture Audit

**Objective:** Determine whether the language runtime works correctly, consistently,
and reliably from source text to final output — and whether the layers between are
sound enough to be the foundation of a production system.

Applies to: any language runtime with a compiler, VM, and embedding API.

---

## 1. Pipeline Map

Trace the actual execution path end-to-end. Be specific — name real modules.

```
Source text
→ Lexer         (tokenization)
→ Parser        (AST construction)
→ Compiler      (bytecode emission)
→ VM / Executor (instruction dispatch, scheduler)
→ Builtins      (stdlib, host functions)
→ Output / Error
```

For each stage: what module owns it, what its input/output contract is, and
what happens if it fails.

---

## 2. Layer Integrity

Identify the layers the runtime declares (e.g. frontend / compiler / VM / stdlib /
embedding API) and evaluate whether boundaries are real.

- Does the VM import parser types?
- Does the compiler depend on runtime state?
- Does the stdlib assume things about the VM internals?
- Does the embedding API bypass the normal execution path?

**Verdict:** Clean | Minor violations | Significant coupling

---

## 3. Execution Guarantees

- Does every execution reach a terminal state (value, error, or timeout)?
- Can a script run forever without the host being able to stop it?
- Is the error model consistent — does a runtime error always surface the same way?
- Are stack overflows, infinite loops, and memory exhaustion handled or defined?
- Is step/instruction counting deterministic?

---

## 4. State Consistency

- Is VM state fully reset between executions, or can state leak between runs?
- If the runtime supports coroutines or concurrent execution: is scheduler state
  consistent on entry and exit?
- If the runtime supports persistent state (workflow graphs, checkpoints): are
  writes atomic? Can a crash leave state corrupt?
- Is user/tenant context isolated from global VM state?

---

## 5. Module and Import System

- Is import resolution deterministic given the same inputs?
- Can circular imports occur? If so, what happens?
- Is the stdlib isolated from user code, or can user code shadow stdlib symbols?
- Are import errors surfaced at load time or silently deferred?

---

## 6. Embedding API Integrity

- Is there a single, stable entry point for embedding (e.g. `NodusRuntime`)?
- Can an embedder accidentally bypass sandbox or security constraints?
- Are host-injected functions (register_function, tool_registry) isolated from
  the language's own namespace?
- Does the embedding API behave identically to the CLI entry point, or are there
  silent behavioral differences?

---

## 7. Async / Concurrency System

If the runtime has coroutines, async execution, or a task scheduler:

- Is the scheduler preemptive or cooperative? Is this documented and enforced?
- Can a runaway coroutine starve others?
- Is `spawn` / `run_loop` behavior consistent between embedded and CLI modes?
- Are coroutine resource limits enforced?

---

## 8. Failure Handling

For each failure class, answer: is it caught, is it surfaced, is it recoverable?

| Failure | Caught | Surfaced | Recoverable |
|---------|--------|----------|-------------|
| Parse error | | | |
| Compile error | | | |
| Runtime error (user code) | | | |
| Builtin error | | | |
| Timeout / step limit | | | |
| Host function exception | | | |
| Import failure | | | |
| VM internal error | | | |

---

## 9. Observability

- Can you reconstruct what a script did from logs or trace output alone?
- Does the stack trace in errors point to the right source location?
- Is bytecode introspectable (disassembly, opcode dump)?
- Is there a way to observe scheduler behavior (coroutine scheduling, task graph)?
- Can an embedder attach an observer without modifying the runtime?

---

## 10. Structural Risks

Identify:

- Tight coupling between non-adjacent layers (e.g. builtin → parser)
- Shared mutable state accessed without synchronization
- Circular dependencies (A imports B imports A)
- God objects or modules with unclear ownership
- Public APIs that expose internal types

---

## 11. Production Readiness

Answer for each: **YES / PARTIAL / NO**

- Safe to execute untrusted code?
- Safe to embed in a long-running server?
- Safe to use in multi-tenant context?
- Errors always visible to the host?
- Resource limits enforceable by the host?

---

## 12. Top 5 Weaknesses

The most critical issues found. One sentence each.

---

## 13. Top 5 Strengths

What is architecturally sound. One sentence each.

---

## 14. Final Verdict

One paragraph: Is this architecture sound enough to be the foundation of a
production language runtime?

---

**Rules:**
- Be factual. Reference real module names and file paths.
- Do not suggest features or redesigns.
- Do not assume intent — evaluate what exists.
- If something is not present, say it is absent, not that it should be added.
