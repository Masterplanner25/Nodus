import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout

import nodus as lang
from nodus.runtime.module_loader import ModuleLoader


def run_program(src: str, source_path: str | None = None) -> list[str]:
    vm = lang.VM([], {}, code_locs=[], source_path=source_path)
    _loader = ModuleLoader(project_root=None, vm=vm)
    buf = io.StringIO()
    with redirect_stdout(buf):
        _loader.load_module_from_source(src, module_name=source_path or "<memory>")
    return buf.getvalue().splitlines()


class StdlibTests(unittest.TestCase):
    def test_std_strings(self):
        src = """
import "std:strings" as s
print(s.upper("hello"))
print(s.lower("HELLO"))
print(s.trim("  hi  "))
print(s.split("a,b,c", ","))
print(s.join(["x", "y"], "-"))
print(s.contains("hello", "ell"))
"""
        self.assertEqual(
            run_program(src, source_path="main.nd"),
            ["HELLO", "hello", "hi", "[\"a\", \"b\", \"c\"]", "x-y", "true"],
        )

    def test_std_collections(self):
        src = """
import "std:collections" as c
let nums = [1, 2, 3]
print(c.len(nums))
print(c.map(nums, fn(x) { return x * 2 }))
print(c.filter(nums, fn(x) { return x > 1 }))
print(c.reduce(nums, fn(acc, x) { return acc + x }, 0))
print(c.push(nums, 4))
print(c.pop(nums))
print(nums)
"""
        self.assertEqual(
            run_program(src, source_path="main.nd"),
            ["3.0", "[2.0, 4.0, 6.0]", "[2.0, 3.0]", "6.0", "[1.0, 2.0, 3.0, 4.0]", "4.0", "[1.0, 2.0, 3.0]"],
        )

    def test_std_json(self):
        src = """
import "std:json" as j
let obj = j.parse("{\\"x\\":1,\\"name\\":\\"Alice\\",\\"tags\\":[1,2]}")
print(obj.x)
print(obj.name)
print(j.stringify(obj))
"""
        self.assertEqual(
            run_program(src, source_path="main.nd"),
            ["1.0", "Alice", "{\"x\": 1, \"name\": \"Alice\", \"tags\": [1, 2]}"],
        )

    def test_std_math(self):
        src = """
import "std:math" as m
print(m.abs(-4))
print(m.min(2, 5))
print(m.max(2, 5))
print(m.floor(2.9))
print(m.ceil(2.1))
print(m.sqrt(9))
print(type(m.random()))
"""
        self.assertEqual(
            run_program(src, source_path="main.nd"),
            ["4.0", "2.0", "5.0", "2.0", "3.0", "3.0", "number"],
        )

    def test_std_fs(self):
        with tempfile.TemporaryDirectory() as td:
            td_norm = td.replace("\\", "/")
            file_path = os.path.join(td_norm, "note.txt").replace("\\", "/")
            src = f"""
import "std:fs" as fs
fs.write("{file_path}", "hello")
print(fs.read("{file_path}"))
print(fs.exists("{file_path}"))
print(fs.listdir("{td_norm}"))
"""
            self.assertEqual(
                run_program(src, source_path="main.nd"),
                ["hello", "true", "[\"note.txt\"]"],
            )


if __name__ == "__main__":
    unittest.main()
