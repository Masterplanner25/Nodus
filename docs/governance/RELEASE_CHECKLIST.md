# Nodus Release Checklist

Use this checklist to cut a clean, repeatable release.

## Pre-release checks
- Run formatter check: `nodus fmt <targets> --check`
- Run validation on key examples: `nodus check examples/import_demo.nd` (and other representative examples)
- Run unit tests: `python -m unittest discover -s tests -v`
- Run example suite (non-interactive): `nodus test-examples`

## Release prep
- Update `CHANGELOG.md` (move items from Unreleased into a new version section)
- Update `ROADMAP.md` milestone status if needed
- Review deprecation timeline in `COMPATIBILITY.md`
- Bump version in `version.py`
- Verify CLI output: `nodus --version`
- Spot-check a few examples manually

## Release
- Tag the release (e.g. `v0.1.1`)
- Publish release notes from the changelog

## Post-release
- Create a fresh Unreleased section in `CHANGELOG.md`
- Note any follow-up issues
