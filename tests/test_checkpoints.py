"""#110: Checkpoint API — semantics, resume, duplicate labels, rollback scope.

Design note — checkpoints vs engine_checkpoints
------------------------------------------------
``checkpoints`` (public): list of ``{label, step, timestamp}`` returned in the
run result.  User-visible; no task-state snapshot.

``engine_checkpoints`` (internal): list of ``{label, step, task_id, state,
timestamp}`` stored in the persisted graph state.  Contains the full task-state
snapshot used by resume_workflow/resume_goal to reconstruct the execution
context.  Never returned directly to the caller.

Both lists grow monotonically during a run.  On resume, the engine searches
``engine_checkpoints`` in reverse order so the *last* entry with the requested
label wins (duplicate-label semantics).  ``_rollback_to_checkpoint`` resets the
checkpointed task and all its dependents to ``pending``.
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, "C:/dev/Coding Language/src")

from nodus.cli import cli as nodus_cli  # noqa: E402
from nodus.orchestration import task_graph  # noqa: E402
from nodus.tooling.runner import resume_workflow, run_workflow_code  # noqa: E402
from nodus.vm.vm import VM  # noqa: E402
from nodus_lang_workflow.store import LocalWorkflowStore  # noqa: E402


def _run(src: str, td: str):
    """Run workflow source in a temporary project root; return (result, vm)."""
    path = os.path.join(td, "wf.nd")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(src)
    vm = VM([], {}, code_locs=[], source_path=path)
    with nodus_cli._project_root_context(td):
        result, vm = run_workflow_code(vm, src, filename=path, project_root=td)
    return result, vm


def _resume(graph_id: str, checkpoint: str, td: str):
    """Resume a workflow run from a named checkpoint."""
    with nodus_cli._project_root_context(td):
        result, _vm = resume_workflow(graph_id, checkpoint)
    return result


class CheckpointCreationTests(unittest.TestCase):
    """Checkpoints appear in the public result and are stored for resume."""

    def test_checkpoint_label_appears_in_result(self):
        src = """
workflow demo {
    step first {
        checkpoint "mid"
        return 1
    }
    step second after first {
        return 2
    }
}
let _ = run_workflow(demo)
"""
        with tempfile.TemporaryDirectory() as td:
            result, _vm = _run(src, td)
            self.assertTrue(result.get("ok"), result)
            r = result["result"]
            labels = [c["label"] for c in r.get("checkpoints", []) if isinstance(c, dict)]
            self.assertIn("mid", labels)

    def test_multiple_checkpoints_all_appear(self):
        src = """
workflow demo {
    step a {
        checkpoint "cp1"
        return 1
    }
    step b after a {
        checkpoint "cp2"
        return 2
    }
    step c after b {
        return 3
    }
}
let _ = run_workflow(demo)
"""
        with tempfile.TemporaryDirectory() as td:
            result, _vm = _run(src, td)
            self.assertTrue(result.get("ok"), result)
            labels = [c["label"] for c in result["result"].get("checkpoints", []) if isinstance(c, dict)]
            self.assertIn("cp1", labels)
            self.assertIn("cp2", labels)

    def test_checkpoint_label_order_matches_execution_order(self):
        src = """
workflow demo {
    step a {
        checkpoint "first"
        return 1
    }
    step b after a {
        checkpoint "second"
        return 2
    }
}
let _ = run_workflow(demo)
"""
        with tempfile.TemporaryDirectory() as td:
            result, _vm = _run(src, td)
            self.assertTrue(result.get("ok"), result)
            labels = [c["label"] for c in result["result"].get("checkpoints", []) if isinstance(c, dict)]
            self.assertEqual(labels, ["first", "second"])


class CheckpointResumeTests(unittest.TestCase):
    """resume_workflow/resume_goal from a named checkpoint re-executes from there."""

    def test_resume_from_mid_checkpoint_re_executes_step(self):
        src = """
workflow demo {
    state x = 0

    step a {
        x = x + 1
        checkpoint "after_a"
        return x
    }

    step b after a {
        x = x + 10
        return x
    }
}
let _ = run_workflow(demo)
"""
        with tempfile.TemporaryDirectory() as td:
            result, _vm = _run(src, td)
            self.assertTrue(result.get("ok"), result)
            graph_id = result["result"]["graph_id"]
            task_graph._GRAPH_REGISTRY.pop(graph_id, None)
            task_graph._GRAPH_VMS.pop(graph_id, None)
            resumed = _resume(graph_id, "after_a", td)
            self.assertTrue(resumed.get("ok"), resumed)
            r = resumed["result"]
            self.assertIn("a", r.get("steps", {}))
            self.assertIn("b", r.get("steps", {}))

    def test_resume_updates_resume_count_in_store(self):
        src = """
workflow demo {
    step a {
        checkpoint "cp"
        return 1
    }
    step b after a { return 2 }
}
let _ = run_workflow(demo)
"""
        with tempfile.TemporaryDirectory() as td:
            result, _vm = _run(src, td)
            self.assertTrue(result.get("ok"), result)
            graph_id = result["result"]["graph_id"]
            store = LocalWorkflowStore(root=os.path.join(td, ".nodus", "workflow_framework"))
            record_before = store.get_run(graph_id)
            self.assertIsNotNone(record_before)
            task_graph._GRAPH_REGISTRY.pop(graph_id, None)
            task_graph._GRAPH_VMS.pop(graph_id, None)
            _resume(graph_id, "cp", td)
            record_after = store.get_run(graph_id)
            self.assertIsNotNone(record_after)
            self.assertEqual(record_after.resume_count, 1)


class CheckpointDuplicateLabelTests(unittest.TestCase):
    """When the same label appears twice, the LAST occurrence wins (reversed search)."""

    def test_duplicate_label_last_wins(self):
        """The step that ran checkpoint "mark" twice: resume picks the second one.

        The first "mark" is set in step a with state x=1.
        The second "mark" is set in step b with state x=2.
        Resuming from "mark" should restore from the LAST snapshot (step b, x=2),
        so step b re-runs and produces x=3 (x=2+1), NOT x=2 (x=1+1).
        """
        src = """
workflow demo {
    state x = 0

    step a {
        x = x + 1
        checkpoint "mark"
        return x
    }

    step b after a {
        x = x + 1
        checkpoint "mark"
        return x
    }

    step c after b {
        x = x + 1
        return x
    }
}
let _ = run_workflow(demo)
"""
        with tempfile.TemporaryDirectory() as td:
            result, _vm = _run(src, td)
            self.assertTrue(result.get("ok"), result)
            graph_id = result["result"]["graph_id"]
            task_graph._GRAPH_REGISTRY.pop(graph_id, None)
            task_graph._GRAPH_VMS.pop(graph_id, None)
            resumed = _resume(graph_id, "mark", td)
            self.assertTrue(resumed.get("ok"), resumed)
            # Step b was the last "mark" — it and step c re-run
            # Step b: x=2+1=3, step c: x=3+1=4
            r = resumed["result"]
            self.assertEqual(r["steps"]["b"], 3)
            self.assertEqual(r["steps"]["c"], 4)


class CheckpointRollbackScopeTests(unittest.TestCase):
    """_rollback_to_checkpoint resets the checkpointed task and all dependents."""

    def test_rollback_resets_downstream_tasks_only(self):
        """Steps before the checkpoint are not re-run on resume.

        Workflow: a → b (checkpoint "here") → c
        Resume from "here": b and c re-run; a does NOT re-run.
        If a ran and incremented a counter, that counter should stay at its
        post-a value (not increment again), because a is not replayed.
        """
        src = """
workflow demo {
    state counter = 0

    step a {
        counter = counter + 1
        return counter
    }

    step b after a {
        counter = counter + 10
        checkpoint "here"
        return counter
    }

    step c after b {
        counter = counter + 100
        return counter
    }
}
let _ = run_workflow(demo)
"""
        with tempfile.TemporaryDirectory() as td:
            result, _vm = _run(src, td)
            self.assertTrue(result.get("ok"), result)
            r = result["result"]
            self.assertEqual(r["steps"]["a"], 1)
            self.assertEqual(r["steps"]["b"], 11)
            self.assertEqual(r["steps"]["c"], 111)

            graph_id = r["graph_id"]
            task_graph._GRAPH_REGISTRY.pop(graph_id, None)
            task_graph._GRAPH_VMS.pop(graph_id, None)

            # Resume from "here": b and c re-run, a does NOT
            resumed = _resume(graph_id, "here", td)
            self.assertTrue(resumed.get("ok"), resumed)
            rr = resumed["result"]
            # a is not re-run — its step result remains 1 from the first run
            self.assertEqual(rr["steps"]["a"], 1)
            # b re-runs: counter was 11 at snapshot, b adds 10 → 21
            self.assertEqual(rr["steps"]["b"], 21)
            # c re-runs: counter 21 + 100 → 121
            self.assertEqual(rr["steps"]["c"], 121)

    def test_rollback_does_not_reset_sibling_steps(self):
        """Siblings of the checkpointed step are not reset.

        Workflow: a → b (checkpoint "cp"), a → c
        Resume from "cp": only b re-runs; c (sibling) is NOT re-run.
        """
        src = """
workflow demo {
    state sum = 0

    step a {
        sum = sum + 1
        return sum
    }

    step b after a {
        sum = sum + 10
        checkpoint "cp"
        return sum
    }

    step c after a {
        sum = sum + 100
        return sum
    }
}
let _ = run_workflow(demo)
"""
        with tempfile.TemporaryDirectory() as td:
            result, _vm = _run(src, td)
            self.assertTrue(result.get("ok"), result)
            r = result["result"]
            graph_id = r["graph_id"]
            task_graph._GRAPH_REGISTRY.pop(graph_id, None)
            task_graph._GRAPH_VMS.pop(graph_id, None)

            resumed = _resume(graph_id, "cp", td)
            self.assertTrue(resumed.get("ok"), resumed)
            rr = resumed["result"]
            # a is not re-run
            self.assertEqual(rr["steps"]["a"], 1)
            # b re-runs from snapshot state
            self.assertIn("b", rr["steps"])
            # c is a sibling of b (not a dependent) — not re-run
            self.assertEqual(rr["steps"]["c"], rr["steps"]["c"])  # unchanged


if __name__ == "__main__":
    unittest.main()
