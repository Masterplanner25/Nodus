import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, "C:/dev/Coding Language/src")

import nodus as lang  # noqa: E402
from nodus.cli import cli as nodus_cli  # noqa: E402
from nodus.orchestration import task_graph  # noqa: E402
from nodus.tooling.runner import resume_workflow, run_workflow_code  # noqa: E402
from nodus.vm.vm import VM  # noqa: E402
from nodus_lang_workflow.models import (  # noqa: E402
    RUN_STATUS_COMPLETED,
    RUN_STATUS_DEAD_LETTERED,
    RUN_STATUS_FAILED,
    RUN_STATUS_RETRY_SCHEDULED,
    RUN_STATUS_WAITING,
)
import nodus_lang_workflow.runner as _wf_runner  # noqa: E402
from nodus_lang_workflow.runner import WorkflowFrameworkRunner  # noqa: E402
from nodus_lang_workflow.store import LocalWorkflowStore, SQLiteWorkflowStore, WorkflowStore, create_workflow_store  # noqa: E402


WORKFLOW_SOURCE = """
workflow demo {
    state value = 0

    step first {
        checkpoint "after-first"
        return 1
    }

    step second after first {
        value = first + 1
        return value
    }
}
"""


def framework_store(project_root: str):
    return LocalWorkflowStore(root=os.path.join(project_root, ".nodus", "workflow_framework"))


class LocalWorkflowStoreTests(unittest.TestCase):
    def test_claim_run_is_exclusive_until_release(self):
        with tempfile.TemporaryDirectory() as td:
            store = LocalWorkflowStore(root=td)
            store.create_run(
                run_id="run-1",
                graph_id="run-1",
                workflow_name="demo",
                execution_kind="workflow",
            )
            first = store.claim_run("run-1", owner="worker-a")
            second = store.claim_run("run-1", owner="worker-b")
            self.assertIsNotNone(first)
            self.assertIsNone(second)
            store.release_claim("run-1", first.token)
            third = store.claim_run("run-1", owner="worker-c")
            self.assertIsNotNone(third)

    def test_wait_registration_can_be_claimed_for_resume(self):
        with tempfile.TemporaryDirectory() as td:
            store = LocalWorkflowStore(root=td)
            store.create_run(
                run_id="run-2",
                graph_id="run-2",
                workflow_name="demo",
                execution_kind="workflow",
            )
            record = store.register_wait(
                "run-2",
                event_type="approval.granted",
                correlation_key="req-7",
                payload={"step": "review"},
            )
            self.assertEqual(record.status, RUN_STATUS_WAITING)
            claim = store.claim_waiting_run_for_resume(
                "run-2",
                owner="worker-a",
                event_type="approval.granted",
                correlation_key="req-7",
            )
            self.assertIsNotNone(claim)

    def test_wait_timeout_expires_to_dead_lettered(self):
        with tempfile.TemporaryDirectory() as td:
            store = LocalWorkflowStore(root=td)
            store.create_run(
                run_id="run-3",
                graph_id="run-3",
                workflow_name="demo",
                execution_kind="workflow",
            )
            record = store.register_wait(
                "run-3",
                event_type="approval.granted",
                correlation_key="req-timeout",
                payload={"step": "review"},
                deadline_ms=5,
            )
            self.assertIsNotNone(record)
            expired = store.expire_wait_timeout("run-3", now_ms=(record.wait.registered_at or 0) + 10)
            self.assertIsNotNone(expired)
            self.assertEqual(expired.status, RUN_STATUS_DEAD_LETTERED)
            self.assertIn("Wait timeout expired", expired.last_error)


class SQLiteWorkflowStoreTests(unittest.TestCase):
    def test_claim_run_is_exclusive_across_store_instances(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "workflow_framework.sqlite3")
            store_a = SQLiteWorkflowStore(path=path)
            store_b = SQLiteWorkflowStore(path=path)
            store_a.create_run(
                run_id="run-sql-1",
                graph_id="run-sql-1",
                workflow_name="demo",
                execution_kind="workflow",
            )
            first = store_a.claim_run("run-sql-1", owner="worker-a")
            second = store_b.claim_run("run-sql-1", owner="worker-b")
            self.assertIsNotNone(first)
            self.assertIsNone(second)
            store_a.release_claim("run-sql-1", first.token)
            third = store_b.claim_run("run-sql-1", owner="worker-c")
            self.assertIsNotNone(third)

    def test_wait_claim_is_visible_across_store_instances(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "workflow_framework.sqlite3")
            store_a = SQLiteWorkflowStore(path=path)
            store_b = SQLiteWorkflowStore(path=path)
            store_a.create_run(
                run_id="run-sql-2",
                graph_id="run-sql-2",
                workflow_name="demo",
                execution_kind="workflow",
            )
            store_a.register_wait(
                "run-sql-2",
                event_type="approval.granted",
                correlation_key="req-sql",
                payload={"step": "review"},
            )
            claim = store_b.claim_waiting_run_for_resume(
                "run-sql-2",
                owner="worker-b",
                event_type="approval.granted",
                correlation_key="req-sql",
            )
            self.assertIsNotNone(claim)

    def test_store_factory_returns_workflow_store_contract(self):
        with tempfile.TemporaryDirectory() as td:
            local = create_workflow_store(backend="local", root=os.path.join(td, "framework"))
            sqlite = create_workflow_store(backend="sqlite", path=os.path.join(td, "workflow.sqlite3"))
            self.assertIsInstance(local, WorkflowStore)
            self.assertIsInstance(sqlite, WorkflowStore)
            self.assertEqual(local.store_info()["backend"], "local")
            self.assertEqual(sqlite.store_info()["backend"], "sqlite")


class LocalWorkflowStoreScanTests(unittest.TestCase):
    """#102: LocalWorkflowStore.list_runs() must skip files older than terminal_max_age_days."""

    def test_old_files_are_excluded_from_list_runs(self):
        """Files not modified within terminal_max_age_days must not appear in list_runs."""
        with tempfile.TemporaryDirectory() as td:
            store = LocalWorkflowStore(root=td, terminal_max_age_days=1)
            store.create_run(
                run_id="new-run",
                graph_id="new-run",
                workflow_name="demo",
                execution_kind="workflow",
            )
            store.create_run(
                run_id="old-run",
                graph_id="old-run",
                workflow_name="demo",
                execution_kind="workflow",
            )
            # Backdate the old-run file to 2+ days ago
            old_path = store._run_path("old-run")
            old_mtime = time.time() - 2 * 86_400
            os.utime(old_path, (old_mtime, old_mtime))

            runs = store.list_runs()
            run_ids = {r.run_id for r in runs}
            self.assertIn("new-run", run_ids)
            self.assertNotIn("old-run", run_ids, "Files older than terminal_max_age_days must be skipped")

    def test_zero_max_age_disables_filtering(self):
        """terminal_max_age_days=0 must disable mtime filtering (all files returned)."""
        with tempfile.TemporaryDirectory() as td:
            store = LocalWorkflowStore(root=td, terminal_max_age_days=0)
            store.create_run(
                run_id="run-a",
                graph_id="run-a",
                workflow_name="demo",
                execution_kind="workflow",
            )
            old_path = store._run_path("run-a")
            os.utime(old_path, (0, 0))  # epoch — oldest possible

            runs = store.list_runs()
            self.assertTrue(any(r.run_id == "run-a" for r in runs))

    def test_recent_run_always_returned(self):
        """A run modified just now must always appear regardless of max_age."""
        with tempfile.TemporaryDirectory() as td:
            store = LocalWorkflowStore(root=td, terminal_max_age_days=1)
            store.create_run(
                run_id="fresh",
                graph_id="fresh",
                workflow_name="demo",
                execution_kind="workflow",
            )
            runs = store.list_runs()
            self.assertTrue(any(r.run_id == "fresh" for r in runs))


class WorkflowStoreSharedBehaviorTests(unittest.TestCase):
    def _store_cases(self, td: str):
        return [
            ("local", LocalWorkflowStore(root=os.path.join(td, "local"))),
            ("sqlite", SQLiteWorkflowStore(path=os.path.join(td, "workflow.sqlite3"))),
        ]

    def test_retry_metadata_shape_matches_across_backends(self):
        with tempfile.TemporaryDirectory() as td:
            for backend, store in self._store_cases(td):
                run_id = f"retry-{backend}"
                store.create_run(
                    run_id=run_id,
                    graph_id=run_id,
                    workflow_name="demo",
                    execution_kind="workflow",
                )
                record = store.schedule_retry(
                    run_id,
                    task_id="task_1",
                    step_name="flaky",
                    attempt=1.0,
                    max_retries=2.0,
                    delay_ms=50.0,
                    next_attempt_at=125.0,
                    classification=None,
                    last_error="boom",
                )
                self.assertIsNotNone(record)
                self.assertEqual(record.status, RUN_STATUS_RETRY_SCHEDULED)
                self.assertIsNone(record.wait)
                self.assertEqual(
                    record.metadata.get("retry"),
                    {
                        "task_id": "task_1",
                        "step": "flaky",
                        "attempt": 1.0,
                        "max_retries": 2.0,
                        "delay_ms": 50.0,
                        "next_attempt_at": 125.0,
                        "classification": "retryable",
                        "last_error": "boom",
                    },
                )

    def test_wait_timeout_metadata_shape_matches_across_backends(self):
        with tempfile.TemporaryDirectory() as td:
            for backend, store in self._store_cases(td):
                run_id = f"timeout-{backend}"
                store.create_run(
                    run_id=run_id,
                    graph_id=run_id,
                    workflow_name="demo",
                    execution_kind="workflow",
                )
                waiting = store.register_wait(
                    run_id,
                    event_type="approval.granted",
                    correlation_key="req-shared",
                    payload={"step": "review"},
                    deadline_ms=5.0,
                )
                self.assertIsNotNone(waiting)
                expired = store.expire_wait_timeout(
                    run_id,
                    now_ms=(waiting.wait.registered_at or 0.0) + 10.0,
                )
                self.assertIsNotNone(expired)
                self.assertEqual(expired.status, RUN_STATUS_DEAD_LETTERED)
                timeout_info = expired.metadata.get("wait_timeout")
                self.assertIsInstance(timeout_info, dict)
                self.assertEqual(timeout_info.get("deadline_ms"), 5.0)
                self.assertEqual(timeout_info.get("event_type"), "approval.granted")
                self.assertEqual(timeout_info.get("correlation_key"), "req-shared")


class WorkflowFrameworkCompatibilityTests(unittest.TestCase):
    def setUp(self):
        # Reset the global default-runner cache so each test starts fresh.
        # get_default_workflow_runner() is keyed on os.getcwd(); stale state
        # from previous tests (deleted temp dirs) causes it to create a runner
        # pointing at the wrong directory.
        _wf_runner._DEFAULT_RUNNER = None
        _wf_runner._DEFAULT_RUNNER_ROOT = None

    def _run_demo_workflow(self, project_root: str):
        path = os.path.join(project_root, "demo.nd")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(WORKFLOW_SOURCE)
        code = open(path, "r", encoding="utf-8").read()
        with nodus_cli._project_root_context(project_root):
            result, _vm = run_workflow_code(
                VM([], {}, code_locs=[], source_path=None),
                code,
                filename=path,
                project_root=project_root,
            )
        self.assertTrue(result.get("ok"))
        return result["result"]

    def test_run_workflow_records_completed_framework_run(self):
        with tempfile.TemporaryDirectory() as td:
            payload = self._run_demo_workflow(td)
            graph_id = payload["graph_id"]
            store = framework_store(td)
            record = store.get_run(graph_id)
            self.assertIsNotNone(record)
            self.assertEqual(record.status, RUN_STATUS_COMPLETED)
            self.assertEqual(record.workflow_name, "demo")
            self.assertEqual(record.current_checkpoint, "after-first")

    def test_resume_workflow_updates_resume_count(self):
        with tempfile.TemporaryDirectory() as td:
            payload = self._run_demo_workflow(td)
            graph_id = payload["graph_id"]
            with nodus_cli._project_root_context(td):
                resumed, _vm = resume_workflow(graph_id, "after-first", timeout_ms=None)
            self.assertTrue(resumed.get("ok"), msg=str(resumed))
            self.assertEqual(resumed["result"]["steps"]["second"], 2)
            store = framework_store(td)
            record = store.get_run(graph_id)
            self.assertIsNotNone(record)
            self.assertEqual(record.status, RUN_STATUS_COMPLETED)
            self.assertEqual(record.resume_count, 1)

    def test_framework_runner_uses_existing_task_graph_execution(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "demo.nd")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(WORKFLOW_SOURCE + "\nlet _ = run_workflow(demo)\n")
            vm = lang.VM([], {}, code_locs=[], source_path=path)
            with nodus_cli._project_root_context(td):
                result, vm = run_workflow_code(vm, WORKFLOW_SOURCE, filename=path, project_root=td)
            self.assertTrue(result.get("ok"))
            graph_id = result["result"]["graph_id"]
            runner = WorkflowFrameworkRunner(framework_store(td))
            record = runner.store.get_run(graph_id)
            self.assertEqual(record.metadata.get("coordination_mode"), "local_only")

    def test_mark_waiting_moves_run_into_rehydratable_set(self):
        with tempfile.TemporaryDirectory() as td:
            payload = self._run_demo_workflow(td)
            graph_id = payload["graph_id"]
            runner = WorkflowFrameworkRunner(framework_store(td))
            record = runner.mark_waiting(
                graph_id,
                event_type="approval.granted",
                correlation_key="req-9",
                payload={"step": "second"},
            )
            self.assertIsNotNone(record)
            self.assertEqual(record.status, RUN_STATUS_WAITING)
            rehydratable = {item.run_id for item in runner.list_rehydratable_runs()}
            self.assertIn(graph_id, rehydratable)

    def test_resume_clears_wait_registration(self):
        with tempfile.TemporaryDirectory() as td:
            payload = self._run_demo_workflow(td)
            graph_id = payload["graph_id"]
            runner = WorkflowFrameworkRunner(framework_store(td))
            runner.mark_waiting(
                graph_id,
                event_type="approval.granted",
                correlation_key="req-10",
                payload={"step": "second"},
            )
            with nodus_cli._project_root_context(td):
                resumed, _vm = resume_workflow(graph_id, "after-first")
            self.assertTrue(resumed.get("ok"))
            record = runner.get_run(graph_id)
            self.assertIsNotNone(record)
            self.assertEqual(record.status, RUN_STATUS_COMPLETED)
            self.assertIsNone(record.wait)

    def test_list_runs_returns_framework_records(self):
        with tempfile.TemporaryDirectory() as td:
            payload = self._run_demo_workflow(td)
            graph_id = payload["graph_id"]
            runner = WorkflowFrameworkRunner(framework_store(td))
            run_ids = {record.run_id for record in runner.list_runs()}
            self.assertIn(graph_id, run_ids)

    def test_list_runs_filtered_and_counts_cover_multiple_statuses(self):
        with tempfile.TemporaryDirectory() as td:
            completed = self._run_demo_workflow(td)
            completed_id = completed["graph_id"]
            runner = WorkflowFrameworkRunner(framework_store(td))
            runner.mark_waiting(
                completed_id,
                event_type="approval.granted",
                correlation_key="req-filter",
                payload={"step": "second"},
            )
            waiting_ids = {record.run_id for record in runner.list_runs_filtered(statuses={RUN_STATUS_WAITING})}
            self.assertIn(completed_id, waiting_ids)

            counts = runner.run_status_counts()
            self.assertGreaterEqual(counts[RUN_STATUS_WAITING], 1)
            self.assertEqual(runner.list_runs_filtered(statuses={"not_a_status"}), [])
            filtered = runner.list_runs_filtered(
                statuses={RUN_STATUS_WAITING},
                workflow_name="demo",
                execution_kind="workflow",
                limit=1,
                offset=0,
            )
            self.assertEqual(len(filtered), 1)
            self.assertEqual(filtered[0].workflow_name, "demo")
            self.assertEqual(filtered[0].execution_kind, "workflow")

    def test_run_inventory_returns_scoped_counts_and_pagination(self):
        with tempfile.TemporaryDirectory() as td:
            first = self._run_demo_workflow(td)
            second = self._run_demo_workflow(td)
            runner = WorkflowFrameworkRunner(framework_store(td))
            runner.mark_waiting(
                first["graph_id"],
                event_type="approval.granted",
                correlation_key="req-inventory-1",
                payload={"step": "second"},
            )
            runner.mark_waiting(
                second["graph_id"],
                event_type="approval.granted",
                correlation_key="req-inventory-2",
                payload={"step": "second"},
            )

            payload = runner.run_inventory(
                statuses={RUN_STATUS_WAITING},
                workflow_name="demo",
                execution_kind="workflow",
                limit=1,
                offset=0,
            )
            self.assertEqual(payload["counts"][RUN_STATUS_WAITING], 2)
            self.assertEqual(payload["counts"][RUN_STATUS_COMPLETED], 0)
            self.assertEqual(payload["filter"]["status"], [RUN_STATUS_WAITING])
            self.assertEqual(payload["pagination"]["total"], 2)
            self.assertEqual(payload["pagination"]["returned"], 1)
            self.assertTrue(payload["pagination"]["has_more"])
            self.assertEqual(len(payload["runs"]), 1)

    def test_run_inventory_supports_retry_wait_time_and_cursor_filters(self):
        with tempfile.TemporaryDirectory() as td:
            completed = self._run_demo_workflow(td)
            graph_id = completed["graph_id"]
            runner = WorkflowFrameworkRunner(framework_store(td))

            waiting = runner.mark_waiting(
                graph_id,
                event_type="approval.granted",
                correlation_key="req-advanced-filter",
                payload={"step": "second"},
            )
            self.assertIsNotNone(waiting)
            waiting.metadata["replay_count"] = 2
            runner.store.save_run(waiting)

            retry_id = "retry-filtered"
            retry_record = runner.store.create_run(
                run_id=retry_id,
                graph_id=retry_id,
                workflow_name="demo",
                execution_kind="workflow",
                metadata={},
            )
            retry_record.updated_at = (waiting.updated_at or 0) + 5
            runner.store.save_run(retry_record)
            runner.store.schedule_retry(
                retry_id,
                task_id="task_1",
                step_name="flaky",
                attempt=1.0,
                max_retries=2.0,
                delay_ms=50.0,
                next_attempt_at=999999.0,
                classification="retryable",
                last_error="boom",
            )

            filtered = runner.run_inventory(
                workflow_name="demo",
                execution_kind="workflow",
                updated_after_ms=(waiting.updated_at or 0) - 1,
                updated_before_ms=(waiting.updated_at or 0) + 1,
                has_wait=True,
                has_retry=False,
                replay_count_min=2,
                limit=1,
                cursor="o:0",
            )
            self.assertEqual(filtered["counts"][RUN_STATUS_WAITING], 1)
            self.assertEqual(filtered["counts"][RUN_STATUS_RETRY_SCHEDULED], 0)
            self.assertEqual(filtered["pagination"]["cursor"], "o:0")
            self.assertIsNone(filtered["pagination"]["next_cursor"])
            self.assertEqual(len(filtered["runs"]), 1)
            self.assertEqual(filtered["runs"][0]["run_id"], graph_id)

            paged = runner.run_inventory(
                workflow_name="demo",
                execution_kind="workflow",
                limit=1,
                cursor="o:0",
            )
            self.assertEqual(paged["pagination"]["next_cursor"], "o:1")
            next_page = runner.run_inventory(
                workflow_name="demo",
                execution_kind="workflow",
                limit=1,
                cursor=paged["pagination"]["next_cursor"],
            )
            self.assertEqual(next_page["pagination"]["cursor"], "o:1")
            self.assertEqual(len(next_page["runs"]), 1)

    def test_framework_records_waiting_run_and_resume(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "wait_demo.nd")
            code = """
workflow demo {
    step gate {
        return workflow_wait("approval.granted", "req-42", {kind: "approval"})
    }

    step finish after gate {
        return "done"
    }
}
"""
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(code)
            with nodus_cli._project_root_context(td):
                result, _vm = run_workflow_code(
                    VM([], {}, code_locs=[], source_path=None),
                    code,
                    filename=path,
                    project_root=td,
                )
            self.assertTrue(result.get("ok"))
            payload = result["result"]
            self.assertEqual(payload["status"], "waiting")
            self.assertEqual(payload["wait"]["event_type"], "approval.granted")
            graph_id = payload["graph_id"]

            runner = WorkflowFrameworkRunner(framework_store(td))
            record = runner.get_run(graph_id)
            self.assertIsNotNone(record)
            self.assertEqual(record.status, RUN_STATUS_WAITING)
            self.assertEqual(record.wait.event_type, "approval.granted")

            with nodus_cli._project_root_context(td):
                resumed, _vm = resume_workflow(graph_id)
            self.assertTrue(resumed.get("ok"))
            self.assertEqual(resumed["result"]["steps"]["finish"], "done")
            record = runner.get_run(graph_id)
            self.assertEqual(record.status, RUN_STATUS_COMPLETED)
            self.assertIsNone(record.wait)

    def test_resume_waiting_run_rejects_mismatched_event_type(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "wait_mismatch.nd")
            code = """
workflow demo {
    step gate {
        return workflow_wait("approval.granted", "req-55", {kind: "approval"})
    }

    step finish after gate {
        return "done"
    }
}
"""
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(code)
            with nodus_cli._project_root_context(td):
                result, _vm = run_workflow_code(
                    VM([], {}, code_locs=[], source_path=None),
                    code,
                    filename=path,
                    project_root=td,
                )
            self.assertTrue(result.get("ok"))
            graph_id = result["result"]["graph_id"]

            with nodus_cli._project_root_context(td):
                resumed, _vm = resume_workflow(
                    graph_id,
                    resume_payload={"approved": True},
                    event_type="approval.denied",
                    correlation_key="req-55",
                )
            self.assertTrue(resumed.get("ok"))
            self.assertFalse(resumed["result"].get("ok"))
            self.assertIn("mismatch", resumed["result"]["error"])

    def test_resume_waiting_run_accepts_payload_and_tracks_metadata(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "wait_payload.nd")
            code = """
workflow demo {
    step gate {
        return workflow_wait("approval.granted", "req-77", {kind: "approval"})
    }

    step finish after gate {
        let payload = workflow_resume_payload()
        return payload["reviewer"]
    }
}
"""
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(code)
            with nodus_cli._project_root_context(td):
                result, _vm = run_workflow_code(
                    VM([], {}, code_locs=[], source_path=None),
                    code,
                    filename=path,
                    project_root=td,
                )
            self.assertTrue(result.get("ok"))
            graph_id = result["result"]["graph_id"]
            runner = WorkflowFrameworkRunner(framework_store(td))

            with nodus_cli._project_root_context(td):
                resumed, _vm = resume_workflow(
                    graph_id,
                    resume_payload={"reviewer": "framework-user"},
                    event_type="approval.granted",
                    correlation_key="req-77",
                )
            self.assertTrue(resumed.get("ok"))
            self.assertEqual(resumed["result"]["steps"]["finish"], "framework-user")
            record = runner.get_run(graph_id)
            self.assertIsNotNone(record)
            self.assertEqual(record.status, RUN_STATUS_COMPLETED)
            self.assertEqual(record.metadata.get("resume_payload"), {"reviewer": "framework-user"})

    def test_expired_wait_is_terminal_and_not_rehydratable(self):
        with tempfile.TemporaryDirectory() as td:
            payload = self._run_demo_workflow(td)
            graph_id = payload["graph_id"]
            runner = WorkflowFrameworkRunner(framework_store(td))
            record = runner.mark_waiting(
                graph_id,
                event_type="approval.granted",
                correlation_key="req-timeout-2",
                payload={"step": "second"},
                deadline_ms=5,
            )
            self.assertIsNotNone(record)
            expired = runner.expire_wait_timeouts(now_ms=(record.wait.registered_at or 0) + 10)
            self.assertEqual(len(expired), 1)
            self.assertEqual(expired[0].status, RUN_STATUS_DEAD_LETTERED)
            rehydratable = {item.run_id for item in runner.list_rehydratable_runs()}
            self.assertNotIn(graph_id, rehydratable)
            terminal = {item.run_id for item in runner.store.list_terminal_runs()}
            self.assertIn(graph_id, terminal)

    def test_resume_rejects_expired_wait(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "wait_timeout_resume.nd")
            code = """
workflow demo {
    step gate {
        return workflow_wait("approval.granted", "req-expired", {kind: "approval"}, 5)
    }

    step finish after gate {
        return "done"
    }
}
"""
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(code)
            with nodus_cli._project_root_context(td):
                result, _vm = run_workflow_code(
                    VM([], {}, code_locs=[], source_path=None),
                    code,
                    filename=path,
                    project_root=td,
                )
            self.assertTrue(result.get("ok"))
            graph_id = result["result"]["graph_id"]
            runner = WorkflowFrameworkRunner(framework_store(td))
            record = runner.get_run(graph_id)
            self.assertIsNotNone(record)
            expired_now = (record.wait.registered_at or 0) + 10
            runner.expire_wait_timeouts(now_ms=expired_now)

            with nodus_cli._project_root_context(td):
                resumed, _vm = resume_workflow(
                    graph_id,
                    resume_payload={"approved": True},
                    event_type="approval.granted",
                    correlation_key="req-expired",
                )
            self.assertTrue(resumed.get("ok"))
            self.assertFalse(resumed["result"].get("ok"))
            self.assertIn("Wait timeout expired", resumed["result"]["error"])
            record = runner.get_run(graph_id)
            self.assertIsNotNone(record)
            self.assertEqual(record.status, RUN_STATUS_DEAD_LETTERED)

    def test_dead_lettered_runs_can_be_listed_rearmed_and_replayed(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "wait_replay.nd")
            code = """
workflow demo {
    step gate {
        return workflow_wait("approval.granted", "req-replay", {kind: "approval"}, 500)
    }

    step finish after gate {
        let payload = workflow_resume_payload()
        return payload["approved"]
    }
}
"""
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(code)
            with nodus_cli._project_root_context(td):
                result, _vm = run_workflow_code(
                    VM([], {}, code_locs=[], source_path=None),
                    code,
                    filename=path,
                    project_root=td,
                )
            self.assertTrue(result.get("ok"))
            graph_id = result["result"]["graph_id"]
            runner = WorkflowFrameworkRunner(framework_store(td))
            record = runner.get_run(graph_id)
            self.assertIsNotNone(record)
            runner.expire_wait_timeouts(now_ms=(record.wait.registered_at or 0) + 1000)

            dead_letters = {item.run_id for item in runner.list_dead_lettered_runs()}
            self.assertIn(graph_id, dead_letters)

            fresh_vm = VM([], {}, code_locs=[], source_path=None)
            with nodus_cli._project_root_context(td):
                rearmed = runner.replay_workflow(
                    fresh_vm,
                    graph_id,
                    rearm_only=True,
                    rebuild_graph=fresh_vm._rebuild_workflow_graph,
                )
            self.assertTrue(rearmed.get("ok"))
            self.assertTrue(rearmed.get("rearmed"))
            record = runner.get_run(graph_id)
            self.assertIsNotNone(record)
            self.assertEqual(record.status, RUN_STATUS_WAITING)

            with nodus_cli._project_root_context(td):
                replayed = runner.replay_workflow(
                    fresh_vm,
                    graph_id,
                    resume_payload={"approved": True},
                    event_type="approval.granted",
                    correlation_key="req-replay",
                    rebuild_graph=fresh_vm._rebuild_workflow_graph,
                )
            self.assertEqual(replayed["steps"]["finish"], True)
            record = runner.get_run(graph_id)
            self.assertIsNotNone(record)
            self.assertEqual(record.status, RUN_STATUS_COMPLETED)
            self.assertEqual(record.metadata.get("replay_count"), 1)

    def test_rehydrate_waiting_run_registers_graph_and_vm(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "wait_rehydrate.nd")
            code = """
workflow demo {
    step gate {
        return workflow_wait("approval.granted", "req-rehydrate", {kind: "approval"})
    }

    step finish after gate {
        return "done"
    }
}
"""
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(code)
            with nodus_cli._project_root_context(td):
                result, _vm = run_workflow_code(
                    VM([], {}, code_locs=[], source_path=None),
                    code,
                    filename=path,
                    project_root=td,
                )
            self.assertTrue(result.get("ok"))
            graph_id = result["result"]["graph_id"]
            task_graph._GRAPH_REGISTRY.pop(graph_id, None)
            task_graph._GRAPH_VMS.pop(graph_id, None)

            runner = WorkflowFrameworkRunner(framework_store(td))
            fresh_vm = VM([], {}, code_locs=[], source_path=None)
            with nodus_cli._project_root_context(td):
                info = runner.rehydrate_run(
                    fresh_vm,
                    graph_id,
                    rebuild_graph=fresh_vm._rebuild_workflow_graph,
                )
            self.assertIsNotNone(info)
            self.assertEqual(info["status"], RUN_STATUS_WAITING)
            self.assertIsNotNone(task_graph.get_registered_graph(graph_id))
            self.assertIs(task_graph.get_registered_vm(graph_id), fresh_vm)

    def test_rehydrate_runs_discovers_waiting_runs(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "wait_rehydrate_many.nd")
            code = """
workflow demo {
    step gate {
        return workflow_wait("approval.granted", "req-rehydrate-many", {kind: "approval"})
    }

    step finish after gate {
        return "done"
    }
}
"""
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(code)
            with nodus_cli._project_root_context(td):
                result, _vm = run_workflow_code(
                    VM([], {}, code_locs=[], source_path=None),
                    code,
                    filename=path,
                    project_root=td,
                )
            self.assertTrue(result.get("ok"))
            graph_id = result["result"]["graph_id"]
            task_graph._GRAPH_REGISTRY.pop(graph_id, None)
            task_graph._GRAPH_VMS.pop(graph_id, None)

            runner = WorkflowFrameworkRunner(framework_store(td))
            with nodus_cli._project_root_context(td):
                rehydrated = runner.rehydrate_runs(
                    lambda _record: VM([], {}, code_locs=[], source_path=None)
                )
            run_ids = {item["run_id"] for item in rehydrated}
            self.assertIn(graph_id, run_ids)

    def test_rehydrate_skips_dead_lettered_runs(self):
        with tempfile.TemporaryDirectory() as td:
            payload = self._run_demo_workflow(td)
            graph_id = payload["graph_id"]
            runner = WorkflowFrameworkRunner(framework_store(td))
            record = runner.mark_waiting(
                graph_id,
                event_type="approval.granted",
                correlation_key="req-rehydrate-dead",
                payload={"step": "second"},
                deadline_ms=5,
            )
            self.assertIsNotNone(record)
            runner.expire_wait_timeouts(now_ms=(record.wait.registered_at or 0) + 10)
            task_graph._GRAPH_REGISTRY.pop(graph_id, None)
            task_graph._GRAPH_VMS.pop(graph_id, None)

            with nodus_cli._project_root_context(td):
                rehydrated = runner.rehydrate_runs(
                    lambda _record: VM([], {}, code_locs=[], source_path=None)
                )
            self.assertEqual(rehydrated, [])

    def test_workflow_retry_is_persisted_as_retry_scheduled(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "retry_scheduled.nd")
            code = """
let state = { "count": 0 }

workflow demo {
    step flaky with { retries: 2, retry_delay_ms: 50 } {
        if (state["count"] == 0) {
            state["count"] = 1
            throw "fail"
        }
        return 5
    }
}
"""
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(code)
            with nodus_cli._project_root_context(td):
                result, _vm = run_workflow_code(
                    VM([], {}, code_locs=[], source_path=None),
                    code,
                    filename=path,
                    project_root=td,
                )
            self.assertTrue(result.get("ok"))
            payload = result["result"]
            self.assertEqual(payload["status"], "retry_scheduled")
            graph_id = payload["graph_id"]
            runner = WorkflowFrameworkRunner(framework_store(td))
            record = runner.get_run(graph_id)
            self.assertIsNotNone(record)
            self.assertEqual(record.status, RUN_STATUS_RETRY_SCHEDULED)
            retry = record.metadata.get("retry")
            self.assertIsInstance(retry, dict)
            self.assertEqual(retry.get("step"), "flaky")
            self.assertEqual(retry.get("classification"), "retryable")
            self.assertEqual(len(runner.list_due_retry_runs(now_ms=0)), 0)

    def test_retry_resume_rejects_before_next_attempt(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "retry_not_due.nd")
            code = """
let state = { "count": 0 }

workflow demo {
    step flaky with { retries: 2, retry_delay_ms: 50 } {
        if (state["count"] == 0) {
            state["count"] = 1
            throw "fail"
        }
        return 5
    }
}
"""
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(code)
            with nodus_cli._project_root_context(td):
                result, _vm = run_workflow_code(
                    VM([], {}, code_locs=[], source_path=None),
                    code,
                    filename=path,
                    project_root=td,
                )
            self.assertTrue(result.get("ok"))
            graph_id = result["result"]["graph_id"]
            runner = WorkflowFrameworkRunner(framework_store(td))
            record = runner.get_run(graph_id)
            self.assertIsNotNone(record)
            retry = record.metadata.get("retry")
            self.assertIsInstance(retry, dict)
            fresh_vm = VM([], {}, code_locs=[], source_path=None)
            with nodus_cli._project_root_context(td):
                resumed = runner.resume_workflow(
                    fresh_vm,
                    graph_id,
                    now_ms=float(retry["next_attempt_at"]) - 1.0,
                    rebuild_graph=fresh_vm._rebuild_workflow_graph,
                )
            self.assertFalse(resumed.get("ok"))
            self.assertIn("Retry not due", resumed["error"])

    def test_retry_resume_succeeds_when_due_and_exhaustion_is_recorded(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "retry_exhausted.nd")
            code = """
let state = { "count": 0 }

workflow demo {
    step flaky with { retries: 1, retry_delay_ms: 50 } {
        state["count"] = state["count"] + 1
        throw "fail"
    }
}
"""
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(code)
            with nodus_cli._project_root_context(td):
                result, _vm = run_workflow_code(
                    VM([], {}, code_locs=[], source_path=None),
                    code,
                    filename=path,
                    project_root=td,
                )
            self.assertTrue(result.get("ok"))
            graph_id = result["result"]["graph_id"]
            runner = WorkflowFrameworkRunner(framework_store(td))
            record = runner.get_run(graph_id)
            self.assertIsNotNone(record)
            retry = record.metadata.get("retry")
            self.assertIsInstance(retry, dict)
            fresh_vm = VM([], {}, code_locs=[], source_path=None)
            with nodus_cli._project_root_context(td):
                resumed = runner.resume_workflow(
                    fresh_vm,
                    graph_id,
                    now_ms=float(retry["next_attempt_at"]) + 1.0,
                    rebuild_graph=fresh_vm._rebuild_workflow_graph,
                )
            self.assertIsInstance(resumed, dict)
            self.assertTrue(isinstance(resumed.get("failed"), list) and resumed["failed"])
            record = runner.get_run(graph_id)
            self.assertIsNotNone(record)
            self.assertEqual(record.status, RUN_STATUS_FAILED)
            terminal_retry = record.metadata.get("retry")
            self.assertIsInstance(terminal_retry, dict)
            self.assertEqual(terminal_retry.get("classification"), "exhausted")

    def test_sweep_resumes_due_retries_and_rehydrates_waiting_runs(self):
        with tempfile.TemporaryDirectory() as td:
            retry_path = os.path.join(td, "retry_sweep.nd")
            retry_code = """
workflow retry_demo {
    state count = 0

    step flaky with { retries: 2, retry_delay_ms: 5 } {
        if (count == 0) {
            count = 1
            throw "fail"
        }
        return 7
    }
}
"""
            wait_path = os.path.join(td, "wait_sweep.nd")
            wait_code = """
workflow wait_demo {
    step gate {
        return workflow_wait("approval.granted", "req-sweep", {kind: "approval"})
    }

    step finish after gate {
        return "done"
    }
}
"""
            with open(retry_path, "w", encoding="utf-8") as handle:
                handle.write(retry_code)
            with open(wait_path, "w", encoding="utf-8") as handle:
                handle.write(wait_code)
            with nodus_cli._project_root_context(td):
                retry_result, _vm = run_workflow_code(
                    VM([], {}, code_locs=[], source_path=None),
                    retry_code,
                    filename=retry_path,
                    project_root=td,
                )
                wait_result, _vm = run_workflow_code(
                    VM([], {}, code_locs=[], source_path=None),
                    wait_code,
                    filename=wait_path,
                    project_root=td,
                )
            self.assertTrue(retry_result.get("ok"))
            self.assertTrue(wait_result.get("ok"))
            retry_graph_id = retry_result["result"]["graph_id"]
            wait_graph_id = wait_result["result"]["graph_id"]
            task_graph._GRAPH_REGISTRY.pop(wait_graph_id, None)
            task_graph._GRAPH_VMS.pop(wait_graph_id, None)

            runner = WorkflowFrameworkRunner(framework_store(td))
            retry_record = runner.get_run(retry_graph_id)
            self.assertIsNotNone(retry_record)
            retry_meta = retry_record.metadata.get("retry")
            self.assertIsInstance(retry_meta, dict)

            with nodus_cli._project_root_context(td):
                summary = runner.sweep(
                    lambda _record: VM([], {}, code_locs=[], source_path=None),
                    now_ms=float(retry_meta["next_attempt_at"]) + 1.0,
                )
            resumed_ids = {item["run_id"] for item in summary["resumed_retries"]}
            rehydrated_ids = {item["run_id"] for item in summary["rehydrated_runs"]}
            self.assertIn(retry_graph_id, resumed_ids)
            self.assertIn(wait_graph_id, rehydrated_ids)
            retry_record = runner.get_run(retry_graph_id)
            wait_record = runner.get_run(wait_graph_id)
            self.assertEqual(retry_record.status, RUN_STATUS_COMPLETED)
            self.assertEqual(wait_record.status, RUN_STATUS_WAITING)
            self.assertIsNotNone(task_graph.get_registered_graph(wait_graph_id))


if __name__ == "__main__":
    unittest.main()
