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


if __name__ == "__main__":
    unittest.main()
