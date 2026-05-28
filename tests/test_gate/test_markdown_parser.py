"""Tests for nodus_gate markdown_parser."""

import sys
import tempfile
import os
import unittest

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

    def test_collect_from_real_root(self):
        root = "C:/dev/Coding Language"
        files = collect_doc_files(root)
        # Should find some .md files
        self.assertIsInstance(files, list)

    def test_collect_is_sorted(self):
        root = "C:/dev/Coding Language"
        files = collect_doc_files(root)
        self.assertEqual(files, sorted(files))

    def test_include_design_adds_more(self):
        root = "C:/dev/Coding Language"
        without = collect_doc_files(root, include_design=False)
        with_design = collect_doc_files(root, include_design=True)
        # design dir should add files
        self.assertGreaterEqual(len(with_design), len(without))


if __name__ == "__main__":
    unittest.main()
