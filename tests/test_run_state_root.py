"""Both halves of a run relocate together, and the Floor follows them (#585).

A durable run is one thing split across `.nodus/graphs/` (graph state and
checkpoint) and `.nodus/workflow_framework/` (the run record). #476 gave the two
halves a shared lifecycle. Their *location* stayed asymmetric:
`NODUS_WORKFLOW_STORE_ROOT` moved the records and the graph root was a hardcoded
module constant, so "give this process its own store" was not expressible and
every tenant in a process shared one CWD-relative graph directory.

The security half is the part worth reading twice. `DEFAULT_FLOOR` forbids a
Nodus program from writing into the runtime's own state, and answered that by
looking for a literal `.nodus` path segment — so the *supported* way to relocate
the store also moved it outside the Floor. That was demonstrated before it was
fixed: with `NODUS_WORKFLOW_STORE_ROOT` set, a guest's
`fs.write("../relocated/pwned.txt", "x")` landed in the live run store, while the
identical write to the default location was denied.
"""

import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from nodus.runtime.capability import DEFAULT_FLOOR  # noqa: E402
from nodus.runtime.state_paths import (  # noqa: E402
    RUN_STATE_ROOT_ENV,
    WORKFLOW_STORE_ROOT_ENV,
    graph_root,
    is_inside_run_state,
    run_state_roots,
    workflow_sqlite_path,
    workflow_store_root,
)


class _CleanEnv(unittest.TestCase):
    def setUp(self):
        self._saved = {n: os.environ.get(n)
                       for n in (RUN_STATE_ROOT_ENV, WORKFLOW_STORE_ROOT_ENV)}
        for name in self._saved:
            os.environ.pop(name, None)

    def tearDown(self):
        for name, value in self._saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


# closes: #585
class OneVariableMovesBothHalvesTests(_CleanEnv):

    def test_the_default_is_unchanged(self):
        self.assertEqual(os.path.join(".nodus", "graphs"), graph_root())
        self.assertEqual(os.path.join(".nodus", "workflow_framework"),
                         workflow_store_root())

    def test_both_halves_move_together(self):
        os.environ[RUN_STATE_ROOT_ENV] = "/state"
        self.assertEqual(os.path.join("/state", "graphs"), graph_root())
        self.assertEqual(os.path.join("/state", "workflow_framework"),
                         workflow_store_root())
        self.assertEqual(os.path.join("/state", "workflow_framework.sqlite3"),
                         workflow_sqlite_path())

    def test_there_is_no_graph_only_override(self):
        """Deliberate: a per-half knob for graphs would re-enable the very
        half-relocated state this exists to prevent. The narrow variable that
        does exist is the documented legacy one, and it moves records only."""
        os.environ["NODUS_GRAPH_ROOT"] = "/graphs-only"
        self.assertEqual(os.path.join(".nodus", "graphs"), graph_root())
        os.environ.pop("NODUS_GRAPH_ROOT", None)

    def test_the_legacy_variable_still_moves_only_its_own_half(self):
        os.environ[WORKFLOW_STORE_ROOT_ENV] = "/records"
        self.assertEqual("/records", workflow_store_root())
        self.assertEqual(os.path.join(".nodus", "graphs"), graph_root(),
                         "the legacy variable must not silently move the graphs too")

    def test_a_blank_value_is_ignored(self):
        os.environ[RUN_STATE_ROOT_ENV] = "   "
        self.assertEqual(os.path.join(".nodus", "graphs"), graph_root())


class TheFloorFollowsRelocatedStateTests(_CleanEnv):

    def _denied(self, path: str) -> bool:
        inside, _root = is_inside_run_state(path)
        return inside

    def test_the_default_location_is_covered(self):
        """The positive control for every negative assertion below."""
        self.assertTrue(self._denied(".nodus/workflow_framework/x.json"))
        self.assertTrue(self._denied(".nodus/graphs/g.json"))
        self.assertTrue(self._denied("../.nodus/graphs/g.json"))

    def test_relocated_state_is_covered(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ[RUN_STATE_ROOT_ENV] = tmp
            self.assertTrue(self._denied(os.path.join(tmp, "graphs", "g.json")))
            self.assertTrue(self._denied(os.path.join(tmp, "workflow_framework", "r.json")))
            self.assertTrue(self._denied(os.path.join(tmp, "anything-at-all")))

    def test_a_relocated_record_store_is_covered(self):
        """The hole as it actually existed: the documented override alone."""
        with tempfile.TemporaryDirectory() as tmp:
            os.environ[WORKFLOW_STORE_ROOT_ENV] = tmp
            self.assertTrue(self._denied(os.path.join(tmp, "runs", "r.json")))

    def test_an_ordinary_directory_is_not_covered(self):
        """The filter must not be too broad, or the Floor denies ordinary writes."""
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(self._denied(os.path.join(tmp, "notes.txt")))
            self.assertFalse(self._denied("output.json"))
            self.assertFalse(self._denied("my.nodus-notes.txt"))

    def test_a_sibling_of_the_root_is_not_covered(self):
        """`startswith` on a bare prefix would catch `/state-backup` for `/state`."""
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.join(tmp, "state")
            os.environ[RUN_STATE_ROOT_ENV] = root
            self.assertTrue(self._denied(os.path.join(root, "graphs", "g.json")))
            self.assertFalse(self._denied(os.path.join(tmp, "state-backup", "g.json")))

    def test_the_floor_itself_denies_a_write_to_relocated_state(self):
        """Through `DEFAULT_FLOOR.check`, not just the path predicate."""
        from nodus.runtime.capability import FS_WRITE, CapabilityRequest

        with tempfile.TemporaryDirectory() as tmp:
            os.environ[RUN_STATE_ROOT_ENV] = tmp
            target = os.path.join(tmp, "graphs", "g.json")
            decision = DEFAULT_FLOOR.check(CapabilityRequest(
                capability=FS_WRITE, target="fs_write", kind="builtin", args=(target,),
            ))
            self.assertIsNotNone(decision, "the Floor let a relocated-state write through")
            self.assertFalse(decision.allowed)

            benign = DEFAULT_FLOOR.check(CapabilityRequest(
                capability=FS_WRITE, target="fs_write", kind="builtin",
                args=(os.path.join(tmp, "..", "ok.txt"),),
            ))
            self.assertIsNone(benign, "the Floor is denying ordinary writes")

    def test_roots_are_absolute_and_deduplicated(self):
        os.environ[RUN_STATE_ROOT_ENV] = "."
        roots = run_state_roots()
        self.assertTrue(all(os.path.isabs(r) for r in roots))
        self.assertEqual(len(roots), len(set(roots)))


class EndToEndTests(_CleanEnv):

    def test_a_cli_run_puts_both_halves_under_the_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            workdir = pathlib.Path(tmp) / "work"
            workdir.mkdir()
            state = pathlib.Path(tmp) / "state"
            (workdir / "wf.nd").write_text(
                "workflow demo {\n"
                "    step a { return 1i }\n"
                "    step b after a { return 2i }\n"
                "}\n"
                "let r = run_workflow(demo)\n"
                'print("steps=\\(r["steps"])")\n',
                encoding="utf-8",
            )
            env = {**os.environ,
                   "PYTHONPATH": str(REPO / "src"),
                   RUN_STATE_ROOT_ENV: str(state)}
            proc = subprocess.run(
                [sys.executable, str(REPO / "nodus.py"), "run", "wf.nd"],
                cwd=str(workdir), capture_output=True, text=True, env=env, timeout=120,
            )
            self.assertEqual(0, proc.returncode, proc.stderr)
            self.assertIn("steps=", proc.stdout)

            graphs = list((state / "graphs").glob("*.json")) if (state / "graphs").is_dir() else []
            runs_dir = state / "workflow_framework" / "runs"
            records = list(runs_dir.glob("*.json")) if runs_dir.is_dir() else []
            self.assertTrue(graphs, "the graph half did not follow the root")
            self.assertTrue(records, "the record half did not follow the root")

            # And nothing run-shaped stayed behind. `.nodus/` may still exist for
            # the *project* family (cache, deps.json), which is a different root
            # and deliberately not moved by this variable.
            self.assertFalse((workdir / ".nodus" / "graphs").exists())
            self.assertFalse((workdir / ".nodus" / "workflow_framework").exists())


if __name__ == "__main__":
    unittest.main()
