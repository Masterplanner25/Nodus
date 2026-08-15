"""Every error reports the resolved absolute path of the file it is in (#342).

Two defects, one cause. Runtime errors resolved the path, syntax errors echoed
what the user typed, so the same command printed two conventions depending on
which phase failed and nothing parsing stderr could assume one shape.

The worse half was not in the report: a syntax error carried **no path at all**,
so the reporter fell back to the path the CLI was given. For a syntax error
inside an *imported* module that meant the **entry file's** name printed against
the *module's* line and column — a file that does not contain the error, at a
position that looks plausible in it. `nodus run imp.nd` blamed `imp.nd:1:25`
for a bug in `sub/bad.nd:1:25`.

The convention chosen is absolute, because that is what runtime errors and every
imported-module error already used; only the entry file was ever reported as
typed. `nodus check <file>` still echoes the given path in its `: OK` line —
that is not an error location.
"""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))  # noqa: E402

_NODUS_PY = str(_REPO_ROOT / "nodus.py")


class ErrorPathTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name).resolve()
        self.addCleanup(self._tmp.cleanup)
        (self.dir / "sub").mkdir()

    def write(self, name: str, body: str) -> Path:
        path = self.dir / name
        path.write_text(body, encoding="utf-8")
        return path

    def run_cli(self, *args: str) -> str:
        """Run nodus from the temp dir with relative arguments; return stderr."""
        proc = subprocess.run(
            [sys.executable, _NODUS_PY, *args],
            capture_output=True, text=True, timeout=60, cwd=str(self.dir),
            env={"PYTHONPATH": str(_REPO_ROOT / "src"),
                 "SYSTEMROOT": "C:\\Windows", "PATH": ""},
        )
        self.assertNotEqual(0, proc.returncode, f"expected failure:\n{proc.stdout}")
        return proc.stderr

    def assert_names(self, stderr: str, expected: Path) -> None:
        """The first error line must name `expected` by absolute path."""
        first = stderr.splitlines()[0]
        self.assertIn(" at ", first, first)
        location = first.split(" at ", 1)[1]
        reported = location.rsplit(".nd", 1)[0] + ".nd"
        self.assertTrue(os.path.isabs(reported),
                        f"path is not absolute: {first}")
        self.assertEqual(os.path.normcase(str(expected)),
                         os.path.normcase(os.path.realpath(reported)),
                         f"wrong file named:\n{first}")


# closes: #342
class SyntaxErrorsNameTheFileTheyAreInTests(ErrorPathTestCase):
    def test_imported_module_syntax_error_names_the_module_not_the_entry(self):
        # The defect the issue did not record: this named the entry file, at the
        # module's line and column.
        module = self.write("sub/bad.nd", "export fn f() { let a = = 1 }\n")
        self.write("main.nd", 'import "./sub/bad" as b\nprint(b.f())\n')
        self.assert_names(self.run_cli("run", "main.nd"), module)

    def test_same_under_check(self):
        module = self.write("sub/bad.nd", "export fn f() { let a = = 1 }\n")
        self.write("main.nd", 'import "./sub/bad" as b\nprint(b.f())\n')
        self.assert_names(self.run_cli("check", "main.nd"), module)

    def test_the_reported_position_points_at_the_bug_in_the_reported_file(self):
        # The old output was misleading in two directions at once: the entry
        # file's name against the module's line and column. Reading the position
        # out of the file the error *names* catches that; reading it out of the
        # file the test expects would pass either way, because the position was
        # always the module's.
        self.write("sub/bad.nd", "export fn f() { let a = = 1 }\n")
        self.write("main.nd", 'import "./sub/bad" as b\nprint(b.f())\n')

        first = self.run_cli("run", "main.nd").splitlines()[0]
        location = first.split(" at ", 1)[1]
        reported_path, line_s, col_s = location.split(": ", 1)[0].rsplit(":", 2)
        line, col = int(line_s), int(col_s)

        text = Path(reported_path).read_text(encoding="utf-8").splitlines()
        self.assertGreaterEqual(len(text), line, f"line does not exist: {first}")
        offending = text[line - 1][col - 1]
        self.assertEqual("=", offending,
                         f"position does not point at the bug in the file it names: {first}")


# closes: #342
class OneConventionEverywhereTests(ErrorPathTestCase):
    def test_entry_file_syntax_error_is_absolute(self):
        entry = self.write("bad.nd", "let x = = 10\n")
        self.assert_names(self.run_cli("run", "bad.nd"), entry)

    def test_entry_file_runtime_error_is_absolute(self):
        entry = self.write("rt.nd", "let x = 10\nprint(y)\n")
        self.assert_names(self.run_cli("run", "rt.nd"), entry)

    def test_check_entry_file_syntax_error_is_absolute(self):
        entry = self.write("bad.nd", "let x = = 10\n")
        self.assert_names(self.run_cli("check", "bad.nd"), entry)

    def test_sandbox_limit_error_is_absolute(self):
        # Carries no path of its own, so it exercises the reporter's fallback.
        entry = self.write("loop.nd", "let i = 0i\nwhile (true) { i = i + 1i }\n")
        self.assert_names(self.run_cli("run", "loop.nd", "--step-limit", "1000"),
                          entry)

    def test_run_and_check_agree_on_the_same_file(self):
        self.write("bad.nd", "let x = = 10\n")
        run_line = self.run_cli("run", "bad.nd").splitlines()[0]
        check_line = self.run_cli("check", "bad.nd").splitlines()[0]
        self.assertEqual(run_line.split(" at ", 1)[1],
                         check_line.split(" at ", 1)[1],
                         "run and check report the same error differently")


# closes: #342
class SuccessOutputIsUnchangedTests(ErrorPathTestCase):
    def test_check_ok_line_still_echoes_the_given_path(self):
        self.write("fine.nd", 'print("hi")\n')
        proc = subprocess.run(
            [sys.executable, _NODUS_PY, "check", "fine.nd"],
            capture_output=True, text=True, timeout=60, cwd=str(self.dir),
            env={"PYTHONPATH": str(_REPO_ROOT / "src"),
                 "SYSTEMROOT": "C:\\Windows", "PATH": ""},
        )
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertEqual("fine.nd: OK", proc.stdout.strip())


if __name__ == "__main__":
    unittest.main()
