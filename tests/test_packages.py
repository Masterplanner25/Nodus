import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

import nodus as lang
from nodus.tooling.runner import run_source


def run_program(src: str, source_path: str | None = None) -> list[str]:
    result, _vm = run_source(src, filename=source_path)
    return result.get("stdout", "").splitlines()


class PackageTests(unittest.TestCase):
    def test_init_creates_manifest_and_modules_dir(self):
        with tempfile.TemporaryDirectory() as td:
            buf = io.StringIO()
            with redirect_stdout(buf):
                exit_code = lang.main(["nodus", "init", "--project-root", td])
            self.assertEqual(exit_code, 0)
            self.assertTrue(os.path.isfile(os.path.join(td, "nodus.toml")))
            self.assertTrue(os.path.isdir(os.path.join(td, ".nodus", "modules")))

    def test_install_creates_dependency_and_lockfile(self):
        with tempfile.TemporaryDirectory() as td:
            utils_dir = os.path.join(td, "utils")
            os.makedirs(utils_dir, exist_ok=True)
            with open(os.path.join(utils_dir, "nodus.toml"), "w", encoding="utf-8") as f:
                f.write('name = "utils"\n')
                f.write('version = "1.2.3"\n')
            with open(os.path.join(utils_dir, "strings.nd"), "w", encoding="utf-8") as f:
                f.write('export fn upper(x) { return x }\n')

            manifest_path = os.path.join(td, "nodus.toml")
            with open(manifest_path, "w", encoding="utf-8") as f:
                f.write('name = "demo"\n')
                f.write('version = "0.1.0"\n\n')
                f.write("[dependencies]\n")
                f.write('utils = { path = "./utils" }\n')

            buf = io.StringIO()
            with redirect_stdout(buf):
                exit_code = lang.main(["nodus", "install", "--project-root", td])

            self.assertEqual(exit_code, 0)
            self.assertTrue(os.path.isdir(os.path.join(td, ".nodus", "modules", "utils")))
            self.assertTrue(os.path.isfile(os.path.join(td, "nodus.lock")))
            with open(os.path.join(td, "nodus.lock"), "r", encoding="utf-8") as f:
                lock_text = f.read()
            self.assertIn('[[package]]', lock_text)
            self.assertIn('name = "utils"', lock_text)
            self.assertIn('source = "path:utils"', lock_text)
            self.assertIn('hash = "sha256:', lock_text)

    def test_dependency_import_resolution(self):
        with tempfile.TemporaryDirectory() as td:
            with open(os.path.join(td, "nodus.toml"), "w", encoding="utf-8") as f:
                f.write('name = "demo"\n')
                f.write('version = "0.1.0"\n\n')
            dep_dir = os.path.join(td, ".nodus", "modules", "utils")
            os.makedirs(dep_dir, exist_ok=True)
            with open(os.path.join(dep_dir, "strings.nd"), "w", encoding="utf-8") as f:
                f.write('export fn upper(value) { return "FROM_DEP:" + value }\n')
            main_path = os.path.join(td, "main.nd")
            with open(main_path, "w", encoding="utf-8") as f:
                f.write('import "utils:strings" as s\nprint(s.upper("ok"))\n')

            with open(main_path, "r", encoding="utf-8") as f:
                src = f.read()
            self.assertEqual(run_program(src, source_path=main_path), ["FROM_DEP:ok"])

    def test_deps_lists_installed_dependencies(self):
        with tempfile.TemporaryDirectory() as td:
            with open(os.path.join(td, "nodus.toml"), "w", encoding="utf-8") as f:
                f.write('name = "demo"\n')
                f.write('version = "0.1.0"\n\n')
                f.write("[dependencies]\n")
                f.write('utils = { path = "./utils" }\n')
            with open(os.path.join(td, "nodus.lock"), "w", encoding="utf-8") as f:
                f.write("[[package]]\n")
                f.write('name = "utils"\n')
                f.write('version = "0.0.0"\n')
                f.write('source = "path:./utils"\n')
                f.write('hash = "sha256:abc123"\n')

            buf = io.StringIO()
            err = io.StringIO()
            with redirect_stdout(buf), redirect_stderr(err):
                exit_code = lang.main(["nodus", "deps", "--project-root", td])
            self.assertEqual(exit_code, 0)
            self.assertEqual(err.getvalue(), "")
            self.assertIn("utils: path:./utils", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
