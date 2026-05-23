"""Tests for Task 5.2: REPL import parity with CLI execution."""
import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout

import nodus as lang
from nodus.runtime.module_loader import ModuleLoader
from nodus.tooling.repl import ReplState, _execute_source


def _make_state() -> ReplState:
    return ReplState(
        globals={},
        fn_defs={},
        import_state={"loaded": set(), "loading": set(), "exports": {}, "modules": {}, "module_ids": {}, "project_root": None},
    )


class ReplImportParityTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.td = self._td.name

    def tearDown(self):
        self._td.cleanup()

    # ------------------------------------------------------------------ 5.2.1
    def test_project_root_relative_import_works_in_repl(self):
        """Bare 'lib' resolves from project root when REPL is started inside a project."""
        lib_nd = os.path.join(self.td, "lib.nd")
        with open(lib_nd, "w", encoding="utf-8") as f:
            f.write("export let answer = 77\n")
        loader = ModuleLoader(project_root=self.td)
        state = _make_state()
        buf = io.StringIO()
        with redirect_stdout(buf):
            _execute_source(state, loader, 'import { answer } from "lib"\nprint(answer)\n')
        self.assertEqual(buf.getvalue().strip(), "77.0")

    # ------------------------------------------------------------------ 5.2.2
    def test_path_traversal_blocked_in_repl(self):
        """import '../outside.nd' must be blocked in the REPL just as in CLI."""
        proj_dir = os.path.join(self.td, "project")
        os.makedirs(proj_dir)
        outside_nd = os.path.join(self.td, "outside.nd")
        with open(outside_nd, "w", encoding="utf-8") as f:
            f.write("export let x = 1\n")
        loader = ModuleLoader(project_root=proj_dir)
        state = _make_state()
        with self.assertRaises(lang.LangRuntimeError) as cm:
            _execute_source(state, loader, 'import { x } from "../outside.nd"\n')
        msg = str(cm.exception)
        self.assertIn("Invalid import", msg)
        self.assertIn("escapes", msg)

    # ------------------------------------------------------------------ 5.2.3
    def test_index_nd_resolution_works_in_repl(self):
        """Bare 'lib' resolves to lib/index.nd when lib.nd does not exist."""
        lib_dir = os.path.join(self.td, "lib")
        os.makedirs(lib_dir)
        index_nd = os.path.join(lib_dir, "index.nd")
        with open(index_nd, "w", encoding="utf-8") as f:
            f.write("export let v = 55\n")
        loader = ModuleLoader(project_root=self.td)
        state = _make_state()
        buf = io.StringIO()
        with redirect_stdout(buf):
            _execute_source(state, loader, 'import { v } from "lib"\nprint(v)\n')
        self.assertEqual(buf.getvalue().strip(), "55.0")

    def test_in_tree_relative_import_works_in_repl(self):
        """./sibling.nd imports still work from the REPL's cwd."""
        sibling_nd = os.path.join(self.td, "sibling.nd")
        with open(sibling_nd, "w", encoding="utf-8") as f:
            f.write("export let z = 13\n")
        loader = ModuleLoader(project_root=self.td)
        state = _make_state()
        old_cwd = os.getcwd()
        os.chdir(self.td)
        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                _execute_source(state, loader, 'import { z } from "./sibling.nd"\nprint(z)\n')
            self.assertEqual(buf.getvalue().strip(), "13.0")
        finally:
            os.chdir(old_cwd)
