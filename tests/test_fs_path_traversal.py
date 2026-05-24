"""Tests for CLI-mode path traversal enforcement (BUG-016) and
stdlib sandbox enforcement via invoke_function (BUG-046)."""

import os
import tempfile
import unittest

from nodus import NodusRuntime
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


class StdlibSandboxTests(unittest.TestCase):
    """BUG-046: allowed_paths must be forwarded to module VMs created by invoke_function.

    Before the fix, fs.read / fs.write / fs.exists / fs.listdir / fs.append all
    bypassed NodusRuntime(allowed_paths=...) by calling through NodusModule.invoke_function,
    which created a new VM without forwarding the sandbox config.
    """

    def _dirs(self):
        """Return (allowed_dir, outside_dir, allowed_file, forbidden_file) as forward-slash paths."""
        allowed = tempfile.mkdtemp()
        outside = tempfile.mkdtemp()
        af = os.path.join(allowed, "data.txt")
        ff = os.path.join(outside, "secret.txt")
        with open(af, "w", encoding="utf-8") as f:
            f.write("allowed data")
        with open(ff, "w", encoding="utf-8") as f:
            f.write("FORBIDDEN")
        return allowed, outside, af.replace("\\", "/"), ff.replace("\\", "/")

    def tearDown(self):
        import shutil
        for attr in ("_allowed", "_outside"):
            path = getattr(self, attr, None)
            if path and os.path.isdir(path):
                shutil.rmtree(path, ignore_errors=True)

    def _rt(self, allowed):
        return NodusRuntime(allowed_paths=[allowed], timeout_ms=5_000, max_steps=100_000)

    def _run(self, rt, source):
        return rt.run_source(source)

    def _fwd(self, path):
        return path.replace("\\", "/")

    # --- fs.read ---

    def test_stdlib_fs_read_allowed_file_succeeds(self):
        allowed, outside, af, ff = self._dirs()
        self._allowed, self._outside = allowed, outside
        rt = self._rt(allowed)
        r = rt.run_source(f'import "std:fs" as fs\nprint(fs.read("{af}"))')
        self.assertTrue(r["ok"], r)
        self.assertIn("allowed data", r["stdout"])

    def test_stdlib_fs_read_forbidden_file_blocked(self):
        allowed, outside, af, ff = self._dirs()
        self._allowed, self._outside = allowed, outside
        rt = self._rt(allowed)
        r = rt.run_source(f'import "std:fs" as fs\nprint(fs.read("{ff}"))')
        self.assertFalse(r["ok"], "fs.read should be blocked for forbidden path")
        error = r.get("error") or {}
        self.assertEqual(error.get("kind"), "sandbox")
        self.assertNotIn("FORBIDDEN", r["stdout"])

    def test_stdlib_fs_read_traversal_blocked(self):
        allowed, outside, af, ff = self._dirs()
        self._allowed, self._outside = allowed, outside
        # Build traversal path: allowed/../outside/secret.txt
        traversal = self._fwd(os.path.join(allowed, "..", os.path.basename(outside), "secret.txt"))
        rt = self._rt(allowed)
        r = rt.run_source(f'import "std:fs" as fs\nprint(fs.read("{traversal}"))')
        self.assertFalse(r["ok"], "fs.read via traversal should be blocked")
        error = r.get("error") or {}
        self.assertEqual(error.get("kind"), "sandbox")
        self.assertNotIn("FORBIDDEN", r["stdout"])

    # --- fs.write ---

    def test_stdlib_fs_write_forbidden_path_blocked(self):
        allowed, outside, af, ff = self._dirs()
        self._allowed, self._outside = allowed, outside
        write_target = self._fwd(os.path.join(outside, "written.txt"))
        rt = self._rt(allowed)
        r = rt.run_source(f'import "std:fs" as fs\nfs.write("{write_target}", "pwned")')
        self.assertFalse(r["ok"], "fs.write should be blocked outside allowed_paths")
        error = r.get("error") or {}
        self.assertEqual(error.get("kind"), "sandbox")
        self.assertFalse(os.path.exists(write_target.replace("/", os.sep)))

    # --- fs.exists ---

    def test_stdlib_fs_exists_forbidden_path_blocked(self):
        allowed, outside, af, ff = self._dirs()
        self._allowed, self._outside = allowed, outside
        rt = self._rt(allowed)
        r = rt.run_source(f'import "std:fs" as fs\nprint(fs.exists("{ff}"))')
        self.assertFalse(r["ok"], "fs.exists should be blocked for forbidden path")
        error = r.get("error") or {}
        self.assertEqual(error.get("kind"), "sandbox")

    # --- fs.listdir ---

    def test_stdlib_fs_listdir_forbidden_dir_blocked(self):
        allowed, outside, af, ff = self._dirs()
        self._allowed, self._outside = allowed, outside
        outside_fwd = self._fwd(outside)
        rt = self._rt(allowed)
        r = rt.run_source(f'import "std:fs" as fs\nprint(fs.listdir("{outside_fwd}"))')
        self.assertFalse(r["ok"], "fs.listdir should be blocked for forbidden dir")
        error = r.get("error") or {}
        self.assertEqual(error.get("kind"), "sandbox")

    # --- allowed_paths=[] (block all) ---

    def test_stdlib_fs_read_empty_allowed_paths_blocks_all(self):
        allowed, outside, af, ff = self._dirs()
        self._allowed, self._outside = allowed, outside
        rt = NodusRuntime(allowed_paths=[], timeout_ms=5_000, max_steps=100_000)
        r = rt.run_source(f'import "std:fs" as fs\nprint(fs.read("{af}"))')
        self.assertFalse(r["ok"], "allowed_paths=[] should block all fs access including allowed dir")
        error = r.get("error") or {}
        self.assertEqual(error.get("kind"), "sandbox")

    # --- CLI mode (runner.run_source with fs_root) ---

    def test_stdlib_fs_read_respects_fs_root_in_cli_mode(self):
        allowed, outside, af, ff = self._dirs()
        self._allowed, self._outside = allowed, outside
        result, _vm = run_source(
            f'import "std:fs" as fs\nprint(fs.read("{ff}"))',
            max_steps=100_000,
            timeout_ms=5_000,
            fs_root=allowed,
        )
        self.assertFalse(result.get("ok"), "fs.read via stdlib should respect fs_root in CLI mode")
        error = result.get("error") or {}
        self.assertEqual(error.get("kind"), "sandbox")
        self.assertNotIn("FORBIDDEN", result.get("stdout", ""))


if __name__ == "__main__":
    unittest.main()
