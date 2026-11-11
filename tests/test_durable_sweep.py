"""#180 stage 4c: a long-lived host resumes durable coroutines through the sweep.

D4 in design 08a: a durable coroutine is a run in the workflow store, so the
machinery that already picks runs up after a crash -- `sweep()`, behind `nodus
workflow sweep` and the server's background sweeper -- picks these up too.
Where a graph run is *adopted* by the sweep and waits for something to carry it
on, a durable coroutine is *resumed*: carrying on is all it means. The sweep is
already the explicit act that may run stored code (it resumes due retries and
released schedules), which is the boundary #176 drew.

The program is rebuilt from the source stored with the run, re-executed only to
re-bind its definitions: its top-level `print`s and its own `durable_spawn`
call are suppressed, so the sweep resumes the run once rather than racing a
second copy of it.

And the paths that cannot resume one say so by kind: `resume_workflow` (`nodus
workflow resume <id>`) and `rehydrate_run`. Before this, a coroutine run was
turned away only because it has no graph-state file, which was right by accident.
"""

import os
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))  # noqa: E402

from nodus.builtins.nodus_builtins import BuiltinInfo  # noqa: E402
from nodus.runtime.durable import run_id_for  # noqa: E402
from nodus.vm.vm import VM  # noqa: E402
from nodus_lang_workflow.models import (  # noqa: E402
    RUN_STATUS_COMPLETED,
    RUN_STATUS_RUNNING,
)
from nodus_lang_workflow.runner import WorkflowFrameworkRunner  # noqa: E402
from nodus_lang_workflow.store import SQLiteWorkflowStore  # noqa: E402

_SIDE = textwrap.dedent("""
    import os, sys
    sys.path.insert(0, {src!r})
    from nodus.runtime.embedding import NodusRuntime
    from nodus_lang_workflow.runner import WorkflowFrameworkRunner, configure_default_workflow_runner
    from nodus_lang_workflow.store import SQLiteWorkflowStore
    configure_default_workflow_runner(runner=WorkflowFrameworkRunner(
        SQLiteWorkflowStore(os.environ["DURABLE_DB"], claim_ttl_ms=200.0)))
    rt = NodusRuntime(timeout_ms=None, max_steps=None)
    rt.register_function("crash", lambda: os._exit(3))
    rt.run_source({program!r})
    os._exit(4)
""")

# `crash` is a host function, and host functions are not rebuilt from source:
# the host that sweeps re-supplies them, as it would any embedder-provided
# function (the same rule as a rebuilt workflow). In the sweep it does nothing.
_PROGRAM = """
let started = durable_spawn("swept", worker, [3i])
print("top-level ran")
fn worker(n) {
    print("worker started")
    let total = n * 10i
    checkpoint "computed"
    crash()
    print("resumed with total=\\(total)")
    return total
}
run_loop()
"""


def _crash_once(tmp: Path) -> None:
    env = dict(os.environ, DURABLE_DB=str(tmp / "runs.db"))
    proc = subprocess.run(
        [sys.executable, "-c", _SIDE.format(src=str(REPO / "src"), program=_PROGRAM)],
        env=env, cwd=str(tmp), capture_output=True, text=True, timeout=120)
    if proc.returncode != 3:
        raise AssertionError(f"expected the side process to die (3), got "
                             f"{proc.returncode}: {proc.stderr[-1500:]}")
    time.sleep(0.4)  # its 200 ms claim lapses


def _sweep(store, *, register=None, min_idle_ms: float = 0.0):
    runner = WorkflowFrameworkRunner(store)

    def vm_factory(_record):
        # The shape `nodus workflow sweep` builds: a bare VM carrying this runner.
        vm = VM([], {}, code_locs=[], source_path=None)
        vm.workflow_runner = runner
        for name, fn in (register or {}).items():
            vm.builtins[name] = BuiltinInfo(name, 0, fn)
        return vm

    out, err = StringIO(), StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        report = runner.sweep(vm_factory, min_idle_ms=min_idle_ms)
    return report, out.getvalue(), err.getvalue()


class TheSweepResumesItTests(unittest.TestCase):

    def test_a_crashed_run_is_carried_on_by_a_sweep(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            _crash_once(tmp)
            store = SQLiteWorkflowStore(str(tmp / "runs.db"), claim_ttl_ms=200.0)
            self.assertEqual(RUN_STATUS_RUNNING, store.get_run(run_id_for("swept")).status)
            report, printed, errors = _sweep(store, register={"crash": lambda: None})
            record = store.get_run(run_id_for("swept"))
        # The rebuild re-runs the top level, which calls `durable_spawn` again.
        # Suppressed, it does nothing. Unsuppressed, it would find the sweep's
        # own claim and warn here -- and with another key it would start that run
        # from inside the rebuild.
        self.assertEqual("", errors)
        (entry,) = report["resumed_coroutines"]
        self.assertTrue(entry["ok"], entry)
        self.assertEqual("swept", entry["key"])
        self.assertEqual(RUN_STATUS_COMPLETED, entry["status"])
        self.assertEqual(RUN_STATUS_COMPLETED, record.status)
        self.assertEqual(1, record.resume_count)
        self.assertEqual([], report["rehydrated_runs"], "a coroutine was also adopted as a graph")
        # Resumed at the checkpoint: the worker did not start again, and its
        # local came back. The rebuild's re-run of the top level printed
        # nothing and started nothing.
        self.assertEqual("resumed with total=30\n", printed)

    def test_a_run_held_by_a_live_process_is_left_alone(self):
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            _crash_once(tmp)
            store = SQLiteWorkflowStore(str(tmp / "runs.db"), claim_ttl_ms=60_000.0)
            self.assertIsNotNone(store.claim_run(run_id_for("swept"), owner="alive"))
            report, printed, _errors = _sweep(store, register={"crash": lambda: None})
            record = store.get_run(run_id_for("swept"))
        self.assertEqual([{"run_id": run_id_for("swept"), "key": "swept",
                           "workflow_name": "worker", "ok": True,
                           "status": "held_elsewhere"}], report["resumed_coroutines"])
        self.assertEqual("", printed)
        self.assertEqual("alive", record.claim.owner)
        self.assertEqual(RUN_STATUS_RUNNING, record.status)

    def test_min_idle_ms_still_gates_it(self):
        """A background sweeper passes `min_idle_ms` because it cannot tell an
        orphan from a run in progress. That gate applies to coroutine runs too."""
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            _crash_once(tmp)
            store = SQLiteWorkflowStore(str(tmp / "runs.db"), claim_ttl_ms=200.0)
            report, _out, _err = _sweep(store, register={"crash": lambda: None},
                                        min_idle_ms=3_600_000.0)
        self.assertEqual([], report["resumed_coroutines"])


class OtherPathsSayWhatItIsTests(unittest.TestCase):

    def _crashed_store(self, tmp: Path):
        _crash_once(tmp)
        return SQLiteWorkflowStore(str(tmp / "runs.db"), claim_ttl_ms=200.0)

    def test_resume_workflow_names_where_it_is_resumed_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as raw:
            store = self._crashed_store(Path(raw))
            before = store.get_run(run_id_for("swept")).to_dict()
            vm = VM([], {}, code_locs=[], source_path=None)
            result = WorkflowFrameworkRunner(store).resume_workflow(
                vm, run_id_for("swept"), rebuild_graph=vm._rebuild_workflow_graph)
            after = store.get_run(run_id_for("swept")).to_dict()
        self.assertFalse(result["ok"])
        self.assertEqual("not_a_graph_run", result["category"])
        self.assertIn("durable_spawn", result["error"])
        self.assertIn("nodus workflow sweep", result["error"])
        self.assertEqual(before, after)

    def test_rehydrate_run_turns_it_away_by_kind_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as raw:
            store = self._crashed_store(Path(raw))
            before = store.get_run(run_id_for("swept")).to_dict()
            vm = VM([], {}, code_locs=[], source_path=None)
            info = WorkflowFrameworkRunner(store).rehydrate_run(
                vm, run_id_for("swept"), rebuild_graph=vm._rebuild_workflow_graph)
            after = store.get_run(run_id_for("swept")).to_dict()
        self.assertIsNone(info)
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
