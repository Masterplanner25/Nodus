import io
import unittest
from contextlib import redirect_stdout

import nodus as lang
from nodus.runtime.module_loader import ModuleLoader


def run_program(src: str, source_path: str | None = None):
    _loader = ModuleLoader(project_root=None)
    code, functions, code_locs = _loader.compile_only(
        src,
        module_name=source_path or "<memory>",
    )
    vm = lang.VM(code, functions, code_locs=code_locs, source_path=source_path)
    buf = io.StringIO()
    with redirect_stdout(buf):
        vm.run()
    return buf.getvalue().splitlines()


class VmErrorWrappingTests(unittest.TestCase):
    def test_python_type_error_wrapped(self):
        src = '"a" - 1'
        with self.assertRaises(lang.LangRuntimeError) as cm:
            run_program(src, source_path="main.nd")
        self.assertEqual(cm.exception.kind, "type")
        self.assertIsNotNone(cm.exception.line)
        self.assertIn("Cannot subtract", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
