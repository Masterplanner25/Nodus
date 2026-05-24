# Nodus Versioning Policy

The full semantic versioning policy — including what counts as a breaking
change, the v2.x exception, the strict-semver commitment from v3.0, pre-release
identifiers, and the Development Status classifier rule — is maintained in:

**[docs/release.md — Semantic Versioning](../release.md#semantic-versioning)**

## Quick reference

- **Patch** (x.y.Z): backward-compatible bug fixes and security patches
- **Minor** (x.Y.z): backward-compatible new functionality
- **Major** (X.y.z): incompatible API or language changes

## Version source of truth

- Runtime version is defined in `src/nodus/support/version.py`
- CLI output (`nodus --version`) is derived from it
- `pyproject.toml` must be kept in sync

## Release flow

1. Update `src/nodus/support/version.py`
2. Update `pyproject.toml`
3. Move items from `[Unreleased]` in `CHANGELOG.md` to the new version section
4. Tag the commit (`git tag vX.Y.Z`) and push the tag
