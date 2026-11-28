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


_REPO_SQLITE_STORE = ROOT / ".nodus" / "workflow_framework.sqlite3"


def _sqlite_run_ids() -> set[str] | None:
    """Run ids in the repo's default SQLite store, or None if it does not exist."""
    import sqlite3

    if not _REPO_SQLITE_STORE.is_file():
        return None
    try:
        conn = sqlite3.connect(str(_REPO_SQLITE_STORE), timeout=5.0)
        try:
            return {row[0] for row in conn.execute("SELECT run_id FROM workflow_runs")}
        finally:
            conn.close()
    except sqlite3.Error:
        return None


def _delete_sqlite_runs_added_since(before: set[str] | None) -> None:
    import sqlite3

    if not _REPO_SQLITE_STORE.is_file():
        return
    if before is None:
        # The session created the file; nothing in it predates the session.
        before = set()
    try:
        conn = sqlite3.connect(str(_REPO_SQLITE_STORE), timeout=5.0)
        try:
            added = [row[0] for row in conn.execute("SELECT run_id FROM workflow_runs")
                     if row[0] not in before]
            conn.executemany("DELETE FROM workflow_runs WHERE run_id = ?",
                             [(run_id,) for run_id in added])
            conn.commit()
        finally:
            conn.close()
    except sqlite3.Error:
        pass


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

    Since 6.0.0 the default store is SQLite (#797), one file beside the JSON
    store's root, so a run is a row rather than a file. The same rule applies
    to rows: those present before the session stay.
    """
    before = _state_files()
    rows_before = _sqlite_run_ids()
    yield
    _delete_sqlite_runs_added_since(rows_before)
    for directory in _REPO_STATE_DIRS:
        if not directory.is_dir():
            continue
        for path in directory.iterdir():
            if (str(directory), path.name) not in before:
                try:
                    path.unlink()
                except OSError:
                    pass
