"""Closed-issue test for #891: run-state paths are built from a validated id.

A run/graph/snapshot id names a `<id>.json`/`.pkl` file under a run-state root,
and several of these ids arrive from a caller the runtime did not author — a
guest `resume_workflow(id)`, an HTTP `snapshot`/`graph_id`. An unvalidated id
with `..` or a separator escaped the state directory.

The fix is the shape CLAUDE.md prescribes for this recurring bug: one decision
(`safe_state_id`) at the path-construction boundary, with every id-to-path
builder driven off it, rather than a check bolted onto each of the four sites.
So the first test names that set and asserts each member refuses a traversing id
— a new path builder that forgets the validator fails here.

Security-boundary rule (TECH_DEBT § Testing Methodology): the guest-reachable
path (`resume_workflow`) is covered through `NodusRuntime` (embedded) and through
the function both the CLI and the embedder funnel into (`load_graph_state`).
"""
import sys
from pathlib import Path

import pytest

# closes: #891

_REPO_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(_REPO_ROOT / "src"))  # noqa: E402

from nodus.orchestration import task_graph  # noqa: E402
from nodus.runtime.snapshots import SnapshotManager  # noqa: E402
from nodus.runtime.state_paths import InvalidStateId, safe_state_id  # noqa: E402

_TRAVERSALS = [
    "../x", "..\\x", "a/b", "a\\b", "/etc/passwd", "C:/x", "../../outside",
    "g_abc/../../x", ".", "..", "", "x" * 129, "a\x00b", "a.b", "a b",
]
_REAL_IDS = ["g_1eeee049", "snap_12ab34cd", "run_0", "task_3", "a", "A-b_C9", "x" * 128]


# --- the validator itself ---------------------------------------------------

@pytest.mark.parametrize("bad", _TRAVERSALS)
def test_safe_state_id_refuses_anything_that_is_not_an_id(bad):
    with pytest.raises(InvalidStateId):
        safe_state_id(bad)


@pytest.mark.parametrize("good", _REAL_IDS)
def test_safe_state_id_accepts_real_ids(good):
    assert safe_state_id(good) == good


# --- every path builder is driven off it (name the set once) ----------------

def _run_path_builder(run_id):
    from nodus_lang_workflow.store import LocalWorkflowStore
    return LocalWorkflowStore()._run_path(run_id)

_PATH_BUILDERS = [
    task_graph._graph_state_path,
    task_graph._checkpoint_path,
    lambda sid: SnapshotManager()._path(sid),
    _run_path_builder,
]


@pytest.mark.parametrize("build", _PATH_BUILDERS)
def test_every_run_state_path_builder_validates(build, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(InvalidStateId):
        build("../../outside")
    # and still works for a real id
    assert isinstance(build("g_0123abcd"), str)


# --- read/delete entry points treat a bad id as "not found", not an error ---

def test_load_graph_state_returns_none_and_touches_nothing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    sentinel = tmp_path / "outside.json"
    sentinel.write_text('{"metadata": {"workflow_name": "x"}}', encoding="utf-8")

    assert task_graph.load_graph_state("../outside") is None
    assert task_graph.load_checkpoint("../outside") is None
    task_graph.delete_graph_state("../outside")
    task_graph.delete_checkpoint("../outside")

    assert sentinel.exists(), "a traversing id must not delete a file outside the state dir"


def test_snapshot_get_and_delete_refuse_traversal(tmp_path):
    snap_dir = tmp_path / "snaps"
    outside = tmp_path / "outside.pkl"
    outside.write_bytes(b"not a real snapshot")
    manager = SnapshotManager(snapshot_dir=str(snap_dir), max_snapshots=10)

    assert manager.get("../outside") is None
    assert manager.delete("../outside") is False
    assert outside.exists(), "a traversing id must not delete a .pkl outside the snapshot dir"


def test_workflow_store_get_and_delete_refuse_traversal(tmp_path, monkeypatch):
    from nodus_lang_workflow.store import LocalWorkflowStore

    monkeypatch.chdir(tmp_path)
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    store = LocalWorkflowStore()

    assert store.get_run("../outside") is None
    assert store.delete_run("../outside") is False
    assert outside.exists()


# --- the guest-reachable path, end to end (embedded mode) -------------------

def test_guest_resume_with_a_traversing_id_is_a_clean_miss(tmp_path, monkeypatch):
    """`resume_workflow("../x")` from guest code must not read outside the dir."""
    from nodus.runtime.embedding import NodusRuntime

    monkeypatch.chdir(tmp_path)
    sentinel = tmp_path / "outside.json"
    sentinel.write_text('{"metadata": {"workflow_name": "research"}}', encoding="utf-8")

    src = (
        'let r = resume_workflow("../outside")\n'
        'if (type(r) == "error") { print("miss") } else { print("miss-\\(r["ok"])") }'
    )
    result = NodusRuntime().run_source(src, timeout_ms=10_000)

    assert result["ok"], result.get("error")
    # A clean miss (unknown run), not a value read out of the outside file.
    assert result["stdout"].strip() in {"miss", "miss-false"}, result["stdout"]
    assert sentinel.exists()
