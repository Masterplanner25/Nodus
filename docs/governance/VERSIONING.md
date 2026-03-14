# Nodus Versioning Policy

Nodus uses simple semantic versioning.

- Patch (x.y.Z): bug fixes, docs, tooling polish, no behavior changes.
- Minor (x.Y.z): new language/runtime capabilities, stdlib additions, CLI improvements.
- Major (X.y.z): breaking syntax/runtime/module changes or removals.

Single source of truth:
- Version is defined in `version.py`.
- CLI output (`nodus --version`) is derived from it.

Release flow:
- Update `version.py`.
- Move items from Unreleased in `CHANGELOG.md` to the new version section.
