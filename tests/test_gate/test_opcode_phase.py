"""Tests for nodus_gate opcode phase.

The point of the phase is that the opcode freeze stops being enforced by prose
alone (#366), so these tests check both halves: that the real repo is clean, and
that each check actually fires when its record drifts. A gate that can only pass
is the failure mode the phase exists to end.
"""

import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))  # noqa: E402
sys.path.insert(0, str(_ROOT / "src"))  # noqa: E402

from tools.nodus_gate.opcode_phase import (  # noqa: E402
    CLAIM_ANCHORS,
    OpcodeResult,
    _check_claims,
    _check_semantic_specs,
    _compare,
    load_dispatch_opcodes,
    parse_freeze_stability_tables,
    parse_reference_appendix,
    parse_reference_inventory,
    parse_reference_categories,
    parse_reference_removed_section,
    parse_specified_opcodes,
    run_opcode_phase,
    scan_emitted_opcodes,
)

_REFERENCE = _ROOT / "docs" / "runtime" / "BYTECODE_REFERENCE.md"
_FREEZE = _ROOT / "docs" / "governance" / "FREEZE_PROPOSAL.md"


def _reference_text() -> str:
    return _REFERENCE.read_text(encoding="utf-8")


def _freeze_text() -> str:
    return _FREEZE.read_text(encoding="utf-8")


class DispatchTableTests(unittest.TestCase):
    def test_reads_a_populated_table_from_a_live_vm(self):
        dispatch, version = load_dispatch_opcodes(str(_ROOT))
        self.assertGreater(len(dispatch), 40)
        self.assertIn("HALT", dispatch)
        self.assertIsInstance(version, int)

    def test_removed_opcode_is_absent(self):
        dispatch, _ = load_dispatch_opcodes(str(_ROOT))
        self.assertNotIn("LOAD_LOCAL", dispatch)


class ParserTests(unittest.TestCase):
    def test_inventory_splits_active_from_removed(self):
        active, removed = parse_reference_inventory(_reference_text())
        self.assertIn("PUSH_CONST", active)
        self.assertEqual({"LOAD_LOCAL"}, removed)
        self.assertNotIn("LOAD_LOCAL", active)

    def test_removed_section_matches_inventory(self):
        _, removed = parse_reference_inventory(_reference_text())
        self.assertEqual(removed, parse_reference_removed_section(_reference_text()))

    def test_appendix_rows_are_parsed(self):
        active, removed = parse_reference_appendix(_reference_text())
        self.assertIn("MOD", active)
        self.assertEqual({"LOAD_LOCAL"}, removed)

    def test_freeze_tables_handle_escaped_pipes_in_stack_effects(self):
        # ITER_NEXT's stack-effect cell contains `val \| jump`; a naive split on
        # "|" shifts the classification column and loses the row.
        stable, provisional, removed = parse_freeze_stability_tables(_freeze_text())
        self.assertIn("ITER_NEXT", stable)
        self.assertEqual(set(), provisional)
        self.assertEqual({"LOAD_LOCAL"}, removed)

    def test_emit_scan_finds_opcodes_from_both_call_and_table_positions(self):
        emitted = scan_emitted_opcodes(str(_ROOT))
        self.assertIn("PUSH_CONST", emitted)   # self.emit("PUSH_CONST", ...)
        self.assertIn("MOD", emitted)          # op_map dict value only
        self.assertIn("RESET_LOCAL_IDX", emitted)


class RealRepoTests(unittest.TestCase):
    # closes: #366
    def test_frozen_opcode_set_matches_every_record(self):
        result = run_opcode_phase(str(_ROOT))
        self.assertEqual(
            [], [f"{f.message}: {f.detail}" for f in result.findings]
        )
        self.assertGreater(result.checks_run, 10)

    def test_every_documented_record_agrees_with_dispatch(self):
        dispatch, _ = load_dispatch_opcodes(str(_ROOT))
        inv_active, _ = parse_reference_inventory(_reference_text())
        app_active, _ = parse_reference_appendix(_reference_text())
        stable, _, _ = parse_freeze_stability_tables(_freeze_text())
        self.assertEqual(dispatch, inv_active)
        self.assertEqual(dispatch, app_active)
        self.assertEqual(dispatch, stable)

    def test_everything_the_compiler_emits_has_a_handler(self):
        dispatch, _ = load_dispatch_opcodes(str(_ROOT))
        emitted = set(scan_emitted_opcodes(str(_ROOT)))
        self.assertEqual(set(), emitted - dispatch)


class DriftDetectionTests(unittest.TestCase):
    """Each check must fire when its record drifts — not just pass when clean."""

    def test_undocumented_opcode_is_reported(self):
        result = OpcodeResult()
        _compare(result, "inventory", {"ADD", "SUB"}, {"ADD", "SUB", "NEWOP"})
        self.assertEqual(1, len(result.findings))
        self.assertIn("NEWOP", result.findings[0].detail)

    def test_documented_but_undispatched_opcode_is_reported(self):
        result = OpcodeResult()
        _compare(result, "inventory", {"ADD", "GHOST"}, {"ADD"})
        self.assertEqual(1, len(result.findings))
        self.assertIn("GHOST", result.findings[0].detail)

    def test_deleting_an_inventory_entry_is_detected(self):
        text = _reference_text()
        stripped = re.sub(r"\n### MOD\n.*?(?=\n### )", "", text, flags=re.S)
        active, _ = parse_reference_inventory(stripped)
        self.assertNotIn("MOD", active)

        dispatch, _ = load_dispatch_opcodes(str(_ROOT))
        result = OpcodeResult()
        _compare(result, "inventory", active, dispatch)
        self.assertEqual(1, len(result.findings))
        self.assertIn("MOD", result.findings[0].detail)


class SemanticSpecTests(unittest.TestCase):
    """#412 phase 2: the phase checks spec *coverage*, not only inventory.

    It cannot check semantics -- `tests/test_opcode_semantics.py` does that. What
    it checks is that the module which does is still aimed at the right set, so
    the result does not rot the way the inventory did before #366.
    """

    def _dispatch(self) -> set:
        dispatch, _ = load_dispatch_opcodes(str(_ROOT))
        return dispatch

    def test_the_real_repo_specifies_every_exception_opcode(self):
        result = OpcodeResult()
        _check_semantic_specs(result, str(_ROOT), _reference_text(), self._dispatch())
        self.assertEqual([], [f.message for f in result.findings])

    def test_the_exception_category_is_the_unwind_path(self):
        """If this set ever changes, the coverage requirement changed with it --
        which is the point of reading the category from the document."""
        categories = parse_reference_categories(_reference_text())
        exceptions = {op for op, cat in categories.items() if cat == "exceptions"}
        self.assertEqual({"SETUP_TRY", "POP_TRY", "FINALLY_END", "THROW"}, exceptions)

    def test_every_exception_opcode_is_named_in_the_spec_module(self):
        specified = parse_specified_opcodes(str(_ROOT))
        self.assertIsNotNone(specified)
        for op in ("SETUP_TRY", "POP_TRY", "FINALLY_END", "THROW"):
            self.assertIn(op, specified)

    def test_an_unspecified_exception_opcode_is_reported(self):
        """Drift in the direction that matters: a new unwind opcode, or a spec
        quietly dropped."""
        result = OpcodeResult()
        _check_semantic_specs(
            result, str(_ROOT),
            # Inserted *inside* §3 — appending past its terminating heading
            # puts the entry outside the section the parser reads, and the
            # check then passes for the wrong reason.
            _reference_text().replace(
                "### SETUP_TRY\n",
                "### NEW_UNWIND\n- Category: exceptions\n\n### SETUP_TRY\n",
                1,
            ),
            self._dispatch() | {"NEW_UNWIND"},
        )
        self.assertTrue(any("no semantic spec" in f.message for f in result.findings),
                        [f.message for f in result.findings])
        self.assertIn("NEW_UNWIND", " ".join(f.detail for f in result.findings))

    def test_a_spec_for_an_undispatched_opcode_is_reported(self):
        """A rename leaves the spec module covering a name nothing dispatches;
        that must be loud, not silently green."""
        result = OpcodeResult()
        _check_semantic_specs(result, str(_ROOT), _reference_text(),
                              self._dispatch() - {"POP_TRY"})
        self.assertTrue(any("does not dispatch" in f.message for f in result.findings),
                        [f.message for f in result.findings])

    def test_a_missing_spec_module_is_a_failure_not_a_skip(self):
        """A check may not pass by being unable to run -- the rule the shapes
        and consumers phases already follow."""
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        result = OpcodeResult()
        _check_semantic_specs(result, str(root), _reference_text(), self._dispatch())
        self.assertTrue(any("SPECIFIED" in f.message for f in result.findings),
                        [f.message for f in result.findings])


class ClaimAnchorTests(unittest.TestCase):
    """Policed prose claims fail loudly on both wrong numbers and rewording."""

    def _fixture_root(self) -> Path:
        root = Path(tempfile.mkdtemp())
        for rel, _, _, _ in CLAIM_ANCHORS:
            dest = root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists():
                shutil.copyfile(_ROOT / rel, dest)
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        return root

    def _run(self, root: Path, *, count: int, version: int = 4) -> OpcodeResult:
        result = OpcodeResult()
        _check_claims(result, str(root), dispatch_count=count,
                      bytecode_version=version)
        return result

    def test_clean_copy_passes(self):
        root = self._fixture_root()
        dispatch, version = load_dispatch_opcodes(str(_ROOT))
        result = self._run(root, count=len(dispatch), version=version)
        self.assertEqual([], [f.message for f in result.findings])

    def test_stale_count_is_reported(self):
        root = self._fixture_root()
        dispatch, version = load_dispatch_opcodes(str(_ROOT))
        result = self._run(root, count=len(dispatch) + 1, version=version)
        self.assertTrue(result.findings)
        self.assertTrue(
            any("wrong opcode count" in f.message for f in result.findings),
            [f.message for f in result.findings],
        )

    def test_unbumped_bytecode_version_is_reported(self):
        root = self._fixture_root()
        dispatch, version = load_dispatch_opcodes(str(_ROOT))
        result = self._run(root, count=len(dispatch), version=version + 1)
        self.assertTrue(
            any("wrong BYTECODE_VERSION" in f.message for f in result.findings),
            [f.message for f in result.findings],
        )

    def test_rewording_a_policed_claim_is_reported(self):
        root = self._fixture_root()
        target = root / "docs" / "runtime" / "INSTRUCTION_SEMANTICS.md"
        text = target.read_text(encoding="utf-8")
        target.write_text(
            text.replace("active opcodes are stable", "opcodes are locked down"),
            encoding="utf-8",
        )
        dispatch, version = load_dispatch_opcodes(str(_ROOT))
        result = self._run(root, count=len(dispatch), version=version)
        self.assertTrue(
            any("no longer matches" in f.message for f in result.findings),
            [f.message for f in result.findings],
        )


if __name__ == "__main__":
    unittest.main()
