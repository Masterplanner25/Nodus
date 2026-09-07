"""Accumulating what a run hits, for the flip nothing static can find (R2).

`nodus check --staged` answers four of the five staged flips from source. Record
equality (#545) needs the runtime type of both `==` operands, so its only
answer is to run something and collect what the warning says — and a warning is
a transient stderr line, so a full test run told you nothing you did not read as
it scrolled past.

`NODUS_STAGED_FLIP_REPORT=<path>` makes every staged-flip site append a JSON
Lines record. Re-running `check --staged` then reports #545 as **checked, by a
run** rather than as unchecked.

Two properties are load-bearing:

- **The recorder does not emit.** Each site keeps announcing itself exactly as
  it did — some through `warn_staged_flip`, two by printing to stderr where an
  embedder reads them out of `result["stderr"]`. Routing emission through the
  recorder as well would have changed all of that at once, and the warning text
  is asserted on elsewhere. `EmissionIsUnchangedTests` pins that.
- **Recording is off unless asked for**, and cannot fail the program it is
  reporting on.
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

from nodus.support.staging import (  # noqa: E402
    REPORT_ENV,
    read_staged_flip_report,
    record_staged_flip,
)

REPO = Path(__file__).resolve().parents[1]
PYTHON = sys.executable

RECORDS = """fn main() {
    let a = record {x: 1i}
    let b = record {x: 1i}
    print("equal: \\(a == b)")
}
"""

RACE = """workflow race {
    state total = 0i

    step a with { worker: "remote" } {
        total = 1i
        return "a"
    }
    step b {
        total = 2i
        return "b"
    }
}

fn main() {
    let r = run_workflow(race)
    print("done")
}
"""

BAD_TYPE = """fn f(a: itn) {
    return a
}

fn main() {
    print("ok")
}
"""


class _Env(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name
        self.addCleanup(self._tmp.cleanup)
        self.report = os.path.join(self.dir, "staged.jsonl")
        self._previous = os.environ.pop(REPORT_ENV, None)
        if self._previous is not None:
            self.addCleanup(os.environ.__setitem__, REPORT_ENV, self._previous)
        self.addCleanup(os.environ.pop, REPORT_ENV, None)

    def write(self, name: str, text: str) -> str:
        path = os.path.join(self.dir, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return path

    def run_nodus(self, *args: str, report: str | None = None):
        env = dict(os.environ)
        env["PYTHONPATH"] = str(REPO / "src")
        env.pop("NODUS_WORKFLOW_STORE_BACKEND", None)
        if report is None:
            env.pop(REPORT_ENV, None)
        else:
            env[REPORT_ENV] = report
        return subprocess.run(
            [PYTHON, "-m", "nodus", *args],
            cwd=self.dir, capture_output=True, text=True, env=env, timeout=120,
        )

    def flips_in_report(self) -> set:
        return {r["flip"] for r in read_staged_flip_report(self.report)}


class RecorderTests(_Env):
    def test_nothing_is_written_when_no_report_was_asked_for(self):
        """Nothing *anywhere*, not merely nothing at the path we named.

        Asserting `not exists(self.report)` was too weak: a recorder that fell
        back to a default filename in the CWD passed it. The neuter matrix
        caught that -- making `report_path()` return a default left this green.
        So this runs from an empty directory and asserts it stays empty.
        """
        work = os.path.join(self.dir, "empty")
        os.makedirs(work)
        previous = os.getcwd()
        os.chdir(work)
        try:
            record_staged_flip("record-equality", "should not be recorded")
        finally:
            os.chdir(previous)
        self.assertEqual(os.listdir(work), [], "something was written unasked")
        self.assertFalse(os.path.exists(self.report))

    def test_records_append_as_json_lines(self):
        os.environ[REPORT_ENV] = self.report
        record_staged_flip("record-equality", "first")
        record_staged_flip("concurrent-write", "second", where="a.nd:1:1")
        records = read_staged_flip_report(self.report)
        self.assertEqual([r["flip"] for r in records],
                         ["record-equality", "concurrent-write"])
        self.assertEqual(records[1]["where"], "a.nd:1:1")
        with open(self.report, encoding="utf-8") as handle:
            for line in handle:
                json.loads(line)

    def test_a_malformed_line_is_skipped_not_fatal(self):
        """A process killed mid-append must not cost you the rest."""
        os.environ[REPORT_ENV] = self.report
        record_staged_flip("record-equality", "good")
        with open(self.report, "a", encoding="utf-8") as handle:
            handle.write('{"flip": "half-writ\n')
        record_staged_flip("concurrent-write", "also good")
        self.assertEqual(self.flips_in_report(), {"record-equality", "concurrent-write"})

    def test_an_unwritable_path_does_not_raise(self):
        """Reporting must never fail the program being reported on."""
        os.environ[REPORT_ENV] = os.path.join(self.dir, "nope.jsonl", "deeper.jsonl")
        record_staged_flip("record-equality", "swallowed")

    def test_reading_a_report_that_does_not_exist_is_empty(self):
        self.assertEqual(read_staged_flip_report(self.report), [])


class SitesRecordTests(_Env):
    """Every flip that can announce itself at run time does."""

    # closes: #802
    def test_record_equality_is_recorded(self):
        self.write("eq.nd", RECORDS)
        self.run_nodus("run", "eq.nd", "--time-limit", "20", report=self.report)
        self.assertIn("record-equality", self.flips_in_report())

    def test_concurrent_write_and_worker_are_recorded(self):
        self.write("race.nd", RACE)
        self.run_nodus("run", "race.nd", "--time-limit", "20", report=self.report)
        found = self.flips_in_report()
        self.assertIn("concurrent-write", found)
        self.assertIn("worker-dispatcher", found)

    def test_unknown_type_name_is_recorded(self):
        self.write("bad.nd", BAD_TYPE)
        self.run_nodus("run", "bad.nd", "--time-limit", "20", report=self.report)
        self.assertIn("unknown-type-name", self.flips_in_report())

    def test_the_default_store_notice_is_recorded(self):
        self.write("race.nd", RACE)
        # First run creates the records; the notice fires once there is state.
        self.run_nodus("run", "race.nd", "--time-limit", "20")
        self.run_nodus("run", "race.nd", "--time-limit", "20", report=self.report)
        self.assertIn("default-store-sqlite", self.flips_in_report())

    def test_a_clean_program_records_nothing(self):
        self.write("clean.nd", 'fn main() {\n    print("ok")\n}\n')
        self.run_nodus("run", "clean.nd", "--time-limit", "20", report=self.report)
        self.assertEqual(read_staged_flip_report(self.report), [])


class EmissionIsUnchangedTests(_Env):
    """The recorder records. It must not have become the emitter.

    Two of these warnings reach an embedder through `result["stderr"]`, and the
    text is asserted on in other suites. Recording alongside is the whole design
    -- if these go quiet, the recorder took over emission and every consumer of
    that stderr changed at once.
    """

    def test_the_warnings_still_print_with_a_report_configured(self):
        self.write("race.nd", RACE)
        with_report = self.run_nodus(
            "run", "race.nd", "--time-limit", "20", report=self.report
        )
        self.assertIn("both wrote state", with_report.stderr)
        self.assertIn("no worker dispatcher is registered", with_report.stderr)

    def test_the_warnings_are_identical_with_and_without_a_report(self):
        """Each run gets its own directory, or the comparison is not one.

        Run twice in one directory and the second additionally emits the
        default-store notice, because the first run left records behind. That
        difference is accumulated state, not the report -- and it made this
        test fail for a reason that had nothing to do with what it asserts.
        """
        outputs = []
        for name in ("no-report", "with-report"):
            work = os.path.join(self.dir, name)
            os.makedirs(work)
            with open(os.path.join(work, "race.nd"), "w", encoding="utf-8") as handle:
                handle.write(RACE)
            env = dict(os.environ)
            env["PYTHONPATH"] = str(REPO / "src")
            env.pop("NODUS_WORKFLOW_STORE_BACKEND", None)
            env.pop(REPORT_ENV, None)
            if name == "with-report":
                env[REPORT_ENV] = self.report
            outputs.append(subprocess.run(
                [PYTHON, "-m", "nodus", "run", "race.nd", "--time-limit", "20"],
                cwd=work, capture_output=True, text=True, env=env, timeout=120,
            ))
        without, with_report = outputs
        self.assertIn("both wrote state", without.stderr, "setup: the warning must fire")
        self.assertEqual(without.stderr, with_report.stderr)
        self.assertEqual(without.returncode, with_report.returncode)
        self.assertTrue(os.path.exists(self.report), "setup: the report must be written")


class CheckStagedMergesTests(_Env):
    """The two halves join: a run's findings upgrade what source cannot reach."""

    # closes: #802
    def test_record_equality_is_unchecked_with_no_report(self):
        self.write("eq.nd", RECORDS)
        result = self.run_nodus("check", "eq.nd", "--staged")
        self.assertIn("[not checked] record-equality", result.stdout)
        self.assertIn("could not be checked from source", result.stdout)
        self.assertIn("NODUS_STAGED_FLIP_REPORT", result.stdout)

    # closes: #802
    def test_a_run_upgrades_it_to_checked(self):
        self.write("eq.nd", RECORDS)
        self.run_nodus("run", "eq.nd", "--time-limit", "20", report=self.report)
        result = self.run_nodus("check", "eq.nd", "--staged", report=self.report)
        self.assertIn("record-equality", result.stdout)
        self.assertIn("[from a run]", result.stdout)
        self.assertNotIn("[not checked] record-equality", result.stdout)
        self.assertNotIn("could not be checked from source", result.stdout)

    def test_the_hint_is_not_printed_once_a_report_exists(self):
        self.write("eq.nd", RECORDS)
        self.run_nodus("run", "eq.nd", "--time-limit", "20", report=self.report)
        result = self.run_nodus("check", "eq.nd", "--staged", report=self.report)
        self.assertNotIn(
            "run your program or tests with", result.stdout,
            "still telling the user to do the thing they have done",
        )


if __name__ == "__main__":
    unittest.main()
