<!-- Authored by Codex during non coding session. Needs review before repo commit and push. -->

# Release Gates

**Version:** 4.0.6
**Status:** Governing document
**Maintainer:** Shawn Knight (Masterplanner25)

This document lists every gate that must pass before a Nodus release is declared
ready. It is authoritative; `docs/governance/RELEASE_CHECKLIST.md` is the procedural
companion that walks through execution. This document defines the standards; the
checklist executes them.

---

## Gate 1: Test suite

**Command:**
```powershell
PYTHONPATH="C:/dev/Coding Language/src" "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/ -q
```

**Passing criteria:**
- All tests pass (0 failures, 0 errors)
- Coverage ≥ 70% (gate: `--cov-fail-under=70`; raised from 60% on 2026-05-31)
- Coverage run uses `--ignore=tests/test_scheduler_fairness.py` to exclude
  timing-sensitive scheduler fairness tests; those tests must still pass in the
  non-coverage run. Known pre-existing flaky test under full-suite load:
  `test_scheduler_fairness.py::test_long_running_task_rotates_with_budget`.

**Exemptions:** None. The coverage gate cannot be lowered without a TECH_DEBT.md entry
documenting the reason and a plan to recover.

---

## Gate 2: Ruff lint

**Command:**
```powershell
& "C:/dev/Coding Language/.venv/Scripts/python.exe" -m ruff check src/ tests/
```

**Passing criteria:**
- Zero violations in any file you changed
- Pre-existing violations in `src/nodus/vm/vm.py` (E702),
  `src/nodus/builtins/time_module.py` (E701, F841),
  `src/nodus/builtins/encoding_module.py` (F401),
  `src/nodus/builtins/secrets_module.py` (F401) are known and do not block release
  if no new violations were introduced

**Exemptions:** When running pre-release, scope to files changed in the release cycle.
Do not introduce new violations; do not fix pre-existing violations as part of a
release without separate review.

---

## Gate 3: Doc-vs-code gate (nodus_gate)

**Command:**
```powershell
PYTHONPATH="C:/dev/Coding Language/src;C:/dev/Coding Language" `
  "C:/dev/Coding Language/.venv/Scripts/python.exe" `
  -m tools.nodus_gate.cli --all
```

**Passing criteria:**
- `--static`: all 76 documented symbols exist in the codebase
- `--runtime`: all doc code blocks run without failure (0 failures; allowlist covers
  intentionally non-runnable blocks)
- `--closed-issues`: all closed-issue regression tests pass

**Exemptions:** New failing blocks must either be fixed before release OR added to
`.nodusgate-allow` with a comment explaining why they are intentionally non-runnable.
No silent additions to the allowlist.

---

## Gate 4: Closed-issue regression test gate

**Standard (established after v3.0.1 incident):**
Every issue marked as closed and referenced in CHANGELOG.md must have at least one
regression test that exercises the specific behavior fixed. Before cutting a release
wheel, the regression tests for all closed issues in the release must pass against
the **installed wheel**, not just the dev source.

**Procedure:**
1. Build the wheel: `python -m build`
2. Install in a clean virtualenv: `pip install dist/nodus_lang-X.Y.Z-py3-none-any.whl`
3. Run the closed-issue regression tests against the installed wheel

**Why this gate exists:** v3.0.1 shipped without a fix that was present in source but
not in the wheel (missing push before PyPI upload). This gate catches that class of error.

---

## Gate 5: Version sync check

**Check:**
- `src/nodus/support/version.py` contains `__version__ = "X.Y.Z"`
- `pyproject.toml` contains `version = "X.Y.Z"`
- Both match the intended release version
- `nodus --version` (from dev source) outputs `X.Y.Z`

**Exemptions:** None.

---

## Gate 6: CHANGELOG.md entry

**Check:**
- `CHANGELOG.md` has a section for the release version
- The `[Unreleased]` section is empty or does not exist
- All significant changes in the release are listed

**Exemptions:** Trivial patch releases (e.g., version bump only) may have minimal
CHANGELOG entries.

---

## Gate 7: README version sync (for major releases)

**Check:**
- `README.md` JSON-LD block `"version"` matches the release version
- `README.md` describes current features accurately (no forward-looking claims as present)

**Exemptions:** Patch and minor releases do not require a full README review, but the
JSON-LD version field must be updated.

---

## Gate 8: Doc-vs-code gate on companion libraries

For any release that includes companion library changes, the doc-vs-code gate must
pass for all affected repos before any of them is published.

**Companion library test commands:**
```powershell
# nodus-mcp
cd C:\dev\nodus-mcp
PYTHONPATH="C:/dev/Coding Language/src" "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/ -q

# nodus-a2a
cd C:\dev\nodus-a2a
PYTHONPATH="C:/dev/Coding Language/src" "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/ -q
```

---

## Gate 9: Spec version verification (for companion library releases)

Before any companion library is published to the registry, a final-pass spec check
must confirm the library implements the version of the spec it claims.

For nodus-mcp: verify against the 2026-07-28 RC (or final, if available)
For nodus-a2a: verify against A2A 1.0.0 (Linux Foundation)

This catches spec changes between implementation and release.

---

## Gate 10: Pre-publish creator validation

**When:** after the wheel is built (Gate 4 artifacts), before `twine upload` to PyPI.

**Purpose:** the maintainer actively tries to break the language against a real installed
wheel — not dev source — with the explicit goal of finding bugs before users do. This is
adversarial by design. It is different from the post-publish independent eval (Stage 5 /
Gate 4): that stage evaluates "does this work as a new user would expect?" This gate asks
"what can I personally make fail?"

**Protocol:**

1. Build the wheel: `python -m build`
2. Install in a **clean virtualenv** (not the dev venv):
   ```powershell
   python -m venv .venv-validation
   .venv-validation/Scripts/pip install dist/nodus_lang-X.Y.Z-py3-none-any.whl
   ```
3. Write 8–12 Nodus programs targeting the highest-complexity surfaces. Required
   categories:
   - **Closures and upvalue capture** — nested closures, mutation through outer scope
   - **Coroutines and channels** — spawn/yield/recv sequences, closed-channel behavior
   - **Error handling** — try/catch/finally interaction, throw inside finally, rethrow
   - **Import system** — multi-file imports, circular import detection, alias resolution
   - **Operator and type edge cases** — division by zero, nil coercion, integer vs float arithmetic
   - **Error messages** — are they user-legible or internal garbage? Trigger each error category
   - **The documented quirks** from `CLAUDE.md §"Nodus language quirks"` — every quirk must
     behave exactly as documented; any deviation is a bug
   - **At least one workflow or goal execution** if the release touches the orchestration layer
4. For each failure found, apply the disposition:
   - **Fixable before publish** (clear root cause, low regression risk) → fix it now; it ships
     in this version; add a regression test; add to CHANGELOG
   - **Not fixable before publish** (requires design, risky, or too large) → file a GitHub issue
     immediately with full repro; note it as a known issue in the release announcement; commit
     to a fast turnaround (see `docs/governance/ISSUE_RESPONSE_POLICY.md`)
5. Record findings in `docs/evals/vX.Y.Z/CREATOR_VALIDATION.md` — even if everything passes.
   A clean run is evidence, not silence.

**Passing criteria:**
- No unfiled bugs. Every failure either has a fix committed or a filed issue with a severity label.
- At least 8 programs executed to completion or to expected failures.
- No regressions introduced by any fix made during this stage (Gate 1 reruns after each fix).

**Exemptions:**
- Emergency security patches may run an abbreviated version scoped to the patched code path only.
- Pure doc-only releases are exempt.

**Why this gate exists:** prior to v4.0.0, discovery of language bugs happened post-publish via
the independent eval (Stage 5). This placed bugs in front of users before the maintainer knew
about them. Creator validation closes that window by moving adversarial testing to before the
upload, when fixes are still cheap.

---

## Gate failure handling

A failed gate blocks the release. The options are:

1. Fix the failing gate → proceed with release
2. Document the failure as a known issue in `docs/governance/TECH_DEBT.md` → release
   with a corresponding GitHub issue tracking the fix (only for non-blocking failures
   like ruff pre-existing violations)
3. Change the gate criteria → requires a governance discussion and update to this document

Option 2 is only available for non-critical gates. Tests, ruff (new violations), and
doc-vs-code failures cannot be deferred.

---

## Gate summary table

| Gate | Applies to | Deferrable? |
|------|-----------|------------|
| Test suite | All releases | No |
| Ruff lint | All releases | Only for pre-existing violations |
| Doc-vs-code | All releases | No |
| Closed-issue regression | Patch/minor | No |
| Version sync | All releases | No |
| CHANGELOG entry | All releases | Minor for trivial patches |
| README version sync | Major releases | No |
| Companion library tests | Coordinated release | No |
| Spec version verification | Companion library releases | No |
| **Pre-publish creator validation** | All releases (abbreviated for security patches) | No |

---

## Related documents

- `docs/governance/RELEASE_CHECKLIST.md` — procedural checklist (should reference this document)
- `docs/governance/RELEASE_PLAYBOOK.md` — full release playbook
- `docs/governance/TECH_DEBT.md` — known gate-adjacent issues
