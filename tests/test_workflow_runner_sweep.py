"""Regression: default workflow-runner auto-sweep thread lifecycle.

Root cause of a flaky CI failure (checkpoint resume returning a result without
``steps``; ``os.replace`` PermissionError on Windows): ``get_default_workflow_runner``
rebuilt the runner+store on every cwd change but left the *previous* auto-sweep
daemon thread alive, bound to the stale store instance. Two store objects for the
same directory, each with its own lock, then raced on the same run files.

These tests pin the fix: at most one sweep thread, always bound to the live
runner, stopped on rebuild / configure / reset.
"""
import os
import shutil
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from nodus_lang_workflow.runner import (  # noqa: E402
    WorkflowFrameworkRunner,
    configure_default_workflow_runner,
    get_default_workflow_runner,
    reset_default_workflow_runner,
)
from nodus_lang_workflow.store import LocalWorkflowStore  # noqa: E402

_SWEEP_NAME = "nodus-workflow-sweep"


def _live_sweep_threads():
    return [t for t in threading.enumerate() if t.name == _SWEEP_NAME and t.is_alive()]


class WorkflowSweepLifecycleTests(unittest.TestCase):
    def setUp(self):
        self._cwd = os.getcwd()
        self._autosweep = os.environ.get("NODUS_WORKFLOW_AUTOSWEEP")
        reset_default_workflow_runner()

    def tearDown(self):
        reset_default_workflow_runner()
        os.chdir(self._cwd)  # leave any temp cwd before addCleanup removes it
        if self._autosweep is None:
            os.environ.pop("NODUS_WORKFLOW_AUTOSWEEP", None)
        else:
            os.environ["NODUS_WORKFLOW_AUTOSWEEP"] = self._autosweep

    def _chdir_temp(self) -> str:
        d = tempfile.mkdtemp()
        # Removal runs after tearDown (which restores cwd + stops the sweep
        # thread), so the dir is no longer the cwd and no thread holds it.
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        os.chdir(d)
        return d

    def test_rebuild_stops_previous_sweep_thread(self):
        os.environ["NODUS_WORKFLOW_AUTOSWEEP"] = "1"
        self._chdir_temp()
        get_default_workflow_runner()
        self.assertEqual(len(_live_sweep_threads()), 1)

        # Rebuild for a different root: the old thread must be stopped, not
        # accumulated — exactly one live sweep thread remains.
        self._chdir_temp()
        get_default_workflow_runner()
        self.assertEqual(len(_live_sweep_threads()), 1)

    def test_reset_stops_thread_and_clears_runner(self):
        os.environ["NODUS_WORKFLOW_AUTOSWEEP"] = "1"
        self._chdir_temp()
        get_default_workflow_runner()
        self.assertEqual(len(_live_sweep_threads()), 1)
        reset_default_workflow_runner()
        self.assertEqual(len(_live_sweep_threads()), 0)

    def test_configure_stops_sweep_thread(self):
        os.environ["NODUS_WORKFLOW_AUTOSWEEP"] = "1"
        a = self._chdir_temp()
        get_default_workflow_runner()
        self.assertEqual(len(_live_sweep_threads()), 1)
        # Configuring a runner explicitly replaces the default and stops the
        # timer thread (it does not start a new one).
        configure_default_workflow_runner(
            runner=WorkflowFrameworkRunner(
                LocalWorkflowStore(root=os.path.join(a, ".nodus", "cfg"))
            )
        )
        self.assertEqual(len(_live_sweep_threads()), 0)

    def test_autosweep_disabled_starts_no_thread(self):
        os.environ["NODUS_WORKFLOW_AUTOSWEEP"] = "0"
        self._chdir_temp()
        get_default_workflow_runner()
        self.assertEqual(len(_live_sweep_threads()), 0)


if __name__ == "__main__":
    unittest.main()
