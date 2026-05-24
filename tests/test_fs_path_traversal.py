"""Tests for CLI-mode path traversal enforcement (BUG-016)."""

import os
import tempfile
import unittest

from nodus.runtime.diagnostics import LangRuntimeError
from nodus.tooling.runner import run_source
from nodus.vm.vm import VM


class FsRootPathTraversalTests(unittest.TestCase):
    def _vm(self, fs_root):
        return VM([], {}, code_locs=[], fs_root=fs_root)

    def test_read_within_root_allowed(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "data.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write("hello")
            vm = self._vm(root)
            self.assertEqual(vm.builtin_read_file(path), "hello")

    def test_read_traversal_blocked(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as outside:
            victim = os.path.join(outside, "secret.txt")
            with open(victim, "w", encoding="utf-8") as f:
                f.write("sensitive")
            vm = self._vm(root)
            with self.assertRaises(LangRuntimeError) as ctx:
                vm.builtin_read_file(victim)
            self.assertEqual(ctx.exception.kind, "sandbox")

    def test_mkdir_within_root_allowed(self):
        with tempfile.TemporaryDirectory() as root:
            target = os.path.join(root, "subdir")
            result, _vm = run_source(
                f'mkdir("{target.replace(chr(92), "/")}")',
                max_steps=10_000,
                timeout_ms=5_000,
                fs_root=root,
            )
            self.assertTrue(result.get("ok"), result)
            self.assertTrue(os.path.isdir(target))

    def test_mkdir_traversal_blocked(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as outside:
            target = os.path.join(outside, "injected").replace("\\", "/")
            result, _vm = run_source(
                f'mkdir("{target}")',
                max_steps=10_000,
                timeout_ms=5_000,
                fs_root=root,
            )
            self.assertFalse(result.get("ok"), "Expected mkdir traversal to be blocked")
            error = result.get("error") or {}
            kind = error.get("kind", "") if isinstance(error, dict) else ""
            self.assertEqual(kind, "sandbox")

    def test_no_fs_root_no_allowed_paths_unrestricted(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "x.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write("ok")
            vm = VM([], {}, code_locs=[])
            self.assertEqual(vm.builtin_read_file(path), "ok")

    def test_allowed_paths_takes_precedence_over_fs_root(self):
        with tempfile.TemporaryDirectory() as allowed, tempfile.TemporaryDirectory() as root:
            path = os.path.join(allowed, "data.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write("yes")
            vm = VM([], {}, code_locs=[], fs_root=root, allowed_paths=[allowed])
            self.assertEqual(vm.builtin_read_file(path), "yes")


if __name__ == "__main__":
    unittest.main()
