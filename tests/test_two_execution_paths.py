"""The CLI and the embedded runtime are two paths, and this is the whole list (#192).

`NodusRuntime` is documented as *the* embedding entry point, but
`tooling/runner.py` builds `VM` instances directly and never goes through it —
seven constructions, zero references. The CLI (`nodus run`), the HTTP service
(`services/api.py`, `services/server.py`) and the `nodus_execute` tool all take
that second path.

Some of the divergence is **decided**. Deny-by-default protects *work you did not
fully author*, and a developer running a script they just wrote is not that, so
the CLI stays permissive; `CLAUDE.md` records the decision and
`SECURITY_POSTURE.md` §3 publishes it. Some of it is **not decided** — three
settings are simply never wired on the runner path, and the two paths confine the
filesystem by *different mechanisms*.

This file is the list. It exists so that:

- a **new** difference fails a test rather than shipping unnoticed, and
- a difference that **disappears** fails too, so unification is deliberate rather
  than accidental.

That is the same treatment `test_status_vocabulary` and the claiming-site tests
give their subjects: name the set once, and make the next change argue with it.

`TheFilesystemIsConfinedByDifferentMechanismsTests` is the one worth reading. The
two paths do not merely differ in configuration — they answer *"where may this
program read"* with `fs_root` (the project root) and `allowed_paths` (the cwd)
respectively, so the same file, the same program and the same working directory
give different answers.
"""

import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))  # noqa: E402

from nodus import NodusRuntime  # noqa: E402
from nodus.tooling import runner  # noqa: E402
from nodus.vm import vm as vm_module  # noqa: E402

TRIVIAL = "fn main() { return 1i }\n"

#: What each path hands the VM, measured rather than read off the call sites.
#: A row here is a claim about behaviour; changing one means changing the table.
EXPECTED = {
    # setting            runner path      NodusRuntime
    "allow_subprocess": (True, False),
    "allow_network": (True, False),
    "allow_env": (True, False),
}


def _built_vm(construct) -> object:
    """Run `construct` and return the first VM *it* built.

    The thread check is load-bearing. Patching `VM.__init__` patches it for the
    whole process, so without it this returns the first VM **any** thread built
    inside the window — and a suite this size always has background threads that
    build VMs: a `RuntimeService` sweeper on a 500 ms timer, an abandoned agent
    handler outliving its deadline (#424), a retry sweeper. Those build
    *confined* VMs, so the failure is `allow_subprocess` reading False on the
    permissive CLI path: a real regression's signature, produced by a foreign
    object.

    It failed exactly that way on CI while the same commit passed on the push
    run of the same workflow. Measured rather than argued: with one thread
    building VMs alongside, the unguarded version returned the foreign VM in
    40 of 40 attempts.
    """
    captured = []
    caller = threading.get_ident()
    original = vm_module.VM.__init__

    def traced(self, *args, **kwargs):
        original(self, *args, **kwargs)
        if threading.get_ident() == caller:
            captured.append(self)

    vm_module.VM.__init__ = traced
    try:
        construct()
    finally:
        vm_module.VM.__init__ = original
    assert captured, "nothing constructed a VM"
    return captured[0]


class TheHarnessMeasuresItsOwnVmTests(unittest.TestCase):
    """Every claim in this file is read off a VM `_built_vm` handed back, so the
    helper picking the wrong object turns the whole file into confident noise
    (#769).

    Patching `VM.__init__` patches it process-wide. This suite always has
    threads building VMs in the background — a `RuntimeService` sweeper on a
    500 ms timer, an abandoned agent handler outliving its deadline (#424), a
    retry sweeper — and those build *confined* VMs. So the foreign object reads
    exactly like the regression this file exists to catch: `allow_subprocess`
    False on the deliberately permissive CLI path.

    It failed that way on CI while the same commit passed on the push run of the
    same workflow, which is the tell worth keeping. Not load sensitivity, and
    re-running would not have diagnosed it.
    """

    # closes: #769
    def test_a_vm_built_on_another_thread_is_not_captured(self):
        """Deterministic rather than raced: the foreign VM is built, and joined,
        before `construct` builds the one under test — so it is unambiguously
        first inside the window. Before the fix this returned the confined VM
        every time."""
        def construct():
            def build_foreign():
                vm_module.VM(
                    [], {}, code_locs=[], source_path=None,
                    allow_subprocess=False, allow_network=False, allow_env=False,
                )

            thread = threading.Thread(target=build_foreign)
            thread.start()
            thread.join()
            runner.run_source(TRIVIAL, filename="probe.nd")

        built = _built_vm(construct)
        self.assertTrue(
            built.allow_subprocess,
            "captured a VM another thread built -- every assertion in this file "
            "is then measuring the wrong object",
        )

    # closes: #769
    def test_it_still_captures_the_vm_the_caller_built(self):
        """The control. Without it the assertion above is satisfied by a helper
        that captures nothing and raises, or one that never matches a thread."""
        built = _built_vm(lambda: runner.run_source(TRIVIAL, filename="probe.nd"))
        self.assertIsInstance(built, vm_module.VM)
        self.assertTrue(built.allow_subprocess)


class TheSandboxFlagsDivergeDeliberatelyTests(unittest.TestCase):
    """Decided, not accidental — and pinned in both directions so neither the
    permissive half nor the strict half is 'tidied away' by a later reader."""

    @classmethod
    def setUpClass(cls):
        cls.cli = _built_vm(lambda: runner.run_source(TRIVIAL, filename="probe.nd"))
        cls.embedded = _built_vm(lambda: NodusRuntime().run_source(TRIVIAL))

    # closes: #192
    def test_each_flag_differs_exactly_as_recorded(self):
        for setting, (cli_value, embedded_value) in EXPECTED.items():
            with self.subTest(setting=setting):
                self.assertEqual(
                    cli_value, getattr(self.cli, setting),
                    "the CLI path is deliberately permissive -- a developer "
                    "running their own script is not untrusted input",
                )
                self.assertEqual(
                    embedded_value, getattr(self.embedded, setting),
                    "the embedded runtime denies by default (#405)",
                )


class ThreeSettingsAreNeverWiredOnTheRunnerPathTests(unittest.TestCase):
    """These are *not* a decision — they are absent.

    A host that configures a capability policy and then shells out to
    `nodus run` gets no policy at all, and there is no CLI surface for them, so
    it cannot be worked around from outside.

    **This used to say "or serves code over `POST /execute`", and #754 closed
    half of that.** `nodus serve` now denies subprocess, network and environment
    access by default and has flags to grant them — so the *sandbox flags* are
    no longer absent there. A `capability_policy`, an `approval_channel` and
    `agent_timeout_ms` still are, on both paths. The narrower claim is the true
    one, and the distinction matters: a reader who takes "serve has no policy"
    to mean "serve is unconfined" would now be wrong.
    """

    UNWIRED = ("capability_policy", "approval_channel", "agent_timeout_ms")

    @classmethod
    def setUpClass(cls):
        cls.cli = _built_vm(lambda: runner.run_source(TRIVIAL, filename="probe.nd"))

    # closes: #192
    def test_they_are_absent_on_the_runner_path(self):
        for setting in self.UNWIRED:
            with self.subTest(setting=setting):
                self.assertIsNone(
                    getattr(self.cli, setting, None),
                    "if this is now wired, the divergence table has changed",
                )

    # closes: #192
    def test_the_embedded_path_does_wire_them(self):
        """The other half. Without this the assertion above is satisfied by a
        runtime that stopped supporting policies altogether."""
        import inspect

        source = inspect.getsource(NodusRuntime.run_source.__globals__["NodusRuntime"])
        for setting in self.UNWIRED:
            with self.subTest(setting=setting):
                self.assertIn(f"vm.{setting} =", source)


class TheFilesystemIsConfinedByDifferentMechanismsTests(unittest.TestCase):
    """Two answers to *"where may this program read"*, and they disagree.

    The CLI sets `fs_root` to the **project root**; `NodusRuntime` sets
    `allowed_paths` to the **cwd**. They coincide only when the two are the same
    directory — run from a subdirectory, the same program reads a project
    sibling on one path and is refused on the other.

    Not currently recorded in `SECURITY_POSTURE.md` §3, whose table covers the
    sandbox flags and the deadline. Demonstrated here rather than described.
    """

    def _project(self, tmp: str) -> str:
        root = os.path.join(tmp, "demo")
        os.makedirs(os.path.join(root, "sub"))
        with open(os.path.join(root, "nodus.toml"), "w", encoding="utf-8") as handle:
            handle.write('[package]\nname = "demo"\nversion = "0.1.0"\n')
        with open(os.path.join(root, "sibling.txt"), "w", encoding="utf-8") as handle:
            handle.write("inside the project")
        script = os.path.join(root, "sub", "read_sibling.nd")
        with open(script, "w", encoding="utf-8") as handle:
            handle.write(
                'import "std:fs" as fs\n\n'
                "fn main() {\n"
                '    print(fs.read("../sibling.txt"))\n'
                "}\n"
            )
        return script

    # closes: #192
    def test_the_same_read_is_allowed_on_one_path_and_refused_on_the_other(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = self._project(tmp)
            cwd = os.getcwd()
            os.chdir(os.path.dirname(script))  # a subdirectory of the project
            try:
                with open(script, encoding="utf-8") as handle:
                    source = handle.read()
                cli_result, _vm = runner.run_source(source, filename=script)
                embedded_result = NodusRuntime().run_file(script)
            finally:
                os.chdir(cwd)

        self.assertTrue(
            cli_result.get("ok"),
            "the CLI confines to the project root, so a sibling is readable",
        )
        self.assertFalse(
            embedded_result.get("ok"),
            "the embedded runtime confines to the cwd, so it is not",
        )
        self.assertEqual("sandbox", embedded_result["error"]["type"])


class TheDeadlineDiffersTests(unittest.TestCase):
    """`EXECUTION_TIMEOUT_MS` (200 ms) on the runner path against no deadline at
    all embedded — the row `SECURITY_POSTURE.md` already records.

    #97 made `NodusRuntime(timeout_ms=None)` the default; the runner path kept
    the CLI's budget, and `cli.run_file` puts it back even when the CLI passes
    `None`, which is why reading either site alone tells you the opposite of what
    happens.
    """

    BUSY = "let i = 0i\nwhile (i < 400000i) { i = i + 1i }\nprint(\"finished\")\n"

    # closes: #192
    def test_the_runner_path_times_out_where_the_embedded_one_does_not(self):
        cli_result, _vm = runner.run_source(self.BUSY, filename="busy.nd")
        self.assertFalse(cli_result.get("ok"), "200ms is not enough for this loop")
        self.assertIn("timed out", str(cli_result.get("error")).lower())

        embedded = NodusRuntime().run_source(self.BUSY)
        self.assertTrue(embedded.get("ok"), embedded.get("error"))
        self.assertIn("finished", embedded.get("stdout", ""))


class TheServiceIsAThirdPositionTests(unittest.TestCase):
    """`nodus serve` builds VMs through the runner path and confines them anyway.

    Added with #754, and it is why this file is a *register* rather than a
    two-column table. The service is not "the CLI" and not "an embedded
    runtime": it shares the CLI's machinery and the embedded runtime's threat
    model, because the source arrives over a socket. Before #754 it inherited
    the machinery's defaults, which is the wrong half to inherit.

    Pinned in both directions — a regression to permissive fails, and so does
    someone "unifying" the CLI to match, which would break `nodus run`.
    """

    @classmethod
    def setUpClass(cls):
        from nodus.services.server import RuntimeService

        cls.service = RuntimeService()
        cls.vm = cls.service._new_vm()

    @classmethod
    def tearDownClass(cls):
        """#632: stop the background work rather than letting it outlive the
        class. The sweeper runs on a timer and builds VMs through
        `_workflow_vm_factory`, so a service left open is a source of foreign
        VMs for every test that runs after this one."""
        cls.service.close()

    # closes: #754
    def test_the_service_denies_what_the_cli_permits(self):
        for setting in ("allow_subprocess", "allow_network", "allow_env"):
            with self.subTest(setting=setting):
                self.assertFalse(
                    getattr(self.vm, setting),
                    "code arriving over a socket is not a script the operator "
                    "wrote and chose to run",
                )

    # closes: #754
    def test_the_cli_is_still_permitted(self):
        """The other direction. Without this, the assertion above is satisfied
        by someone denying on the CLI path too — which is a real regression and
        a decision `CLAUDE.md` and `SECURITY_POSTURE.md` both record."""
        cli = _built_vm(lambda: runner.run_source(TRIVIAL, filename="probe.nd"))
        for setting in ("allow_subprocess", "allow_network", "allow_env"):
            with self.subTest(setting=setting):
                self.assertTrue(getattr(cli, setting))

    # closes: #754
    def test_an_operator_can_grant_them_back(self):
        from nodus.services.server import RuntimeService

        granted = RuntimeService(
            allow_subprocess=True, allow_network=True, allow_env=True
        )._new_vm()
        for setting in ("allow_subprocess", "allow_network", "allow_env"):
            with self.subTest(setting=setting):
                self.assertTrue(getattr(granted, setting))


class TheRunnerPathHasNoNodusRuntimeTests(unittest.TestCase):
    """The structural claim underneath all of the above."""

    # closes: #192
    def test_the_runner_builds_vms_directly(self):
        import ast

        source = (_REPO_ROOT / "src" / "nodus" / "tooling" / "runner.py").read_text(
            encoding="utf-8"
        )
        tree = ast.parse(source)
        constructions = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "VM"
        ]
        self.assertGreater(
            len(constructions), 1,
            "the second path is defined by building VMs itself",
        )
        self.assertNotIn(
            "NodusRuntime(", source,
            "if the runner now goes through NodusRuntime, this whole file is "
            "obsolete and the divergence table should be deleted with it",
        )


if __name__ == "__main__":
    unittest.main()
