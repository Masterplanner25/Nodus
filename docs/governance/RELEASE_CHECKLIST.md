<!-- Reconciled 2026-05-29: updated to current CLI commands and added doc-vs-code gate. Needs review before repo commit and push. -->

# Nodus Release Checklist

Use this checklist to cut a clean, repeatable release. For the authoritative gate
definitions and passing criteria, see `docs/governance/RELEASE_GATES.md`.
For the full release playbook, see `docs/governance/RELEASE_PLAYBOOK.md`.

## Pre-release checks
- [ ] Verify no lint violations in changed files:
  ```powershell
  & "C:/dev/Coding Language/.venv/Scripts/python.exe" -m ruff check src/ tests/
  ```
- [ ] Run full test suite:
  ```powershell
  PYTHONPATH="C:/dev/Coding Language/src" "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/ -q
  ```
- [ ] Run doc-vs-code gate (mandatory before release):
  ```powershell
  PYTHONPATH="C:/dev/Coding Language/src;C:/dev/Coding Language" `
    "C:/dev/Coding Language/.venv/Scripts/python.exe" `
    -m tools.nodus_gate.cli --all
  ```
- [ ] Validate representative examples: `nodus check examples/import_demo.nd`
- [ ] Confirm CI passes on the release branch before tagging

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
