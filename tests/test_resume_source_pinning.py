"""A resume replays the source the run was planned against, from every entry point.

`vm.source_code` is what `_rebuild_workflow_graph` recompiles to resume a run in
another process. It used to be set only by `tooling/runner.py` and
`dap/server.py`, so one `resume_workflow` call meant three different things:

    nodus run / nodus dap   ->  the pinned source; edits ignored
    NodusRuntime.run_file   ->  the current file; edits picked up
    NodusRuntime.run_source ->  nothing -- the run could not be resumed (#469)

All three are pinned now, and a resume says so when the file has moved on rather
than swallowing it.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus.runtime.embedding import NodusRuntime  # noqa: E402
from nodus.vm.vm import VM  # noqa: E402

WORKFLOW = """
workflow w {{
    state log = ""
    step a {{ print("a {marker}"); log = log + "a"; checkpoint "cp"; return 1i }}
    step b after a {{ log = log + "b"; return 2i }}
}}
fn main() {{
    let r = run_workflow(w)
    let g = r["graph_id"]
    print("GID=\\(g)")
}}
"""


def _gid(stdout: str) -> str:
    for line in (stdout or "").splitlines():
        if line.startswith("GID="):
            return line[4:].strip()
    raise AssertionError(f"no graph id in {stdout!r}")


class RebuildHandleIsAConstructorArgumentTests(unittest.TestCase):
    """Assert on the source, not the behaviour.

    A behaviour test passes on whichever entry point is already correct, which is
    how this survived: the CLI worked, so nothing caught that the embedding layer
    recorded no source. `source_path` was a `VM` parameter and `source_code` was
    assignable only afterwards, so an entry point could pass one and look
    complete. Keeping both as parameters is what makes a *new* entry point meet
    them together.
    """

    def test_vm_takes_both_halves_of_the_rebuild_handle(self):
        import inspect

        params = inspect.signature(VM.__init__).parameters
        self.assertIn("source_path", params)
        self.assertIn(
            "source_code",
            params,
            msg="source_code must stay a VM constructor parameter beside source_path; "
            "as a post-hoc attribute it is invisible at the construction site (#469)",
        )

    def test_constructor_value_reaches_the_attribute(self):
        vm = VM([], {}, code_locs=[], source_path="x.nd", source_code="workflow w {}")
        self.assertEqual(vm.source_code, "workflow w {}")


class EveryEntryPointRecordsItsSourceTests(unittest.TestCase):
    def test_run_source_run_is_resumable_in_a_fresh_runtime(self):
        """#469: `run_source` recorded no source, so the run was unresumable.

        Two runtimes rather than one -- a same-process resume succeeds off the
        in-memory graph registry and never reaches the rebuild, which is why this
        went unnoticed.
        """
        with tempfile.TemporaryDirectory() as td:
            cwd = os.getcwd()
            os.chdir(td)
            try:
                started = NodusRuntime(timeout_ms=None).run_source(
                    WORKFLOW.format(marker="ran")
                )
                gid = _gid(started.get("stdout"))

                resumed = NodusRuntime(timeout_ms=None).run_source(
                    'fn main() {{ let r = resume_workflow("{}", "cp"); '
                    'let s = r["state"]; print("STATE=\\(s)") }}'.format(gid)
                )
            finally:
                os.chdir(cwd)

        stdout = resumed.get("stdout") or ""
        self.assertNotIn("workflow_rebuild_failed", stdout)
        self.assertIn("STATE=", stdout)


class ResumeReplaysThePinnedSourceTests(unittest.TestCase):
    def _run_then_edit_then_resume(self, edit: bool):
        with tempfile.TemporaryDirectory() as td:
            cwd = os.getcwd()
            os.chdir(td)
            try:
                path = os.path.join(td, "wf.nd")
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write(WORKFLOW.format(marker="ORIGINAL"))

                started = NodusRuntime(timeout_ms=None).run_file(path)
                gid = _gid(started.get("stdout"))

                if edit:
                    with open(path, "w", encoding="utf-8") as handle:
                        handle.write(WORKFLOW.format(marker="EDITED"))

                return NodusRuntime(timeout_ms=None).run_source(
                    'fn main() {{ let r = resume_workflow("{}", "cp"); '
                    'print("done") }}'.format(gid)
                )
            finally:
                os.chdir(cwd)

    def test_edits_made_after_the_run_are_not_replayed(self):
        resumed = self._run_then_edit_then_resume(edit=True)
        stdout = resumed.get("stdout") or ""
        self.assertIn("a ORIGINAL", stdout)
        self.assertNotIn("a EDITED", stdout)

    def test_drift_is_reported_rather_than_swallowed(self):
        resumed = self._run_then_edit_then_resume(edit=True)
        stderr = resumed.get("stderr") or ""
        self.assertIn("replaying the source stored when the run started", stderr)
        self.assertIn("wf.nd", stderr)

    def test_an_unchanged_file_produces_no_warning(self):
        """Falsifiability guard: a warning that always fires reports nothing."""
        resumed = self._run_then_edit_then_resume(edit=False)
        stderr = resumed.get("stderr") or ""
        self.assertNotIn("replaying the source stored", stderr)


if __name__ == "__main__":
    unittest.main()
