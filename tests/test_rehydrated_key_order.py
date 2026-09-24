"""A rehydrated run sees its data in the order the live run built it (#871).

Both stores and the graph snapshot persisted state with `sort_keys=True`, so a
map the program built as `{web, code, data}` came back `{code, data, web}` after
a cross-process resume. Same content, different string — and anything derived
from it therefore differed across a restart: a draft, a hash, an `@exactly_once`
key. That last one is how it was found: an idempotent publish re-fired on a
rehydrated replay of an identical draft.

JSON objects preserve order and `json.load` round-trips it, so nothing but the
sort was destroying it.

**The distinction this pins is `reported` vs `compared`.** Persisted state is
read back and handed to a program, so it must come back as it went in. An
*identity* — `compute_action_id`, the bytecode cache key — is hashed, and there
two equal maps must produce one answer, so those stay sorted. Both directions
are asserted here: removing the sort where it is load-bearing has to fail too,
or this file would read as "sorting is always wrong".
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, "C:/dev/Coding Language/src")

from nodus.runtime.embedding import NodusRuntime  # noqa: E402

# Deliberately not alphabetical, and not reverse-alphabetical either: a sort
# would move every key, and an accidental pass-through of *some* order would
# still be visible.
UNSORTED = '{"web": 1, "code": 2, "data": 3}'

STEP_RESULT_SOURCE = '''
import "std:json" as json
workflow w {
    step analyze { return {"web": 1, "code": 2, "data": 3} }
    step gate after analyze { return workflow_wait("go", "k1", {}) }
    step derive after analyze, gate { return {"s": json.stringify(analyze)} }
}
'''

# Declared unsorted as well as written. The record a store persists at park time
# carries the *declaration*, not the step's write — found by asserting on the
# write and getting the declared value back.
STATE_CELL_SOURCE = '''
import "std:json" as json
workflow w {
    state cfg = {"web": 1, "code": 2, "data": 3}
    step a { cfg = {"web": 1, "code": 2, "data": 3}; return workflow_wait("go", "k1", {}) }
    step b after a { return {"s": json.stringify(cfg)} }
}
'''


class _Harness(unittest.TestCase):
    """Runs on whatever backend the process already has.

    Deliberately not parametrised by backend. `NODUS_WORKFLOW_STORE_BACKEND` is
    read when the default runner is *built*, and that runner is cached for the
    process — so setting the variable in `setUp` after another test has built one
    silently does nothing, and the test then reads a store it is not writing to.
    Which is what happened here: these passed alone and failed in the file.

    The round trip under test is the **graph snapshot**, which both backends
    share, so one run covers it. The store-level serialization is covered
    directly in `EachStoreKeepsTheOrderItWasGiven`, against stores constructed in
    a tempdir with no global state involved.
    """

    def setUp(self):
        self.captured: dict = {}

    def _runtime(self):
        runtime = NodusRuntime(timeout_ms=None)
        runtime.register_function(
            "_cap", lambda v: self.captured.__setitem__("r", v), arity=1)
        return runtime

    def _park(self, source):
        runtime = self._runtime()
        runtime.run_source(source + "\n_cap(run_workflow(w))\n")
        started = runtime._to_host_value(self.captured["r"])
        self.assertEqual(started["status"], "waiting", "expected a parked run")
        return started["graph_id"]

    def _resume(self, source, graph_id):
        runtime = self._runtime()
        runtime.run_source(source)
        vm = runtime._get_active_vm()
        return runtime._to_host_value(
            vm.builtin_resume_workflow(graph_id, None, {"ok": True}))


# closes: #871
class StepResultsKeepTheirOrder(_Harness):
    def test_a_rehydrated_step_result_stringifies_as_it_was_built(self):
        result = self._resume(
            STEP_RESULT_SOURCE, self._park(STEP_RESULT_SOURCE))
        self.assertEqual(
            result["steps"]["derive"]["s"], UNSORTED,
            "a prior step's result came back reordered, so anything derived "
            "from it differs across a restart",
        )

    def test_the_live_run_is_the_control(self):
        # Without this the test above passes on a build where stringify itself
        # sorts, which would be the same symptom from a different cause.
        runtime = self._runtime()
        runtime.run_source(
            STEP_RESULT_SOURCE.replace(
                'step gate after analyze { return workflow_wait("go", "k1", {}) }',
                "step gate after analyze { return {\"g\": 1} }")
            + "\n_cap(run_workflow(w))\n")
        live = runtime._to_host_value(self.captured["r"])
        self.assertEqual(live["steps"]["derive"]["s"], UNSORTED)


# closes: #871
class StateCellsKeepTheirOrder(_Harness):
    def test_a_rehydrated_state_cell_stringifies_as_it_was_written(self):
        result = self._resume(STATE_CELL_SOURCE, self._park(STATE_CELL_SOURCE))
        self.assertEqual(result["steps"]["b"]["s"], UNSORTED)


# closes: #871
class EachStoreKeepsTheOrderItWasGiven(unittest.TestCase):
    """`nodus workflow inspect` prints `metadata`, so a sorted copy is visible.

    The resume reads the graph snapshot, so the store's copy being sorted was not
    what broke a run — it was a second answer to the same question, which is how
    the first one comes back. Both backends serialize through different code, so
    both are checked, against stores built in a tempdir rather than the ambient
    one: the repo-root store holds hundreds of records from other tests, and
    `list_runs()[-1]` there reads a stranger's state.
    """

    def _round_trip(self, store, run_id):
        record = store.create_run(
            run_id=run_id, graph_id=run_id, workflow_name="demo",
            execution_kind="workflow",
            metadata={"workflow_state": {"cfg": {"web": 1, "code": 2, "data": 3}}},
        )
        store.save_run(record)
        reloaded = store.get_run(run_id)
        self.assertIsNotNone(reloaded)
        return reloaded.metadata["workflow_state"]["cfg"]

    def test_the_local_store_keeps_the_order(self):
        from nodus_lang_workflow.store import LocalWorkflowStore

        with tempfile.TemporaryDirectory() as root:
            cfg = self._round_trip(LocalWorkflowStore(root=root), "r-local")
            self.assertEqual(
                list(cfg), ["web", "code", "data"],
                f"the local store reordered a state cell: {json.dumps(cfg)}",
            )

    def test_the_sqlite_store_keeps_the_order(self):
        from nodus_lang_workflow.store import SQLiteWorkflowStore

        with tempfile.TemporaryDirectory() as root:
            store = SQLiteWorkflowStore(path=os.path.join(root, "w.sqlite3"))
            cfg = self._round_trip(store, "r-sqlite")
            self.assertEqual(
                list(cfg), ["web", "code", "data"],
                f"the sqlite store reordered a state cell: {json.dumps(cfg)}",
            )


# closes: #871
class CanonicalFormSurvivesWhereItIsLoadBearing(unittest.TestCase):
    """The other direction, so this is not read as "sorting is always wrong".

    An identity is *compared*, not reported: two equal maps built in different
    orders must hash the same. Asserted on the source, because a behavioural
    test would pass on whichever call site already happens to be canonical.
    """

    def _source_of(self, fn):
        import inspect

        return inspect.getsource(fn)

    def test_the_effect_action_id_still_hashes_a_sorted_payload(self):
        from nodus.builtins import effects_module

        source = self._source_of(effects_module)
        self.assertIn(
            "sort_keys=True", source,
            "compute_action_id stopped canonicalising, so two equal payloads "
            "built in different orders would get different @exactly_once keys",
        )

    def test_the_graph_cache_key_still_hashes_a_sorted_payload(self):
        from nodus.orchestration import task_graph

        source = self._source_of(task_graph)
        self.assertIn(
            'json.dumps(payload, sort_keys=True', source,
            "the cache key stopped canonicalising",
        )

    def test_the_state_snapshot_does_not_canonicalise(self):
        # The fix itself, asserted on the source: a behavioural test cannot tell
        # a snapshot that preserves order from one whose keys happened to be
        # written in sorted order already.
        from nodus.orchestration import task_graph

        source = self._source_of(task_graph)
        self.assertIn('json.dump(data, handle, separators=(",", ":"))', source)
        self.assertNotIn(
            'json.dump(data, handle, sort_keys=True', source,
            "the graph snapshot sorts again (#871)",
        )


if __name__ == "__main__":
    unittest.main()
