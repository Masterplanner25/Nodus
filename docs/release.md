# Release Preparation

This document covers Nodus's semantic versioning policy and the procedure
for building and validating a release.

---

## Semantic Versioning

Nodus follows semantic versioning ([semver.org](https://semver.org)). Version
numbers are `MAJOR.MINOR.PATCH` where:

- **MAJOR** is incremented for incompatible API or language changes
- **MINOR** is incremented for backward-compatible new functionality
- **PATCH** is incremented for backward-compatible bug fixes and security patches

### What counts as a breaking change

A change is breaking if Nodus code that ran correctly under version X.Y.Z
would fail or produce different results under the new version. Breaking changes
require a MAJOR version bump. Examples:

- Removing or renaming a stdlib function
- Changing the return type or behavior of a stdlib function
- Changing the syntax of a language construct
- Removing or renaming a CLI command or flag
- Changing the meaning of an existing operator

Examples of **non-breaking** changes that do not require a MAJOR bump:

- Adding new stdlib functions or modules
- Adding new operators or syntax that doesn't conflict with existing code
- Adding new optional CLI flags or subcommands
- Adding new fields to the embedded API result dict (additive)
- Fixing bugs where the previous behavior was incorrect with no reasonable
  expectation of correctness (judgment call — document in CHANGELOG)
- Security patches that restrict previously-permitted behavior (e.g. sandbox
  fixes that block paths a script could previously access — these are fixes,
  not breaks)

### The v2.x exception

Nodus v2.0.0 was the first release on PyPI (May 2026). During the v2.x cycle,
the project shipped two changes that, under strict semver, would warrant a
MAJOR bump:

- **v2.1.0 — `json.parse` now returns maps, not records.** Code using
  dot-access on parsed JSON (e.g. `result.key`) stopped working; bracket
  access (`result["key"]`) is the correct form. The previous behavior
  blocked standard map operations (`has_key`, `keys`, `values`) and was
  arguably incorrect. The change was documented in the CHANGELOG and the
  working-with-json guide with a migration note.
- **v2.1.1 — `allowed_paths` now enforces sandbox for `std:fs` calls.** The
  fix correctly blocked filesystem access that the previous version
  incorrectly permitted. This is treated as a security patch (PATCH bump),
  not a break — scripts relying on the bypass were relying on a bug.

These were deliberate choices made early in adoption when:
- Deployed usage of the affected versions was minimal
- The previous behaviors were demonstrably incorrect or unsafe
- The CHANGELOG and user guides provided clear upgrade paths

The v2.x cycle is the last time Nodus will ship breaking changes in MINOR or
PATCH versions. The commitment below applies from v3.0 forward.

### Strict semver from v3.0

Beginning with v3.0.0, Nodus commits to strict semantic versioning:

- Any change that breaks existing Nodus scripts or embedding API consumers
  requires a MAJOR version bump
- If a v3.x.y release is found after publication to contain an unintentional
  breaking change, the project will either issue a corrective patch that
  restores prior behavior, or yank the release and republish as the next
  appropriate version

### Pre-release identifiers

Non-stable builds use standard semver pre-release identifiers:

- `X.Y.Z-alpha.N` — early development; APIs unstable
- `X.Y.Z-beta.N` — feature-complete but not fully validated
- `X.Y.Z-rc.N` — release candidate; no planned changes

Pre-release versions are not subject to the strict-semver guarantee. Breaking
changes may occur between pre-releases in the same X.Y.Z series.

### How breaking changes are announced

When a MAJOR version bump introduces breaking changes, the release must include:

- A **Breaking Changes** section in the CHANGELOG with before/after code
  examples for each break
- A migration guide in `docs/guide/` or extended migration notes in the
  most relevant existing guide
- Verbatim error messages users will encounter running old code on the new
  version, so they are searchable

### Development Status classifier

The PyPI Development Status classifier reflects deployed maturity:

- **Beta** (`Development Status :: 4 - Beta`) — default until stability
  criteria are met
- **Production/Stable** (`Development Status :: 5 - Production/Stable`) —
  requires two consecutive minor releases with no CRITICAL findings from
  independent evaluation

Nodus is currently classified as **Beta** (v4.0.3). The classifier was downgraded from
Production/Stable to Beta in v2.0.1 after the v2.0.0 evaluation found three
CRITICAL issues. Reassessment to Production/Stable requires two consecutive minor
releases with no CRITICAL findings from independent evaluation.

---

## Version

Release target: `4.0.3`

## Clean Build Preparation

Review and remove stale local build artifacts before building if they exist:

```bash
rm -rf dist build *.egg-info
```

On Windows PowerShell:

```powershell
Remove-Item -Recurse -Force dist, build, *.egg-info
```

Only remove artifacts that are generated build output. Do not delete source directories.

## Build Validation

Build and reinstall locally:

```bash
python -m build
pip install dist/*.whl --force-reinstall
```

Packaging expectations:

- the `nodus` CLI is exposed through the wheel entry point
- stdlib files are included from `src/nodus/stdlib/`
- the REPL module is included with the package

## Runtime Validation Checklist

Run these checks against the built wheel:

```bash
nodus --version
nodus repl
nodus run main.nd
nodus run
```

Additional validation:

```bash
# stdlib import
nodus run stdlib_check.nd

# REPL import
nodus repl

# circular import failure
nodus run circular_runner.nd

# invalid import failure
nodus run invalid_import.nd
```

Expected outcomes:

- `nodus --version` reports `4.0.3`
- `nodus repl` starts successfully from the installed package
- `nodus run main.nd` runs only the explicit file
- `nodus run` runs only `src/main.nd` inside a project root
- stdlib imports resolve from the installed wheel
- circular imports fail with a clear chain message instead of a recursion error
- invalid imports fail with a structured import error
- `fs.read` on a missing file returns an err record (kind `"io_error"`), does not throw
- integer literals (`42i`) parse and `type(42i)` returns `"int"`
