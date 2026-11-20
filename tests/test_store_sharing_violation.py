"""Store reads and writes wait out a Windows sharing violation (#939).

On Windows, opening a run record while another process renames over it fails
with ``[Errno 13]``, and renaming over a record another process has open fails
with ``[WinError 5]``. Both clear quickly. #376 gave the write a bounded retry
(``_replace_with_retry``) and left the read bare, so ``get_run`` in one process
failed on ~5% of calls while another process was saving (measured 8% with a
reader polling every 10 ms). That was fixed first.

The write's retry was also too short: 5 tries, about 0.2 s. A reader in a tight
loop outlasted it and the writer's ``save_run`` failed within seconds, every
run. The retry is now a 2 s time budget, about twice the slowest save measured
surviving such a reader (1.1 s).

Both halves go through one policy, ``_retry_sharing_violation``. These tests pin
the behaviour with injected fakes (never by patching the global ``open``, for
the reason #612 gives), pin the budget with an injected clock, pin the
one-policy shape at the source, and, on Windows, run the real two-process race.
"""

import ast
import inspect
import os
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))  # noqa: E402

from nodus_lang_workflow import store as store_module  # noqa: E402
from nodus_lang_workflow.store import LocalWorkflowStore  # noqa: E402


def _denied(*_args, **_kwargs):
    raise PermissionError(13, "Permission denied")


class _FlakyOpener:
    """Denies the first `failures` opens, then opens for real."""

    def __init__(self, failures: int):
        self.failures = failures
        self.calls = 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        if self.calls <= self.failures:
            raise PermissionError(13, "Permission denied")
        return open(*args, **kwargs)


class ReadRetryTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = LocalWorkflowStore(root=self._tmp.name)
        self.store.create_run(run_id="r1", graph_id="r1", workflow_name="w",
                              execution_kind="workflow")

    def _route_reads_through(self, opener):
        # Per instance, so nothing else in the process sees the fake (#612).
        self.store._read_record_json = (
            lambda path: LocalWorkflowStore._read_record_json(path, opener=opener))

    # closes: #939
    def test_get_run_waits_out_a_transient_denial(self):
        opener = _FlakyOpener(failures=2)
        self._route_reads_through(opener)

        record = self.store.get_run("r1")

        self.assertIsNotNone(record, "the read was not retried")
        self.assertEqual("r1", record.run_id)
        self.assertEqual(3, opener.calls)

    # closes: #939
    def test_list_runs_waits_out_a_transient_denial(self):
        """The listing reads through the same method, so a sweep or
        `nodus workflow runs` in a second process no longer fails either."""
        opener = _FlakyOpener(failures=2)
        self._route_reads_through(opener)

        self.assertEqual(["r1"], [r.run_id for r in self.store.list_runs()])
        # Without this, a listing that opened files itself would pass too.
        self.assertEqual(3, opener.calls, "the listing bypassed the retrying reader")

    def test_a_persistent_denial_is_raised_not_waited_on_forever(self):
        self._route_reads_through(_denied)
        started = time.monotonic()
        with self.assertRaises(PermissionError):
            self.store.get_run("r1")
        self.assertLess(time.monotonic() - started, 5.0)

    def test_a_missing_record_is_not_retried(self):
        """`FileNotFoundError` is not a sharing violation. Retrying it would
        add ~0.2 s to every lookup of a run that does not exist."""
        opener = _FlakyOpener(failures=0)
        self._route_reads_through(opener)

        self.assertIsNone(self.store.get_run("no_such_run"))
        self.assertEqual(1, opener.calls)

    def test_the_injected_opener_is_used_and_open_is_untouched(self):
        """#612's lesson, applied to the read: a count-based test cannot tell
        an injected fake from a patched global."""
        import builtins

        before = builtins.open
        seen = []

        def recording_open(path, *args, **kwargs):
            seen.append(path)
            return before(path, *args, **kwargs)

        path = self.store._run_path("r1")
        LocalWorkflowStore._read_record_json(path, opener=recording_open)

        self.assertEqual([path], seen)
        self.assertIs(before, builtins.open)


class _FakeTime:
    """A clock that only moves when the code under test sleeps."""

    def __init__(self):
        self.now = 1000.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def _denied_until(fake: _FakeTime, until: float):
    """An operation denied until the fake clock reaches `until`."""

    def op():
        if fake.now < until:
            raise PermissionError(5, "Access is denied")
        return "done"

    return op


class RetryBudgetTests(unittest.TestCase):
    """The budget is time, and it is 2 s. With an injected clock, so nothing
    here actually waits."""

    def test_the_budget_is_two_seconds(self):
        self.assertEqual(2.0, store_module._SHARING_VIOLATION_BUDGET_S)

    # closes: #939
    def test_a_denial_lasting_well_past_the_old_window_is_waited_out(self):
        """1.5 s of denial. The old 5-try policy gave up after about 0.2 s, and
        a tight-loop reader in another process measured up to 1.1 s."""
        fake = _FakeTime()
        start = fake.now
        result = store_module._retry_sharing_violation(
            _denied_until(fake, start + 1.5), clock=fake.clock, sleep=fake.sleep)
        self.assertEqual("done", result)
        self.assertGreaterEqual(fake.now - start, 1.5)

    def test_it_gives_up_at_the_budget_and_not_before(self):
        fake = _FakeTime()
        start = fake.now
        with self.assertRaises(PermissionError):
            store_module._retry_sharing_violation(
                _denied_until(fake, float("inf")), clock=fake.clock, sleep=fake.sleep)
        waited = fake.now - start
        self.assertGreaterEqual(waited, 2.0, "gave up before the budget")
        self.assertLessEqual(waited, 2.0 + 1e-9, "slept past the budget")

    def test_no_single_sleep_is_long(self):
        """A reader lets go within milliseconds. A long sleep would mostly
        waste the window a writer is waiting for."""
        fake = _FakeTime()
        with self.assertRaises(PermissionError):
            store_module._retry_sharing_violation(
                _denied_until(fake, float("inf")), clock=fake.clock, sleep=fake.sleep)
        self.assertLessEqual(max(fake.sleeps), 0.1)
        self.assertGreater(len(fake.sleeps), 10, "too few tries across 2 s")

    def test_success_on_the_first_try_does_not_sleep(self):
        fake = _FakeTime()
        result = store_module._retry_sharing_violation(
            lambda: "done", clock=fake.clock, sleep=fake.sleep)
        self.assertEqual("done", result)
        self.assertEqual([], fake.sleeps)

    def test_the_write_uses_the_same_budget(self):
        """`_replace_with_retry` must not carry a shorter default of its own,
        which is how the write ended up at 0.2 s while nothing said so."""
        default = inspect.signature(
            LocalWorkflowStore._replace_with_retry).parameters["budget_s"].default
        self.assertEqual(store_module._SHARING_VIOLATION_BUDGET_S, default)


def _body_without_docstring(func) -> str:
    """A function's source with its docstring removed, so a source assertion
    cannot be satisfied by the docstring explaining the fix."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(func)))
    node = tree.body[0]
    if (node.body and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)):
        node.body = node.body[1:]
    return ast.unparse(node)


class OnePolicyTests(unittest.TestCase):
    """#939's cause was two halves with two policies: the write retried and the
    read did not. Pinned at the source so a new path cannot bring that back."""

    # closes: #939
    def test_read_and_write_share_one_retry_helper(self):
        for func in (LocalWorkflowStore._replace_with_retry,
                     LocalWorkflowStore._read_record_json):
            body = _body_without_docstring(func)
            self.assertIn("_retry_sharing_violation(", body, func.__name__)
            self.assertNotIn("PermissionError", body,
                             f"{func.__name__} has its own retry policy again")

    def test_the_helper_is_the_only_place_permission_errors_are_caught(self):
        source = inspect.getsource(store_module)
        helper = inspect.getsource(store_module._retry_sharing_violation)
        self.assertEqual(1, source.count("except PermissionError"))
        self.assertIn("except PermissionError", helper)

    def test_no_record_is_opened_outside_the_two_helpers(self):
        """Every bare `open(` call in the store is the temp-file write. A read
        added with a plain `open(...)` would skip the retry, which is #939."""
        bodies = [_body_without_docstring(member)
                  for _name, member in inspect.getmembers(LocalWorkflowStore)
                  if inspect.isfunction(member)
                  and member.__qualname__.startswith("LocalWorkflowStore.")]
        calls = [b for b in bodies if "open(" in b.replace("do_open(", "")]
        self.assertEqual(1, len(calls), calls)
        self.assertIn("open(tmp_path, 'w'", calls[0])

    def test_the_read_goes_through_the_retrying_reader(self):
        body = _body_without_docstring(LocalWorkflowStore._load_run_unlocked)
        self.assertIn("self._read_record_json(", body)


_WRITER = """
import sys, time
sys.path.insert(0, {src!r})
from nodus_lang_workflow.store import LocalWorkflowStore
store = LocalWorkflowStore(root={root!r})
rec = store.get_run("r1")
end = time.time() + {seconds}
saves = failed = 0
while time.time() < end:
    rec.metadata["n"] = saves
    try:
        store.save_run(rec)
    except PermissionError:
        failed += 1  # keep the race going; the exit code reports it
    saves += 1
print(f"saves={{saves}} failed={{failed}}")
sys.exit(1 if failed else 0)
"""


@unittest.skipUnless(os.name == "nt", "the sharing violation is Windows-only")
class CrossProcessRaceTests(unittest.TestCase):
    """The real race: one process saving in a loop, this one reading the same
    record in a tight loop, which is the case that outlasted the old 0.2 s
    write retry. Neither side may see a `PermissionError`.

    It skips rather than passes when it cannot discriminate. Each iteration
    also makes one bare `open()` of the record; if none of those is ever
    denied, the two processes never contended and a clean run proves nothing.
    """

    SECONDS = 6

    # closes: #939
    def test_neither_side_fails_while_two_processes_share_a_record(self):
        with tempfile.TemporaryDirectory() as root:
            store = LocalWorkflowStore(root=root)
            store.create_run(run_id="r1", graph_id="r1", workflow_name="w",
                             execution_kind="workflow")
            path = store._run_path("r1")
            writer = subprocess.Popen(
                [sys.executable, "-c", _WRITER.format(
                    src=str(_REPO_ROOT / "src"), root=root, seconds=self.SECONDS)],
                stdout=subprocess.PIPE, text=True)
            try:
                time.sleep(0.5)  # let the writer import and start
                bare_denied = store_denied = reads = 0
                end = time.monotonic() + self.SECONDS - 1
                while time.monotonic() < end:
                    try:
                        with open(path, "r", encoding="utf-8") as handle:
                            handle.read()
                    except PermissionError:
                        bare_denied += 1
                    try:
                        store.get_run("r1")
                    except PermissionError:
                        store_denied += 1
                    reads += 1
            finally:
                writer_out, _ = writer.communicate(timeout=60)

        if bare_denied == 0:
            self.skipTest(f"no contention in {reads} reads; cannot discriminate")
        self.assertEqual(
            0, store_denied,
            f"get_run denied {store_denied} times in {reads} reads "
            f"(a bare open was denied {bare_denied} times)")
        self.assertEqual(
            0, writer.returncode,
            f"the writer's save_run failed against a tight-loop reader: "
            f"{writer_out.strip()}")


if __name__ == "__main__":
    unittest.main()
