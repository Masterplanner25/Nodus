"""A call into a module runs within the caller's bounds.

A call to a function exported by an imported module, the stdlib included, runs
on a child VM built for that call (`runtime/module.py`). So does a tool handler
registered from another module. Both children inherited the caller's authority
(#405) and host wiring (#868), but not its bounds. #873 had added bounds to one
child-VM site, the workflow resume, and the other three went without.

Measured before the fix, with `NodusRuntime(max_steps=1000, timeout_ms=100)`:
`std:strings.repeat("a", 200000i)` ran to completion in 2.6 s, and
`get_execution_stats()` reported 13 instructions. The CLI's 200 ms deadline did
not stop it either. Nearly every stdlib function is a module function, so any
loop in the stdlib was a way out of both limits.

`derive_child_vm` now carries all three things together, and each site charges
the child's steps back to the caller in a `finally`. These tests cover embedded
mode and CLI mode, per the security-boundary rule in `CLAUDE.md`, and the
source-level checks keep every child-VM site on the shared helper.
"""

import os
import subprocess
import sys
import tempfile
import time
import unittest

sys.path.insert(0, "C:/dev/Coding Language/src")

from nodus.runtime.embedding import NodusRuntime  # noqa: E402

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# One stdlib call whose loop runs 16 instructions per list element: about 3 s
# for 300,000 elements, unbounded. Building the list is a single instruction in
# the caller, so nearly all the work is inside the module.
#
# This was `std:strings.repeat` until #992 made `repeat` one step. Whatever
# stands here must loop in Nodus once per unit of its argument, or these tests
# stop measuring the bound; `test_steps_taken_inside_a_module_are_counted`
# checks that it does.
_LOOP = 'import "std:collections" as c\nprint(c.list_sum([1i] * {n}i))\n'

# Many cheap stdlib calls, about 150 instructions each. Each fits easily in the
# budget; the total does not.
_MANY_CALLS = (
    'import "std:collections" as c\n'
    "let i = 0i\n"
    "while (i < 200i) {\n"
    "    c.list_sum([1i, 2i, 3i, 4i, 5i, 6i, 7i, 8i])\n"
    "    i = i + 1i\n"
    "}\n"
    'print("done")\n'
)


# A tool whose handler loops 100,000 times, and a later program that calls it.
_REGISTER_SPIN = (
    'import "std:tool" as tool\n'
    'tool.register({name: "bounds.spin", description: "spin", handler: fn(args) {\n'
    "    let i = 0i\n"
    "    while (i < 100000i) {\n"
    "        i = i + 1i\n"
    "    }\n"
    "    return i\n"
    "}})\n"
)
_CALL_SPIN = 'import "std:tool" as tool\nprint(tool.call("bounds.spin", {}))\n'


def _error(result) -> str:
    return str((result.get("error") or {}).get("message") or "")


class AStdlibCallIsBounded(unittest.TestCase):
    def test_the_step_limit_stops_a_loop_inside_a_stdlib_function(self):
        result = NodusRuntime(max_steps=1000, timeout_ms=None).run_source(_LOOP.format(n=200000))
        self.assertFalse(result.get("ok"), "a stdlib loop ran past max_steps=1000")
        self.assertIn("step limit", _error(result))

    def test_the_deadline_stops_a_loop_inside_a_stdlib_function(self):
        # About 3 s of work without the fix, so the bound is visible in the
        # elapsed time as well as in the error.
        started = time.monotonic()
        result = NodusRuntime(max_steps=None, timeout_ms=100).run_source(_LOOP.format(n=300000))
        elapsed = time.monotonic() - started
        self.assertFalse(result.get("ok"), "a stdlib loop ran past timeout_ms=100")
        self.assertIn("timed out", _error(result))
        self.assertLess(elapsed, 2.0, f"stopped only after {elapsed:.2f}s")

    def test_steps_taken_inside_a_module_are_counted(self):
        runtime = NodusRuntime(max_steps=None, timeout_ms=None)
        result = runtime.run_source(_LOOP.format(n=2000))
        self.assertTrue(result.get("ok"), _error(result))
        executed = runtime.get_execution_stats()["instructions_executed"]
        # 2,000 iterations of a loop body of several instructions. Uncounted,
        # this reported 13.
        self.assertGreater(executed, 2000 * 5)

    def test_the_charge_accumulates_across_calls(self):
        # 200 calls of about 150 instructions each. A per-call allowance would
        # let every call through; the budget is for the run.
        result = NodusRuntime(max_steps=5000, timeout_ms=None).run_source(_MANY_CALLS)
        self.assertFalse(result.get("ok"), "200 module calls each got a fresh budget")
        self.assertIn("step limit", _error(result))

    def test_the_control_the_same_program_fits_a_larger_budget(self):
        result = NodusRuntime(max_steps=200000, timeout_ms=None).run_source(_MANY_CALLS)
        self.assertTrue(result.get("ok"), _error(result))
        self.assertIn("done", result.get("stdout") or "")


class AUserModuleAndAToolHandlerAreBounded(unittest.TestCase):
    """The same boundary, reached through code the guest wrote itself."""

    def _run_in(self, directory, files, source, **limits):
        for name, text in files.items():
            with open(os.path.join(directory, name), "w", encoding="utf-8") as handle:
                handle.write(text)
        cwd = os.getcwd()
        os.chdir(directory)
        try:
            return NodusRuntime(**limits).run_source(source, filename="main.nd")
        finally:
            os.chdir(cwd)

    def test_a_relative_import(self):
        spin = (
            "export fn spin(n) {\n"
            "    let i = 0i\n"
            "    while (i < n) {\n"
            "        i = i + 1i\n"
            "    }\n"
            "    return i\n"
            "}\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            result = self._run_in(
                directory, {"spin.nd": spin},
                'import "./spin.nd" as m\nprint(m.spin(100000i))\n',
                max_steps=1000, timeout_ms=None,
            )
        self.assertFalse(result.get("ok"), "an imported module's loop ran past max_steps")
        self.assertIn("step limit", _error(result))

    def test_a_tool_handler_registered_by_another_vm(self):
        # `tool.call` runs a handler on a child VM when the handler was
        # registered by a VM with different code. That happens when the registry
        # is handed to a derived VM (`inherit_host_state`), as in a resumed
        # workflow step. Simulated directly: the entry registered by one run is
        # installed into a second run's registry. Registered and called by one
        # program, a handler runs on the caller's own VM and was always bounded.
        runtime = NodusRuntime(max_steps=5000, timeout_ms=None)
        captured: dict = {}
        runtime.register_function(
            "grab_registry",
            lambda: captured.update(runtime.active_vm().tool_registry),
            arity=0,
        )
        runtime.register_function(
            "install_registry",
            lambda: runtime.active_vm().tool_registry.update(captured),
            arity=0,
        )
        registered = runtime.run_source(_REGISTER_SPIN + "grab_registry()\n")
        self.assertTrue(registered.get("ok"), _error(registered))
        self.assertIn("bounds.spin", captured)
        result = runtime.run_source("install_registry()\n" + _CALL_SPIN)
        self.assertFalse(result.get("ok"), "a tool handler's loop ran past max_steps: "
                         + str(result.get("stdout")))
        self.assertIn("step limit", _error(result))


class TheCliDeadlineHoldsToo(unittest.TestCase):
    """`CLAUDE.md`: a security-boundary fix needs CLI and embedded coverage."""

    def test_nodus_run_stops_a_stdlib_loop_at_its_deadline(self):
        with tempfile.TemporaryDirectory() as directory:
            script = os.path.join(directory, "t.nd")
            with open(script, "w", encoding="utf-8") as handle:
                # Several seconds of work without the fix; the CLI's default
                # deadline is 200 ms.
                handle.write(_LOOP.format(n=400000))
            env = dict(os.environ)
            env["PYTHONPATH"] = os.path.join(_REPO, "src")
            proc = subprocess.run(
                [sys.executable, os.path.join(_REPO, "nodus.py"), "run", script],
                cwd=directory, env=env, capture_output=True, text=True, timeout=120,
            )
        output = proc.stdout + proc.stderr
        self.assertNotEqual(proc.returncode, 0, f"ran to completion: {output}")
        self.assertIn("timed out", output)


class EveryChildVmSiteUsesTheSharedHelper(unittest.TestCase):
    """Asserted on the source: the defect was a site nobody taught.

    Behaviour tests pass on whichever site is already right. These check that each
    site goes through `derive_child_vm` and charges its child back, and that
    nothing outside `capability.py` calls the three parts directly.
    """

    SITES = (
        "src/nodus/vm/vm.py",
        "src/nodus/runtime/module.py",
        "src/nodus/builtins/tool_module.py",
        "src/nodus/dap/server.py",
    )
    PARTS = ("inherit_authority(", "inherit_host_state(", "inherit_run_bounds(")

    def _read(self, relative):
        with open(os.path.join(_REPO, relative), "r", encoding="utf-8") as handle:
            return handle.read()

    def test_every_site_derives_through_the_helper_and_charges_back(self):
        for relative in self.SITES:
            source = self._read(relative)
            for call in ("derive_child_vm(", "charge_run_bounds("):
                self.assertTrue(call in source, f"{relative} does not call {call}")

    def test_nothing_else_calls_the_parts_directly(self):
        src = os.path.join(_REPO, "src")
        offenders = []
        for root, _dirs, files in os.walk(src):
            for name in files:
                if not name.endswith(".py") or name == "capability.py":
                    continue
                path = os.path.join(root, name)
                with open(path, "r", encoding="utf-8") as handle:
                    text = handle.read()
                for part in self.PARTS:
                    if part in text:
                        offenders.append(f"{os.path.relpath(path, _REPO)}: {part}")
        self.assertEqual(offenders, [], "call derive_child_vm instead")


if __name__ == "__main__":
    unittest.main()
