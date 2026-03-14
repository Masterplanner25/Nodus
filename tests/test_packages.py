import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch

import nodus as lang


def run_program(src: str, source_path: str | None = None) -> list[str]:
    _ast, code, functions, code_locs = lang.compile_source(
        src,
        source_path=source_path,
        import_state={"loaded": set(), "loading": set(), "exports": {}, "modules": {}, "module_ids": {}, "project_root": None},
    )
    vm = lang.VM(code, functions, code_locs=code_locs, source_path=source_path)
    buf = io.StringIO()
    with redirect_stdout(buf):
        vm.run()
    return buf.getvalue().splitlines()


class PackageTests(unittest.TestCase):
    def test_init_creates_manifest_and_deps_dir(self):
        with tempfile.TemporaryDirectory() as td:
            buf = io.StringIO()
            with redirect_stdout(buf):
                exit_code = lang.main(["nodus", "init", "--project-root", td])
            self.assertEqual(exit_code, 0)
            self.assertTrue(os.path.isfile(os.path.join(td, "nodus.toml")))
            self.assertTrue(os.path.isdir(os.path.join(td, "deps")))

    def test_install_creates_dependency_and_lockfile(self):
        with tempfile.TemporaryDirectory() as td:
            manifest_path = os.path.join(td, "nodus.toml")
            with open(manifest_path, "w", encoding="utf-8") as f:
                f.write('name = "demo"\n')
                f.write('version = "0.1.0"\n\n')
                f.write("[dependencies]\n")
                f.write('utils = "git+https://example.com/utils.git"\n')

            def fake_run_git(args, cwd=None):
                if args[0] == "clone":
                    dest = args[2]
                    os.makedirs(dest, exist_ok=True)
                    with open(os.path.join(dest, "strings.nd"), "w", encoding="utf-8") as f:
                        f.write('export fn upper(x) { return x }\n')
                    return ""
                if args[0] == "-C" and args[2] == "rev-parse":
                    return "abc123"
                raise AssertionError(f"Unexpected git args: {args}")

            buf = io.StringIO()
            with patch("package_manager.run_git", side_effect=fake_run_git):
                with redirect_stdout(buf):
                    exit_code = lang.main(["nodus", "install", "--project-root", td])

            self.assertEqual(exit_code, 0)
            self.assertTrue(os.path.isdir(os.path.join(td, "deps", "utils")))
            self.assertTrue(os.path.isfile(os.path.join(td, "nodus.lock")))
            with open(os.path.join(td, "nodus.lock"), "r", encoding="utf-8") as f:
                lock_text = f.read()
            self.assertIn('utils = "git+https://example.com/utils.git@abc123"', lock_text)

    def test_dependency_import_resolution(self):
        with tempfile.TemporaryDirectory() as td:
            with open(os.path.join(td, "nodus.toml"), "w", encoding="utf-8") as f:
                f.write('name = "demo"\n')
                f.write('version = "0.1.0"\n\n')
                f.write("[dependencies]\n")
                f.write('utils = "git+https://example.com/utils.git"\n')
            dep_dir = os.path.join(td, "deps", "utils")
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
                f.write('utils = "git+https://example.com/utils.git"\n')
            with open(os.path.join(td, "nodus.lock"), "w", encoding="utf-8") as f:
                f.write('utils = "git+https://example.com/utils.git@abc123"\n')

            buf = io.StringIO()
            err = io.StringIO()
            with redirect_stdout(buf), redirect_stderr(err):
                exit_code = lang.main(["nodus", "deps", "--project-root", td])
            self.assertEqual(exit_code, 0)
            self.assertEqual(err.getvalue(), "")
            self.assertIn("utils: git+https://example.com/utils.git@abc123", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
