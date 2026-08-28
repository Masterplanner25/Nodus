"""Closed-issue test for #632: RuntimeService.close() waits for its sweeper.

`close()` set `_stop_event` and notified the condition the sweeper waits on, and
then returned -- without joining. So it returned while `_worker_sweeper_loop`
could still be *inside* `sweep()`, touching the workflow store. Any caller that
then removed the store's directory raced a live thread.

The symptom was reported as a tempdir race, because that is all Linux shows:

    sqlite3.OperationalError: no such table: workflow_runs
    OSError: [Errno 39] Directory not empty: '/tmp/tmpa8bixhqk'

Windows names the actual cause, which is what identified it:

    PermissionError: [WinError 32] The process cannot access the file because
    it is being used by another process: '...\\workflow_framework.sqlite3'

This is the **second** sweeper, not the one #591 fixed. That fix stopped the
default runner's `nodus-workflow-sweep` daemon through
`reset_default_workflow_runner()` and left `_worker_sweeper_loop` running, so
the symptom outlived its own fix. Two threads, one question -- the shape
`docs`/`CLAUDE.md` describe.

Deliberately **no** `SQLiteWorkflowStore.close()`. The issue proposed one; it
turned out to be unnecessary and would have been inert. The store connects per
operation through `_managed_conn` and closes each connection, so it holds
nothing between calls: once no thread is mid-operation, SQLite removes the
`-wal`/`-shm` sidecars itself. Measured, not assumed -- with only the join
added, 8/8 probe rounds under CPU load left no sidecars and removed cleanly,
against 3/8 failing before.

**There is deliberately no end-to-end "and then the directory can be removed"
test.** One was written and deleted: on an idle box it passes with the join
mutated out, because an unblocked sweeper exits before the removal reaches it.
Making it fail reliably means simulating the race, which is what
`test_close_returns_only_once_the_sweeper_has_stopped` already does at the
level the bug lives at -- a sweeper that is dead cannot be holding the store.
A test that cannot fail would have recorded the removal as *guarded* when it
was only *lucky*, which is the same mistake as the check removed in #480.
"""

import sys
import threading
import time

from pathlib import Path

# closes: #632

_REPO_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(_REPO_ROOT / "src"))  # noqa: E402

from nodus.services.server import RuntimeService  # noqa: E402


def _sweeper(service) -> threading.Thread | None:
    return getattr(service, "_sweeper_thread", None)


def test_close_returns_only_once_the_sweeper_has_stopped():
    """The claim, made falsifiable by pinning the sweeper inside an iteration.

    Without a slow sweep this passes either way: an idle sweeper exits so
    quickly that an unjoined `close()` looks correct. Holding it inside
    `_run_workflow_sweep_once` guarantees it is *running* at the moment
    `close()` is called, which is the state the bug is about.
    """
    service = RuntimeService(worker_sweep_interval_ms=10)
    entered = threading.Event()
    release = threading.Event()
    original = service._run_workflow_sweep_once

    def slow_sweep():
        entered.set()
        release.wait(timeout=5.0)
        return original()

    service._run_workflow_sweep_once = slow_sweep
    try:
        assert entered.wait(timeout=5.0), "the sweeper never ran"
        thread = _sweeper(service)
        assert thread is not None and thread.is_alive()

        release.set()
        service.close()

        assert not thread.is_alive(), (
            "close() returned while the sweeper was still running; a caller "
            "removing the store directory now would race it"
        )
    finally:
        release.set()
        service.close()


def test_close_is_safe_to_call_twice():
    """`server_close()` runs from `finally` blocks, sometimes more than once."""
    service = RuntimeService(worker_sweep_interval_ms=10)
    service.close()
    service.close()
    thread = _sweeper(service)
    assert thread is None or not thread.is_alive()


def test_close_does_not_raise_when_the_sweeper_overruns():
    """A stuck sweeper is reported, not raised.

    `close()` runs from `server_close()`, which runs in `finally` blocks;
    raising there would replace whatever error was already being handled. The
    warning is the observable part -- silence is what let this persist through
    #591.
    """
    import warnings

    service = RuntimeService(worker_sweep_interval_ms=10)
    release = threading.Event()
    original = service._run_workflow_sweep_once

    def stuck_sweep():
        release.wait(timeout=30.0)
        return original()

    service._run_workflow_sweep_once = stuck_sweep
    time.sleep(0.05)

    import nodus.services.server as server_module

    previous = server_module.SWEEPER_JOIN_TIMEOUT_S
    server_module.SWEEPER_JOIN_TIMEOUT_S = 0.1
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            service.close()  # must not raise
        messages = [str(w.message) for w in caught]
        assert any("#632" in m for m in messages), messages
    finally:
        server_module.SWEEPER_JOIN_TIMEOUT_S = previous
        release.set()
        service.close()
