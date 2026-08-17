"""Two small backlog fixes, each with the mechanism already in the codebase.

#396 — `nodus check` reported `OK` for a workflow whose steps depend on each other
in a loop. Acyclicity is the one structural property of a workflow knowable from
the source alone, and the detector already existed: `_detect_cycle_task_ids` has
run at *execution* time since #323. The fix routes both callers through one
implementation rather than writing a second.

#425 — resuming a `graph_id` that does not exist reported *"is already claimed"*,
sending the reader to look for a concurrent run that was never there. A typo'd id
is far likelier than a claim conflict.

The interesting constraint on #396 is what the fix must *not* do. Detecting the
cycle in the parser also works — and breaks 14 tests in
`tests/test_cyclic_workflow_err.py`, because #323 deliberately made a cycle a
recoverable `err` record with `category: "cyclic_workflow"` that scripts inspect.
The right reading is that the runtime behaviour is load-bearing. `check` gains the
diagnosis; `run` keeps the error record. Both halves are pinned below.
"""

import unittest

from nodus.runtime.embedding import NodusRuntime
from nodus.support.graph_cycles import detect_cycle, format_cycle
from nodus.tooling.runner import check_source

CYCLIC = """
workflow w {
    step a after b { print("a") }
    step b after a { print("b") }
}
"""

ACYCLIC = """
workflow w {
    step a { print("a") }
    step b after a { print("b") }
    step c after b { print("c") }
}
"""


class TestCheckCatchesDependencyCycles(unittest.TestCase):
    # closes: #396
    def test_check_rejects_a_two_step_cycle(self):
        result = check_source(CYCLIC, filename="t.nd")
        self.assertFalse(result.get("ok"), result)
        msg = str(result["error"]["message"])
        self.assertIn("Dependency cycle", msg)
        self.assertIn("a -> b -> a", msg)

    def test_check_names_the_flow_it_found_the_cycle_in(self):
        """A file with several workflows should say which one is cyclic."""
        result = check_source(CYCLIC, filename="t.nd")
        self.assertIn("'w'", str(result["error"]["message"]))

    def test_check_rejects_a_self_cycle(self):
        result = check_source(
            'workflow w {\n    step a after a { print("a") }\n}\n', filename="t.nd"
        )
        self.assertFalse(result.get("ok"), result)
        self.assertIn("a -> a", str(result["error"]["message"]))

    def test_check_still_passes_an_acyclic_workflow(self):
        """Positive control. A check that rejected everything would satisfy the
        tests above and make `nodus check` useless."""
        result = check_source(ACYCLIC, filename="t.nd")
        self.assertTrue(result.get("ok"), result)

    def test_check_still_passes_a_file_with_no_workflow_at_all(self):
        result = check_source('let x = 1i\nprint(x)\n', filename="t.nd")
        self.assertTrue(result.get("ok"), result)

    def test_a_cycle_is_not_a_parse_error(self):
        """The constraint that shaped this fix.

        #323 made a cyclic workflow return an inspectable `err` record at run time,
        with `category: "cyclic_workflow"`. If the cycle were rejected by the
        parser, the program would never run and that contract would vanish —
        silently, since the only sign is 14 tests in another file going red.
        """
        rt = NodusRuntime(timeout_ms=None)
        try:
            result = rt.run_source(CYCLIC + "\nlet r = run_workflow(w)\n", filename="t.nd")
        finally:
            rt.shutdown()
        # It must reach execution: a parse failure would report stage "parse"/"compile".
        self.assertNotIn(result.get("stage"), ("parse", "compile"), result)

    def test_acyclic_workflow_still_runs_in_dependency_order(self):
        rt = NodusRuntime(timeout_ms=None)
        try:
            result = rt.run_source(
                ACYCLIC + '\nlet r = run_workflow(w)\nprint("failed: \\(r["failed"])")\n',
                filename="t.nd",
            )
        finally:
            rt.shutdown()
        self.assertTrue(result.get("ok"), result)
        out = result["stdout"]
        self.assertLess(out.index("a"), out.index("b"))
        self.assertLess(out.index("b"), out.index("c"))
        self.assertIn("failed: []", out)


class TestCycleDetectorIsShared(unittest.TestCase):
    """One implementation, two callers — assert on the source, not just behaviour."""

    def test_runtime_detector_delegates_to_the_shared_helper(self):
        import inspect

        from nodus.orchestration.task_graph import _detect_cycle_task_ids

        src = inspect.getsource(_detect_cycle_task_ids)
        # Assert on the *import*, not on the bare name: "detect_cycle" is a
        # substring of `_detect_cycle_task_ids` itself, so matching that would pass
        # against the old duplicated implementation too — a test that cannot fail.
        self.assertIn(
            "from nodus.support.graph_cycles import detect_cycle",
            src,
            "the runtime detector must delegate to support.graph_cycles, or the "
            "check-time and run-time notions of a cycle can drift (#396)",
        )
        self.assertNotIn(
            "def dfs",
            src,
            "the runtime detector still carries its own traversal; there should be "
            "one implementation, not two",
        )

    def test_detect_cycle_handles_the_shapes_that_matter(self):
        self.assertIsNone(detect_cycle({"a": [], "b": ["a"]}))
        self.assertIsNone(detect_cycle({}))
        self.assertEqual(detect_cycle({"a": ["a"]}), ["a"])
        self.assertIsNotNone(detect_cycle({"a": ["b"], "b": ["c"], "c": ["a"]}))
        # a diamond is not a cycle, though it revisits a node
        self.assertIsNone(detect_cycle({"d": ["b", "c"], "b": ["a"], "c": ["a"], "a": []}))

    def test_detect_cycle_survives_a_long_chain(self):
        """Iterative, not recursive: a deep chain must not raise RecursionError."""
        n = 5000
        adj = {f"s{i}": [f"s{i+1}"] for i in range(n)}
        adj[f"s{n}"] = []
        self.assertIsNone(detect_cycle(adj))

    def test_format_cycle_closes_the_loop(self):
        self.assertEqual(format_cycle(["a", "b"]), "a -> b -> a")
        self.assertEqual(format_cycle([]), "")


class TestResumeUnknownRunSaysNotFound(unittest.TestCase):
    # closes: #425
    def test_resuming_a_missing_run_reports_not_found(self):
        rt = NodusRuntime(timeout_ms=None)
        try:
            result = rt.run_source(
                'let r = resume_workflow("g_doesnotexist", "cp", {})\nprint(r)\n',
                filename="t.nd",
            )
        finally:
            rt.shutdown()
        self.assertTrue(result.get("ok"), result)
        out = result["stdout"]
        self.assertIn("not found", out)
        self.assertNotIn("already claimed", out)

    def test_the_message_names_the_run_that_was_missing(self):
        rt = NodusRuntime(timeout_ms=None)
        try:
            result = rt.run_source(
                'let r = resume_workflow("g_typo_here", "cp", {})\nprint(r)\n',
                filename="t.nd",
            )
        finally:
            rt.shutdown()
        self.assertIn("g_typo_here", result["stdout"])


if __name__ == "__main__":
    unittest.main()
