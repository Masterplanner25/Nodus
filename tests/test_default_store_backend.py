"""Which workflow store backs a run when nothing chose one (#174, #797).

**The default is SQLite since 6.0.0.** Through 5.x it was `LocalWorkflowStore`,
the file-backed JSON store whose claims are exclusive only within one process
(#937; it is crash-safe, writing each record atomically).

The flip was staged for a long time for one reason: runs recorded in the JSON
store are invisible to a SQLite one, so switching silently would make an
in-flight `waiting` run stop existing. So it landed as a **refusal**: with no
backend configured, a JSON store holding runs SQLite lacks raises
`StrandedRunsError`, naming them and the command that copies them
(`nodus workflow migrate-store --to sqlite`). Choosing a backend is an answer:
`local` keeps the JSON store, and an explicit `sqlite` is warned rather than
stopped.

Both `nodus serve` and the default runner read the backend from the same two
variables, through one pair of readers in `store.py`.
"""
import io
import os
import subprocess
import sys
import tempfile
import unittest
import warnings
from contextlib import redirect_stderr
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus_lang_workflow.runner import (  # noqa: E402
    WorkflowFrameworkRunner,
    get_default_workflow_runner,
    reset_default_workflow_runner,
    reset_stranded_runs_warning,
)
from nodus_lang_workflow.store import (  # noqa: E402
    DEFAULT_WORKFLOW_STORE_BACKEND,
    WORKFLOW_STORE_BACKEND_ENV,
    WORKFLOW_STORE_PATH_ENV,
    LocalWorkflowStore,
    StrandedRunsError,
    create_workflow_store,
)

REPO = Path(__file__).resolve().parents[1]
_ENV_KEYS = (
    WORKFLOW_STORE_BACKEND_ENV,
    WORKFLOW_STORE_PATH_ENV,
    "NODUS_WORKFLOW_STORE_ROOT",
    "NODUS_RUN_STATE_ROOT",
)


class _Isolated(unittest.TestCase):
    """A temporary working directory and a clean store environment."""

    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in _ENV_KEYS}
        for key in _ENV_KEYS:
            os.environ.pop(key, None)
        self._cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        os.chdir(self._tmp.name)
        reset_default_workflow_runner()
        reset_stranded_runs_warning()

    def tearDown(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        reset_default_workflow_runner()
        reset_stranded_runs_warning()
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def _store(self):
        reset_default_workflow_runner()
        return get_default_workflow_runner().store

    def _json_root(self) -> str:
        return os.path.join(self._tmp.name, ".nodus", "workflow_framework")

    def _record_a_json_run(self, run_id: str = "g_probe") -> None:
        """Put one run in the JSON store, the way a 5.x project has them."""
        LocalWorkflowStore(root=self._json_root()).create_run(
            run_id=run_id, graph_id=run_id,
            workflow_name="probe", execution_kind="workflow",
        )


class DefaultStoreBackendTests(_Isolated):
    # closes: #797
    def test_the_default_backend_is_sqlite(self):
        self.assertEqual(DEFAULT_WORKFLOW_STORE_BACKEND, "sqlite")
        store = self._store()
        self.assertEqual(type(store).__name__, "SQLiteWorkflowStore")

    def test_the_default_sqlite_file_sits_beside_the_json_root(self):
        """Where the default SQLite file always was, so a host that already
        chose `sqlite` and the default now agree on one database."""
        expected = os.path.abspath(self._json_root()) + ".sqlite3"
        self.assertEqual(self._store().store_info().get("path"), expected)
        os.environ[WORKFLOW_STORE_BACKEND_ENV] = "sqlite"
        self.assertEqual(self._store().store_info().get("path"), expected)

    def test_a_relocated_json_root_moves_the_default_sqlite_file(self):
        """`NODUS_WORKFLOW_STORE_ROOT` relocated the default store in 5.x. With
        the default now SQLite, ignoring it would put the database in the
        working directory while the host believes it moved."""
        moved = os.path.join(self._tmp.name, "elsewhere", "runs")
        os.environ["NODUS_WORKFLOW_STORE_ROOT"] = moved
        self.assertEqual(
            self._store().store_info().get("path"), os.path.abspath(moved) + ".sqlite3"
        )

    def test_an_explicit_root_argument_moves_it_too(self):
        moved = os.path.join(self._tmp.name, "explicit")
        store = create_workflow_store(root=moved)
        self.assertEqual(store.store_info().get("path"), os.path.abspath(moved) + ".sqlite3")

    def test_a_runner_built_with_no_store_gets_the_default(self):
        """`WorkflowFrameworkRunner()` built a `LocalWorkflowStore` of its own,
        a second answer to "what is the default store"."""
        self.assertEqual(type(WorkflowFrameworkRunner().store).__name__, "SQLiteWorkflowStore")

    def test_an_explicit_local_is_honoured(self):
        os.environ[WORKFLOW_STORE_BACKEND_ENV] = "local"
        self.assertEqual(type(self._store()).__name__, "LocalWorkflowStore")

    def test_the_store_path_is_honoured(self):
        target = os.path.join(self._tmp.name, "custom", "runs.db")
        os.environ[WORKFLOW_STORE_BACKEND_ENV] = "sqlite"
        os.environ[WORKFLOW_STORE_PATH_ENV] = target
        self.assertEqual(self._store().store_info().get("path"), os.path.abspath(target))

    def test_the_store_path_is_honoured_with_no_backend_set(self):
        target = os.path.join(self._tmp.name, "custom", "default.db")
        os.environ[WORKFLOW_STORE_PATH_ENV] = target
        self.assertEqual(self._store().store_info().get("path"), os.path.abspath(target))

    def test_an_unknown_backend_is_refused(self):
        """A misspelling must not silently fall back to the default store."""
        os.environ[WORKFLOW_STORE_BACKEND_ENV] = "postgres"
        with self.assertRaises(ValueError) as caught:
            self._store()
        self.assertIn("postgres", str(caught.exception))

    # closes: #174
    def test_a_run_is_recorded_in_the_default_backend(self):
        """End to end: the run lands in SQLite, and nothing in the JSON store.

        A store-type assertion alone would pass on a runner that built the right
        object and then wrote somewhere else.
        """
        from nodus.runtime.embedding import NodusRuntime

        result = NodusRuntime(timeout_ms=None).run_source(
            "workflow saga {\n"
            '    step a { checkpoint "cp"; return "A" }\n'
            '    step b after a { throw "boom" }\n'
            "}\n"
            "fn main() { let r = run_workflow(saga); print(\"F=\\(r[\"failed\"])\") }\n"
        )
        self.assertTrue(result["ok"], result.get("error"))
        self.assertIn('F=["b"]', result.get("stdout") or "")

        store = get_default_workflow_runner().store
        self.assertEqual(type(store).__name__, "SQLiteWorkflowStore")
        self.assertEqual(len(store.list_runs()), 1)
        json_runs = os.path.join(self._json_root(), "runs")
        self.assertFalse(
            os.path.isdir(json_runs) and os.listdir(json_runs),
            "run records leaked into the JSON store while SQLite was the default",
        )

    def test_the_environment_is_read_in_one_place(self):
        """Source assertion: the CLI and the default runner share the readers.

        Two independent `os.environ.get("NODUS_WORKFLOW_STORE_BACKEND")` calls is
        exactly how `nodus serve` came to honour a setting the embedded runner
        ignored. A behavioural test cannot catch a second reader being added, so
        this reads the source.
        """
        import inspect

        from nodus.cli import cli

        cli_src = inspect.getsource(cli)
        self.assertNotIn(
            'os.environ.get("NODUS_WORKFLOW_STORE_BACKEND")',
            cli_src,
            "cli.py must delegate to store.workflow_store_backend_from_env()",
        )
        self.assertNotIn('os.environ.get("NODUS_WORKFLOW_STORE_PATH")', cli_src)

    # closes: #937
    def test_the_json_store_writes_records_atomically(self):
        """The JSON store is crash-safe: every record write goes through
        `_atomic_write_json`, which fsyncs a temp file and renames it over the
        record. What it lacks is a claim another process can see. A new write
        path that bypassed the temp file would make "not crash-safe" true, and
        this is what would notice."""
        import inspect
        import re

        from nodus_lang_workflow import store as store_module

        source = inspect.getsource(store_module.LocalWorkflowStore)
        writer = inspect.getsource(store_module.LocalWorkflowStore._atomic_write_json)
        self.assertIn("os.fsync", writer)
        self.assertIn("_replace_with_retry", writer)
        writes = re.findall(
            r"open\(\s*([\w.]+)\s*,\s*[\"'](?:w|a|x|r\+)[bt+]*[\"']", source)
        self.assertEqual(["tmp_path"], writes)
        self.assertNotIn("write_text(", source)
        self.assertNotIn("write_bytes(", source)


class StrandedRunsRefusalTests(_Isolated):
    """The flip lands as a refusal, not a silent switch (#797)."""

    # closes: #797
    def test_unconfigured_with_json_runs_is_refused_naming_them(self):
        self._record_a_json_run("g_parked")
        with self.assertRaises(StrandedRunsError) as caught:
            self._store()
        message = str(caught.exception)
        self.assertIn("g_parked", message)
        self.assertIn("migrate-store --to sqlite", message)
        self.assertIn("NODUS_WORKFLOW_STORE_BACKEND=local", message)
        self.assertEqual(caught.exception.run_ids, ["g_parked"])

    def test_it_is_quiet_when_the_json_store_is_empty(self):
        """A project with no state has nothing to lose: no refusal, no notice."""
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            self._store()
        self.assertEqual([], [str(w.message) for w in caught])

    def test_choosing_local_keeps_the_json_store(self):
        self._record_a_json_run()
        os.environ[WORKFLOW_STORE_BACKEND_ENV] = "local"
        store = self._store()
        self.assertEqual(type(store).__name__, "LocalWorkflowStore")
        self.assertEqual([r.run_id for r in store.list_runs()], ["g_probe"])

    def test_choosing_sqlite_warns_instead_of_refusing(self):
        """A host that set the backend itself chose the switch; it is told
        which runs it left behind, as in 5.x, and not stopped."""
        self._record_a_json_run()
        os.environ[WORKFLOW_STORE_BACKEND_ENV] = "sqlite"
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            store = self._store()
        self.assertEqual(type(store).__name__, "SQLiteWorkflowStore")
        messages = [str(w.message) for w in caught]
        self.assertTrue(
            [m for m in messages if "not in the SQLite store" in m and "g_probe" in m],
            messages,
        )
        self.assertFalse([m for m in messages if "6.0.0" in m], messages)

    def test_a_migrated_run_is_not_stranded(self):
        """The migration copies and leaves the JSON store intact, so a JSON
        store that still has records is the expected state afterwards."""
        from nodus_lang_workflow.store import migrate_workflow_store

        self._record_a_json_run()
        source = LocalWorkflowStore(root=self._json_root())
        target = create_workflow_store(root=self._json_root(), refuse_stranded=False)
        report = migrate_workflow_store(source, target)
        self.assertEqual(report["migrated_count"], 1)
        store = self._store()
        self.assertEqual([r.run_id for r in store.list_runs()], ["g_probe"])
        self.assertTrue(os.listdir(os.path.join(self._json_root(), "runs")))

    def test_the_refusal_is_in_the_factory_every_path_shares(self):
        """Source assertion, paired with the behavioural tests above: the
        default runner, `configure_default_workflow_runner` and a bare
        `WorkflowFrameworkRunner()` all build through `create_workflow_store`,
        so none of them can switch silently."""
        import inspect

        from nodus_lang_workflow import runner as runner_module

        source = inspect.getsource(runner_module)
        self.assertNotIn("LocalWorkflowStore(", source)
        self.assertIn("store or create_workflow_store()", source)
        self._record_a_json_run()
        with self.assertRaises(StrandedRunsError):
            WorkflowFrameworkRunner()
        with self.assertRaises(StrandedRunsError):
            runner_module.configure_default_workflow_runner(root=self._json_root())


class CliTests(_Isolated):
    """The refusal and its remedy, as an operator meets them."""

    def _nodus(self, *args: str) -> subprocess.CompletedProcess:
        env = dict(os.environ)
        env["PYTHONPATH"] = str(REPO / "src")
        return subprocess.run(
            [sys.executable, "-m", "nodus", *args],
            cwd=self._tmp.name, capture_output=True, text=True, env=env, timeout=120,
        )

    # closes: #797
    def test_a_command_is_refused_then_migrate_store_clears_it(self):
        self._record_a_json_run("g_parked")

        refused = self._nodus("workflow", "runs")
        self.assertEqual(refused.returncode, 1, refused.stdout)
        self.assertIn("Error: the default workflow store is SQLite", refused.stderr)
        self.assertIn("g_parked", refused.stderr)
        self.assertNotIn("Traceback", refused.stderr)

        dry = self._nodus("workflow", "migrate-store", "--to", "sqlite", "--dry-run")
        self.assertEqual(dry.returncode, 0, dry.stderr)
        self.assertIn('"migrated_count": 1', dry.stdout)
        self.assertEqual(self._nodus("workflow", "runs").returncode, 1)

        moved = self._nodus("workflow", "migrate-store", "--to", "sqlite")
        self.assertEqual(moved.returncode, 0, moved.stderr)
        self.assertIn('"backend": "local"', moved.stdout)

        listed = self._nodus("workflow", "runs")
        self.assertEqual(listed.returncode, 0, listed.stderr)
        self.assertIn("g_parked", listed.stdout)

    def test_the_migration_targets_the_store_the_runtime_will_open(self):
        moved = os.path.join(self._tmp.name, "moved")
        os.environ["NODUS_WORKFLOW_STORE_ROOT"] = moved
        LocalWorkflowStore(root=moved).create_run(
            run_id="g_moved", graph_id="g_moved",
            workflow_name="probe", execution_kind="workflow",
        )
        done = self._nodus("workflow", "migrate-store", "--to", "sqlite")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("moved.sqlite3", done.stdout.replace("\\\\", "/"))
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            store = self._store()
        self.assertEqual([r.run_id for r in store.list_runs()], ["g_moved"])


if __name__ == "__main__":
    unittest.main()
