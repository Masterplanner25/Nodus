"""#922: `nodus check --staged` finds rebuild effects from source.

The `rebuild-effect` flip (#917) is the 6.0.0 refusal of a top-level effect that
a rebuild would run again. Its runtime warning fires only when a stored run is
actually resumed. This is the static half, so a project can learn its exposure
before then.

It looks where a rebuild runs code: a file that can be rebuilt (it calls
`run_workflow`, `run_goal` or `durable_spawn`, or declares a workflow or goal),
its statements outside function bodies, and the bodies of same-file functions
those call -- except `main`, which a rebuild skips (#909). It reports builtins by
the runtime's own rule (`is_rebuild_effect`), stdlib wrappers by what their
source calls, and `extern`-declared host functions. A host function called with
no `extern` is visible only when it runs, so a run's report is merged in.

The static and runtime answers are the same question asked twice, so one test
holds them to the same positions. That test found the runtime warning pointing
into `std:fs`'s own source for a top-level `fs.write`.
"""

import json
import os
import sys
import tempfile
import textwrap
import unittest
import warnings
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))  # noqa: E402

from nodus.runtime.embedding import NodusRuntime  # noqa: E402
from nodus.tooling.staged_readiness import _stdlib_effects, scan  # noqa: E402

_APP = textwrap.dedent("""\
    import "std:fs" as fs
    extern record_visit()

    let cfg = read_file("cfg.txt")
    write_file("out.txt", "again")
    fs.write("log.txt", "again")
    record_visit()

    fn prepare() {
        write_file("prep.txt", "x")
        return 1i
    }
    let p = prepare()

    fn job() { checkpoint "half"; return 1i }
    spawn(fn() { write_file("spawned.txt", "x") })

    fn main() {
        write_file("main.txt", "x")
        durable_spawn("k", job, [])
        run_loop()
    }
    main()
    """)

# Lines 5, 6, 7: a builtin, a stdlib wrapper, a declared host function. Line 10:
# a builtin inside `prepare`, which the top level calls. Not line 4 (a read),
# 16 (a closure handed to spawn) or 19 (inside main).
_EXPECTED = [(5, 1), (6, 1), (7, 1), (10, 5)]


def _findings(sources, **kwargs):
    report = scan(sources=sources, **kwargs)
    (flip,) = [f for f in report.flips if f.name == "rebuild-effect"]
    return flip


class TheSourceScanTests(unittest.TestCase):

    # closes: #922
    def test_it_finds_each_top_level_effect_and_nothing_else(self):
        flip = _findings([("app.nd", _APP)], dynamic_report="")
        self.assertTrue(flip.checked)
        self.assertEqual(_EXPECTED, [(f.line, f.col) for f in flip.findings])
        messages = [f.message for f in flip.findings]
        self.assertIn("call to `write_file`", messages[0])
        self.assertIn("`fs.write` (`write_file`)", messages[1])
        self.assertIn("host function `record_visit`", messages[2])
        self.assertIn("rebuild_safe=True", messages[2])
        self.assertIn("in `prepare`, called at top level", messages[3])
        for message in messages:
            self.assertIn("refused at 6.0.0", message)

    def test_a_file_that_cannot_be_rebuilt_is_not_flagged(self):
        """A plain script is never rebuilt, so its top-level write is its own
        business. Without this rule every script that prints would be noise."""
        source = 'write_file("plain.txt", "x")\nprint("a plain script")\n'
        self.assertEqual([], _findings([("plain.nd", source)], dynamic_report="").findings)

    def test_a_stdlib_wrapper_is_classified_by_what_its_source_calls(self):
        effects = _stdlib_effects("fs")
        self.assertEqual("write_file", effects.get("write"))
        self.assertEqual("fs_delete", effects.get("delete"))
        self.assertNotIn("read", effects)


class TheStaticAndRuntimeAnswersAgreeTests(unittest.TestCase):

    def test_both_name_the_same_positions(self):
        """The runtime warning and the source scan answer one question. If they
        disagree, one of them is wrong, whichever looks right."""
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "cfg.txt").write_text("cfg", encoding="utf-8")
            app = Path(tmp, "app.nd")
            app.write_text(_APP, encoding="utf-8")
            rt = NodusRuntime(timeout_ms=None, max_steps=None,
                              allowed_paths=[tmp], project_root=tmp)
            rt.register_function("record_visit", lambda: None)
            vm = rt.new_vm()
            cwd = os.getcwd()
            os.chdir(tmp)
            try:
                with warnings.catch_warnings(record=True) as caught:
                    warnings.simplefilter("always")
                    vm.reexecute_source_for_resume(_APP, str(app), what="test")
            finally:
                os.chdir(cwd)
        runtime = []
        for w in caught:
            message = str(w.message)
            if message.startswith("a rebuild re-ran"):
                where = message[message.index(" at ") + 4:message.index(", which")]
                line, col = where.rsplit(":", 2)[-2:]
                runtime.append((int(line), int(col)))
                self.assertIn("app.nd", where, "a warning pointed outside the program")
        self.assertEqual(_EXPECTED, runtime)

    def test_the_runtime_warning_for_a_wrapper_names_the_users_line(self):
        """The regression the agreement test found: `fs.write` at top level was
        reported at `std:fs`'s own source line."""
        with tempfile.TemporaryDirectory() as tmp:
            vm = NodusRuntime(timeout_ms=None, max_steps=None, allowed_paths=[tmp]).new_vm()
            target = json.dumps(str(Path(tmp, "x.txt")))
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                vm.reexecute_source_for_resume(
                    f'import "std:fs" as fs\nfs.write({target}, "x")\n', None, what="test")
        (message,) = [str(w.message) for w in caught if str(w.message).startswith("a rebuild")]
        self.assertIn("<memory>:2:1", message)
        self.assertNotIn("stdlib", message)


class ARunsReportAddsWhatSourceCannotSeeTests(unittest.TestCase):

    def test_an_undeclared_host_function_is_added_from_a_run(self):
        """No `extern`, so the scan cannot tell `log_visit` from a typo. The
        rebuild's warning can, and its report is merged into the same flip."""
        source = "log_visit()\nfn job() { return 1i }\ndurable_spawn(\"k\", job, [])\n"
        self.assertEqual([], _findings([("app.nd", source)], dynamic_report="").findings)
        with tempfile.TemporaryDirectory() as tmp:
            report_file = str(Path(tmp, "flips.json"))
            previous = os.environ.get("NODUS_STAGED_FLIP_REPORT")
            os.environ["NODUS_STAGED_FLIP_REPORT"] = report_file
            try:
                rt = NodusRuntime(timeout_ms=None, max_steps=None)
                rt.register_function("log_visit", lambda: None)
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    rt.new_vm().reexecute_source_for_resume(source, None, what="test")
            finally:
                if previous is None:
                    os.environ.pop("NODUS_STAGED_FLIP_REPORT", None)
                else:
                    os.environ["NODUS_STAGED_FLIP_REPORT"] = previous
            flip = _findings([("app.nd", source)], dynamic_report=report_file)
        self.assertEqual(1, flip.observed)
        self.assertEqual(1, len(flip.findings))
        self.assertIn("host function `log_visit`", flip.findings[0].message)


if __name__ == "__main__":
    unittest.main()
