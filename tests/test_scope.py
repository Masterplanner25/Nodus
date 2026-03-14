import unittest

import nodus as lang


class ScopeTests(unittest.TestCase):
    def test_block_scope_does_not_leak(self):
        src = """
if (true) {
    let x = 1
}
print(x)
"""
        with self.assertRaises(lang.LangSyntaxError) as cm:
            lang.compile_source(
                src,
                source_path="main.nd",
                import_state={"loaded": set(), "loading": set(), "exports": {}},
            )
        self.assertIn("Undefined variable: x", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
