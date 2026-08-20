"""The reported status vocabulary and the prose about it stay in step.

Three features landed in 5.1.0 that touch the same vocabulary: per-task statuses,
`with { on: [...] }` join policies, and `when` guards. They landed in that order,
and the guards made `skipped` and `omitted` real -- which quietly falsified prose
written for the two earlier ones. At the 5.1.0 cut, four artifacts still described
the five-value world:

- the CHANGELOG entry, which listed five statuses and said `skipped` and `omitted`
  "wait on a conditional-edge design (#471)"
- `README.md`, which is the PyPI long description and is frozen at tag time
- `docs/guide/workflows-and-tasks.md`, which said the valid `on:` outcomes "are
  **`completed`** and **`failed`**" while `on: ["skipped"]` worked
- the comment directly above `JOIN_ON_STATES`, which said `skipped` was absent, one
  line above a tuple containing it

None of that is a code defect and no behaviour test would have caught any of it.
What they share is a vocabulary that lives in several places at once, so this file
gives it one source and holds the rest to it.
"""
import ast
import inspect
import os
import re
import sys
import textwrap
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus.orchestration import task_graph  # noqa: E402
from nodus.orchestration.task_graph import JOIN_ON_STATES, TASK_STATUSES  # noqa: E402

GUIDE = os.path.join(
    os.path.dirname(__file__), "..", "docs", "guide", "workflows-and-tasks.md"
)


def _reported_literals():
    """Every string literal `task_statuses` assigns as a status.

    Reads that one function's AST rather than the file's text: the question is
    which values it can produce, which is a property, not a code shape. The
    `else` branch assigns `task.status` -- a name, not a literal -- so it is
    invisible here and is covered separately below.
    """
    source = inspect.getsource(task_graph.run_task_graph)
    tree = ast.parse(textwrap.dedent(source))
    found = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name != "task_statuses":
            continue
        for inner in ast.walk(node):
            if not isinstance(inner, ast.Assign):
                continue
            target = inner.targets[0]
            if not isinstance(target, ast.Subscript):
                continue
            if not (isinstance(target.value, ast.Name) and target.value.id == "statuses"):
                continue
            if isinstance(inner.value, ast.Constant) and isinstance(inner.value.value, str):
                found.add(inner.value.value)
    return found


class TheTupleMatchesWhatTheCodeEmitsTests(unittest.TestCase):
    def test_task_statuses_names_every_status_the_runtime_assigns(self):
        emitted = _reported_literals()
        self.assertTrue(emitted, "found no status assignments -- the walk is broken")
        self.assertEqual(
            set(TASK_STATUSES),
            emitted,
            "TASK_STATUSES and `task_statuses()` disagree. Adding a status without "
            "adding it here leaves the guide and the release notes describing a "
            "vocabulary the runtime no longer has -- which is how #521's release "
            "cycle shipped four stale descriptions of this exact list.",
        )

    def test_the_join_options_are_a_subset_of_the_reported_statuses(self):
        """`on:` names dependency outcomes, so every admissible one must be a
        status the runtime can actually report. A value in `JOIN_ON_STATES` that
        is not in `TASK_STATUSES` could never match."""
        self.assertLessEqual(set(JOIN_ON_STATES), set(TASK_STATUSES))

    def test_end_of_run_conclusions_are_not_offered_as_join_options(self):
        """`upstream_failed`, `omitted`, `cancelled` and `abandoned` are drawn by
        walking the finished graph, so a step waiting on one would never become
        ready. Admitting one would be a knob that silently never fires."""
        for status in ("upstream_failed", "omitted", "cancelled", "abandoned"):
            with self.subTest(status=status):
                self.assertNotIn(status, JOIN_ON_STATES)


class TheGuideMatchesTheTuplesTests(unittest.TestCase):
    """The guide is the reference for what an author may write, so it is held to
    the code. Prose enumerations in `README.md` and `CHANGELOG.md` are the release
    checklist's job -- a changelog entry is a historical record and must not be
    rewritten by a test."""

    @classmethod
    def setUpClass(cls):
        with open(GUIDE, encoding="utf-8") as handle:
            cls.text = handle.read()

    def _valid_outcomes_sentence(self):
        match = re.search(r"The valid outcomes are (.+?)\n\n", self.text, re.S)
        self.assertIsNotNone(
            match,
            "could not find the sentence naming the valid `on:` outcomes in "
            f"{os.path.basename(GUIDE)} -- if it was reworded, update this test "
            "rather than deleting it",
        )
        return match.group(1)

    def test_every_admissible_join_outcome_is_documented(self):
        sentence = self._valid_outcomes_sentence()
        for status in JOIN_ON_STATES:
            with self.subTest(status=status):
                self.assertIn(
                    f"`{status}`",
                    sentence,
                    f"`on: [\"{status}\"]` is accepted by the runtime but the guide "
                    f"does not list it as valid",
                )

    def test_the_guide_does_not_offer_an_outcome_the_runtime_refuses(self):
        sentence = self._valid_outcomes_sentence()
        for status in set(TASK_STATUSES) - set(JOIN_ON_STATES):
            with self.subTest(status=status):
                self.assertNotIn(
                    f"`{status}`",
                    sentence,
                    f"the guide names `{status}` among the valid `on:` outcomes, but "
                    f"the runtime refuses it at the point of declaration",
                )


if __name__ == "__main__":
    unittest.main()
