"""The CLI must not import the server, and so must not import FastAPI (#173).

`nodus.cli.cli` imported `nodus.services.server` at module scope for four
commands that need it -- `serve`, `snapshot`, `snapshots`, `restore`. That module
imports FastAPI, uvicorn and pydantic, so **every** `nodus run`, `nodus fmt`,
`nodus check` and `nodus --version` paid for a web server nobody asked for.

Measured on the developer box before and after making those four imports lazy:

    import nodus.cli.cli      1840 ms  ->   743 ms
    nodus --version           1624 ms  ->   886 ms
    nodus run hello.nd        2095 ms  ->  1790 ms

That is also the standing blocker on #173's PyPy path: PyPy's *interpreter*
starts faster than CPython's (104 ms vs 184 ms), and the adoption cost is
importing Nodus's own module tree -- run-once code the JIT never warms, against
`nodus run`'s 200 ms default deadline.

A behavioural test cannot see this: the CLI works perfectly either way, only
slower. So this asserts on **what is in `sys.modules`**, in a subprocess,
because by the time any other test runs, something else has usually imported
FastAPI already.
"""

import subprocess
import sys
import textwrap
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC = str(_REPO_ROOT / "src")


def _modules_after(statement: str) -> set[str]:
    """Import something in a clean interpreter and report the top-level modules."""
    probe = textwrap.dedent(f"""
        import sys
        sys.path.insert(0, {_SRC!r})
        {statement}
        print("\\n".join(sorted({{m.split(".")[0] for m in sys.modules}})))
    """)
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        raise AssertionError(f"probe failed: {result.stderr[-800:]}")
    return set(result.stdout.split())


class TheCliDoesNotImportTheServerTests(unittest.TestCase):
    #: Only ever reached through `nodus serve` and the three snapshot commands.
    SERVER_ONLY = ("fastapi", "uvicorn", "starlette")

    @classmethod
    def setUpClass(cls):
        cls.cli_modules = _modules_after("import nodus.cli.cli")

    # closes: #173
    def test_the_cli_module_pulls_in_no_web_framework(self):
        for name in self.SERVER_ONLY:
            with self.subTest(module=name):
                self.assertNotIn(
                    name, self.cli_modules,
                    f"importing nodus.cli.cli pulled in {name}. It is only needed "
                    "by `serve` and the snapshot commands, so import it inside "
                    "those functions -- every other command pays for it here.",
                )

    # closes: #173
    def test_the_cli_still_imports_what_it_actually_uses(self):
        """The control, and it must run.

        Without it the assertion above is satisfied by a `cli` module that
        imports nothing at all, or by one that fails to import and is caught.
        """
        self.assertIn("nodus", self.cli_modules)
        for name in ("nodus", "json", "os"):
            with self.subTest(module=name):
                self.assertIn(name, self.cli_modules)

    # closes: #173
    def test_the_server_module_is_still_reachable(self):
        """The second control: made lazy, not deleted. A `nodus serve` that
        cannot find its own server would satisfy every assertion above."""
        modules = _modules_after("import nodus.services.server")
        for name in self.SERVER_ONLY[:2]:
            with self.subTest(module=name):
                self.assertIn(
                    name, modules,
                    "the server module no longer imports its web framework, so "
                    "the test above is passing for the wrong reason",
                )

    # closes: #173
    def test_the_four_lazy_names_are_importable_from_the_server(self):
        """What the lazy imports inside the command bodies name. A rename there
        is a `NameError` only when that command runs, which no fast test path
        exercises -- so it is checked here instead."""
        probe = (
            "from nodus.services.server import "
            "serve, snapshot_session, restore_snapshot, list_snapshots; "
            "print('ok')"
        )
        result = subprocess.run(
            [sys.executable, "-c", f"import sys; sys.path.insert(0, {_SRC!r}); {probe}"],
            capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(0, result.returncode, result.stderr[-800:])
        self.assertIn("ok", result.stdout)


if __name__ == "__main__":
    unittest.main()
