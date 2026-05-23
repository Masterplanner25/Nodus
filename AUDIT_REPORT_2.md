# Nodus Re-Audit Report
**Date:** 2026-05-22
**Auditor:** Claude Code
**Baseline:** AUDIT_REPORT.md (2026-05-21)
**Version audited:** 1.1.2 (unreleased audit-fix commit `0e9acfb` on top of 1.1.2)

## Executive delta summary

Eight of the ten prior priority items are fully resolved in a single commit (`0e9acfb` — "CI, code hygiene, and docs improvements from audit (Phase 1–3)") applied the day after the baseline audit. One item is PARTIAL: a ruff lint step was added to CI but no baseline or `# noqa` suppression was configured for the 66 remaining legacy errors, meaning CI now fails on every push. One item PERSISTS: the starlette/fastapi dependency version gap is unchanged at the package level, though fastapi and uvicorn now carry upper-bound pins in the published extras. Two new findings were identified: CI is currently broken by design due to the lint backlog, and TECH_DEBT.md contains two stale open-item notes that contradict current code behavior. The overall trajectory is strongly positive — the structural and documentation debt from the flat-layout migration is cleared and AISO indexing is now in place.

---

## Prior Top 10 — status

| # | Item | Status | Notes |
|---|------|--------|-------|
| 1 | CONTRIBUTING.md flat-layout references | RESOLVED | Diagram now shows `src/nodus/` layout; `requirements-dev.txt` reference changed to `requirements.txt`; both `LANGUAGE_SPEC.md` references updated to `docs/language/LANGUAGE_SPEC.md`. DEVELOPMENT.md also updated (all 7 file refs now use full paths). |
| 2 | `test_formatter_foreach.py` excluded from CI | RESOLVED | `Pytest` step (`python -m pytest -q`) added to `ci.yml` after the `Unit tests` step. File remains a bare pytest function; the fix is in CI, not in the test file. |
| 3 | No lint step in CI | PARTIAL | `Lint` step (`pip install ruff && ruff check .`) added as the first substantive step. The step is check-only, no `--fix`. However, no ruff ignore/baseline is configured, so the 66 remaining legacy errors cause CI to fail on every push. See NEW finding #1. |
| 4 | Unpinned server extras in `pyproject.toml` | RESOLVED | `fastapi>=0.111.0,<1` and `uvicorn>=0.30.0,<1` now set. No longer fully unpinned. |
| 5 | `nodus.py:23` undefined name `main` | RESOLVED | `from nodus.cli.cli import main` added inside the `if __name__ == "__main__":` block. ruff F821 count: 1 → 0. |
| 6 | `src/nodus/frontend/types.py` exec() pattern | RESOLVED | Replaced with explicit `from types import (AsyncGeneratorType, BuiltinFunctionType, …)` statements. Module is now statically analysable. |
| 7 | `llms.txt` absent | RESOLVED | `llms.txt` created at project root with project name header, one-sentence canonical definition, creator attribution (Shawn Knight), Masterplan Infinite Weave and Infinity Algorithm definitions, and links to 8 key documents. |
| 8 | `runtime/project.py` 7 unused imports | RESOLVED | 9 unused imports removed (prior audit counted 7; TECH_DEBT.md and commit message count 9). File now imports only what its 2 public functions use. |
| 9 | starlette/fastapi major version gap | PERSISTS | starlette 0.37.2 (latest 1.0.1), fastapi 0.111.0 (latest 0.136.1) — versions unchanged in the venv. Upper-bound pins added to published extras (`<1`) prevent pulling 1.x on fresh installs but do not update the dev environment. |
| 10 | Auto-format CI step creates history mutations | RESOLVED | Auto-format + git-commit step pair removed. `permissions: contents` downgraded from `write` to `read`. Format enforcement retained as check-only via the existing `nodus fmt --check` step. |

---

## 1. Code Quality & Architecture

### Delta findings

**RESOLVED — Prior item 5 — nodus.py:23 F821**
`nodus.py:23` now reads `from nodus.cli.cli import main` inside the `if __name__ == "__main__":` block. ruff F821 count dropped from 1 to 0.

**RESOLVED — Prior item 6 — frontend/types.py exec()**
`src/nodus/frontend/types.py` no longer uses `exec(compile(...))`. The file now has an explicit `from types import (...)` block listing all names from `types.__all__`. No behavior change; the module is now statically analysable and portable across Python distributions.

**RESOLVED — Prior item 8 — runtime/project.py unused imports**
`src/nodus/runtime/project.py` reduced from 14 import lines to 5. Nine names removed: `DependencySpec`, `create_project`, `find_project_root`, `load_manifest`, `load_project`, `load_project_from`, `parse_dependencies`, `read_lockfile`, `write_lockfile`. All two public functions in the file now have all their imports satisfied.

**PERSISTS — Duplicate `import threading` in services/server.py**
`src/nodus/services/server.py` still has `import threading` at line 12 and again at line 48. ruff reports F811 (redefinition of unused `threading`). Count: 1 (unchanged).

**PERSISTS — vm.py line count**
`src/nodus/vm/vm.py` is 2,418 lines (unchanged from baseline). Workflow/goal/agent/memory builtins remain inline in `VM.__init__`. No further extraction occurred.

**PERSISTS — vm.py imports from services layer**
`src/nodus/vm/vm.py:14–22` still imports directly from `services/agent_runtime`, `services/memory_runtime`, and `services/tool_runtime`. VM cannot run standalone without the services infrastructure.

**PERSISTS — BuiltinRegistry inline in builtins/__init__.py**
`src/nodus/builtins/__init__.py` still houses the full `BuiltinRegistry` class (57 lines). Not extracted to `builtins/registry.py`.

**PERSISTS — __init__.py logic beyond re-exports**
`src/nodus/__init__.py` still defines `run_source()`, `resolve_imports()`, and `main()` wrapper functions with docstrings beyond pure re-exports.

**PERSISTS — No mypy installed or configured**
mypy remains absent from the venv. No `[tool.mypy]` section in `pyproject.toml`. Zero type-check results available.

**NEW — TECH_DEBT.md stale max_frames note**
`docs/governance/TECH_DEBT.md:39` states "VM call stack has no explicit max depth check (e.g., `src/nodus/vm/vm.py:1459` `call_closure` and `src/nodus/vm/vm.py:2012` `CALL` opcode paths)." The check IS now present: `vm.py:1518` has `if self.max_frames is not None and len(self.frames) + 1 > self.max_frames: self.runtime_error("sandbox", "Call stack overflow")` and a parallel check at line 2071 for the CALL opcode path. The TECH_DEBT entry was not marked ✅ after the implementation was added. This is a documentation inconsistency, not a behavioral one.

**PERSISTS — TECH_DEBT.md stale vm.py line count**
`docs/governance/TECH_DEBT.md:94` states "`vm.py` line count: ~2,371 lines as of v1.0." Actual current count is 2,418. This was noted in the prior audit and remains uncorrected.

### Metrics

**Ruff error counts**

| Code | Prior | Current | Delta | Description |
|------|-------|---------|-------|-------------|
| F401 | 55 | 46 | −9 | Unused imports (project.py cleanup drove reduction) |
| E402 | 12 | 11 | −1 | Module-level import not at top |
| F841 | 6 | 6 | 0 | Assigned but never used |
| E401 | 2 | 2 | 0 | Multiple imports on one line (`tmp_demo/`) |
| F811 | 1 | 1 | 0 | Redefinition of unused name (threading in server.py) |
| F821 | 1 | 0 | −1 | Undefined name — **RESOLVED** |
| **Total** | **77** | **66** | **−11** | 50 fixable with `--fix` |

**Module line counts**

| File | Prior | Current | Delta |
|------|-------|---------|-------|
| `vm/vm.py` | 2,418 | 2,418 | 0 |
| `cli/cli.py` | 1,562 | 1,562 | 0 |
| `services/server.py` | 1,267 | 1,267 | 0 |
| `tooling/runner.py` | 1,126 | 1,126 | 0 |
| `lsp/server.py` | 1,028 | 1,028 | 0 |
| `runtime/module_loader.py` | 941 | 941 | 0 |

**mypy:** Not installed — no type-check results available (unchanged).

---

## 2. Test Coverage & CI/CD

### Delta findings

**RESOLVED — Prior item 2 — test_formatter_foreach.py now in CI**
`ci.yml` now has a `Pytest` step (`python -m pytest -q`) positioned after `Unit tests`. `tests/test_formatter_foreach.py::test_format_foreach` is now run in CI. The test file itself remains a bare pytest function (not a `unittest.TestCase`).

**RESOLVED — Prior item 3 (structural) — Lint step present**
`ci.yml` now has a `Lint` step as the first substantive step after `Set up Python`. No `--fix` flag; lint is check-only.

**RESOLVED — Prior item 10 — Auto-format commit step removed**
The `Auto-format all .nd files` + `Commit formatted files` step pair is gone. `permissions: contents: read` (was `write`).

**NEW — CI fails on every push due to lint backlog (Prior item 3, partial consequence)**
With 66 outstanding ruff errors and no ruff configuration (`[tool.ruff]` absent from `pyproject.toml`, no `ruff.toml`, no per-file `# noqa` suppression for the backlog), the newly added `ruff check .` step exits with code 1 on every push. CI has moved from "passes with no lint gate" to "fails on every push with 66 lint errors." The TECH_DEBT.md acknowledges this was intentional ("77 existing errors will immediately surface on the next CI run") but no remediation plan or timeline is recorded.

**PERSISTS — No coverage gate**
`pytest-cov` is not installed. `ci.yml` has no `pytest --cov` step and no coverage threshold. Per-module coverage data remains unavailable.

**PERSISTS — Action versions unpinned to SHAs**
`actions/checkout@v4` and `actions/setup-python@v5` remain unpinned to commit SHAs.

**PERSISTS — unittest/pytest gap unchanged**
unittest discover: 368 tests. pytest: 414 collected, 413 passed, 1 skipped. Gap of 46 tests (unchanged). The gap exists because many pytest-collected test files use `unittest.TestCase` but pytest discovers them via its collector while `python -m unittest discover` misses them.

### Metrics

| Runner | Prior | Current | Delta |
|--------|-------|---------|-------|
| pytest collected | 414 | 414 | 0 |
| pytest passed | 413 | 413 | 0 |
| pytest skipped | 1 | 1 | 0 |
| pytest failed | 0 | 0 | 0 |
| unittest discover | 368 | 368 | 0 |
| Coverage % | N/A | N/A | — |

---

## 3. Documentation & AISO Indexing

### Delta findings

**RESOLVED — Prior item 1 — CONTRIBUTING.md flat-layout references**
- Repository structure diagram now uses `src/nodus/` paths throughout (`src/nodus/frontend/lexer.py`, `src/nodus/compiler/`, etc.).
- `pip install -r requirements-dev.txt` changed to `pip install -r requirements.txt` (line 98).
- `LANGUAGE_SPEC.md` bare reference updated to `docs/language/LANGUAGE_SPEC.md` (line 213).
- The `LANGUAGE_SPEC.md` reference at the prior-audit "line 50" is now absent — the structure block no longer references it there.

**RESOLVED — DEVELOPMENT.md file references**
`docs/onboarding/DEVELOPMENT.md` now uses full `src/nodus/` paths for all 7 core component files (lexer, parser, ast_nodes, compiler, vm, task_graph, workflow_lowering).

**RESOLVED — Prior item 7 — llms.txt**
`llms.txt` now exists at project root. It contains:
- Project name header and one-sentence canonical definition naming Nodus, Shawn Knight, and the Masterplan Infinite Weave ecosystem.
- Creator section: "Shawn Knight — creator of Nodus and architect of the Masterplan Infinite Weave ecosystem."
- Key concepts section defining Nodus, Masterplan Infinite Weave, Infinity Algorithm, NodusRuntime, and Task graph.
- Links to 8 documents (README, LANGUAGE_SPEC, ARCHITECTURE, NODUS.md, BYTECODE_REFERENCE, CHANGELOG, CONTRIBUTING, SECURITY).
- README.md links to `llms.txt`.

**RESOLVED — README.md completeness**
README.md now includes:
- Creator attribution: "created by **Shawn Knight** as part of the Masterplan Infinite Weave ecosystem"
- Canonical one-sentence definition referencing the Infinity Algorithm
- CI badge (`actions/workflows/ci.yml`), PyPI badge, license badge
- Documentation section linking to language spec, architecture, changelog, contributing guide, and llms.txt

**RESOLVED — AISO: Infinity Algorithm and Masterplan Infinite Weave now defined**
Both concepts are defined in `llms.txt` and `README.md` in one-sentence extractable form. Prior audit flagged both as absent from all documentation.

**RESOLVED — AISO: Shawn Knight now in human-readable docs**
Shawn Knight is now named as creator in README.md (prominent paragraph) and llms.txt (dedicated Creator section), not only in `pyproject.toml`.

**PERSISTS — SECURITY.md unformatted**
`SECURITY.md` remains plain text without Markdown headers (`#`) or tables. The "Supported Versions" block uses plain text columns, not a Markdown table. GitHub Security Advisories will not parse it as structured data.

**PERSISTS — TECH_DEBT.md vm.py line count stale**
`docs/governance/TECH_DEBT.md:94` still records "`vm.py` line count: ~2,371 lines as of v1.0." Actual current count: 2,418. Noted in the prior audit; not updated.

**PERSISTS — TECH_DEBT.md max_frames note stale**
`docs/governance/TECH_DEBT.md:39` still lists "VM call stack has no explicit max depth check" without a ✅ resolved marker. The check exists in `vm.py:1518` and `vm.py:2071`. See also Section 1 NEW finding.

**PERSISTS — No JSON-LD/schema.org metadata**
No `SoftwareApplication` JSON-LD block in README or any HTML file. No schema.org structured metadata anywhere in the project.

**PERSISTS — No AUTHORS/CONTRIBUTORS file**
No `AUTHORS` or `CONTRIBUTORS` file at the project root.

**PERSISTS — NODUS.md lacks creator attribution**
`docs/onboarding/NODUS.md` (57 lines) does not name Shawn Knight. Attribution now exists in README.md and llms.txt but not in the dedicated onboarding doc.

**PERSISTS — CONTRIBUTING.md lacks Markdown heading markup**
All section headers in `CONTRIBUTING.md` are plain text (no `#` prefix). The file renders as a wall of text without a heading hierarchy on GitHub or in any Markdown renderer. This was present in the prior audit but not individually flagged — the prior finding focused on content staleness. The structure is functionally correct but visually unnavigable.

### Missing artifacts (updated)

| Artifact | Prior | Current |
|----------|-------|---------|
| `llms.txt` | Missing | **Present** |
| `requirements-dev.txt` | Missing (referenced in CONTRIBUTING.md) | N/A — CONTRIBUTING.md now references `requirements.txt` which exists |
| `AUTHORS` or `CONTRIBUTORS` | Missing | Still missing |
| JSON-LD / schema.org metadata | Missing | Still missing |
| `SECURITY.md` proper Markdown | Missing | Still missing |

---

## 4. Security & Dependency Hygiene

### Delta findings

**RESOLVED — Prior item 6/4 — exec() in frontend/types.py**
`src/nodus/frontend/types.py` no longer uses `exec(compile(...))`. No injection vector was ever present, but the pattern was fragile and non-portable. Now resolved.

**RESOLVED — Prior item 4 — fastapi/uvicorn upper-bound pins**
`pyproject.toml [project.optional-dependencies]`:
- `fastapi>=0.111.0,<1` (was `fastapi` — fully unpinned)
- `uvicorn>=0.30.0,<1` (was `uvicorn` — fully unpinned)

A `pip install "nodus-lang[server]"` now cannot pull fastapi 1.x or uvicorn 1.x. The dev venv remains at the tested versions (0.111.0 / 0.30.0).

**PERSISTS — starlette major version gap**
starlette 0.37.2 (dev venv) vs. latest 1.0.1. Active `PendingDeprecationWarning` from starlette importing `python_multipart` is suppressed in `pyproject.toml` `filterwarnings`. No update since the prior audit.

**PERSISTS — VM.allowed_paths default None**
`VM.allowed_paths` defaults to `None` (unrestricted) at `vm.py:149`. Documented in TECH_DEBT.md as opt-in. Unchanged.

**PERSISTS — certifi and idna outdated**
certifi: 2026.2.25 (latest 2026.5.20). idna: 3.11 (latest 3.16). Both are security-relevant bundles; neither has been updated.

**PERSISTS — No hardcoded credentials**
No hardcoded credentials found. `secrets.token_hex(16)` still used for session ID generation. No subprocess/os.system calls in `src/`. Unchanged.

### Outdated dependencies (updated)

| Package | Current | Latest | Delta vs prior audit |
|---------|---------|--------|----------------------|
| starlette | 0.37.2 | 1.0.1 | Unchanged |
| fastapi | 0.111.0 | 0.136.1 | Now pinned `>=0.111.0,<1` in extras |
| uvicorn | 0.30.0 | 0.47.0 | Now pinned `>=0.30.0,<1` in extras |
| certifi | 2026.2.25 | 2026.5.20 | Latest moved (security bundle) |
| idna | 3.11 | 3.16 | Unchanged |
| pydantic | 2.12.5 | 2.13.4 | Unchanged |
| pydantic_core | 2.41.5 | 2.47.0 | Latest moved from 2.46.4 → 2.47.0 |
| pytest | 8.2.0 | 9.0.3 | Unchanged |
| python-multipart | 0.0.22 | 0.0.29 | Unchanged |
| setuptools | 65.5.0 | 82.0.1 | Unchanged |
| pip | 24.0 | 26.1.1 | Unchanged |
| click | 8.3.1 | 8.4.1 | Unchanged |
| anyio | 4.12.1 | 4.13.0 | Unchanged |
| requests | 2.33.1 | 2.34.2 | Unchanged |
| urllib3 | 2.6.3 | 2.7.0 | Unchanged |
| watchfiles | 1.1.1 | 1.2.0 | Unchanged |
| cmake | 4.2.3 | 4.3.2 | Unchanged |
| build | 1.4.4 | 1.5.0 | NEW — not in prior outdated list |
| rich | 14.3.3 | 15.0.0 | NEW — major version available |
| typer | 0.24.1 | 0.25.1 | NEW — not in prior outdated list |
| packaging | 26.0 | 26.2 | NEW — not in prior outdated list |
| markdown-it-py | 4.0.0 | 4.2.0 | NEW — not in prior outdated list |
| Pygments | 2.19.2 | 2.20.0 | NEW — not in prior outdated list |
| zipp | 3.23.0 | 4.1.0 | NEW — not in prior outdated list |
| ujson | 5.12.0 | 5.12.1 | NEW — not in prior outdated list |
| orjson | 3.11.7 | 3.11.9 | NEW — not in prior outdated list |
| nh3 | 0.3.4 | 0.3.5 | NEW — not in prior outdated list |
| jaraco.functools | 4.4.0 | 4.5.0 | NEW — not in prior outdated list |
| rich-toolkit | 0.19.7 | 0.19.10 | NEW — not in prior outdated list |
| xdis | 6.3.0.dev0 | 6.3.0 | NEW — editable install, dev pre-release |

---

## New findings

**NEW-1 — CI fails on every push (lint backlog not gated) — HIGH**
`files: .github/workflows/ci.yml, pyproject.toml`
The `Lint` step (`ruff check .`) was added without configuring a ruff baseline, per-file `# noqa` suppression, or `[tool.ruff.per-file-ignores]` in `pyproject.toml`. All 66 remaining lint errors are unfixed, so the step exits with code 1 on every push. CI is currently broken for the `main` branch. The TECH_DEBT.md acknowledges this was intentional but records no remediation plan or timeline.

**NEW-2 — TECH_DEBT.md has two stale open-item notes — LOW**
`file: docs/governance/TECH_DEBT.md`
- Line 39: "VM call stack has no explicit max depth check." The check has been implemented: `vm.py:1518` guards `call_closure` and `vm.py:2071` guards the `CALL` opcode path. The item was never marked ✅.
- Line 94: "`vm.py` line count: ~2,371 lines as of v1.0." Current count: 2,418 lines. This note was also flagged in the prior audit and has not been updated.

**NEW-3 — CONTRIBUTING.md lacks Markdown heading markup — LOW**
`file: CONTRIBUTING.md`
All section titles (e.g., "Project Philosophy," "Repository Structure," "Development Setup," "Running Tests") are plain text with no `#` prefix. The file renders as a continuous wall of text on GitHub. Prior audit focused on content staleness; the formatting issue was not individually recorded.

---

## Updated Top 10 Priority Items

1. **CI fails on every push — lint backlog not remediated (CI/CD)** — The `ruff check .` step gates all merges but 66 legacy errors remain. Either add a ruff `extend-ignore` or `per-file-ignores` for the known backlog (and enforce zero-new-error policy), or fix the errors. Until resolved, no CI-gated workflow is functional.

2. **starlette 0.37.2 → 1.0.1 major version gap (Security/Deps)** — Active `PendingDeprecationWarning` suppressed by `pyproject.toml`; starlette is 25+ minor versions behind and over a full major version behind. May contain patched CVEs. Update requires coordinating fastapi compatibility.

3. **certifi and idna outdated (Security/Deps)** — certifi 2026.2.25 vs. 2026.5.20; idna 3.11 vs. 3.16. Both are security-relevant dependency bundles that should be updated promptly.

4. **Duplicate `import threading` in services/server.py:12 and :48 (Code Quality)** — Triggers ruff F811. One-line fix; blocking lint resolution (contributes to NEW-1 above).

5. **Remaining 46 F401 unused imports across source and tests (Code Quality)** — Distributed across `lsp/server.py`, `orchestration/workflow_lowering.py`, `runtime/errors.py`, `services/server.py`, `builtins/collections.py`, and multiple test files. Auto-fixable via `ruff check --fix`; blocking lint resolution.

6. **SECURITY.md unformatted plain text (Documentation)** — No Markdown headers or table markup. GitHub Security Advisories cannot parse structured version support data from it.

7. **TECH_DEBT.md stale open-item notes (Documentation)** — Two entries describe issues that no longer exist in code: max_frames enforcement (vm.py:1518) and vm.py line count (~2,371 vs. actual 2,418). Misleads contributors investigating security or architecture.

8. **No coverage gate or pytest-cov configured (CI/CD)** — No per-module coverage data available. The test suite gap (pytest 414 vs. unittest 368) persists; no visibility into which modules have low coverage.

9. **CONTRIBUTING.md lacks Markdown heading markup (Documentation)** — All section titles are plain text; file is unnavigable on GitHub without rendered headings.

10. **No AUTHORS/CONTRIBUTORS file; NODUS.md lacks creator attribution (Documentation)** — Shawn Knight is now named in README.md and llms.txt, but `docs/onboarding/NODUS.md` (the primary onboarding summary) has no creator attribution, and no formal AUTHORS file exists.
