<!-- Authored by Codex during non coding session. Needs review before repo commit and push. -->

# High-Conflict Doc Reconciliation Plan

**Date:** 2026-05-29
**Status:** Working document — track reconciliation progress here
**Maintainer:** Shawn Knight (Masterplanner25)

This document identifies the highest-conflict documentation areas — where docs
contradict each other, make stale claims, or blur important boundaries — and plans
the reconciliation.

---

## Conflict ranking

"Conflict" means: a reader arriving at this doc will get a materially false impression
of the current state, or will be unable to determine what is authoritative.

| Rank | Document | Conflict type | Severity |
|------|----------|--------------|----------|
| 1 | `docs/governance/LIBRARY_ECOSYSTEM.md` | nodus-a2a scope overclaim | High |
| 2 | `README.md` (JSON-LD block) | Version drift (2.1.0 vs 3.0.2) | High |
| 3 | `docs/governance/COMPATIBILITY.md` | Deprecation timeline masquerades as compatibility model | High |
| 4 | `docs/governance/STABILITY.md` | Too thin; no surface-by-surface stability | Medium |
| 5 | `docs/governance/RELEASE_CHECKLIST.md` | Pre-v1.0 CLI commands | Medium |
| 6 | `docs/language/LANGUAGE_VISION.md` | "Near-Term Direction" describes v4.0 as in-progress (accurate but may drift) | Low |
| 7 | Multiple docs | Missing `STDLIB_PHILOSOPHY.md` referenced by `LIBRARY_ECOSYSTEM.md` | Low |

---

## Conflict 1: LIBRARY_ECOSYSTEM.md nodus-a2a overclaim

**Status:** ACTION REQUIRED (not yet reconciled)

**Problem:** The nodus-a2a entry in `LIBRARY_ECOSYSTEM.md` claims:
> "All three protocol bindings (JSON-RPC, gRPC, HTTP+JSON/REST). Full A2A v1.0.0 spec
> support (Task lifecycle, Message/Artifact/Part data model, AgentCard discovery,
> streaming via SSE, push notifications via webhooks, multi-turn via contextId/taskId,
> Extensions mechanism, bearer-token auth for v0.1)."

The actual nodus-a2a v0.1 supports only:
- HTTP+JSON/REST (not JSON-RPC, not gRPC)
- Message-only — no Task lifecycle
- No streaming (no SSE)
- No push notifications
- Bearer-token auth only

**Reconciliation action:** Update `LIBRARY_ECOSYSTEM.md` §"Tier 3" nodus-a2a entry to
accurately describe v0.1. Add an explicit note that the description is the v0.2+ target.
The architectural commitment section is accurate and does not need changes.

**Draft corrected text:**
```
- `nodus-a2a` — Agent2Agent Protocol library. v0.1.0 scope: HTTP+JSON/REST transport
  only; message-only (no Task lifecycle); bearer-token auth; AgentCard discovery;
  DataPart-based tool dispatch. Deferred to v0.2+: JSON-RPC binding, gRPC binding,
  Task lifecycle and state machine, SSE streaming, push notification webhooks,
  OAuth/OIDC. Full A2A 1.0.0 spec coverage is the v0.2+ target.
```

**Estimated effort:** 30 minutes (targeted edit)

---

## Conflict 2: README.md version drift

**Status:** ACTION REQUIRED (not yet reconciled)

**Problem:** `README.md` JSON-LD block has `"version": "2.1.0"` while the current
release is 3.0.2.

**Reconciliation action:** Change the JSON-LD version to `"3.0.2"`. Add to release
gate check (Gate 7 in `RELEASE_GATES.md`).

**Draft change:**
```diff
-  "version": "2.1.0",
+  "version": "3.0.2",
```

**Estimated effort:** 5 minutes

---

## Conflict 3: COMPATIBILITY.md vs actual compatibility model

**Status:** New governing document created; cross-reference needed

**Problem:** `COMPATIBILITY.md` is a deprecation timeline. Readers looking for the
compatibility policy (what counts as breaking, semver rules, bytecode compatibility)
find only a timeline of deprecation decisions.

**Reconciliation action:**
1. `COMPATIBILITY_MODEL.md` is now the governing document (created in this sweep)
2. Add a preamble to `COMPATIBILITY.md` directing readers to `COMPATIBILITY_MODEL.md`
3. Rename the file to `DEPRECATION_TIMELINE.md` (optional — preserves the existing name
   for continuity if external links exist)

**Status:** `COMPATIBILITY_MODEL.md` created. Preamble addition to `COMPATIBILITY.md` pending.

---

## Conflict 4: STABILITY.md vs surface-by-surface reality

**Status:** New governing document created; cross-reference needed

**Problem:** `STABILITY.md` provides a useful but thin three-tier classification.
The Experimental tier lists workflows and coroutines without graduation criteria.
The Stable tier does not distinguish between language syntax stability and API stability.

**Reconciliation action:**
1. `LANGUAGE_STABILITY_INDEX.md` is now the governing document (created in this sweep)
2. Add a preamble to `STABILITY.md` directing readers to `LANGUAGE_STABILITY_INDEX.md`
3. Keep `STABILITY.md` as a quick-reference summary

**Status:** `LANGUAGE_STABILITY_INDEX.md` created. Preamble addition to `STABILITY.md` pending.

---

## Conflict 5: RELEASE_CHECKLIST.md stale commands

**Status:** ACTION REQUIRED (not yet reconciled)

**Problem:** The checklist uses `python nodus.py` (pre-v1.0 command) and
`python -m unittest discover -s tests -v` (not used since pytest migration). It also
does not include the doc-vs-code gate.

**Reconciliation action:** Update the checklist to use current commands and add doc-vs-code
gate step. Reference `RELEASE_GATES.md` for the authoritative gate definitions.

**Draft update:**
```markdown
## Pre-release checks
- Verify no lint violations in changed files:
  ```powershell
  & ".venv/Scripts/python.exe" -m ruff check src/ tests/
  ```
- Run test suite:
  ```powershell
  PYTHONPATH="src" ".venv/Scripts/python.exe" -m pytest tests/ -q
  ```
- Run doc-vs-code gate:
  ```powershell
  PYTHONPATH="src;." ".venv/Scripts/python.exe" -m tools.nodus_gate.cli --all
  ```
- Verify version sync (src/nodus/support/version.py and pyproject.toml)
- Verify CLI output: nodus --version
```

**Estimated effort:** 20 minutes

---

## Conflict 6: LANGUAGE_VISION.md forward-looking section

**Status:** Minor; monitor but do not change now

**Problem:** The "Near-Term Direction" section describes v4.0 phases as in-progress.
This is accurate as of the writing date but may become stale as phases complete.

**Reconciliation approach:** After the v4.0 release, update LANGUAGE_VISION.md to
reflect that v4.0 is complete. Not urgent during the pre-release period.

---

## Conflict 7: Missing STDLIB_PHILOSOPHY.md

**Status:** Tolerable gap; resolve before v4.0 release

**Problem:** `LIBRARY_ECOSYSTEM.md` references `docs/governance/STDLIB_PHILOSOPHY.md`
four times as a "Phase 4 deliverable." The file does not exist.

**Reconciliation approach:** The philosophy is already captured in:
- `LIBRARY_ECOSYSTEM.md §"What this ecosystem explicitly does NOT pursue"` (the not-pursued list)
- `LANGUAGE_VISION.md §"What Nodus Is Not"`
- `LIBRARY_ECOSYSTEM.md §"Tier 1 ceiling"`

Options:
1. Create a minimal `STDLIB_PHILOSOPHY.md` that is a thin summary pointing to the above sections
2. Replace the four references with specific section links to the existing docs

Option 1 is cleaner. Estimated effort: 30 minutes.

---

## Reconciliation tracking

| Doc | Status | Action |
|-----|--------|--------|
| `LIBRARY_ECOSYSTEM.md` | ❌ Not reconciled | Update nodus-a2a entry |
| `README.md` JSON-LD | ❌ Not reconciled | Fix version |
| `COMPATIBILITY.md` | 🟡 Partially reconciled | Add preamble pointing to COMPATIBILITY_MODEL.md |
| `STABILITY.md` | 🟡 Partially reconciled | Add preamble pointing to LANGUAGE_STABILITY_INDEX.md |
| `RELEASE_CHECKLIST.md` | ❌ Not reconciled | Update commands |
| `LANGUAGE_VISION.md` | 🟢 Acceptable as-is | Update post v4.0 launch |
| `STDLIB_PHILOSOPHY.md` | ❌ Missing | Create stub or remove references |

---

## Related documents

- `docs/governance/DOCSET_ALIGNMENT_AUDIT.md` — source of these findings
- `docs/governance/DOCSET_STATUS_AUDIT.md` — per-document status summary
- `docs/governance/DOCSET_CHANGELOG.md` — what changed in this sweep
