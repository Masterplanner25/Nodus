"""The scheduler interleaves a quick coroutine ahead of a long-running one.

These tests are about **ordering**. They were also, accidentally, asserting that
the machine can finish 8000 loop iterations in 200 ms (#631): the harness ran
them under the default `EXECUTION_TIMEOUT_MS`, which is 200 ms of *wall clock*
and counts time the coroutine did not consume. Under CPU contention the run was
killed with `{'kind': 'sandbox', 'message': 'Execution timed out'}` before the
ordering assertion was ever reached — 9 of 10 runs red under load, while an idle
box passed ~60 consecutive runs. The test measured how busy the machine was.

The deadline is explicit and generous here, and it lives in `_run` rather than at
each call site so a third test cannot reintroduce the coupling by forgetting it.
It is deliberately finite rather than `None`: a scheduler that genuinely never
rotates should fail this file, not hang the suite.

Raising the deadline rather than shrinking the loop is the deliberate choice —
fewer iterations would make the interleaving these tests exist to observe less
likely to happen at all, which is a test that passes for the wrong reason.

**This is a harness fix. `EXECUTION_TIMEOUT_MS` is unchanged**; it is a
deliberate production default, and `nodus run --time-limit` is what raises it.
"""

from nodus.tooling.runner import run_source

# 150x the default. Large enough that machine load cannot plausibly cause a
# timeout, small enough that a scheduler which never rotates still fails.
FAIRNESS_TIMEOUT_MS = 30_000


def _run(script: str, tmp_path):
    """Run a fairness script with a deadline that is not part of the assertion."""
    result, _vm = run_source(
        script,
        filename=str(tmp_path / "main.nd"),
        timeout_ms=FAIRNESS_TIMEOUT_MS,
    )
    # Surface a deadline kill as itself rather than as a confusing ordering
    # failure -- that ambiguity is what sent triage the wrong way on #631.
    error = (result.get("error") or {}) if isinstance(result, dict) else {}
    assert error.get("message") != "Execution timed out", (
        f"the run hit the {FAIRNESS_TIMEOUT_MS} ms harness deadline, so this says "
        f"nothing about fairness: {result}"
    )
    assert result.get("ok", False), result
    return result.get("stdout", "").splitlines()


def test_multiple_tasks_progress(tmp_path):
    script = """
let busy = coroutine(fn() {
    let i = 0
    while (i < 5000) {
        i = i + 1
    }
    print("busy-done")
})

let fast = coroutine(fn() {
    print("fast")
})

spawn(busy)
spawn(fast)
run_loop()
"""
    lines = _run(script, tmp_path)
    assert "fast" in lines
    assert "busy-done" in lines
    assert lines.index("fast") < lines.index("busy-done")


def test_long_running_task_rotates_with_budget(tmp_path):
    script = """
let heavy = coroutine(fn() {
    let i = 0
    while (i < 8000) {
        i = i + 1
    }
    print("heavy complete")
})

let quick = coroutine(fn() {
    print("quick")
})

spawn(heavy)
spawn(quick)
run_loop()
"""
    lines = _run(script, tmp_path)
    assert "quick" in lines
    assert "heavy complete" in lines
    assert lines.index("quick") < lines.index("heavy complete")


# closes: #631
def test_the_harness_sets_its_own_deadline(tmp_path):
    """Source assertion: the deadline is set once, in the shared helper.

    A behavioural test cannot catch the regression this guards. Both tests pass
    on an idle box with or without the fix, so nothing would go red if a future
    edit dropped `timeout_ms` and put the file back under the 200 ms production
    default -- it would simply become load-sensitive again, and be rediscovered
    the same slow way.
    """
    import inspect

    src = inspect.getsource(_run)
    assert "timeout_ms=FAIRNESS_TIMEOUT_MS" in src, (
        "the fairness harness must pass an explicit deadline; without one these "
        "tests assert that the machine is fast, not that the scheduler is fair"
    )
    assert FAIRNESS_TIMEOUT_MS >= 10_000

    # And every run in this file goes through it, so the deadline cannot be
    # forgotten by a test added later.
    #
    # Counted from the AST, not with `in`/`count` on the text: a substring
    # search here matches the assertion's own source and asserts 2 == 1, which
    # is the self-matching trap that has produced unfalsifiable source
    # assertions in this repo before.
    import ast

    tree = ast.parse(inspect.getsource(inspect.getmodule(_run)))
    calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "run_source"
    ]
    assert len(calls) == 1, f"every run must go through _run; found {len(calls)} call sites"
