"""Tests for UTF-8 BOM handling in source files (BUG-017)."""

import os
import tempfile
import unittest

from nodus.tooling.runner import run_source
from nodus.vm.vm import VM


class BomHandlingTests(unittest.TestCase):
    def test_bom_source_file_runs_without_crash(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "bom.nd")
            # Write file with UTF-8 BOM prefix
            with open(path, "wb") as f:
                f.write(b"\xef\xbb\xbfprint(\"hello\")\n")
            with open(path, "r", encoding="utf-8-sig") as _f:
                _src = _f.read()
            result, _vm = run_source(
                _src,
                filename=path,
                max_steps=10_000,
                timeout_ms=5_000,
            )
            self.assertTrue(result.get("ok"), result)
            self.assertIn("hello", result.get("stdout", ""))

    def test_bom_stripped_from_read_file_builtin(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "bom_data.txt")
            with open(path, "wb") as f:
                f.write(b"\xef\xbb\xbfcontent")
            vm = VM([], {}, code_locs=[], fs_root=td)
            result = vm.builtin_read_file(path)
            # BOM should be stripped
            self.assertFalse(result.startswith("﻿"))
            self.assertEqual(result, "content")

    def test_no_bom_file_unaffected(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "normal.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write("normal content")
            vm = VM([], {}, code_locs=[], fs_root=td)
            self.assertEqual(vm.builtin_read_file(path), "normal content")


if __name__ == "__main__":
    unittest.main()
