"""Tests for Task 5.1: path traversal consistency in imports."""
import os
import tempfile
import unittest

import nodus as lang
from nodus.runtime.module_loader import ModuleLoader


def _loader_for(project_root: str | None) -> ModuleLoader:
    return ModuleLoader(project_root=project_root)


class PathTraversalProjectModeTests(unittest.TestCase):
    """Traversal checks when an explicit project root is set."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.td = self._td.name
        self.proj = os.path.join(self.td, "project")
        os.makedirs(self.proj)
        outside = os.path.join(self.td, "outside.nd")
        with open(outside, "w", encoding="utf-8") as f:
            f.write("export let x = 99\n")

    def tearDown(self):
        self._td.cleanup()

    def _write_main(self, import_line: str) -> str:
        main = os.path.join(self.proj, "main.nd")
        with open(main, "w", encoding="utf-8") as f:
            f.write(import_line + "\n")
        return main

    def test_escaping_import_raises(self):
        main = self._write_main('import { x } from "../outside.nd"')
        loader = _loader_for(self.proj)
        with self.assertRaises(lang.LangRuntimeError) as cm:
            loader.load_module_from_path(main)
        msg = str(cm.exception)
        self.assertIn("Invalid import", msg)
        self.assertIn("../outside.nd", msg)
        self.assertIn("escapes", msg)

    def test_escaping_import_error_names_path(self):
        """Error message must name the offending import path."""
        main = self._write_main('import { x } from "../outside.nd"')
        loader = _loader_for(self.proj)
        with self.assertRaises(lang.LangRuntimeError) as cm:
            loader.load_module_from_path(main)
        self.assertIn("'../outside.nd'", str(cm.exception))

    def test_in_tree_relative_import_accepted(self):
        sibling = os.path.join(self.proj, "sibling.nd")
        with open(sibling, "w", encoding="utf-8") as f:
            f.write("export let v = 42\n")
        main = self._write_main('import { v } from "./sibling.nd"\nprint(v)\n')
        loader = _loader_for(self.proj)
        loader.load_module_from_path(main)

    def test_double_dot_chain_blocked(self):
        """Multiple levels of .. are also blocked."""
        deep = os.path.join(self.proj, "sub")
        os.makedirs(deep)
        main = os.path.join(deep, "main.nd")
        with open(main, "w", encoding="utf-8") as f:
            f.write('import { x } from "../../outside.nd"\n')
        loader = _loader_for(self.proj)
        with self.assertRaises(lang.LangRuntimeError) as cm:
            loader.load_module_from_path(main)
        self.assertIn("escapes", str(cm.exception))


class PathTraversalSingleFileModeTests(unittest.TestCase):
    """Traversal checks when no project root is given (single-file mode)."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.td = self._td.name
        self.file_dir = os.path.join(self.td, "src")
        os.makedirs(self.file_dir)
        outside = os.path.join(self.td, "outside.nd")
        with open(outside, "w", encoding="utf-8") as f:
            f.write("export let x = 99\n")

    def tearDown(self):
        self._td.cleanup()

    def test_escaping_import_blocked_in_single_file_mode(self):
        main = os.path.join(self.file_dir, "main.nd")
        with open(main, "w", encoding="utf-8") as f:
            f.write('import { x } from "../outside.nd"\n')
        loader = _loader_for(None)
        with self.assertRaises(lang.LangRuntimeError) as cm:
            loader.load_module_from_path(main)
        msg = str(cm.exception)
        self.assertIn("Invalid import", msg)
        self.assertIn("escapes", msg)

    def test_in_tree_relative_import_accepted_single_file_mode(self):
        sibling = os.path.join(self.file_dir, "sibling.nd")
        with open(sibling, "w", encoding="utf-8") as f:
            f.write("export let v = 7\n")
        main = os.path.join(self.file_dir, "main.nd")
        with open(main, "w", encoding="utf-8") as f:
            f.write('import { v } from "./sibling.nd"\nprint(v)\n')
        loader = _loader_for(None)
        loader.load_module_from_path(main)
