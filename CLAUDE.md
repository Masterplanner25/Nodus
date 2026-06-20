# Nodus — Claude Instructions

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
    'body': '## Summary\n\n...\n\n## Reproduction\n\n...\n\n## Expected behavior\n\n...\n\n## Fix direction\n\n...\n\n## Affected versions\n\nv4.0.0 (current).',
    'labels': ['bug', 'subsystem:X', 'severity:low|medium|high|critical'],
    'milestone': None   # check current milestone on GitHub
}
```

Write the script to a temp file and run it — inline heredocs with
triple-quoted strings cause PowerShell/Bash quoting issues.

## GitHub release immutability — permanent gotcha

**Once a release is created against a protected tag, the tag's immutable state is permanent.**
Deleting the release does NOT clear it. Disabling the branch/tag ruleset does NOT clear it.
`gh release create <same-tag>` after deletion returns: "tag_name was used by an immutable release".

Consequences:
- Never create a GitHub release until you are certain the tag points to the right commit
- Artifact swaps (delete + re-upload) are **impossible** for immutable releases
- The only recovery is a new tag (`v4.0.0-fix1`, etc.) — accept the name change or accept the mismatch

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
| Security test matrix | `docs/security/SECURITY_MATRIX.md` |
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
| Companion library contract | `docs/governance/COMPANION_LIBRARY_CONTRACT.md` |
| Pre-publish eval prompt | `docs/governance/EVAL_PREPUBLISH.md` — Gate 10 creator validation |
| Post-publish eval prompt | `docs/governance/EVAL_POSTPUBLISH.md` — Stage 5 independent eval (pointer to template) |
| Stage 4 eval template | `docs/governance/EVAL_STAGE4_TEMPLATE.md` — generalized pre/post-publish template; copy+fill Section 0 & 4 each cycle |
| Eval test scripts | `tests/eval/` — quirk_probe.nd, language_exerciser.nd, framework_capabilities.nd |
| Eval results (per-version) | `docs/evals/` — e.g. `docs/evals/v4.0.0/CREATOR_VALIDATION.md` |
| Audit prompt index | `docs/governance/AUDIT_INDEX.md` — 9 reusable audit prompts (architecture, runtime readiness + bootstrap, boundary integrity, user reality, capability, limits, security model, infinity runtime, real-world capability) |
| Maturity checklist + re-score | `docs/governance/MATURITY_CHECKLIST.md` — 72.5 → 82-83 (2026-05-31) |
| Issue response policy | `docs/governance/ISSUE_RESPONSE_POLICY.md` |
| AI discoverability (canonical map) | `llms.txt` |
| AI discoverability (rich summaries) | `llms-full.txt` |
| GitHub wiki (local) | `C:\dev\Nodus Wiki\nodus-wiki\` — git repo, branch `master`, remote `Masterplanner25/Nodus.wiki.git` |
| nodus-mcp companion repo | `C:\dev\nodus-mcp` / github.com/Masterplanner25/nodus-mcp |
| nodus-a2a companion repo | `C:\dev\nodus-a2a` / github.com/Masterplanner25/nodus-a2a |
| nodus-memory companion repo | `C:\dev\nodus-memory` / github.com/Masterplanner25/nodus-memory |
| nodus-native-memory-engine repo | `C:\dev\nodus-native-memory-engine` / github.com/Masterplanner25/nodus-native-memory-engine |
| nodus-extension companion repo | `C:\dev\nodus-extension` / github.com/Masterplanner25/nodus-extension |
| nodus-mcp-server repo | `C:\dev\nodus-mcp-server` / github.com/Masterplanner25/nodus-mcp-server |
| nodus-jupyter repo | `C:\dev\nodus-jupyter` / github.com/Masterplanner25/nodus-jupyter |
| nodus-vscode repo | `C:\dev\nodus-vscode` / github.com/Masterplanner25/nodus-vscode |
| nodus-run-action repo | `C:\dev\nodus-run-action` / github.com/Masterplanner25/nodus-run-action |
| nodus-workflow repo | `C:\dev\nodus-workflow` / github.com/Masterplanner25/nodus-workflow |
| nodus-sdk repo | `C:\dev\nodus-sdk` / github.com/Masterplanner25/nodus-sdk |
| nodus-store-sql repo | `C:\dev\nodus-store-sql` / github.com/Masterplanner25/nodus-store-sql |
| Ecosystem incubator specs | `docs/ecosystem/` — spec docs for planned libraries |
| Ecosystem incubator scaffolds | `packages/` — Python-first scaffolds for planned libraries |

## Test suite

```powershell
# Full suite
PYTHONPATH="C:/dev/Coding Language/src" "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/ -q

# Coverage (excludes 3 timing-sensitive tests)
PYTHONPATH="C:/dev/Coding Language/src" "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/ --cov=src/nodus --cov-fail-under=70 --ignore=tests/test_scheduler_fairness.py -q
```

Coverage baseline: 76% overall (19,126 stmts, 1,645 tests). Gate: 70% (raised from 60% on 2026-05-31).
See `docs/governance/TECH_DEBT.md` for the per-module breakdown and the three deselected flaky tests.

**Pre-existing flaky tests (pass individually, timing-sensitive in full suite):**
- `test_scheduler_fairness.py::test_long_running_task_rotates_with_budget`

**Flaky test fix pattern — timing headroom:**
Tests that race a sleep against a timeout need **5–10x headroom**, not 2x. Under full-suite parallel
load, a 20ms sleep takes longer than 20ms wall-clock. Rule: if the test sleeps N ms and the code
times out at M ms, ensure M ≥ 5N.

Two classes can't share incompatible timeout requirements. If a test needs `session_timeout_ms=50`
(to observe expiry quickly) and another needs `session_timeout_ms=2000` (to survive load without
expiring), split them into two classes with separate server instances — one per `setUpClass`.

**Sweeper startup race:** `RuntimeService` starts the sweeper thread in `__init__` with the default
interval. If you set `_worker_heartbeat_timeout_ms` after construction, the sweeper sleeps the
default interval (500ms) before adopting the new value. Fix: pass `worker_sweep_interval_ms=N`
directly to the constructor.

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

## PR workflow — required (enforce_admins is ON)

`enforce_admins` is enabled on the `main` branch. **Direct pushes to `main` are rejected for
everyone, including the repo owner.** All changes must go through a branch + PR + CI.

Workflow:
1. `git checkout -b <branch-name>` — create a branch
2. Commit and push: `git push -u origin <branch-name>`
3. `gh pr create --title "..." --body "..."` — open the PR
4. Wait for CI to pass, then merge via `gh pr merge --squash` (or GitHub UI)

Never attempt `git push origin main` directly — it will be rejected.

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

**Regression test convention for `--closed-issues`:** add a `# closes: #N`
comment immediately before the test function that verifies a fix. The
`closed_issues_phase` scanner finds tests by this marker:

```python
# closes: #99
def test_spawn_threads_joined_on_reset(self):
    ...
```

Without the marker, the gate reports the issue as "no test found" and the
closure-verification step in `PLAYBOOK_PATCH_MINOR.md` Stage 3 will fail.

**Golden bytecode tests:** `tests/test_bytecode_golden.py` checks opcode
sequences for core constructs against fixtures in `tests/fixtures/bytecode/`.
Re-generate after intentional compiler changes:

```powershell
NODUS_UPDATE_GOLDEN=1 PYTHONPATH="C:/dev/Coding Language/src" `
  "C:/dev/Coding Language/.venv/Scripts/python.exe" `
  -m pytest tests/test_bytecode_golden.py -q
```

## nodus-mcp companion library

- Repo: `C:\dev\nodus-mcp` / `github.com/Masterplanner25/nodus-mcp`
- **Status: v0.1.0 PUBLISHED on PyPI.**  BYTECODE_VERSION 4, no new opcodes.
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
- Key contracts: TD-007–010 in `docs/governance/TECH_DEBT.md`.

## nodus-a2a companion library

⚠️ **LOCAL REPO REPLACED.** Local `C:\dev\nodus-a2a` is the Tier 2 AgentCoordinator (23 tests, no nodus-lang dep). Original A2A wire protocol adapter (180 tests, nodus-lang dep) is preserved at `github.com/Masterplanner25/nodus-a2a`.

**Current local `C:\dev\nodus-a2a` (AgentCoordinator layer, 23 tests):**
- `AgentRegistry`, `AgentCoordinator` (local/delegate mode), `DelegationRequest`
- `DeadLetterService`, `StuckRunWatchdog`
- No nodus-lang dependency; standalone coordination primitives

## Nodus language quirks (relevant when writing test .nd code)

These burn time when forgotten:

- **No `await` keyword.** `test.flush_async()` is synchronous — no `await`.
- **`+=`, `-=`, `*=`, `/=` work** (added in 4.0.1 pre-release, PR #183). In closures, you
  still can't assign outer `let` variables at all — use a **map** with quoted keys and mutate
  via bracket notation: `state["count"] = state["count"] + 1i`.
  (The pattern uses `{"count": 0i}` — quoted-key map — NOT `{count: 0i}` record.)
- **Maps vs Records — dot vs bracket notation:**
  - `{"key": val}` (quoted keys) → **map** → access with `state["key"]`
  - `{key: val}` (unquoted keys) → **record** → access with `state.key`
  - Mixing them causes "Field access is only supported on records" or
    "Indexing is only supported on lists and maps". Never use dot on a map.
- **`run_workflow()` and `run_goal()` return maps** — use bracket notation:
  `result["steps"]`, `result["failed"]`, `result["goal"]`. NOT `result.steps`.
- **Channels are built-in functions, NOT a stdlib module.** `import "std:channel"`
  fails with "Import not found". Use built-ins directly: `channel()`, `send(ch, val)`,
  `recv(ch)`, `close(ch)`. No import needed.
- **Workflow step dependencies use `after` keyword:**
  `step b after a { ... }` — not `depends_on`, not any other syntax.
- **`checkpoint` is valid INSIDE step bodies only**, not at workflow-body level.
  `step a { checkpoint "mid"; return "done" }` — correct.
  `workflow w { checkpoint "mid"; step a { ... } }` — syntax error.
- **Async test two-flush pattern:** `spawn → flush (task sleeps) → advance_clock(N) → flush (task wakes)`.
  Skipping either flush or the advance causes the test to pass vacuously.
- **`spawn()` takes a coroutine value**, not a function literal. Use
  `let c = coroutine(fn() {...})` then `spawn(c)`.
- **`fn` is a reserved keyword** — can't use as a parameter name in `.nd` files.
- **`if` conditions with function calls require parentheses.** `if (module.fn(a, b))` works;
  `if module.fn(a, b)` gives "Expected '(', got identifier". Simple field access works without
  parens (`if record.field`), but call expressions need `if (expr)`.
- **Multiline list literals and function calls cannot span newlines.** Both
  `[1,\n2]` and `len(\n"hi"\n)` give "Unexpected end of statement". Keep on one line.
- **`print()` is single-argument.** `print("label:", value)` → syntax error.
  Use string interpolation: `print("\(label): \(value)")`.
- **`std:hash` returns a hash record, not a string.** `hash.sha256(data)` returns
  a record with methods; call `.to_hex()` to get hex: `hash.sha256(data).to_hex()`.
- **`std:tool` names must be dotted.** `tool.register({name:"greet",...})` silently
  returns an error. Use `"myapp.greet"`. Error message says "must use dotted namespacing".
- **`http.get()` and `subprocess.run()` return records** — use dot notation:
  `result.status`, `result.body`, `result.ok` (http); `result.stdout`, `result.exit_code` (subprocess).
- **CLI sandbox flag is `--allow-paths`** (not `--allowed-paths`). Relative paths
  resolve against CWD. To block a specific subdir, pass an explicit absolute path.
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

## nodus-memory companion library

⚠️ **LOCAL REPO REPLACED.** Local `C:\dev\nodus-memory` is the Tier 2 full memory library (28 tests). Original nodus-lang adapter (192 tests, `attach_to_runtime`, `nm_*` host functions, `import "nodus-memory"`) is preserved at `github.com/Masterplanner25/nodus-memory`.

**Current local `C:\dev\nodus-memory` (Tier 2 full library, 28 tests):**
- `MemoryNode`, `InMemoryStore`, MAS `build_path()`/`glob_match()`
- `score_nodes()`, `update_feedback()`, `recall()`/`recall_async()`, `EmbeddingProvider` protocol
- Depends on `nodus-events>=0.1.0`; optional `pgvector` and `openai` extras
- Flat layout (`nodus_memory/`), setuptools build
- Run tests: `cd C:\dev\nodus-memory && python -m pytest -q`

## nodus-native-memory-engine companion library

- Repo: `C:\dev\nodus-native-memory-engine` / `github.com/Masterplanner25/nodus-native-memory-engine`
- **Status: v0.1.0 PUBLISHED on PyPI.** PyO3/Maturin Rust extension; pure-Python fallback for all operations. `is_native()` → True when Rust extension loaded.
- **Build requires Rust:** `VIRTUAL_ENV="C:/dev/Coding Language/.venv" maturin develop --release`
  Rust 1.93.1, PyO3 0.22.6, maturin 1.12.6 all installed.
- Run tests: `cd C:\dev\nodus-native-memory-engine && "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest -q`

## nodus-extension companion library

- Repo: `C:\dev\nodus-extension` / `github.com/Masterplanner25/nodus-extension`
- **Status: v0.1.0 PUBLISHED on PyPI.** BYTECODE_VERSION 4, no new opcodes.
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

## Standalone package ecosystem (at `C:\dev\`)

All packages have GitHub repos under Masterplanner25. No nodus-lang dependency unless noted.
Test command: `cd C:\dev\<pkg> && python -m pytest -q`.
Package tables (deps + key abstractions by tier): `docs/ecosystem/PACKAGE_QUICK_REF.md`.

### Dependency audit (critical pattern)

**Rule — before adding a dep:** Check that it has a module-level unconditional import with no fallback. `TYPE_CHECKING`, `try/except ImportError`, and constructor injection all mean optional.

### `.nodus/` cache in standalone packages

When nodus-lang tests run inside a standalone package directory, nodus may
write a `.nodus/` cache directory (bytecode cache, graph state). This has been
added to `.gitignore` in all repos but watch for it in new packages — it can
contain hundreds of files that should never be committed.

### Ecosystem dependency notes

- **nodus-extensions** test fix: use `asyncio.run()` not `asyncio.get_event_loop().run_until_complete()` (Python 3.11+)
- nodus-queue redis tests need a live Redis server — always run with `--ignore=tests/test_redis_backend.py` in dev
- **nodus-mcp** test_phase_m.py has 2 port-conflict-sensitive tests — they pass individually but fail in full suite runs (pre-existing race condition, not a code bug)

### In-tree framework modules (namespace-qualified to avoid collision)

The in-tree workflow and schema modules were renamed in 2026-05-31 (NAME-COL-001 Option A)
to avoid install-order collisions with the same-named standalone PyPI packages. The
install-order collision is now resolved.

| In-tree module | Python import | Standalone package | Python import |
|----------------|---------------|--------------------|---------------|
| `src/nodus_lang_schema/` | `nodus_lang_schema` | `C:\dev\nodus-schema` | `nodus_schema` |
| `src/nodus_lang_workflow/` | `nodus_lang_workflow` | `C:\dev\nodus-workflow` | `nodus_workflow` |

**In-tree vs standalone — different scope, different content:**
- `nodus_lang_schema` = runtime ABI contracts for syscalls and extension surfaces (used by nodus-lang internally)
- `nodus_schema` (standalone) = general schema validation library (SchemaRegistry, parse_versioned_name)
- `nodus_lang_workflow` = full orchestration framework wired into the nodus-lang server (7-state lifecycle, SQLite store, HTTP/CLI)
- `nodus_workflow` (standalone) = lightweight workflow primitives (FlowDefinition, SchedulerEngine, no server wiring)

**Option C consolidation** (post-publish): make standalone packages canonical, remove in-tree
modules, have nodus-lang depend on them. Tracked in GitHub #104 and skill `/nodus-name-col-consolidation`.

## Ecosystem incubators (`packages/` in this repo)

Eight Python-first scaffold packages live at `C:\dev\Coding Language\packages\`.
They are **design references / API contracts**, not production implementations.

- `nodus-a2a-spec`, `nodus-agent`, `nodus-event`, `nodus-events`, `nodus-http`,
  `nodus-memory-spec`, `nodus-retry`
- **`nodus-store-sql` has been promoted** — no longer an incubator scaffold;
  production package at `C:\dev\nodus-store-sql` (47 tests, sync+async)
- **Never pip-install the `-spec` packages alongside the production packages** —
  `nodus-memory-spec` and `nodus-a2a-spec` share Python module names with the
  production packages in `C:\dev\`. Installing both in the same venv causes import conflicts.
- Run incubator tests from within each package directory:
  ```powershell
  cd "C:\dev\Coding Language\packages\nodus-memory" && python -m pytest -q
  ```
  The `pythonpath = ["src"]` in each package's pytest config provides the import path.
- Spec docs live at `docs/ecosystem/` (NODUS_HTTP.md, NODUS_RETRY.md, etc.)

## nodus-workflow (in-tree framework)

- **Location:** `src/nodus_lang_workflow/` (in this repo, not a separate package yet)
- **Status:** Near-runtime-complete. Core semantics complete; production hardening
  and packaging documented in `plans/nodus-workflow-framework.md`.
- **Test file:** `tests/test_nodus_workflow_framework.py` (30 tests)
- **7 run states:** `pending → running → waiting → retry_scheduled → completed / failed / dead_lettered`
- **Backends:** `LocalWorkflowStore` (file-backed) and `SQLiteWorkflowStore` (cross-process)
- **VM builtins added:** `workflow_wait(event_type, ...)`, `resume_workflow(id, checkpoint, payload)`,
  `workflow_resume_payload()` — delegate to `get_default_workflow_runner()`
- **CLI:** `nodus workflow runs|inspect|dead-letters|replay|migrate-state`
- **HTTP:** `GET /workflow/runs`, `GET /workflow/runs/{id}`, `GET /workflow/dead-letters`, `POST /workflow/replay`
- **Server flags:** `--workflow-store-backend {local|sqlite}`, `--workflow-store-path PATH`

**Operational gotcha — local store scan performance:**
The `LocalWorkflowStore` scans all `.nodus/workflow_framework/runs/*.json` on every sweep.
670+ accumulated files cause >2s per sweep, breaking the `test_worker_death_detected_by_sweeper`
test (500ms deadline). Fix: use SQLite temp store in tests, OR clean `.nodus/workflow_framework/runs/`
(safe — test artifacts only).

**Circular import:** `nodus.vm.vm` imports `get_default_workflow_runner` from `nodus_lang_workflow.runner`
at top level. Works at runtime (nodus initializes first) but fails if `nodus_lang_workflow` is imported
before `nodus` in a fresh process. Fix tracked as CIRC-001 (#103), skill `/nodus-scheduler-freeze` Phase A.

## nodus_lang_schema (in-tree ABI contracts package)

- **Location:** `src/nodus_lang_schema/` — renamed from `nodus_schema` (NAME-COL-001, 2026-05-31)
- **Python import:** `from nodus_lang_schema.syscalls import SyscallSpec`
- **Exports:** `SyscallSpec`, `parse_syscall_name()`, `resolve_version()`,
  `validate_input()`, `validate_output()`, `validate_payload()`, extension ABI models.
- **Note:** Not the same as the standalone `nodus-schema` package (`C:\dev\nodus-schema`).
  Option C post-launch will consolidate these. Skill: `/nodus-name-col-consolidation`.

## nodus-vscode VS Code extension

- Repo: `C:\dev\nodus-vscode` / `github.com/Masterplanner25/nodus-vscode`
- **Status: v0.1.0 PUBLISHED — live on VS Code Marketplace 2026-06-15 under publisher `MasterplanInfiniteWeave`.**
- **Phase 1:** TextMate grammar, 23 snippets, bracket/fold config
- **Phase 2:** Diagnostics via `nodus check` (fallback; skipped once LSP starts)
- **Phase 3:** Run File (`Ctrl+Alt+N`), Format File, DAP debugger (`Ctrl+Alt+D`, `nodus dap`)
- **Phase 4:** LSP via `nodus lsp` — hover docs, go-to-definition, completions
- **Build:** `cd C:\dev\nodus-vscode && npm run package` (requires `@vscode/vsce`)
- **Publish:** upload VSIX at marketplace.visualstudio.com → Manage Publishers & Extensions → `+ New extension` → `Visual Studio Code`. Publisher ID must be `MasterplanInfiniteWeave` in package.json.
- **Key settings:** `nodus.executablePath` (default: `nodus`), `nodus.lspCommand` (array, overrides LSP command — useful for dev source: `["C:/dev/Coding Language/.venv/Scripts/python.exe", "C:/dev/Coding Language/nodus.py", "lsp"]`)
- **LSP note:** VS Code spawns the INSTALLED `nodus.exe`, not dev source. LSP server changes require a new nodus-lang release to take effect in the extension.

## nodus-mcp-server

- Repo: `C:\dev\nodus-mcp-server` / `github.com/Masterplanner25/nodus-mcp-server`
- **Status: v0.1.11 PUBLISHED on PyPI.** Install via `pipx install nodus-mcp-server`.
- **Supports two transports:**
  - **Claude Desktop (stdio):** Add to `claude_desktop_config.json` under `mcpServers`
  - **ChatGPT Desktop (HTTP/SSE):** Run `nodus-mcp-server --http --port 8765`, tunnel via ngrok
- **HTTP transport uses `StreamableHTTPSessionManager`** (MCP SDK 1.28.0), single endpoint `POST /mcp`.
  The old `SseServerTransport` (two-endpoint SSE) is broken — do not use it.
- **ngrok static domain:** `nodusmcpserver.ngrok.io` (paid plan). ChatGPT Desktop requires public HTTPS;
  server runs plain HTTP, ngrok terminates SSL. Point ChatGPT at `https://nodusmcpserver.ngrok.io/mcp`.
- **Windows auto-startup:** Registry `HKCU:\Software\Microsoft\Windows\CurrentVersion\Run` runs
  `C:\Users\shawn\.nodus-mcp-server\startup.ps1` at login (no admin needed). Starts server + ngrok.
- **Shared memory:** Both Claude Desktop and ChatGPT Desktop read/write the same SQLite DB at
  `~/.nodus-mcp-server/data/memory.db` — memory written in one AI is readable by the other.
- **6 MCP tools:** `nodus_run_goal`, `nodus_run_workflow`, `nodus_resume_workflow`,
  `nodus_store_memory`, `nodus_recall`, `nodus_list_graphs`
- **goal vs workflow naming convention:** `goal` = outcome-oriented, single-shot (steps are impl details);
  `workflow` = process-oriented, resumable (pipeline itself is the point, returns `graph_id`).
  Runtime treats them identically; convention is semantic.
- Run tests: `cd C:\dev\nodus-mcp-server && python -m pytest -q`

## nodus-jupyter

- Repo: `C:\dev\nodus-jupyter` / `github.com/Masterplanner25/nodus-jupyter`
- **Status: v0.1.0 PUBLISHED on PyPI 2026-06-15.**
- **Install:** `pip install nodus-jupyter && python -m nodus_jupyter install`
- **32 unit tests** — require `ipykernel` installed (`pip install ipykernel`).
- Provides a Jupyter kernel for `.nd` files; works in JupyterLab, Jupyter Notebook, VS Code notebooks.

## nodus-run-action

- Repo: `C:\dev\nodus-run-action` / `github.com/Masterplanner25/nodus-run-action`
- **Status: v1.0.0 — GitHub Action (not a PyPI package).**
- **Usage:** `uses: Masterplanner25/nodus-run-action@v1`
- **Three modes:** `file` (run a .nd script), `test-path` (run test suite), `fmt-check` (format gate)
- Pin the nodus-lang version with `version: '4.0.5'` for reproducible CI.
- No local test suite — tests run in CI via the action itself.

## nodus-sdk companion package

- Repo: `C:\dev\nodus-sdk` / `github.com/Masterplanner25/nodus-sdk`
- **Status: v0.1.0 PUBLISHED on PyPI.**
  99 tests. Unified platform SDK auto-wiring the 27-package ecosystem.
- **Install:** `pip install nodus-sdk[agent,sql,fastapi]` (extras-based)
- **Key exports:** `NodusSDKRuntime`, `create_runtime(**kwargs)`, `detect_available()`
- **9 bridges:** redis, http, llm, observability (wrappers), sql, vector, scheduler, webhook, api (new)
- **Bridge return type:** host functions return maps not Records — `.nd` must use `r["key"]` not `r.key`
- **FastAPI bridge:** `create_nodus_router(rt)` → POST /run, GET /health, GET /syscalls, memory CRUD
- **NodusTraceMiddleware:** reads X-Trace-ID header → `runtime.set_trace_id()`
- Run tests: `cd C:\dev\nodus-sdk && PYTHONPATH="C:/dev/Coding Language/src" python -m pytest -q`

## nodus-store-sql companion package

- Repo: `C:\dev\nodus-store-sql` / `github.com/Masterplanner25/nodus-store-sql`
- **Status: v0.1.0 PUBLISHED on PyPI.**
  47 tests (31 sync + 16 async). Promoted from `packages/nodus-store-sql` incubator scaffold.
- **Async tests require `aiosqlite`** — not installed by default. Run `pip install aiosqlite` if async tests fail with `ModuleNotFoundError`.
- **Three stores:** `RunStore` (optimistic locking), `EventStore` (append-only), `JobStore` (atomic claiming)
- **Async:** `AsyncSqlStore` via `sqlalchemy.ext.asyncio`; test with `sqlite+aiosqlite:///:memory:`
- **Tables:** `nodus_runs`, `nodus_events`, `nodus_jobs`
- **No Alembic:** `create_all()` is the dev schema bootstrap; production manages migrations independently
- Run tests: `cd C:\dev\nodus-store-sql && python -m pytest -q`

## SemVer policy

The current published version is **v4.0.5** (live on PyPI). Both files must stay in sync:
- `src/nodus/support/version.py` — `__version__ = "4.0.5"`
- `pyproject.toml` — `version = "4.0.5"`

Patch releases (4.0.x) for bug fixes and stability graduations. Next minor bump (4.1.0) requires a substantive feature addition. Never bump without a corresponding PyPI publish. If you see these files at different values, fix the mismatch before doing anything else.

## Embedding API — known blockers and operational traps

These were identified by a raw-path readiness probe and are filed as GitHub issues.
Full analysis: `C:\dev\nodus-mcp\docs\design\06-embedding-runtime-blockers.md`.
All entries are also in `docs/governance/TECH_DEBT.md`.

**EMBED-001 (#97) — The 200ms default trap (hits every first-time embedder):**
`NodusRuntime()` with NO arguments applies a **200ms wall-clock deadline** — the same
as `nodus run`. Any coroutine sleeping cumulatively more than 200ms (workflows, async
loops, MCP/A2A request handlers) will be killed silently.

```python
# WRONG for any long-lived use:
rt = NodusRuntime()

# CORRECT for servers, MCP hosts, workflow engines, anything with sleep:
rt = NodusRuntime(timeout_ms=None, max_steps=None)
```

**SPAWN-001 (#117, open):** `spawn().wait_async()` is sync — blocks scheduler thread. Low severity; does not affect `subprocess_run_async`.

**CHAN-001 (open):** `recv()` on empty channel strands the coroutine silently — pre-populate the channel or use the subprocess-pipe pattern. See `docs/governance/TECH_DEBT.md`.

## Published ecosystem — current state (as of 2026-06-20)

All packages are live. PyPI rate limit is 2-3 new uploads per session; wait ~1 hour between sessions.

**nodus-lang:** v4.0.5 on PyPI. nodus-retry is an optional dep (`nodus-lang[retry]`); runtime falls back to built-in `InMemoryEffectStore` when absent.

**Standalone packages (all v0.1.0, PyPI):**
```
nodus-schema, nodus-protocol, nodus-state, nodus-session, nodus-events
nodus-channels, nodus-context, nodus-approvals, nodus-retry, nodus-circuit-breaker
nodus-agent, nodus-auth, nodus-observability, nodus-queue, nodus-router
nodus-delivery, nodus-http, nodus-llm, nodus-adapter-base, nodus-gateway
nodus-observability-framework, nodus-workflow, nodus-store-sql, nodus-sdk
nodus-mcp, nodus-extension, nodus-native-memory-engine, nodus-jupyter
nodus-mcp-server (v0.1.11)
```

**Other published artifacts:**
- nodus-vscode v0.1.0 — VS Code Marketplace (MasterplanInfiniteWeave)
- nodus-run-action v1.0.0 — GitHub Action (Masterplanner25/nodus-run-action@v1)

**PyPI token note:** Each package in a separate repo (nodus-mcp, nodus-extension,
nodus-memory, nodus-native-memory-engine, nodus-mcp-server) needs its own project-specific PyPI token.
nodus-lang packages use the main nodus-lang token. Retrieve from user at upload time —
never store tokens in any file.

**Future publish sequence:** For any new package, the pattern is:
1. `python -m build` (in the package dir)
2. `twine upload --username __token__ --password <token> dist/*`
3. Add status badge to README, commit, push
