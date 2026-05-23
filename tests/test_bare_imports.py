"""Tests for Tasks 3.1 and 3.2: project-root-relative imports and index.nd resolution."""
import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout

import nodus as lang
from nodus.runtime.module_loader import ModuleLoader
from nodus.vm.vm import VM


def _run(src: str, source_path: str) -> list[str]:
    module_name = os.path.abspath(source_path)
    base_dir = os.path.dirname(module_name)
    vm = VM([], {}, code_locs=[], source_path=source_path)
    loader = ModuleLoader(project_root=None, vm=vm)
    buf = io.StringIO()
    with redirect_stdout(buf):
        loader.load_module_from_source(src, module_name=module_name, base_dir=base_dir)
    return buf.getvalue().splitlines()


class BareImportTests(unittest.TestCase):
    # ------------------------------------------------------------------ 3.1
    def test_bare_import_resolves_from_project_root_subdirectory(self):
        """import "lib/math" from src/main.nd finds <root>/lib/math.nd."""
        with tempfile.TemporaryDirectory() as td:
            lib_dir = os.path.join(td, "lib")
            src_dir = os.path.join(td, "src")
            os.makedirs(lib_dir)
            os.makedirs(src_dir)
            # nodus.toml establishes td as the project root so that bare "lib/math"
            # resolves relative to td, not relative to src/.
            with open(os.path.join(td, "nodus.toml"), "w", encoding="utf-8") as f:
                f.write('[package]\nname = "test"\nversion = "0.1.0"\n\n[dependencies]\n')
            math_nd = os.path.join(lib_dir, "math.nd")
            main_nd = os.path.join(src_dir, "main.nd")
            with open(math_nd, "w", encoding="utf-8") as f:
                f.write("export let pi = 3\n")
            with open(main_nd, "w", encoding="utf-8") as f:
                f.write('import { pi } from "lib/math"\nprint(pi)\n')
            src = open(main_nd, encoding="utf-8").read()
            result = _run(src, main_nd)
        self.assertEqual(result, ["3.0"])

    def test_bare_import_from_same_level_resolves_from_root(self):
        """import "utils" finds <root>/utils.nd without a leading ./."""
        with tempfile.TemporaryDirectory() as td:
            utils_nd = os.path.join(td, "utils.nd")
            main_nd = os.path.join(td, "main.nd")
            with open(utils_nd, "w", encoding="utf-8") as f:
                f.write("export let v = 42\n")
            with open(main_nd, "w", encoding="utf-8") as f:
                f.write('import { v } from "utils"\nprint(v)\n')
            src = open(main_nd, encoding="utf-8").read()
            result = _run(src, main_nd)
        self.assertEqual(result, ["42.0"])

    def test_bare_import_not_found_error_names_paths_tried(self):
        """Error for a missing bare import mentions both project-root and stdlib paths."""
        with tempfile.TemporaryDirectory() as td:
            main_nd = os.path.join(td, "main.nd")
            with open(main_nd, "w", encoding="utf-8") as f:
                f.write('import { x } from "totally/missing"\n')
            src = open(main_nd, encoding="utf-8").read()
            with self.assertRaises(lang.LangRuntimeError) as cm:
                _run(src, main_nd)
        msg = str(cm.exception)
        self.assertIn("Import not found", msg)
        # Error should name the project-root path that was tried
        self.assertIn("totally", msg)
        # Error should name both .nd and index.nd candidates
        self.assertIn(".nd", msg)
        self.assertIn("index.nd", msg)

    # ------------------------------------------------------------------ 3.2
    def test_bare_directory_import_resolves_to_index_nd(self):
        """import "lib" resolves to lib/index.nd when lib.nd does not exist."""
        with tempfile.TemporaryDirectory() as td:
            lib_dir = os.path.join(td, "lib")
            os.makedirs(lib_dir)
            index_nd = os.path.join(lib_dir, "index.nd")
            main_nd = os.path.join(td, "main.nd")
            with open(index_nd, "w", encoding="utf-8") as f:
                f.write("export let answer = 99\n")
            with open(main_nd, "w", encoding="utf-8") as f:
                f.write('import { answer } from "lib"\nprint(answer)\n')
            src = open(main_nd, encoding="utf-8").read()
            result = _run(src, main_nd)
        self.assertEqual(result, ["99.0"])

    def test_bare_file_takes_priority_over_index(self):
        """lib.nd is preferred over lib/index.nd for import "lib"."""
        with tempfile.TemporaryDirectory() as td:
            lib_dir = os.path.join(td, "lib")
            os.makedirs(lib_dir)
            lib_nd = os.path.join(td, "lib.nd")
            index_nd = os.path.join(lib_dir, "index.nd")
            main_nd = os.path.join(td, "main.nd")
            with open(lib_nd, "w", encoding="utf-8") as f:
                f.write("export let v = 1\n")
            with open(index_nd, "w", encoding="utf-8") as f:
                f.write("export let v = 9\n")
            with open(main_nd, "w", encoding="utf-8") as f:
                f.write('import { v } from "lib"\nprint(v)\n')
            src = open(main_nd, encoding="utf-8").read()
            result = _run(src, main_nd)
        self.assertEqual(result, ["1.0"])
