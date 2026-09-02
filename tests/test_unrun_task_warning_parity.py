"""The "spawned task never executed" warning reaches both doors (#675).

A program that spawns and never calls `run_loop()` silently does nothing. The
scheduler has always *counted* that (`_spawned_without_loop`), but the sentence was
built inside `runtime/embedding.py` — so only `NodusRuntime` callers saw it. The CLI
constructs a `VM` directly and never builds a `NodusRuntime`, so `nodus run` printed
nothing and exited 0 on a program whose work never ran.

Same runtime, two doors, two answers: the recurring shape in its **diagnostic**
variant, which is arguably the worse one to leave. The whole point of the check is
to tell a human something they cannot otherwise see, so a door that skips it is not
degraded — it is silent.

**This repo's deliberate CLI-vs-`NodusRuntime` asymmetry does not cover this**, and
the distinction is worth keeping straight. Deny-by-default splits the two because it
is a decision about authority over work you did not fully author; a developer running
a script they just wrote is not that. "The work you spawned never ran" is worth the
same through both doors, so `test_the_two_doors_produce_the_same_sentence` asserts
equality rather than merely that each is non-empty.
"""

import ast
import io
import os
import subprocess
import sys
import textwrap
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))  # noqa: E402

from nodus import NodusRuntime  # noqa: E402
from nodus.tooling.runner import run_source  # noqa: E402

DROPS_A_TASK = textwrap.dedent(
    """
    fn main() {
        spawn(fn() { print("never runs") })
        print("caller forgot to drive the scheduler")
    }
    """
)

DRIVES_THE_LOOP = textwrap.dedent(
    """
    fn main() {
        spawn(fn() { print("ran") })
        run_loop()
    }
    """
)

WARNING_MARKER = "spawned task never executed"


def _write(directory: str, name: str, source: str) -> str:
    path = os.path.join(directory, name)
    with io.open(path, "w", encoding="utf-8") as handle:
        handle.write(source)
    return path


def _cli_stderr(source: str) -> str:
    """The stderr the CLI's own door produces, without spawning a subprocess."""
    with TemporaryDirectory() as tmp:
        path = _write(tmp, "prog.nd", source)
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            result, _vm = run_source(
                io.open(path, encoding="utf-8").read(),
                filename=path,
                timeout_ms=None,
            )
    return result.get("stderr") or ""


def _embedded_stderr(source: str) -> str:
    with TemporaryDirectory() as tmp:
        path = _write(tmp, "prog.nd", source)
        return NodusRuntime().run_file(path).get("stderr") or ""


class UnrunTaskWarningParityTests(unittest.TestCase):
    # closes: #675
    def test_the_cli_door_warns(self):
        """The half that was silent."""
        self.assertIn(WARNING_MARKER, _cli_stderr(DROPS_A_TASK))

    # closes: #675
    def test_the_embedded_door_still_warns(self):
        """The half that already worked; moving the decision must not lose it."""
        self.assertIn(WARNING_MARKER, _embedded_stderr(DROPS_A_TASK))

    # closes: #675
    def test_the_two_doors_produce_the_same_sentence(self):
        """Equality, not merely "both non-empty".

        Two doors each building their own wording is the shape this fixes, one
        step removed — they would drift on the next edit, and a test that only
        checked for a substring would not notice.
        """
        self.assertEqual(
            _cli_stderr(DROPS_A_TASK), _embedded_stderr(DROPS_A_TASK)
        )

    # closes: #675
    def test_neither_door_warns_when_the_loop_is_driven(self):
        """The negative case, through both. A warning that always fires is noise,
        and `run_loop()` resets the counter precisely so it does not."""
        self.assertEqual("", _cli_stderr(DRIVES_THE_LOOP))
        self.assertEqual("", _embedded_stderr(DRIVES_THE_LOOP))

    # closes: #675
    def test_the_count_and_plural_agree(self):
        source = textwrap.dedent(
            """
            fn main() {
                spawn(fn() { print("a") })
                spawn(fn() { print("b") })
            }
            """
        )
        for stderr in (_cli_stderr(source), _embedded_stderr(source)):
            self.assertIn("2 spawned tasks never executed", stderr)


class TheWarningSurvivesTheRealCliTests(unittest.TestCase):
    """One end-to-end check through the actual executable.

    The tests above call `run_source` directly, which is the CLI's door but not
    the CLI. #675 is about what a user sees at a terminal, and the two are only
    the same as long as `run_file` keeps printing the result's stderr — so one
    test goes the whole way rather than assuming it.
    """

    # closes: #675
    def test_nodus_run_prints_the_warning_and_still_exits_zero(self):
        with TemporaryDirectory() as tmp:
            path = _write(tmp, "prog.nd", DROPS_A_TASK)
            env = dict(os.environ, PYTHONPATH=str(_REPO_ROOT / "src"))
            proc = subprocess.run(
                # `--time-limit` because the whole program is bounded at 200 ms by
                # default and an import is charged to that budget (SCHED-001).
                [sys.executable, "-m", "nodus", "run", path, "--time-limit", "30"],
                capture_output=True, text=True, env=env, timeout=90,
            )
        self.assertIn(WARNING_MARKER, proc.stderr)
        self.assertIn("caller forgot to drive the scheduler", proc.stdout)
        self.assertEqual(0, proc.returncode, proc.stderr)


class TheDecisionLivesInOnePlaceTests(unittest.TestCase):
    """Asserts on the source, because behaviour cannot see this.

    Both doors agree today whichever way it is implemented. What this pins is that
    they agree *by construction* -- a second copy of the sentence would pass every
    test above until someone edited one of them, which is exactly how #675 came to
    exist.

    Scans **string literals across all of `src/`**, not the two doors by name, so
    a third copy in a module nobody thought to name here is still caught.

    The marker is the warning's *action clause*, and getting there took two
    corrections worth recording. Matching raw file text tripped over a **comment**
    quoting the warning. Matching the phrase "never executed" in string literals
    then tripped over an unrelated sentence in `orchestration/task_graph.py` --
    which is not even a docstring, because a `nonlocal` statement precedes it and
    makes it `body[1]`. Both misses are the same mistake: a source assertion aimed
    at the *words* rather than at the *construct*. "call run_loop() after spawn()"
    can only be this warning.
    """

    MARKER = "call run_loop() after spawn()"

    def _modules_with_the_sentence(self) -> list[str]:
        homes = []
        for path in sorted((_REPO_ROOT / "src").rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError, OSError):
                continue
            for node in ast.walk(tree):
                if (isinstance(node, ast.Constant)
                        and isinstance(node.value, str)
                        and self.MARKER in node.value):
                    homes.append(path.relative_to(_REPO_ROOT).as_posix())
                    break
        return homes

    # closes: #675
    def test_exactly_one_module_builds_the_sentence(self):
        homes = self._modules_with_the_sentence()
        self.assertEqual(
            ["src/nodus/runtime/scheduler.py"], homes,
            "the unrun-task warning is built in more than one place; ask "
            "Scheduler.unrun_task_warning() so there is one wording",
        )

    # closes: #675
    def test_both_doors_ask_the_scheduler(self):
        for path in (_REPO_ROOT / "src/nodus/runtime/embedding.py",
                     _REPO_ROOT / "src/nodus/tooling/runner.py"):
            with self.subTest(door=path.name):
                self.assertIn("unrun_task_warning()", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
