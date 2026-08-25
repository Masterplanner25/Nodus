"""The two halves of a run share a lifecycle (#476).

A durable run is split across two stores -- graph state and checkpoint under
`.nodus/graphs/`, the run record under the workflow store -- and nothing kept
them in step: `nodus workflow cleanup` deleted graph state and left records to
accumulate forever, the store's opt-in record cap deleted records and left
graph state orphaned, and a resume whose record was gone (while the state sat
on disk) reported "not found".

Now cleanup removes both halves, the record cap prunes the graph state with
the record, and the missing-record resume names the real situation.
"""
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus.cli.cli import main  # noqa: E402
from nodus.runtime.embedding import NodusRuntime  # noqa: E402

WAITING_SOURCE = """
workflow waiter {
    step q { checkpoint "started"; return workflow_wait("go") }
    step act after q { return 1i }
}
fn main() {
    let r = run_workflow(waiter)
    let g = r["graph_id"]
    print("GID=\\(g)")
}
"""

COMPLETED_SOURCE = """
workflow done {
    step a { return 1i }
}
fn main() {
    let r = run_workflow(done)
    let g = r["graph_id"]
    print("GID=\\(g)")
}
"""


def _gid(stdout: str) -> str:
    for line in (stdout or "").splitlines():
        if line.startswith("GID="):
            return line[4:].strip()
    raise AssertionError(f"no graph id in {stdout!r}")


class _StoreHarness(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self._cwd = os.getcwd()
        os.chdir(self._td.name)
        self.addCleanup(self._restore)

    def _restore(self):
        os.chdir(self._cwd)
        self._td.cleanup()

    def _run(self, source: str) -> str:
        path = os.path.join(self._td.name, "wf.nd")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(source)
        started = NodusRuntime(timeout_ms=None).run_file(path)
        return _gid(started.get("stdout"))

    def _graph_state_path(self, gid: str) -> str:
        return os.path.join(self._td.name, ".nodus", "graphs", f"{gid}.json")

    def _record_path(self, gid: str) -> str:
        return os.path.join(
            self._td.name, ".nodus", "workflow_framework", "runs", f"{gid}.json"
        )


# closes: #476
class SharedLifecycleTests(_StoreHarness):
    def test_cleanup_removes_the_run_record_with_the_graph_state(self):
        gid = self._run(COMPLETED_SOURCE)
        self.assertTrue(os.path.exists(self._graph_state_path(gid)))
        self.assertTrue(os.path.exists(self._record_path(gid)))

        out = io.StringIO()
        with redirect_stdout(out):
            code = main(["nodus", "workflow", "cleanup", "--force"])
        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue().strip())
        self.assertIn(gid, payload["removed"])
        self.assertIn(gid, payload["run_records_removed"])
        self.assertFalse(os.path.exists(self._graph_state_path(gid)))
        self.assertFalse(os.path.exists(self._record_path(gid)))

    def test_missing_record_resume_names_the_real_cause(self):
        """The issue's repro: delete only the records directory and a live
        waiting run reported "not found" while its state sat on disk."""
        gid = self._run(WAITING_SOURCE)
        record = self._record_path(gid)
        os.remove(record)
        self.assertTrue(os.path.exists(self._graph_state_path(gid)))

        resumed = NodusRuntime(timeout_ms=None).run_source(
            'fn main() {{ let r = resume_workflow("{}", {{"reply": "x"}}); '
            'print("R=\\(r)") }}'.format(gid)
        )
        stdout = resumed.get("stdout") or ""
        self.assertIn('"ok": false', stdout)
        self.assertNotIn("not found", stdout)
        self.assertIn("no run record", stdout)
        self.assertIn("cleaned independently", stdout)
        self.assertIn("run_record_missing", stdout)

    def test_unknown_id_still_says_not_found(self):
        """Falsifiability guard: the richer diagnosis must not swallow the
        plain case -- an id with neither half is still simply not found."""
        self._run(COMPLETED_SOURCE)
        resumed = NodusRuntime(timeout_ms=None).run_source(
            'fn main() { let r = resume_workflow("g_deadbeef", {"x": 1i}); '
            'print("R=\\(r)") }'
        )
        stdout = resumed.get("stdout") or ""
        self.assertIn("not found", stdout)
        self.assertNotIn("cleaned independently", stdout)

    def test_record_cap_prunes_graph_state_with_the_record(self):
        from nodus_lang_workflow.store import LocalWorkflowStore

        graphs = os.path.join(self._td.name, ".nodus", "graphs")
        os.makedirs(graphs, exist_ok=True)
        store = LocalWorkflowStore(max_terminal_runs=1)
        for gid in ("g_old", "g_new"):
            with open(os.path.join(graphs, f"{gid}.json"), "w", encoding="utf-8") as f:
                json.dump({"graph_id": gid, "status": "completed"}, f)
            record = store.create_run(
                run_id=gid, graph_id=gid, workflow_name="w", execution_kind="workflow"
            )
            record.status = "completed"
            store.save_run(record)
            # Prune order is (updated_at, run_id); two saves inside the same
            # clock tick would tie and fall back to the id, which is not the
            # property under test.
            import time

            time.sleep(0.01)

        self.assertIsNone(store.get_run("g_old"))
        self.assertIsNotNone(store.get_run("g_new"))
        self.assertFalse(
            os.path.exists(os.path.join(graphs, "g_old.json")),
            "pruning the record left its graph state orphaned",
        )
        self.assertTrue(os.path.exists(os.path.join(graphs, "g_new.json")))

    def test_sqlite_store_delete_run(self):
        from nodus_lang_workflow.store import SQLiteWorkflowStore

        store = SQLiteWorkflowStore(os.path.join(self._td.name, "wf.sqlite3"))
        store.create_run(
            run_id="g_x", graph_id="g_x", workflow_name="w", execution_kind="workflow"
        )
        self.assertTrue(store.delete_run("g_x"))
        self.assertIsNone(store.get_run("g_x"))
        self.assertFalse(store.delete_run("g_x"))


if __name__ == "__main__":
    unittest.main()
