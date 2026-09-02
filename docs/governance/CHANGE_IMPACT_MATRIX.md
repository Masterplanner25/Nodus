# Change Impact Matrix

**Last reviewed:** 2026-09-01, against 5.9.0
**Status:** Reference document
**Maintainer:** Shawn Knight (Masterplanner25)

This matrix maps change types to their ripple effects across the Nodus ecosystem.
Use it when planning changes to understand what else needs to move.

---

## How to read this matrix

Row = change type. Columns = impacted areas. Cell = what must be updated.

`✅` = impact expected; update required
`—` = no expected impact
`?` = possible impact; verify case-by-case

---

## Core language changes

| Change | LANG_SPEC | CHANGELOG | LANGUAGE_STABILITY_INDEX | Migration guide | Eval | nodus-mcp | nodus-a2a |
|--------|-----------|-----------|--------------------------|-----------------|------|-----------|-----------|
| New syntax (stable) | ✅ | ✅ | ✅ | — | ✅ | — | — |
| New syntax (experimental) | ✅ | ✅ | ✅ | — | ? | — | — |
| Syntax breaking change | ✅ | ✅ | ✅ | ✅ | ✅ | ? | ? |
| Removed deprecated syntax | ✅ | ✅ | ✅ | ✅ | — | ? | ? |
| New stdlib function (minor) | ✅ | ✅ | ✅ | — | ? | — | — |
| Stdlib breaking change | ✅ | ✅ | ✅ | ✅ | ✅ | ? | ? |

---

## VM and bytecode changes

| Change | BYTECODE_REF | INSTRUCTION_SEMANTICS | ARCHITECTURE | CHANGELOG | BYTECODE_VERSION | FREEZE_PROPOSAL | BYTECODE cache invalidated |
|--------|-------------|----------------------|-------------|-----------|-----------------|----------------|--------------------------|
| New opcode | ✅ | ✅ | ? | ✅ | ✅ (bump) | ✅ | ✅ |
| Opcode semantics change | ✅ | ✅ | — | ✅ | ✅ (bump) | ✅ | ✅ |
| Dispatch table change | — | — | ✅ | ✅ | — | — | — |
| VM performance optimization | — | — | ✅ | ✅ | — | — | — |
| Stack frame layout change | ? | — | ✅ | ✅ | ✅ (bump) | — | ✅ |

Frame layout is a VM internal: `docs/runtime/RUNTIME.md` is the document that
describes it, and `BYTECODE_REFERENCE.md` only needs touching if an instruction's
operand meaning moves with it — hence `?`.

**A new opcode has two gate obligations the `✅`s above do not spell out**, and
`nodus_gate --opcodes` fails until both are met:

- `BYTECODE_REFERENCE.md` **§3 and its appendix table** and the
  `FREEZE_PROPOSAL.md` stability tables must all name the same set, with matching
  counts and `BYTECODE_VERSION` ([#366](https://github.com/Masterplanner25/Nodus/issues/366)).
- Every dispatched opcode must carry a **semantic spec** in
  `tests/test_opcode_semantics*.py` and a `- Category:` line
  ([#412](https://github.com/Masterplanner25/Nodus/issues/412) phase 4). The
  relation is an equality: a spec naming nothing dispatched fails too.

The step-by-step procedure is in `RELEASE_CHECKLIST.md § "Adding a new opcode"`.

---

## Embedding API changes

| Change | EMBEDDING.md | RUNBOOK | CHANGELOG | COMPATIBILITY_MODEL | nodus-mcp | nodus-a2a |
|--------|-------------|---------|-----------|--------------------|-----------| ---------|
| New NodusRuntime parameter | ✅ | ✅ | ✅ | — | — | — |
| Breaking NodusRuntime parameter change | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| New run_source() result key | ✅ | ✅ | ✅ | — | ? | ? |
| Breaking run_source() result change | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| New host function registration API | ✅ | ✅ | ✅ | — | — | — |

---

## Sandbox / security changes

| Change | SECURITY_POSTURE | EMBEDDING.md | TECH_DEBT | CHANGELOG | Test required (both modes) |
|--------|-----------------|-------------|-----------|-----------|--------------------------|
| New sandbox parameter | ✅ | ✅ | — | ✅ | ✅ |
| Security bug fix | ✅ | ? | ✅ | ✅ | ✅ |
| Sandbox enforcement tightened | ✅ | ✅ | — | ✅ | ✅ |
| Sandbox enforcement relaxed | ✅ | ✅ | ✅ | ✅ | ✅ |

---

## Module system changes

| Change | ARCHITECTURE | CHANGELOG | LANG_SPEC | Migration guide |
|--------|-------------|-----------|-----------|-----------------|
| Import path resolution change | ✅ | ✅ | ✅ | ? |
| Module cache format change | ✅ | ✅ | — | — |
| Module object shape change | ✅ | ✅ | — | ? |
| Import containment rule change | ✅ | ✅ | ✅ | ✅ |

---

## Workflow and orchestration changes

| Change | WORKFLOWS | ARCHITECTURE | LANG_SPEC | LANG_STABILITY_INDEX | CHANGELOG |
|--------|-----------|-------------|-----------|----------------------|-----------|
| Workflow syntax change | ✅ | — | ✅ | ✅ | ✅ |
| Task graph persistence format change | ✅ | ✅ | — | — | ✅ |
| Scheduler behavior change | — | ✅ | — | — | ✅ |
| Workflow API graduation (Experimental → Stable) | — | — | ✅ | ✅ | ✅ |

---

## Companion library changes

| Change | LIBRARY_ECOSYSTEM | ECOSYSTEM_READINESS | nodus-mcp README | nodus-a2a README | CHANGELOG (core) |
|--------|-------------------|--------------------|-----------------|-----------------|--------------------|
| Companion library published | ✅ | ✅ | — | — | — |
| Companion library breaking change | ? | ✅ | ✅ | ✅ | — |
| Companion library new transport | ✅ | ✅ | ✅ | ✅ | — |
| Protocol spec upgrade | ✅ | ✅ | ✅ | ✅ | — |
| Companion library deprecation | ✅ | ✅ | ✅ | ✅ | — |

---

## Documentation-only changes

| Change | DOCSET_INDEX | `Last reviewed:` field |
|--------|--------------|------------------------|
| New governing doc | ✅ | ✅ (set it) |
| Existing doc reconciled | — | ✅ (only if the whole doc was checked) |
| Doc removed | ✅ | — |
| Doc superseded | ✅ | ✅ set `Status: Historical` |

**This table used to require `DOCSET_CHANGELOG`, `DOCSET_STATUS_AUDIT` and
`HIGH_CONFLICT_PLAN`. All three are now closed or frozen** and updating them is
wrong:

- `DOCSET_CHANGELOG.md` and `DOCSET_STATUS_AUDIT.md` were frozen 2026-09-01 as
  dated records of the 2026-05-29 sweep — each says *"Do not update it to match
  the tree."* The changelog had accumulated exactly one entry in nine releases,
  so the requirement had already lapsed before it became contradictory.
- `HIGH_CONFLICT_DOC_RECONCILIATION_PLAN.md` is **closed**; all seven conflicts
  were verified resolved 2026-08-07. It is not a to-do list.

`DOCSET_GOVERNANCE.md § "Where doc changes are recorded"` carries the same
correction — this row and that procedure were two statements of one rule, and
freezing the target files updated neither.

---

## Changes that add a required entry to a manifest

Six gates read a hand-maintained manifest. A change of the kind in the left
column fails `nodus_gate` until the manifest moves with it — these are the rows
most easily missed, because the code compiles and the tests pass.

| Change | Manifest to update | Gate that fails |
|--------|--------------------|-----------------|
| New opcode | a spec in `tests/test_opcode_semantics*.py` | `--opcodes` |
| New runtime invariant in `EXECUTION_INVARIANTS.md` | `tools/invariant_coverage.json` | `--invariants` |
| New sentence in prose asserting the current version | `tools/version_claims.json` | `--versions` |
| New keyword | a set in `lexer.py` — never a bare literal in `parser.py` — then `tools/consumers.json` | `--consumers`, `tests/test_keyword_coverage.py` |
| New field on an existing AST node | nothing to declare, but `fmt` must render it | `tests/test_formatter_round_trip.py` |
| A second implementation of a question already answered elsewhere | `tools/shape_manifest.json`, with a stated reason | `--shapes` (advisory; `--strict` fails) |

Two of these exist because the failure they catch shipped. `each` was matched by
a bare string literal in `parser.py`, so `lexer.ALL_KEYWORDS` never named it and
`--consumers` reported "in step" on a release that changed the keyword set
([#480](https://github.com/Masterplanner25/Nodus/issues/480)). And `each` and
`budget { limits: … }` are new **fields** on existing nodes, so the formatter's
node-level completeness guard stayed green while `fmt` silently dropped them
([#657](https://github.com/Masterplanner25/Nodus/issues/657)) — a guard at node
granularity does not cover field granularity, which is why the round-trip test
is the row above and not the node walker.

---

## Rules for using this matrix

1. Before a code change, check the row for its change type
2. Before a release, verify all impacted areas are updated
3. If unsure whether a change qualifies for a row, check COMPATIBILITY_MODEL.md
4. If the change has cross-repo impact (core → nodus-mcp or nodus-a2a), coordinate
   the update before tagging either repo

---

## Related documents

- `docs/governance/COMPATIBILITY_MODEL.md` — what counts as breaking
- `docs/governance/RELEASE_GATES.md` — gates that must pass before release
- `docs/governance/TECH_DEBT.md` — open items that may affect impact assessment
