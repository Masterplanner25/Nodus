"""#909: a rebuild re-binds definitions and does not repeat work it can avoid.

A workflow resume, a sweep and a durable coroutine's resume all rebuild the
program by re-running its stored source on a fresh VM (`VM.reexecute_source_
for_resume`). The re-run exists to re-bind functions, workflows, imports and
module-level values. `print`, `run_workflow`, `run_goal` and `durable_spawn`
were already suppressed; everything else at the top level ran again.

Two kinds of work are now skipped as well:

- **the scheduling builtins** (`REBUILD_INERT_BUILTINS`): `spawn` and
  `spawn_after` return the coroutine unscheduled, and `run_loop` and `wait`
  return nil. Starting work never defines anything.
- **a top-level call to `main()`**: the loader already did not auto-run `main`
  during a rebuild, but a program that calls it itself ran its work again.
  Skipped at run time, so the rebuilt chunk is byte-identical and a durable
  coroutine's program fingerprint still matches.

Still re-run, deliberately, and filed separately: a top-level host-function call
or effectful builtin outside `main`. Such a call may compute a value a definition
depends on, so skipping it silently could rebuild a different program.
"""

import os
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))  # noqa: E402

from nodus.builtins.coroutine import REBUILD_INERT_BUILTINS  # noqa: E402
from nodus.builtins.nodus_builtins import BuiltinInfo  # noqa: E402
from nodus.runtime.durable import run_id_for  # noqa: E402
from nodus.runtime.embedding import NodusRuntime  # noqa: E402
from nodus.vm.vm import VM  # noqa: E402
from nodus_lang_workflow.models import RUN_STATUS_COMPLETED  # noqa: E402
from nodus_lang_workflow.runner import WorkflowFrameworkRunner  # noqa: E402
from nodus_lang_workflow.store import SQLiteWorkflowStore  # noqa: E402

_PROGRAM = """
let base = 10i
note("top-level host call")
fn helper() { note("helper ran"); return base }
let h = spawn(fn() { note("spawned coroutine ran") })
let d = spawn_after(5i, fn() { note("delayed coroutine ran") })
let status = coroutine_status(h)
cancel(h)
wait(d)
run_loop()
fn main() { note("main ran"); helper() }
main()
"""


def _noting_vm(calls: list) -> VM:
    vm = VM([], {}, code_locs=[], source_path=None)
    vm.builtins["note"] = BuiltinInfo("note", 1, lambda s: calls.append(s))
    return vm


class ARebuildSkipsWhatStartsWorkTests(unittest.TestCase):

    # closes: #909
    def test_a_rebuild_runs_only_what_binds_definitions(self):
        calls = []
        vm = _noting_vm(calls)
        vm.reexecute_source_for_resume(textwrap.dedent(_PROGRAM), None, what="test")
        # Only the top-level host call, the residue a rebuild cannot judge.
        self.assertEqual(["top-level host call"], calls)
        # And the definitions are there: a value, functions, and the handle
        # the rest of the top level used, unscheduled.
        self.assertEqual(10, vm.globals["base"])
        self.assertIn("helper", vm.functions)
        self.assertIn("main", vm.functions)
        self.assertEqual("created", vm.globals["status"])
        self.assertFalse(vm.scheduler.ready_queue)
        self.assertFalse(vm.scheduler.timers)

    def test_the_same_program_run_normally_does_all_of_it(self):
        """The control: everything skipped above runs when it is not a rebuild,
        so the rebuild test is not passing because the program does nothing."""
        calls = []
        rt = NodusRuntime(timeout_ms=None, max_steps=None)
        rt.register_function("note", lambda s: calls.append(s))
        result = rt.run_source(textwrap.dedent(_PROGRAM))
        self.assertTrue(result.get("ok"), result)
        self.assertEqual(
            ["top-level host call", "delayed coroutine ran", "main ran", "helper ran"],
            calls)

    def test_main_called_from_inside_a_function_is_not_the_top_level_call(self):
        """Only the top-level call is skipped. `main` reached through another
        function is that function's business, and the rule stays narrow."""
        calls = []
        vm = _noting_vm(calls)
        vm.reexecute_source_for_resume(textwrap.dedent("""
            fn main() { note("main ran") }
            fn boot() { main() }
            boot()
            """), None, what="test")
        self.assertEqual(["main ran"], calls)

    def test_each_inert_builtin_does_nothing_that_runs(self):
        """Per name, so a builtin added to the vocabulary and not wrapped, or
        wrapped and not added, shows up here."""
        self.assertEqual({"spawn", "spawn_after", "__spawn_after", "run_loop", "wait"},
                         set(REBUILD_INERT_BUILTINS))
        for name in REBUILD_INERT_BUILTINS:
            with self.subTest(name):
                vm = VM([], {}, code_locs=[], source_path=None)
                vm._suppress_flow_execution = True
                fn = vm.builtins[name].fn
                args = {"spawn": [vm.builtins["coroutine"].fn(_closure(vm))],
                        "spawn_after": [1, _closure(vm)],
                        "__spawn_after": [1, _closure(vm)],
                        "run_loop": [],
                        "wait": [None]}[name]
                fn(*args)
                self.assertFalse(vm.scheduler.ready_queue, name)
                self.assertFalse(vm.scheduler.timers, name)


def _closure(vm: VM):
    """A zero-argument Nodus function, compiled in `vm`."""
    vm.reexecute_source_for_resume("fn zero() { return 1i }\n", None, what="helper")
    from nodus.vm.types import Closure
    return Closure(vm.functions["zero"], [])


_SIDE = textwrap.dedent("""
    import os, sys
    sys.path.insert(0, {src!r})
    from nodus.runtime.embedding import NodusRuntime
    from nodus_lang_workflow.runner import WorkflowFrameworkRunner
    from nodus_lang_workflow.store import SQLiteWorkflowStore
    runner = WorkflowFrameworkRunner(SQLiteWorkflowStore(os.environ["DURABLE_DB"], claim_ttl_ms=200.0))
    rt = NodusRuntime(timeout_ms=None, max_steps=None, workflow_runner=runner)
    def note(line):
        with open(os.environ["DURABLE_LOG"], "a", encoding="utf-8") as fh:
            fh.write(line + "\\n")
    rt.register_function("note", note)
    rt.register_function("crash", lambda: os._exit(3))
    rt.run_source({program!r})
    os._exit(4)
""")

_DURABLE = """
fn job() {
    note("job started")
    checkpoint "half"
    crash()
    note("job resumed")
    return 1i
}
fn main() {
    note("main started")
    spawn(fn() { note("side work in main") })
    durable_spawn("rebuild-job", job, [])
    run_loop()
}
spawn(fn() { note("side work at top level") })
main()
"""


class ADurableResumeDoesNotRepeatThemTests(unittest.TestCase):

    def test_a_sweep_resumes_the_job_without_rerunning_main_or_spawns(self):
        """The case #909 is about: the program calls `main()` itself and spawns
        side work at top level. A sweep resumes the job, and none of that runs
        a second time. The resume succeeding also shows the rebuilt chunk kept
        its fingerprint, which a compile-time strip of `main()` would break."""
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            env = dict(os.environ, DURABLE_DB=str(tmp / "runs.db"), DURABLE_LOG=str(tmp / "log.txt"))
            proc = subprocess.run(
                [sys.executable, "-c", _SIDE.format(src=str(REPO / "src"), program=_DURABLE)],
                env=env, cwd=raw, capture_output=True, text=True, timeout=120)
            self.assertEqual(3, proc.returncode, proc.stderr[-1500:])
            before = (tmp / "log.txt").read_text(encoding="utf-8").splitlines()
            time.sleep(0.4)

            store = SQLiteWorkflowStore(str(tmp / "runs.db"), claim_ttl_ms=200.0)
            rt = NodusRuntime(timeout_ms=None, max_steps=None,
                              workflow_runner=WorkflowFrameworkRunner(store))
            log = tmp / "log.txt"
            rt.register_function("note", lambda line: log.open("a", encoding="utf-8").write(line + "\n"))
            rt.register_function("crash", lambda: None)
            report = rt.sweep()
            after = log.read_text(encoding="utf-8").splitlines()[len(before):]
            record = store.get_run(run_id_for("rebuild-job"))
        self.assertIn("job started", before)
        (entry,) = report["resumed_coroutines"]
        self.assertTrue(entry["ok"], entry)
        self.assertEqual(RUN_STATUS_COMPLETED, record.status)
        self.assertEqual(["job resumed"], after)


if __name__ == "__main__":
    unittest.main()
