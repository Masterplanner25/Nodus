"""Pointing `run`/`check` at a directory that is not a project (#807).

It used to hand back a raw `FileNotFoundError` naming a `nodus.toml` that was
never there — correct exit code, Python internals as the message, for an
ordinary mistake. The neighbouring cases were already fine, which is what made
it stand out: a nonexistent path says "File not found", a real project is
discovered, a named file just works.

The message names the *actual* root when there is one above, because the common
shape is `nodus check src` typed from inside a real project and the useful reply
is where the project is.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PYTHON = sys.executable

MANIFEST = '[package]\nname = "probe"\nversion = "0.1.0"\n'
ENTRY = 'fn main() {\n    print("hi")\n}\n'


class _Tree(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name
        self.addCleanup(self._tmp.cleanup)

    def make_project(self) -> None:
        with open(os.path.join(self.dir, "nodus.toml"), "w", encoding="utf-8") as h:
            h.write(MANIFEST)
        os.makedirs(os.path.join(self.dir, "src"), exist_ok=True)
        with open(os.path.join(self.dir, "src", "main.nd"), "w", encoding="utf-8") as h:
            h.write(ENTRY)

    def nodus(self, *args: str, cwd: str | None = None):
        env = dict(os.environ)
        env["PYTHONPATH"] = str(REPO / "src")
        return subprocess.run(
            [PYTHON, "-m", "nodus", *args],
            cwd=cwd or self.dir, capture_output=True, text=True, env=env, timeout=120,
        )


class NoProjectHereTests(_Tree):
    # closes: #807
    def test_a_directory_with_no_manifest_does_not_leak_an_errno(self):
        self.make_project()
        for command in ("check", "run"):
            with self.subTest(command=command):
                result = self.nodus(command, "src")
                self.assertEqual(result.returncode, 1)
                self.assertNotIn("Errno", result.stderr)
                self.assertNotIn("nodus.toml'", result.stderr.replace("nodus.toml.", ""))
                self.assertIn("No Nodus project in", result.stderr)

    # closes: #807
    def test_it_names_the_real_project_root_when_there_is_one(self):
        """The common mistake is `nodus check src` from inside a project."""
        self.make_project()
        result = self.nodus("check", "src")
        self.assertIn(self.dir, result.stderr, "the message should say where the project is")
        self.assertIn("run this from there", result.stderr)

    def test_with_no_project_above_it_says_what_to_do_instead(self):
        os.makedirs(os.path.join(self.dir, "sub"))
        result = self.nodus("run", "sub")
        self.assertEqual(result.returncode, 1)
        self.assertIn("No Nodus project in", result.stderr)
        self.assertIn("Name a file directly", result.stderr)
        self.assertNotIn("run this from there", result.stderr, "there is no root to name")


class TheNeighbouringCasesAreUnchangedTests(_Tree):
    """Each of these was already right, and a fix that broke one is not a fix."""

    def test_a_nonexistent_path_still_says_file_not_found(self):
        result = self.nodus("check", "nosuchdir")
        self.assertIn("File not found", result.stderr)

    def test_a_real_project_directory_still_resolves(self):
        self.make_project()
        result = self.nodus("check", ".")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("OK", result.stdout)

    def test_project_discovery_from_inside_still_works(self):
        self.make_project()
        result = self.nodus("check", cwd=os.path.join(self.dir, "src"))
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_naming_a_file_still_works(self):
        self.make_project()
        result = self.nodus("check", "src/main.nd")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_malformed_manifest_keeps_its_own_message(self):
        """The other raise sites were left alone on purpose.

        `ManifestError` is written for a reader; folding it into the generic
        no-project sentence would lose the detail that makes it useful.
        """
        with open(os.path.join(self.dir, "nodus.toml"), "w", encoding="utf-8") as h:
            h.write('[package]\nname = "probe"\nversion = "0.1.0"\n[nonsense]\nx = 1\n')
        result = self.nodus("check", ".")
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("No Nodus project in", result.stderr)
        self.assertIn("nonsense", result.stderr, "the manifest error names the offending table")


if __name__ == "__main__":
    unittest.main()
