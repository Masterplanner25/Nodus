"""#908: an embedder sweeps on VMs configured like its own runtime.

`WorkflowFrameworkRunner.sweep(vm_factory)` rebuilds each resumed program on a
VM the host supplies. The only one an embedder could build was a bare
`VM([], {})`, which has two problems:

- **it lacks the host's functions**, so a resumed durable coroutine or workflow
  that calls one fails with `Undefined function`;
- **it lacks the host's confinement**, and that is the worse half. A bare VM
  is permissive by default, so code that an embedded runtime denies (the
  environment, subprocesses, the network) was allowed once it was resumed.

`NodusRuntime.new_vm()` builds a VM the way `run_source` does, through one
builder, and `NodusRuntime.sweep()` sweeps with it.
"""

import os
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))  # noqa: E402

from nodus.runtime.durable import run_id_for  # noqa: E402
from nodus.runtime.embedding import NodusRuntime  # noqa: E402
from nodus.vm.vm import VM  # noqa: E402
from nodus_lang_workflow.models import RUN_STATUS_COMPLETED, RUN_STATUS_FAILED  # noqa: E402
from nodus_lang_workflow.runner import WorkflowFrameworkRunner  # noqa: E402
from nodus_lang_workflow.store import SQLiteWorkflowStore  # noqa: E402

_SIDE = textwrap.dedent("""
    import os, sys
    sys.path.insert(0, {src!r})
    from nodus.runtime.embedding import NodusRuntime
    from nodus_lang_workflow.runner import WorkflowFrameworkRunner
    from nodus_lang_workflow.store import SQLiteWorkflowStore
    runner = WorkflowFrameworkRunner(SQLiteWorkflowStore(os.environ["DURABLE_DB"], claim_ttl_ms=200.0))
    rt = NodusRuntime(timeout_ms=None, max_steps=None, workflow_runner=runner)
    rt.register_function("upload", lambda rows: None)
    rt.register_function("crash", lambda: os._exit(3))
    rt.run_source({program!r})
    os._exit(4)
""")


def _crashed(tmp: Path, program: str) -> SQLiteWorkflowStore:
    """Run `program` until it calls crash(), as a real process dying would."""
    env = dict(os.environ, DURABLE_DB=str(tmp / "runs.db"))
    proc = subprocess.run(
        [sys.executable, "-c", _SIDE.format(src=str(REPO / "src"), program=program)],
        env=env, cwd=str(tmp), capture_output=True, text=True, timeout=120)
    if proc.returncode != 3:
        raise AssertionError(f"side process exited {proc.returncode}: {proc.stderr[-1500:]}")
    time.sleep(0.4)  # its 200 ms claim lapses
    return SQLiteWorkflowStore(str(tmp / "runs.db"), claim_ttl_ms=200.0)


_UPLOADER = """
fn job(rows) {
    checkpoint "received"
    crash()
    upload(rows)
    print("uploaded \\(len(rows))")
    return len(rows)
}
durable_spawn("upload-job", job, [[1i, 2i, 3i]])
run_loop()
"""

_READS_ENV = """
fn job() {
    checkpoint "started"
    crash()
    let home = env_get("PATH", "unset")
    print("read the environment")
    return 1i
}
durable_spawn("env-job", job, [])
run_loop()
"""


class TheHostsFunctionsComeAlongTests(unittest.TestCase):

    # closes: #908
    def test_a_runtime_sweep_resumes_code_that_calls_a_host_function(self):
        uploaded = []
        with tempfile.TemporaryDirectory() as raw:
            store = _crashed(Path(raw), _UPLOADER)
            rt = NodusRuntime(timeout_ms=None, max_steps=None,
                              workflow_runner=WorkflowFrameworkRunner(store))
            rt.register_function("upload", lambda rows: uploaded.append(rows))
            rt.register_function("crash", lambda: None)
            host_out = StringIO()
            with redirect_stdout(host_out):
                report = rt.sweep()
            record = store.get_run(run_id_for("upload-job"))
        (entry,) = report["resumed_coroutines"]
        self.assertTrue(entry["ok"], entry)
        self.assertEqual(RUN_STATUS_COMPLETED, record.status)
        self.assertEqual([[1, 2, 3]], uploaded)
        # The resumed program's output is in the report, not on the host's stdout.
        self.assertEqual("uploaded 3\n", report["stdout"])
        self.assertEqual("", host_out.getvalue())

    def test_the_bare_vm_this_replaces_could_not(self):
        """The control: without the host's functions the same resume fails, so
        the test above is passing because of what `new_vm` carries."""
        with tempfile.TemporaryDirectory() as raw:
            store = _crashed(Path(raw), _UPLOADER)
            runner = WorkflowFrameworkRunner(store)
            with redirect_stdout(StringIO()):
                report = runner.sweep(lambda _r: VM([], {}, code_locs=[]))
        (entry,) = report["resumed_coroutines"]
        self.assertFalse(entry["ok"])
        self.assertIn("Undefined function", entry["error"])


class TheHostsConfinementComesAlongTests(unittest.TestCase):

    def test_a_capability_the_runtime_denies_stays_denied_after_a_resume(self):
        """`NodusRuntime` denies the environment by default (#405). Resumed on
        its own VM, the program is refused exactly as in a normal run."""
        with tempfile.TemporaryDirectory() as raw:
            store = _crashed(Path(raw), _READS_ENV)
            rt = NodusRuntime(timeout_ms=None, max_steps=None,
                              workflow_runner=WorkflowFrameworkRunner(store))
            rt.register_function("crash", lambda: None)
            report = rt.sweep()
            record = store.get_run(run_id_for("env-job"))
        (entry,) = report["resumed_coroutines"]
        self.assertFalse(entry["ok"])
        self.assertEqual(RUN_STATUS_FAILED, record.status)
        self.assertIn("allow_env", record.last_error)
        self.assertNotIn("read the environment", report.get("stdout", ""))

    def test_on_a_bare_vm_the_same_resume_escapes_that_confinement(self):
        """The defect's worse half, kept visible: a bare VM is permissive, so
        the program the runtime would refuse reads the environment once it is
        resumed. This is what an embedder following the documented sweep
        pattern was doing."""
        with tempfile.TemporaryDirectory() as raw:
            store = _crashed(Path(raw), _READS_ENV)

            def bare(_record):
                vm = VM([], {}, code_locs=[])
                vm.builtins["crash"] = rt_builtin
                return vm

            from nodus.builtins.nodus_builtins import BuiltinInfo
            rt_builtin = BuiltinInfo("crash", 0, lambda: None)
            out = StringIO()
            with redirect_stdout(out):
                WorkflowFrameworkRunner(store).sweep(bare)
            record = store.get_run(run_id_for("env-job"))
        self.assertEqual(RUN_STATUS_COMPLETED, record.status)
        self.assertIn("read the environment", out.getvalue())


class OneBuilderTests(unittest.TestCase):
    """`new_vm` and `run_source` build through `_build_vm`. Asked of the VMs
    themselves, not the source, so a second construction path that drifted
    would show up here."""

    _CONFIG = ("allowed_paths", "writable_paths", "allow_subprocess", "allow_network",
               "allow_env", "allowed_commands", "allowed_hosts", "capability_policy",
               "approval_channel", "agent_timeout_ms", "persist_workflow_source",
               "memory_store", "agent_registry", "budget_meters", "workflow_runner",
               "max_steps", "max_frames", "input_fn")

    def test_new_vm_is_configured_as_a_run_is(self):
        with tempfile.TemporaryDirectory() as tmp:
            rt = NodusRuntime(timeout_ms=None, max_steps=12345, allowed_paths=[tmp],
                              allow_network=True, max_frames=321)
            rt.register_function("host_fn", lambda: 1)
            rt.run_source("let x = 1i")
            ran_on = rt.active_vm()
            fresh = rt.new_vm()
        self.assertIsNot(ran_on, fresh)
        for name in self._CONFIG:
            with self.subTest(name):
                a, b = getattr(ran_on, name, None), getattr(fresh, name, None)
                if callable(a) and callable(b) and name == "input_fn":
                    self.assertEqual(getattr(a, "__func__", a), getattr(b, "__func__", b))
                else:
                    self.assertEqual(a, b)
        self.assertIn("host_fn", fresh.builtins)
        self.assertEqual(12345, fresh.max_steps)
        self.assertEqual(321, fresh.max_frames)

    def test_new_vm_does_not_replace_the_last_run(self):
        rt = NodusRuntime(timeout_ms=None, max_steps=None)
        rt.run_source("let x = 1i")
        ran_on = rt.active_vm()
        rt.new_vm()
        self.assertIs(ran_on, rt.active_vm())


if __name__ == "__main__":
    unittest.main()
