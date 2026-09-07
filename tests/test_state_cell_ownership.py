"""A state cell owns its value, and every way of changing one is recorded (#822).

A cell used to hold a live reference to whatever object was assigned into it, and
`cell[i] = v` lowered to a **read** of the cell followed by an in-place mutation.
Three consequences, all silent:

* `cell[i] = v` and `m["k"] = v` never called `TrackedState.__setitem__`, so the
  step that changed the cell was not recorded as writing it. Two concurrent
  indexed writes lost one with **no conflict warning**, no `merge:` policy
  consulted, and nothing for #547's staged 6.0.0 error to fire on — while the
  plain `cell = v` spelling one line away had all three.
* A step could read a cell and mutate what it read, changing the recorded state
  without ever writing to it.
* A step could assign an outside container into a cell and then mutate that
  container — from the same step or a later one — and the cell changed with it.

One root cause: the cell did not own its value. `clone_state` already existed and
was applied at three sites, all of them *recording* a checkpoint or a durable
entry (`task_graph.py:1130`, `:1978`, `:1982`); it was applied on neither read
nor write. The declared write path was watched and the sibling path was not,
which is this codebase's recurring shape in the place it costs most.

The fix is ownership, in three parts:

* `TrackedState.__setitem__` stores a copy — the cell owns what it holds.
* `TrackedState.__getitem__` returns a copy — a reader cannot reach the cell's
  object.
* `TrackedState.open_for_write` is the **one** deliberate exception: it records a
  read and a write and then hands back the cell's own object, so the in-place
  mutation the compiler emits for `cell[i] = v` lands where it is meant to. The
  lowering routes both container-assignment forms through it.

**Barrier inference was never affected** and is asserted here so nobody
"restores" it: `_record_container_write` already walked an index chain to its
root at compile time, so a `barrier: true` cell written as `cell[0] = v` always
inferred the edge. Compile-time bookkeeping was right; the runtime half was
missing.

`RewritingIsRoutedThroughOneHelperTests` asserts on the source, because a
behaviour test only covers the assignment forms it happens to know about — and
#518 was exactly an enumeration of assignment forms with a member missing.
"""

import ast
import io
import pathlib
import unittest
from contextlib import redirect_stdout

import nodus as lang
from nodus.runtime.diagnostics import LangSyntaxError
from nodus.runtime.module_loader import ModuleLoader

REPO = pathlib.Path(__file__).resolve().parents[1]
LOWERING = REPO / "src" / "nodus" / "orchestration" / "workflow_lowering.py"


def run_program(src: str, source_path: str = "state.nd") -> list[str]:
    vm = lang.VM([], {}, code_locs=[], source_path=source_path)
    _loader = ModuleLoader(project_root=None, vm=vm)
    buf = io.StringIO()
    with redirect_stdout(buf):
        _loader.load_module_from_source(src, module_name=source_path, base_dir=None)
    return buf.getvalue().splitlines()


class IndexedWritesStillWorkTests(unittest.TestCase):
    """The fix must not cost the feature it makes safe."""

    # closes: #822
    def test_an_indexed_write_to_a_list_cell_lands(self):
        src = """
workflow w {
    state cell = [1i, 2i, 3i]
    step s {
        cell[0] = 99i
        return "ok"
    }
}
print(run_workflow(w)["state"]["cell"][0])
"""
        self.assertEqual(run_program(src), ["99"])

    def test_a_keyed_write_to_a_map_cell_lands(self):
        src = """
workflow w {
    state m = { "k": 1i }
    step s {
        m["k"] = 42i
        return "ok"
    }
}
print(run_workflow(w)["state"]["m"]["k"])
"""
        self.assertEqual(run_program(src), ["42"])

    def test_a_nested_indexed_write_lands_at_depth(self):
        """`cell["a"][0] = v` — only the innermost cell read is replaced."""
        src = """
workflow w {
    state cell = { "a": [1i, 2i] }
    step s {
        cell["a"][0] = 77i
        return "ok"
    }
}
print(run_workflow(w)["state"]["cell"]["a"][0])
"""
        self.assertEqual(run_program(src), ["77"])

    def test_repeated_indexed_writes_in_one_step_accumulate(self):
        """Each write reopens the cell, so the previous one must have persisted."""
        src = """
workflow w {
    state cell = [0i, 0i, 0i]
    step s {
        cell[0] = 1i
        cell[1] = 2i
        cell[2] = 3i
        return "ok"
    }
}
let out = run_workflow(w)["state"]["cell"]
print("\\(out[0])\\(out[1])\\(out[2])")
"""
        self.assertEqual(run_program(src), ["123"])


class IndexedWritesAreRecordedTests(unittest.TestCase):
    """The half that was missing: the tracker sees them."""

    def _stderr(self, src: str) -> str:
        """The conflict report lands in the run result's `stderr`, not `warnings`.

        Same harness as `tests/test_state_write_conflicts.py`, and run in a temp
        cwd so the workflow store does not write into the repo.
        """
        import os
        import tempfile

        from nodus.runtime.embedding import NodusRuntime

        with tempfile.TemporaryDirectory() as td:
            cwd = os.getcwd()
            os.chdir(td)
            try:
                result = NodusRuntime(timeout_ms=None, max_steps=None).run_source(src)
            finally:
                os.chdir(cwd)
        return result.get("stderr") or ""

    _CONCURRENT_INDEXED = """
workflow w {
    state cell = [0i, 0i]
    step a { cell[0] = 1i; return "ok" }
    step b { cell[0] = 2i; return "ok" }
    step j after a, b { return "ok" }
}
print(run_workflow(w)["state"]["cell"][0])
"""

    def test_two_concurrent_indexed_writes_are_reported(self):
        text = self._stderr(self._CONCURRENT_INDEXED)
        self.assertIn("both wrote state 'cell'", text)
        self.assertIn("a", text)
        self.assertIn("b", text)

    def test_the_report_says_read_modify_write(self):
        """An indexed update *is* a read-modify-write, so it gets #485's wording.

        Not the weaker "with different values" phrasing: the values agreeing is
        precisely when an update was lost, which is why `open_for_write` records
        the read before the write rather than only the write.
        """
        self.assertIn("each read it before writing", self._stderr(self._CONCURRENT_INDEXED))

    def test_an_indexed_write_to_a_fold_cell_is_refused_at_compile_time(self):
        """A fold cell is written by contribution; the plain `=` was already refused.

        `acc[0] = v` was accepted and silently set the cell behind the fold.
        """
        src = """
workflow w {
    state acc = [0i] with { merge: "append" }
    step a { acc[0] = 1i; return "ok" }
}
print(run_workflow(w))
"""
        with self.assertRaises(LangSyntaxError) as caught:
            run_program(src)
        message = str(caught.exception)
        self.assertIn("written by contribution, not by mutation", message)
        self.assertIn("acc += ", message)


class ACellOwnsItsValueTests(unittest.TestCase):
    """The three ways a cell used to change without a write."""

    def test_a_reader_mutating_what_it_read_does_not_change_the_cell(self):
        src = """
workflow w {
    state cell = [1i, 2i, 3i]
    step reader {
        let got = cell
        got[0] = 555i
        return "ok"
    }
}
print(run_workflow(w)["state"]["cell"][0])
"""
        self.assertEqual(run_program(src), ["1"])

    def test_mutating_the_source_after_writing_it_does_not_change_the_cell(self):
        src = """
workflow w {
    state cell = []
    step s {
        let local = [1i, 2i, 3i]
        cell = local
        local[0] = 777i
        return "ok"
    }
}
print(run_workflow(w)["state"]["cell"][0])
"""
        self.assertEqual(run_program(src), ["1"])

    def test_a_later_step_mutating_the_source_does_not_change_the_cell(self):
        src = """
let outside = [1i, 2i, 3i]
workflow w {
    state seen = []
    step a { seen = outside; return "ok" }
    step b after a { outside[0] = 999i; return "ok" }
}
let r = run_workflow(w)
print(r["state"]["seen"][0])
print(outside[0])
"""
        self.assertEqual(run_program(src), ["1", "999"])

    def test_a_nested_container_is_owned_too(self):
        """A shallow copy would leave the inner list shared."""
        src = """
let outside = { "inner": [1i, 2i] }
workflow w {
    state cell = {}
    step a { cell = outside; return "ok" }
    step b after a { outside["inner"][0] = 999i; return "ok" }
}
print(run_workflow(w)["state"]["cell"]["inner"][0])
"""
        self.assertEqual(run_program(src), ["1"])


class BarrierInferenceIsUnaffectedTests(unittest.TestCase):
    """Compile-time bookkeeping was always right — do not "restore" it.

    `_record_container_write` walks an index chain to its root, so a
    `barrier: true` cell written with `cell[0] = v` inferred the edge before this
    fix and still does. It is the runtime half that was missing.
    """

    def test_a_barrier_cell_written_by_index_still_orders_its_reader(self):
        src = """
workflow w {
    state cell = [0i] with { barrier: true }
    step writer { cell[0] = 5i; return "ok" }
    step reader { return "saw \\(cell[0])" }
}
print(run_workflow(w)["steps"]["reader"])
"""
        self.assertEqual(run_program(src), ["saw 5"])


class PlainAndCompoundWritesAreUnchangedTests(unittest.TestCase):
    """The two spellings that already worked keep working, exactly."""

    def test_a_plain_assignment_still_sets_the_cell(self):
        src = """
workflow w {
    state n = 0i
    step s { n = 7i; return "ok" }
}
print(run_workflow(w)["state"]["n"])
"""
        self.assertEqual(run_program(src), ["7"])

    def test_a_fold_contribution_still_folds(self):
        src = """
workflow w {
    state n = 0i with { merge: "sum" }
    step a { n += 1i; return "ok" }
    step b { n += 1i; return "ok" }
    step j after a, b { return "ok" }
}
print(run_workflow(w)["state"]["n"])
"""
        self.assertEqual(run_program(src), ["2"])


class RewritingIsRoutedThroughOneHelperTests(unittest.TestCase):
    """Assert on the source: a third container-assignment form must not be forgotten.

    #518 was an enumeration of assignment forms with a member missing, and
    `_record_container_write` exists because of it. This is the same guard for
    the runtime half — a behaviour test only ever covers the forms it knows
    about.
    """

    def _assign_branches(self) -> dict[str, ast.If]:
        """The `isinstance(expr, <Form>)` branches inside `_StateRewriter.rewrite_expr`.

        Matched narrowly on purpose: a tuple `isinstance(x, (IndexAssign,
        FieldAssign))` elsewhere in the module is a different question, and an
        earlier draft of this matched it instead and passed for the wrong reason.
        """
        tree = ast.parse(LOWERING.read_text(encoding="utf-8"))
        rewriter = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef) and node.name == "_StateRewriter"
        )
        rewrite_expr = next(
            node
            for node in rewriter.body
            if isinstance(node, ast.FunctionDef) and node.name == "rewrite_expr"
        )
        found: dict[str, ast.If] = {}
        for node in ast.walk(rewrite_expr):
            if not isinstance(node, ast.If) or not isinstance(node.test, ast.Call):
                continue
            call = node.test
            if not (isinstance(call.func, ast.Name) and call.func.id == "isinstance"):
                continue
            if len(call.args) != 2 or not isinstance(call.args[1], ast.Name):
                continue
            form = call.args[1].id
            if form in ("IndexAssign", "FieldAssign"):
                found.setdefault(form, node)
        return found

    def test_both_container_assignment_forms_have_a_branch(self):
        self.assertEqual(set(self._assign_branches()), {"IndexAssign", "FieldAssign"})

    def test_both_route_their_target_through_the_mutation_rewriter(self):
        for form, branch in self._assign_branches().items():
            with self.subTest(form=form):
                body = ast.dump(branch)
                self.assertIn(
                    "_rewrite_mutation_target",
                    body,
                    f"{form} rewrites its target with the ordinary read path, so a "
                    f"mutation through it is not recorded as a write (#822)",
                )

    def test_both_refuse_a_write_to_a_fold_cell(self):
        for form, branch in self._assign_branches().items():
            with self.subTest(form=form):
                self.assertIn(
                    "_refuse_container_write_to_fold_cell", ast.dump(branch)
                )

    def test_open_for_write_is_the_only_place_that_hands_out_the_cell_s_object(self):
        """`dict.__getitem__` bypasses the copy, so it may appear exactly once."""
        source = (
            REPO / "src" / "nodus" / "orchestration" / "workflow_state.py"
        ).read_text(encoding="utf-8")
        self.assertEqual(
            source.count("dict.__getitem__(self"),
            1,
            "a second raw read would hand out the cell's own object without "
            "recording a write, which is the defect #822 is about",
        )


if __name__ == "__main__":
    unittest.main()
