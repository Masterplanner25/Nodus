"""Tests for nodus_gate runtime phase."""

import sys
import tempfile
import os
import shutil
import unittest

sys.path.insert(0, "C:/dev/Coding Language")  # noqa: E402
sys.path.insert(0, "C:/dev/Coding Language/src")  # noqa: E402

from tools.nodus_gate.runtime_phase import run_runtime_phase, _run_block_with_timeout  # noqa: E402


def _make_temp_doc_root(content: str) -> str:
    """Create a temp root with docs/language/test.md."""
    root = tempfile.mkdtemp()
    lang = os.path.join(root, "docs", "language")
    os.makedirs(lang, exist_ok=True)
    with open(os.path.join(lang, "test.md"), "w", encoding="utf-8") as f:
        f.write(content)
    return root


class RunBlockTests(unittest.TestCase):
    """Unit tests for _run_block_with_timeout."""

    def test_simple_pass(self):
        stdout, stderr, err = _run_block_with_timeout('print("hello")', 5000)
        self.assertIsNone(err)
        self.assertIn("hello", stdout)

    def test_runtime_error_captured(self):
        stdout, stderr, err = _run_block_with_timeout(
            'let x = 1i\nx.nonexistent_field', 5000
        )
        self.assertIsNotNone(err)

    def test_syntax_error_captured(self):
        _, _, err = _run_block_with_timeout("let = broken syntax !!!", 5000)
        self.assertIsNotNone(err)

    def test_output_captured(self):
        stdout, _, err = _run_block_with_timeout('print(42i)\nprint("done")', 5000)
        self.assertIsNone(err)
        self.assertIn("42", stdout)
        self.assertIn("done", stdout)


class RuntimePhaseTests(unittest.TestCase):

    def _run(self, content: str) -> object:
        root = _make_temp_doc_root(content)
        try:
            return run_runtime_phase(root)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_valid_block_passes(self):
        result = self._run('```nodus\nprint(1i + 1i)\n```\n')
        self.assertEqual(result.passed, 1)
        self.assertEqual(len(result.findings), 0)

    def test_erroring_block_fails(self):
        result = self._run('```nodus\nthrow "boom"\n```\n')
        err_findings = [f for f in result.findings if f.kind == "error"]
        self.assertGreater(len(err_findings), 0)

    def test_no_run_block_skipped(self):
        result = self._run('```nodus-no-run\nthrow "never runs"\n```\n')
        self.assertEqual(result.total_blocks, 0)
        self.assertEqual(result.passed, 0)
        self.assertEqual(len(result.findings), 0)

    def test_skip_block_skipped(self):
        result = self._run('```nodus-skip\nthrow "never runs"\n```\n')
        self.assertEqual(result.total_blocks, 0)

    def test_expect_output_correct(self):
        md = '```nodus-expect=output\nprint("hi")\n```\n\nOutput:\n\n```\nhi\n```\n'
        result = self._run(md)
        self.assertEqual(len(result.findings), 0)
        self.assertEqual(result.passed, 1)

    def test_expect_output_wrong_fails(self):
        md = '```nodus-expect=output\nprint("hello")\n```\n\nOutput:\n\n```\nworld\n```\n'
        result = self._run(md)
        mismatch = [f for f in result.findings if f.kind == "output_mismatch"]
        self.assertEqual(len(mismatch), 1)
        self.assertIn("hello", mismatch[0].actual_output)

    def test_expect_output_missing_companion(self):
        md = '```nodus-expect=output\nprint("x")\n```\n'
        result = self._run(md)
        no_exp = [f for f in result.findings if f.kind == "no_expected_output"]
        self.assertEqual(len(no_exp), 1)

    def test_allowlist_suppresses_block(self):
        content = '```nodus\nthrow "boom"\n```\n'
        root = _make_temp_doc_root(content)
        try:
            rel_path = os.path.relpath(
                os.path.join(root, "docs", "language", "test.md"), root
            ).replace("\\", "/")
            allowlist = {f"block:{rel_path}:1"}
            result = run_runtime_phase(root, allowlist=allowlist)
            self.assertEqual(len(result.findings), 0)
            self.assertEqual(result.passed, 1)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_multiple_blocks(self):
        md = (
            '```nodus\nprint("a")\n```\n\n'
            '```nodus\nprint("b")\n```\n\n'
            '```nodus-no-run\nbroken\n```\n'
        )
        result = self._run(md)
        self.assertEqual(result.total_blocks, 2)
        self.assertEqual(result.passed, 2)

    def test_scanned_files_count(self):
        md = '```nodus\nprint(1i)\n```\n'
        root = _make_temp_doc_root(md)
        try:
            result = run_runtime_phase(root)
            self.assertEqual(result.scanned_files, 1)
        finally:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
