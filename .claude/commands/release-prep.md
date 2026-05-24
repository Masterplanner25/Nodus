Prepare and execute a Nodus release. Walks through every step in order,
verifying state before proceeding.

Arguments: $ARGUMENTS
(Pass the target version, e.g. `2.2.0` or `2.1.2`. If omitted, determine
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

## Step 7 — Runtime validation

```
PYTHONPATH="C:/dev/Coding Language/src" "C:/dev/Coding Language/.venv/Scripts/nodus.exe" --version
```

Then reinstall from the built wheel and verify again:

```
"C:/dev/Coding Language/.venv/Scripts/pip.exe" install dist/*.whl --force-reinstall
nodus --version
```

Both should report `nodus X.Y.Z`.

## Step 8 — Upload to PyPI

```
"C:/dev/Coding Language/.venv/Scripts/python.exe" -m twine upload dist/*
```

Token: retrieve from user or environment. Do NOT store the token in any file.
After upload, confirm the new version appears on PyPI.

## Step 9 — GitHub release

Create a release via the GitHub API (gh CLI not installed):

```python
import urllib.request, json

token = '<token from git credential fill>'
headers = {
    'Accept': 'application/vnd.github+json',
    'Authorization': f'Bearer {token}',
    'X-GitHub-Api-Version': '2022-11-28',
    'User-Agent': 'nodus-dev',
    'Content-Type': 'application/json'
}

payload = {
    'tag_name': 'vX.Y.Z',
    'name': 'Nodus vX.Y.Z',
    'body': '<release notes from CHANGELOG>',
    'draft': False,
    'prerelease': False
}

body = json.dumps(payload).encode()
req = urllib.request.Request(
    'https://api.github.com/repos/Masterplanner25/Nodus/releases',
    data=body, headers=headers, method='POST'
)
with urllib.request.urlopen(req) as r:
    result = json.loads(r.read())
    print(result['html_url'])
```

## Post-release checklist

- [ ] `nodus --version` reports `X.Y.Z` from installed wheel
- [ ] PyPI page shows new version
- [ ] GitHub release is published with correct tag
- [ ] `COMPATIBILITY.md` updated
- [ ] `CHANGELOG.md` has `[Unreleased]` section ready for next cycle
