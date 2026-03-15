import io
import unittest
from contextlib import redirect_stdout

import nodus as lang


def run_program(src: str, source_path: str | None = None):
    _ast, code, functions, code_locs = lang.compile_source(
        src,
        source_path=source_path,
        import_state={"loaded": set(), "loading": set(), "exports": {}},
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
