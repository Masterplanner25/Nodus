import unittest

import nodus as lang
from nodus.runtime.module_loader import ModuleLoader


class ScopeTests(unittest.TestCase):
    def test_block_scope_does_not_leak(self):
        src = """
if (true) {
    let x = 1
}
print(x)
"""
        with self.assertRaises(lang.LangSyntaxError) as cm:
            _loader = ModuleLoader(project_root=None)
            _loader.compile_only(src, module_name="main.nd")
        self.assertIn("Undefined variable: x", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
