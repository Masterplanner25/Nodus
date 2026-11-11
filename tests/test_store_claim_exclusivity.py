"""#180 stage 4a: a store's claim on a run is exclusive across processes, or it says not.

Durable coroutines (design 08a, D3-D5) depend on one property of the store: a
program restarted after a crash and a host rehydrating runs must never both
resume one coroutine. `claim_run` decides between them, so the property is that
two claimants **in different processes** cannot both win.

It is not "crash safety". Both built-in stores write each record atomically:
`LocalWorkflowStore` by fsync and rename, SQLite by transaction. What separates
them is that the JSON store's check-then-write is guarded by a `threading.Lock`,
which one process holds and another cannot see.

Each store declares the property (`EXCLUSIVE_CLAIMS_ACROSS_PROCESSES`), and this
file checks every declaration against a race rather than trusting it. Two
instances over the same backing stand in for two processes: neither instance
can see the other's in-process lock, which is exactly the cross-process
condition. The second claimant starts *inside* the first one's check-then-write
window, the only place the race can be lost.
"""

import sys
import tempfile
import threading
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))  # noqa: E402

from nodus_lang_workflow.models import RUN_STATUS_RUNNING  # noqa: E402
from nodus_lang_workflow.store import (  # noqa: E402
    LocalWorkflowStore,
    SQLiteWorkflowStore,
    StoreUnsuitableError,
    WorkflowStore,
    require_exclusive_claims,
)

# Every built-in store, with how to open two handles on one backing and which
# method is the read inside its claim's critical section.
_STORES = {
    "LocalWorkflowStore": (lambda tmp: LocalWorkflowStore(str(tmp)), "_load_run_unlocked"),
    "SQLiteWorkflowStore": (lambda tmp: SQLiteWorkflowStore(str(tmp / "runs.db")), "_get_run_with_conn"),
}


def _race(open_store, read_hook: str) -> list:
    """Claim one run from two handles, the second inside the first's window.
    Returns every claim that was granted."""
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        first, second = open_store(tmp), open_store(tmp)
        record = first.create_run(run_id="r1", graph_id="r1", workflow_name="w",
                                  execution_kind="workflow")
        record.status = RUN_STATUS_RUNNING
        first.save_run(record)

        granted: list = []
        rival_result: list = []
        original = getattr(first, read_hook)

        def read_then_let_the_rival_in(*args, **kwargs):
            value = original(*args, **kwargs)
            rival = threading.Thread(
                target=lambda: rival_result.append(second.claim_run("r1", owner="second")))
            rival.start()
            # A store that excludes the rival keeps it waiting here; one that
            # does not lets it finish. Either way the first claimant then goes on.
            #
            # The timeout is headroom for the non-exclusive case: if the rival
            # has not finished by then, the race was not run and that store
            # would look exclusive. `join` returns as soon as the rival
            # finishes, so only the exclusive store pays the full wait, and it
            # stays under SQLite's 5 s busy timeout so its rival waits rather
            # than erroring.
            rival.join(timeout=3.0)
            read_then_let_the_rival_in.rival = rival
            return value

        setattr(first, read_hook, read_then_let_the_rival_in)
        granted.append(first.claim_run("r1", owner="first"))
        read_then_let_the_rival_in.rival.join(timeout=30)
        granted.extend(rival_result)
        return [claim for claim in granted if claim is not None]


class EachStoreDeclaresWhatItDoesTests(unittest.TestCase):

    def test_every_built_in_store_is_checked(self):
        """A store class added later must be added to `_STORES`, or its
        declaration is unchecked."""
        def subclasses(cls):
            for sub in cls.__subclasses__():
                yield sub
                yield from subclasses(sub)
        built_in = {c.__name__ for c in subclasses(WorkflowStore)
                    if c.__module__ == "nodus_lang_workflow.store"}
        self.assertEqual(set(_STORES), built_in)

    def test_the_declaration_matches_a_race(self):
        for name, (open_store, hook) in _STORES.items():
            with self.subTest(name):
                cls = {"LocalWorkflowStore": LocalWorkflowStore,
                       "SQLiteWorkflowStore": SQLiteWorkflowStore}[name]
                granted = _race(open_store, hook)
                exclusive = len(granted) == 1
                self.assertGreaterEqual(len(granted), 1, "nobody got the claim")
                self.assertEqual(cls.EXCLUSIVE_CLAIMS_ACROSS_PROCESSES, exclusive,
                                 f"{name} declares {cls.EXCLUSIVE_CLAIMS_ACROSS_PROCESSES} "
                                 f"but {len(granted)} claimants won the race")

    def test_the_base_class_assumes_the_worst(self):
        """A third-party store that says nothing is treated as not exclusive: a
        wrong True costs a run resumed twice, a wrong False only an opt-in."""
        self.assertIs(False, WorkflowStore.EXCLUSIVE_CLAIMS_ACROSS_PROCESSES)


class TheRefusalTests(unittest.TestCase):

    def test_a_store_without_exclusive_claims_is_refused_with_the_fix(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(StoreUnsuitableError) as caught:
                require_exclusive_claims(LocalWorkflowStore(tmp), feature="durable_spawn")
        message = str(caught.exception)
        self.assertIn("durable_spawn", message)
        self.assertIn("LocalWorkflowStore", message)
        self.assertIn("NODUS_WORKFLOW_STORE_BACKEND=sqlite", message)
        self.assertIn("migrate-store", message)

    def test_a_store_with_exclusive_claims_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            require_exclusive_claims(SQLiteWorkflowStore(str(Path(tmp) / "r.db")),
                                     feature="durable_spawn")

    def test_only_a_real_true_counts(self):
        """`getattr(..., False) is True`, so a truthy non-bool (a string, say)
        does not slip through as a declaration."""
        class Sloppy:
            EXCLUSIVE_CLAIMS_ACROSS_PROCESSES = "yes"
        with self.assertRaises(StoreUnsuitableError):
            require_exclusive_claims(Sloppy(), feature="x")


if __name__ == "__main__":
    unittest.main()
