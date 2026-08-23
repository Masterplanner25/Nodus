"""`nodus graph show` -- rendering a planned graph as Mermaid or DOT.

The plan object was always there; only the projection is new.  These tests
pin the projection, and in particular that a user-authored step name can never
reach an identifier position in either output format.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))  # noqa: E402

from nodus.orchestration.graph_render import (  # noqa: E402
    FORMATS,
    GraphRenderError,
    render,
    to_dot,
    to_mermaid,
)

DIAMOND = {
    "workflow": "build",
    "graph_id": "g_abc123",
    "nodes": ["fetch", "compile", "lint", "package"],
    "edges": [
        ["fetch", "compile"],
        ["fetch", "lint"],
        ["compile", "package"],
        ["lint", "package"],
    ],
    "levels": [["fetch"], ["compile", "lint"], ["package"]],
}


class MermaidTests(unittest.TestCase):
    def test_emits_a_flowchart_with_every_node_and_edge(self):
        out = to_mermaid(DIAMOND)
        self.assertTrue(out.startswith("flowchart TD"))
        for name in DIAMOND["nodes"]:
            self.assertIn(f'["{name}"]', out)
        self.assertEqual(out.count(" --> "), len(DIAMOND["edges"]))

    def test_title_comes_from_the_workflow_name(self):
        self.assertIn("%% build", to_mermaid(DIAMOND))

    def test_falls_back_to_graph_id_when_unnamed(self):
        plan = {"graph_id": "g_zzz", "nodes": ["a"], "edges": []}
        self.assertIn("%% g_zzz", to_mermaid(plan))

    def test_step_names_never_reach_an_identifier_position(self):
        """Node ids are generated; the name only appears inside a label."""
        plan = {
            "nodes": ['weird "name" [x]', "b"],
            "edges": [['weird "name" [x]', "b"]],
        }
        out = to_mermaid(plan)
        self.assertIn("n0[", out)
        self.assertIn("n0 --> n1", out)
        # Neither a quote nor a bracket survives into the label unescaped.
        label_line = next(ln for ln in out.splitlines() if ln.strip().startswith("n0["))
        self.assertNotIn('"name"', label_line)
        self.assertIn("#quot;", label_line)
        self.assertIn("#91;", label_line)


class DotTests(unittest.TestCase):
    def test_emits_a_digraph(self):
        out = to_dot(DIAMOND)
        self.assertTrue(out.startswith('digraph "build" {'))
        self.assertTrue(out.rstrip().endswith("}"))
        self.assertEqual(out.count(" -> "), len(DIAMOND["edges"]))

    def test_parallel_levels_become_rank_same_groups(self):
        """The one thing DOT gives that Mermaid does not: the levels line up."""
        out = to_dot(DIAMOND)
        self.assertIn("rank=same", out)
        # Only the two-member level is pinned; single-node levels need no rank.
        self.assertEqual(out.count("rank=same"), 1)

    def test_single_node_levels_are_not_ranked(self):
        plan = {"nodes": ["a", "b"], "edges": [["a", "b"]], "levels": [["a"], ["b"]]}
        self.assertNotIn("rank=same", to_dot(plan))

    def test_quotes_and_backslashes_in_names_are_escaped(self):
        plan = {"nodes": ['a"b', "c\\d"], "edges": []}
        out = to_dot(plan)
        self.assertIn('label="a\\"b"', out)
        self.assertIn('label="c\\\\d"', out)


class ErrorTests(unittest.TestCase):
    def test_rejects_an_object_that_is_not_a_plan(self):
        with self.assertRaises(GraphRenderError):
            to_mermaid({"ok": True, "result": None})

    def test_rejects_a_malformed_edge(self):
        with self.assertRaises(GraphRenderError):
            to_dot({"nodes": ["a"], "edges": [["a"]]})

    def test_rejects_an_edge_to_an_unknown_node(self):
        with self.assertRaises(GraphRenderError):
            to_mermaid({"nodes": ["a"], "edges": [["a", "ghost"]]})

    def test_rejects_an_unknown_format(self):
        with self.assertRaises(GraphRenderError):
            render(DIAMOND, "svg")

    def test_render_dispatches_every_declared_format(self):
        for fmt in FORMATS:
            self.assertTrue(render(DIAMOND, fmt).strip(), f"{fmt} rendered empty")


class EmptyGraphTests(unittest.TestCase):
    def test_a_graph_with_no_nodes_still_renders(self):
        plan = {"nodes": [], "edges": []}
        self.assertIn("flowchart TD", to_mermaid(plan))
        self.assertIn("digraph", to_dot(plan))


if __name__ == "__main__":
    unittest.main()
