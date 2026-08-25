"""A nested run knows where it came from, and cleanup can follow the link (#501).

A `run_graph` / `run_workflow` call inside a workflow step creates a separate
run. Its record used to be an orphan: metadata `{}`, no link in either
direction, one more per resume (#486 re-enters the step, so the nested call
runs again), and nothing to attribute or cascade over.

Now the child's metadata records `parent_graph_id` / `parent_step` /
`parent_task_id` / `parent_workflow` from its first persist; the parent
accumulates `child_graph_ids` (carried across resume rebuilds, so the list is
cumulative); `workflow list` surfaces the link; and `workflow cleanup`
removes children with their parent. The re-execution itself is the documented
step-re-entry rule, not fixed here -- see the guide's checkpoint section.
"""
import glob
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

SOURCE = """
workflow pipeline {
    step plan { return ["a", "b"] }
    step process after plan {
        let t = task(fn() { return 1i }, nil)
        let sub = run_graph([t])
        let gid = sub["graph_id"]
        print("SUB=\\(gid)")
        checkpoint "fanned_out"
        return 1i
    }
}
fn main() {
    let r = run_workflow(pipeline)
    let g = r["graph_id"]
    print("GID=\\(g)")
}
"""


def _tagged(stdout: str, tag: str) -> list[str]:
    return [line[len(tag):].strip() for line in (stdout or "").splitlines() if line.startswith(tag)]


class _NestedHarness(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self._cwd = os.getcwd()
        os.chdir(self._td.name)
        self.addCleanup(self._restore)
        path = os.path.join(self._td.name, "wf.nd")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(SOURCE)
        started = NodusRuntime(timeout_ms=None).run_file(path)
        stdout = started.get("stdout") or ""
        self.gid = _tagged(stdout, "GID=")[0]
        self.child = _tagged(stdout, "SUB=")[0]

    def _restore(self):
        os.chdir(self._cwd)
        self._td.cleanup()

    def _state(self, gid: str) -> dict:
        with open(
            os.path.join(self._td.name, ".nodus", "graphs", f"{gid}.json"),
            encoding="utf-8",
        ) as handle:
            return json.load(handle)


# closes: #501
class NestedRunLinkageTests(_NestedHarness):
    def test_child_records_its_parent(self):
        meta = self._state(self.child)["metadata"]
        self.assertEqual(meta["parent_graph_id"], self.gid)
        self.assertEqual(meta["parent_step"], "process")
        self.assertEqual(meta["parent_workflow"], "pipeline")
        self.assertIn("parent_task_id", meta)

    def test_parent_records_its_children_cumulatively_across_resumes(self):
        resumed = NodusRuntime(timeout_ms=None).run_source(
            'fn main() {{ let r = resume_workflow("{}", "fanned_out"); '
            'print("R") }}'.format(self.gid)
        )
        second_child = _tagged(resumed.get("stdout") or "", "SUB=")[0]
        children = self._state(self.gid)["metadata"]["child_graph_ids"]
        self.assertIn(self.child, children)
        self.assertIn(second_child, children)

    def test_listing_surfaces_the_link(self):
        from nodus.orchestration.task_graph import list_graph_snapshots_info

        by_id = {info["graph_id"]: info for info in list_graph_snapshots_info()}
        self.assertEqual(by_id[self.child]["parent_graph_id"], self.gid)
        self.assertEqual(by_id[self.child]["parent_step"], "process")
        # Falsifiability control: a run that was not nested carries no link.
        self.assertNotIn("parent_graph_id", by_id[self.gid])

    def test_cleanup_cascades_from_parent_to_children(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = main(["nodus", "workflow", "cleanup", "--force"])
        self.assertEqual(code, 0)
        payload = json.loads(out.getvalue().strip())
        self.assertIn(self.gid, payload["removed"])
        self.assertIn(self.child, payload["removed"])
        leftover = [
            os.path.basename(path)
            for path in glob.glob(
                os.path.join(self._td.name, ".nodus", "graphs", "*.json")
            )
        ]
        self.assertEqual(leftover, [])


if __name__ == "__main__":
    unittest.main()
