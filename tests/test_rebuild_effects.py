"""#917: a top-level effect re-run by a rebuild is reported now, refused at 6.0.0.

A rebuild (workflow resume, sweep, durable coroutine resume) re-runs a program's
stored source to re-bind its definitions. Since #909 it skips `main()` and the
scheduling builtins. Anything else at the top level that reaches outside the
program (a file write, a request, a subprocess, a host function) happened
again, silently, on every rebuild.

`nodus.runtime.rebuild_effects` decides what happens instead, from the two
chokepoints a call outside the program goes through. In mode `warn`, the default
for now, it reports each one with its line. In `refuse`, the 6.0.0 default, it
raises. In `allow`, the operator's override for a run whose stored source
predates the fix, it lets the call through. Reads are not effects; host
functions are, unless registered `rebuild_safe=True`.
"""

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
import warnings
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))  # noqa: E402

from nodus.orchestration.task_graph import WorkflowRebuildError  # noqa: E402
from nodus.runtime.capability import BUILTIN_CAPABILITIES, ENV  # noqa: E402
from nodus.runtime.durable import run_id_for  # noqa: E402
from nodus.runtime.embedding import NodusRuntime  # noqa: E402
from nodus.runtime.rebuild_effects import (  # noqa: E402
    DEFAULT_REBUILD_EFFECTS,
    EFFECT_CAPABILITIES,
    READ_CAPABILITIES,
    is_rebuild_effect,
)
from nodus.support.staging import StagedFlipWarning  # noqa: E402
from nodus.vm.vm import VM  # noqa: E402
from nodus_lang_workflow.models import RUN_STATUS_COMPLETED  # noqa: E402
from nodus_lang_workflow.runner import WorkflowFrameworkRunner  # noqa: E402
from nodus_lang_workflow.store import SQLiteWorkflowStore  # noqa: E402


class TheClassificationTests(unittest.TestCase):

    def test_every_capability_is_an_effect_or_a_read(self):
        """A capability added later and classified as neither would be treated as
        a read by default, silently. So each one must be put in a set."""
        for capability in sorted(set(BUILTIN_CAPABILITIES.values())):
            with self.subTest(capability):
                placed = (capability in EFFECT_CAPABILITIES) + (capability in READ_CAPABILITIES) + (capability == ENV)
                self.assertEqual(1, placed, f"{capability!r} is not classified exactly once")

    def test_the_decisions(self):
        cases = {
            "write_file": True, "fs_delete": True, "http_get": True, "http_post": True,
            "subprocess_run": True, "env_set": True, "env_unset": True, "memory_put": True,
            "agent_call": True, "tool_call": True, "syscall": True,
            "read_file": False, "list_dir": False, "env_get": False, "env_has": False,
            "memory_get": False, "len": False, "print": False,
        }
        for name, effect in cases.items():
            with self.subTest(name):
                self.assertEqual(effect, is_rebuild_effect(name))

    def test_the_default_is_warn_until_the_major(self):
        self.assertEqual("warn", DEFAULT_REBUILD_EFFECTS)


def _rebuild(source: str, mode: str | None = None):
    """Rebuild `source` on a fresh VM; return (warnings, error)."""
    vm = VM([], {}, code_locs=[], source_path=None)
    if mode is not None:
        vm.rebuild_effects = mode
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            vm.reexecute_source_for_resume(source, None, what="test")
            error = None
        except WorkflowRebuildError as err:
            error = err.describe()
    return [str(w.message) for w in caught if issubclass(w.category, StagedFlipWarning)], error


class ABuiltinEffectTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        (self.dir / "cfg.txt").write_text("cfg", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def _program(self, write_line: str) -> str:
        cfg = json.dumps(str(self.dir / "cfg.txt"))
        out = json.dumps(str(self.dir / "out.txt"))
        main_out = json.dumps(str(self.dir / "main.txt"))
        return (f'import "std:fs" as fs\n'
                f'let cfg = read_file({cfg})\n'
                f'{write_line.format(out=out)}\n'
                f'fn main() {{ write_file({main_out}, "x") }}\n'
                f'main()\n')

    # closes: #917
    def test_warn_reports_the_effect_with_its_line_and_still_runs_it(self):
        reported, error = _rebuild(self._program('write_file({out}, "again")'))
        self.assertIsNone(error)
        self.assertEqual(1, len(reported), reported)
        self.assertIn("builtin `write_file` at <memory>:3:", reported[0])
        self.assertIn("In 6.0.0 this is refused", reported[0])
        self.assertIn("fn main()", reported[0])
        self.assertTrue((self.dir / "out.txt").exists(), "warn changed behaviour")
        # The read was not reported, and `main` was skipped (#909).
        self.assertFalse((self.dir / "main.txt").exists())

    def test_an_effect_through_a_stdlib_wrapper_is_caught_too(self):
        """`fs.write` runs `write_file` on a per-call child VM. The rebuild is
        the root VM's, so the decision reads the root."""
        reported, error = _rebuild(self._program('fs.write({out}, "again")'))
        self.assertIsNone(error)
        self.assertEqual(1, len(reported), reported)
        self.assertIn("`write_file`", reported[0])

    def test_refuse_raises_at_the_call_and_does_not_run_it(self):
        reported, error = _rebuild(self._program('write_file({out}, "again")'), "refuse")
        self.assertIsNotNone(error)
        self.assertIn("builtin `write_file` at <memory>:3:", error)
        self.assertIn('rebuild_effects="allow"', error)
        self.assertFalse((self.dir / "out.txt").exists())

    def test_allow_lets_it_run_silently(self):
        reported, error = _rebuild(self._program('write_file({out}, "again")'), "allow")
        self.assertIsNone(error)
        self.assertEqual([], reported)
        self.assertTrue((self.dir / "out.txt").exists())

    def test_outside_a_rebuild_nothing_is_reported(self):
        out = json.dumps(str(self.dir / "plain.txt"))
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = NodusRuntime(timeout_ms=None, max_steps=None,
                                  allowed_paths=[str(self.dir)]).run_source(
                f'write_file({out}, "x")\n')
        self.assertTrue(result.get("ok"), result)
        self.assertEqual([], [w for w in caught if issubclass(w.category, StagedFlipWarning)])


_SIDE = textwrap.dedent("""
    import os, sys
    sys.path.insert(0, {src!r})
    from nodus.runtime.embedding import NodusRuntime
    from nodus_lang_workflow.runner import WorkflowFrameworkRunner
    from nodus_lang_workflow.store import SQLiteWorkflowStore
    runner = WorkflowFrameworkRunner(SQLiteWorkflowStore(os.environ["DURABLE_DB"], claim_ttl_ms=200.0))
    rt = NodusRuntime(timeout_ms=None, max_steps=None, workflow_runner=runner)
    rt.register_function("load_config", lambda: "cfg", rebuild_safe=True)
    rt.register_function("record_visit", lambda: None)
    rt.register_function("crash", lambda: os._exit(3))
    rt.run_source({program!r})
    os._exit(4)
""")

_HOSTED = """
let cfg = load_config()
record_visit()
fn job() {
    checkpoint "half"
    crash()
    return cfg
}
durable_spawn("hosted", job, [])
run_loop()
"""


class AHostFunctionEffectTests(unittest.TestCase):
    """Through `runtime.sweep()`, after a real crash: an unmarked host function
    at the top level is the effect; one registered `rebuild_safe` is not."""

    def _crashed(self, tmp: Path) -> SQLiteWorkflowStore:
        env = dict(os.environ, DURABLE_DB=str(tmp / "runs.db"))
        proc = subprocess.run(
            [sys.executable, "-c", _SIDE.format(src=str(REPO / "src"), program=_HOSTED)],
            env=env, cwd=str(tmp), capture_output=True, text=True, timeout=120)
        self.assertEqual(3, proc.returncode, proc.stderr[-1500:])
        time.sleep(0.4)
        return SQLiteWorkflowStore(str(tmp / "runs.db"), claim_ttl_ms=200.0)

    def _sweeper(self, store, visits: list) -> NodusRuntime:
        rt = NodusRuntime(timeout_ms=None, max_steps=None,
                          workflow_runner=WorkflowFrameworkRunner(store))
        rt.register_function("load_config", lambda: "cfg", rebuild_safe=True)
        rt.register_function("record_visit", lambda: visits.append(1))
        rt.register_function("crash", lambda: None)
        return rt

    def test_warn_names_the_unmarked_one_and_only_that_one(self):
        visits = []
        with tempfile.TemporaryDirectory() as raw:
            store = self._crashed(Path(raw))
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                report = self._sweeper(store, visits).sweep()
            record = store.get_run(run_id_for("hosted"))
        reported = [str(w.message) for w in caught if issubclass(w.category, StagedFlipWarning)]
        self.assertEqual(1, len(reported), reported)
        self.assertIn("host function `record_visit`", reported[0])
        self.assertIn("rebuild_safe=True", reported[0])
        self.assertEqual([1], visits, "warn changed behaviour")
        self.assertTrue(report["resumed_coroutines"][0]["ok"])
        self.assertEqual(RUN_STATUS_COMPLETED, record.status)

    def test_refuse_stops_the_resume_and_allow_lets_it_through(self):
        with tempfile.TemporaryDirectory() as raw:
            store = self._crashed(Path(raw))
            visits = []
            refused = self._sweeper(store, visits).sweep(rebuild_effects="refuse")
            self.assertEqual([], visits)
            (entry,) = refused["resumed_coroutines"]
            self.assertFalse(entry["ok"])
            self.assertIn("host function `record_visit`", entry["error"])
            time.sleep(0.4)
            allowed = self._sweeper(store, visits).sweep(rebuild_effects="allow")
            record = store.get_run(run_id_for("hosted"))
        (entry,) = allowed["resumed_coroutines"]
        self.assertTrue(entry["ok"], entry)
        self.assertEqual([1], visits)
        self.assertEqual(RUN_STATUS_COMPLETED, record.status)

    def test_an_unknown_mode_is_refused_up_front(self):
        with self.assertRaises(ValueError):
            NodusRuntime().sweep(rebuild_effects="sometimes")


class TheCliOverrideTests(unittest.TestCase):

    def _sweep(self, *flags):
        with tempfile.TemporaryDirectory() as raw:
            env = dict(os.environ, NODUS_WORKFLOW_STORE_BACKEND="sqlite",
                       NODUS_RUN_STATE_ROOT=str(Path(raw) / "state"),
                       PYTHONPATH=str(REPO / "src"))
            return subprocess.run(
                [sys.executable, str(REPO / "nodus.py"), "workflow", "sweep", *flags],
                env=env, cwd=raw, capture_output=True, text=True, timeout=120)

    def test_each_mode_is_accepted_and_nonsense_is_not(self):
        for mode in ("warn", "refuse", "allow"):
            with self.subTest(mode):
                self.assertEqual(0, self._sweep("--rebuild-effects", mode).returncode)
        bad = self._sweep("--rebuild-effects", "sometimes")
        self.assertEqual(1, bad.returncode)
        self.assertIn("warn, refuse, allow", bad.stderr)


if __name__ == "__main__":
    unittest.main()
