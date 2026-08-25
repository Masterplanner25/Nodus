"""A rebuilt graph must be the shape the run was planned for (#470).

The persisted state is per-task bookkeeping keyed to the planned graph. When a
resume rebuilds a *different* shape -- a legacy run rebuilt from an edited file,
a hand-edited state file, a lowering change across versions -- applying that
bookkeeping manufactures false diagnoses: a step inserted between two others
collides with a stored task id and surfaced as `Dependency cycle detected:
z -> z` in source with no cycle.

Every run now records `workflow_topology` (step names + dependency edges) in its
metadata, and `_rebuild_workflow_graph` refuses a mismatch with the real cause.
Runs that predate the recording are checked on step names alone, from
`step_to_task` -- edges were not recorded for them, so an edge-only rewire on
such a run is still undetectable, which is a stated limit rather than a bug.
"""
import glob
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus.runtime.embedding import NodusRuntime  # noqa: E402

ORIGINAL = """
workflow w {
    state log = ""
    step a { log = log + "a"; checkpoint "cp"; return 1i }
    step b after a { log = log + "b"; return 2i }
}
fn main() {
    let r = run_workflow(w)
    let g = r["graph_id"]
    print("GID=\\(g)")
}
"""

EDITED_INSERTED_STEP = """
workflow w {
    state log = ""
    step a { log = log + "a"; checkpoint "cp"; return 1i }
    step z after a { log = log + "z"; return 9i }
    step b after z { log = log + "b"; return 2i }
}
fn main() {
    let r = run_workflow(w)
    let g = r["graph_id"]
    print("GID=\\(g)")
}
"""

RESUME = (
    'fn main() {{ let r = resume_workflow("{gid}", "cp"); print("RESULT=\\(r)") }}'
)


def _gid(stdout: str) -> str:
    for line in (stdout or "").splitlines():
        if line.startswith("GID="):
            return line[4:].strip()
    raise AssertionError(f"no graph id in {stdout!r}")


def _state_files(root: str, gid: str) -> list[str]:
    return glob.glob(os.path.join(root, ".nodus", "graphs", f"{gid}*.json"))


def _edit_metadata(path: str, mutate) -> None:
    with open(path, encoding="utf-8") as handle:
        state = json.load(handle)
    if isinstance(state.get("metadata"), dict):
        mutate(state["metadata"])
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(state, handle, sort_keys=True, separators=(",", ":"))


class _WorkflowHarness(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self._cwd = os.getcwd()
        os.chdir(self._td.name)
        self.addCleanup(self._restore)
        self.path = os.path.join(self._td.name, "wf.nd")
        with open(self.path, "w", encoding="utf-8") as handle:
            handle.write(ORIGINAL)
        started = NodusRuntime(timeout_ms=None).run_file(self.path)
        self.gid = _gid(started.get("stdout"))

    def _restore(self):
        os.chdir(self._cwd)
        self._td.cleanup()

    def _resume(self) -> dict:
        return NodusRuntime(timeout_ms=None).run_source(RESUME.format(gid=self.gid))


# closes: #470
class TopologyValidationTests(_WorkflowHarness):
    def test_legacy_run_with_inserted_step_refuses_with_real_cause(self):
        """The original report: an edited file resumed against a legacy run
        produced `Dependency cycle detected: z -> z` in source with no cycle."""
        for state_file in _state_files(self._td.name, self.gid):
            _edit_metadata(
                state_file,
                lambda meta: (
                    meta.__setitem__("workflow_source_code", None),
                    meta.pop("workflow_topology", None),
                ),
            )
        with open(self.path, "w", encoding="utf-8") as handle:
            handle.write(EDITED_INSERTED_STEP)

        stdout = self._resume().get("stdout") or ""
        self.assertNotIn("Dependency cycle detected", stdout)
        self.assertIn("planned against a different version", stdout)
        self.assertIn("steps added: z", stdout)
        self.assertIn("start a new run", stdout)

    def test_tampered_stored_topology_refuses(self):
        """The stored-topology comparison itself, on a pinned run."""
        for state_file in _state_files(self._td.name, self.gid):
            if state_file.endswith(".checkpoint.json"):
                continue
            _edit_metadata(
                state_file,
                lambda meta: meta["workflow_topology"]["steps"].append("ghost"),
            )

        stdout = self._resume().get("stdout") or ""
        self.assertIn("planned against a different version", stdout)
        self.assertIn("steps removed: ghost", stdout)

    def test_unchanged_resume_still_passes_validation(self):
        """Falsifiability guard: a check that always refuses reports nothing."""
        result = self._resume()
        stdout = result.get("stdout") or ""
        self.assertNotIn("planned against a different version", stdout)
        self.assertIn('"state"', stdout)

    def test_new_runs_record_their_topology(self):
        state_file = [
            path
            for path in _state_files(self._td.name, self.gid)
            if not path.endswith(".checkpoint.json")
        ][0]
        with open(state_file, encoding="utf-8") as handle:
            state = json.load(handle)
        topology = state["metadata"]["workflow_topology"]
        self.assertEqual(topology["steps"], ["a", "b"])
        self.assertEqual(topology["edges"], [["a", "b"]])


class UnpinnedRebuildSaysSoTests(_WorkflowHarness):
    def test_legacy_rebuild_from_disk_warns_and_still_resumes(self):
        """The other half of the fork (#497): a legacy run rebuilt from the file
        as it is now used to do so with no signal at all. With the file
        unchanged the resume must still succeed -- the warning is a signal,
        not a refusal."""
        for state_file in _state_files(self._td.name, self.gid):
            _edit_metadata(
                state_file,
                lambda meta: (
                    meta.__setitem__("workflow_source_code", None),
                    meta.pop("workflow_topology", None),
                ),
            )

        result = self._resume()
        self.assertIn('"state"', result.get("stdout") or "")
        stderr = result.get("stderr") or ""
        self.assertIn("predates source recording", stderr)
        self.assertIn("wf.nd", stderr)

    def test_pinned_rebuild_does_not_claim_to_be_unpinned(self):
        stderr = self._resume().get("stderr") or ""
        self.assertNotIn("predates source recording", stderr)


if __name__ == "__main__":
    unittest.main()
