"""#180 stage 3: capture a continuation, discard the coroutine, rebuild, continue.

The design's stage table calls this the stage that falsifies the document: if a
continuation cannot be rebuilt from its own written form, §4's decision (a
bare-coroutine checkpoint is a *position*) is wrong, and no store would have
saved it.

The shape of every test: a program suspends a `worker` at `sleep(0i)`. An
`inspector` coroutine captures it to JSON with `capture_continuation`, then
discards it from the scheduler, as a crash would. A second runtime, compiled
from the same source, restores it with `restore_continuation` and lets it run.
The second runtime's output is what the worker did *after* the suspend, and
nothing from before it.

The last class does it across two real processes, so the program's identity is
checked with a different hash seed on each side.
"""

import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))  # noqa: E402

from nodus.runtime.continuation import (  # noqa: E402
    FORMAT,
    ContinuationRefused,
    capture_continuation,
    restore_continuation,
)
from nodus.runtime.embedding import NodusRuntime  # noqa: E402

# Every program ends with this. `mode()` and the two hooks are host functions.
_DRIVER = """
fn inspector() { snap(); return 1i }
fn main() {
    if (mode() == "fresh") {
        spawn(coroutine(worker))
        spawn(coroutine(inspector))
    } else {
        adopt()
    }
    run_loop()
}
main()
"""


def _discard(scheduler, coroutine) -> None:
    """Take a suspended coroutine out of the scheduler, as a crash would."""
    scheduler.timers = [t for t in scheduler.timers if t[2] is not coroutine]
    scheduler.ready_queue = type(scheduler.ready_queue)(
        c for c in scheduler.ready_queue if c is not coroutine)
    scheduler.queue = scheduler.ready_queue
    scheduler.sleeping_tasks.discard(coroutine.id)
    coroutine.state = "finished"


def _worker(scheduler):
    return next(t for t in scheduler.tasks.values()
                if t.closure.function.name == "worker")


def _run(src: str, mode: str, data=None, *, on_capture=None):
    """Run `src` in a fresh runtime. Returns (result, captured data)."""
    captured = {}
    runtime = NodusRuntime(timeout_ms=None, max_steps=None)

    def snap():
        scheduler = runtime.active_vm().scheduler
        worker = _worker(scheduler)
        raw = capture_continuation(worker)
        # Through text and back: whatever the restore sees is pure data.
        captured["data"] = json.loads(json.dumps(raw))
        if on_capture is not None:
            on_capture(worker, captured["data"])
        _discard(scheduler, worker)

    def adopt():
        vm = runtime.active_vm()
        vm.scheduler.spawn(restore_continuation(vm, data))

    runtime.register_function("mode", lambda: mode)
    runtime.register_function("snap", snap)
    runtime.register_function("adopt", adopt)
    result = runtime.run_source(textwrap.dedent(src) + _DRIVER)
    return result, captured.get("data")


def _round_trip(src: str):
    first, data = _run(src, "fresh")
    assert first.get("ok"), first.get("error")
    assert data is not None, "the worker was never captured"
    second, _ = _run(src, "resume", data)
    assert second.get("ok"), second.get("error")
    return first["stdout"], second["stdout"]


class ItContinuesFromThePositionTests(unittest.TestCase):

    def test_effects_before_the_suspend_run_once_and_the_rest_runs_after(self):
        before, after = _round_trip("""
            fn worker() {
                let n = 41i
                print("before")
                sleep(0i)
                n += 1i
                print("after \\(n)")
                return n
            }
            """)
        self.assertEqual("before\n", before)
        self.assertEqual("after 42\n", after)

    def test_a_suspend_inside_a_nested_call_returns_to_its_caller(self):
        before, after = _round_trip("""
            fn helper(xs) {
                let count = len(xs)
                sleep(0i)
                return count * 10i
            }
            fn worker() {
                let xs = [1i, 2i, 3i]
                print("calling")
                let got = helper(xs)
                print("helper gave \\(got)")
                return got
            }
            """)
        self.assertEqual("calling\n", before)
        self.assertEqual("helper gave 30\n", after)

    def test_sharing_cycles_and_records_survive(self):
        """Two names for one list are one list after the restore, a list that
        holds itself is still itself, and a record keeps its kind and fields."""
        _, after = _round_trip("""
            fn worker() {
                let a = [1i]
                let b = a
                let r = {tags: a, name: "job"}
                let loop = []
                list_push(loop, loop)
                sleep(0i)
                list_push(b, 2i)
                print("a=\\(a) r.tags=\\(r.tags) name=\\(r.name)")
                print("self=\\(len(loop[0][0][0]))")
                return 1i
            }
            """)
        self.assertEqual("a=[1, 2] r.tags=[1, 2] name=job\nself=1\n", after)

    def test_int_float_and_nil_keep_their_types(self):
        _, after = _round_trip("""
            fn worker() {
                let i = 3i
                let f = 3.0
                let z = nil
                let m = {"k": 1.5, "flag": false}
                sleep(0i)
                print("\\(type(i)) \\(type(f)) \\(type(z)) \\(type(m["k"])) \\(m["flag"])")
                return 1i
            }
            """)
        self.assertEqual("int float nil float false\n", after)

    def test_a_suspend_inside_nested_for_loops_continues_at_the_next_elements(self):
        """#911. The suspend is on the first cell of the first row; the restored
        coroutine must carry on with the second cell, then the second row,
        without repeating the first. The inner loop walks a list the outer loop
        also holds, so the heap table has to keep them one list."""
        before, after = _round_trip("""
            fn worker() {
                let grid = [["a", "b"], ["c"]]
                for row in grid {
                    for cell in row {
                        print("cell \\(cell)")
                        if (cell == "a") { sleep(0i) }
                    }
                }
                print("rows \\(len(grid))")
                return 1i
            }
            """)
        self.assertEqual("cell a\n", before)
        self.assertEqual("cell b\ncell c\nrows 2\n", after)

    def test_the_restored_loop_walks_the_same_list_the_locals_hold(self):
        """The iterator's list goes through the heap table with the locals, so a
        list the loop is walking and a local that names it are still one list.
        Written as a copy, the append below would be invisible to the loop."""
        _, after = _round_trip("""
            fn worker() {
                let xs = [1i, 2i]
                for x in xs {
                    if (x == 1i) {
                        sleep(0i)
                        list_push(xs, 3i)
                    }
                    print("x=\\(x)")
                }
                return 1i
            }
            """)
        self.assertEqual("x=1\nx=2\nx=3\n", after)

    def test_a_pending_finally_runs_after_the_restore_and_not_before(self):
        before, after = _round_trip("""
            fn worker() {
                try {
                    print("in try")
                    sleep(0i)
                    print("still in try")
                } finally {
                    print("cleanup")
                }
                return 1i
            }
            """)
        self.assertEqual("in try\n", before)
        self.assertEqual("still in try\ncleanup\n", after)

    def test_the_restored_coroutine_shares_nothing_with_the_original(self):
        """Discarded means gone. If the rebuilt coroutine held one of the old
        containers, a same-process round trip would pass for the wrong reason."""
        seen = {}

        def remember(worker, _data):
            ids = set()
            for frame in worker.frames:
                for value in list(frame.locals.values()) + list(frame.locals_array or []):
                    if isinstance(value, (list, dict)):
                        ids.add(id(value))
            seen["old"] = ids
            seen["keep"] = worker  # keep the ids unique while we compare

        src = """
            fn worker() {
                let xs = [1i, 2i]
                sleep(0i)
                return len(xs)
            }
            """
        _, data = _run(src, "fresh", on_capture=remember)
        runtime = NodusRuntime(timeout_ms=None, max_steps=None)
        runtime.register_function("mode", lambda: "idle")
        runtime.register_function("snap", lambda: None)
        runtime.register_function("adopt", lambda: None)
        self.assertTrue(runtime.run_source(textwrap.dedent(src) + _DRIVER).get("ok"))
        rebuilt = restore_continuation(runtime.active_vm(), data)
        new_ids = {id(v) for f in rebuilt.frames
                   for v in list(f.locals.values()) + list(f.locals_array or [])
                   if isinstance(v, (list, dict))}
        self.assertTrue(new_ids, "the rebuilt frame holds no containers to compare")
        self.assertFalse(new_ids & seen["old"])


class TheCaptureCoversTheInventoryTests(unittest.TestCase):
    """§3.1's table is the list of what a suspend saves, pinned by the premises
    test. Each member is either written down here or deliberately rebuilt on the
    other side. A member added to the suspend later, and to neither, would be
    silently dropped by a resume."""

    REBUILT = {"module_ctx"}  # the target VM's own context, from source

    def test_every_saved_field_is_captured_or_rebuilt(self):
        import importlib.util

        # By path, so it imports the same way under pytest and either unittest form.
        spec = importlib.util.spec_from_file_location(
            "_premises", _REPO_ROOT / "tests" / "test_durable_coroutine_premises.py")
        premises = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(premises)
        Premises = premises.TheContinuationCaptureIsAnInventoryTests
        _, data = _run("""
            fn worker() { sleep(0i); return 1i }
            """, "fresh")
        missing = set(Premises._EXPECTED) - self.REBUILT - set(data)
        self.assertEqual(set(), missing,
                         "saved on suspend but neither captured nor rebuilt")


class ItRefusesRatherThanLiesTests(unittest.TestCase):

    def test_a_non_durable_coroutine_is_refused_with_the_stage_two_reasons(self):
        for name, body, phrase in (
            ("a channel local", "let ch = channel()\n    sleep(0i)", "local `ch`: a channel"),
            # A `for` over a list is data since #911; one over a user-defined
            # iterator keeps its position in a closure and is still refused.
            ("inside a for over a user-defined iterator",
             "let st = {done: false}\n"
             "    for x in {__next__: fn(r) { if (st.done) { return nil }\n"
             "        st.done = true\n        return 1i }} { sleep(0i) }",
             "user-defined iterator"),
        ):
            with self.subTest(name):
                runtime = NodusRuntime(timeout_ms=None, max_steps=None)
                caught = []

                def snap():
                    try:
                        capture_continuation(_worker(runtime.active_vm().scheduler))
                    except ContinuationRefused as exc:
                        caught.append(exc)

                runtime.register_function("mode", lambda: "fresh")
                runtime.register_function("snap", snap)
                runtime.register_function("adopt", lambda: None)
                src = f"fn worker() {{\n    {body}\n    return 1i\n}}\n"
                self.assertTrue(runtime.run_source(src + _DRIVER).get("ok"))
                self.assertEqual(1, len(caught))
                self.assertIsNotNone(caught[0].report)
                self.assertIn(phrase, str(caught[0]))

    def test_a_running_coroutine_is_refused(self):
        runtime = NodusRuntime(timeout_ms=None, max_steps=None)
        caught = []

        def snap_self():
            try:
                capture_continuation(runtime.active_vm().current_coroutine)
            except ContinuationRefused as exc:
                caught.append(str(exc))

        runtime.register_function("snap_self", snap_self)
        src = "fn w() { snap_self(); return 1i }\nspawn(coroutine(w))\nrun_loop()\n"
        self.assertTrue(runtime.run_source(src).get("ok"))
        self.assertEqual(1, len(caught))
        self.assertIn("only a suspended coroutine", caught[0])

    _SIMPLE = """
        fn worker() {
            print("before")
            sleep(0i)
            print("after")
            return 1i
        }
        """

    def _restore_error(self, src: str, data) -> str:
        runtime = NodusRuntime(timeout_ms=None, max_steps=None)
        caught = []

        def adopt():
            try:
                restore_continuation(runtime.active_vm(), data)
            except ContinuationRefused as exc:
                caught.append(str(exc))

        runtime.register_function("mode", lambda: "resume")
        runtime.register_function("snap", lambda: None)
        runtime.register_function("adopt", adopt)
        result = runtime.run_source(textwrap.dedent(src) + _DRIVER)
        self.assertTrue(result.get("ok"), result.get("error"))
        self.assertEqual(1, len(caught), "the restore was not refused")
        self.assertEqual("", result["stdout"], "the refused continuation ran anyway")
        return caught[0]

    def test_a_different_program_is_refused(self):
        _, data = _run(self._SIMPLE, "fresh")
        edited = self._SIMPLE.replace('print("before")', 'print("before!")')
        self.assertIn("different program", self._restore_error(edited, data))

    def test_a_function_that_moved_is_refused_even_with_a_matching_program(self):
        """The fingerprint is the first line of defence and the per-function
        address the second. Tampered data checks the second on its own."""
        _, data = _run(self._SIMPLE, "fresh")
        data["entry"]["addr"] += 1
        self.assertIn("has moved", self._restore_error(self._SIMPLE, data))

    _WITH_A_STEP = """
        workflow w { step s { print("STEP BODY RAN"); return 1i } }
        fn worker() {
            print("before")
            sleep(0i)
            print("after")
            return 1i
        }
        """

    def _step_body_ref(self) -> dict:
        runtime = NodusRuntime(timeout_ms=None, max_steps=None)
        for name in ("mode", "snap", "adopt"):
            runtime.register_function(name, (lambda: "idle") if name == "mode" else (lambda: None))
        self.assertTrue(runtime.run_source(textwrap.dedent(self._WITH_A_STEP) + _DRIVER).get("ok"))
        steps = [fn for fn in runtime.active_vm().functions.values() if fn.step_owner]
        self.assertEqual(1, len(steps), "expected exactly one step body")
        return {"name": steps[0].name, "addr": steps[0].addr}

    def _refused_by_the_step_guard(self, data) -> None:
        """#394: restore is a door into a function, so a continuation naming a
        step body must not run it outside its workflow."""
        runtime = NodusRuntime(timeout_ms=None, max_steps=None)
        caught = []

        def adopt():
            try:
                restore_continuation(runtime.active_vm(), data)
            except Exception as exc:  # the guard's own error, not ours
                caught.append(str(exc))

        runtime.register_function("mode", lambda: "resume")
        runtime.register_function("snap", lambda: None)
        runtime.register_function("adopt", adopt)
        result = runtime.run_source(textwrap.dedent(self._WITH_A_STEP) + _DRIVER)
        self.assertTrue(result.get("ok"), result.get("error"))
        self.assertEqual(1, len(caught), "a continuation naming a step body was restored")
        self.assertIn("cannot be called directly", caught[0])
        self.assertNotIn("STEP BODY RAN", result["stdout"])

    def test_a_step_body_named_as_the_entry_is_refused(self):
        _, data = _run(self._WITH_A_STEP, "fresh")
        data["entry"] = self._step_body_ref()
        data["frames"][0]["function"] = data["entry"]
        self._refused_by_the_step_guard(data)

    def test_a_step_body_named_in_a_deeper_frame_is_refused(self):
        """The resume re-checks the entry closure; nothing re-checks a deeper
        frame, so this is the case the restore's own guard exists for."""
        _, data = _run(self._WITH_A_STEP, "fresh")
        frame = dict(data["frames"][0])
        frame["function"] = self._step_body_ref()
        frame["fn_name"] = frame["function"]["name"]
        frame["slots"] = None
        data["frames"].append(frame)
        self._refused_by_the_step_guard(data)

    def test_a_frame_of_an_unknown_function_is_refused(self):
        _, data = _run(self._SIMPLE, "fresh")
        data["frames"][0]["function"] = None
        data["frames"][0]["fn_name"] = "no_such_fn"
        self.assertIn("not a function of this program", self._restore_error(self._SIMPLE, data))

    def test_a_format_1_continuation_is_still_read(self):
        """/2 only added the list iterator (#911). Data written as /1 holds
        none, so it means the same thing and is restored, not refused."""
        _, data = _run(self._SIMPLE, "fresh")
        self.assertEqual(FORMAT, data["format"])
        data["format"] = "nodus-continuation/1"
        result, _ = _run(self._SIMPLE, "resume", data)
        self.assertEqual("after\n", result["stdout"])

    def test_an_unknown_format_is_refused(self):
        _, data = _run(self._SIMPLE, "fresh")
        data["format"] = "nodus-continuation/0"
        self.assertIn(FORMAT, self._restore_error(self._SIMPLE, data))


class AcrossTwoProcessesTests(unittest.TestCase):
    """The claim a store will rest on: the data written by one process means the
    same thing to another. Each side has its own hash seed, which is what would
    make an unstable program fingerprint show up."""

    _PROGRAM = textwrap.dedent("""
        fn worker() {
            let seen = {"a": [1i, 2i], "b": 2.5}
            print("before")
            sleep(0i)
            print("after \\(len(seen["a"])) \\(seen["b"])")
            return 1i
        }
        """)

    def _side(self, mode: str, tmp: Path, seed: str) -> str:
        script = textwrap.dedent(f"""
            import json, sys
            sys.path.insert(0, {str(_REPO_ROOT / "src")!r})
            sys.path.insert(0, {str(_REPO_ROOT / "tests")!r})
            from test_continuation_roundtrip import _run
            from pathlib import Path
            store = Path({str(tmp / "continuation.json")!r})
            src = {self._PROGRAM!r}
            if {mode!r} == "fresh":
                result, data = _run(src, "fresh")
                store.write_text(json.dumps(data), encoding="utf-8")
            else:
                result, _ = _run(src, "resume", json.loads(store.read_text(encoding="utf-8")))
            assert result.get("ok"), result.get("error")
            sys.stdout.write("OUT " + json.dumps(result["stdout"]))
        """)
        import os
        env = dict(os.environ, PYTHONHASHSEED=seed)
        proc = subprocess.run([sys.executable, "-c", script], capture_output=True,
                              text=True, timeout=120, cwd=str(tmp), env=env)
        self.assertEqual(0, proc.returncode, proc.stderr[-1500:])
        return json.loads(proc.stdout.split("OUT ", 1)[1])

    def test_a_continuation_written_by_one_process_resumes_in_another(self):
        with tempfile.TemporaryDirectory() as tmp:
            before = self._side("fresh", Path(tmp), seed="1")
            after = self._side("resume", Path(tmp), seed="2")
        self.assertEqual("before\n", before)
        self.assertEqual("after 2 2.5\n", after)


if __name__ == "__main__":
    unittest.main()
