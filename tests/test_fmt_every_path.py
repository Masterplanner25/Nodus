"""`nodus fmt` handles every path it is given (#954).

It used to format `positional[0]` and silently drop the rest, exiting 0. The
format gate's advice (`Run: python nodus.py fmt <every unformatted path>`) and
CLAUDE.md's `python nodus.py fmt src/nodus/stdlib/*.nd` both pass several, so
following either fixed one file and left the gate failing on the others.
"""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent

# Valid, and not in the formatter's layout.
_UNFORMATTED = "fn f(x) {\nif (x) { print(1) } else { print(2) }\n}\n"


def _fmt(*args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(_REPO / "src")
    return subprocess.run(
        [sys.executable, str(_REPO / "nodus.py"), "fmt", *args],
        capture_output=True, text=True, env=env, timeout=180,
    )


# closes: #954
class EveryPathIsHandled(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.paths = []
        for name in ("a.nd", "b.nd", "c.nd"):
            path = os.path.join(self._dir.name, name)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(_UNFORMATTED)
            self.paths.append(path)

    def tearDown(self):
        self._dir.cleanup()

    def _contents(self):
        return [Path(p).read_text(encoding="utf-8") for p in self.paths]

    def test_fmt_formats_every_file(self):
        result = _fmt(*self.paths)
        self.assertEqual(result.returncode, 0, result.stderr)
        for path, text in zip(self.paths, self._contents()):
            self.assertNotEqual(text, _UNFORMATTED, f"{path} was not formatted")
        self.assertEqual(_fmt("--check", *self.paths).returncode, 0)

    def test_check_reports_every_unformatted_file(self):
        result = _fmt("--check", *self.paths)
        self.assertEqual(result.returncode, 1)
        for path in self.paths:
            self.assertIn(os.path.basename(path), result.stderr)
        self.assertEqual(self._contents(), [_UNFORMATTED] * 3, "--check wrote a file")

    def test_one_failure_does_not_stop_the_rest_and_is_reported(self):
        missing = os.path.join(self._dir.name, "missing.nd")
        result = _fmt(self.paths[0], missing, self.paths[2])
        self.assertEqual(result.returncode, 1, "a failed path must fail the command")
        self.assertIn("missing.nd", result.stderr)
        contents = self._contents()
        self.assertNotEqual(contents[0], _UNFORMATTED)
        self.assertNotEqual(contents[2], _UNFORMATTED, "a path after the failure was skipped")
        self.assertEqual(contents[1], _UNFORMATTED, "a path not named was touched")


if __name__ == "__main__":
    unittest.main()
