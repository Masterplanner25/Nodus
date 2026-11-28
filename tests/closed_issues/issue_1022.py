"""Closed-issue test for #1022: `nodus check --staged` scans what the entry imports.

The report has always said it checked "the entry file and what it imports".
It scanned the entry file alone, so a workflow race, a `worker:` declaration or
a top-level effect in an imported module was reported `[ok]`. It walks each
module's recorded import specs now, which a module loaded from the bytecode
cache still carries, so the answer does not depend on whether the cache is warm.
"""
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, "C:/dev/Coding Language/src")

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_FLOWS = (
    "workflow race {\n"
    "    state total = 0i\n"
    "    step a {\n"
    "        total = 1i\n"
    '        return "a"\n'
    "    }\n"
    "    step b {\n"
    "        total = 2i\n"
    '        return "b"\n'
    "    }\n"
    "}\n"
    "export fn noop(x: itn) {\n"
    "    return 1\n"
    "}\n"
)


def _write(directory, name, text):
    path = os.path.join(directory, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


class StagedScansImports(unittest.TestCase):

    # closes: #1022
    def test_findings_in_an_imported_file_are_reported_cold_and_warm(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "nodus.toml", '[project]\nname = "i1022"\n')
            _write(d, "flows.nd", _FLOWS)
            _write(d, "main.nd", 'import "./flows.nd" as flows\nprint("ok")\n')
            env = dict(os.environ, PYTHONPATH=os.path.join(_REPO, "src"),
                       NODUS_WORKFLOW_STORE_BACKEND="local")
            for run in (1, 2):
                proc = subprocess.run(
                    [sys.executable, "-m", "nodus", "check", "--staged", "main.nd"],
                    cwd=d, env=env, capture_output=True, text=True, timeout=120)
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                self.assertIn("and 1 file(s) it imports", proc.stdout, f"check {run}")
                self.assertIn("[ 1 found]   unknown-type-name (#609)", proc.stdout,
                              f"check {run}: {proc.stdout}")
                self.assertIn("flows.nd:12", proc.stdout)
                # The race is a landed flip since 6.0.0 (#547): plain `nodus
                # check` reports it, and it scans the imports the same way.
                plain = subprocess.run(
                    [sys.executable, "-m", "nodus", "check", "main.nd"],
                    cwd=d, env=env, capture_output=True, text=True, timeout=120)
                self.assertIn("flows.nd", plain.stderr, f"check {run}: {plain.stderr}")
                self.assertIn("both write state 'total'", plain.stderr)
                # Warm the bytecode cache for the second check.
                subprocess.run([sys.executable, "-m", "nodus", "run", "main.nd"],
                               cwd=d, env=env, capture_output=True, text=True, timeout=120)


if __name__ == "__main__":
    unittest.main()
