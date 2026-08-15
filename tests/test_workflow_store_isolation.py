"""Workflow runs must not accumulate in the working tree (#380).

`LocalWorkflowStore.list_runs()` parses every file in
`.nodus/workflow_framework/runs/` on every call — ~1.3 ms each, linear to 10,000
files (13.5 s). The default store root is CWD-relative, so the suite and the doc
gate wrote there on every run and never cleaned up. At 299 accumulated files a
single scan costs 540 ms, past the 500 ms sweep interval deadline-sensitive tests
assume, and the suite started failing intermittently in places with no visible
connection to each other.

Two mechanisms are covered here:

- `NODUS_WORKFLOW_STORE_ROOT` relocates the default store, which is what the doc
  gate uses for throwaway runs (and what a host with a read-only working
  directory would use).
- the gate's runtime phase actually sets it, and puts the environment back.

The third mechanism — the session fixture in `conftest.py` that deletes what a
pytest run added — cannot meaningfully assert on itself from inside the session
it is cleaning. Its effect is checked the way it was found: run the suite, then
count the directory.
"""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))  # noqa: E402
sys.path.insert(0, str(_REPO_ROOT))  # noqa: E402

from nodus_lang_workflow.runner import default_store_root  # noqa: E402
from tools.nodus_gate.runtime_phase import (  # noqa: E402
    _WORKFLOW_STORE_ENV,
    RuntimeResult,
)

_REPO_RUNS = _REPO_ROOT / ".nodus" / "workflow_framework" / "runs"


def _repo_run_files() -> set[str]:
    return {p.name for p in _REPO_RUNS.iterdir()} if _REPO_RUNS.is_dir() else set()


class DefaultStoreRootTests(unittest.TestCase):
    def setUp(self):
        self._saved = os.environ.get(_WORKFLOW_STORE_ENV)
        os.environ.pop(_WORKFLOW_STORE_ENV, None)

    def tearDown(self):
        if self._saved is None:
            os.environ.pop(_WORKFLOW_STORE_ENV, None)
        else:
            os.environ[_WORKFLOW_STORE_ENV] = self._saved

    def test_default_is_cwd_relative(self):
        self.assertEqual(os.path.join(".nodus", "workflow_framework"),
                         default_store_root())

    def test_env_var_overrides_it(self):
        os.environ[_WORKFLOW_STORE_ENV] = "/somewhere/else"
        self.assertEqual("/somewhere/else", default_store_root())

    def test_blank_env_var_is_ignored(self):
        os.environ[_WORKFLOW_STORE_ENV] = "   "
        self.assertEqual(os.path.join(".nodus", "workflow_framework"),
                         default_store_root())


# closes: #380
class RunsGoWhereTheOverrideSaysTests(unittest.TestCase):
    def test_a_workflow_run_writes_outside_the_repo(self):
        # End-to-end through the CLI, with the repo as CWD — the exact shape that
        # was filling `.nodus/` — and assert nothing lands there.
        source = (
            "workflow demo {\n"
            '    step a { print("ran") }\n'
            "}\n"
            "run_workflow(demo)\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "wf.nd"
            script.write_text(source, encoding="utf-8")
            store = Path(tmp) / "store"

            before = _repo_run_files()
            env = {
                "PYTHONPATH": str(_REPO_ROOT / "src"),
                "SYSTEMROOT": "C:\\Windows",
                "PATH": "",
                _WORKFLOW_STORE_ENV: str(store),
            }
            proc = subprocess.run(
                [sys.executable, str(_REPO_ROOT / "nodus.py"), "run", str(script)],
                capture_output=True, text=True, timeout=60,
                cwd=str(_REPO_ROOT), env=env,
            )
            self.assertEqual(0, proc.returncode, proc.stderr)
            self.assertIn("ran", proc.stdout)

            self.assertEqual(before, _repo_run_files(),
                             "the run wrote into the repo despite the override")
            self.assertTrue((store / "runs").is_dir(),
                            f"nothing written to the override root: {store}")


# closes: #380
class GateIsolatesItsOwnRunsTests(unittest.TestCase):
    def test_runtime_phase_sets_and_restores_the_override(self):
        import tools.nodus_gate.runtime_phase as phase

        seen: dict = {}
        original = phase._run_blocks

        def _capture(result, root, **kwargs):
            seen["root"] = os.environ.get(_WORKFLOW_STORE_ENV)
            return result

        phase._run_blocks = _capture
        outer_before = os.environ.get(_WORKFLOW_STORE_ENV)
        try:
            phase.run_runtime_phase(str(_REPO_ROOT))
        finally:
            phase._run_blocks = original

        self.assertIsNotNone(seen.get("root"), "blocks ran without an override")
        self.assertNotIn(str(_REPO_ROOT), seen["root"],
                         "the gate's store root is inside the repo")
        self.assertEqual(outer_before, os.environ.get(_WORKFLOW_STORE_ENV),
                         "the gate left the environment modified")

    def test_result_is_returned_unchanged(self):
        # The refactor that added the isolation split the phase in two; the
        # return value has to survive that.
        import tools.nodus_gate.runtime_phase as phase

        marker = RuntimeResult()
        marker.scanned_files = 4242
        original = phase._run_blocks
        phase._run_blocks = lambda result, root, **kwargs: marker
        try:
            self.assertIs(marker, phase.run_runtime_phase(str(_REPO_ROOT)))
        finally:
            phase._run_blocks = original


if __name__ == "__main__":
    unittest.main()
