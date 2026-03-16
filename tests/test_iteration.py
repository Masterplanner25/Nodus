import io
import unittest
from contextlib import redirect_stdout

import nodus as lang
from nodus.runtime.module_loader import ModuleLoader


def run_program(src: str, source_path: str | None = None) -> list[str]:
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


class CoroutineIterationTests(unittest.TestCase):
    def test_coroutine_iteration_suspend_resume(self):
        """Iterator object on stack survives coroutine suspend/resume cycles."""
        src = """
fn worker() {
    for n in [10, 20, 30] {
        yield n
    }
}

let c = coroutine(worker)
print(resume(c))
print(resume(c))
print(resume(c))
print(coroutine_status(c))
"""
        self.assertEqual(
            run_program(src, source_path="main.nd"),
            ["10.0", "20.0", "30.0", "suspended"],
        )

    def test_coroutine_custom_iterator_suspend_resume(self):
        """Custom record iterator advance_fn survives coroutine suspend/resume cycles."""
        src = """
fn worker() {
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
        yield n
    }
}

let c = coroutine(worker)
print(resume(c))
print(resume(c))
print(coroutine_status(c))
"""
        self.assertEqual(
            run_program(src, source_path="main.nd"),
            ["1.0", "2.0", "suspended"],
        )


if __name__ == "__main__":
    unittest.main()
