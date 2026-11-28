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

    def test_the_default_store_records_nothing(self):
        """default-store-sqlite was recorded here, from a notice the runner
        printed. It landed in 6.0.0 (#797) as a refusal, so no notice is left."""
        self.write("race.nd", RACE)
        self.run_nodus("run", "race.nd", "--time-limit", "20")
        self.run_nodus("run", "race.nd", "--time-limit", "20", report=self.report)
        self.assertNotIn("default-store-sqlite", self.flips_in_report())

    def test_a_clean_program_records_nothing(self):
        self.write("clean.nd", 'fn main() {\n    print("ok")\n}\n')
        self.run_nodus("run", "clean.nd", "--time-limit", "20", report=self.report)
        self.assertEqual(read_staged_flip_report(self.report), [])

    def test_no_site_in_src_records_or_warns(self):
        """Every 6.0.0 flip has landed, so nothing calls the recorder or the
        warning. The next major's first staged flip changes this deliberately."""
        src = REPO / "src"
        callers = []
        for path in src.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for name in ("record_staged_flip(", "warn_staged_flip("):
                for line in text.splitlines():
                    if name in line and not line.lstrip().startswith("def "):
                        callers.append(f"{path.relative_to(REPO)}: {line.strip()}")
        self.assertEqual(callers, [])


class EmissionIsUnchangedTests(_Env):
    """The recorder records. It must not have become the emitter.

    A staged-flip site announces itself (`warn_staged_flip`, or its own stderr
    line) and records alongside. If recording took over emission, every
    consumer of that stderr would change at once. No site is live since the
    6.0.0 cohort landed, so this drives the two functions directly.
    """

    def test_recording_does_not_emit(self):
        import warnings as _warnings

        os.environ[REPORT_ENV] = self.report
        with _warnings.catch_warnings(record=True) as caught:
            _warnings.simplefilter("always")
            record_staged_flip("next-flip", "recorded")
        self.assertEqual([], [str(w.message) for w in caught])
        self.assertEqual(self.flips_in_report(), {"next-flip"})

    def test_warning_is_the_same_with_and_without_a_report(self):
        import warnings as _warnings

        from nodus.support.staging import StagedFlipWarning, warn_staged_flip

        seen = []
        for configured in (False, True):
            if configured:
                os.environ[REPORT_ENV] = self.report
            else:
                os.environ.pop(REPORT_ENV, None)
            with _warnings.catch_warnings(record=True) as caught:
                _warnings.simplefilter("always")
                warn_staged_flip("this changes at the next major")
            seen.append([(w.category, str(w.message)) for w in caught])
        self.assertEqual(seen[0], seen[1])
        self.assertEqual(seen[0], [(StagedFlipWarning, "this changes at the next major")])
        self.assertFalse(os.path.exists(self.report), "warning must not record")


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
