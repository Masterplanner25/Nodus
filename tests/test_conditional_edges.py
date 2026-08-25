"""A conditional edge says so, in the plan and in the diagram (#471, #537).

Two different things make a workflow edge conditional, and through v5.2.0 the
plan object recorded neither:

* `with { on: [...] }` -- which dependency outcomes let the step run (#537)
* `when <predicate>`   -- a guard on the step itself (#471)

So `plan_workflow` rendered a guarded edge identically to an unguarded one, and
`nodus graph show` drew both as plain arrows. The renderer was right to refuse to
guess -- an unconditional arrow for a conditional edge is a lie a diagram tells
convincingly -- but the information had to reach it first.

Both are reported as *additional* keys rather than by reshaping `edges`, which
the CLI, the tests and anything reading `plan_workflow()` already consume.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus.orchestration.graph_render import to_dot, to_mermaid  # noqa: E402
from nodus.runtime.embedding import NodusRuntime  # noqa: E402


WORKFLOW = """
workflow deploy {
    step build { checkpoint "flaky"; return "ok" }
    step notify after build with { on: ["failed"] } { return "alerted" }
    step verify after build when reached("flaky") { return "checked" }
    step done after build { return "fin" }
}
"""


def plan() -> dict:
    """The plan `deploy` produces, as a Python dict."""
    runtime = NodusRuntime(timeout_ms=None)
    result = runtime.run_source(WORKFLOW + "\nlet p = plan_workflow(deploy)\n")
    assert result["ok"], result.get("error")
    return runtime.active_vm().last_graph_plan


class PlanRecordsConditionalityTests(unittest.TestCase):
    def setUp(self):
        self.plan = plan()

    # closes: #471
    def test_a_when_guarded_edge_is_listed(self):
        self.assertEqual(self.plan["conditional_edges"], [["build", "verify"]])

    # closes: #537
    def test_a_non_default_on_filter_is_recorded(self):
        self.assertEqual(self.plan["edge_conditions"], {"build->notify": ["failed"]})

    def test_the_default_on_filter_is_not_recorded(self):
        """Labelling every edge `completed` would be noise.

        Absence carries the meaning instead, which is stated in TASK_GRAPHS.md
        rather than left for a reader to infer.
        """
        self.assertNotIn("build->done", self.plan["edge_conditions"])
        self.assertNotIn("build->verify", self.plan["edge_conditions"])

    def test_edges_is_unchanged(self):
        """The whole point of additive keys: existing consumers keep working."""
        self.assertEqual(
            self.plan["edges"],
            [["build", "notify"], ["build", "verify"], ["build", "done"]],
        )

    def test_levels_is_unchanged(self):
        """`levels` stays the topological partition, not a prediction.

        A guarded step is in it whether or not the guard will hold -- so it is a
        superset, and `conditional_edges` is what says which parts are in doubt.
        """
        # Order within a level is not meaningful -- the members run concurrently,
        # and the plan builds each level from a set. Compare the partition.
        self.assertEqual(
            [set(level) for level in self.plan["levels"]],
            [{"build"}, {"notify", "verify", "done"}],
        )

    def test_the_two_kinds_do_not_bleed_into_each_other(self):
        """`on:` and `when` are different questions about the same edge."""
        guarded = {tuple(edge) for edge in self.plan["conditional_edges"]}
        filtered = set(self.plan["edge_conditions"])
        self.assertEqual(guarded, {("build", "verify")})
        self.assertEqual(filtered, {"build->notify"})


class RenderingTests(unittest.TestCase):
    def setUp(self):
        self.plan = plan()

    # closes: #537
    def test_mermaid_labels_a_filtered_edge(self):
        self.assertIn("|failed|", to_mermaid(self.plan))

    # closes: #471
    def test_mermaid_dashes_a_guarded_edge(self):
        mermaid = to_mermaid(self.plan)
        self.assertIn("-.->", mermaid)
        guarded_line = next(line for line in mermaid.splitlines() if "-.->" in line)
        self.assertNotIn("|", guarded_line, "an unlabelled guard needs no label slot")

    def test_mermaid_leaves_a_plain_edge_plain(self):
        lines = [line.strip() for line in to_mermaid(self.plan).splitlines()]
        plain = [line for line in lines if line.endswith("--> n3")]
        self.assertEqual(len(plain), 1, "the unconditional edge must stay unadorned")

    # closes: #537
    def test_dot_labels_a_filtered_edge(self):
        self.assertIn('[label="failed"]', to_dot(self.plan))

    # closes: #471
    def test_dot_dashes_a_guarded_edge(self):
        self.assertIn("[style=dashed]", to_dot(self.plan))

    def test_an_older_plan_without_the_keys_still_renders(self):
        """A stored plan from before these keys existed knows only the topology.

        Rendering it as plain arrows is then correct, not a regression -- so the
        renderer must not require the keys it now prefers.
        """
        old = {"nodes": ["a", "b"], "edges": [["a", "b"]], "graph_id": "g_old"}
        self.assertIn("-->", to_mermaid(old))
        self.assertIn("->", to_dot(old))

    def test_a_label_cannot_break_out_of_the_diagram(self):
        """Step names are user-authored and reach the renderer unfiltered."""
        hostile = {
            "nodes": ["a", "b"],
            "edges": [["a", "b"]],
            "edge_conditions": {"a->b": ['"] evil ["']},
            "graph_id": "g",
        }
        self.assertNotIn('"] evil ["', to_mermaid(hostile))
        self.assertNotIn('"] evil ["', to_dot(hostile))


class PredicateErrorNamesItsClauseTests(unittest.TestCase):
    """`step … when` was refused with a sentence about goal `until` (#471).

    Both clauses share a grammar and a parser, so the error named the parser's
    original caller rather than what the author wrote -- pointing at a construct
    that appears nowhere in their program.
    """

    def _error(self, source: str) -> str:
        result = NodusRuntime(timeout_ms=None).run_source(source)
        self.assertFalse(result["ok"])
        return result["errors"][0]["message"]

    # closes: #471
    def test_a_step_guard_error_names_when(self):
        message = self._error(
            "workflow w { step a { return 1i } "
            "step b after a when (a < 5i) { return 2i } }\nfn main() { }"
        )
        self.assertIn("step guard `when`", message)
        self.assertNotIn("goal `until`", message)

    # closes: #471
    def test_a_step_guard_error_points_at_the_idiom(self):
        """A refusal with no route forward reads as a missing feature.

        Branching on data *is* expressible -- record the checkpoint
        conditionally -- so the error has to say so.
        """
        message = self._error(
            "workflow w { step a { return 1i } "
            "step b after a when (a < 5i) { return 2i } }\nfn main() { }"
        )
        self.assertIn("checkpoint", message)
        self.assertIn("reached(", message)

    def test_a_goal_until_error_still_names_until(self):
        message = self._error(
            'workflow w { step a { checkpoint "c"; return 1i } }\n'
            "goal g over w { until (a < 5i) }\nfn main() { }"
        )
        self.assertIn("goal `until`", message)
        self.assertNotIn("step guard", message)


class GuardBehaviourTests(unittest.TestCase):
    """What the shipped `when` already decided, pinned so it stays decided."""

    def _statuses(self, record_checkpoint: str) -> dict:
        result = NodusRuntime(timeout_ms=None).run_source("""
workflow w {
    step a { if (%s) { checkpoint "maybe" } return 1i }
    step b after a { return 2i }
    step c after a when reached("maybe") { return 3i }
    step d after b, c { return 4i }
}
fn main() {
    let r = run_workflow(w)
    print("\\(r["statuses"])")
}
""" % record_checkpoint)
        self.assertTrue(result["ok"], result.get("error"))
        return result["stdout"]

    def test_a_failing_guard_skips_the_step_and_its_dependents(self):
        statuses = self._statuses("false")
        self.assertIn('"c": "skipped"', statuses)
        self.assertIn('"d": "skipped"', statuses)

    def test_a_holding_guard_runs_everything(self):
        statuses = self._statuses("true")
        self.assertIn('"c": "completed"', statuses)
        self.assertIn('"d": "completed"', statuses)

    def test_a_join_can_opt_into_a_skipped_dependency(self):
        result = NodusRuntime(timeout_ms=None).run_source("""
workflow w {
    step a { if (false) { checkpoint "maybe" } return 1i }
    step b after a { return 2i }
    step c after a when reached("maybe") { return 3i }
    step d after b, c with { on: ["completed", "skipped"] } { return 4i }
}
fn main() { let r = run_workflow(w); print("\\(r["statuses"])") }
""")
        self.assertTrue(result["ok"], result.get("error"))
        self.assertIn('"c": "skipped"', result["stdout"])
        self.assertIn('"d": "completed"', result["stdout"])


if __name__ == "__main__":
    unittest.main()
