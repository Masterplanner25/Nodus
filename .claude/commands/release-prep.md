Prepare and execute a Nodus release. Walks through every step in order,
verifying state before proceeding.

Arguments: $ARGUMENTS
(Pass the target version, e.g. `4.0.0`. If omitted, determine
from context or ask.)

## Pre-flight checks

Before touching any files:

1. Confirm working tree is clean: `git status`
2. Confirm current branch is `main`: `git branch --show-current`
3. Confirm all tests pass:
   ```
   PYTHONPATH="C:/dev/Coding Language/src" "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/ -q
   ```
4. Read `src/nodus/support/version.py` — note current version
5. Read `[Unreleased]` section of `CHANGELOG.md` — confirm there is
   content to release
6. Check `docs/evals/vX.Y.Z/CREATOR_VALIDATION.md` exists — Gate 10 must
   be complete before publishing. If it doesn't exist, run the Gate 10
   protocol from `docs/governance/EVAL_PREPUBLISH.md` first.

## Step 1 — Determine version bump type

Based on `[Unreleased]` content and semver policy in `docs/release.md`:

- **PATCH** (x.y.Z): bug fixes and security patches only
- **MINOR** (x.Y.z): new backward-compatible functionality
- **MAJOR** (X.y.z): breaking changes (requires explicit user confirmation)

Confirm the target version with the user before proceeding.

## Step 2 — Bump version files

Edit both files atomically — they must always match:

- `src/nodus/support/version.py`: `__version__ = "X.Y.Z"`
- `pyproject.toml`: `version = "X.Y.Z"`

Verify with:
```
PYTHONPATH="C:/dev/Coding Language/src" "C:/dev/Coding Language/.venv/Scripts/nodus.exe" --version
```
Expected: `nodus X.Y.Z`

## Step 3 — Update CHANGELOG.md

Move all items from `## [Unreleased]` to a new `## [X.Y.Z] - YYYY-MM-DD`
section above `[Unreleased]`. Use today's date.

If this is a security release, the new section's first subsection must be
`### Security` — not `### Fixed`.

Update `docs/release.md` if the "Release target" version or expected
`nodus --version` output is stale.

Update `docs/governance/COMPATIBILITY.md`:
- Remove `(current)` from the previous version entry
- Add a new entry for X.Y.Z with `(current)` and a one-line summary

## Step 4 — Commit

```
git add src/nodus/support/version.py pyproject.toml CHANGELOG.md docs/release.md docs/governance/COMPATIBILITY.md
git commit -m "release: bump to X.Y.Z, update changelog"
```

## Step 5 — Tag and push

```
git tag vX.Y.Z
git push origin main
git push origin vX.Y.Z
```

Confirm both pushes succeed before building.

## Step 6 — Build

```powershell
Remove-Item -Recurse -Force dist, build -ErrorAction SilentlyContinue
"C:/dev/Coding Language/.venv/Scripts/python.exe" -m build
"C:/dev/Coding Language/.venv/Scripts/python.exe" -m twine check dist/*
```

Expected: `PASSED` for both the `.tar.gz` and `.whl`.

## Step 7 — Gate 10 creator validation (against the built wheel)

Build a fresh validation venv and run all 3 standard eval scripts:

```powershell
python -m venv .venv-validation
.venv-validation/Scripts/pip install dist/nodus_lang-X.Y.Z-py3-none-any.whl
.venv-validation/Scripts/nodus --version   # must match X.Y.Z
.venv-validation/Scripts/nodus run tests/eval/quirk_probe.nd
.venv-validation/Scripts/nodus run tests/eval/language_exerciser.nd
.venv-validation/Scripts/nodus run tests/eval/framework_capabilities.nd
```

All three must print their success message (`ALL QUIRKS CONFIRMED` etc.).
Any failure is a regression — stop and investigate before uploading.

See `docs/governance/EVAL_PREPUBLISH.md` for the full 8-category adversarial
protocol. Results go in `docs/evals/vX.Y.Z/CREATOR_VALIDATION.md`.

## Step 8 — Upload to PyPI

Retrieve the token from the user (do NOT store in any file). Use explicit
flags — `~/.pypirc` may have an empty password field that causes a 403:

```powershell
"C:/dev/Coding Language/.venv/Scripts/python.exe" -m twine upload --username __token__ --password <token> dist/*
```

After upload, confirm the new version appears on PyPI.

## Step 9 — GitHub release

`gh` CLI is installed and authenticated as Masterplanner25. Use it directly:

```powershell
gh release create vX.Y.Z --title "Nodus vX.Y.Z" --notes "<release notes from CHANGELOG>"
```

Or to use a notes file:
```powershell
gh release create vX.Y.Z --title "Nodus vX.Y.Z" --notes-file /tmp/release_notes.md
```

## Post-release checklist

- [ ] `nodus --version` reports `X.Y.Z` from installed wheel
- [ ] PyPI page shows new version
- [ ] GitHub release is published with correct tag
- [ ] `COMPATIBILITY.md` updated
- [ ] `CHANGELOG.md` has `[Unreleased]` section ready for next cycle
- [ ] `docs/evals/vX.Y.Z/CREATOR_VALIDATION.md` committed and pushed
