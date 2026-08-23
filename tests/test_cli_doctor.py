"""`nodus doctor` -- environment diagnostics.

The load-bearing test here is `test_doctor_does_not_write`: this is the command
someone runs when an install is already broken, so it must not create the
store, the cache, or anything else it reports on.
"""

from __future__ import annotations

import io
import contextlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))  # noqa: E402

from nodus.cli import doctor  # noqa: E402
from nodus.cli.cli import main  # noqa: E402


class ResolutionTests(unittest.TestCase):
    def test_package_dir_is_derived_from_a_submodule(self):
        """Not from `nodus.__file__`, which the repo-root shim can occupy."""
        package_dir = doctor._package_dir()
        self.assertEqual(package_dir.name, "nodus")
        self.assertTrue((package_dir / "support" / "version.py").is_file())

    def test_reports_the_bare_version_not_the_display_string(self):
        """`VERSION` is "Nodus 5.1.0"; comparing that to dist metadata never matches."""
        check = doctor._resolved_package()
        from nodus.support.version import __version__

        self.assertEqual(check.data["version"], __version__)
        self.assertNotIn("Nodus ", check.data["version"])

    def test_version_sync_compares_like_with_like(self):
        check = doctor._version_gap()
        self.assertIn(check.status, {doctor.OK, doctor.WARN, doctor.ERROR})
        if check.status == doctor.OK:
            self.assertEqual(check.data["module"], check.data["installed"])


class ReportTests(unittest.TestCase):
    def test_every_check_has_a_known_status(self):
        for check in doctor.run_checks():
            self.assertIn(check.status, {doctor.OK, doctor.WARN, doctor.ERROR})
            self.assertTrue(check.detail, f"{check.name} has no detail")

    def test_report_renders_every_check(self):
        checks = doctor.run_checks()
        report = doctor.format_report(checks)
        for check in checks:
            self.assertIn(check.name, report)

    def test_json_ok_is_false_only_when_something_failed(self):
        checks = [doctor.Check("a", doctor.OK, "fine"), doctor.Check("b", doctor.WARN, "eh")]
        self.assertTrue(doctor.to_json(checks)["ok"])
        checks.append(doctor.Check("c", doctor.ERROR, "broken"))
        self.assertFalse(doctor.to_json(checks)["ok"])

    def test_warnings_alone_do_not_fail_the_command(self):
        checks = [doctor.Check("a", doctor.WARN, "eh")]
        self.assertTrue(doctor.to_json(checks)["ok"])
        self.assertIn("No problems.", doctor.format_report(checks))


class CliTests(unittest.TestCase):
    def _run(self, argv: list[str]) -> tuple[int, str]:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = main(argv)
        return code, buf.getvalue()

    def test_doctor_runs_and_prints_a_report(self):
        code, out = self._run(["nodus", "doctor"])
        self.assertIn(code, (0, 1))
        self.assertIn("nodus package", out)
        self.assertIn("version sync", out)

    def test_json_output_parses(self):
        _code, out = self._run(["nodus", "doctor", "--json"])
        payload = json.loads(out)
        self.assertIn("ok", payload)
        self.assertTrue(payload["checks"])
        self.assertTrue(all("status" in c for c in payload["checks"]))

    def test_help_does_not_run_the_command(self):
        """#353: --help must never do work."""
        _code, out = self._run(["nodus", "doctor", "--help"])
        self.assertIn("doctor", out)
        self.assertNotIn("version sync", out)


class NoSideEffectsTests(unittest.TestCase):
    def test_doctor_does_not_write(self):
        """A diagnostic must not mutate the thing it is diagnosing.

        Runs against an empty directory and asserts nothing appears -- no
        `.nodus/`, no cache, no manifest.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            before = set(root.rglob("*"))
            checks = doctor.run_checks(cwd=root)
            doctor.format_report(checks)
            doctor.to_json(checks)
            after = set(root.rglob("*"))
        self.assertEqual(before, after, "doctor created something in a clean directory")

    def test_store_check_reports_absence_without_creating_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            check = doctor._store(root)
            self.assertEqual(check.status, doctor.OK)
            self.assertEqual(check.data["runs"], 0)
            self.assertFalse((root / ".nodus").exists())

    def test_store_check_counts_existing_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs = Path(tmp) / ".nodus" / "workflow_framework" / "runs"
            runs.mkdir(parents=True)
            for i in range(3):
                (runs / f"g_{i}.json").write_text("{}", encoding="utf-8")
            (runs / "not-a-run.txt").write_text("", encoding="utf-8")
            check = doctor._store(Path(tmp))
        self.assertEqual(check.data["runs"], 3)

    def test_project_check_reports_a_missing_entry_point(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            check = doctor._project(root)
            self.assertEqual(check.status, doctor.OK)
            self.assertIsNone(check.data["manifest"])


if __name__ == "__main__":
    unittest.main()
