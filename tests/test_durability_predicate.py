"""#180 stage 2: a durability check over a live coroutine that says *why*.

`nodus.runtime.durability.assess_coroutine` reads a running or suspended
coroutine and lists every obstacle to writing its continuation down, each with
where it is. Nothing is persisted; stage 3 is what tries.

Each test drives a real program through `NodusRuntime` and assesses the
coroutine from inside it, via a host function, because the design is a claim
about what a live coroutine holds and a hand-built `Coroutine` would only test
what the author expected it to hold. The one exception is the bundled-module
prefix, which the default loader does not produce.

`OBSTACLE_KINDS` is the vocabulary, and `_CASES` must cover it exactly, so a new
kind cannot be added without a program that produces it.
"""

import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from types import SimpleNamespace

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))  # noqa: E402

from nodus.runtime.durability import (  # noqa: E402
    OBSTACLE_KINDS,
    DurabilityReport,
    Obstacle,
    _entry_identity_problem,
    assess_coroutine,
)
from nodus.runtime.embedding import NodusRuntime  # noqa: E402


def _assess(src: str, *, every_task: bool = False) -> dict:
    """Run `src`; each `probe("label")` records a report under that label.

    With `every_task`, the probe instead assesses every coroutine the
    scheduler knows, keyed by entry name, which is how a coroutine that cannot
    call the probe itself (a blocked one, a finished one) gets assessed.
    """
    reports: dict = {}
    runtime = NodusRuntime(timeout_ms=None, max_steps=None)

    def probe(label):
        vm = runtime.active_vm()
        if every_task:
            for task in vm.scheduler.tasks.values():
                reports[task.closure.function.display_name] = assess_coroutine(task)
        else:
            reports[label] = assess_coroutine(vm.current_coroutine)
        return None

    runtime.register_function("probe", probe)
    result = runtime.run_source(textwrap.dedent(src))
    assert result.get("ok"), result.get("error")
    return reports


def _only(report: DurabilityReport, kind: str) -> Obstacle:
    matching = [o for o in report.obstacles if o.kind == kind]
    assert len(matching) == 1, report.explain()
    return matching[0]


# kind -> (program, label to read, expected `where`, a phrase the detail must hold)
_CASES = {
    "not_resumable": ("""
        fn done() { return 1i }
        fn inspector() { probe("x"); return 1i }
        spawn(coroutine(done))
        run_loop()
        spawn(coroutine(inspector))
        run_loop()
        """, "done", "coroutine", "finished", True),
    "workflow_step": ("""
        workflow w { step s { probe("step"); return 1i } }
        run_workflow(w)
        """, "step", "coroutine", "w.s", False),
    "blocked": ("""
        let ch = channel()
        fn waiter() { let v = recv(ch); return v }
        fn inspector() { probe("x"); send(ch, 1i); return 1i }
        spawn(coroutine(waiter))
        spawn(coroutine(inspector))
        run_loop()
        """, "waiter", "coroutine", "channel_recv", True),
    "unnamed_entry": ("""
        spawn(fn() { probe("anon"); return 1i })
        run_loop()
        """, "anon", None, "anonymous function", False),
    "captured_cell": ("""
        fn make(b) { return fn() { probe("closure"); return b } }
        fn named() { return 1i }
        spawn(coroutine(make(3i)))
        run_loop()
        """, "closure", None, "captures `b`", False),
    "live_value": ("""
        fn holds() { let ch = channel(); probe("ch"); return 1i }
        spawn(coroutine(holds))
        run_loop()
        """, "ch", "frame 0 (`holds`), local `ch`", "a channel", False),
    "shared_with_module": ("""
        let shared = [1i]
        fn alias() { let t = {"inner": shared}; probe("alias"); return 1i }
        spawn(coroutine(alias))
        run_loop()
        """, "alias", 'frame 0 (`alias`), local `t`, at `t["inner"]`', "module-level `shared`", False),
}


class EachObstacleTests(unittest.TestCase):

    def test_the_cases_cover_the_vocabulary_exactly(self):
        self.assertEqual(set(OBSTACLE_KINDS), set(_CASES))

    def test_each_kind_is_reported_where_it_is(self):
        for kind, (src, label, where, phrase, every_task) in _CASES.items():
            with self.subTest(kind):
                report = _assess(src, every_task=every_task)[label]
                self.assertFalse(report.durable, report.explain())
                obstacle = _only(report, kind)
                if where is not None:
                    self.assertEqual(where, obstacle.where)
                self.assertIn(phrase, obstacle.detail)

    def test_an_unknown_kind_cannot_be_constructed(self):
        with self.assertRaises(ValueError):
            Obstacle("typo", "somewhere", "detail")


class DurableControlTests(unittest.TestCase):
    """Without these, every test above passes on a check that refuses everything."""

    def test_plain_data_is_durable(self):
        report = _assess("""
            fn clean() {
                let n = 1i
                let f = 2.5
                let s = "text"
                let m = {"k": [1i, 2i], "nested": {"deep": nil}}
                let r = {x: [m], ok: true}
                probe("clean")
                return n
            }
            spawn(coroutine(clean))
            run_loop()
            """)["clean"]
        self.assertTrue(report.durable, report.explain())
        self.assertIn("durable", report.explain())

    def test_sharing_and_cycles_inside_the_continuation_are_durable(self):
        """A serialiser keeps sharing within one snapshot with a memo, as
        `copy()` does. Only sharing with something *outside* it is a split."""
        report = _assess("""
            fn cyc() {
                let a = [1i]
                list_push(a, a)
                let b = a
                let m = {"one": a, "two": b}
                probe("cyc")
                return 1i
            }
            spawn(coroutine(cyc))
            run_loop()
            """)["cyc"]
        self.assertTrue(report.durable, report.explain())

    def test_a_module_scalar_read_into_a_local_is_durable(self):
        """A scalar has no identity to split; only containers can alias."""
        report = _assess("""
            let limit = 5i
            fn reads() { let l = limit; probe("r"); return l }
            spawn(coroutine(reads))
            run_loop()
            """)["r"]
        self.assertTrue(report.durable, report.explain())

    def test_a_named_entry_in_an_imported_module_is_identified(self):
        """The module loader gives it its plain name and the coroutine records
        its module, so (module, name) finds it. Asserted because the obvious
        rule -- 'only the main module's functions are nameable' -- refuses it."""
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "lib.nd").write_text(textwrap.dedent("""
                fn work() { sleep(1i); return 1i }
                export fn start() { spawn(coroutine(work)); return 1i }
                """), encoding="utf-8")
            main = Path(tmp, "main.nd")
            main.write_text(textwrap.dedent("""
                import "./lib.nd" as lib
                fn inspector() { probe("x"); return 1i }
                lib.start()
                spawn(coroutine(inspector))
                run_loop()
                """), encoding="utf-8")
            reports: dict = {}
            runtime = NodusRuntime(timeout_ms=None, max_steps=None)

            def probe(_label):
                for task in runtime.active_vm().scheduler.tasks.values():
                    reports[task.closure.function.display_name] = (
                        assess_coroutine(task), task.module)

            runtime.register_function("probe", probe)
            result = runtime.run_file(str(main))
            self.assertTrue(result.get("ok"), result.get("error"))
        report, module = reports["work"]
        self.assertTrue(os.path.basename(module).startswith("lib"), module)
        self.assertNotIn("unnamed_entry", report.kinds(), report.explain())


class WhyNotJustWhetherTests(unittest.TestCase):

    def test_every_obstacle_is_reported_not_just_the_first(self):
        report = _assess("""
            let shared = {"k": 1i}
            fn make(b) {
                return fn() {
                    let ch = channel()
                    let s = shared
                    for x in [1i] { probe("all") }
                    return b
                }
            }
            spawn(coroutine(make(1i)))
            run_loop()
            """)["all"]
        self.assertEqual(
            {"unnamed_entry", "captured_cell", "live_value", "shared_with_module"},
            report.kinds(), report.explain())
        live = sorted(o.where for o in report.obstacles if o.kind == "live_value")
        # The `for` loop's list iterator is data since #911, so the channel is
        # the only live value here.
        self.assertEqual(["frame 0 (`__anon_1`), local `ch`"], live)

    def test_a_captured_variable_is_reported_from_both_sides(self):
        """The frame that owns a captured variable holds a Cell, and the closure
        that captured it is a live value. Either alone would be enough to refuse,
        and a fix for one must not hide the other."""
        report = _assess("""
            fn cap() {
                let n = 0i
                let bump = fn() { n += 1i; return n }
                bump()
                probe("cap")
                return n
            }
            spawn(coroutine(cap))
            run_loop()
            """)["cap"]
        by_where = {o.where: o.kind for o in report.obstacles}
        self.assertEqual("captured_cell", by_where.get("frame 0 (`cap`), local `n`"), report.explain())
        self.assertEqual("live_value", by_where.get("frame 0 (`cap`), local `bump`"), report.explain())

    def test_a_nested_named_function_is_not_reachable_by_name(self):
        report = _assess("""
            fn outer() {
                fn inner() { probe("inner"); return 1i }
                return inner
            }
            spawn(coroutine(outer()))
            run_loop()
            """)["inner"]
        self.assertIn("inside another function", _only(report, "unnamed_entry").detail)

    def test_a_step_reports_only_that_it_is_a_step(self):
        """A step body is always anonymous; saying so as well adds noise to the
        one finding that matters."""
        report = _assess(_CASES["workflow_step"][0])["step"]
        self.assertEqual({"workflow_step"}, report.kinds(), report.explain())

    def test_a_bundled_module_prefix_is_an_index_not_a_name(self):
        """The default loader does not produce `__modN__` names, so this one is
        checked on the entry-identity rule directly."""
        fn = SimpleNamespace(name="__mod0__work", display_name="work")
        self.assertIn("import order", _entry_identity_problem(fn))
        self.assertIsNone(_entry_identity_problem(
            SimpleNamespace(name="work", display_name="work")))


# A user-defined iterator: a record whose `__next__` closure keeps the position.
_COUNTDOWN = """
fn countdown(n) {
    let state = {left: n}
    return {__next__: fn(r) {
        if (state.left <= 0i) { return nil }
        state.left = state.left - 1i
        return state.left
    }}
}
"""


class AFor_LoopOverAListIsDataTests(unittest.TestCase):
    """Design §3.2 said the operand stack is empty at every statement boundary.
    Inside a `for` body it is not: GET_ITER leaves the loop's iterator there for
    the whole body. Stage 2 found that and refused it. #911 gave the iterator
    over a list a written form -- the list and an index -- so it is walked like
    any other value. An iterator driven by a user-defined `__next__` keeps its
    position in user code and is still refused, by name."""

    def test_a_loop_over_a_list_is_durable(self):
        report = _assess("""
            fn batch() {
                for job in [1i, 2i] { probe("in-for") }
                return 1i
            }
            spawn(coroutine(batch))
            run_loop()
            """)["in-for"]
        self.assertTrue(report.durable, report.explain())

    def test_nested_loops_and_a_list_from_iter_are_durable(self):
        report = _assess("""
            fn batch() {
                let grid = {__iter__: fn(r) { return [[1i, 2i], [3i]] }}
                for row in grid { for cell in row { probe("nested") } }
                return 1i
            }
            spawn(coroutine(batch))
            run_loop()
            """)["nested"]
        # The record holding `__iter__` is a local with a function in it, which
        # is a live value of its own. The two iterators on the stack are not.
        self.assertEqual(
            ["frame 0 (`batch`), local `grid`, at `grid.__iter__`"],
            [o.where for o in report.obstacles], report.explain())

    def test_a_loop_over_a_module_level_list_is_sharing_and_is_caught(self):
        """The iterator holds the list it walks. If that list is module state,
        a resume would walk a copy, so the module-sharing rule applies to it."""
        report = _assess("""
            let jobs = [1i, 2i]
            fn batch() {
                for job in jobs { probe("module-list") }
                return 1i
            }
            spawn(coroutine(batch))
            run_loop()
            """)["module-list"]
        obstacle = _only(report, "shared_with_module")
        self.assertEqual("operand stack slot 0", obstacle.where)
        self.assertIn("module-level `jobs`", obstacle.detail)

    def test_a_loop_over_a_user_defined_iterator_is_refused_by_name(self):
        report = _assess(_COUNTDOWN + """
            fn batch() {
                for n in countdown(2i) { probe("custom") }
                return 1i
            }
            spawn(coroutine(batch))
            run_loop()
            """)["custom"]
        stack = [o for o in report.obstacles if o.where == "operand stack slot 0"]
        self.assertEqual(1, len(stack), report.explain())
        self.assertEqual("live_value", stack[0].kind)
        self.assertIn("user-defined iterator", stack[0].detail)

    def test_after_the_loop_the_stack_is_clear_again(self):
        report = _assess("""
            fn batch() {
                for job in [1i, 2i] { let x = job }
                probe("after")
                return 1i
            }
            spawn(coroutine(batch))
            run_loop()
            """)["after"]
        self.assertTrue(report.durable, report.explain())


class TheCheckOnlyReadsTests(unittest.TestCase):

    def test_assessing_does_not_change_the_program_or_the_answer(self):
        src = textwrap.dedent("""
            fn worker() {
                let ch = channel()
                let total = 0i
                for x in [1i, 2i, 3i] { total += x; probe("p") }
                print("total=\\(total)")
                return total
            }
            spawn(coroutine(worker))
            run_loop()
            """)
        seen = []
        runtime = NodusRuntime(timeout_ms=None, max_steps=None)

        def probe(_label):
            co = runtime.active_vm().current_coroutine
            first, second = assess_coroutine(co), assess_coroutine(co)
            seen.append(first == second)
            return None

        runtime.register_function("probe", probe)
        result = runtime.run_source(src)
        self.assertTrue(result.get("ok"), result.get("error"))
        self.assertEqual("total=6", result["stdout"].strip())
        self.assertEqual([True, True, True], seen)


if __name__ == "__main__":
    unittest.main()
