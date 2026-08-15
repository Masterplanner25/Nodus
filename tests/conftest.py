import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

for path in (ROOT, SRC):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)


_REPO_RUNS = ROOT / ".nodus" / "workflow_framework" / "runs"


def _run_files() -> set[str]:
    return {p.name for p in _REPO_RUNS.iterdir()} if _REPO_RUNS.is_dir() else set()


@pytest.fixture(scope="session", autouse=True)
def _leave_no_workflow_runs_behind():
    """Delete workflow-run files this session created in the repo (#380).

    The default workflow store root is CWD-relative, so a suite run from the repo
    root writes into the repo's own `.nodus/workflow_framework/runs/`. A full run
    leaves ~41 files, retention is 30 days, and `LocalWorkflowStore.list_runs()`
    parses every file on every call — about 1.3 ms each. Left alone the directory
    reached 299 files, where a single scan costs 540 ms, past the 500 ms sweep
    interval deadline-sensitive tests assume. The suite was slowly breaking its
    own later runs, surfacing as unrelated-looking flakes that passed on re-run.

    Cleaning up afterwards rather than redirecting the store during the run:
    several tests build a project directory, chdir into it and then assert that
    the default runner wrote under *that* root, so pointing the default
    elsewhere breaks them (26 failures when tried). Their behaviour is the
    documented one — the defect is only that the files outlive the session.

    Files present before the session are left alone; this removes what the
    session added, nothing else.
    """
    before = _run_files()
    yield
    if not _REPO_RUNS.is_dir():
        return
    for path in _REPO_RUNS.iterdir():
        if path.name not in before:
            try:
                path.unlink()
            except OSError:
                pass
