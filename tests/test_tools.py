import json
import unittest

from nodus.tools import nodus_execute, nodus_check, nodus_ast, nodus_dis


class ToolWrapperTests(unittest.TestCase):
    def test_execute_tool(self):
        result = nodus_execute("print(2)", filename="inline.nd")
        self.assertTrue(result["ok"])
        self.assertEqual(result["stage"], "execute")
        self.assertEqual(result["stdout"], "2.0\n")
        json.dumps(result)

    def test_check_tool(self):
        result = nodus_check("let x = 1", filename="inline.nd")
        self.assertTrue(result["ok"])
        self.assertEqual(result["stage"], "check")
        json.dumps(result)

    def test_ast_tool(self):
        result = nodus_ast("let x = 1", filename="inline.nd")
        self.assertTrue(result["ok"])
        self.assertEqual(result["stage"], "ast")
        self.assertIn("ast", result)
        json.dumps(result)

    def test_dis_tool(self):
        result = nodus_dis("print(1)", filename="inline.nd")
        self.assertTrue(result["ok"])
        self.assertEqual(result["stage"], "disassemble")
        self.assertIn("dis", result)
        json.dumps(result)


if __name__ == "__main__":
    unittest.main()
