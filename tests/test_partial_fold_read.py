"""A reader of a folded cell must join every contributor (#722).

`merge:` (#485) fixed *lost* writes -- the final value is right. What it left open
is that a reader which does not depend on every contributor observes an
**intermediate** value, silently. Which one depends on scheduling: the reproduction
printed `1` with a slow producer and `3` with a fast one, from the same source. A
wrong answer that changes with the machine is worse than a wrong answer, because a
test can pass on the box that wrote it.

Refused at compile time, matching what the same rewriter already does to a plain
`=` on a folded cell. There is no ordering that makes a partial fold the intended
value, so allowing it preserves nothing.

The negative cases are the substance of this file. A refusal that also rejects
correct programs is worse than the defect: `test_transitive_dependencies_are_enough`,
`test_a_mapped_writer_needs_no_special_case` and
`test_a_compensation_step_is_not_a_writer` each pin a shape that a naive
implementation gets wrong.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus.frontend.lexer import tokenize  # noqa: E402
from nodus.frontend.parser import Parser  # noqa: E402
from nodus.orchestration.workflow_lowering import lower_workflow_ast  # noqa: E402
from nodus.runtime.diagnostics import LangSyntaxError  # noqa: E402


def lower(source: str):
    """Lower every workflow in *source*, which is where the check lives."""
    for stmt in Parser(tokenize(source)).parse():
        if type(stmt).__name__ == "WorkflowDef":
            lower_workflow_ast(stmt)


class APartialFoldReadIsRefusedTests(unittest.TestCase):
    # closes: #722
    def test_a_reader_that_joins_one_of_three_writers_is_refused(self):
        with self.assertRaises(LangSyntaxError) as caught:
            lower(
                """
                workflow tally {
                    state counter = 0i with { merge: "sum" }
                    step a { counter += 1i; return "a" }
                    step b { counter += 1i; return "b" }
                    step c { counter += 1i; return "c" }
                    step reader after a { return counter }
                }
                """
            )
        message = str(caught.exception)
        self.assertIn("reads state 'counter'", message)
        self.assertIn("'b'", message)
        self.assertIn("'c'", message)

    # closes: #722
    def test_the_message_names_the_missing_writers_and_the_policy(self):
        """A refusal that does not say what to add is a puzzle, not a diagnostic."""
        with self.assertRaises(LangSyntaxError) as caught:
            lower(
                """
                workflow tally {
                    state log = [] with { merge: "append" }
                    step a { log += ["a"]; return "a" }
                    step b { log += ["b"]; return "b" }
                    step reader after a { return len(log) }
                }
                """
            )
        message = str(caught.exception)
        self.assertIn('merge: "append"', message)
        self.assertIn("partial fold", message)
        self.assertIn("depends on scheduling", message)

    # closes: #722
    def test_a_reader_with_no_dependencies_at_all_is_refused(self):
        with self.assertRaises(LangSyntaxError):
            lower(
                """
                workflow tally {
                    state counter = 0i with { merge: "sum" }
                    step a { counter += 1i; return "a" }
                    step reader { return counter }
                }
                """
            )

    # closes: #722
    def test_a_read_inside_an_interpolated_string_counts(self):
        """The reproduction read the cell through `print("\\(counter)")`.

        A check that only saw a bare `Var` in an expression would have missed the
        exact program that motivated it.
        """
        with self.assertRaises(LangSyntaxError):
            lower(
                """
                workflow tally {
                    state counter = 0i with { merge: "sum" }
                    step a { counter += 1i; return "a" }
                    step b { counter += 1i; return "b" }
                    step reader after a { print("\\(counter)"); return 1i }
                }
                """
            )


class CorrectProgramsAreStillAcceptedTests(unittest.TestCase):
    """The half that matters more: what the refusal must not reject."""

    # closes: #722
    def test_joining_every_writer_directly_is_accepted(self):
        lower(
            """
            workflow tally {
                state counter = 0i with { merge: "sum" }
                step a { counter += 1i; return "a" }
                step b { counter += 1i; return "b" }
                step reader after a, b { return counter }
            }
            """
        )

    # closes: #722
    def test_transitive_dependencies_are_enough(self):
        """`after mid` where `mid after a, b` already orders both.

        Requiring a *direct* edge would refuse this, which is correct code -- the
        contributors are finished before the reader starts.
        """
        lower(
            """
            workflow tally {
                state counter = 0i with { merge: "sum" }
                step a { counter += 1i; return "a" }
                step b { counter += 1i; return "b" }
                step mid after a, b { return "mid" }
                step reader after mid { return counter }
            }
            """
        )

    # closes: #722
    def test_a_mapped_writer_needs_no_special_case(self):
        """`each x in src` implies `after src`, and a dependent joins the whole
        fan-out -- so the writer set is a set of step *names* and stays static
        however many instances run. Verified end to end: three items each
        contributing `+= 1i` give a dependent `counter = 3`."""
        lower(
            """
            workflow publish {
                state counter = 0i with { merge: "sum" }
                step discover { return ["a", "b", "c"] }
                step render each page in discover { counter += 1i; return page }
                step index after render { return counter }
            }
            """
        )

    # closes: #722
    def test_a_compensation_step_is_not_a_writer(self):
        """A `compensates` step is excluded from the forward graph by declaration
        (#577), so no forward reader can name it in `after`. Counting it would make
        every read of a cell it touches unsatisfiable -- a refusal with no legal
        program behind it."""
        lower(
            """
            workflow charge {
                state undone = [] with { merge: "append" }
                step pay { return "paid" }
                step refund compensates pay { undone += ["r"]; return "refunded" }
                step check after pay { return len(undone) }
            }
            """
        )

    # closes: #722
    def test_a_cell_with_no_fold_policy_is_untouched(self):
        """Only folded cells accumulate. A plain cell is last-write-wins and is
        #485's territory, not this check's."""
        lower(
            """
            workflow p {
                state note = "x"
                step a { note = "set"; return "a" }
                step reader { return note }
            }
            """
        )

    # closes: #722
    def test_a_writer_may_read_a_cell_it_is_the_only_contributor_to(self):
        lower(
            """
            workflow solo {
                state counter = 0i with { merge: "sum" }
                step a { counter += 1i; return counter }
            }
            """
        )

    # closes: #722
    def test_a_contribution_is_not_itself_a_read(self):
        """`counter += 1i` never reads the cell -- that is what closes the
        read-modify-write window. Two contributors that do not join each other
        must stay legal, or every fan-out fold becomes a refusal."""
        lower(
            """
            workflow tally {
                state counter = 0i with { merge: "sum" }
                step a { counter += 1i; return "a" }
                step b { counter += 1i; return "b" }
                step done after a, b { return "done" }
            }
            """
        )


if __name__ == "__main__":
    unittest.main()
