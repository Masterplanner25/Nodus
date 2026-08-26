import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

for path in (ROOT, SRC):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)


# #585: a run is two directories, and this fixture used to know about one.
# Redirecting the store for the session is not an option here -- several tests
# chdir into a project directory and assert the default runner wrote under *that*
# root, which is the documented behaviour (26 failures when it was tried). So the
# suite still cleans up after itself; it just does it for both halves now, off one
# list, rather than growing a second hand-maintained sweep.
_REPO_STATE_DIRS = (
    ROOT / ".nodus" / "workflow_framework" / "runs",
    ROOT / ".nodus" / "graphs",
)


def _state_files() -> set[tuple[str, str]]:
    present: set[tuple[str, str]] = set()
    for directory in _REPO_STATE_DIRS:
        if directory.is_dir():
            present.update((str(directory), entry.name) for entry in directory.iterdir())
    return present


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
    before = _state_files()
    yield
    for directory in _REPO_STATE_DIRS:
        if not directory.is_dir():
            continue
        for path in directory.iterdir():
            if (str(directory), path.name) not in before:
                try:
                    path.unlink()
                except OSError:
                    pass
