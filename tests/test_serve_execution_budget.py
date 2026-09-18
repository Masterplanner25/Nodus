"""The budget submitted programs run under is settable, and a breach returns (#857, #862).

#857: every `RuntimeService` endpoint ran submitted code at the CLI's 200 ms
default, at eight runner call sites, and nothing could raise it -- no `serve`
flag, no payload key, no env. A workflow that made one real HTTP call fit or
timed out by how many instructions followed the call. `serve --time-limit
SECS` is the ceiling now, a request may ask for less with `timeout_ms`, and
`_budget()` is the one place the answer comes from.

#862, found while testing #857: under a service a step that exceeded the
budget never returned. Worker mode runs each step on a thread through
`dispatcher.submit`, and the deadline's `RuntimeLimitExceeded` came out of
that call *above* the try/finally that decrements `active_workers` -- the
thread died counted, and the request thread waited on `worker_cond` forever.
`while (true)` in a step was a one-line denial of service. Raising the budget
without that fix would have made every timeout a hang.

Also fixed on the way: the hidden legacy `workflow-run --time-limit` passed
seconds through as milliseconds, so `--time-limit 30` was a 30 ms budget.
`workflow run` and `goal-run` had no flag at all.
"""

import os
import pathlib
import re
import subprocess
import sys
import tempfile
import threading
import unittest

REPO = pathlib.Path(__file__).resolve().parents[1]
SRC = REPO / "src"
NODUS_PY = REPO / "nodus.py"
sys.path.insert(0, str(SRC))

from nodus.cli.commands import flags_for  # noqa: E402
from nodus.services.server import RuntimeService  # noqa: E402

# Past 200 ms on any box this suite runs on; well inside 30 s.
SLOW_STEP = (
    "workflow w {\n"
    "    step a {\n"
    "        let n = 0\n"
    "        while (n < 300000) { n = n + 1 }\n"
    "        return n\n"
    "    }\n"
    "}\n"
)
INFINITE_STEP = "workflow w { step a { while (true) { let x = 1 }\n return 1 } }\n"
SLOW_GOAL = SLOW_STEP.replace("workflow w", "goal g")

HANG_GUARD_SECONDS = 60


def _bounded(fn):
    """Run `fn` on a daemon thread; fail rather than hang if it never returns.

    The defect this guards against is a request that never returns, and a
    test that never returns is not a red test. The thread is daemon so a hung
    worker cannot pin the process.
    """
    out: dict = {}

    def run():
        try:
            out["value"] = fn()
        except BaseException as exc:  # noqa: BLE001
            out["error"] = exc

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(HANG_GUARD_SECONDS)
    if t.is_alive():
        raise AssertionError(f"call did not return within {HANG_GUARD_SECONDS}s (#862: the request hung)")
    if "error" in out:
        raise out["error"]
    return out["value"]


class _ServiceCase(unittest.TestCase):
    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory(prefix="nodus857-")
        os.chdir(self._tmp.name)
        self._services = []

    def tearDown(self):
        for svc in self._services:
            svc.close()
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def service(self, **kwargs):
        svc = RuntimeService(**kwargs)
        self._services.append(svc)
        return svc


# closes: #862
class ABreachReturnsTests(_ServiceCase):

    def test_a_step_past_the_default_budget_times_out_instead_of_hanging(self):
        svc = self.service()
        r = _bounded(lambda: svc.workflow_run({"code": INFINITE_STEP, "filename": "w.nd"}))
        self.assertFalse(r["ok"])
        self.assertIn("Execution timed out", r["error"]["message"])

    def test_a_goal_step_past_the_budget_times_out_too(self):
        svc = self.service()
        r = _bounded(lambda: svc.goal_run({"code": INFINITE_STEP.replace("workflow w", "goal g"), "filename": "g.nd"}))
        self.assertFalse(r["ok"])
        self.assertIn("Execution timed out", r["error"]["message"])

    def test_the_service_still_answers_afterwards(self):
        """A breach must not leave the worker accounting wedged for the next request."""
        svc = self.service()
        _bounded(lambda: svc.workflow_run({"code": INFINITE_STEP, "filename": "w.nd"}))
        r = _bounded(lambda: svc.workflow_run({"code": "workflow w { step a { return 1i } }", "filename": "w.nd"}))
        self.assertTrue(r["ok"], r.get("error"))


# closes: #857
class TheBudgetIsSettableTests(_ServiceCase):

    def test_the_default_is_the_cli_default_and_the_slow_step_does_not_fit(self):
        svc = self.service()
        r = _bounded(lambda: svc.workflow_run({"code": SLOW_STEP, "filename": "w.nd"}))
        self.assertFalse(r["ok"])
        self.assertIn("Execution timed out", r["error"]["message"])

    def test_a_server_ceiling_lets_the_slow_step_finish(self):
        svc = self.service(timeout_ms=30_000)
        r = _bounded(lambda: svc.workflow_run({"code": SLOW_STEP, "filename": "w.nd"}))
        self.assertTrue(r["ok"], r.get("error"))
        self.assertEqual(r["result"]["steps"], {"a": 300000.0})

    def test_the_ceiling_reaches_goal_run_too(self):
        svc = self.service(timeout_ms=30_000)
        r = _bounded(lambda: svc.goal_run({"code": SLOW_GOAL, "filename": "g.nd"}))
        self.assertTrue(r["ok"], r.get("error"))

    def test_a_request_may_ask_for_less(self):
        svc = self.service(timeout_ms=30_000)
        r = _bounded(lambda: svc.workflow_run({"code": SLOW_STEP, "filename": "w.nd", "timeout_ms": 50}))
        self.assertFalse(r["ok"])
        self.assertIn("Execution timed out", r["error"]["message"])

    def test_a_request_may_not_ask_for_more(self):
        """The operator's setting is the ceiling. A payload asking for 60 s on
        a 100 ms server gets 100 ms."""
        svc = self.service(timeout_ms=100)
        r = _bounded(lambda: svc.workflow_run({"code": SLOW_STEP, "filename": "w.nd", "timeout_ms": 60_000}))
        self.assertFalse(r["ok"])
        self.assertIn("Execution timed out", r["error"]["message"])

    def test_execute_honours_a_request_budget(self):
        svc = self.service(timeout_ms=30_000)
        r = _bounded(lambda: svc.execute({"code": "while (true) { let x = 1 }", "filename": "e.nd", "timeout_ms": 100}))
        self.assertFalse(r["ok"])
        self.assertIn("Execution timed out", r["error"]["message"])

    def test_a_malformed_timeout_is_refused_not_ignored(self):
        """#490's rule: a declaration the runtime accepts must bind. Silently
        running at the default would be #791's shape -- a value typed to have
        an effect, and dropped."""
        svc = self.service(timeout_ms=30_000)
        for bad in ("x", -1, 0, True, 2.5e-9):
            with self.subTest(timeout_ms=bad):
                r = svc.workflow_run({"code": "workflow w { step a { return 1i } }", "filename": "w.nd", "timeout_ms": bad})
                self.assertFalse(r["ok"])
                self.assertIn("timeout_ms must be a positive number", r["error"]["message"])
        # The refusal happens before anything runs.
        r = svc.execute({"code": 'print("ran")', "filename": "e.nd", "timeout_ms": "x"})
        self.assertFalse(r["ok"])
        self.assertNotIn("ran", r.get("stdout", ""))


class EveryRunnerCallCarriesTheBudgetTests(unittest.TestCase):
    """Assert on the source. Eight call sites answered "what budget does this
    run under" by omission; a ninth added without `timeout_ms=` would run at
    the default again and no behaviour test would know which route to try."""

    SERVER_SRC = (SRC / "nodus" / "services" / "server.py").read_text(encoding="utf-8")
    RUNNER_CALL = re.compile(r"\b(run_in_vm|run_graph_code|run_workflow_code|plan_workflow_code|run_goal_code|plan_goal_code)\((?P<args>[^;]*?)\)\n", re.S)

    def test_every_runner_call_in_the_service_passes_timeout_ms(self):
        calls = list(self.RUNNER_CALL.finditer(self.SERVER_SRC))
        self.assertGreaterEqual(len(calls), 8, "expected the eight runner call sites")
        missing = [m.group(0).strip()[:70] for m in calls if "timeout_ms=" not in m.group("args")]
        self.assertEqual(missing, [], f"runner calls without a budget: {missing}")

    def test_the_budget_is_computed_in_one_place(self):
        self.assertEqual(self.SERVER_SRC.count("def _budget(self, payload"), 1)
        # No call site reads the payload's timeout_ms for itself.
        self.assertEqual(self.SERVER_SRC.count('payload.get("timeout_ms")'), 1)


# closes: #857
class CliTimeLimitTests(unittest.TestCase):

    def _run(self, *argv, cwd):
        return subprocess.run(
            [sys.executable, str(NODUS_PY), *argv],
            capture_output=True, text=True, timeout=180, cwd=cwd,
            env={"PYTHONPATH": str(SRC), "SYSTEMROOT": "C:\\Windows", "PATH": ""},
        )

    def test_workflow_run_takes_time_limit_in_seconds(self):
        with tempfile.TemporaryDirectory(prefix="nodus857-") as tmp:
            path = pathlib.Path(tmp) / "w.nd"
            path.write_text(SLOW_STEP, encoding="utf-8")
            without = self._run("workflow", "run", str(path), cwd=tmp)
            with_limit = self._run("workflow", "run", str(path), "--time-limit", "30", cwd=tmp)
            legacy = self._run("workflow-run", str(path), "--time-limit", "30", cwd=tmp)
        self.assertNotEqual(without.returncode, 0)
        self.assertIn("Execution timed out", without.stderr + without.stdout)
        self.assertEqual(with_limit.returncode, 0, with_limit.stderr)
        # Before #857 the legacy form took the value as *milliseconds*: 30 ms.
        self.assertEqual(legacy.returncode, 0, legacy.stderr)

    def test_goal_run_takes_time_limit(self):
        with tempfile.TemporaryDirectory(prefix="nodus857-") as tmp:
            path = pathlib.Path(tmp) / "g.nd"
            path.write_text(SLOW_GOAL, encoding="utf-8")
            proc = self._run("goal-run", str(path), "--time-limit", "30", cwd=tmp)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_serve_declares_the_flag(self):
        with_values, _ = flags_for("serve")
        self.assertIn("--time-limit", with_values)


if __name__ == "__main__":
    unittest.main()
