<!-- Authored by Codex during non coding session. Needs review before repo commit and push. -->

# Change Impact Matrix

**Version:** 3.0.2
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
| New stdlib function (minor) | LANG_SPEC | ✅ | ✅ | — | ? | — | — |
| Stdlib breaking change | ✅ | ✅ | ✅ | ✅ | ✅ | ? | ? |

---

## VM and bytecode changes

| Change | BYTECODE_REF | INSTRUCTION_SEMANTICS | ARCHITECTURE | CHANGELOG | BYTECODE_VERSION | FREEZE_PROPOSAL | BYTECODE cache invalidated |
|--------|-------------|----------------------|-------------|-----------|-----------------|----------------|--------------------------|
| New opcode | ✅ | ✅ | ? | ✅ | ✅ (bump) | ✅ | ✅ |
| Opcode semantics change | ✅ | ✅ | — | ✅ | ✅ (bump) | ✅ | ✅ |
| Dispatch table change | — | — | ✅ | ✅ | — | — | — |
| VM performance optimization | — | — | ✅ | ✅ | — | — | — |
| Stack frame layout change | RUNTIME | — | ✅ | ✅ | ✅ (bump) | — | ✅ |

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

| Change | DOCSET_CHANGELOG | DOCSET_STATUS_AUDIT | HIGH_CONFLICT_PLAN |
|--------|-----------------|--------------------|--------------------|
| New governing doc | ✅ | ✅ | — |
| Existing doc reconciled | ✅ | ✅ | ✅ |
| Doc removed | ✅ | ✅ | — |
| Doc superseded | ✅ | ✅ | ✅ |

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
