from nodus.cli import cli as nodus_cli
from nodus.orchestration import task_graph
from nodus.tooling.runner import resume_workflow, run_workflow_code
from nodus.vm.vm import VM


WORKFLOW_SOURCE = """
workflow sample_workflow {
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


def _run_sample_workflow(tmp_path):
    script = tmp_path / "workflow.nd"
    script.write_text(WORKFLOW_SOURCE)
    with nodus_cli._project_root_context(str(tmp_path)):
        code = script.read_text()
        result, _vm = run_workflow_code(
            VM([], {}, code_locs=[], source_path=None),
            code,
            filename=str(script),
            project_root=str(tmp_path),
        )
    assert result.get("ok") is True
    return result["result"]


def test_workflow_resume_uses_checkpoint(tmp_path):
    payload = _run_sample_workflow(tmp_path)
    graph_id = payload["graph_id"]
    assert payload["steps"]["second"] == 2
    with nodus_cli._project_root_context(str(tmp_path)):
        resumed, _ = resume_workflow(graph_id)
    assert resumed.get("ok") is True
    assert resumed["result"]["steps"]["second"] == 2
    assert resumed["result"]["graph_id"] == graph_id


def test_checkpoint_records_pending_tasks(tmp_path):
    payload = _run_sample_workflow(tmp_path)
    graph_id = payload["graph_id"]
    with nodus_cli._project_root_context(str(tmp_path)):
        checkpoint = task_graph.load_checkpoint(graph_id)
    assert isinstance(checkpoint, dict)
    pending = checkpoint.get("pending") or []
    assert pending
    tasks = checkpoint.get("tasks") or {}
    assert tasks
    assert "task_1" in tasks
    assert "task_2" in pending
    workflow_state = checkpoint.get("workflow_state") or {}
    assert workflow_state.get("value") == 0


def test_workflow_cleanup_removes_snapshots(tmp_path):
    payload = _run_sample_workflow(tmp_path)
    graph_id = payload["graph_id"]
    with nodus_cli._project_root_context(str(tmp_path)):
        assert graph_id in task_graph.list_graph_ids()
    result = nodus_cli._workflow_cleanup(str(tmp_path), retention_seconds=None, force=True)
    assert result == 0
    with nodus_cli._project_root_context(str(tmp_path)):
        assert graph_id not in task_graph.list_graph_ids()
    assert task_graph.load_checkpoint(graph_id) is None
