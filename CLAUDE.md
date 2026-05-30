# Nodus — Claude Instructions

## Project identity

Nodus (`nodus-lang` on PyPI) is a bytecode-compiled scripting language and
runtime implemented in Python. Working directory: `C:\dev\Coding Language`.
Source lives under `src/nodus/`. Tests under `tests/`.

## Running code during development

The project `.venv` has an older PyPI install that takes precedence over
`src/` in `sys.path`. Always prefix with `PYTHONPATH` to get the dev source:

```powershell
PYTHONPATH="C:/dev/Coding Language/src" "C:/dev/Coding Language/.venv/Scripts/python.exe" ...
PYTHONPATH="C:/dev/Coding Language/src" "C:/dev/Coding Language/.venv/Scripts/nodus.exe" run script.nd
PYTHONPATH="C:/dev/Coding Language/src" "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/
```

Without `PYTHONPATH`, you get the installed package, not the current source.
Verify with: `nodus --version` — should match `src/nodus/support/version.py`.

## GitHub API

The `gh` CLI **is installed** and authenticated as `Masterplanner25`. Use it
directly for issue/PR/release operations:

```powershell
gh issue create --title "..." --body "..."
gh repo create Masterplanner25/name --public
gh release create vX.Y.Z --notes "..."
```

For raw API calls not covered by `gh`, use `urllib.request` with a token
retrieved from:

```bash
git credential fill <<< $'protocol=https\nhost=github.com'
```

Repo: `https://api.github.com/repos/Masterplanner25/Nodus`

Standard issue shape:

```python
{
    'title': 'BUG-NNN: short description',
    'body': '## Summary\n\n...\n\n## Reproduction\n\n...\n\n## Expected behavior\n\n...\n\n## Fix direction\n\n...\n\n## Affected versions\n\nv2.1.1 (current).',
    'labels': ['bug', 'subsystem:X', 'severity:low|medium|high|critical'],
    'milestone': 3   # v2.2 milestone
}
```

Write the script to a temp file and run it — inline heredocs with
triple-quoted strings cause PowerShell/Bash quoting issues.

## Version sync — must keep in step

Two files must always match:

- `src/nodus/support/version.py` — `__version__ = "X.Y.Z"`
- `pyproject.toml` — `version = "X.Y.Z"`

Release order: bump both files → move `[Unreleased]` in `CHANGELOG.md` to
the new version section → commit → `git tag vX.Y.Z` → `git push origin main
--tags` → build wheel → upload to PyPI.

PyPI upload — use explicit flags; `~/.pypirc` may have an empty password field
which causes a 403:

```powershell
"C:/dev/Coding Language/.venv/Scripts/python.exe" -m twine upload --username __token__ --password <token> dist/*
```

Token: retrieve from the user at upload time. Never store in any file.

Full release checklist: `docs/release.md`.

## Guide file testing standard

Every code example in `docs/guide/` must be run and produce verbatim output.
Protocol for each guide file:

1. Create a temp test directory: `/tmp/<guide-name>-tests/`
2. Run each example against dev source using the `PYTHONPATH` prefix above
3. Paste output verbatim into the doc — no invented output
4. Any surprising behavior gets a numbered finding (F32, F33, …) in a
   `<!-- TESTED ... -->` comment block at the bottom of the file
5. File behavioral findings as GitHub issues before committing

Guide files live in `docs/guide/`. The full guide index is in
`docs/guide/getting-started.md §7` and `llms.txt`.

## Key file locations

| What | Where |
|------|-------|
| Version | `src/nodus/support/version.py` |
| Changelog | `CHANGELOG.md` |
| Bug/issue list | GitHub Issues (Masterplanner25/Nodus) |
| Semver policy | `docs/release.md#semantic-versioning` |
| Compatibility policy | `docs/governance/COMPATIBILITY_MODEL.md` |
| Deprecation timeline | `docs/governance/COMPATIBILITY.md` |
| Stability index (surface-by-surface) | `docs/governance/LANGUAGE_STABILITY_INDEX.md` |
| Security posture | `docs/governance/SECURITY_POSTURE.md` |
| Release gates | `docs/governance/RELEASE_GATES.md` |
| Tech debt | `docs/governance/TECH_DEBT.md` |
| Docset index (reader entry point) | `docs/governance/DOCSET_INDEX.md` |
| Ecosystem maturity | `docs/governance/ECOSYSTEM_READINESS_ASSESSMENT.md` |
| Runtime invariants | `docs/runtime/EXECUTION_INVARIANTS.md` |
| Failure model | `docs/runtime/FAILURE_AND_DEGRADATION_MODEL.md` |
| Embedder runbook | `docs/runtime/OPERATOR_OR_EMBEDDER_RUNBOOK.md` |
| Guide files | `docs/guide/` |
| Runtime reference docs | `docs/runtime/` |
| Governance docs | `docs/governance/` |
| Release playbook | `docs/governance/RELEASE_PLAYBOOK.md` |
| Skills | `.claude/commands/` |
| Doc-vs-code gate | `tools/nodus_gate/` — run `python -m tools.nodus_gate.cli --all` |
| Library entry-point contract | `docs/guide/library-entry-points.md` |
| nodus-mcp companion repo | `C:\dev\nodus-mcp` / github.com/Masterplanner25/nodus-mcp |
| nodus-a2a companion repo | `C:\dev\nodus-a2a` / github.com/Masterplanner25/nodus-a2a |
| nodus-memory companion repo | `C:\dev\nodus-memory` / github.com/Masterplanner25/nodus-memory |
| nodus-native-memory-engine repo | `C:\dev\nodus-native-memory-engine` / github.com/Masterplanner25/nodus-native-memory-engine |
| nodus-extension companion repo | `C:\dev\nodus-extension` / github.com/Masterplanner25/nodus-extension |
| Ecosystem incubator specs | `docs/ecosystem/` — spec docs for planned libraries |
| Ecosystem incubator scaffolds | `packages/` — Python-first scaffolds for planned libraries |

## Test suite

```powershell
# Full suite
PYTHONPATH="C:/dev/Coding Language/src" "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/ -q

# Coverage (excludes 3 timing-sensitive tests)
PYTHONPATH="C:/dev/Coding Language/src" "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/ --cov=src/nodus --cov-fail-under=60 --ignore=tests/test_scheduler_fairness.py -q
```

Coverage baseline: 77% overall. Gate: 60%. See `docs/governance/TECH_DEBT.md`
for the per-module breakdown and the three deselected flaky tests.

## .nd file formatting — authoritative command

**Always use `python nodus.py fmt` — never `nodus.exe` or bare `nodus fmt`.**

`nodus.exe` in `.venv` is the stale installed package (e.g. old release). CI runs
`python nodus.py fmt --check {}` which loads from `src/` (the dev source). Using
`nodus.exe` writes a format that diverges from what CI checks → commits pass locally
but fail CI. This is the writer-vs-checker split that broke the stdlib format gate
repeatedly across multiple pushes.

To format .nd files correctly (matches CI exactly):
```powershell
# Format one file
python nodus.py fmt src/nodus/stdlib/hash.nd

# Format all stdlib .nd files
python nodus.py fmt src/nodus/stdlib/*.nd

# Verify (verbatim CI check):
find . -name "*.nd" -not -path "./.git/*" -not -path "./.venv/*" -not -path "./tmp_demo/*" -not -path "./tests/fixtures/fmt/*" | xargs -I {} python nodus.py fmt --check {}
```

A pre-commit hook enforces this: if staged `.nd` files fail `python nodus.py fmt --check`,
the commit is blocked and the exact fix command is printed. Hook lives at `.git/hooks/pre-commit`
(not tracked by git — reinstall after fresh clone with `chmod +x .git/hooks/pre-commit`).

## Lint gate (ruff)

Ruff runs in CI and blocks merges. Check locally before pushing:

```powershell
& "C:/dev/Coding Language/.venv/Scripts/python.exe" -m ruff check src/ tests/
```

Two rules come up repeatedly:

- **F401 unused import** — just remove it; never suppress with `# noqa`.
- **E402 module-level import not at top** — occurs in test files that do
  `sys.path.insert` before imports (intentional path isolation pattern).
  Suppress with `# noqa: E402` on each affected import line. Do not
  restructure the path manipulation to avoid it.

**Pre-existing violations:** `ruff check src/` always shows ~33 pre-existing
errors in `src/nodus/vm/vm.py` (E702), `src/nodus/builtins/time_module.py`
(E701, F841), `src/nodus/builtins/encoding_module.py` (F401), and
`src/nodus/builtins/secrets_module.py` (F401). These pre-date Phase 3C and
are known. Do not introduce them into new code, but do not treat them as a
blocker for your own changes. When verifying a commit, run ruff scoped to the
files you actually changed rather than the whole `src/` tree.

## Git commit syntax (PowerShell)

Multi-line commit messages require a PowerShell here-string — bash `<<EOF`
syntax is not valid in PowerShell:

```powershell
git commit -m @'
Subject line here

Body paragraph here.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
'@
```

The closing `'@` must be at column 0 with no leading whitespace. For commits
that need a file (e.g. cross-repo where stdin is awkward), write the message
to `.git\COMMIT_MSG_TEMP` with `Out-File -Encoding utf8` then use
`git commit -F ".git\COMMIT_MSG_TEMP"`.

## Doc-vs-code gate (nodus_gate)

The gate is mandatory before any release. Run from the nodus-lang root:

```powershell
PYTHONPATH="C:/dev/Coding Language/src;C:/dev/Coding Language" `
  "C:/dev/Coding Language/.venv/Scripts/python.exe" `
  -m tools.nodus_gate.cli --all
```

- `--static`: verifies documented symbols exist in the codebase (76 symbols)
- `--runtime`: runs all ` ```nodus ` and ` ```nodus-expect=output ` blocks
  in docs (180 blocks); expects 0 failures with the `.nodusgate-allow`
  allowlist in place
- `--closed-issues`: runs closed-issue tests for CHANGELOG-referenced issues

The allowlist at `.nodusgate-allow` suppresses intentionally non-runnable
doc blocks (multi-file examples, error demos). New failing blocks go in the
allowlist OR are fixed before release.

## nodus-mcp companion library

- Repo: `C:\dev\nodus-mcp` / `github.com/Masterplanner25/nodus-mcp`
- **Status: v0.1.0 COMPLETE — prepared, not yet published.**
  All 14 phases done (Phase 1 design docs + Phases A–N implementation).
  361 tests pass (Phase A–N nodus-lang adapter + aindy bridge adapter tests).
  BYTECODE_VERSION 4, no new opcodes.
  Publication waits for nodus-a2a v0.1.0 (coordinated three-artifact launch).
- **Dual layout**: `src/nodus_mcp/` = full MCP protocol library (Phase A–N);
  `nodus_mcp_aindy/` = aindy-derived bridge adapter (wraps ToolRegistry as MCP server).
  The pyproject.toml `where = ["src"]` installs the Phase A–N library; the aindy
  adapter is importable as `nodus_mcp_aindy` but is not the primary package.
- Dev install: `pip install -e . --no-deps`
- Run tests: `cd C:\dev\nodus-mcp && PYTHONPATH="C:/dev/Coding Language/src" "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/ -q`
- **egg-info pitfall**: If `nodus_mcp.egg-info/` appears in the repo root (generated
  by old `setup.py develop` runs), pytest adds the rootdir to sys.path and
  `importlib.metadata` finds the stale egg-info instead of the site-packages dist-info.
  This breaks entry-point discovery. Fix: `rm -rf nodus_mcp.egg-info && pip install -e . --no-deps`.
  The `*.egg-info/` is in `.gitignore`.
- Entry-point contract: `[project.entry-points."nodus.nd"]` → callable returns
  absolute path to `.nd` root dir — see `docs/guide/library-entry-points.md`
- Key documented contracts (see `docs/governance/TECH_DEBT.md`):
  - TD-007: server-initiated requests over HTTP are stdio-only (no SSE/push)
  - TD-008: `_validate_args` is top-level type checking only (not full JSON Schema)
  - TD-009: resource read handler must raise `KeyError` for unknown URI → -32601
  - TD-010: `requestState` is on the wire; never checkpoint secrets in sentinel state
- **Next: coordinated three-artifact publication** — all three are prepared; push
  and publish nodus-lang 4.0.0 + nodus-mcp 0.1.0 + nodus-a2a 0.1.0 together.

## nodus-a2a companion library

- Repo: `C:\dev\nodus-a2a` / `github.com/Masterplanner25/nodus-a2a`
- **Status: v0.1.0 COMPLETE — all pre-Phase-5 gates passed. Waiting for publish.**
  All 10 phases done (Phase 1 design docs + Phases A–J implementation).
  180 tests pass (includes breakage-gate additions). BYTECODE_VERSION 4, no new opcodes.
  Publication waits for coordinated three-artifact launch with nodus-lang 4.0.0
  and nodus-mcp 0.1.0.
- **Python API:** `runtime.tool_registry.register({...})` — NOT `runtime.register_tool()` (doesn't exist).
- **nodus-a2a issues:** #1 (non-dict args coerced to {}), #2 (exception str verbatim to client).
  Both filed; #2 needs doc note before Phase 5 (or accept as known gap).
- Run tests: `cd C:\dev\nodus-a2a && PYTHONPATH="C:/dev/Coding Language/src" "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/ -q`
- Coverage: 93% (gate: ≥80%). `pyproject.toml` has `pythonpath = ["src"]` so
  only nodus-lang needs to be in PYTHONPATH when running tests.
- Skill: `/nodus-a2a-phase` — start or continue a design doc or implementation phase.
- **A2A protocol facts** (verified during Phase 1 protocol audit):
  - Spec repo: `a2aproject/A2A` (transferred from `google/A2A`)
  - Proto: `specification/a2a.proto` (not `spec/a2a.proto`)
  - Well-known URI: `/.well-known/agent-card.json` (not `agent.json` — that's 0.3)
  - Content-Type: `application/a2a+json` (not `application/json`)
  - HTTP transport only — A2A has no stdio binding anywhere
  - Flask is NOT in the shared venv — transport uses stdlib `ThreadingHTTPServer`
- **D5 (message-only):** server never emits a Task. All task-management paths
  return `UnsupportedOperationError` HTTP 501.
- **D6 inversion (critical for v0.2):** A2A `INPUT_REQUIRED` is park-and-resume
  by design — the OPPOSITE of nodus-mcp's no-thread-parks rule. Do NOT import
  that rule into a2a. See `docs/design/05-deferred-features.md §2`.
- **`BYTECODE_VERSION`** lives at `nodus.compiler.compiler` (not `nodus.vm.vm`).
- Tool dispatch: clients send `DataPart(data={"tool":"<name>","args":{...}})`;
  single-tool agents accept any Message as a fallback.

## Nodus language quirks (relevant when writing test .nd code)

These burn time when forgotten:

- **No `await` keyword.** `test.flush_async()` is synchronous — no `await`.
- **No `+=` operator.** Use `x = x + 1i`. In closures, you can't assign
  outer `let` variables at all — use a map and mutate a field: `state.count = state.count + 1i`.
- **Async test two-flush pattern:** `spawn → flush (task sleeps) → advance_clock(N) → flush (task wakes)`.
  Skipping either flush or the advance causes the test to pass vacuously.
- **`spawn()` takes a coroutine value**, not a function literal. Use
  `let c = coroutine(fn() {...})` then `spawn(c)`.
- **`fn` is a reserved keyword** — can't use as a parameter name in `.nd` files.
- **Multiline list literals and function calls cannot span newlines.** Both
  `[1,\n2]` and `len(\n"hi"\n)` give "Unexpected end of statement". Keep on one line.
- **`print()` is single-argument.** `print("label:", value)` → syntax error.
  Use string interpolation: `print("\(label): \(value)")`.
- **`std:hash` returns a hash record, not a string.** `hash.sha256(data)` returns
  a record with methods; call `.to_hex()` to get hex: `hash.sha256(data).to_hex()`.
- **`std:tool` names must be dotted.** `tool.register({name:"greet",...})` silently
  returns an error. Use `"myapp.greet"`. Error message says "must use dotted namespacing".
- **Coroutine execution limits (scheduler quirk):** The default 200ms deadline
  (`EXECUTION_TIMEOUT_MS=200`) counts wall-clock time including cooperative sleep.
  A coroutine that sleeps 4 × 100ms will be killed after 200ms total even though it
  consumed no CPU. Workaround: `nodus run --time-limit N`. SCHED-001, deferred to 4.0.1.

## Security boundary test rule

Any fix for a security boundary (path traversal, sandbox escape, allowed_paths
enforcement, resource limits) must have tests covering BOTH CLI mode and
`NodusRuntime` embedded mode. The enforcement code path can differ between
contexts. See `docs/governance/TECH_DEBT.md § Testing Methodology`.

## Documentation governance

The governing docset layer was established in a 2026-05-29 sweep. Key rules:

- **`docs/governance/DOCSET_INDEX.md`** — the reader entry point and precedence list.
  When docs conflict, DOCSET_INDEX.md defines which wins.
- **`docs/governance/DOCSET_ALIGNMENT_AUDIT.md`** — 14 findings from the sweep;
  tracks what still needs fixing.
- **`docs/governance/HIGH_CONFLICT_DOC_RECONCILIATION_PLAN.md`** — ranked list
  of still-unresolved doc conflicts.

Remaining doc tasks before Phase 5 publish:
1. ~~nodus-a2a `pyproject.toml` metadata~~ — DONE (added in breakage gate prep)
2. `RELEASE_CHECKLIST.md` post-release section still has old commands — batch to 4.0.1
3. `LIBRARY_ECOSYSTEM.md` STDLIB_PHILOSOPHY.md cross-refs — stub exists; expand post-launch
4. nodus-a2a #2 (exception str verbatim to client) — add doc note or accept as known gap

nodus-mcp spec version: README says "2026-07-28 RC" (authoritative). Verify CHANGELOG reflects it.

## nodus-memory companion library

- Repo: `C:\dev\nodus-memory` / `github.com/Masterplanner25/nodus-memory`
- **Status: v0.1.0 COMPLETE — prepared, not yet published.**
  Phases A–K done. 192 tests, 97% coverage. BYTECODE_VERSION 4, no new opcodes.
  Publication follows the three-artifact launch as a separate, later release.
- **Python API:** `MemoryStore`, `MemoryConfig`, `attach_to_runtime(runtime, store)`
- **Nodus bindings:** `import "nodus-memory"` → `share(k,v)`, `recall_from(k)`,
  `forget(k)`, `recall_all(tag)`, `tag(k,tags)`, `link(child,parent)`
- **Host functions use `_ext_` naming** — no, `nm_` prefix: `nm_recall_from`, `nm_share`, etc.
  (The .nd wrappers are named `recall_from`, `share` etc; the host functions are `nm_*`)
- **nodus-native-memory-engine** auto-detected: if installed, `cosine_similarity()`
  and `ScoreTracker.compute_weight()` route to Rust automatically.
- Dev install: `pip install -e . --no-deps` (from `C:\dev\nodus-memory`)
- Run tests: `cd C:\dev\nodus-memory && PYTHONPATH="C:/dev/Coding Language/src" "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/ -q`
- SQLAlchemy is an optional `[db]` extra; installed in shared venv for tests.

## nodus-native-memory-engine companion library

- Repo: `C:\dev\nodus-native-memory-engine` / `github.com/Masterplanner25/nodus-native-memory-engine`
- **Status: v0.1.0 COMPLETE — prepared, not yet published.**
  PyO3/Maturin Rust extension. 76 tests. Pure-Python fallback for all 9 operations.
  Publication follows nodus-memory.
- **Build requires Rust:** `VIRTUAL_ENV="C:/dev/Coding Language/.venv" maturin develop --release`
  Rust 1.93.1, PyO3 0.22.6, maturin 1.12.6 all installed.
- **9 operations:** `cosine_similarity`, `batch_cosine_similarity`, `compute_weight`,
  `batch_compute_weights`, `argsort_by_weight`, `traverse_chain`, `would_create_cycle`,
  `rank_by_similarity`, `rank_blended`
- `is_native()` → True when Rust extension loaded; falls back to pure Python silently.
- Run tests: `cd C:\dev\nodus-native-memory-engine && "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest -q`

## nodus-extension companion library

- Repo: `C:\dev\nodus-extension` / `github.com/Masterplanner25/nodus-extension`
- **Status: v0.1.0 COMPLETE — prepared, not yet published.**
  Phases A–J done. 126 tests, 93% coverage. BYTECODE_VERSION 4, no new opcodes.
  Publication follows nodus-memory.
- **Purpose:** Typed, versioned, sandboxed plugin framework. Third-party developers
  write `nodus-extension.json` + `extension.py`; the framework loads them via subprocess.
- **Python API:** `ExtensionRegistry`, `ExtensionHost`, `attach_to_runtime(runtime, registry)`
- **Nodus bindings:** `import "nodus-extension"` → `ext_load(path)`, `ext_list()`,
  `ext_invoke(name, tool, args_json)`, `ext_describe(name)`
- **Host functions use `_ext_` prefix** (not `ext_`): `_ext_load`, `_ext_list`, etc.
  The .nd wrappers are named `ext_load`, `ext_list` etc. (same split as nodus-memory)
- **ext_invoke takes args as JSON string** — not a Nodus map. Caller must pass e.g.
  `ext_invoke("myext", "tool.name", "{\"key\": \"value\"}")`.
- **Sandbox tier 1 only** (subprocess, insecure-dev). OCI/VM deferred to v0.2.
- **Capability gate:** extension must declare `"tool.invoke"` to call tools.
- Dev install: `pip install -e . --no-deps` (from `C:\dev\nodus-extension`)
- Run tests: `cd C:\dev\nodus-extension && PYTHONPATH="C:/dev/Coding Language/src" "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/ -q`

## Aindy-derived standalone packages (at `C:\dev\`)

These were extracted from the aindy-runtime codebase. They have no git repos and
do not depend on nodus-lang. Test command for each: `cd C:\dev\<pkg> && python -m pytest -q`.

| Package | Tests | Key deps | Notes |
|---------|-------|----------|-------|
| nodus-circuit-breaker | 24 | none | Three-state CB, sync+async, optional Prometheus |
| nodus-auth | 36 | python-jose, passlib, bcrypt<5.0, pydantic | **bcrypt must be <5.0** — passlib 1.7.4 breaks with bcrypt 5.x |
| nodus-observability | 27 | python-json-logger (otel/prometheus optional) | Structured logging + tracing bootstrap |
| nodus-queue | 53 | tenacity (redis optional) | DLQ, delayed jobs. Redis tests need live Redis — skip with `--ignore=tests/test_redis_backend.py` |
| nodus-state | 73 | none | FlowStatus, AgentStatus, ExecutionContext, ResumeSpec |
| nodus-observability-framework | 43 | nodus-observability, fastapi optional | RequestMetricWriter, middleware, health router |
| nodus-mcp (aindy bridge) | see nodus-mcp section | mcp>=1.0.0 | Bridge adapter lives at `nodus_mcp_aindy/` in the nodus-mcp repo |

## Ecosystem incubators (`packages/` in this repo)

Eight Python-first scaffold packages live at `C:\dev\Coding Language\packages\`.
They are **design references / API contracts**, not production implementations.

- `nodus-a2a-spec`, `nodus-agent`, `nodus-event`, `nodus-events`, `nodus-http`,
  `nodus-memory-spec`, `nodus-retry`, `nodus-store-sql`
- **Never pip-install the `-spec` packages alongside the production packages** —
  `nodus-memory-spec` and `nodus-a2a-spec` share Python module names with the
  production packages in `C:\dev\`. Installing both in the same venv causes import conflicts.
- Run incubator tests from within each package directory:
  ```powershell
  cd "C:\dev\Coding Language\packages\nodus-memory" && python -m pytest -q
  ```
  The `pythonpath = ["src"]` in each package's pytest config provides the import path.
- Spec docs live at `docs/ecosystem/` (NODUS_HTTP.md, NODUS_RETRY.md, etc.)

## Phase 5 publish status (as of 2026-05-30)

All pre-ship gates passed. The only remaining step is the coordinated publish:

**Pre-Phase-5 verification completed:**
- TestPyPI full three-artifact roundtrip: all three from index, site-packages, 14/14 invariants
- Adversarial gate (SCHED-002 fixed, BUG-A2A-001/002 filed)
- Pre-ship eval: 5 fix-before-publish items resolved (BUG-EVAL-01–05)
- Full nodus-lang test suite: 1455 passed

**Rebuild state (2026-05-30):**
- nodus-lang 4.0.0: rebuilt (scheduler.py SCHED-002 fix in wheel)
- nodus-a2a 0.1.0: rebuilt (README quick-start fix in wheel)
- nodus-mcp 0.1.0: prior wheel still valid (no code changes)
- All twine check: PASSED

**Phase 5 publish sequence** (do NOT run until explicitly asked):
1. `git tag v4.0.0 && git push origin main --tags` (nodus-lang)
2. Upload nodus-lang 4.0.0 to real PyPI (token from user at upload time)
3. Confirm `pip install nodus-lang==4.0.0` succeeds
4. Rebuild nodus-mcp and nodus-a2a against the published nodus-lang 4.0.0
5. Upload nodus-mcp 0.1.0 and nodus-a2a 0.1.0 (need per-project PyPI tokens)
6. Create GitHub releases for all three
7. Update ECOSYSTEM_READINESS_ASSESSMENT.md to reflect published status
