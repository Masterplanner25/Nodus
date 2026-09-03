"""Run the `nodus-scheduler` package's own `.nd` suite (#88).

The library is written in Nodus, so its tests are too — `nodus test` on
`packages/nodus-scheduler/tests/scheduler_test.nd`. Nothing else in the Python
suite would run them, and a test suite CI does not run is a test suite that
rots.

Kept as a thin shell-out rather than reimplemented in Python on purpose. The
question these answer — "does this schedule expression mean the instant a
person expects" — is the library's own, and asking it twice in two languages
would be the duplicated question this codebase keeps finding.

`test_the_suite_is_reachable_at_all` is the one that earns its place: a
`--time-limit`-less subprocess, a moved file, or a missing `nodus.toml` all make
the suite silently run zero cases, and "0 tests, 0 failed" exits 0.
"""

import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PACKAGE = _REPO_ROOT / "packages" / "nodus-scheduler"


def run_nd_suite() -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONPATH=str(_REPO_ROOT / "src"))
    return subprocess.run(
        [sys.executable, str(_REPO_ROOT / "nodus.py"), "test", "tests/scheduler_test.nd"],
        capture_output=True,
        text=True,
        cwd=str(_PACKAGE),
        env=env,
        # The leap-day case searches ~790 days of calendar in the interpreter.
        # Generous rather than tight: this races nothing, and a timeout here
        # would read as a scheduling bug (#711).
        timeout=600,
    )


class TheSchedulerPackageSuiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.proc = run_nd_suite()

    # closes: #88
    def test_the_suite_is_reachable_at_all(self):
        """A suite that ran zero cases exits 0 and looks exactly like success."""
        self.assertIn("Tests:", self.proc.stdout, self.proc.stderr)
        match = re.search(r"Tests:\s+(\d+) total", self.proc.stdout)
        self.assertIsNotNone(match, f"no test count in output:\n{self.proc.stdout}")
        self.assertGreaterEqual(
            int(match.group(1)), 20, "the .nd suite did not collect its cases"
        )

    # closes: #88
    def test_every_case_passes(self):
        self.assertEqual(
            0, self.proc.returncode, f"{self.proc.stdout}\n{self.proc.stderr}"
        )
        self.assertNotIn("failed", self.proc.stdout.lower().replace("0 failed", ""))


class ThePackageIsShapedForImportTests(unittest.TestCase):
    """The two things that make the relative import resolve, both of which fail
    as "path escapes the project root" rather than as anything about imports."""

    # closes: #88
    def test_the_manifest_marks_the_package_root(self):
        """`find_project_root` walks up for `nodus.toml`. Without one, the root
        falls back to the *test file's* directory and `../src/scheduler.nd`
        escapes it."""
        self.assertTrue((_PACKAGE / "nodus.toml").is_file())

    # closes: #88
    def test_the_module_is_where_the_manifest_says(self):
        self.assertTrue((_PACKAGE / "src" / "scheduler.nd").is_file())
        manifest = (_PACKAGE / "nodus.toml").read_text(encoding="utf-8")
        self.assertIn('entry = "src/scheduler.nd"', manifest)


if __name__ == "__main__":
    unittest.main()
