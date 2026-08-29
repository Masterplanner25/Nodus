"""`fmt` preserves every field of every node it renders (#656).

`test_formatter_completeness.py` walks the AST **node list** and fails when a node
*type* has no formatter case. That is what stops a new node from being silently
corrupted, and it works.

It cannot see a new **field** on an existing node. `each_var` / `each_source` were
added to `WorkflowStep` by #480 and the completeness test stayed green, because
the node was still "handled" — while `fmt` rewrote `each page in discover` as
`after discover` and dropped the loop variable. The result still parsed, still
ran, and reported `ok: true` while producing different output:

    original    {"discover": [1, 2], "render": [10, 20]}
    after fmt   {"discover": [1, 2]}

This closes that gap at the level it lives on. It parses a corpus, formats it,
re-parses, and compares the two ASTs **structurally** — every field, recursively.
`Base` excludes `_tok` and `_module` from `__eq__`, so node equality is exactly
the structural comparison this needs.

Any field added to any node from here on is covered by construction: if the
formatter does not render it, the re-parsed tree differs and this fails, naming
the case.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus.frontend.lexer import tokenize  # noqa: E402
from nodus.frontend.parser import Parser  # noqa: E402
from nodus.tooling.formatter import format_source  # noqa: E402

#: Each entry exercises a *field*, not just a node type. Add to this whenever a
#: node gains one — that is cheaper than rediscovering #656.
CORPUS = {
    "mapped step": """
workflow w {
    step discover { return [1i] }
    step render each page in discover { return page }
}
""",
    "mapped step with a downstream join": """
workflow w {
    step discover { return [1i] }
    step render each page in discover { return page }
    step publish after render { return 1i }
}
""",
    "step with multiple deps": """
workflow w {
    step a { return 1i }
    step b { return 2i }
    step c after a, b { return 3i }
}
""",
    "step guard": """
workflow w {
    step a { checkpoint "ready"
        return 1i }
    step b after a when reached("ready") { return 2i }
}
""",
    "step options": """
workflow w {
    step a with { retries: 2i, timeout_ms: 500i } { return 1i }
}
""",
    "state cell with options": """
workflow w {
    state total = 0i with { merge: "sum" }
    step a { total = total + 1i
        return total }
}
""",
    "goal pursuit": """
workflow tune {
    step a { checkpoint "good"
        return 1i }
}
goal reach over tune {
    until reached("good")
    budget { max_iterations: 3i }
}
""",
    "goal step with each": """
goal g {
    step discover { return [1i] }
    step render each page in discover { return page }
}
""",
    "compensation handler": """
workflow saga {
    step reserve { return "r" }
    step charge after reserve { return "c" }
    step release compensates reserve { return "released" }
}
""",
    "extern declaration": """
extern delegate(who: string, task: string) -> string
fn main() { print(delegate("a", "b")) }
""",
    "function with types": """
fn add(a: int, b: int) -> int { return a + b }
""",
    "try/catch/finally": """
fn main() {
    try { throw "x" } catch (e) { print("c") } finally { print("f") }
}
""",
    "match": """
fn main() {
    let x = 1i
    match x { 1i => print("one"), _ => print("other") }
}
""",
    "destructuring let": """
fn main() {
    let [a, b] = [1i, 2i]
    print(a + b)
}
""",
}


class FormatterRoundTripTests(unittest.TestCase):
    def _parse(self, source: str):
        return Parser(tokenize(source)).parse()

    def test_every_corpus_entry_round_trips_structurally(self):
        for label, source in CORPUS.items():
            with self.subTest(label):
                before = self._parse(source)
                formatted = format_source(source)
                after = self._parse(formatted)
                self.assertEqual(
                    before, after,
                    f"`fmt` changed the AST of {label!r}. A field is being "
                    f"dropped or rewritten — that is #656's shape, and it "
                    f"produces a file that still parses and does something "
                    f"else.\n\n--- formatted ---\n{formatted}",
                )

    def test_formatting_is_idempotent(self):
        """A second pass must be a no-op; otherwise `fmt --check` never settles."""
        for label, source in CORPUS.items():
            with self.subTest(label):
                once = format_source(source)
                self.assertEqual(once, format_source(once), label)

    # closes: #657
    def test_a_goal_budget_renders_only_what_is_declared(self):
        """#488 made the bounds individually optional and added `limits`.

        The formatter printed both dimensions unconditionally — so a
        single-dimension budget crashed with `Unknown expr node: None` — and
        never read `limits`, so formatting silently erased a spend bound. The
        third assertion is the one that matters: a crash is loud, a dropped
        bound is not.
        """
        flow = 'workflow t { step a { checkpoint "g"\n        return 1i } }\n'

        only_iterations = format_source(
            flow + 'goal r over t { until reached("g") budget { max_iterations: 3i } }\n'
        )
        self.assertIn("budget { max_iterations: 3i }", only_iterations)

        only_deadline = format_source(
            flow + 'goal r over t { until reached("g") budget { deadline_ms: 500i } }\n'
        )
        self.assertIn("budget { deadline_ms: 500i }", only_deadline)

        with_limits = format_source(
            flow
            + 'goal r over t { until reached("g") '
            + "budget { max_iterations: 3i, limits: { tokens: 100i } } }\n"
        )
        self.assertIn("limits: { tokens: 100i }", with_limits)

    # closes: #656
    def test_a_mapped_step_keeps_its_loop_variable(self):
        """The reported case, asserted on the text as well as the AST.

        The structural test above already covers it; this one fails with the
        actual symptom rather than an AST diff, because that is what someone
        hitting it will search for.
        """
        formatted = format_source(
            "workflow w {\n"
            "    step discover { return [1i] }\n"
            "    step render each page in discover { return page }\n"
            "}\n"
        )
        self.assertIn("each page in discover", formatted)
        self.assertNotIn("step render after discover", formatted)


if __name__ == "__main__":
    unittest.main()
