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

The `gh` CLI is not installed. File issues, create releases, and make other
GitHub API calls using `urllib.request` directly with a token retrieved from:

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

## Test suite

```powershell
# Full suite
PYTHONPATH="C:/dev/Coding Language/src" "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/ -q

# Coverage (excludes 3 timing-sensitive tests)
PYTHONPATH="C:/dev/Coding Language/src" "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/ --cov=src/nodus --cov-fail-under=60 --ignore=tests/test_scheduler_fairness.py -q
```

Coverage baseline: 77% overall. Gate: 60%. See `docs/governance/TECH_DEBT.md`
for the per-module breakdown and the three deselected flaky tests.

## Security boundary test rule

Any fix for a security boundary (path traversal, sandbox escape, allowed_paths
enforcement, resource limits) must have tests covering BOTH CLI mode and
`NodusRuntime` embedded mode. The enforcement code path can differ between
contexts. See `docs/governance/TECH_DEBT.md § Testing Methodology`.
