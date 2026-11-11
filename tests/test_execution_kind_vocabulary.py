"""#180 stage 4a: the run-kind vocabulary is named once, and every site uses it.

A run record's `execution_kind` was a string literal at every site that read
it, and the resume path branched on it two ways: `goal`, or else `workflow`. A
third kind -- a durable coroutine (design 08a, D4) -- would have fallen into the
workflow branch and failed with "workflow ... is not defined", which names the
wrong problem. This is this codebase's recurring shape: one vocabulary, N
enumerations, one of them missing a member.

So the vocabulary lives in `nodus.orchestration.workflow_state`, the new member
is added before anything creates it, and this file holds both halves:

- **the source** cannot compare `execution_kind` against a literal anywhere
  else, so a site cannot quietly enumerate the kinds for itself;
- **the behaviour** of the two places a non-graph run could reach -- the graph
  rebuild and the rehydrate sweep -- is driven with a coroutine record.
"""

import ast
import io
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))  # noqa: E402

from nodus.orchestration.task_graph import WorkflowRebuildError  # noqa: E402
from nodus.orchestration.workflow_state import (  # noqa: E402
    EXECUTION_KIND_COROUTINE,
    EXECUTION_KIND_GOAL,
    EXECUTION_KIND_WORKFLOW,
    EXECUTION_KINDS,
    GRAPH_EXECUTION_KINDS,
    is_graph_execution_kind,
)
from nodus.runtime.embedding import NodusRuntime  # noqa: E402
from nodus_lang_workflow.models import RUN_STATUS_RUNNING  # noqa: E402
from nodus_lang_workflow.runner import WorkflowFrameworkRunner  # noqa: E402
from nodus_lang_workflow.store import SQLiteWorkflowStore  # noqa: E402

VOCABULARY_MODULE = "src/nodus/orchestration/workflow_state.py"


def _mentions_kind(node) -> bool:
    """`execution_kind`, `x.execution_kind`, `m.get("execution_kind")`, `m["execution_kind"]`."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name) and sub.id == "execution_kind":
            return True
        if isinstance(sub, ast.Attribute) and sub.attr == "execution_kind":
            return True
        if isinstance(sub, ast.Constant) and sub.value == "execution_kind":
            return True
    return False


def _string_literal(node) -> bool:
    """A str constant, a collection of them, or `Str("...")` (the lowering's AST)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return True
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return any(_string_literal(e) for e in node.elts)
    if (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "Str"
            and node.args and isinstance(node.args[0], ast.Constant)):
        return True
    return False


def _violations(path: Path, source: str) -> list[str]:
    out = []
    tree = ast.parse(source)
    for node in ast.walk(tree):
        # 1. execution_kind compared with a literal: `== "goal"`, `in ("workflow", "goal")`
        if isinstance(node, ast.Compare):
            operands = [node.left, *node.comparators]
            kinds = [op for op in operands if _mentions_kind(op)]
            if kinds and any(_string_literal(op) for op in operands if op not in kinds):
                out.append(f"{path}:{node.lineno} compares execution_kind with a literal")
        # 2. a literal passed as the kind: `f(execution_kind="goal")`
        if isinstance(node, ast.keyword) and node.arg == "execution_kind":
            if _string_literal(node.value):
                out.append(f"{path}:{node.value.lineno} passes a literal execution_kind")
        # 3. a literal stored as the kind: `{"execution_kind": "goal"}`, or the
        #    lowering's `(Str("execution_kind"), Str("goal"))` pair.
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if key is not None and _mentions_kind(key) and _string_literal(value):
                    out.append(f"{path}:{value.lineno} stores a literal execution_kind")
        if isinstance(node, ast.Tuple) and len(node.elts) == 2:
            key, value = node.elts
            if _mentions_kind(key) and _string_literal(value):
                out.append(f"{path}:{node.lineno} pairs execution_kind with a literal")
    return out


class TheVocabularyIsNamedOnceTests(unittest.TestCase):

    def test_no_site_spells_a_kind_for_itself(self):
        found = []
        for path in sorted(REPO.joinpath("src").rglob("*.py")):
            rel = path.relative_to(REPO).as_posix()
            if rel == VOCABULARY_MODULE:
                continue
            source = io.open(path, encoding="utf-8").read()
            if "execution_kind" not in source:
                continue
            found.extend(_violations(Path(rel), source))
        self.assertEqual([], found,
                         "use the constants in nodus.orchestration.workflow_state, "
                         "so that adding a kind is one edit and every site has to "
                         "say which kinds it handles")

    def test_the_scan_sees_each_shape_it_claims_to(self):
        """The control: a scan that finds nothing proves nothing unless it would
        have found something."""
        shapes = {
            "compare": 'if execution_kind == "goal": pass',
            "membership": 'ok = record.execution_kind in ("workflow", "goal")',
            "metadata get": 'x = m.get("execution_kind") != "workflow"',
            "keyword": 'f(execution_kind="workflow")',
            "dict": 'd = {"execution_kind": "goal"}',
            "lowering pair": 'p = (Str("execution_kind"), Str("goal"))',
        }
        for name, snippet in shapes.items():
            with self.subTest(name):
                self.assertTrue(_violations(Path("x.py"), snippet), snippet)
        self.assertEqual([], _violations(
            Path("x.py"), "if execution_kind == EXECUTION_KIND_GOAL: pass"))

    def test_the_vocabulary_is_classified(self):
        self.assertEqual(len(EXECUTION_KINDS), len(set(EXECUTION_KINDS)))
        self.assertLessEqual(GRAPH_EXECUTION_KINDS, set(EXECUTION_KINDS))
        self.assertEqual({EXECUTION_KIND_WORKFLOW, EXECUTION_KIND_GOAL}, GRAPH_EXECUTION_KINDS)
        self.assertIn(EXECUTION_KIND_COROUTINE, EXECUTION_KINDS)
        self.assertNotIn(EXECUTION_KIND_COROUTINE, GRAPH_EXECUTION_KINDS)
        # A record from before the field existed is a workflow.
        self.assertTrue(is_graph_execution_kind(None))


class WhatRealRunsRecordTests(unittest.TestCase):

    def test_a_workflow_and_a_goal_record_kinds_from_the_vocabulary(self):
        """The vocabulary has to match what the lowering actually writes, or the
        scan above is guarding a list nobody uses. The block form of `goal` is
        the one that records `goal`; `goal ... over w` runs its iterations as
        runs of the workflow `w`."""
        src = """
            workflow w { step a { return 1i } }
            goal g { step a { return 1i } }
            fn main() {
                let r1 = run_workflow(w)
                let r2 = run_goal(g)
                print("ok")
            }
            main()
            """
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteWorkflowStore(str(Path(tmp) / "runs.db"))
            from nodus_lang_workflow import runner as runner_mod
            previous = runner_mod.get_default_workflow_runner
            runner = WorkflowFrameworkRunner(store)
            runner_mod.get_default_workflow_runner = lambda: runner
            try:
                result = NodusRuntime(timeout_ms=None, max_steps=None).run_source(
                    "\n".join(line[12:] for line in src.splitlines()))
            finally:
                runner_mod.get_default_workflow_runner = previous
            self.assertTrue(result.get("ok"), result.get("error"))
            kinds = {record.execution_kind for record in store.list_all_runs()}
        self.assertEqual({EXECUTION_KIND_WORKFLOW, EXECUTION_KIND_GOAL}, kinds)


class ANonGraphRunIsNotTreatedAsAWorkflowTests(unittest.TestCase):

    def test_the_rebuild_refuses_it_by_name(self):
        vm = NodusRuntime(timeout_ms=None, max_steps=None)
        vm.run_source("let x = 1i")
        state = {"metadata": {"execution_kind": EXECUTION_KIND_COROUTINE,
                              "workflow_name": "worker", "workflow_source_code": "let x = 1i"}}
        with self.assertRaises(WorkflowRebuildError) as caught:
            vm.active_vm()._rebuild_workflow_graph("run-1", state)
        message = caught.exception.describe()
        self.assertIn("'coroutine' run", message)
        self.assertNotIn("is not defined", message)

    def test_the_rehydrate_sweep_leaves_it_alone(self):
        """Unattended, so the one that matters most: it must not build a VM for
        the run, and must not write a rebuild error onto its record each sweep."""
        with tempfile.TemporaryDirectory() as tmp:
            store = SQLiteWorkflowStore(str(Path(tmp) / "runs.db"))
            record = store.create_run(run_id="co-1", graph_id="co-1",
                                      workflow_name="worker",
                                      execution_kind=EXECUTION_KIND_COROUTINE)
            record.status = RUN_STATUS_RUNNING
            store.save_run(record)
            built = []
            result = WorkflowFrameworkRunner(store).rehydrate_runs(
                lambda rec: built.append(rec.run_id))
            after = store.get_run("co-1")
        self.assertEqual([], result)
        self.assertEqual([], built, "a VM was built to rebuild a coroutine as a graph")
        self.assertIsNone(after.last_error)
        self.assertEqual(RUN_STATUS_RUNNING, after.status)


if __name__ == "__main__":
    unittest.main()
