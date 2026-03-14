import io
import unittest
from contextlib import redirect_stdout

import nodus as lang


def run_program(src: str, source_path: str | None = None) -> list[str]:
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


class IterationTests(unittest.TestCase):
    def test_array_iteration(self):
        src = """
let nums = [1, 2, 3]
for n in nums {
    print(n)
}
"""
        self.assertEqual(run_program(src), ["1.0", "2.0", "3.0"])

    def test_nested_iteration(self):
        src = """
let nums = [1, 2]
for a in nums {
    for b in nums {
        print(a + b)
    }
}
"""
        self.assertEqual(run_program(src), ["2.0", "3.0", "3.0", "4.0"])

    def test_empty_iteration(self):
        src = """
let nums = []
for n in nums {
    print(n)
}
"""
        self.assertEqual(run_program(src), [])

    def test_record_iterator(self):
        src = """
let iter = record {
    data: [1, 2],
    index: 0,
    __iter__: fn(self) { return self },
    __next__: fn(self) {
        if (self.index >= len(self.data)) {
            return nil
        }
        let v = self.data[self.index]
        self.index = self.index + 1
        return v
    }
}
for n in iter {
    print(n)
}
"""
        self.assertEqual(run_program(src), ["1.0", "2.0"])


if __name__ == "__main__":
    unittest.main()
