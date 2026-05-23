# Nodus Audit Report
**Date:** 2026-05-21
**Auditor:** Claude Code

---

## Summary

Nodus 1.1.2 is a well-structured bytecode-compiled scripting runtime with a clean lexer → parser → AST → compiler → VM pipeline and a comprehensive test suite. The core language pipeline is clearly separated, the opcode set is frozen, and 413 of 414 collected tests pass. The primary weaknesses are: (1) a significant doc/CONTRIBUTING divergence from the actual `src/nodus/` package layout inherited from a pre-refactor flat layout; (2) one pytest-only test file that is silently excluded from the CI's `unittest`-based runner; (3) 77 ruff lint errors dominated by unused imports in a compatibility shim module; and (4) `pyproject.toml`'s optional `[server]` extras ship unpinned `fastapi`/`uvicorn` dependencies that can pull breaking versions. No hardcoded secrets were found and no subprocess or `os.system` calls exist in non-test code.

---

## 1. Code Quality & Architecture

### Findings

**Module structure**
- Package layout (`src/nodus/{frontend,compiler,vm,runtime,tooling,services,orchestration,builtins,lsp,dap,cli,stdlib}`) matches the documented architecture in `docs/runtime/ARCHITECTURE.md`. The pipeline is correctly separated.
- `vm/vm.py` (2,418 lines) remains the largest file. It contains the core dispatch loop, all reflection builtins, workflow/goal/agent/memory dispatch builtins, and coroutine helpers. The `BuiltinRegistry` extraction framework exists but workflow/goal/agent/memory builtins remain inline in `VM.__init__` rather than being extracted into category modules.
- `cli/cli.py` (1,562 lines) imports from 24 internal nodus modules — acts as a hub/God module for the CLI surface.
- `tooling/runner.py` (1,126 lines) likewise imports from 24 internal modules.
- `services/server.py` has a duplicate `import threading` at lines 12 and 48.

**`__init__.py` logic beyond re-exports**
- `src/nodus/__init__.py`: Contains a `__getattr__` lazy loader for `VM`, plus `run_source()`, `resolve_imports()`, and `main()` wrapper functions with docstrings. Exceeds pure re-export responsibility.
- `src/nodus/builtins/__init__.py`: Houses the full `BuiltinRegistry` class implementation (57 lines including `register_all`). This is logic, not a re-export; the class would be better placed in `builtins/registry.py`.

**Undefined name / broken shim**
- `nodus.py:23`: References `main` which is never explicitly imported or assigned in that file. The shim uses `spec.loader.exec_module()` to populate the module namespace, so `main` is only available if the exec succeeds — but ruff correctly flags this as `F821 Undefined name 'main'`. Running `python nodus.py` directly as a script would raise `NameError` because `main` is not in local scope at that point.

**exec() in non-test code**
- `src/nodus/frontend/types.py:8`: Uses `exec(compile(_f.read(), _stdlib_types_path, "exec"), _stdlib_namespace)` to load Python's own stdlib `types.py` into a fresh namespace and re-export its contents alongside Nodus-specific type objects. The path is constructed from `os.path.dirname(os.__file__)` (Python stdlib directory) — not user input — so there is no injection vector. However, the `exec()` pattern is fragile: it depends on the internal structure of CPython's `types.py` and could break on PyPy, alternative Python distributions, or future CPython versions that restructure that file.

**Missing type annotations on public interfaces**
- `vm/vm.py`: 181 public methods have no parameter annotations out of 181 total (0% annotated).
- `services/server.py`: 62 methods unannotated.
- `tooling/loader.py`: 54 methods unannotated.
- `lsp/server.py`: 45 methods unannotated.
- `frontend/parser.py`: 44 methods unannotated.
- No mypy or pyright configured (`mypy` is not installed in the venv).

**Dead code / unreachable branches**
- `vm/vm.py:1638–1651`: `_op_load_local` handler is an intentional tombstone that raises `RuntimeError` — not dead code, but documents that `LOAD_LOCAL` was removed from the dispatch table at v1.0.
- `compiler/compiler.py`: TECH_DEBT.md previously noted unreachable `For`/`ForEach` branches at lines 513/515; these have since been resolved — the relevant `return` guards are in place.
- `src/nodus/runtime/project.py:4–14`: Imports `DependencySpec`, `create_project`, `find_project_root`, `load_manifest`, `load_project`, `load_project_from`, and `parse_dependencies` from `tooling.project` — none of these are referenced anywhere in the file body (ruff F401 ×7). The module exists only to expose `resolve_dependencies` and `install_dependencies` helpers.

**Stale TODO/FIXME**
- No `# TODO` or `# FIXME` comments found in `src/`. TECH_DEBT.md tracks open items in prose form.
- Two `# type: ignore` suppressions: `orchestration/workflow_lowering.py:240` and `tooling/user_config.py:17` (tomllib import fallback).

**Language pipeline layer discipline**
- `frontend/types.py` runs `exec()` at import time, which is a side-effect-on-import pattern. This is an unusual approach compared to a direct `from types import *`.
- `orchestration/` correctly lives outside `runtime/` and `vm/` — good separation.
- `vm.py` imports directly from `services/agent_runtime`, `services/memory_runtime`, and `services/tool_runtime`, coupling the VM to the agent/tool service layer. This means the VM cannot run standalone without the services infrastructure.

### Metrics

**Ruff (77 errors total)**

| Code | Count | Description |
|------|-------|-------------|
| F401 | 55 | Unused imports |
| E402 | 12 | Module-level import not at top of file |
| F841 | 6 | Local variable assigned but never used |
| E401 | 2 | Multiple imports on one line (`tmp_demo/`) |
| F811 | 1 | Redefined while unused |
| F821 | 1 | Undefined name (`nodus.py:23` — `main`) |

59 errors are auto-fixable. `tmp_demo/` contributes 3 errors (E401×2, F401×1); excluding it the source count is 74.

**Notable individual ruff findings**
- `src/nodus/runtime/project.py`: 7 unused imports (F401)
- `src/nodus/lsp/server.py:33`: `ModuleAlias` imported but unused (F401)
- `src/nodus/lsp/server.py:868`: `err` bound but never used (F841)
- `src/nodus/orchestration/task_graph.py:416`: `scheduler_hint` assigned but never used (F841)
- `src/nodus/orchestration/task_graph.py:937`: `by_id` assigned but never used (F841)
- `src/nodus/orchestration/workflow_lowering.py:47`: `WorkflowStateDecl` imported but unused (F401)
- `src/nodus/runtime/errors.py:5`: `field` from `dataclasses` imported but unused (F401)
- `nodus.py:23`: `F821 Undefined name main`
- `services/server.py:48`: duplicate `import threading` (covered by F401)

**mypy:** Not installed — no type-check results available.

**Module line counts (top 6)**

| File | Lines |
|------|-------|
| `vm/vm.py` | 2,418 |
| `cli/cli.py` | 1,562 |
| `tooling/runner.py` | 1,126 |
| `lsp/server.py` | 1,028 |
| `services/server.py` | 1,267 |
| `runtime/module_loader.py` | 941 |

---

## 2. Test Coverage & CI/CD

### Findings

**Test runner divergence — silent gap**
- `tests/test_formatter_foreach.py` is written as a bare pytest function (`def test_format_foreach():`) with no `unittest.TestCase`. The CI pipeline runs `python -m unittest discover -s tests -v` which discovers **0 tests** from this file. The test only runs under `pytest`. The unittest runner reports `Ran 368 tests`; pytest collects 414 (413 pass, 1 skip). The gap is the 1 pytest-only test in `test_formatter_foreach.py` plus the skipped test.
- This is a known pattern from the project's prior conversion of `test_formatter_coverage.py` from pytest to unittest (v0.9.0) — `test_formatter_foreach.py` was not converted.

**Test categories**
- Language-level spec tests (execute `.nd` source via `run_source`/`ModuleLoader`): ~40 files covering closures, coroutines, destructuring, exceptions, finally, foreach, imports, methods, records, scope, stdlib, and workflows.
- Unit/integration tests: ~30 files covering CLI, AST serialization, formatter fixtures, LSP, DAP, registry client, sandbox, sessions, snapshots, and server endpoints.
- No dedicated integration test directory or category label — all tests live flat in `tests/`.
- No performance regression tests (benchmark exists as `examples/benchmark.nd` but is not wired to CI).

**CI/CD workflow (`ci.yml`) findings**
- **No lint step**: `ruff`, `flake8`, or any linter is not invoked. The 77 ruff errors are invisible to CI.
- **No coverage gate**: `pytest-cov` is not installed; no coverage threshold enforced.
- **Auto-format + git commit step**: The workflow auto-formats `.nd` files and commits the result with `permissions: write`. This modifies the commit history on every push and can cause conflicts when a developer pushes immediately after the CI bot commits. The step also runs before tests, meaning a format-only commit can pass CI without any test gate attached to it.
- **Action versions**: `actions/checkout@v4` and `actions/setup-python@v5` are unpinned to specific SHAs. They resolve to the latest patch within the major version — acceptable for most projects but not hermetically reproducible.
- **Installed wheel smoke test**: Present — `test_distribution_smoke.py` is run in a separate step with `NODUS_RUN_DIST_SMOKE=1`. Good practice.
- **Example suite**: `nodus.py test-examples` is run. No failure reporting format specified.
- **No branch protection / required status checks** configured in the workflow file itself (these would be repo settings, not CI YAML).
- **Static checks step**: Runs `nodus check` on two example files only — not a project-wide static analysis pass.

### Metrics

**pytest run**
- 413 passed, 1 skipped, 0 failed — 12.86s
- Skipped: 1 (distribution smoke test gated on `NODUS_RUN_DIST_SMOKE` env var)

**unittest discover run**
- 368 tests collected and run — 9.2s
- Gap vs pytest: 46 tests (45 in pytest-collected test files that use `unittest.TestCase` but are only discovered by pytest, plus 1 bare pytest function)

**Coverage:** `pytest-cov` not installed in the project venv. No per-module coverage data available.

---

## 3. Documentation & AISO Indexing

### Findings

**Stale flat-layout references in CONTRIBUTING.md**
- `CONTRIBUTING.md:27–51` shows a repository structure diagram using the old flat layout (`lexer.py`, `parser.py`, `ast_nodes.py`, `compiler.py`, `vm.py`, `runner.py`, `api.py`, `cli.py` all at the root). The actual package lives under `src/nodus/{frontend,compiler,vm,tooling,services}/`. This diagram would mislead any new contributor.
- `CONTRIBUTING.md:50` references `LANGUAGE_SPEC.md` at the project root. The actual path is `docs/language/LANGUAGE_SPEC.md`.
- `CONTRIBUTING.md:75` instructs `pip install -r requirements-dev.txt`. This file does not exist — only `requirements.txt` exists.
- `CONTRIBUTING.md:190` says "Update LANGUAGE_SPEC.md" (bare filename) without the `docs/language/` path.

**Stale references in DEVELOPMENT.md**
- `docs/onboarding/DEVELOPMENT.md:28,44,52,60,88,106` references all core files by bare name (`lexer.py`, `parser.py`, `ast_nodes.py`, `compiler.py`, `vm.py`) without package paths. These exist under `src/nodus/frontend/`, `src/nodus/compiler/`, and `src/nodus/vm/` respectively.

**Minor stale reference in TECH_DEBT.md**
- `docs/governance/TECH_DEBT.md:94` states `vm.py` line count is `~2,371 lines as of v1.0`. Actual current count is 2,418 lines.

**SECURITY.md formatting**
- `SECURITY.md` is plain text without proper Markdown headers or tables despite the `.md` extension. The "Supported Versions" table is formatted as plain text, not a Markdown table. GitHub's Security Advisories will not parse it as structured data.

**README completeness**
- `README.md` is concise (84 lines) — appropriate for a project of this scale. However it contains no:
  - One-sentence canonical definition of what Nodus is (beyond "a scripting language runtime")
  - Creator/author attribution
  - Link to the language spec or architecture docs
  - Badge/status indicators (CI, PyPI version, license)

**AISO readiness**
- `llms.txt` — **absent**. No machine-readable document exists at the project root for AI crawler indexing.
- `robots.txt` — **absent** (N/A for a code repository but noted).
- No JSON-LD, schema.org `SoftwareApplication`, or other structured metadata.
- The concept "Infinity Algorithm" does not appear in any current documentation (removed with AINDY concepts in v1.1.0). There is no canonical definition document for this concept or its relationship to Nodus.
- "Masterplan Infinite Weave" — no mention anywhere in docs.
- "Shawn Knight" appears only in `pyproject.toml` as the package author. No human-readable doc (README, NODUS.md, any concept doc) identifies the creator.
- `docs/onboarding/NODUS.md` is the most machine-readable summary of the project but lacks: creator attribution, SPDX license identifier, canonical concept definitions, and cross-references to the language spec.
- No canonical anchoring document defines Nodus, its relationship to the Infinity Algorithm, or the Masterplan Infinite Weave in one-sentence extractable form.

**Documentation completeness**
- Present: README, CHANGELOG, ARCHITECTURE, LANGUAGE_SPEC, CONTRIBUTING, CODE_OF_CONDUCT, SECURITY, AGENTS.md, extensive governance docs.
- `docs/language/LANGUAGE_SPEC.md` is comprehensive and current.
- `docs/runtime/ARCHITECTURE.md` is accurate to the current `src/nodus/` layout.
- No `ARCHITECTURE.md` at the project root — architecture docs live only under `docs/runtime/`.
- No `AUTHORS` or `CONTRIBUTORS` file.

### Missing Artifacts

- `llms.txt` — AI crawler index file
- `requirements-dev.txt` — referenced in CONTRIBUTING.md but does not exist
- Root-level `ARCHITECTURE.md` shortcut (or pointer from README)
- Canonical concept definition document for Nodus / Infinity Algorithm / Masterplan Infinite Weave
- `AUTHORS` or `CONTRIBUTORS` file with creator attribution
- PyPI badge, CI badge, license badge in README
- `docs/onboarding/DEVELOPMENT.md` updated to `src/nodus/` package paths

---

## 4. Security & Dependency Hygiene

### Findings

**eval/exec in non-test source**
- `src/nodus/frontend/types.py:8`: `exec(compile(_f.read(), _stdlib_types_path, "exec"), _stdlib_namespace)` — executes CPython's own `types.py` stdlib file at import time. The path is derived from `os.path.dirname(os.__file__)` (not user input), so there is no injection vector. However: (a) this pattern will silently break on PyPy or any Python distribution where `types.py` is not a regular file at that path; (b) changes to CPython's internal `types.py` structure across Python versions could corrupt the `types` namespace for Nodus modules; (c) this can mask `ImportError`s and makes static analysis tools unable to resolve the types. This is the only `exec()` call in non-test source.

**File I/O sandbox**
- `VM.allowed_paths` is opt-in and remains `None` (unrestricted) by default. CLI and server wiring exists, but embedding users who instantiate `NodusRuntime` without `allowed_paths=` get unrestricted file access to the entire filesystem. Documented in TECH_DEBT.md as a known item.

**VM call stack depth**
- No explicit max frame depth check in `vm.py`. A deeply recursive or malicious Nodus script can overflow Python's own recursion limit but will produce a Python `RecursionError` rather than a clean `LangRuntimeError`. The `max_frames` field exists on `VM` but is not enforced in `call_closure`. Documented in TECH_DEBT.md.

**HTTP server bearer token**
- `services/server.py`: Bearer-token auth is opt-in. Non-local binding requires a token, but local-only binding (`127.0.0.1`) does not enforce auth by default. This is consistent with the documented design but means any process on the same host can reach an unprotected local server.

**Hardcoded credentials**
- None found. `secrets.token_hex(16)` is used correctly for session ID generation in `runtime/sessions.py`.

**Subprocess / os.system calls**
- None found in `src/` (non-test source).

**Unpinned dependencies in published package**
- `pyproject.toml` `[project.optional-dependencies]` lists `"fastapi"` and `"uvicorn"` without version pins. A `pip install "nodus-lang[server]"` will pull the latest release. Current latest is `fastapi==0.136.1` (vs development pin of `0.111.0`) and `uvicorn==0.47.0` (vs `0.30.0`) — both are major-minor version jumps that may contain breaking API changes.
- `requirements.txt` pins `pytest==8.2.0`, `fastapi==0.111.0`, `uvicorn==0.30.0` for development — good.
- Core `dependencies = []` in `pyproject.toml` — no unpinned runtime dependencies.

**SECURITY.md**
- Present but unformatted (plain text despite `.md` extension). No CVE/advisory disclosure process email is specified beyond "email the maintainer."

### Outdated Dependencies

| Package | Current | Latest | Notes |
|---------|---------|--------|-------|
| fastapi | 0.111.0 | 0.136.1 | Unpinned in published extras |
| uvicorn | 0.30.0 | 0.47.0 | Unpinned in published extras |
| starlette | 0.37.2 | 1.0.1 | Major version; DeprecationWarning tracked in DEPRECATIONS.md |
| pytest | 8.2.0 | 9.0.3 | Dev dep; pinned |
| pydantic | 2.12.5 | 2.13.4 | — |
| pydantic_core | 2.41.5 | 2.46.4 | — |
| setuptools | 65.5.0 | 82.0.1 | Build backend |
| pip | 24.0 | 26.1.1 | — |
| click | 8.3.1 | 8.4.1 | — |
| certifi | 2026.2.25 | 2026.5.20 | Security bundle; should be updated |
| idna | 3.11 | 3.16 | Security-relevant; should be updated |
| python-multipart | 0.0.22 | 0.0.29 | — |
| requests | 2.33.1 | 2.34.2 | — |
| anyio | 4.12.1 | 4.13.0 | — |
| cmake | 4.2.3 | 4.3.2 | — |
| urllib3 | 2.6.3 | 2.7.0 | — |
| watchfiles | 1.1.1 | 1.2.0 | — |

---

## Top 10 Priority Items

1. **`CONTRIBUTING.md` flat-layout references (Docs)** — The repository structure diagram, file paths, `LANGUAGE_SPEC.md` location, and `requirements-dev.txt` reference are all stale from the pre-`src/` refactor. A new contributor following these instructions will be immediately confused. Also affects `docs/onboarding/DEVELOPMENT.md`.

2. **`test_formatter_foreach.py` excluded from CI (CI/CD)** — The pytest-only `test_format_foreach` function is silently not run by the CI `python -m unittest discover` step. Either convert the file to a `unittest.TestCase` class or add a `pytest` step to CI.

3. **No lint step in CI (CI/CD)** — 77 ruff errors (55 unused imports, 12 E402, 6 unused variables, 1 undefined name) are invisible to CI. Adding `ruff check .` would catch these on every push.

4. **Unpinned server extras in `pyproject.toml` (Security/Deps)** — `fastapi` and `uvicorn` are unpinned in `[project.optional-dependencies]`. A `pip install "nodus-lang[server]"` today pulls `fastapi 0.136.1` and `uvicorn 0.47.0` instead of the tested `0.111.0` / `0.30.0`. Pin with `>=0.111.0,<1.0` or use the same exact versions as `requirements.txt`.

5. **`nodus.py:23` undefined name `main` (Code Quality)** — The compatibility shim's `if __name__ == "__main__": raise SystemExit(main())` references `main` which is not guaranteed to be in local scope after `spec.loader.exec_module()`. Should use an explicit `from nodus import main` or `from nodus.cli.cli import main`.

6. **`src/nodus/frontend/types.py:8` exec() pattern (Security/Code Quality)** — Using `exec(compile(...))` to extend the Python `types` module is fragile and non-portable. Should be replaced with `from types import *` followed by the Nodus-specific exports, or by explicitly listing what is needed from `types`.

7. **`llms.txt` absent (AISO Indexing)** — No machine-readable project index exists for AI crawlers. At minimum, `docs/onboarding/NODUS.md` should be linked or promoted, and a root-level `llms.txt` should be created pointing to key documents with canonical one-sentence definitions of Nodus, its creator (Shawn Knight), and related concepts.

8. **`src/nodus/runtime/project.py` — 7 unused imports (Code Quality)** — This compatibility shim imports `DependencySpec`, `create_project`, `find_project_root`, `load_manifest`, `load_project`, `load_project_from`, and `parse_dependencies` but uses none of them. These are dead re-exports that pollute the module's public surface.

9. **`starlette` / `fastapi` major version gap (Security/Deps)** — `starlette 0.37.2` → `1.0.1` is a major version jump. DEPRECATIONS.md documents an active `DeprecationWarning` from `starlette` importing `python_multipart`. The dev environment is 25 minor versions behind on `fastapi`. These outdated versions may contain patched CVEs.

10. **Auto-format CI step creates history mutations (CI/CD)** — The `ci.yml` auto-format + git-commit step runs with `permissions: write` and commits directly to the branch on every push. This can create conflicts when developers push quickly after each other, and it means CI produces commits that were never reviewed by a human. Consider moving format enforcement to a lint-only check (`--check` flag) rather than a mutating commit.
