# Why the ecosystem packages are written in Python, not Nodus

**Status:** design rationale · **Last reviewed:** 2026-07-05

A recurring question: Nodus is our language — so why is (nearly) every companion
package (`nodus-a2a`, `nodus-agent`, `nodus-auth`, `nodus-approvals`, …) written
in **Python** instead of in Nodus itself?

The short answer: **Nodus is a Python-hosted language, and most of these packages
exist to connect Nodus *to* the outside (Python/native) world — so they have to
live on the host side.** It is a deliberate staging decision, not an accident.

## The reasons, in order of weight

1. **Nodus runs *on* Python.** The `.nd` interpreter, VM, and stdlib all execute
   in CPython. Anything that plugs into the runtime — host functions (`_ext_*`,
   `nm_*`), `attach_to_runtime`, the SDK bridges that return maps — *is* the host
   boundary. You cannot write the host boundary in the guest language; that is
   circular. So every runtime-integrating library is Python by definition.

2. **Their actual job is interop with things Nodus cannot reach.** Look at what
   they wrap: `bcrypt` / `python-jose` (auth), `sqlalchemy` (store-sql), `fastapi`
   (sdk), the MCP protocol SDK, Redis, PyO3/Rust (native-memory-engine). Nodus has
   no FFI to arbitrary Python/C libraries. The package *is* the glue that makes
   `bcrypt` callable from a Nodus program. Rewriting that glue in Nodus would first
   require Nodus to call Python — the opposite direction.

3. **The language cannot self-host yet — but the compiler *shape* is now
   expressible.** The first parser/compiler written *in* Nodus was
   `examples/expr_compiler.nd` (a small arithmetic compiler + tree-walking
   evaluator, added as a self-hosting-readiness probe). It surfaced concrete gaps
   that have since been closed: `match`/tag dispatch (#308), `break`/`continue`
   (#309), and a `fmt` escape round-trip bug (#310). `examples/tiny_vm.nd` then
   pushed the exercise the full distance — a lexer, parser, **bytecode compiler**
   with back-patched jumps, and a **stack VM** with call frames and recursion, all
   in Nodus — and it compiles and runs a recursive `fib`/`fact` program on the
   Nodus-hosted VM. So the *architecture* of a real language implementation is now
   reachable in Nodus. What still blocks self-hosting *Nodus itself* is not
   expressiveness but **performance** (a Nodus-hosted interpreter is double
   interpretation and far too slow for production) plus the remaining surface gaps
   (dynamic typing, no first-class bytes, no substring/slice builtin). Shipping
   20–130-test production libraries on that basis would still be premature.

4. **Velocity and maturity.** Python brings mature testing (pytest), packaging
   (PyPI, wheels), typing, and debuggers. The standard bootstrapping order is: build
   the ecosystem in the host language first, then migrate selected pieces to the
   guest language *as it earns it* (Rule of Three — don't rewrite in Nodus until the
   rewrite is a win, not a fight).

## There is already Nodus-written code

The distinction is not "no Nodus code" — it is **"Nodus for language-level surface,
Python for host integration."** The stdlib modules (`src/nodus/stdlib/*.nd` —
strings, math, fs, json) *are* Nodus; they are thin wrappers over Python builtins.
This is codified in the README's "Shared design rules": Python-first APIs are the
canonical contract, Nodus builtins are thin wrappers over them.

## Which packages could migrate to Nodus later

Two categories:

- **Host-boundary packages (stay Python permanently):** anything wrapping a Python/
  native library or plugging into the runtime — `nodus-auth`, `nodus-store-sql`,
  `nodus-sdk`, `nodus-mcp`, `nodus-native-memory-engine`, the bridges. These *are*
  the host boundary; they cannot be Nodus.

- **Pure-logic packages (candidate for self-hosting):** the ones marked "no
  nodus-lang dependency" — `nodus-a2a` (AgentCoordinator), `nodus-approvals`,
  `nodus-agent`. These are pure coordination/algorithm code with no runtime
  plumbing — exactly the shape `expr_compiler.nd` proved Nodus can express. They are
  Python today purely for maturity/velocity, and are the natural first candidates
  for the dogfooding / self-hosting path once the language gaps above are closed.

## Bottom line

Python-hosted-language + interop-focused-ecosystem means the runtime-integrating
packages will always be Python. The pure-logic packages are the migration frontier,
gated on the language earning it — which is what the `expr_compiler.nd` probe and
issues #308/#309/#310 are the first steps toward.
