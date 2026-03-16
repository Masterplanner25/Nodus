# Nodus Release Checklist

Use this checklist to cut a clean, repeatable release.

## Pre-release checks
- [ ] Verify no unformatted .nd files exist:
  ```bash
  find . -name "*.nd" \
    -not -path "./.git/*" \
    -not -path "./.venv/*" \
    -not -path "./tmp_demo/*" \
    -not -path "./tests/fixtures/fmt/*" \
    | xargs -I {} python nodus.py fmt --check {}
  ```
  (CI auto-formats all `.nd` files in the repo (excluding `.git`, `.venv`, `tmp_demo`, and
  `tests/fixtures/fmt`) before the check runs and commits any changes back with `[skip ci]`,
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

## Adding a new opcode (post-v1.0 freeze)

The opcode set is frozen at v1.0. To add a new opcode in a future release:

1. Open `docs/governance/FREEZE_PROPOSAL.md` and add a new "Extension Proposal" entry
   documenting the opcode name, motivation, and provisional/stable classification.
2. Add `_op_<name>` to `src/nodus/vm/vm.py` and register it in `_build_dispatch_table()`.
3. Emit it from `src/nodus/compiler/compiler.py`.
4. Bump `BYTECODE_VERSION` in `compiler.py` and `NODUS_BYTECODE_VERSION` in `module.py`.
5. Document the opcode in `docs/runtime/BYTECODE_REFERENCE.md`, `BYTECODE.md`, and
   `INSTRUCTION_SEMANTICS.md`. Add a version history entry to `BYTECODE.md`.
6. Update `CHANGELOG.md` to record the version bump reason.
