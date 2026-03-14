import unittest

from nodus.tooling.runner import build_ast


class AstSerializationTests(unittest.TestCase):
    def test_ast_dict_structure(self):
        result = build_ast("let x = 1", filename="inline.nd")
        self.assertTrue(result["ok"])
        self.assertIn("ast", result)
        ast = result["ast"]
        self.assertIsInstance(ast, list)
        self.assertTrue(ast)
        let_node = ast[0]
        self.assertEqual(let_node["type"], "Let")
        self.assertEqual(let_node["name"], "x")
        expr = let_node["expr"]
        self.assertEqual(expr["type"], "Num")
        self.assertEqual(expr["v"], 1.0)


if __name__ == "__main__":
    unittest.main()
