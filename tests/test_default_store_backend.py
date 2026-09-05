"""The default workflow runner honours the store-backend environment (#174).

`get_default_workflow_runner()` hardcoded `LocalWorkflowStore`, the file-backed
JSON store that is explicitly not crash-safe. `nodus serve` had honoured
`NODUS_WORKFLOW_STORE_BACKEND` for a long time, so the same question — *which
store backs this run?* — had two answers, and the half every embedder reaches by
calling `run_workflow()` was the one that could not be configured at all short of
`configure_default_workflow_runner()`.

Both halves read the same two variables now, through one pair of readers in
`store.py`.

**The default is deliberately unchanged.** Flipping it to SQLite is a 6.0.0
change, and not merely because the file location moves: runs already recorded in
the JSON store are invisible to a SQLite one, so an in-flight `waiting` run would
silently become unresumable. `test_the_default_backend_is_still_local` is what
fails if that is flipped.

**The blocker that deferred it is now gone, and this paragraph used to say
otherwise.** It read *"`nodus workflow migrate-state` migrates graph snapshots,
not store backends, so there is no migration path to offer yet."* True when
written; `nodus workflow migrate-store --to sqlite` now copies run records
between backends. Verified end to end rather than assumed: a run parked
`waiting` in the local store arrives in SQLite still `waiting` with its
`wait.event_type` intact, the local copy is left in place, and `--dry-run`
reports the plan without writing.

So what remains is the breaking-change gate, not a missing tool — and the flip
is staged the way this repo stages #545, #547 and #609: warn now, change at the
major. `TheTransitionalWarningTests` below pins that warning, including the
cases where it must stay quiet.
"""
import os
import sys
import tempfile
import unittest
import warnings

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus_lang_workflow.runner import (  # noqa: E402
    get_default_workflow_runner,
    reset_default_store_warning,
    reset_default_workflow_runner,
)
from nodus_lang_workflow.store import (  # noqa: E402
    WORKFLOW_STORE_BACKEND_ENV,
    WORKFLOW_STORE_PATH_ENV,
)

_ENV_KEYS = (WORKFLOW_STORE_BACKEND_ENV, WORKFLOW_STORE_PATH_ENV)


class DefaultStoreBackendTests(unittest.TestCase):
    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in _ENV_KEYS}
        self._cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory()
        os.chdir(self._tmp.name)
        reset_default_workflow_runner()

    def tearDown(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        reset_default_workflow_runner()
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def _store(self):
        reset_default_workflow_runner()
        return get_default_workflow_runner().store

    def test_the_default_backend_is_still_local(self):
        """Unset environment must not change what an existing embedder gets.

        Fails if the default is flipped to SQLite. Read the module docstring
        before changing it: the blocker is that JSON-recorded runs are invisible
        to a SQLite store, not that the path moves.
        """
        for key in _ENV_KEYS:
            os.environ.pop(key, None)
        self.assertEqual(type(self._store()).__name__, "LocalWorkflowStore")

    def test_sqlite_can_be_selected_by_environment(self):
        os.environ[WORKFLOW_STORE_BACKEND_ENV] = "sqlite"
        store = self._store()
        self.assertEqual(type(store).__name__, "SQLiteWorkflowStore")
        self.assertEqual(store.store_info().get("backend"), "sqlite")

    def test_an_explicit_local_is_honoured(self):
        os.environ[WORKFLOW_STORE_BACKEND_ENV] = "local"
        self.assertEqual(type(self._store()).__name__, "LocalWorkflowStore")

    def test_the_store_path_is_honoured(self):
        target = os.path.join(self._tmp.name, "custom", "runs.db")
        os.environ[WORKFLOW_STORE_BACKEND_ENV] = "sqlite"
        os.environ[WORKFLOW_STORE_PATH_ENV] = target
        self.assertEqual(self._store().store_info().get("path"), os.path.abspath(target))

    def test_an_unknown_backend_is_refused(self):
        """A misspelling must not silently fall back to the non-durable store.

        Falling back would be the declared-but-not-enforced shape: the operator
        asked for durability and would get JSON files with no signal.
        """
        os.environ[WORKFLOW_STORE_BACKEND_ENV] = "postgres"
        with self.assertRaises(ValueError) as caught:
            self._store()
        self.assertIn("postgres", str(caught.exception))

    # closes: #174
    def test_a_run_is_recorded_in_the_selected_backend(self):
        """End to end: selecting sqlite actually records the run there.

        A store-type assertion alone would pass on a runner that built the right
        object and then wrote somewhere else.
        """
        from nodus.runtime.embedding import NodusRuntime

        os.environ[WORKFLOW_STORE_BACKEND_ENV] = "sqlite"
        reset_default_workflow_runner()
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
        # and nothing landed in the JSON store it replaced
        json_runs = os.path.join(
            self._tmp.name, ".nodus", "workflow_framework", "runs"
        )
        self.assertFalse(
            os.path.isdir(json_runs) and os.listdir(json_runs),
            "run records leaked into the local store while sqlite was selected",
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



class TheTransitionalWarningTests(unittest.TestCase):
    """The "warn now, flip at the major" half of #174.

    Deliberately narrow, and the quiet cases are the ones worth pinning: a
    warning everybody sees is a warning everybody filters. It fires only when a
    host has state that the 6.0.0 flip would not carry — an *unconfigured*
    local store that already holds runs. Choosing `local` explicitly is an
    answer, not an oversight, and silences it.
    """

    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in _ENV_KEYS}
        self._cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory()
        os.chdir(self._tmp.name)
        for key in _ENV_KEYS:
            os.environ.pop(key, None)
        reset_default_workflow_runner()
        reset_default_store_warning()

    def tearDown(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        reset_default_workflow_runner()
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def _record_a_run(self):
        """Put one run in the default (local) store."""
        runner = get_default_workflow_runner()
        runner.store.create_run(
            run_id="g_probe", graph_id="g_probe",
            workflow_name="probe", execution_kind="workflow",
        )
        reset_default_workflow_runner()
        reset_default_store_warning()

    def _warnings_from_building_the_runner(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            get_default_workflow_runner()
        return [w for w in caught if issubclass(w.category, DeprecationWarning)]

    # closes: #174
    def test_it_warns_when_an_unconfigured_local_store_holds_runs(self):
        self._record_a_run()
        found = self._warnings_from_building_the_runner()
        self.assertEqual(1, len(found), [str(w.message) for w in found])
        message = str(found[0].message)
        self.assertIn("migrate-store", message, "a warning must say what to type")
        self.assertIn("6.0.0", message)

    # closes: #174
    def test_it_is_quiet_when_the_store_is_empty(self):
        """A short script that has never run a workflow has nothing to lose, and
        the local store is genuinely right for it."""
        self.assertEqual([], self._warnings_from_building_the_runner())

    # closes: #174
    def test_choosing_local_explicitly_silences_it(self):
        """`NODUS_WORKFLOW_STORE_BACKEND=local` is a host saying it means this."""
        self._record_a_run()
        os.environ[WORKFLOW_STORE_BACKEND_ENV] = "local"
        self.assertEqual([], self._warnings_from_building_the_runner())

    # closes: #174
    def test_choosing_sqlite_silences_it(self):
        self._record_a_run()
        os.environ[WORKFLOW_STORE_BACKEND_ENV] = "sqlite"
        self.assertEqual([], self._warnings_from_building_the_runner())

    # closes: #174
    def test_it_fires_once_per_process(self):
        """Repeated on every `run_workflow()` it would be noise, and the runner
        is rebuilt whenever the working directory changes."""
        self._record_a_run()
        self.assertEqual(1, len(self._warnings_from_building_the_runner()))
        reset_default_workflow_runner()
        self.assertEqual([], self._warnings_from_building_the_runner())

if __name__ == "__main__":
    unittest.main()
