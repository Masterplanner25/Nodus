"""`spawn(fn() { ... })` wraps and spawns, without a separate `coroutine()` call (#718).

`spawn` took a coroutine value and nothing else, so launching a task cost two
statements and passing the function -- the thing every reader tries first -- was a
runtime type error documented as a quirk.

The widening delegates to `builtin_coroutine_create` rather than building a
`Coroutine` in `builtin_spawn`. That is the part these tests are really protecting:
that function carries the zero-arity check and the ASYNC-MOD-003 / #691
`_foreign_closure_origin` pinning, so a second construction site would be one
question answered in two voices. `test_the_wrapping_path_is_the_coroutine_builtin`
asserts on the source for that reason -- a behavioural test passes either way, since
a duplicated implementation would produce the same result until one of them changed.
"""

import io
import re
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))  # noqa: E402

import nodus as lang  # noqa: E402
from nodus.runtime.module_loader import ModuleLoader  # noqa: E402


def run_program(src: str) -> list[str]:
    loader = ModuleLoader(project_root=None)
    code, functions, code_locs = loader.compile_only(src, module_name="<memory>")
    vm = lang.VM(code, functions, code_locs=code_locs)
    buf = io.StringIO()
    with redirect_stdout(buf):
        vm.run()
    return buf.getvalue().splitlines()


def error_from(src: str) -> str:
    """The refusal text, however the runtime chose to deliver it.

    Two delivery paths, and the test should not care which: a builtin's own
    `runtime_error` propagates out of `vm.run()`, while a failure raised while the
    scheduler is resuming a task -- which is where the #394 step guard fires, at
    first resume inside `run_loop()` -- is reported to stderr instead. Asserting
    against only the raised form made the step-body tests report "expected the
    program to raise" while the refusal they were looking for sat in stderr.
    """
    loader = ModuleLoader(project_root=None)
    code, functions, code_locs = loader.compile_only(src, module_name="<memory>")
    vm = lang.VM(code, functions, code_locs=code_locs)
    err = io.StringIO()
    try:
        with redirect_stdout(io.StringIO()), redirect_stderr(err):
            vm.run()
    except Exception as exc:  # noqa: BLE001 - the message is the assertion
        return str(exc)
    reported = err.getvalue().strip()
    if reported:
        return reported
    raise AssertionError("expected the program to fail, it did not")


class SpawnAcceptsAFunctionTests(unittest.TestCase):
    # closes: #718
    def test_spawn_accepts_a_zero_argument_function(self):
        out = run_program(
            """
let t = spawn(fn() { print("direct") })
run_loop()
print(coroutine_status(t))
"""
        )
        self.assertEqual(["direct", "finished"], out)

    # closes: #718
    def test_the_two_step_form_is_unchanged(self):
        """The widening is additive; the spelling that worked still works."""
        out = run_program(
            """
let c = coroutine(fn() { print("two-step") })
let t = spawn(c)
run_loop()
print(coroutine_status(t))
"""
        )
        self.assertEqual(["two-step", "finished"], out)

    # closes: #718
    def test_spawn_still_returns_the_handle_when_given_a_function(self):
        """#395/#157 (D2): the return is load-bearing -- `cancel` and
        `coroutine_status` take it. A wrapped spawn must return the coroutine it
        built, not the closure it was handed."""
        out = run_program(
            """
let t = spawn(fn() { yield 1i })
print(coroutine_status(t))
"""
        )
        self.assertEqual(["created"], out)

    # closes: #718
    def test_a_non_function_non_coroutine_names_both_accepted_shapes(self):
        message = error_from("spawn(5i)")
        self.assertIn("coroutine or a zero-argument function", message)

    # closes: #718
    def test_arity_is_still_checked_and_the_error_names_spawn(self):
        """The check is not duplicated -- it is `builtin_coroutine_create`'s, reached
        through the delegation. It must still report the name the author wrote."""
        message = error_from("spawn(fn(a) { print(a) })")
        self.assertIn("zero-argument function", message)
        self.assertIn("spawn(fn)", message)
        self.assertNotIn("coroutine(fn)", message)

    # closes: #718
    def test_coroutine_still_names_itself(self):
        """The caller label must not leak the other direction."""
        message = error_from("let c = coroutine(fn(a) { print(a) })")
        self.assertIn("coroutine(fn)", message)
        self.assertNotIn("spawn(fn)", message)


class SpawnIsNotANewDoorTests(unittest.TestCase):
    """#394: a workflow step body runs only as part of its workflow.

    There were four doors, and the fix is a positive capability the graph runner
    grants -- not a check on which path called. Accepting a function in `spawn`
    routes through coroutine *creation*, and creation is not a door: the guard is at
    first resume. That is the reasoning; this is the test, because "I reasoned it
    cannot be a door" is exactly how a fifth one would ship.
    """

    _FLOW = """
workflow w {
    step a { return 1i }
}
let f = w["steps"][0]["fn"]
%s
run_loop()
print("reached end")
"""

    # closes: #718
    def test_spawning_a_step_body_function_directly_is_refused(self):
        message = error_from(self._FLOW % "spawn(f)")
        self.assertIn("cannot be called directly", message)

    # closes: #718
    def test_the_two_step_form_is_refused_identically(self):
        """Both paths must give the same refusal, or the new one is a bypass."""
        direct = error_from(self._FLOW % "spawn(f)")
        two_step = error_from(self._FLOW % "let c = coroutine(f)\n    spawn(c)")
        self.assertIn("cannot be called directly", two_step)
        marker = "cannot be called directly"
        self.assertEqual(
            direct[direct.index(marker):].splitlines()[0],
            two_step[two_step.index(marker):].splitlines()[0],
            "the two paths refuse with different wording; the new one is not "
            "reaching the same guard",
        )


class WrappingDelegatesRatherThanDuplicatesTests(unittest.TestCase):
    """Asserts on the source, because behaviour cannot see this.

    A `Coroutine(...)` constructed inside `builtin_spawn` would pass every test
    above and silently miss the origin pinning the moment `builtin_coroutine_create`
    is next amended -- the failure would surface as a cross-module coroutine
    resuming against the wrong chunk, which is #691's symptom class and is not
    traceable back to here.
    """

    _SOURCE = (_REPO_ROOT / "src/nodus/builtins/coroutine.py").read_text(
        encoding="utf-8"
    )

    def _spawn_body(self) -> str:
        match = re.search(
            r"def builtin_spawn\(value\):(.*?)\n    def ", self._SOURCE, re.S
        )
        self.assertIsNotNone(match, "builtin_spawn not found; this test needs updating")
        return match.group(1)

    # closes: #718
    def test_spawn_delegates_to_the_coroutine_builtin(self):
        self.assertIn("builtin_coroutine_create(", self._spawn_body())

    # closes: #718
    def test_spawn_does_not_construct_a_coroutine_itself(self):
        body = self._spawn_body()
        self.assertNotRegex(
            body,
            r"\bCoroutine\(",
            "builtin_spawn constructs a Coroutine directly; wrap through "
            "builtin_coroutine_create so the zero-arity check and the "
            "ASYNC-MOD-003/#691 origin pinning are not duplicated",
        )


if __name__ == "__main__":
    unittest.main()
