"""Tests for the import-cluster fix: nested imports raise a compile-time error.

Covers issues #32 (BUG-031), #43 (BUG-042), #52 (if/else variant).
Root cause: resolve_imports walks only top-level stmts; the compiler
silently ignored Import nodes in nested positions. Fix: compiler now
raises LangSyntaxError with a clear message for any import that is not
at module root.
"""
import os
import tempfile
import unittest

from nodus.runtime.diagnostics import LangSyntaxError
from nodus.runtime.module_loader import ModuleLoader
from nodus.vm.vm import VM


def _compile(src: str):
    """Compile src in a temp dir; return None on success, raise on error."""
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "main.nd")
        vm = VM([], {}, code_locs=[], source_path=path)
        loader = ModuleLoader(project_root=None, vm=vm)
        loader.load_module_from_source(src, module_name=path, base_dir=td)


def _expect_error(src: str) -> LangSyntaxError:
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "main.nd")
        vm = VM([], {}, code_locs=[], source_path=path)
        loader = ModuleLoader(project_root=None, vm=vm)
        try:
            loader.load_module_from_source(src, module_name=path, base_dir=td)
        except LangSyntaxError as e:
            return e
    raise AssertionError("expected LangSyntaxError but none was raised")


class ImportNestingTests(unittest.TestCase):

    # ── error cases ───────────────────────────────────────────────────────────

    def test_import_inside_function_body_raises(self):
        """#32 BUG-031: import inside a function body must fail at compile time."""
        err = _expect_error("""
fn greet() {
    import "nonexistent"
    print("hi")
}
""")
        self.assertIn("top level", err.args[0])

    def test_import_inside_if_then_branch_raises(self):
        """#52: import inside if-body must fail at compile time."""
        err = _expect_error("""
let x = 1
if (x == 1) {
    import "nonexistent"
}
""")
        self.assertIn("top level", err.args[0])

    def test_import_inside_if_else_branch_raises(self):
        """#52: import inside else-body must fail at compile time."""
        err = _expect_error("""
let x = 0
if (x == 1) {
    let a = 1
} else {
    import "nonexistent"
}
""")
        self.assertIn("top level", err.args[0])

    def test_import_inside_try_block_raises(self):
        """#43 BUG-042: import inside try block must fail at compile time."""
        err = _expect_error("""
try {
    import "nonexistent"
} catch e {
    print(e)
}
""")
        self.assertIn("top level", err.args[0])

    def test_import_inside_catch_block_raises(self):
        """#43 BUG-042: import inside catch block must fail at compile time."""
        err = _expect_error("""
try {
    let x = 1
} catch e {
    import "nonexistent"
}
""")
        self.assertIn("top level", err.args[0])

    def test_import_inside_for_loop_raises(self):
        err = _expect_error("""
for (let i = 0; i < 3; i = i + 1) {
    import "nonexistent"
}
""")
        self.assertIn("top level", err.args[0])

    def test_import_inside_foreach_raises(self):
        err = _expect_error("""
for item in [1, 2, 3] {
    import "nonexistent"
}
""")
        self.assertIn("top level", err.args[0])

    def test_import_inside_nested_function_raises(self):
        """Nested function inside a top-level function — still not at module root."""
        err = _expect_error("""
fn outer() {
    fn inner() {
        import "nonexistent"
    }
}
""")
        self.assertIn("top level", err.args[0])

    def test_error_names_move_to_top(self):
        """Error message must tell the user what to do."""
        err = _expect_error('fn f() { import "x" }')
        self.assertIn("top of the file", err.args[0])

    # ── regression: top-level imports still work ──────────────────────────────

    def test_top_level_import_still_works(self):
        """Top-level imports must not be broken by the nested-import guard."""
        with tempfile.TemporaryDirectory() as td:
            mod_path = os.path.join(td, "greet.nd")
            with open(mod_path, "w", encoding="utf-8") as f:
                f.write('export let hello = "hi"\n')
            src = 'import { hello } from "./greet"\nprint(hello)\n'
            main_path = os.path.join(td, "main.nd")
            vm = VM([], {}, code_locs=[], source_path=main_path)
            loader = ModuleLoader(project_root=None, vm=vm)
            import io
            from contextlib import redirect_stdout
            buf = io.StringIO()
            with redirect_stdout(buf):
                loader.load_module_from_source(src, module_name=main_path, base_dir=td)
            self.assertEqual(buf.getvalue().strip(), "hi")

    def test_top_level_import_alias_still_works(self):
        """Aliased top-level import must continue to work."""
        with tempfile.TemporaryDirectory() as td:
            mod_path = os.path.join(td, "util.nd")
            with open(mod_path, "w", encoding="utf-8") as f:
                f.write('export let val = 42\n')
            src = 'import "./util" as u\nprint(u.val)\n'
            main_path = os.path.join(td, "main.nd")
            vm = VM([], {}, code_locs=[], source_path=main_path)
            loader = ModuleLoader(project_root=None, vm=vm)
            import io
            from contextlib import redirect_stdout
            buf = io.StringIO()
            with redirect_stdout(buf):
                loader.load_module_from_source(src, module_name=main_path, base_dir=td)
            self.assertEqual(buf.getvalue().strip(), "42.0")


if __name__ == "__main__":
    unittest.main()
