import os
import tempfile
import unittest

from nodus.runtime.diagnostics import LangRuntimeError
from nodus.vm.vm import VM


class SandboxFilesystemTests(unittest.TestCase):
    def test_filesystem_allowlist_allows_root(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "data.txt")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("ok")
            vm = VM([], {}, code_locs=[], allowed_paths=[td])
            self.assertEqual(vm.builtin_read_file(path), "ok")

    def test_filesystem_allowlist_blocks_outside(self):
        with tempfile.TemporaryDirectory() as allowed, tempfile.TemporaryDirectory() as outside:
            path = os.path.join(outside, "secret.txt")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("nope")
            vm = VM([], {}, code_locs=[], allowed_paths=[allowed])
            with self.assertRaises(LangRuntimeError) as ctx:
                vm.builtin_read_file(path)
            self.assertEqual(ctx.exception.kind, "sandbox")


if __name__ == "__main__":
    unittest.main()
