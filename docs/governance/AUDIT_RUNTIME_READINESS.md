# Runtime Readiness Audit

**Objective:** Determine whether this is a complete, self-sufficient language runtime
that can stand alone, be embedded, be extended, and eventually describe itself — or
whether it is still a prototype masquerading as one.

Applies to: any bytecode-compiled, embeddable language runtime.

---

## How to score

Each check returns **PASS / WARN / FAIL**. Evidence must reference real code or
real behavior — not documented intent.

---

## Check 1 — Dependency Boundary

Does the runtime have a clean surface of host-language (e.g. Python) dependencies?

- Name the required runtime dependencies. Could you rebuild the core on a different
  host language with a defined effort?
- Are dependencies version-pinned in a manifest?
- Does the runtime depend on anything that could be replaced by language builtins?
- Are optional features (e.g. HTTP client, DB) properly separated from the core?

**Score:** PASS / WARN / FAIL

---

## Check 2 — Domain Independence

Does the runtime execute arbitrary programs, or does it assume a specific problem domain?

- Are there hardcoded domain concepts (e.g. "agent", "task", "tenant") in the VM,
  compiler, or scheduler?
- Can the runtime be used to write a general-purpose program that has nothing to do
  with the language's primary use case?
- Does the stdlib provide general-purpose primitives (strings, math, collections, I/O)?
- Are language-level built-ins domain-neutral?

**Score:** PASS / WARN / FAIL

---

## Check 3 — Module / Import Completeness

Is the module system complete enough to write non-trivial programs?

- Is there a resolution algorithm? Is it documented?
- Can modules export functions, values, types?
- Can circular imports be detected at load time?
- Is there a path to user-defined libraries (not just stdlib)?

**Score:** PASS / WARN / FAIL

---

## Check 4 — Runtime Neutrality

Does the runtime behave identically regardless of deployment context?

- CLI mode vs embedded mode: are there silent behavioral differences?
- Does execution depend on the host process's working directory, env vars, or
  other ambient state in ways the language does not expose to the script?
- Is execution deterministic given the same source and inputs?

**Score:** PASS / WARN / FAIL

---

## Check 5 — Embedding API Surface

Is the embedding API complete for a realistic host application?

- Single stable entry point?
- Can a host inject functions and receive return values?
- Can a host set resource limits (timeout, step count, memory)?
- Can a host observe errors without crashing?
- Does the API surface have a documented stability tier?

**Score:** PASS / WARN / FAIL

---

## Check 6 — Plugin / Extension Contract

Can third-party code extend the runtime without forking it?

- Is there a documented extension point (plugin, library entry-point, host function)?
- Is there an ABI version that extensions can pin to?
- Can extensions be loaded at startup without modifying the core?
- Is extension code sandboxed from the runtime internals?

**Score:** PASS / WARN / FAIL

---

## Check 7 — Standalone Boot

Can the runtime start, execute a program, and terminate with no external services?

- No required network connection at boot?
- No required database at boot?
- No required configuration file at boot?
- Can "Hello, world" run from a fresh install with a single command?

**Score:** PASS / WARN / FAIL

---

## Check 8 — Lifecycle Ownership

Does the runtime control its own startup and shutdown, or does it depend on the host
to manage these?

- Are initialization steps explicit and ordered?
- Is there a clean shutdown path (flush, drain, join)?
- Can the runtime be instantiated multiple times in the same process?
- Does shutdown release all resources without leaking?

**Score:** PASS / WARN / FAIL

---

## Check 9 — Error Surface Completeness

Do errors produced by the runtime give a user enough to fix their program?

- Do syntax errors include file, line, and column?
- Do runtime errors include a stack trace to the .nd source line?
- Are all error kinds documented?
- Are internal runtime errors distinguished from user program errors?

**Score:** PASS / WARN / FAIL

---

## Check 10 — Test Coverage and Regression Signal

Does the test suite give meaningful confidence in the runtime's correctness?

- Are the compiler, VM, stdlib, and embedding API all covered?
- Are there golden tests (fixed inputs → fixed outputs) that catch regressions?
- Do tests run in CI with a single command?
- Is there a documented coverage floor?

**Score:** PASS / WARN / FAIL

---

## Bootstrap Readiness

Bootstrap readiness measures whether the language has evolved to the point where
its own compiler, parser, or VM could be written in itself. This is a long-term
milestone — reached by Go, Rust, Python (PyPy) — not a release requirement.
It is worth tracking because each stage requires real language maturity.

### Stage classification

| Stage | Requirement | Check |
|-------|-------------|-------|
| 0 | Nothing above "hello world" is expressible | |
| 1 | A lexer can be written in the language | String ops, character access, arrays, loops, recursion |
| 2 | A parser can be written in the language | Recursive descent, algebraic data types or tagged maps, error propagation |
| 3 | Bytecode emission can be expressed | Integer arithmetic, byte/binary output, file write |
| 4 | A VM loop can be expressed | Mutable state, dispatch table, coroutines or loops |
| 5 | Full self-hosting | The language's own toolchain builds and runs via itself |

**Current stage:** ___

### Specific checks

For each, answer: **available / missing / workaround only**

- Character-level string access and slicing
- Integer bit manipulation (AND, OR, XOR, shift)
- Binary file write (not just text)
- Direct recursion with controllable depth
- Tail-call optimization or explicit stack management
- Algebraic types or tagged unions (to represent AST nodes)
- First-class functions (closures passable as values)
- Error propagation without try/catch overhead (result type or tagged return)
- Subprocess invocation (to call the existing runtime)
- Compiler/runtime API access from within a script

### Gap summary

What is the single most significant missing feature before advancing to the next
bootstrap stage?

### Bootstrap confidence

Can the current language express a working tokenizer for its own source syntax?
Write it or state exactly what it would require that is currently absent.

---

## Final Classification

| Classification | Criteria |
|----------------|----------|
| **COMPLETE RUNTIME** | All 10 checks PASS; bootstrap Stage ≥ 2 |
| **PRODUCTION-CAPABLE** | 8+ PASS, no FAIL; bootstrap Stage ≥ 1 |
| **INFRASTRUCTURE-IN-PROGRESS** | 6+ PASS; bootstrap Stage ≥ 0; clear path to remaining checks |
| **PROTOTYPE** | < 6 PASS or any FAIL on Checks 1, 4, 5, or 7 |

**Classification:** ___

**One-sentence justification:**

---

**Rules:**
- Report on what exists, not what is planned.
- WARN requires a quoted specific limitation.
- FAIL requires a named missing or broken thing.
- Bootstrap stage must reflect the actual language feature set, not roadmap intent.
