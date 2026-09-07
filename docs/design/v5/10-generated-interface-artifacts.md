# One definition, many artifacts — should a Nodus interface generate its consumers?

**Status: proposal, unbuilt.** No issue yet. Condensed 2026-09-07 from a July
conversation sketch (`Lightweight IDL.md`), rewritten against 5.12.0 because the
sketch was greenfield and half of what it proposed had already shipped under
other names.

Prerequisite reading: [`11-docs-as-contracts.md`](11-docs-as-contracts.md), which
covers the *declaration* half of this question and whose one open constraint is
named below.

## The sketch, and what was already true

The original proposed six stages: validation-only metadata → executable
contracts with examples → a reusable type system → compiler awareness → code
generation → service definitions. Checked against the tree, the first three are
substantially built and the last three are untouched.

| Sketch stage | Reality at 5.12.0 |
|---|---|
| 1. Validate signatures exist | **Shipped**, twice over. `SyscallSpec` (`nodus_lang_schema/syscalls.py`) carries name, version, capability, `input_schema`, `output_schema`, stability and deprecation. `HandlerContract` (`contracts.py`) carries `input_schema`, `returns_schema`, `effects`, `capabilities_required`, `version`, `tags`, `deprecated`, and a `validate()`. |
| 2. Executable contracts | **Half.** `validate_input()` / `validate_output()` / `validate_payload()` check payloads at runtime. Nothing runs the *examples* the sketch wanted, because nothing carries examples. |
| 3. Reusable types | **Different shape.** Schemas are dicts rather than a named type vocabulary, and `nodus check` has its own type-name set (#609). Two answers to "what is a type here", which is worth noticing before adding a third. |
| 4. Compiler awareness | Not built. |
| 5. Code generation | **Not built, and this is the actual proposal.** |
| 6. Service definitions | Not built. |

The sketch also missed two things the shipped contracts already have and an IDL
would need to keep: **effects** (`pure`, `reads_state`, `writes_state`,
`network`, `filesystem`, `spawns_task`) and **capability requirements**. Those
are what the capability policy and the sandbox read. A definition format that
described only signatures would be a step backwards from `HandlerContract`.

## The real proposal

Strip the staging away and one question is left, and it is not "should Nodus
have an IDL":

> **A handler is declared once. Should its documentation, its contract tests,
> its MCP schema and its bindings be generated from that declaration, or
> maintained beside it?**

Today the answer is *maintained beside it*. Every consumer of `HandlerContract`
and `SyscallSpec` is a **reader** — `tool_module.py`, `capability.py`,
`syscall_runtime.py`, and the gate's `contracts_phase.py`. Nothing generates
anything.

## Why this repo, specifically

The argument is not aesthetic. **One fact maintained in two places drifts here,
reliably, and the tree keeps proving it.** A partial list from a single session:

- **#810** — two registries of "which companions depend on nodus-lang", six
  names against seven, true answer eight. One dependent had neither its suite
  run before an upload nor its range checked after one.
- **#816** — one in-place builtin spelled as a reassignment across four files
  and twenty sites, because nothing checked.
- **#480** — `each` matched by a bare literal in the parser, so
  `lexer.ALL_KEYWORDS` never named it and every consumer that reads that set —
  editors, docs, `--consumers` — was blind to it.
- **#487, #518, #662, #671** — the same shape in the compiler and analyzer.

`nodus_gate --shapes` exists to *detect* this class after the fact, and the
recurring-bug-shape table in `CLAUDE.md` is the register of instances. A
generator is the other move: not detecting the second copy, but not having one.

The handler surface is a good place to try it because the copies are already
visible. A tool's description exists in `HandlerContract.description` **and** in
whatever guide documents it; its schema exists in `input_schema` **and** in the
MCP tool definition a companion exports; its behaviour is asserted in a
hand-written test that nothing ties to the contract.

## What would have to be decided first

1. **`11-docs-as-contracts.md`'s open constraint, which is a prerequisite.** An
   unannotated handler still validates clean and reports `effects: ["pure"]` —
   verified at 5.12.0, four minors after that document recorded it at 4.1.1. A
   generator over declarations that are mostly absent generates a confident
   wrong answer at scale, which is worse than generating nothing. **Enforcement
   first, generation second.**
2. **Which direction is authoritative.** Generating docs *from* contracts and
   generating contracts *from* `.nd` source are different projects with
   different failure modes. The repo's own experience says pick one: `--flips`,
   `--invariants` and `--consumers` all work by making one artifact the source
   and checking the rest against it.
3. **Whether generated output is committed or produced on demand.** Committed
   output needs a gate proving it is current — which is the same drift problem
   one level up, and `llms.txt` already lives with it (`tools/sync_llms_txt.py`
   plus `tests/test_llms_txt_shipped.py`, because the file ships inside the
   wheel).
4. **Whether examples belong in the contract.** The sketch's stage 2 wanted
   them, and the doc gate already runs examples — but from *markdown*, not from
   a declaration. Two places again, so this is a real question rather than a
   free addition.

## What is deliberately not proposed

A `.nd` grammar change. `11-docs-as-contracts.md` settled that the registry layer
is the right home and the language is not involved, and nothing here disturbs
that. This is about what a registration *produces*, not how it is spelled.

Stage 6's service definitions are also out of scope until the first generator
earns its keep. "One definition generating HTTP APIs, MCP tools, syscalls, SDKs
and CLI commands" is a description of Protobuf, and adopting the ambition before
the mechanism is how a schema system ends up with six half-supported targets.
