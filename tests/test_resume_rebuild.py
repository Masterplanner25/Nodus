"""Cross-process resume rebuilds a run's graph by re-executing its module (#399).

Three defects shared one root:

1. A script that *read* the `run_workflow` result could not be resumed. The
   rebuild suppresses `run_workflow`/`run_goal` and substitutes an index-safe
   placeholder, but the placeholder was missing `status`/`wait`/`retry`/`error` —
   exactly the keys a result carries when a run defers, which is the only kind of
   run anyone resumes. `r["status"]` raised `Missing map key`.
2. That exception was swallowed by a bare `except Exception: return None`, and
   the caller turned `None` into **"Unknown graph"** — for a run the store lists,
   whose state file is on disk. The real cause never surfaced, which is why this
   survived releases.
3. Module top-level side effects repeat on every rebuild.

(3) is a design decision rather than a bug and is documented, not fixed here —
see `WorkflowRebuildTopLevelEffectsTests` for what is actually true.
"""

import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, "C:/dev/Coding Language/src")

from nodus.cli import cli as nodus_cli  # noqa: E402
from nodus.orchestration.task_graph import WorkflowRebuildError  # noqa: E402
from nodus.vm.vm import VM  # noqa: E402
from nodus_lang_workflow.runner import retry_sweeper  # noqa: E402


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODUS_PY = os.path.join(REPO_ROOT, "nodus.py")


def _cli(argv, cwd, env_extra=None) -> tuple[int, str]:
    """Run the CLI in a **subprocess**, which is the whole point here.

    These defects are cross-process: the run happens in one process and the
    resume in another, so the resume has nothing in memory and must rebuild the
    graph from persisted source. In-process the `ModuleLoader` cache returns the
    module from the first run and the rebuild never re-executes anything — an
    in-process version of these tests passes without exercising the code under
    test at all. That was the first draft, and it passed against the unfixed
    code.
    """
    env = dict(os.environ)
    env["PYTHONPATH"] = os.path.join(REPO_ROOT, "src")
    env.pop("NODUS_REBUILD_EFFECTS", None)
    env.update(env_extra or {})
    proc = subprocess.run(
        [sys.executable, NODUS_PY, *argv[1:]],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return proc.returncode, proc.stdout + proc.stderr


class _TempProject:
    """Scratch project root, so runs land in its store and not the repo's (#380)."""

    def __enter__(self):
        self._td = tempfile.TemporaryDirectory()
        self.root = self._td.__enter__()
        self._ctx = nodus_cli._project_root_context(self.root)
        self._ctx.__enter__()
        return self

    def __exit__(self, *exc):
        self._ctx.__exit__(*exc)
        return self._td.__exit__(*exc)

    def write(self, name: str, source: str) -> str:
        path = os.path.join(self.root, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(source)
        return path

    def read(self, name: str) -> str:
        path = os.path.join(self.root, name)
        if not os.path.exists(path):
            return ""
        with open(path, encoding="utf-8") as handle:
            return handle.read()


# The shape `docs/guide/` teaches: assign the result, then read it. Reading
# `status` is what a caller does to find out the run is waiting at all.
READS_RESULT = r"""
workflow w {
    step a { return workflow_wait("approval", "k1") }
    step b after a { return "done" }
}
let r = run_workflow(w)
print("graph_id=\(r["graph_id"]) status=\(r["status"])")
"""


def _graph_id_from(out: str) -> str:
    for line in out.splitlines():
        if line.startswith("graph_id="):
            return line.split("graph_id=")[1].split(" ")[0]
    raise AssertionError(f"no graph_id in output: {out!r}")


# closes: #399
class ResumeAfterReadingTheResultTests(unittest.TestCase):
    """Defect 1 — the common case, not an edge case."""

    def test_resume_succeeds_when_the_script_reads_status(self):
        with _TempProject() as project:
            path = project.write("wait1.nd", READS_RESULT)
            rc, out = _cli(["nodus", "run", path], project.root)
            self.assertEqual(rc, 0, out)
            self.assertIn("status=waiting", out)
            graph_id = _graph_id_from(out)


            rc, out = _cli(["nodus", "workflow", "resume", graph_id], project.root)
        self.assertEqual(rc, 0, out)
        self.assertNotIn("Unknown graph", out)
        self.assertIn('"b": "done"', out)

    def test_suppressed_result_covers_every_shape_run_task_graph_returns(self):
        """The drift guard.

        `_suppressed_flow_result` hardcodes a key list that has to stay in step
        with the real result shapes, and nothing enforced that — which is how
        `status` went missing. Generate the real shapes and require the
        placeholder to cover all of them, so adding a result key without adding it
        there fails here instead of breaking resume in the field.
        """
        placeholder = set(VM([], {}, code_locs=[], source_path=None)._suppressed_flow_result())

        completed = """
workflow w { step a { return 1i } }
"""
        waiting = """
workflow w { step a { return workflow_wait("e", "k") } }
"""
        failing = """
workflow w { step a { throw "boom" } }
"""
        retrying = """
workflow w { step a with { retries: 1, retry_delay_ms: 1 } { throw "boom" } }
"""
        goal_src = """
goal g { step a { return 1i } }
"""

        seen: dict[str, set] = {}
        with _TempProject():
            for label, src, kind in (
                ("completed", completed, "workflow"),
                ("waiting", waiting, "workflow"),
                ("failed", failing, "workflow"),
                ("goal", goal_src, "goal"),
            ):
                vm = VM([], {}, code_locs=[], source_path=None)
                seen[label] = set(self._run_flow(vm, src, kind))
            # retry_scheduled only exists while a sweeper is registered (#392).
            with retry_sweeper():
                vm = VM([], {}, code_locs=[], source_path=None)
                seen["retry_scheduled"] = set(self._run_flow(vm, retrying, "workflow"))

        for label, keys in seen.items():
            missing = keys - placeholder
            self.assertEqual(
                missing,
                set(),
                f"_suppressed_flow_result() is missing {sorted(missing)}, which a "
                f"{label!r} result carries. A script reading one of those keys "
                f"cannot be resumed (#399).",
            )
        # Guard the guard: if these shapes stop producing the deferral keys, the
        # assertion above passes vacuously.
        self.assertIn("status", seen["waiting"])
        self.assertIn("wait", seen["waiting"])
        self.assertIn("status", seen["retry_scheduled"])
        self.assertIn("retry", seen["retry_scheduled"])
        self.assertIn("error", seen["failed"])

    def _run_flow(self, vm, src, kind):
        from nodus.runtime.module_loader import ModuleLoader
        from nodus.orchestration.workflow_lowering import find_goal_value, find_workflow_value

        loader = ModuleLoader(project_root=None)
        code, functions, code_locs = loader.compile_only(src, module_name="t.nd")
        vm = VM(code, functions, code_locs=code_locs, source_path="t.nd")
        vm.run()
        if kind == "goal":
            return vm.builtin_run_goal(find_goal_value(vm.globals, "g"))
        return vm.builtin_run_workflow(find_workflow_value(vm.globals, "w"))


# The rebuild re-executes module top level, so a top level that throws on its
# SECOND execution is a reliable, purely-public way to make a rebuild fail.
FAILS_ON_REBUILD = r"""
import "std:fs" as fs
if (fs.exists("once.txt")) { throw "module top level ran a second time" }
fs.write("once.txt", "1")
workflow w {
    step a { return workflow_wait("approval", "k1") }
    step b after a { return "done" }
}
let r = run_workflow(w)
print("graph_id=\(r["graph_id"]) status=\(r["status"])")
"""


# closes: #399
class RebuildFailureIsDiagnosedTests(unittest.TestCase):
    """Defect 2 — "Unknown graph" was the wrong answer to a different question."""

    def test_rebuild_failure_reports_its_cause_and_differs_from_unknown(self):
        # One run + one resume + one bogus resume. Deliberately a single test
        # rather than two: each CLI call is a subprocess, and this file's
        # subprocess load already pushed `test_len_returns_int`'s 10s subprocess
        # timeout over the edge in a full-suite run.
        with _TempProject() as project:
            path = project.write("once.nd", FAILS_ON_REBUILD)
            rc, out = _cli(["nodus", "run", path], project.root)
            self.assertEqual(rc, 0, out)
            self.assertIn("status=waiting", out)
            graph_id = _graph_id_from(out)

            rebuild_rc, rebuild_out = _cli(["nodus", "workflow", "resume", graph_id], project.root)
            unknown_rc, unknown_out = _cli(
                ["nodus", "workflow", "resume", "g_doesnotexist"], project.root
            )

        # #920: both are failures the runner reports as an inner `ok: false`,
        # and both exited 0 -- a cron job checking the code was told it worked.
        self.assertEqual(1, rebuild_rc, rebuild_out)
        self.assertEqual(1, unknown_rc, unknown_out)

        # Before #399 this said exactly: {"ok": false, "error": "Unknown graph"} —
        # for a run the store lists as waiting, with its state file on disk.
        self.assertNotIn("Unknown graph", rebuild_out)
        self.assertIn("Could not rebuild", rebuild_out)
        self.assertIn("workflow_rebuild_failed", rebuild_out)
        self.assertIn(graph_id, rebuild_out)
        # The actual cause, which the bare `except Exception: return None` ate.
        self.assertIn("module top level ran a second time", rebuild_out)

        # A rebuild failure and a nonexistent id must not collapse into one
        # message. Only the difference is asserted, not the unknown-id wording —
        # that message is itself wrong ("is already claimed") and is #425.
        self.assertNotIn("workflow_rebuild_failed", unknown_out)
        self.assertNotEqual(rebuild_out.strip(), unknown_out.strip())

    def test_rebuild_error_describe_includes_the_cause(self):
        err = WorkflowRebuildError("rebuilding failed", cause=ValueError("boom"))
        self.assertEqual(err.describe(), "rebuilding failed: ValueError: boom")
        self.assertEqual(WorkflowRebuildError("plain").describe(), "plain")


# closes: #399
class WorkflowRebuildTopLevelEffectsTests(unittest.TestCase):
    """Defect 3, which this file first recorded as measured and not fixed.

    Rebuilding re-executes the module to re-bind its definitions, so a side
    effect at module top level ran again once per resume, on completed runs too.
    5.16.0 warned about it (#917), and since 6.0.0 the rebuild refuses it: the
    resume fails, naming the call, and does not repeat it. The run is left as it
    was, so it can still go through once an operator allows it, which a run
    stored before its program was fixed needs. That is `NODUS_REBUILD_EFFECTS`,
    the one override every resume path reads.
    """

    SIDE_EFFECT = r"""
import "std:fs" as fs
let prev = fs.exists("counter.txt")
if (prev) { fs.write("counter.txt", fs.read("counter.txt") + "X") }
if (!prev) { fs.write("counter.txt", "X") }
workflow w {
    step a { return workflow_wait("approval", "k1") }
    step b after a { return "done" }
}
let r = run_workflow(w)
print("graph_id=\(r["graph_id"]) status=\(r["status"])")
"""

    def test_a_resume_refuses_the_top_level_effect_and_leaves_the_run(self):
        with _TempProject() as project:
            path = project.write("eff.nd", self.SIDE_EFFECT)
            rc, out = _cli(["nodus", "run", path], project.root)
            self.assertEqual(rc, 0, out)
            graph_id = _graph_id_from(out)
            self.assertEqual(project.read("counter.txt"), "X")

            rc, out = _cli(["nodus", "workflow", "resume", graph_id], project.root)
            self.assertEqual(rc, 1, out)
            self.assertIn("`write_file`", out)
            self.assertIn("eff.nd:4:", out)
            self.assertIn("NODUS_REBUILD_EFFECTS=allow", out)
            self.assertEqual(project.read("counter.txt"), "X", "the refused write ran")

            # The run was left waiting, so the override still reaches it, on a
            # path that takes no mode of its own.
            rc, out = _cli(["nodus", "workflow", "resume", graph_id], project.root,
                           {"NODUS_REBUILD_EFFECTS": "allow"})
            self.assertEqual(rc, 0, out)
            self.assertIn('"b": "done"', out)
            self.assertEqual(project.read("counter.txt"), "XX")


if __name__ == "__main__":
    unittest.main()
