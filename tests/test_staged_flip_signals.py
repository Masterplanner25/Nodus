"""Staged-flip warnings reach the path a user actually runs (plan gate G2).

A warning about a future break is only a deprecation if someone sees it.
`COMPATIBILITY_MODEL.md` §5.1 makes "the CLI emits a warning" one of three
required signals, and two of the five staged flips did not have one:

- **#797** — the default-store notice was a plain `DeprecationWarning` raised
  outside `__main__`, which Python's default filters discard. No CLI user had
  ever seen it, for the whole of its deprecation window, on the one flip that
  costs *state* rather than a build.
- **#609** — unknown type names reached `nodus check` and the LSP only. At
  6.0.0 the command that starts *failing* is `nodus run`, so the command that
  said nothing was the one whose behaviour changes.

The cold/warm pairs below are not padding. The first version of #609's fix
warned on a cold compile and went silent on every run after, because the
bytecode cache is a third path to the same question — the fourth time that has
happened here (#521, #400, #394, and #348 for `--trace-imports`). A warning that
stops on the second run is worse than none: it looks fixed.
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
import tempfile
import unittest
import warnings
from contextlib import redirect_stderr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))  # noqa: E402

from nodus.support.staging import StagedFlipWarning, warn_staged_flip  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
PYTHON = sys.executable

BAD_ANNOTATION = 'fn f(a: itn) {\n    return a\n}\n\nfn main() {\n    print("ok")\n}\n'
CLEAN = 'fn main() {\n    print("ok")\n}\n'


def _run_nodus(cwd: str, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO / "src")
    return subprocess.run(
        [PYTHON, "-m", "nodus", *args],
        cwd=cwd, capture_output=True, text=True, env=env, timeout=120,
    )


class CategoryTests(unittest.TestCase):
    """The category is the handle the CLI filters on."""

    def test_it_is_a_deprecation_warning(self):
        """An embedder's existing `DeprecationWarning` filters must still catch it."""
        self.assertTrue(issubclass(StagedFlipWarning, DeprecationWarning))
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", DeprecationWarning)
            warn_staged_flip("something changes at the major")
        self.assertEqual(len(caught), 1)
        self.assertIs(caught[0].category, StagedFlipWarning)

    def test_an_embedder_can_turn_it_into_an_error(self):
        """The point of staying in the warnings machinery rather than printing."""
        with warnings.catch_warnings():
            warnings.simplefilter("error", StagedFlipWarning)
            with self.assertRaises(StagedFlipWarning):
                warn_staged_flip("boom")


class CliDisplayTests(unittest.TestCase):
    # closes: #797
    def test_the_cli_shows_a_staged_flip_warning(self):
        from nodus.cli.cli import _show_staged_flip_warnings

        with warnings.catch_warnings():
            warnings.resetwarnings()
            previous = warnings.showwarning
            try:
                _show_staged_flip_warnings()
                buffer = io.StringIO()
                with redirect_stderr(buffer):
                    warn_staged_flip("the default store changes")
                self.assertIn("warning: the default store changes", buffer.getvalue())
                self.assertNotIn("StagedFlipWarning", buffer.getvalue())
            finally:
                warnings.showwarning = previous

    def test_it_does_not_unsuppress_unrelated_deprecations(self):
        """Scoped to our category, or our notice drowns in other libraries'.

        The control matters here: raising a `DeprecationWarning` from a test
        body proves nothing, because `__main__`-attributed deprecations are
        shown by default anyway. This raises from a module.
        """
        from nodus.cli.cli import _show_staged_flip_warnings

        with warnings.catch_warnings():
            warnings.resetwarnings()
            previous = warnings.showwarning
            try:
                _show_staged_flip_warnings()
                buffer = io.StringIO()
                with redirect_stderr(buffer):
                    # Attributed to this module, not __main__, so the default
                    # filters genuinely suppress it.
                    warnings.warn("unrelated library", DeprecationWarning, stacklevel=1)
                self.assertEqual(buffer.getvalue().strip(), "")
            finally:
                warnings.showwarning = previous


class _ProjectCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name
        self.addCleanup(self._tmp.cleanup)

    def write(self, name: str, text: str) -> str:
        path = os.path.join(self.dir, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return path


class UnknownTypeNameOnRunTests(_ProjectCase):
    # closes: #609
    def test_run_reports_an_unknown_type_name(self):
        self.write("bad.nd", BAD_ANNOTATION)
        result = _run_nodus(self.dir, "run", "bad.nd", "--time-limit", "20")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Unknown type name 'itn'", result.stderr)
        self.assertIn("6.0.0", result.stderr)

    # closes: #609
    def test_it_still_reports_on_a_warm_bytecode_cache(self):
        """The cache is always one of the paths (#521, #400, #394, #348).

        The first version of this fix warned once and then never again, which
        looks exactly like a bug someone fixed.
        """
        self.write("bad.nd", BAD_ANNOTATION)
        counts = []
        for _ in range(3):
            result = _run_nodus(self.dir, "run", "bad.nd", "--time-limit", "20")
            counts.append(result.stderr.count("Unknown type name"))
        self.assertEqual(counts, [1, 1, 1], f"warm runs lost the warning: {counts}")

    def test_an_imported_module_is_covered_and_named(self):
        """Imports fail at the major on the same terms, so they warn too."""
        self.write("lib/helper.nd", 'export fn helper(v: flaot) {\n    return v\n}\n')
        self.write("main.nd", 'import "./lib/helper.nd" as lib\n\nfn main() {\n    print("\\(lib.helper(1i))")\n}\n')
        result = _run_nodus(self.dir, "run", "main.nd", "--time-limit", "20")
        self.assertIn("Unknown type name 'flaot'", result.stderr)
        self.assertIn("helper.nd", result.stderr, "named the entry file, not the import")

    def test_a_clean_program_says_nothing(self):
        """Cold and warm. A warning everyone sees is a warning nobody reads."""
        self.write("clean.nd", CLEAN)
        for _ in range(2):
            result = _run_nodus(self.dir, "run", "clean.nd", "--time-limit", "20")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn("Unknown type name", result.stderr)

    def test_check_still_reports_it_too(self):
        """`run` gaining the signal must not cost `check` its own."""
        self.write("bad.nd", BAD_ANNOTATION)
        result = _run_nodus(self.dir, "check", "bad.nd")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Unknown type name 'itn'", result.stderr)


class DefaultStoreNoticeTests(_ProjectCase):
    """#797: the notice a CLI user could not see."""

    WORKFLOW = (
        "workflow demo {\n"
        "    step a {\n"
        '        return "a"\n'
        "    }\n"
        "}\n"
        "\n"
        "fn main() {\n"
        "    let r = run_workflow(demo)\n"
        '    print("done")\n'
        "}\n"
    )

    # closes: #797
    def test_the_notice_reaches_a_plain_cli_run(self):
        self.write("wf.nd", self.WORKFLOW)
        # First run creates the records; the notice fires once there is state.
        _run_nodus(self.dir, "run", "wf.nd", "--time-limit", "20")
        result = _run_nodus(self.dir, "run", "wf.nd", "--time-limit", "20")
        self.assertIn("becomes SQLite at 6.0.0", result.stderr)
        self.assertIn("migrate-store", result.stderr, "a notice must say what to type")

    def test_a_project_with_no_runs_hears_nothing(self):
        """The narrowing has to survive being made visible."""
        self.write("clean.nd", CLEAN)
        result = _run_nodus(self.dir, "run", "clean.nd", "--time-limit", "20")
        self.assertNotIn("becomes SQLite", result.stderr)

    def test_choosing_the_local_backend_silences_it(self):
        """Saying `local` is an answer, not an oversight."""
        self.write("wf.nd", self.WORKFLOW)
        _run_nodus(self.dir, "run", "wf.nd", "--time-limit", "20")
        env = dict(os.environ)
        env["PYTHONPATH"] = str(REPO / "src")
        env["NODUS_WORKFLOW_STORE_BACKEND"] = "local"
        result = subprocess.run(
            [PYTHON, "-m", "nodus", "run", "wf.nd", "--time-limit", "20"],
            cwd=self.dir, capture_output=True, text=True, env=env, timeout=120,
        )
        self.assertNotIn("becomes SQLite", result.stderr)


if __name__ == "__main__":
    unittest.main()
