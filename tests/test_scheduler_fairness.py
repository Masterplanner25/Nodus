import os

from nodus.tooling.runner import run_source


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
    result, _vm = run_source(script, filename=str(tmp_path / "main.nd"))
    assert result.get("ok", False), result
    lines = result.get("stdout", "").splitlines()
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
    result, _vm = run_source(script, filename=str(tmp_path / "main.nd"))
    assert result.get("ok", False), result
    lines = result.get("stdout", "").splitlines()
    assert "quick" in lines
    assert "heavy complete" in lines
    assert lines.index("quick") < lines.index("heavy complete")
