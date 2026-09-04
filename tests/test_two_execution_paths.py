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
    """Run `construct` and return the first VM it built."""
    captured = []
    original = vm_module.VM.__init__

    def traced(self, *args, **kwargs):
        original(self, *args, **kwargs)
        captured.append(self)

    vm_module.VM.__init__ = traced
    try:
        construct()
    finally:
        vm_module.VM.__init__ = original
    assert captured, "nothing constructed a VM"
    return captured[0]


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
    `nodus run`, or serves code over `POST /execute`, gets no policy at all.
    Unlike the sandbox flags there is no CLI surface for them either, so this
    cannot be worked around from outside.
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
