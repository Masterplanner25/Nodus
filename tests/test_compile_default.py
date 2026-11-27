"""Compile-to-Python is on by default (5.19.0 for `nodus run` and `NodusRuntime`;
after it for `nodus serve`, `nodus test` and the runner the tools layer uses).

It was opt-in for one release (5.17.0, design decision 1 in
`docs/design/throughput/01-compile-to-python.md`), with CI's `compiled` job
green throughout. The switches, and who wins:

- `NODUS_COMPILE_FUNCTIONS`, when set, decides for every VM: `1` (or any true
  value) and `always` turn it on, **anything else turns it off**. That is the
  operator's switch, and what an unrecognised value always meant;
- otherwise the caller's flag: `NodusRuntime(compile_functions=...)`, default
  `True`, and `nodus run --no-compile`.

`pycompile.enabled_for` is the one place that is decided.
"""
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, "C:/dev/Coding Language/src")

from nodus.runtime.embedding import NodusRuntime  # noqa: E402
from nodus.vm import pycompile  # noqa: E402

_REPO = Path(__file__).resolve().parents[1]
_SRC = "fn total(n) {\n    let t = 0i\n    for x in range(0i, n) { t = t + x }\n    return t\n}\nprint(total(100i))\n"


def _embedded(env, **kwargs):
    environ = {"NODUS_COMPILE_FUNCTIONS": env if env is not None else ""}
    with mock.patch.dict(os.environ, environ):
        runtime = NodusRuntime(timeout_ms=None, max_steps=None, **kwargs)
        result = runtime.run_source(_SRC, filename="p.nd")
    assert result.get("ok"), result.get("error")
    state = runtime.active_vm()._pycompile
    return (result["stdout"], runtime.get_execution_stats()["instructions_executed"],
            state.compiled_count if state is not None else 0)


class TheRuntimeCompilesByDefault(unittest.TestCase):
    # closes: #976
    def test_on_with_no_argument(self):
        self.assertEqual(_embedded(None)[2], 1)

    def test_compile_functions_false_turns_it_off(self):
        self.assertEqual(_embedded(None, compile_functions=False)[2], 0)

    def test_the_default_changes_nothing_but_speed(self):
        on, off = _embedded(None), _embedded(None, compile_functions=False)
        self.assertEqual(on[:2], off[:2], "output or instruction count differ")


class TheEnvironmentOverridesEitherWay(unittest.TestCase):
    def test_an_off_value_wins_over_the_default_and_over_true(self):
        for value in ("0", "false", "off", "no", "a typo"):
            for kwargs in ({}, {"compile_functions": True}):
                with self.subTest(value=value, kwargs=kwargs):
                    self.assertEqual(_embedded(value, **kwargs)[2], 0)

    def test_an_on_value_wins_over_false(self):
        for value in ("1", "true", "always"):
            with self.subTest(value=value):
                self.assertEqual(_embedded(value, compile_functions=False)[2], 1)

    def test_empty_means_unset(self):
        with mock.patch.dict(os.environ, {"NODUS_COMPILE_FUNCTIONS": "  "}):
            self.assertIsNone(pycompile.environment_setting())
            self.assertTrue(pycompile.enabled_for(True))
            self.assertFalse(pycompile.enabled_for(False))


# Patches `pycompile.enable` to report on stderr, then runs the real CLI.
_SPY = (
    "import sys, runpy\n"
    "from nodus.vm import pycompile as p\n"
    "real = p.enable\n"
    "def spy(vm, **k):\n"
    "    print('ENABLED', file=sys.stderr)\n"
    "    return real(vm, **k)\n"
    "p.enable = spy\n"
    "sys.argv = ['nodus'] + sys.argv[1:]\n"
    "runpy.run_module('nodus', run_name='__main__')\n"
)


class NodusRunCompilesByDefault(unittest.TestCase):
    def _run(self, flags, env=None, expect=0):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "p.nd").write_text(_SRC, encoding="utf-8")
            environ = dict(os.environ, PYTHONPATH=str(_REPO / "src"))
            environ.pop("NODUS_COMPILE_FUNCTIONS", None)
            if env is not None:
                environ["NODUS_COMPILE_FUNCTIONS"] = env
            proc = subprocess.run([sys.executable, "-c", _SPY, "run", *flags, "p.nd"], cwd=directory,
                                  capture_output=True, text=True, env=environ, timeout=120)
        self.assertEqual(proc.returncode, expect, proc.stderr)
        if expect:
            return proc.stderr
        self.assertEqual(proc.stdout.strip(), "4950")
        return "ENABLED" in proc.stderr

    def test_on_with_no_flag(self):
        self.assertTrue(self._run([]))

    def test_no_compile_turns_it_off(self):
        self.assertFalse(self._run(["--no-compile"]))

    def test_compile_is_still_accepted(self):
        self.assertTrue(self._run(["--compile"]))

    def test_both_together_are_refused(self):
        self.assertIn("contradict", self._run(["--compile", "--no-compile"], expect=2))

    def test_the_environment_wins_over_the_cli_default(self):
        self.assertFalse(self._run([], env="0"))


class OnePlaceDecides(unittest.TestCase):
    """Asserted on the source, since a behaviour test passes on whichever path
    is already right."""

    def test_every_enable_is_guarded_by_enabled_for(self):
        sites = []
        for path in (_REPO / "src" / "nodus").rglob("*.py"):
            if path.name == "pycompile.py":
                continue
            text = path.read_text(encoding="utf-8-sig")
            for match in re.finditer(r"pycompile\.enable\(", text):
                window = text[max(0, match.start() - 300):match.start()]
                sites.append((path.relative_to(_REPO).as_posix(), "enabled_for(" in window))
        self.assertEqual(sorted(sites), [("src/nodus/runtime/embedding.py", True),
                                         ("src/nodus/services/server.py", True),
                                         ("src/nodus/testing/cli.py", True),
                                         ("src/nodus/tooling/runner.py", True)])

    def test_the_runtime_default_is_true(self):
        import inspect
        default = inspect.signature(NodusRuntime.__init__).parameters["compile_functions"].default
        self.assertIs(default, True)


class EveryEntryPointCompilesByDefault(unittest.TestCase):
    """`nodus serve`, `nodus test` and the shared runner, after `nodus run` and
    `NodusRuntime`. Each still yields to the environment, and an observer
    (a profiler, coverage) keeps compilation off."""

    def _runner(self, env=None, **kwargs):
        from nodus.tooling.runner import run_source
        with mock.patch.dict(os.environ, {"NODUS_COMPILE_FUNCTIONS": env or ""}):
            result, vm = run_source(_SRC, filename=None, max_steps=None, timeout_ms=None, **kwargs)
        self.assertTrue(result.get("ok"), result)
        return vm._pycompile

    def test_the_runner(self):
        self.assertIsNotNone(self._runner())
        self.assertIsNone(self._runner(compile_functions=False))
        self.assertIsNone(self._runner(env="0"))

    def test_the_runner_not_under_a_profiler(self):
        from nodus.runtime.profiler import Profiler
        self.assertIsNone(self._runner(profiler=Profiler()))

    def _service_vm(self, env=None, session=False):
        from nodus.services.server import RuntimeService
        with tempfile.TemporaryDirectory() as directory:
            cwd = os.getcwd()
            os.chdir(directory)
            service = RuntimeService()
            try:
                with mock.patch.dict(os.environ, {"NODUS_COMPILE_FUNCTIONS": env or ""}):
                    if session:
                        sid = service.create_session()["session"]
                        result = service.execute({"code": _SRC, "session": sid})
                        vm = service.sessions.get(sid).vm
                    else:
                        result = service.execute({"code": _SRC})
                        vm = service.last_vm
            finally:
                service.close()
                os.chdir(cwd)
        self.assertTrue(result.get("ok"), result)
        return vm._pycompile

    def test_nodus_serve(self):
        self.assertIsNotNone(self._service_vm())
        self.assertIsNone(self._service_vm(env="0"))

    def test_nodus_serve_sessions(self):
        self.assertIsNotNone(self._service_vm(session=True))

    def _nodus_test(self, flags, env=None):
        source = ('import "std:test" as test\n' + _SRC.replace("print(total(100i))\n", "")
                  + 'test.suite("s", fn() {\n    test.case("c", fn() {\n'
                  '        test.assert_eq(total(100i), 4950i, "sum")\n    })\n})\n')
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "t_test.nd").write_text(source, encoding="utf-8")
            environ = dict(os.environ, PYTHONPATH=str(_REPO / "src"))
            environ.pop("NODUS_COMPILE_FUNCTIONS", None)
            if env is not None:
                environ["NODUS_COMPILE_FUNCTIONS"] = env
            proc = subprocess.run([sys.executable, "-c", _SPY, "test", *flags, "t_test.nd"], cwd=directory,
                                  capture_output=True, text=True, env=environ, timeout=120)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("1 passed", proc.stdout)
        return "ENABLED" in proc.stderr

    def test_nodus_test(self):
        self.assertTrue(self._nodus_test([]))
        self.assertFalse(self._nodus_test([], env="0"))

    def test_nodus_test_not_under_coverage(self):
        self.assertFalse(self._nodus_test(["--coverage"]))


if __name__ == "__main__":
    unittest.main()
