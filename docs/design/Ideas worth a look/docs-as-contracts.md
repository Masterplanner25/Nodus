# Docs-as-Contracts

## Summary

The idea is to treat handler registrations as formal contracts rather than loose
documentation strings. A contract declares what a handler *guarantees* — its
preconditions, postconditions, and observable effects — and the runtime (or a
gate tool) enforces that the declaration is present and structurally valid. This
is distinct from docstrings or description fields, which are advisory and ignored
at call time.

## Three Core Constraints

- **Contracts, not descriptions.** The declaration must name preconditions (what
  inputs are required and in what shape), effects (what state changes the call
  produces), and guarantees (what the caller can rely on after the call returns).
  A plain English description satisfies none of these; a typed schema can satisfy
  all three.

- **Runtime/registry layer, not language grammar.** The declaration lives at the
  point where a handler registers itself — `tool.register()`, a builtin table
  entry, a workflow step definition, an extension entry point. It does not touch
  `.nd` syntax, the parser, or the compiler. This keeps the grammar stable and
  makes the contract portable to any runtime host.

- **Enforced, not optional.** Omitting the contract is an error at registration
  time, not a lint warning. The runtime rejects handlers that do not conform.
  This is what separates contracts from documentation: documentation degrades
  silently; contracts do not.

## Where the Seed Already Exists

`tool.register()` already enforces dotted namespacing and requires a descriptor
map. `nodus_schema` (`src/nodus_schema/`) already has `SyscallSpec`,
`validate_input()`, and `validate_output()` — typed schemas that the runtime
uses to validate syscall boundaries. The gap is that these two enforcement points
use different mechanisms and only cover their own surfaces (tools vs. syscalls).
Formalizing into a single contract schema that all handler types share is the
open question.

## Open Questions

1. **Single schema or per-surface schemas?** One unified `HandlerContract` type
   vs. separate schemas for tools, builtins, workflow steps, and extension
   entry points. Unified is cleaner; per-surface is more precise.

2. **Enforcement point: registration or call time?** Checking at registration
   catches missing contracts early. Checking at call time can validate argument
   values against preconditions. Both may be needed.

3. **What counts as an "effect"?** Side effects on external state (I/O, network)
   are hard to verify statically. A practical scope might be: declared I/O
   category (pure / reads-state / writes-state / network), not full effect typing.

4. **Tooling integration.** Does `nodus_gate --static` validate contracts? Does
   `tool.register()` fail fast in dev mode but warn in production? Does the
   formatter enforce a canonical contract shape?

5. **Backward compatibility.** Existing `tool.register()` calls have no formal
   contract fields. Migration path: warn-then-error on a semver cycle, or
   require contracts only for newly registered tools (opt-in surface).

## Non-Goals

- Changes to `.nd` syntax or the grammar/compiler.
- Free-text descriptions or docstrings (those can coexist, but they are not the contract).
- Optional hints or advisory metadata that the runtime ignores.
- Effect typing at the language level (that is a much larger type-system project).
