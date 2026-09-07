"""Tests for nodus_gate markdown_parser."""

import sys
import tempfile
import os
import unittest
from pathlib import Path

sys.path.insert(0, "C:/dev/Coding Language")  # noqa: E402
sys.path.insert(0, "C:/dev/Coding Language/src")  # noqa: E402

from tools.nodus_gate.markdown_parser import extract_blocks, collect_doc_files  # noqa: E402


def _write_temp(content: str) -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8")
    f.write(content)
    f.close()
    return f.name


class ExtractBlocksTests(unittest.TestCase):

    def setUp(self):
        self._tmp_files = []

    def tearDown(self):
        for f in self._tmp_files:
            try:
                os.unlink(f)
            except OSError:
                pass

    def _tmp(self, content: str) -> str:
        p = _write_temp(content)
        self._tmp_files.append(p)
        return p

    def test_plain_nodus_block(self):
        path = self._tmp('```nodus\nprint("hello")\n```\n')
        blocks = extract_blocks(path)
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].fence_type, "nodus")
        self.assertIn("hello", blocks[0].source)

    def test_no_run_block(self):
        path = self._tmp('```nodus-no-run\nlet x = broken\n```\n')
        blocks = extract_blocks(path)
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0].fence_type, "nodus-no-run")
        self.assertFalse(blocks[0].should_run)
        self.assertTrue(blocks[0].is_static_only)

    def test_skip_block(self):
        path = self._tmp('```nodus-skip\nold code\n```\n')
        blocks = extract_blocks(path)
        self.assertEqual(len(blocks), 1)
        self.assertTrue(blocks[0].is_skip)

    def test_expect_output_with_companion(self):
        md = (
            '```nodus-expect=output\nprint("hello")\n```\n\n'
            'Output:\n\n'
            '```\nhello\n```\n'
        )
        path = self._tmp(md)
        blocks = extract_blocks(path)
        # Should have nodus-expect=output block; companion plain block filtered out
        nodus_blocks = [b for b in blocks if b.fence_type == "nodus-expect=output"]
        self.assertEqual(len(nodus_blocks), 1)
        self.assertEqual(nodus_blocks[0].expected_output.strip(), "hello")

    def test_expect_output_requires_companion(self):
        path = self._tmp('```nodus-expect=output\nprint("x")\n```\n')
        blocks = extract_blocks(path)
        self.assertEqual(blocks[0].expected_output, None)

    def test_multiple_blocks(self):
        md = (
            '```nodus\nlet x = 1i\n```\n\n'
            '```nodus-no-run\nplaceholder\n```\n\n'
            '```nodus-skip\nignored\n```\n'
        )
        path = self._tmp(md)
        blocks = extract_blocks(path)
        self.assertEqual(len(blocks), 3)
        types = [b.fence_type for b in blocks]
        self.assertIn("nodus", types)
        self.assertIn("nodus-no-run", types)
        self.assertIn("nodus-skip", types)

    def test_start_line_tracking(self):
        path = self._tmp("Line 1\nLine 2\n```nodus\ncode\n```\n")
        blocks = extract_blocks(path)
        self.assertEqual(blocks[0].start_line, 3)

    def test_timeout_option_seconds(self):
        path = self._tmp('```nodus-expect=output timeout=30s\nprint(1)\n```\n')
        blocks = extract_blocks(path)
        self.assertEqual(blocks[0].timeout_ms, 30_000)

    def test_timeout_option_default(self):
        path = self._tmp('```nodus\nprint(1)\n```\n')
        blocks = extract_blocks(path)
        self.assertEqual(blocks[0].timeout_ms, 10_000)

    def test_non_nodus_blocks_ignored(self):
        path = self._tmp('```python\nx = 1\n```\n\n```json\n{}\n```\n')
        blocks = extract_blocks(path)
        self.assertEqual(len(blocks), 0)

    def test_should_run_flags(self):
        md = (
            '```nodus\ncode\n```\n'
            '```nodus-expect=output\ncode\n```\n'
            '```nodus-no-run\ncode\n```\n'
            '```nodus-skip\ncode\n```\n'
        )
        path = self._tmp(md)
        blocks = extract_blocks(path)
        by_type = {b.fence_type: b for b in blocks}
        self.assertTrue(by_type["nodus"].should_run)
        self.assertTrue(by_type["nodus-expect=output"].should_run)
        self.assertFalse(by_type["nodus-no-run"].should_run)
        self.assertFalse(by_type["nodus-skip"].should_run)

    def test_file_not_found_returns_empty(self):
        blocks = extract_blocks("/nonexistent/path.md")
        self.assertEqual(blocks, [])


class CollectDocFilesTests(unittest.TestCase):
    """Which documents the gate scans.

    These used to hardcode `root = "C:/dev/Coding Language"`, which does not
    exist on a CI runner -- so `collect_doc_files` returned `[]` there and every
    assertion held trivially. Measured: `assertIsInstance([], list)`,
    `[] == sorted([])` and `len([]) >= len([])` are all true, so all three tests
    passed by checking nothing on the machine that arbitrates.

    The root comes from `__file__` now, and each assertion would fail against an
    empty result.
    """

    ROOT = str(Path(__file__).resolve().parents[2])

    def test_collect_finds_the_documents(self):
        files = collect_doc_files(self.ROOT)
        self.assertTrue(files, "no documents collected -- is the root right?")

    def test_collect_is_sorted(self):
        files = collect_doc_files(self.ROOT)
        self.assertTrue(files)
        self.assertEqual(files, sorted(files))

    def test_include_design_adds_more(self):
        without = collect_doc_files(self.ROOT, include_design=False)
        with_design = collect_doc_files(self.ROOT, include_design=True)
        self.assertTrue(without)
        self.assertGreater(
            len(with_design), len(without),
            "--include-design added nothing; the design docs are not being found",
        )

    def test_migration_docs_are_scanned(self):
        """The documents people follow *during an upgrade*.

        They were outside the scan until `v6.0-staged-flips.md` was written, so
        nothing had ever run their examples -- the highest-stakes docs were the
        unchecked ones. Adding the pattern turned up nine pre-existing
        fragments, all allowlisted with a reason.
        """
        files = collect_doc_files(self.ROOT)
        migration = [f for f in files if "migration" in Path(f).as_posix()]
        self.assertTrue(
            migration,
            "docs/migration/ is not in the gate's scan; its examples are unchecked",
        )
        self.assertTrue(
            any("v6.0-staged-flips" in f for f in migration),
            "the 6.0.0 migration guide is not being scanned",
        )


if __name__ == "__main__":
    unittest.main()
