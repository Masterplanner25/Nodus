"""Accumulating what a run hits, for a flip nothing static can find (R2).

It was built for record equality (#545), which needed the runtime type of both
`==` operands, so its only answer was to run something and collect what the
warning said — and a warning is a transient stderr line, so a full test run
told you nothing you did not read as it scrolled past. #545 landed in 6.0.0;
the mechanism stays for the next flip like it, and the tests that need such a
flip use a synthetic register.

`NODUS_STAGED_FLIP_REPORT=<path>` makes every staged-flip site append a JSON
Lines record. Re-running `check --staged` then reports a flip with no scan as
**checked, by a run** rather than as unchecked.

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

#: A workflow that runs and stores a run. It used to be a lost update too, the
#: concurrent-write flip's warning; that landed in 6.0.0 (#547) as a refusal,
#: so the cell declares last-write-wins. `LOST_UPDATE` is the undeclared form.
RACE = """workflow race {
    state total = 0i with { merge: "any" }

    step a {
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
    def test_record_equality_records_nothing(self):
        """record-equality was the flip this report existed for. It landed in
        6.0.0 (#545): `==` is structural, so there is no divergence to record."""
        self.write("eq.nd", RECORDS)
        result = self.run_nodus("run", "eq.nd", "--time-limit", "20", report=self.report)
        self.assertIn("equal: true", result.stdout)
        self.assertNotIn("record-equality", self.flips_in_report())

    def test_a_landed_flip_records_nothing(self):
        """concurrent-write (#547) and worker-dispatcher (#798) were recorded
        here. Both landed in 6.0.0 as refusals, so there is no warning left to
        record -- and a run that is refused must not leave a stale entry."""
        self.write("race.nd", RACE.replace(' with { merge: "any" }', "")
                   .replace("step a {", 'step a with { worker: "remote" } {'))
        self.run_nodus("run", "race.nd", "--time-limit", "20", report=self.report)
        found = self.flips_in_report()
        self.assertNotIn("concurrent-write", found)
        self.assertNotIn("worker-dispatcher", found)

    def test_an_unknown_type_name_records_nothing(self):
        """unknown-type-name was recorded here; it landed in 6.0.0 (#609) as a
        syntax error, so a run of this file stops before anything records."""
        self.write("bad.nd", BAD_TYPE)
        self.run_nodus("run", "bad.nd", "--time-limit", "20", report=self.report)
        self.assertNotIn("unknown-type-name", self.flips_in_report())

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
        # The first run leaves a stored run; the default-store notice needs one.
        self.run_nodus("run", "race.nd", "--time-limit", "20")
        with_report = self.run_nodus(
            "run", "race.nd", "--time-limit", "20", report=self.report
        )
        self.assertIn("default workflow store", with_report.stderr)
        self.assertIn("default-store-sqlite", self.flips_in_report())

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
            command = [PYTHON, "-m", "nodus", "run", "race.nd", "--time-limit", "20"]
            # Seed a stored run, identically in both directories, so the
            # second run emits the default-store notice.
            subprocess.run(command, cwd=work, capture_output=True, text=True,
                           env=env, timeout=120)
            if name == "with-report":
                env[REPORT_ENV] = self.report
            outputs.append(subprocess.run(
                command, cwd=work, capture_output=True, text=True, env=env, timeout=120,
            ))
        without, with_report = outputs
        self.assertIn("default workflow store", without.stderr, "setup: the warning must fire")
        self.assertEqual(without.stderr, with_report.stderr)
        self.assertEqual(without.returncode, with_report.returncode)
        self.assertTrue(os.path.exists(self.report), "setup: the report must be written")


class CheckStagedMergesTests(_Env):
    """The two halves join: a run's findings upgrade what source cannot reach.

    No staged flip is out of reach of a scan since record-equality (#545)
    landed, so these use a synthetic register: the next flip with no static
    check takes this path, and it must still work when it arrives.
    """

    def _register(self) -> Path:
        register = Path(self.dir) / "staged_flips.json"
        register.write_text(json.dumps({
            "target": "7.0.0",
            "flips": {"no-scan-yet": {"issue": 1, "summary": "s"}},
        }), encoding="utf-8")
        return register

    # closes: #802
    def test_a_flip_with_no_scan_is_unchecked_with_no_report(self):
        from nodus.tooling.staged_readiness import scan

        report = scan(sources=[("a.nd", "fn main() {}")],
                      register_path=self._register(), dynamic_report=self.report)
        entry = report.flips[0]
        self.assertFalse(entry.checked)
        self.assertEqual(entry.observed, 0)

    # closes: #802
    def test_a_run_upgrades_it_to_checked(self):
        from nodus.tooling.staged_readiness import scan

        os.environ[REPORT_ENV] = self.report
        record_staged_flip("no-scan-yet", "seen at run time", where="a.nd:1:1")
        report = scan(sources=[("a.nd", "fn main() {}")],
                      register_path=self._register(), dynamic_report=self.report)
        entry = report.flips[0]
        self.assertTrue(entry.checked)
        self.assertEqual(entry.observed, 1)
        self.assertEqual([f.where for f in entry.findings], ["a.nd:1:1"])

    def test_no_hint_when_every_flip_is_checked_from_source(self):
        """The real register has no unchecked flip, so the CLI must not tell
        the user to collect a run report that would add nothing."""
        self.write("eq.nd", RECORDS)
        result = self.run_nodus("check", "eq.nd", "--staged")
        self.assertNotIn("[not checked]", result.stdout)
        self.assertNotIn("record-equality", result.stdout)
        self.assertNotIn("could not be checked from source", result.stdout)
        self.assertNotIn("run your program or tests with", result.stdout)


if __name__ == "__main__":
    unittest.main()
