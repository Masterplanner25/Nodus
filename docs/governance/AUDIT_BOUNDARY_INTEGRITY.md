# Boundary Integrity Audit

**Objective:** Determine whether the runtime/compiler core is clean — containing only
infrastructure — or whether product logic, domain concepts, or application-specific
behavior have leaked into layers that should be neutral.

Applies to: any language runtime with declared internal layers (frontend, compiler,
VM, stdlib, embedding API).

---

## What "contamination" means

A clean runtime layer contains only things that are true regardless of what programs
are written in the language. Contamination is any code that:

- Names a specific domain (e.g. "agent", "task", "approval", "tenant", "user")
- Assumes a specific deployment topology (e.g. "database", "queue", "HTTP server")
- Makes decisions on behalf of the user program that the user program should make
- Encodes policy that belongs in the application layer, not the language layer

---

## Section 1 — Dependency Direction

Identify the declared layers (e.g. lexer → parser → compiler → VM → builtins →
stdlib → embedding). For each real import in the codebase, verify the direction.

- Does any lower layer import from a higher layer?
- Does the VM import from stdlib?
- Does the compiler import from the embedding API?
- Does the lexer import from the VM?

List any violations found. Format: `[lower_module] imports [higher_module] — reason this matters`.

**Verdict:** Clean | Minor upward import | Structural inversion

---

## Section 2 — Domain Language in Core

Search the compiler and VM source for domain-specific nouns.

Scan for: identifiers, class names, function names, variable names, docstrings, and
comments that name application concepts rather than language concepts.

Language-neutral terms (acceptable in core): `value`, `frame`, `opcode`, `scope`,
`token`, `node`, `register`, `coroutine`, `error`, `result`, `type`.

Domain-specific terms (signal contamination if found in core): names of the
application's problem domain, proper nouns from any specific industry or use case,
names that would not appear in the CPython or V8 source.

List any found: `[identifier]` in `[file:line]` — domain contamination? YES/NO — why.

**Verdict:** None found | Isolated in stdlib | Present in VM or compiler

---

## Section 3 — Runtime Neutrality

Does the runtime behave differently based on deployment context in ways that are
not controlled by the script or the embedding API?

- Does the VM read environment variables that alter execution semantics?
- Does any builtin have behavior that depends on the host machine's state in
  undocumented ways?
- Does behavior differ between CLI and embedded mode in ways not exposed to scripts?
- Are there hardcoded paths, URLs, or service names in the core runtime?

List any found.

**Verdict:** Fully neutral | Context-sensitive with documented escapes | Implicit ambient dependency

---

## Section 4 — Data Model Purity

Does the VM's data model (types, values, frames) contain application-specific fields?

- Do value types carry metadata that only makes sense in one deployment context?
- Does the execution frame carry fields that belong in application state?
- Are there special-cased types that are not first-class language types?

**Verdict:** Pure | Minor special-casing | Structural leakage

---

## Section 5 — API Contract Stability

Does the embedding API expose internal types that callers then depend on?

- Does the public embedding API return VM-internal objects (frames, opcodes, internal
  value wrappers)?
- Are there methods on the public API that only make sense for a specific host
  application pattern?
- Is any method marked `_private` but used outside its module?

List any violations.

**Verdict:** Clean surface | Leaky internals | No real boundary

---

## Section 6 — Plugin / Extension Boundary

If an extension/plugin system exists:

- Can a plugin read or mutate VM-internal state directly?
- Does the plugin API expose things that should be internal (frame stack, opcode
  stream, GC roots)?
- Is there a documented contract for what plugins may access?
- Is there a version marker that lets the runtime warn on ABI mismatch?

**Verdict:** Clean contract | Overly broad access | No boundary

---

## Section 7 — Legacy / Dead Infrastructure

Identify code that exists only for historical reasons and now represents a liability.

- Are there deprecated APIs still called from within the codebase?
- Are there two implementations of the same thing where only one should exist?
- Are there files or modules with no callers?
- Are there TODO/FIXME comments that reveal known but unresolved design debt?

Count: ___ deprecated call sites, ___ orphan modules, ___ unfixed TODOs in core.

**Verdict:** Acceptable | Needs scheduled removal | Blocking clean separation

---

## Section 8 — Capability Ownership

Who decides what a script is allowed to do?

- Is capability enforcement (filesystem access, network, subprocess) in the core,
  in the embedding API, in the stdlib, or in the application?
- Is it possible for a script to escalate past the enforcement layer?
- Is the same capability enforced consistently across CLI and embedded modes?

Describe exactly where enforcement lives and whether it is escapable.

**Verdict:** Correctly owned | Partially enforced | Enforcement absent or bypassable

---

## Violations Table

Summarize all violations found across all sections.

| Location | Section | Contamination | Severity (Low/Med/High/Critical) |
|----------|---------|---------------|----------------------------------|
| | | | |

---

## Risk Summary

- **Refactoring risk:** Is the contamination incidental (easy to extract) or structural
  (would require redesigning the layer boundary)?
- **Stability risk:** Do embedders depend on the leaked types/behavior? Removing them
  would be a breaking change?
- **Security risk:** Does any contamination create a path for capability escalation?

---

## Final Classification

| Classification | Criteria |
|----------------|----------|
| **Clean runtime** | No contamination in core layers; any domain concepts confined to optional stdlib modules |
| **Minor residual coupling** | Domain names or concepts found in stdlib only; core layers clean |
| **Significant contamination** | Domain concepts in VM or compiler; embedding API exposes internal types |
| **Product masquerading as runtime** | Core layers are organized around a specific application; not separable without a rewrite |

**Classification:** ___

**Recommended priority:** Low / Medium / High / Blocking

**Confidence:** High / Medium / Low — and why.

---

**Rules:**
- Cite actual file paths and line numbers for violations.
- Do not suggest redesigns.
- Do not assess intent — report what the code does.
- Confidence is lower if large files were sampled rather than fully read.
