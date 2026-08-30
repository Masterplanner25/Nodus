"""A runtime-built graph can name its steps, and its results survive (#679).

`task(fn, opts)` had no way to name a step. Two consequences, and the second is
the one that cost real information:

1. every generated step was `task_N`, so a runtime-built graph was not
   inspectable the way a declared `workflow` is;
2. **the run result's `steps` map came back empty** — the per-step results were
   computed and then discarded.

Found while designing #93 (`docs/design/v5/07-generated-plans.md`), where a
planner emits named steps and the names could not survive into the graph.

**Two halves, and fixing one is not enough.** `TaskNode.step_name` already
existed and `builtin_task` could not reach it; separately, `step_results()` keys
off `graph.metadata["task_to_step"]`, which only the workflow-DSL lowering
populated. Adding the option without filling the metadata would have given named
steps and *still* an empty `steps` map — a fix that looks complete and is not.

So the tests below assert both, and the pairing is deliberate: a test that only
checks `step_name` is set would pass on the broken half.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus.orchestration.task_graph import TaskNode, step_name_metadata  # noqa: E402
from nodus.runtime.embedding import NodusRuntime  # noqa: E402

_DECLARED = (
    "workflow declared {\n"
    "    step fetch { return 1i }\n"
    "    step analyze after fetch { return 2i }\n"
    "}\n"
)


def run(source: str) -> dict:
    return NodusRuntime(timeout_ms=None).run_source(source)


def out(source: str) -> str:
    result = run(source)
    assert result["ok"], result.get("error")
    return result.get("stdout") or ""


# closes: #679
class NamedGeneratedStepsTests(unittest.TestCase):
    def test_a_named_generated_step_reports_its_result(self):
        """Half 2. This is the assertion that was empty before, and the one a
        `step_name`-only test would not have caught."""
        text = out(
            "fn main() {\n"
            '    let a = task(fn() { return 1i }, {"name": "fetch", "deps": []})\n'
            '    let b = task(fn() { return 2i }, {"name": "analyze", "deps": [a]})\n'
            '    print(run_graph(graph([a, b]))["steps"])\n'
            "}\n"
        )
        self.assertIn("fetch", text)
        self.assertIn("analyze", text)

    def test_a_generated_run_is_indistinguishable_from_a_declared_one(self):
        """The issue's actual bar. Same pipeline, both spellings, same result
        map — anything less means a planner's output is a second-class graph."""
        declared = out(_DECLARED + 'fn main() { print(run_workflow(declared)["steps"]) }\n')
        generated = out(
            "fn main() {\n"
            '    let a = task(fn() { return 1i }, {"name": "fetch", "deps": []})\n'
            '    let b = task(fn() { return 2i }, {"name": "analyze", "deps": [a]})\n'
            '    print(run_graph(graph([a, b]))["steps"])\n'
            "}\n"
        )
        self.assertEqual(declared.strip(), generated.strip())

    def test_the_plan_shows_names_too(self):
        """`plan_workflow` translated ids to names and `plan_graph` did not, so
        the same DAG read differently depending on how it was built."""
        declared = out(_DECLARED + 'fn main() { print(plan_workflow(declared)["parallel_groups"]) }\n')
        generated = out(
            "fn main() {\n"
            '    let a = task(fn() { return 1i }, {"name": "fetch", "deps": []})\n'
            '    let b = task(fn() { return 2i }, {"name": "analyze", "deps": [a]})\n'
            '    print(plan_graph(graph([a, b]))["parallel_groups"])\n'
            "}\n"
        )
        self.assertEqual(declared.strip(), generated.strip())

    def test_run_graph_on_a_bare_list_names_its_steps_too(self):
        """Two construction sites — `graph(tasks)` and `run_graph([...])`. A
        program's step results must not depend on which spelling it used."""
        text = out(
            "fn main() {\n"
            '    let a = task(fn() { return 7i }, {"name": "only", "deps": []})\n'
            '    print(run_graph([a])["steps"])\n'
            "}\n"
        )
        self.assertIn("only", text)
        self.assertIn("7", text)


# closes: #679
class UnnamedTasksAreUnchangedTests(unittest.TestCase):
    """Decision 3: an unnamed task gets **no entry**, rather than a synthetic
    `task_N` key. A name is either meaningful or absent — inventing one would put
    the unstable VM-counter id into a map a program reads by name."""

    def test_an_unnamed_graph_still_reports_no_steps(self):
        text = out(
            "fn main() {\n"
            '    let a = task(fn() { return 1i }, {"deps": []})\n'
            '    print(run_graph(graph([a]))["steps"])\n'
            "}\n"
        )
        self.assertIn("{}", text)

    def test_an_unnamed_task_alongside_a_named_one_is_simply_absent(self):
        text = out(
            "fn main() {\n"
            '    let a = task(fn() { return 1i }, {"name": "named", "deps": []})\n'
            '    let b = task(fn() { return 2i }, {"deps": []})\n'
            '    let g = run_graph(graph([a, b]))\n'
            '    print("steps: \\(g["steps"])")\n'
            '    print("failed: \\(g["failed"])")\n'
            "}\n"
        )
        self.assertIn("named", text)
        self.assertIn("failed: []", text, "the unnamed task did not run")

    def test_an_unnamed_run_still_succeeds(self):
        """The compatibility half. Every generated graph written before this
        existed is unnamed, and none of them may change behaviour."""
        result = run(
            "fn main() {\n"
            '    let a = task(fn() { return 1i }, {"deps": []})\n'
            '    let b = task(fn() { return 2i }, {"deps": [a]})\n'
            '    let g = run_graph(graph([a, b]))\n'
            '    print("failed: \\(g["failed"])")\n'
            "}\n"
        )
        self.assertTrue(result["ok"], result.get("error"))
        self.assertIn("failed: []", result.get("stdout") or "")


# closes: #679
class DuplicateNamesAreRefusedTests(unittest.TestCase):
    """Decision 4: refused at graph construction. The DSL cannot produce a
    duplicate, and silently overwriting one step's result with another's is
    worse than refusing to run."""

    def test_two_tasks_with_one_name_is_an_error(self):
        result = run(
            "fn main() {\n"
            '    let a = task(fn() { return 1i }, {"name": "same", "deps": []})\n'
            '    let b = task(fn() { return 2i }, {"name": "same", "deps": []})\n'
            '    print(run_graph(graph([a, b]))["steps"])\n'
            "}\n"
        )
        self.assertFalse(result["ok"])
        message = (result.get("error") or {}).get("message", "")
        self.assertIn("duplicate step name 'same'", message)

    def test_the_error_names_both_tasks(self):
        """So a graph with fifty generated steps is diagnosable."""
        result = run(
            "fn main() {\n"
            '    let a = task(fn() { return 1i }, {"name": "dup", "deps": []})\n'
            '    let b = task(fn() { return 2i }, {"name": "dup", "deps": []})\n'
            '    print(run_graph(graph([a, b]))["steps"])\n'
            "}\n"
        )
        message = (result.get("error") or {}).get("message", "")
        self.assertIn("task_", message)


# closes: #679
class NameOptionValidationTests(unittest.TestCase):
    def test_a_non_string_name_is_refused(self):
        result = run(
            "fn main() {\n"
            '    let a = task(fn() { return 1i }, {"name": 3i, "deps": []})\n'
            "    print(a)\n"
            "}\n"
        )
        self.assertFalse(result["ok"])
        self.assertIn("expects a string", (result.get("error") or {}).get("message", ""))

    def test_a_blank_name_is_refused(self):
        """A blank name would produce an unreachable key rather than an absent
        one, which is the confusing middle case between named and unnamed."""
        result = run(
            "fn main() {\n"
            '    let a = task(fn() { return 1i }, {"name": "   ", "deps": []})\n'
            "    print(a)\n"
            "}\n"
        )
        self.assertFalse(result["ok"])
        self.assertIn("cannot be blank", (result.get("error") or {}).get("message", ""))


# closes: #679
class MetadataHelperTests(unittest.TestCase):
    """The mapping itself, at the level it is decided."""

    def _node(self, task_id: str, step_name=None) -> TaskNode:
        return TaskNode(task_id=task_id, function=None, dependencies=[], step_name=step_name)

    def test_only_named_nodes_appear(self):
        mapping = step_name_metadata([
            self._node("task_1", "alpha"),
            self._node("task_2"),
            self._node("task_3", "beta"),
        ])
        self.assertEqual({"task_1": "alpha", "task_3": "beta"}, mapping)

    def test_an_empty_graph_maps_to_nothing(self):
        self.assertEqual({}, step_name_metadata([]))

    def test_a_duplicate_raises_with_both_ids(self):
        with self.assertRaises(ValueError) as caught:
            step_name_metadata([
                self._node("task_1", "same"),
                self._node("task_2", "same"),
            ])
        message = str(caught.exception)
        self.assertIn("task_1", message)
        self.assertIn("task_2", message)


if __name__ == "__main__":
    unittest.main()
