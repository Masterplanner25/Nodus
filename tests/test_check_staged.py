"""`nodus check --staged`: what breaks at the next major, found without running.

Gate G3 of `docs/governance/V6_0_PLAN.md`; design in
`docs/design/v6/01-readiness.md`.

Two properties carry most of the weight, and both are about honesty rather than
detection:

- **Every flip in the register appears in the report**, including the one
  nothing looked at. The report is built by walking the register, so a sixth
  flip added tomorrow shows as "not checked" rather than being silently absent.
- **A clean run never says "ready".** #545 cannot be answered from source, so
  green means "nothing found in what was checked". A bare "no issues" would be
  #797's failure again: a message that is careful, correct, and leaves someone
  believing something false.

The concurrent-write cases pin the thing that makes the static answer worth
having: it reports every pair that *could* race, where the runtime warning
reports the pair that *did* on one interleaving.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))  # noqa: E402

from nodus.tooling.staged_readiness import load_register, scan  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
PYTHON = sys.executable

RACE = """workflow race {
    state total = 0i
    state safe = 0i with { merge: "any" }

    step a with { worker: "remote" } {
        total = 1i
        safe = 1i
        return "a"
    }
    step b {
        total = 2i
        safe = 2i
        return "b"
    }
    step c after a {
        total = 3i
        return "c"
    }
}

fn helper(v: itn) {
    return v
}

fn main() {
    print("done")
}
"""

CLEAN = """workflow good {
    state total = 0i

    step a {
        total = 1i
        return "a"
    }
    step b after a {
        total = 2i
        return "b"
    }
}

fn main() {
    print("ok")
}
"""


def _findings(report, flip: str) -> list:
    for entry in report.flips:
        if entry.name == flip:
            return entry.findings
    raise AssertionError(f"{flip} is not in the report at all")


def _scan(code: str, **kwargs):
    return scan(sources=[("probe.nd", code)], **kwargs)


class RegisterCoverageTests(unittest.TestCase):
    """The report is a projection of the register, not a second list."""

    # closes: #802
    def test_every_registered_flip_appears(self):
        data, error = load_register()
        self.assertIsNone(error, error)
        report = _scan(CLEAN)
        self.assertEqual(
            sorted(f.name for f in report.flips),
            sorted(data["flips"]),
            "the report and the register name different flips",
        )

    def test_a_flip_with_no_static_check_is_reported_as_unchecked(self):
        report = _scan(CLEAN)
        unchecked = {f.name for f in report.unchecked}
        self.assertIn("record-equality", unchecked)
        entry = next(f for f in report.flips if f.name == "record-equality")
        self.assertTrue(entry.reason, "unchecked with no reason given")
        self.assertIn("runtime type", entry.reason)

    def test_an_unreadable_register_is_an_error_not_an_empty_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "staged_flips.json"
            bad.write_text("{not json", encoding="utf-8")
            report = _scan(CLEAN, register_path=bad)
        self.assertIsNotNone(report.error)
        self.assertEqual(report.flips, [])


class ConcurrentWriteTests(unittest.TestCase):
    """#547, and the reason the static answer beats the runtime one."""

    # closes: #802
    def test_unordered_co_writers_are_found(self):
        found = _findings(_scan(RACE), "concurrent-write")
        pairs = {(f.message.split("steps ")[1].split(" both")[0]) for f in found}
        self.assertIn("'a' and 'b'", pairs)

    def test_a_pair_the_runtime_would_miss_is_still_found(self):
        """`b` and `c` are unordered and both write `total`.

        The runtime warning reports whichever pair raced on the interleaving
        that happened; this reports every pair that could.
        """
        found = _findings(_scan(RACE), "concurrent-write")
        pairs = {(f.message.split("steps ")[1].split(" both")[0]) for f in found}
        self.assertIn("'b' and 'c'", pairs)

    def test_an_ordered_pair_is_not_reported(self):
        """`c after a` orders them, so it is not merely every pair."""
        found = _findings(_scan(RACE), "concurrent-write")
        pairs = {(f.message.split("steps ")[1].split(" both")[0]) for f in found}
        self.assertNotIn("'a' and 'c'", pairs)

    def test_a_declared_merge_policy_silences_the_cell(self):
        """`safe` is written by the same unordered pair and declared `any`.

        The control is the point: an earlier version of this fixture declared
        `safe` and had no step write it, so the assertion held for a reason
        that had nothing to do with the merge policy. The neuter matrix caught
        it -- emptying `_SILENCING_MERGES` left this test green.
        """
        found = _findings(_scan(RACE), "concurrent-write")
        self.assertTrue(
            [f for f in found if "'total'" in f.message],
            "the fixture is not exercising co-writers at all",
        )
        self.assertFalse(
            [f for f in found if "'safe'" in f.message],
            "a cell whose declaration states the intent was still reported",
        )

    def test_a_fully_ordered_workflow_is_clean(self):
        self.assertEqual(_findings(_scan(CLEAN), "concurrent-write"), [])


class WorkerAndTypeNameTests(unittest.TestCase):
    def test_a_worker_declaration_is_reported(self):
        found = _findings(_scan(RACE), "worker-dispatcher")
        self.assertEqual(len(found), 1)
        self.assertIn("worker 'remote'", found[0].message)

    def test_a_workflow_with_no_worker_is_clean(self):
        self.assertEqual(_findings(_scan(CLEAN), "worker-dispatcher"), [])

    def test_type_warnings_are_passed_through_not_recomputed(self):
        report = _scan(
            CLEAN,
            type_warnings=[{"message": "Unknown type name 'itn'", "line": 3, "column": 9}],
        )
        found = _findings(report, "unknown-type-name")
        self.assertEqual(len(found), 1)
        self.assertEqual((found[0].line, found[0].col), (3, 9))


class DefaultStoreTests(unittest.TestCase):
    """#174/#797 is a filesystem question, and keeps the runtime's narrowing."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self.addCleanup(self._tmp.cleanup)
        self._backend = os.environ.pop("NODUS_WORKFLOW_STORE_BACKEND", None)
        if self._backend is not None:
            self.addCleanup(
                os.environ.__setitem__, "NODUS_WORKFLOW_STORE_BACKEND", self._backend
            )

    def _with_runs(self, count: int) -> None:
        runs = Path(self.root) / ".nodus" / "workflow_framework" / "runs"
        runs.mkdir(parents=True, exist_ok=True)
        for i in range(count):
            (runs / f"g_{i}.json").write_text("{}", encoding="utf-8")

    def test_runs_in_the_json_store_are_reported(self):
        self._with_runs(3)
        found = _findings(_scan(CLEAN, project_root=self.root), "default-store-sqlite")
        self.assertEqual(len(found), 1)
        self.assertIn("3 run record(s)", found[0].message)
        self.assertIn("migrate-store", found[0].message)

    def test_a_project_with_no_runs_is_clean(self):
        found = _findings(_scan(CLEAN, project_root=self.root), "default-store-sqlite")
        self.assertEqual(found, [])

    def test_choosing_the_backend_silences_it(self):
        """Saying `local` is an answer, not an oversight -- the runtime's rule."""
        self._with_runs(3)
        os.environ["NODUS_WORKFLOW_STORE_BACKEND"] = "local"
        self.addCleanup(os.environ.pop, "NODUS_WORKFLOW_STORE_BACKEND", None)
        found = _findings(_scan(CLEAN, project_root=self.root), "default-store-sqlite")
        self.assertEqual(found, [])


class CliTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name
        self.addCleanup(self._tmp.cleanup)

    def _write(self, name: str, text: str) -> str:
        path = os.path.join(self.dir, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return path

    def _run(self, *args: str) -> subprocess.CompletedProcess:
        env = dict(os.environ)
        env["PYTHONPATH"] = str(REPO / "src")
        env.pop("NODUS_WORKFLOW_STORE_BACKEND", None)
        return subprocess.run(
            [PYTHON, "-m", "nodus", *args],
            cwd=self.dir, capture_output=True, text=True, env=env, timeout=120,
        )

    # closes: #802
    def test_a_clean_project_is_not_told_it_is_ready(self):
        """R4. The whole reason this wording is pinned."""
        self._write("ok.nd", CLEAN)
        result = self._run("check", "ok.nd", "--staged")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("nothing found in the", result.stdout)
        self.assertIn("could not be checked from source", result.stdout)
        self.assertNotIn("ready", result.stdout.lower())

    def test_findings_do_not_fail_the_command(self):
        """It reports what is coming; it is not a gate."""
        self._write("race.nd", RACE)
        result = self._run("check", "race.nd", "--staged")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("thing(s) to fix", result.stdout)

    def test_the_type_warning_is_not_printed_twice(self):
        self._write("race.nd", RACE)
        result = self._run("check", "race.nd", "--staged")
        combined = result.stdout + result.stderr
        self.assertEqual(combined.count("Unknown type name 'itn'"), 1)

    def test_plain_check_is_unchanged(self):
        self._write("race.nd", RACE)
        result = self._run("check", "race.nd")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("OK (1 warning(s))", result.stdout)
        self.assertNotIn("Staged for", result.stdout)

    def test_trace_flags_are_still_refused(self):
        """Refusing by name must not have widened to every valueless flag."""
        self._write("ok.nd", CLEAN)
        result = self._run("check", "ok.nd", "--trace")
        self.assertEqual(result.returncode, 2)
        self.assertIn("not supported", result.stderr)

    def test_staged_is_documented_in_help(self):
        result = self._run("check", "--help")
        self.assertIn("--staged", result.stdout)


class RegisterShipsTests(unittest.TestCase):
    # closes: #802
    def test_the_register_lives_in_the_package_and_is_declared_package_data(self):
        """One file: the gate checks it and the shipped command reads it.

        Two copies -- one under `tools/` to gate with, one in the package to
        ship -- would be exactly the drift `nodus_gate --flips` exists to catch.
        """
        register = REPO / "src" / "nodus" / "support" / "staged_flips.json"
        self.assertTrue(register.is_file(), "the register is not in the package")
        json.loads(register.read_text(encoding="utf-8"))
        pyproject = (REPO / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn(
            "support/staged_flips.json", pyproject,
            "the register is in the package but will not ship in the wheel",
        )
        self.assertFalse(
            (REPO / "tools" / "v6_flips.json").exists(),
            "the old copy is back; there must be exactly one register",
        )


if __name__ == "__main__":
    unittest.main()
