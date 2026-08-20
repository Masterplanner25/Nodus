"""The SQLite workflow store closes its cursors instead of relying on refcounting.

`conn.execute(...)` returns a cursor. Left unreferenced, CPython's refcounting
frees it at once and the statement is finalised; a runtime without refcounting
keeps it alive until the next GC, and the statement is still open when the
enclosing block commits:

    sqlite3.OperationalError: cannot commit transaction - SQL statements in progress

So the store depended on *when CPython happens to free an object* for correctness
(#516). That is a latent defect on CPython too, and it made nine tests fail under
PyPy -- every one of them from this single cause.

Testing it on CPython is the awkward part, because CPython is precisely the
runtime where forgetting to close is invisible. These tests therefore assert on
the mechanism rather than waiting for a symptom that only appears elsewhere.
"""
import gc
import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus_lang_workflow.store import (  # noqa: E402
    SQLiteWorkflowStore,
    _exec,
    _fetchall,
    _fetchone,
)


class TheHelpersCloseWhatTheyOpenTests(unittest.TestCase):
    """Direct: hand each helper a connection that records its cursors."""

    def setUp(self):
        self.opened = []
        outer = self

        class RecordingCursor(sqlite3.Cursor):
            def close(self):
                outer.opened.append(("closed", id(self)))
                super().close()

        class RecordingConnection(sqlite3.Connection):
            def cursor(self, factory=RecordingCursor):
                cur = super().cursor(RecordingCursor)
                outer.opened.append(("opened", id(cur)))
                return cur

        self.conn = sqlite3.connect(":memory:", factory=RecordingConnection)
        self.conn.execute("CREATE TABLE t (a INTEGER)")
        self.opened.clear()

    def tearDown(self):
        self.conn.close()

    def _balanced(self) -> bool:
        opened = {i for kind, i in self.opened if kind == "opened"}
        closed = {i for kind, i in self.opened if kind == "closed"}
        return opened == closed and bool(opened)

    def test_exec_closes(self):
        _exec(self.conn, "INSERT INTO t (a) VALUES (?)", (1,))
        self.assertTrue(self._balanced(), self.opened)

    def test_fetchone_closes(self):
        _exec(self.conn, "INSERT INTO t (a) VALUES (?)", (2,))
        self.opened.clear()
        row = _fetchone(self.conn, "SELECT a FROM t")
        self.assertEqual(2, row[0])
        self.assertTrue(self._balanced(), self.opened)

    def test_fetchall_closes(self):
        _exec(self.conn, "INSERT INTO t (a) VALUES (?)", (3,))
        self.opened.clear()
        rows = _fetchall(self.conn, "SELECT a FROM t")
        self.assertEqual(1, len(rows))
        self.assertTrue(self._balanced(), self.opened)

    def test_fetchone_closes_even_when_the_query_raises(self):
        with self.assertRaises(sqlite3.OperationalError):
            _fetchone(self.conn, "SELECT a FROM no_such_table")
        # The cursor was opened before the statement failed; it must still close.
        self.assertTrue(self._balanced(), self.opened)


class NoCallSiteBypassesThemTests(unittest.TestCase):
    """Assert on the source.

    The helpers are only worth having if nothing goes around them, and a
    behaviour test cannot show that on CPython -- an unclosed cursor there is
    invisible. Twelve call sites each remembering to close is twelve chances to
    forget; this is what makes the thirteenth fail out loud.
    """

    def test_the_store_calls_execute_only_inside_the_helpers(self):
        path = os.path.join(
            os.path.dirname(__file__), "..", "src", "nodus_lang_workflow", "store.py"
        )
        with open(path, encoding="utf-8") as handle:
            lines = handle.readlines()

        offenders = []
        for number, line in enumerate(lines, start=1):
            if "conn.execute(" not in line:
                continue
            # Prose is fine; the docstring on `_exec` quotes the old pattern to
            # explain what it replaced.
            if line.lstrip().startswith(("#", "`", '"', "*")) or "`conn.execute(" in line:
                continue
            offenders.append(f"{number}: {line.strip()}")

        self.assertEqual(
            [], offenders,
            "call sites bypassing the cursor-closing helpers -- use _exec / "
            "_fetchone / _fetchall, which own the cursor and close it on every "
            "exit including a raising statement",
        )


class TheStoreStillWorksTests(unittest.TestCase):
    """The rewrite touched every query in the store, so exercise the round trip."""

    # closes: #516
    def test_a_run_survives_write_read_claim_and_release(self):
        with tempfile.TemporaryDirectory() as td:
            store = SQLiteWorkflowStore(os.path.join(td, "w.db"))
            record = store.create_run(
                run_id="r1", graph_id="g1", workflow_name="w", execution_kind="workflow"
            )
            self.assertEqual("r1", record.run_id)

            self.assertEqual("g1", store.get_run("r1").graph_id)
            self.assertEqual(["r1"], [r.run_id for r in store.list_runs()])

            claim = store.claim_run("r1", owner="me")
            self.assertIsNotNone(claim, "claim_run committed -- this is the path #516 broke")
            released = store.release_claim("r1", claim.token)
            self.assertIsNotNone(released)
            self.assertIsNone(released.claim)

    def test_commit_succeeds_with_no_live_statements(self):
        """The failure mode directly: a claim commits inside an open transaction
        with a SELECT and an UPDATE before it. Under refcount-free GC those
        cursors were still open and the commit raised."""
        with tempfile.TemporaryDirectory() as td:
            store = SQLiteWorkflowStore(os.path.join(td, "w.db"))
            store.create_run(
                run_id="r2", graph_id="g2", workflow_name="w", execution_kind="workflow"
            )
            gc.disable()  # do not let a collection paper over a leaked cursor
            try:
                claim = store.claim_run("r2", owner="me")
            finally:
                gc.enable()
            self.assertIsNotNone(claim)


if __name__ == "__main__":
    unittest.main()
