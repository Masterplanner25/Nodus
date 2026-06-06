"""v3.0.1 Commit 4 tests — Polish, deprecations, and design-item capture.

Covers:
- BUG-E11: Lexer gives specific error for non-ASCII identifiers (#63)
- BUG-E12: Uppercase 'I' integer suffix produces parse error, not name error (#64)
- BUG-E14: Deprecated top-level run_source emits DeprecationWarning (#66)
- BUG-E16: Import path resolution error message doesn't double .nd extension (#68)
"""

import os
import sys
import tempfile
import unittest
import warnings


PYTHONPATH = os.path.join(os.path.dirname(__file__), "..", "src")
if PYTHONPATH not in sys.path:
    sys.path.insert(0, PYTHONPATH)

from nodus import NodusRuntime  # noqa: E402
from nodus.runtime.diagnostics import LangSyntaxError  # noqa: E402
from nodus.frontend.lexer import tokenize  # noqa: E402


class NonAsciiIdentifierTests(unittest.TestCase):
    """BUG-E11: Non-ASCII identifier characters produce a helpful error message."""

    def _parse_err(self, src):
        rt = NodusRuntime()
        return rt.run_source(src)

    def test_non_ascii_letter_error_message(self):
        rt = NodusRuntime()
        result = rt.run_source("let café = 1")
        self.assertFalse(result["ok"])
        err_text = str(result.get("error", ""))
        self.assertIn("ASCII", err_text)

    def test_non_ascii_raises_syntax_error(self):
        with self.assertRaises(LangSyntaxError) as ctx:
            tokenize("let é = 1")
        self.assertIn("ASCII", str(ctx.exception))

    def test_non_ascii_greek_raises_syntax_error(self):
        with self.assertRaises(LangSyntaxError) as ctx:
            tokenize("let α = 1")
        self.assertIn("ASCII", str(ctx.exception))

    def test_non_ascii_cjk_raises_syntax_error(self):
        with self.assertRaises(LangSyntaxError) as ctx:
            tokenize("let 中 = 1")
        self.assertIn("ASCII", str(ctx.exception))

    def test_ascii_identifier_still_works(self):
        rt = NodusRuntime()
        result = rt.run_source("let x = 42\nprint(x)")
        self.assertTrue(result["ok"])
        self.assertIn("42", result["stdout"])

    def test_unexpected_symbol_still_generic_message(self):
        # Use ~ which is not a valid Nodus token (@ is now valid — annotation syntax).
        with self.assertRaises(LangSyntaxError) as ctx:
            tokenize("let x = ~")
        msg = str(ctx.exception)
        self.assertIn("Unexpected character", msg)
        self.assertNotIn("ASCII", msg)


class UppercaseIntegerSuffixTests(unittest.TestCase):
    """BUG-E12: 1I (uppercase I suffix) gives parse error, not a confusing name error."""

    def test_uppercase_I_suffix_raises_syntax_error(self):
        with self.assertRaises(LangSyntaxError) as ctx:
            tokenize("let x = 1I")
        msg = str(ctx.exception)
        self.assertIn("lowercase", msg)

    def test_uppercase_I_suffix_hints_at_lowercase(self):
        with self.assertRaises(LangSyntaxError) as ctx:
            tokenize("42I")
        msg = str(ctx.exception)
        self.assertIn("42i", msg)

    def test_lowercase_i_suffix_still_works(self):
        tokens = tokenize("42i")
        int_toks = [t for t in tokens if t.kind == "NUM_INT"]
        self.assertEqual(len(int_toks), 1)
        self.assertEqual(int_toks[0].val, "42")


class DeprecatedRunSourceTests(unittest.TestCase):
    """BUG-E14: tooling.loader.run_source() emits DeprecationWarning."""

    def test_run_source_emits_deprecation_warning(self):
        from nodus.tooling.loader import run_source
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            run_source("let x = 1")
        dep_warnings = [w for w in caught if issubclass(w.category, DeprecationWarning)]
        self.assertTrue(
            len(dep_warnings) >= 1,
            f"Expected DeprecationWarning, got: {[str(w.message) for w in caught]}"
        )

    def test_run_source_warning_message_mentions_NodusRuntime(self):
        from nodus.tooling.loader import run_source
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            run_source("let x = 1")
        dep_warnings = [w for w in caught if issubclass(w.category, DeprecationWarning)]
        self.assertTrue(len(dep_warnings) >= 1)
        self.assertIn("NodusRuntime", str(dep_warnings[0].message))

    def test_run_source_still_executes(self):
        from nodus.tooling.loader import run_source
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            vm = run_source("let x = 42")
        self.assertIsNotNone(vm)


class ImportExtensionDoubleTests(unittest.TestCase):
    """BUG-E16: import 'module.nd' error message shows .nd once, not .nd.nd."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _run(self, source, project_root=None):
        rt = NodusRuntime(project_root=project_root or self._tmpdir)
        return rt.run_source(source)

    def test_import_missing_module_no_extension(self):
        result = self._run('import "missing_module" as m')
        self.assertFalse(result["ok"])
        err_text = str(result.get("error", ""))
        self.assertNotIn("missing_module.nd.nd", err_text)

    def test_import_missing_module_with_nd_extension_no_doubling(self):
        result = self._run('import "missing_module.nd" as m')
        self.assertFalse(result["ok"])
        err_text = str(result.get("error", ""))
        self.assertNotIn("missing_module.nd.nd", err_text)

    def test_import_missing_module_with_nd_extension_shows_nd_once(self):
        result = self._run('import "logparse.nd" as m')
        self.assertFalse(result["ok"])
        err_text = str(result.get("error", ""))
        self.assertNotIn("logparse.nd.nd", err_text)

    def test_import_existing_module_with_nd_suffix_works(self):
        module_path = os.path.join(self._tmpdir, "mymodule.nd")
        with open(module_path, "w") as f:
            f.write('export fn greet() { return "hi" }\n')
        result = self._run('import "mymodule.nd" as m\nprint(m.greet())')
        self.assertTrue(result["ok"], f"Expected success, got: {result.get('error')}")
        self.assertIn("hi", result["stdout"])

    def test_import_existing_module_without_nd_suffix_works(self):
        module_path = os.path.join(self._tmpdir, "mymodule.nd")
        with open(module_path, "w") as f:
            f.write('export fn greet() { return "hi" }\n')
        result = self._run('import "mymodule" as m\nprint(m.greet())')
        self.assertTrue(result["ok"], f"Expected success, got: {result.get('error')}")
        self.assertIn("hi", result["stdout"])


if __name__ == "__main__":
    unittest.main()
