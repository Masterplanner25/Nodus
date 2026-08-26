"""Folded state cells: `merge: "sum"` and `merge: "append"` (#485 step 3).

The emission model is Option A, decided on the issue: under a fold policy
`cell += expr` **contributes** `expr` to be folded at the join, and `cell = expr`
is a compile-time error, because a final value cannot be combined with another
branch's.

`test_the_lost_update_is_fixed_by_a_fold` is the one that matters — it is the
issue's own reproduction, and it is why the rest exists.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))  # noqa: E402

from nodus.orchestration.workflow_state import (  # noqa: E402
    FOLD_STATE_MERGE_POLICIES,
    STATE_MERGE_POLICIES,
    check_contribution,
    fold_contributions,
    is_fold_policy,
)
from nodus.runtime.embedding import NodusRuntime  # noqa: E402


def _run(src: str) -> dict:
    return NodusRuntime(timeout_ms=None, max_steps=None).run_source(src, filename="<fold>")


def _out(src: str) -> str:
    result = _run(src)
    assert result.get("ok"), result.get("errors")
    return (result.get("stdout") or "").strip()


def _error(src: str) -> str:
    result = _run(src)
    assert not result.get("ok"), "expected a refusal"
    errors = result.get("errors") or []
    return errors[0].get("message", "") if errors else ""


class TheBugTests(unittest.TestCase):
    # closes: #485
    def test_the_lost_update_is_fixed_by_a_fold(self):
        """The issue's own reproduction. A suspension between read and write is
        what lost an increment; a contribution never reads the cell, so there is
        no window to lose it in."""
        out = _out(
            """
workflow race {
    state counter = 0i with { merge: "sum" }
    step a { sleep(20i); counter += 1i; return 1i }
    step b { sleep(20i); counter += 1i; return 2i }
    step j after a, b { return 0i }
}
fn main() { let r = run_workflow(race); print("C=\\(r["state"]["counter"])") }
"""
        )
        self.assertIn("C=2", out)

    def test_the_serialised_case_is_also_right(self):
        """The case a read-isolating overlay would have broken."""
        out = _out(
            """
workflow latent {
    state counter = 0i with { merge: "sum" }
    step a { counter += 1i; return 1i }
    step b { counter += 1i; return 2i }
    step j after a, b { return 0i }
}
fn main() { let r = run_workflow(latent); print("C=\\(r["state"]["counter"])") }
"""
        )
        self.assertIn("C=2", out)

    def test_a_folded_cell_does_not_warn_about_concurrent_writers(self):
        """Two branches contributing is the feature, not the defect."""
        result = _run(
            """
workflow race {
    state counter = 0i with { merge: "sum" }
    step a { counter += 1i; return 1i }
    step b { counter += 1i; return 2i }
    step j after a, b { return 0i }
}
fn main() { run_workflow(race) }
"""
        )
        self.assertNotIn("both wrote state", result.get("stderr") or "")

    def test_three_branches_all_land(self):
        out = _out(
            """
workflow wide {
    state counter = 0i with { merge: "sum" }
    step a { sleep(10i); counter += 1i; return 1i }
    step b { sleep(10i); counter += 2i; return 2i }
    step c { sleep(10i); counter += 3i; return 3i }
    step j after a, b, c { return 0i }
}
fn main() { let r = run_workflow(wide); print("C=\\(r["state"]["counter"])") }
"""
        )
        self.assertIn("C=6", out)


class AppendTests(unittest.TestCase):
    def test_concurrent_branches_both_append(self):
        out = _out(
            """
workflow gather {
    state log = [] with { merge: "append" }
    step a { sleep(10i); log += ["a"]; return 1i }
    step b { sleep(10i); log += ["b"]; return 2i }
    step j after a, b { return 0i }
}
fn main() { let r = run_workflow(gather); print("N=\\(len(r["state"]["log"]))") }
"""
        )
        self.assertIn("N=2", out)

    def _failing_step(self, src: str) -> tuple[str, str]:
        """A wrong contribution fails its *step*, not the run.

        `run_workflow` reports a failed step in its result rather than aborting,
        so the run is still `ok` and the diagnostic is on stderr. Asserting on
        run-level `ok` here would pass for the wrong reason.
        """
        result = _run(src)
        self.assertTrue(result.get("ok"), result.get("errors"))
        return (result.get("stdout") or "").strip(), (result.get("stderr") or "")

    def test_a_number_contribution_to_append_is_refused(self):
        out, err = self._failing_step(
            """
workflow bad {
    state log = [] with { merge: "append" }
    step a { log += 1i; return 1i }
}
fn main() { let r = run_workflow(bad); print("F=\\(len(r["failed"]))") }
"""
        )
        self.assertIn("F=1", out)
        self.assertIn("must be a list", err)

    def test_a_list_contribution_to_sum_is_refused(self):
        out, err = self._failing_step(
            """
workflow bad {
    state total = 0i with { merge: "sum" }
    step a { total += [1i]; return 1i }
}
fn main() { let r = run_workflow(bad); print("F=\\(len(r["failed"]))") }
"""
        )
        self.assertIn("F=1", out)
        self.assertIn("must be a number", err)


class UnionTests(unittest.TestCase):
    """`union` = append, minus elements already present.

    Its blocker was never the fold -- it was knowing when two elements are the
    same. Nodus `==` answers that structurally for numbers, strings, bools, nil,
    lists and maps at any depth. It does not for records, which compare by
    identity (#545), so those are refused rather than silently not deduplicated.
    """

    def test_overlapping_contributions_deduplicate(self):
        out = _out(
            """
workflow tags {
    state seen = [] with { merge: "union" }
    step a { sleep(10i); seen += ["x", "y"]; return 1i }
    step b { sleep(10i); seen += ["y", "z"]; return 2i }
    step j after a, b { return 0i }
}
fn main() { let r = run_workflow(tags); print("N=\\(len(r["state"]["seen"]))") }
"""
        )
        self.assertIn("N=3", out)

    def test_a_record_element_is_refused(self):
        result = _run(
            """
workflow bad {
    state seen = [] with { merge: "union" }
    step a { seen += [record {x: 1i}]; return 1i }
}
fn main() { let r = run_workflow(bad); print("F=\\(len(r["failed"]))") }
"""
        )
        self.assertTrue(result.get("ok"), result.get("errors"))
        self.assertIn("F=1", (result.get("stdout") or ""))
        stderr = result.get("stderr") or ""
        self.assertIn("compare by identity", stderr)
        self.assertIn("#545", stderr)

    def test_a_non_list_contribution_is_refused(self):
        result = _run(
            """
workflow bad {
    state seen = [] with { merge: "union" }
    step a { seen += 5i; return 1i }
}
fn main() { let r = run_workflow(bad); print("F=\\(len(r["failed"]))") }
"""
        )
        self.assertIn("must be a list; got int", result.get("stderr") or "")

    def test_maps_deduplicate_structurally(self):
        """A map is the workaround the refusal message names."""
        out = _out(
            """
workflow tags {
    state seen = [] with { merge: "union" }
    step a { sleep(10i); seen += [{"id": 1i}]; return 1i }
    step b { sleep(10i); seen += [{"id": 1i}, {"id": 2i}]; return 2i }
    step j after a, b { return 0i }
}
fn main() { let r = run_workflow(tags); print("N=\\(len(r["state"]["seen"]))") }
"""
        )
        self.assertIn("N=2", out)


class CompileTimeRefusalTests(unittest.TestCase):
    """`=` under a fold policy is refused before the program runs."""

    def test_plain_assignment_is_a_compile_error(self):
        message = _error(
            """
workflow bad {
    state counter = 0i with { merge: "sum" }
    step a { counter = 5i; return 1i }
}
fn main() { run_workflow(bad) }
"""
        )
        self.assertIn("+=", message)
        self.assertIn("final value", message)

    def test_a_non_additive_compound_is_refused(self):
        message = _error(
            """
workflow bad {
    state counter = 0i with { merge: "sum" }
    step a { counter -= 1i; return 1i }
}
fn main() { run_workflow(bad) }
"""
        )
        self.assertIn("folds with", message)

    def test_a_computed_merge_policy_is_refused(self):
        """The policy decides at compile time what a write means, so it cannot
        be computed."""
        message = _error(
            """
fn pick() { return "sum" }
workflow bad {
    state counter = 0i with { merge: pick() }
    step a { counter += 1i; return 1i }
}
fn main() { run_workflow(bad) }
"""
        )
        self.assertIn("literal policy name", message)

    def test_a_local_shadowing_the_cell_is_untouched(self):
        """`let counter` inside a step is an ordinary local, fold or not."""
        out = _out(
            """
workflow shadow {
    state counter = 0i with { merge: "sum" }
    step a { let counter = 10i; counter = counter + 1i; print("L=\\(counter)"); return 1i }
}
fn main() { run_workflow(shadow) }
"""
        )
        self.assertIn("L=11", out)


class UnfoldedCellsAreUnchangedTests(unittest.TestCase):
    def test_an_undeclared_cell_still_assigns(self):
        out = _out(
            """
workflow plain {
    state x = 0i
    step a { x = 5i; return 1i }
    step b after a { return x }
}
fn main() { let r = run_workflow(plain); print("X=\\(r["state"]["x"])") }
"""
        )
        self.assertIn("X=5", out)

    def test_compound_assign_on_an_unfolded_cell_still_reads_the_cell(self):
        out = _out(
            """
workflow plain {
    state x = 1i
    step a { x += 4i; return 1i }
    step b after a { return x }
}
fn main() { let r = run_workflow(plain); print("X=\\(r["state"]["x"])") }
"""
        )
        self.assertIn("X=5", out)


class CheckpointTests(unittest.TestCase):
    def test_a_checkpoint_sees_a_pending_contribution(self):
        """Otherwise a resume from that label contributes a second time."""
        out = _out(
            """
workflow demo {
    state counter = 0i with { merge: "sum" }
    step a { counter += 2i; checkpoint "after_a"; return 1i }
    step b after a { return 2i }
}
fn main() { let r = run_workflow(demo); print("C=\\(r["state"]["counter"])") }
"""
        )
        self.assertIn("C=2", out)


class FoldPrimitiveTests(unittest.TestCase):
    """The fold itself, without a workflow around it."""

    def test_sum_folds_in_order(self):
        self.assertEqual(fold_contributions("sum", 0, [1, 2, 3]), 6)

    def test_append_concatenates_in_order(self):
        self.assertEqual(fold_contributions("append", ["a"], [["b"], ["c"]]), ["a", "b", "c"])

    def test_a_missing_base_takes_the_first_contribution(self):
        self.assertEqual(fold_contributions("sum", None, [5, 1]), 6)

    def test_folding_is_batching_invariant(self):
        """fold(fold(s, xs), ys) == fold(s, xs + ys).

        This is why the policy set is closed rather than a user function: a
        resume that regroups writes must produce the same total, and here that
        is guaranteed by construction rather than being the author's contract.
        """
        for policy, base, xs, ys in [
            ("sum", 0, [1, 2], [3, 4]),
            ("append", [], [["a"], ["b"]], [["c"]]),
            ("union", ["a"], [["b", "a"], ["c"]], [["b"], ["d"]]),
        ]:
            grouped = fold_contributions(policy, fold_contributions(policy, base, xs), ys)
            flat = fold_contributions(policy, base, xs + ys)
            self.assertEqual(grouped, flat, policy)

    def test_check_contribution_accepts_and_rejects(self):
        self.assertIsNone(check_contribution("sum", 1))
        self.assertIsNone(check_contribution("sum", 1.5))
        self.assertIsNone(check_contribution("append", [1]))
        self.assertIsNone(check_contribution("union", [1, "a", [2], {"k": 3}]))
        for merge, bad, expected in [
            ("sum", [1], "must be a number; got list"),
            ("sum", True, "must be a number; got bool"),
            ("append", 1, "must be a list; got int"),
            ("union", "x", "must be a list; got string"),
        ]:
            with self.subTest(merge=merge):
                problem = check_contribution(merge, bad)
                self.assertIsNotNone(problem)
                self.assertIn(expected, problem)

    def test_a_record_element_blocks_a_union_contribution(self):
        """The element-equality blocker, stated precisely (#545)."""
        from nodus.vm.types import Record

        problem = check_contribution("union", [Record({"x": 1})])
        self.assertIsNotNone(problem)
        self.assertIn("compare by identity", problem)

    def test_a_datetime_record_does_not_block_it(self):
        """`Record.__eq__` compares datetime and duration by value."""
        from nodus.vm.types import Record

        self.assertIsNone(
            check_contribution("union", [Record({"epoch_ms": 5}, "datetime")])
        )

    def test_a_nested_record_blocks_it_too(self):
        """A record inside a map makes the map compare false as well."""
        from nodus.vm.types import Record

        self.assertIsNotNone(check_contribution("union", [{"r": Record({"x": 1})}]))

    def test_union_deduplicates_by_nodus_equality(self):
        self.assertEqual(fold_contributions("union", ["a"], [["b", "a"], ["c"]]),
                         ["a", "b", "c"])

    def test_union_inherits_the_int_float_coercion(self):
        """Nodus `==` says 1 == 1.0, so union must agree -- which is why it
        borrows `VM._nodus_eq` instead of using Python `==` or a set."""
        self.assertEqual(fold_contributions("union", [1], [[1.0, 2]]), [1, 2])

    def test_union_does_not_treat_true_as_one(self):
        self.assertEqual(fold_contributions("union", [True], [[1]]), [True, 1])

    def test_union_deduplicates_structural_values(self):
        self.assertEqual(
            fold_contributions("union", [[1, 2]], [[[1, 2], [3]]]), [[1, 2], [3]]
        )

    def test_non_fold_policies_accept_anything(self):
        self.assertIsNone(check_contribution("any", object()))

    def test_is_fold_policy(self):
        for policy in FOLD_STATE_MERGE_POLICIES:
            self.assertTrue(is_fold_policy(policy))
        self.assertFalse(is_fold_policy("any"))
        self.assertFalse(is_fold_policy("once"))

    def test_the_fold_set_is_a_subset_of_the_vocabulary(self):
        self.assertTrue(set(FOLD_STATE_MERGE_POLICIES) <= set(STATE_MERGE_POLICIES))


class ContributionReachesTheBuiltinTests(unittest.TestCase):
    LOWERING_SOURCE = (
        ROOT / "src" / "nodus" / "orchestration" / "workflow_lowering.py"
    ).read_text(encoding="utf-8")

    def test_the_contribution_goes_through_builtin_call(self):
        """#411: a lowering must reach the builtin past whatever the program
        bound to that name, or a guest can intercept its own state writes."""
        self.assertIn('builtin_call("state_contribute"', self.LOWERING_SOURCE)

    def test_state_contribute_is_governed_and_cannot_be_shadowed(self):
        """It is a lowering artifact, and #616 changed how that is enforced.

        This test used to assert `state_contribute` was absent from
        `BUILTIN_NAMES`, on the reading that absence made it non-public. It did
        not. The name resolved from a guest program the whole time — the VM
        dispatches from its own table, and `BUILTIN_NAMES` is not consulted for
        resolution. What absence *did* do was leave the name outside
        `register_function`'s override guard and outside the capability
        classification, which is #616.

        What actually keeps a program from contributing to a cell the runtime
        has no policy for is the runtime guard below, not this set.
        """
        from nodus.builtins.nodus_builtins import BUILTIN_NAMES
        from nodus.runtime.capability import (
            BUILTIN_CAPABILITIES,
            NO_AUTHORITY_BUILTIN_NAMES,
        )

        self.assertIn("state_contribute", BUILTIN_NAMES)
        self.assertIn(
            "state_contribute",
            set(BUILTIN_CAPABILITIES) | set(NO_AUTHORITY_BUILTIN_NAMES),
            "every dispatched builtin must carry a capability decision (#616)",
        )

    def test_calling_it_outside_a_step_is_refused_by_the_runtime(self):
        """The guard that actually holds, asserted on its message.

        Previously this asserted only that *some* message came back, under the
        name `test_calling_it_by_name_does_not_resolve`. The name did resolve;
        the message was `state contribution outside a workflow step`, so the
        test passed for an unrelated reason and would have kept passing if
        resolution had broken. Assert the specific refusal.
        """
        message = _error("fn main() { state_contribute(\"x\", 1i) }")
        self.assertIn("outside a workflow step", message)


if __name__ == "__main__":
    unittest.main()
