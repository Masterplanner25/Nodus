"""Sandbox enforcement for std:subprocess file redirects and cwd.

Covers:
  - stdout/stderr redirect to a path outside allowed_paths is blocked
  - cwd outside allowed_paths is blocked
  - Both NodusRuntime embedded mode and run_source CLI mode (fs_root)
  - Allowed paths and unrestricted mode still work
"""

import os
import sys
import tempfile
import unittest

from nodus import NodusRuntime
from nodus.runtime.diagnostics import LangRuntimeError
from nodus.tooling.runner import run_source

_PY = sys.executable.replace("\\", "/")
_IMPORT = 'import "std:subprocess" as sp\n'


def _fwd(path):
    return path.replace("\\", "/")


class SubprocessRedirectSandboxTests(unittest.TestCase):
    """stdout/stderr file redirects must respect allowed_paths."""

    def setUp(self):
        self.allowed_dir = tempfile.mkdtemp()
        self.outside_dir = tempfile.mkdtemp()
        self.allowed_out = _fwd(os.path.join(self.allowed_dir, "out.txt"))
        self.forbidden_out = _fwd(os.path.join(self.outside_dir, "forbidden.txt"))

    def tearDown(self):
        import shutil
        for d in (self.allowed_dir, self.outside_dir):
            shutil.rmtree(d, ignore_errors=True)

    # ── embedded mode ──────────────────────────────────────────────────────

    def test_stdout_redirect_forbidden_blocked_embedded(self):
        rt = NodusRuntime(allowed_paths=[self.allowed_dir], timeout_ms=10_000, max_steps=500_000)
        src = _IMPORT + f'sp.run(["{_PY}", "-c", "print(1)"], {{stdout: "{self.forbidden_out}"}})'
        r = rt.run_source(src)
        self.assertFalse(r["ok"], "stdout redirect to forbidden path should be blocked")
        self.assertEqual((r.get("error") or {}).get("kind"), "sandbox")
        self.assertFalse(os.path.exists(self.forbidden_out), "file must not have been created")

    def test_stderr_redirect_forbidden_blocked_embedded(self):
        rt = NodusRuntime(allowed_paths=[self.allowed_dir], timeout_ms=10_000, max_steps=500_000)
        src = _IMPORT + f'sp.run(["{_PY}", "-c", "import sys; sys.stderr.write(\'x\')"], {{stderr: "{self.forbidden_out}", check: false}})'
        r = rt.run_source(src)
        self.assertFalse(r["ok"], "stderr redirect to forbidden path should be blocked")
        self.assertEqual((r.get("error") or {}).get("kind"), "sandbox")
        self.assertFalse(os.path.exists(self.forbidden_out), "file must not have been created")

    def test_stdout_redirect_allowed_succeeds_embedded(self):
        rt = NodusRuntime(allowed_paths=[self.allowed_dir], timeout_ms=10_000, max_steps=500_000)
        src = _IMPORT + f'sp.run(["{_PY}", "-c", "print(\'written\')"], {{stdout: "{self.allowed_out}", check: false}})'
        r = rt.run_source(src)
        self.assertTrue(r["ok"], f"stdout redirect to allowed path should succeed: {r}")
        self.assertTrue(os.path.exists(self.allowed_out), "output file should have been created")
        self.assertIn("written", open(self.allowed_out, encoding="utf-8").read())

    def test_stdout_append_redirect_forbidden_blocked_embedded(self):
        rt = NodusRuntime(allowed_paths=[self.allowed_dir], timeout_ms=10_000, max_steps=500_000)
        # ">>" prefix means append mode
        src = _IMPORT + f'sp.run(["{_PY}", "-c", "print(1)"], {{stdout: ">>{self.forbidden_out}"}})'
        r = rt.run_source(src)
        self.assertFalse(r["ok"], "append redirect to forbidden path should be blocked")
        self.assertEqual((r.get("error") or {}).get("kind"), "sandbox")

    def test_no_restriction_when_unrestricted_embedded(self):
        rt = NodusRuntime(timeout_ms=10_000, max_steps=500_000)
        src = _IMPORT + f'sp.run(["{_PY}", "-c", "print(\'ok\')"], {{stdout: "{self.allowed_out}", check: false}})'
        r = rt.run_source(src)
        self.assertTrue(r["ok"], "unrestricted mode should allow any path")

    # ── CLI mode (fs_root) ─────────────────────────────────────────────────

    def test_stdout_redirect_forbidden_blocked_cli(self):
        result, _vm = run_source(
            _IMPORT + f'sp.run(["{_PY}", "-c", "print(1)"], {{stdout: "{self.forbidden_out}"}})',
            max_steps=500_000,
            timeout_ms=10_000,
            fs_root=self.allowed_dir,
        )
        self.assertFalse(result.get("ok"), "stdout redirect should be blocked in CLI mode")
        self.assertEqual((result.get("error") or {}).get("kind"), "sandbox")
        self.assertFalse(os.path.exists(self.forbidden_out))

    def test_stderr_redirect_forbidden_blocked_cli(self):
        result, _vm = run_source(
            _IMPORT + f'sp.run(["{_PY}", "-c", "import sys; sys.stderr.write(\'x\')"], {{stderr: "{self.forbidden_out}", check: false}})',
            max_steps=500_000,
            timeout_ms=10_000,
            fs_root=self.allowed_dir,
        )
        self.assertFalse(result.get("ok"), "stderr redirect should be blocked in CLI mode")
        self.assertEqual((result.get("error") or {}).get("kind"), "sandbox")
        self.assertFalse(os.path.exists(self.forbidden_out))


class SubprocessCwdSandboxTests(unittest.TestCase):
    """cwd option must respect allowed_paths."""

    def setUp(self):
        self.allowed_dir = tempfile.mkdtemp()
        self.outside_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        for d in (self.allowed_dir, self.outside_dir):
            shutil.rmtree(d, ignore_errors=True)

    # ── embedded mode ──────────────────────────────────────────────────────

    def test_cwd_outside_allowed_blocked_embedded(self):
        rt = NodusRuntime(allowed_paths=[self.allowed_dir], timeout_ms=10_000, max_steps=500_000)
        outside_fwd = _fwd(self.outside_dir)
        src = _IMPORT + f'sp.run(["{_PY}", "-c", "pass"], {{cwd: "{outside_fwd}"}})'
        r = rt.run_source(src)
        self.assertFalse(r["ok"], "cwd outside allowed_paths should be blocked")
        self.assertEqual((r.get("error") or {}).get("kind"), "sandbox")

    def test_cwd_within_allowed_succeeds_embedded(self):
        rt = NodusRuntime(allowed_paths=[self.allowed_dir], timeout_ms=10_000, max_steps=500_000)
        allowed_fwd = _fwd(self.allowed_dir)
        src = _IMPORT + f'sp.run(["{_PY}", "-c", "pass"], {{cwd: "{allowed_fwd}", check: false}})'
        r = rt.run_source(src)
        self.assertTrue(r["ok"], f"cwd within allowed_paths should succeed: {r}")

    def test_cwd_no_restriction_when_unrestricted_embedded(self):
        rt = NodusRuntime(timeout_ms=10_000, max_steps=500_000)
        outside_fwd = _fwd(self.outside_dir)
        src = _IMPORT + f'sp.run(["{_PY}", "-c", "pass"], {{cwd: "{outside_fwd}", check: false}})'
        r = rt.run_source(src)
        self.assertTrue(r["ok"], "unrestricted mode should allow any cwd")

    # ── CLI mode (fs_root) ─────────────────────────────────────────────────

    def test_cwd_outside_blocked_cli(self):
        outside_fwd = _fwd(self.outside_dir)
        result, _vm = run_source(
            _IMPORT + f'sp.run(["{_PY}", "-c", "pass"], {{cwd: "{outside_fwd}"}})',
            max_steps=500_000,
            timeout_ms=10_000,
            fs_root=self.allowed_dir,
        )
        self.assertFalse(result.get("ok"), "cwd outside fs_root should be blocked in CLI mode")
        self.assertEqual((result.get("error") or {}).get("kind"), "sandbox")


if __name__ == "__main__":
    unittest.main()
