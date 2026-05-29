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
| Deprecation timeline | `docs/governance/COMPATIBILITY.md` |
| Tech debt | `docs/governance/TECH_DEBT.md` |
| Guide files | `docs/guide/` |
| Runtime reference docs | `docs/runtime/` |
| Governance docs | `docs/governance/` |
| Release playbook | `docs/governance/RELEASE_PLAYBOOK.md` |
| Skills | `.claude/commands/` |
| Doc-vs-code gate | `tools/nodus_gate/` — run `python -m tools.nodus_gate.cli --all` |
| Library entry-point contract | `docs/guide/library-entry-points.md` |
| nodus-mcp companion repo | `C:\dev\nodus-mcp` / github.com/Masterplanner25/nodus-mcp |

## Test suite

```powershell
# Full suite
PYTHONPATH="C:/dev/Coding Language/src" "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/ -q

# Coverage (excludes 3 timing-sensitive tests)
PYTHONPATH="C:/dev/Coding Language/src" "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/ --cov=src/nodus --cov-fail-under=60 --ignore=tests/test_scheduler_fairness.py -q
```

Coverage baseline: 77% overall. Gate: 60%. See `docs/governance/TECH_DEBT.md`
for the per-module breakdown and the three deselected flaky tests.

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

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
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
  280 tests pass. BYTECODE_VERSION 4, no new opcodes.
  Publication waits for nodus-a2a v0.1.0 (coordinated three-artifact launch).
- Dev install: `pip install -e . --no-deps`
- Run tests: `cd C:\dev\nodus-mcp && PYTHONPATH="C:/dev/Coding Language/src" "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/ -q`
- Entry-point contract: `[project.entry-points."nodus.nd"]` → callable returns
  absolute path to `.nd` root dir — see `docs/guide/library-entry-points.md`
- Key documented contracts (see `docs/governance/TECH_DEBT.md`):
  - TD-007: server-initiated requests over HTTP are stdio-only (no SSE/push)
  - TD-008: `_validate_args` is top-level type checking only (not full JSON Schema)
  - TD-009: resource read handler must raise `KeyError` for unknown URI → -32601
  - TD-010: `requestState` is on the wire; never checkpoint secrets in sentinel state
- **Next: nodus-a2a v0.1.0** — will follow nodus-mcp's pattern (Phase 0 decisions
  → Phase 1 design docs → Phases A–N). The `/nodus-mcp-phase` skill can be adapted
  for a2a once a2a's repo scaffold exists.

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
- **Multiline function calls across newlines** may fail parsing — keep
  args on the same line as the opening paren where possible.

## Security boundary test rule

Any fix for a security boundary (path traversal, sandbox escape, allowed_paths
enforcement, resource limits) must have tests covering BOTH CLI mode and
`NodusRuntime` embedded mode. The enforcement code path can differ between
contexts. See `docs/governance/TECH_DEBT.md § Testing Methodology`.
