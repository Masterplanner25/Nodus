from nodus.cli import cli as nodus_cli
from nodus.orchestration import task_graph
from nodus.tooling.runner import resume_workflow, run_workflow_code
from nodus.vm.vm import VM
import json


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


def test_checkpoint_state_separates_public_and_engine_checkpoints(tmp_path):
    payload = _run_sample_workflow(tmp_path)
    graph_id = payload["graph_id"]
    with nodus_cli._project_root_context(str(tmp_path)):
        state = task_graph.load_graph_state(graph_id)
        checkpoint = task_graph.load_checkpoint(graph_id)
    assert isinstance(state, dict)
    public_checkpoints = state.get("checkpoints") or []
    engine_checkpoints = state.get("engine_checkpoints") or []
    assert public_checkpoints
    assert engine_checkpoints
    assert "state" not in public_checkpoints[0]
    assert engine_checkpoints[0]["label"] == public_checkpoints[0]["label"]
    assert "state" in engine_checkpoints[0]
    assert isinstance(checkpoint, dict)
    assert isinstance(checkpoint.get("checkpoints"), list)
    assert isinstance(checkpoint.get("engine_checkpoints"), list)


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


def test_load_graph_state_normalizes_legacy_checkpoint_shape(tmp_path):
    graph_root = tmp_path / ".nodus" / "graphs"
    graph_root.mkdir(parents=True, exist_ok=True)
    graph_id = "g_legacy1234"
    legacy_state = {
        "graph_id": graph_id,
        "status": "completed",
        "tasks": {},
        "metadata": {
            "workflow_name": "legacy_demo",
            "execution_kind": "workflow",
            "checkpoints": [
                {
                    "label": "after-first",
                    "step": "first",
                    "task_id": "task_1",
                    "timestamp": 123.0,
                    "state": {"value": 1},
                }
            ],
        },
        "pending": [],
        "scheduler_queue": [],
        "task_outputs": {},
        "results": {},
        "workflow_state": {"value": 1},
        "updated_at": 123.0,
    }
    checkpoint = {
        "graph_id": graph_id,
        "label": "after-first",
        "timestamp": 123.0,
        "status": "completed",
        "tasks": {},
        "pending": [],
        "scheduler_queue": [],
        "task_outputs": {},
        "results": {},
        "workflow_state": {"value": 1},
        "metadata": {"checkpoints": legacy_state["metadata"]["checkpoints"]},
        "checkpoints": legacy_state["metadata"]["checkpoints"],
    }
    (graph_root / f"{graph_id}.json").write_text(json.dumps(legacy_state), encoding="utf-8")
    (graph_root / f"{graph_id}.checkpoint.json").write_text(json.dumps(checkpoint), encoding="utf-8")
    with nodus_cli._project_root_context(str(tmp_path)):
        state = task_graph.load_graph_state(graph_id)
        loaded_checkpoint = task_graph.load_checkpoint(graph_id)
    assert isinstance(state, dict)
    assert state["checkpoints"][0]["label"] == "after-first"
    assert "state" not in state["checkpoints"][0]
    assert state["engine_checkpoints"][0]["state"] == {"value": 1}
    assert isinstance(loaded_checkpoint, dict)
    assert "state" not in loaded_checkpoint["checkpoints"][0]
    assert loaded_checkpoint["engine_checkpoints"][0]["state"] == {"value": 1}


def test_migrate_graph_snapshot_rewrites_legacy_files(tmp_path):
    graph_root = tmp_path / ".nodus" / "graphs"
    graph_root.mkdir(parents=True, exist_ok=True)
    graph_id = "g_migrate1234"
    legacy_checkpoints = [
        {
            "label": "after-first",
            "step": "first",
            "task_id": "task_1",
            "timestamp": 456.0,
            "state": {"value": 2},
        }
    ]
    legacy_state = {
        "graph_id": graph_id,
        "status": "waiting",
        "tasks": {},
        "metadata": {"checkpoints": legacy_checkpoints},
        "pending": ["task_2"],
        "scheduler_queue": [],
        "task_outputs": {},
        "results": {},
        "workflow_state": {"value": 2},
        "updated_at": 456.0,
    }
    legacy_checkpoint = {
        "graph_id": graph_id,
        "label": "after-first",
        "timestamp": 456.0,
        "status": "waiting",
        "tasks": {},
        "pending": ["task_2"],
        "scheduler_queue": [],
        "task_outputs": {},
        "results": {},
        "workflow_state": {"value": 2},
        "metadata": {"checkpoints": legacy_checkpoints},
        "checkpoints": legacy_checkpoints,
    }
    state_path = graph_root / f"{graph_id}.json"
    checkpoint_path = graph_root / f"{graph_id}.checkpoint.json"
    state_path.write_text(json.dumps(legacy_state), encoding="utf-8")
    checkpoint_path.write_text(json.dumps(legacy_checkpoint), encoding="utf-8")

    with nodus_cli._project_root_context(str(tmp_path)):
        result = task_graph.migrate_graph_snapshot(graph_id)

    assert result["updated"] is True
    assert result["graph_state_updated"] is True
    assert result["checkpoint_updated"] is True

    migrated_state = json.loads(state_path.read_text(encoding="utf-8"))
    migrated_checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    assert "state" not in migrated_state["checkpoints"][0]
    assert migrated_state["engine_checkpoints"][0]["state"] == {"value": 2}
    assert migrated_state["metadata"]["workflow_checkpoints"][0]["label"] == "after-first"
    assert "state" not in migrated_checkpoint["checkpoints"][0]
    assert migrated_checkpoint["engine_checkpoints"][0]["state"] == {"value": 2}


def test_migrate_all_graph_snapshots_updates_only_legacy_files(tmp_path):
    graph_root = tmp_path / ".nodus" / "graphs"
    graph_root.mkdir(parents=True, exist_ok=True)

    legacy_graph_id = "g_bulk_legacy"
    normalized_graph_id = "g_bulk_normalized"

    legacy_state = {
        "graph_id": legacy_graph_id,
        "status": "completed",
        "tasks": {},
        "metadata": {
            "checkpoints": [
                {
                    "label": "legacy",
                    "step": "first",
                    "task_id": "task_1",
                    "timestamp": 100.0,
                    "state": {"value": 1},
                }
            ]
        },
        "pending": [],
        "scheduler_queue": [],
        "task_outputs": {},
        "results": {},
        "workflow_state": {"value": 1},
        "updated_at": 100.0,
    }
    normalized_state = {
        "graph_id": normalized_graph_id,
        "status": "completed",
        "tasks": {},
        "metadata": {
            "workflow_checkpoints": [
                {
                    "label": "current",
                    "step": "first",
                    "task_id": "task_1",
                    "timestamp": 200.0,
                }
            ],
            "engine_checkpoints": [
                {
                    "label": "current",
                    "step": "first",
                    "task_id": "task_1",
                    "timestamp": 200.0,
                    "state": {"value": 2},
                }
            ],
            "checkpoints": [
                {
                    "label": "current",
                    "step": "first",
                    "task_id": "task_1",
                    "timestamp": 200.0,
                }
            ],
        },
        "pending": [],
        "scheduler_queue": [],
        "task_outputs": {},
        "results": {},
        "workflow_state": {"value": 2},
        "checkpoints": [
            {
                "label": "current",
                "step": "first",
                "task_id": "task_1",
                "timestamp": 200.0,
            }
        ],
        "engine_checkpoints": [
            {
                "label": "current",
                "step": "first",
                "task_id": "task_1",
                "timestamp": 200.0,
                "state": {"value": 2},
            }
        ],
        "updated_at": 200.0,
    }

    (graph_root / f"{legacy_graph_id}.json").write_text(json.dumps(legacy_state), encoding="utf-8")
    (graph_root / f"{normalized_graph_id}.json").write_text(json.dumps(normalized_state), encoding="utf-8")

    with nodus_cli._project_root_context(str(tmp_path)):
        results = task_graph.migrate_all_graph_snapshots()

    by_id = {entry["graph_id"]: entry for entry in results}
    assert by_id[legacy_graph_id]["updated"] is True
    assert by_id[normalized_graph_id]["updated"] is False
