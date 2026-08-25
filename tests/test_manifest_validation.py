"""A manifest declaration either binds or is refused (#490).

`nodus.toml` accepted any table and any key and read four of them. The rest were
neither honoured nor reported -- the "declared but not enforced" shape recorded
in `CORPUS_SYNTHESIS.md` §6, in the place it is least visible: a manifest looks
like configuration that worked.

The two halves are tested together because they are one decision. Refusing
`[project]` is only reasonable if `entry` -- the key those manifests actually
wanted -- does something.
"""

import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus.tooling.project import (  # noqa: E402
    MANIFEST_SECTIONS,
    PACKAGE_KEYS,
    ManifestError,
    load_project,
    project_entry_path,
    validate_manifest,
    write_project_manifest,
)
from nodus.tooling.package_manager import add_dependency  # noqa: E402


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class ManifestValidationTests(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.root = self._dir.name
        self.addCleanup(self._dir.cleanup)

    def write(self, text: str) -> None:
        path = os.path.join(self.root, "nodus.toml")
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)

    # closes: #490
    def test_unknown_table_is_refused_and_named(self):
        """The manifest that motivated this, verbatim.

        Every table in it was ignored. `[project]` is one character from
        `[package]`, which is why nobody re-read it.
        """
        self.write(
            '[project]\n'
            'name = "claw"\n'
            'entry = "workflows/bootstrap.nd"\n'
            '\n[runtime]\n'
            'log_level = "info"\n'
            '\n[workflows]\n'
            'dir = "workflows"\n'
        )
        with self.assertRaises(ManifestError) as caught:
            load_project(self.root)
        message = str(caught.exception)
        for table in ("[project]", "[runtime]", "[workflows]"):
            self.assertIn(table, message)
        self.assertIn("did you mean [package]?", message)

    def test_unknown_package_key_is_refused(self):
        self.write('[package]\nname = "x"\nverison = "0.1.0"\n')
        with self.assertRaises(ManifestError) as caught:
            load_project(self.root)
        self.assertIn("'verison'", str(caught.exception))
        self.assertIn("did you mean 'version'?", str(caught.exception))

    def test_a_far_off_name_gets_no_invented_suggestion(self):
        """A hint that is always produced is a hint nobody trusts."""
        self.write('[package]\nname = "x"\n\n[quxzzy]\na = 1\n')
        with self.assertRaises(ManifestError) as caught:
            load_project(self.root)
        self.assertNotIn("did you mean", str(caught.exception))

    def test_known_manifest_still_loads(self):
        self.write(
            '[package]\nname = "x"\nversion = "2.0.0"\n\n[dependencies]\n'
        )
        project = load_project(self.root)
        self.assertEqual(project.name, "x")
        self.assertEqual(project.version, "2.0.0")

    def test_legacy_top_level_form_still_loads(self):
        """Pre-`[package]` manifests are a real form, not a typo."""
        self.write('name = "old"\nversion = "0.2.0"\n\n[dependencies]\n')
        project = load_project(self.root)
        self.assertEqual((project.name, project.version), ("old", "0.2.0"))

    def test_every_documented_section_and_key_is_accepted(self):
        """The refusal is driven by the same tuples the message quotes.

        Asserting on the constants rather than a hand-written list is what keeps
        a newly-supported key from being refused by a stale test -- and a newly
        refused one from passing because the test never knew about it.
        """
        others = "\n".join(
            f"[{name}]" for name in MANIFEST_SECTIONS if name != "package"
        )
        package_body = "\n".join(f'{key} = "v"' for key in PACKAGE_KEYS)
        self.write(f"[package]\n{package_body}\n\n{others}\n")
        validate_manifest(load_toml(os.path.join(self.root, "nodus.toml")))


class EntryPointTests(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.root = self._dir.name
        self.addCleanup(self._dir.cleanup)

    def write(self, text: str) -> None:
        with open(os.path.join(self.root, "nodus.toml"), "w",
                  encoding="utf-8", newline="\n") as handle:
            handle.write(text)

    # closes: #490
    def test_declared_entry_is_what_runs(self):
        os.makedirs(os.path.join(self.root, "workflows"))
        self.write('[package]\nname = "claw"\nentry = "workflows/bootstrap.nd"\n')
        entry = project_entry_path(load_project(self.root))
        self.assertEqual(
            os.path.normcase(entry),
            os.path.normcase(os.path.join(self.root, "workflows", "bootstrap.nd")),
        )

    def test_absent_entry_falls_back_to_the_convention(self):
        self.write('[package]\nname = "claw"\n')
        entry = project_entry_path(load_project(self.root))
        self.assertEqual(
            os.path.normcase(entry),
            os.path.normcase(os.path.join(self.root, "src", "main.nd")),
        )

    def test_entry_may_not_escape_the_project_root(self):
        self.write('[package]\nname = "claw"\nentry = "../../elsewhere.nd"\n')
        with self.assertRaises(ManifestError) as caught:
            project_entry_path(load_project(self.root))
        self.assertIn("outside the project root", str(caught.exception))

    def test_entry_survives_a_manifest_rewrite(self):
        """`nodus add` rewrites the manifest from parsed values.

        Anything the writer does not know about is dropped -- which is how
        `registry_url` was being deleted by `nodus add` before this.
        """
        os.makedirs(os.path.join(self.root, ".nodus"), exist_ok=True)
        write_project_manifest(
            os.path.join(self.root, "nodus.toml"),
            name="claw",
            version="0.1.0",
            dependencies={},
            registry_url="https://example.invalid",
            entry="workflows/bootstrap.nd",
        )
        project = load_project(self.root)
        self.assertEqual(project.entry, "workflows/bootstrap.nd")
        self.assertEqual(project.registry_url, "https://example.invalid")

        try:
            add_dependency(self.root, "definitely-not-a-real-package")
        except Exception:
            pass  # the add is expected to fail; the manifest must be intact
        after = load_project(self.root)
        self.assertEqual(after.entry, "workflows/bootstrap.nd")
        self.assertEqual(after.registry_url, "https://example.invalid")


class CliSurfaceTests(unittest.TestCase):
    """The boundary must hold through the CLI too, not only the API.

    `docs/governance/TECH_DEBT.md § Testing Methodology`: enforcement can differ
    between contexts, so a path-containment check gets both.
    """

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.root = self._dir.name
        self.addCleanup(self._dir.cleanup)

    def run_nodus(self, *args: str) -> subprocess.CompletedProcess:
        env = dict(os.environ)
        env["PYTHONPATH"] = os.path.join(REPO_ROOT, "src")
        return subprocess.run(
            [sys.executable, os.path.join(REPO_ROOT, "nodus.py"), *args],
            capture_output=True, cwd=self.root, env=env, timeout=120,
        )

    def write(self, text: str) -> None:
        with open(os.path.join(self.root, "nodus.toml"), "w",
                  encoding="utf-8", newline="\n") as handle:
            handle.write(text)

    def test_cli_run_reports_an_unreadable_manifest_rather_than_a_traceback(self):
        self.write('[project]\nname = "claw"\n')
        result = self.run_nodus("run")
        output = (result.stdout + result.stderr).decode("utf-8", "replace")
        self.assertNotIn("Traceback", output)
        self.assertIn("[project]", output)
        self.assertNotEqual(result.returncode, 0)

    def test_cli_run_honours_a_declared_entry(self):
        os.makedirs(os.path.join(self.root, "flows"))
        with open(os.path.join(self.root, "flows", "boot.nd"), "w",
                  encoding="utf-8", newline="\n") as handle:
            handle.write('print("ran the declared entry")\n')
        self.write('[package]\nname = "claw"\nentry = "flows/boot.nd"\n')
        result = self.run_nodus("run")
        output = (result.stdout + result.stderr).decode("utf-8", "replace")
        self.assertIn("ran the declared entry", output)

    def test_cli_run_refuses_an_entry_outside_the_root(self):
        self.write('[package]\nname = "claw"\nentry = "../escape.nd"\n')
        result = self.run_nodus("run")
        output = (result.stdout + result.stderr).decode("utf-8", "replace")
        self.assertNotIn("Traceback", output)
        self.assertIn("outside the project root", output)
        self.assertNotEqual(result.returncode, 0)


def load_toml(path: str) -> dict:
    import tomllib

    with open(path, "rb") as handle:
        return tomllib.load(handle)


if __name__ == "__main__":
    unittest.main()
