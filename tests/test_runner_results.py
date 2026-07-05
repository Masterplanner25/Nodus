import unittest

from nodus.tooling.runner import run_source, check_source, build_ast, disassemble_source


class RunnerResultTests(unittest.TestCase):
    def assert_base_fields(self, result: dict):
        for key in ["ok", "stdout", "stderr", "result", "error", "errors", "diagnostics", "stage", "filename"]:
            self.assertIn(key, result)

    def test_run_source_success_format(self):
        result, _vm = run_source("print(1)", filename="inline.nd")
        self.assert_base_fields(result)
        self.assertTrue(result["ok"])
        self.assertEqual(result["stage"], "execute")
        self.assertEqual(result["stdout"], "1.0\n")
        self.assertEqual(result["errors"], [])
        self.assertIsNone(result["error"])

    def test_run_source_error_format(self):
        result, _vm = run_source("fn {", filename="inline.nd")
        self.assert_base_fields(result)
        self.assertFalse(result["ok"])
        self.assertIn(result["stage"], {"parse", "compile"})
        self.assertTrue(result["errors"])
        self.assertEqual(result["error"]["type"], "syntax")
        self.assertEqual(result["errors"][0]["type"], "SyntaxError")

    def test_check_source_format(self):
        result = check_source("print(2)", filename="inline.nd")
        self.assert_base_fields(result)
        self.assertTrue(result["ok"])
        self.assertEqual(result["stage"], "check")

    def test_build_ast_format(self):
        result = build_ast("let x = 1", filename="inline.nd")
        self.assert_base_fields(result)
        self.assertTrue(result["ok"])
        self.assertIn("Module", result.get("ast_pretty", ""))

    def test_disassemble_format(self):
        result = disassemble_source("print(1)", filename="inline.nd")
        self.assert_base_fields(result)
        self.assertTrue(result["ok"])
        self.assertIn("CALL print", result.get("disassembly", ""))

    def test_parse_error_carries_snippet_with_caret(self):
        result = check_source("let x = ", filename="inline.nd")
        self.assertFalse(result["ok"])
        err = result["errors"][0]
        self.assertIn("snippet", err)
        # source line + caret line pointing at the reported column (1-based)
        line_text, caret = err["snippet"].split("\n")
        self.assertEqual(line_text, "let x = ")
        self.assertEqual(caret.index("^"), err["column"] - 1)

    def test_runtime_error_carries_snippet_on_offending_line(self):
        result, _vm = run_source("let a = 5\nlet b = a + (10 / 0)", filename="inline.nd")
        self.assertFalse(result["ok"])
        err = result["errors"][0]
        line_text, caret = err["snippet"].split("\n")
        self.assertEqual(line_text, "let b = a + (10 / 0)")
        self.assertEqual(caret.index("^"), err["column"] - 1)

    def test_success_result_has_no_error_snippet(self):
        result, _vm = run_source("print(1)", filename="inline.nd")
        self.assertTrue(result["ok"])
        self.assertEqual(result["errors"], [])


if __name__ == "__main__":
    unittest.main()
