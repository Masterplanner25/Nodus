# Nodus Release Checklist

Use this checklist to cut a clean, repeatable release.

## Pre-release checks
- Run formatter check on examples:
  ```bash
  find examples/ -name "*.nd" | xargs -I {} python nodus.py fmt --check {}
  ```
  (CI auto-formats `examples/` before the check runs and commits any changes back with `[skip ci]`,
  so manual pre-formatting is not required — but running it locally catches issues before push.)
- Run validation on key examples: `nodus check examples/import_demo.nd` (and other representative examples)
- Run unit tests: `python -m unittest discover -s tests -v`
- Run example suite (non-interactive): `nodus test-examples`
- Confirm CI passes on the release branch before tagging

## Release prep
- Update `CHANGELOG.md` (move items from Unreleased into a new version section)
- Update `ROADMAP.md` milestone status if needed
- Review deprecation timeline in `COMPATIBILITY.md`
- Bump version in `version.py`
- Bump package metadata version in `pyproject.toml`
- Verify CLI output: `nodus --version`
- Spot-check a few examples manually
- Verify `examples/` contains only `.nd` files: `find examples/ -name "*.tl"` should return empty

## Release
- Tag the release (e.g. `v0.1.1`)
- Publish release notes from the changelog

## Post-release
- Create a fresh Unreleased section in `CHANGELOG.md`
- Note any follow-up issues
