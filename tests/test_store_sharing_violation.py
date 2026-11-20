"""A record read waits out a Windows sharing violation, like a write does (#939).

On Windows, opening a run record while another process renames over it fails
with ``[Errno 13]`` for a few milliseconds. #376 gave the write a bounded retry
(``_replace_with_retry``) and left the read bare, so ``get_run`` in one process
failed on ~5% of calls while another process was saving (#939, measured 8% with
a reader polling every 10 ms).

The fix is one retry policy, ``_retry_sharing_violation``, that both halves go
through. These tests pin the behaviour with injected fakes (never by patching the
global ``open``, for the reason #612 gives), pin the one-policy shape at the
source, and, on Windows, run the real two-process race.

Not covered here, because it is not fixed: a reader in a tight loop can still
outlast the *write's* retry. That half of #939 is open.
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
n = 0
while time.time() < end:
    rec.metadata["n"] = n
    try:
        store.save_run(rec)
    except PermissionError:
        pass  # the write half of #939 is not fixed; keep the race going
    n += 1
"""


@unittest.skipUnless(os.name == "nt", "the sharing violation is Windows-only")
class CrossProcessReadTests(unittest.TestCase):
    """The real race: another process saving while this one reads.

    It skips rather than passes when it cannot discriminate. Each iteration
    also makes one bare `open()` of the record; if none of those is ever
    denied, the writer never contended and a clean `get_run` proves nothing.
    """

    SECONDS = 4

    # closes: #939
    def test_get_run_is_not_denied_while_another_process_saves(self):
        with tempfile.TemporaryDirectory() as root:
            store = LocalWorkflowStore(root=root)
            store.create_run(run_id="r1", graph_id="r1", workflow_name="w",
                             execution_kind="workflow")
            path = store._run_path("r1")
            writer = subprocess.Popen([sys.executable, "-c", _WRITER.format(
                src=str(_REPO_ROOT / "src"), root=root, seconds=self.SECONDS)])
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
                    time.sleep(0.005)
            finally:
                writer.wait(timeout=30)

        if bare_denied == 0:
            self.skipTest(f"no contention in {reads} reads; cannot discriminate")
        self.assertEqual(
            0, store_denied,
            f"get_run denied {store_denied} times in {reads} reads "
            f"(a bare open was denied {bare_denied} times)")


if __name__ == "__main__":
    unittest.main()
