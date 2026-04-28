# Release Preparation

This document prepares a local release build for `nodus-lang` without uploading anything externally.

## Version

Release target: `1.1.2`

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

- `nodus --version` reports `1.1.2`
- `nodus repl` starts successfully from the installed package
- `nodus run main.nd` runs only the explicit file
- `nodus run` runs only `src/main.nd` inside a project root
- stdlib imports resolve from the installed wheel
- circular imports fail with a clear chain message instead of a recursion error
- invalid imports fail with a structured import error
