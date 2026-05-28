"""Closed-issue test for #78: err records carry location fields (Doc 13)."""

import sys
import io
from contextlib import redirect_stdout

sys.path.insert(0, "C:/dev/Coding Language/src")

import nodus
from nodus.runtime.module_loader import ModuleLoader


def _run(src):
    vm = nodus.VM([], {}, code_locs=[], source_path="test.nd")
    buf = io.StringIO()
    with redirect_stdout(buf):
        loader = ModuleLoader(project_root=None, vm=vm)
        loader.load_module_from_source(src, module_name="test.nd")
    return buf.getvalue().splitlines()


def test_err_record_has_path_field():
    lines = _run(
        'import "std:env" as env\n'
        'let e = env.set("=bad_name", "value")\n'
        'print(type(e))\n'
        'print(e.path != nil)'
    )
    assert lines[0] == "error", f"expected error, got {lines[0]}"
    assert lines[1] == "true", f"expected path != nil, got {lines[1]}"


def test_err_record_has_line_field():
    lines = _run(
        'import "std:env" as env\n'
        'let e = env.set("=bad_name", "value")\n'
        'print(e.line != nil)'
    )
    assert lines[0] == "true", f"expected line != nil, got {lines[0]}"


def test_err_record_has_origin_field():
    lines = _run(
        'import "std:env" as env\n'
        'let e = env.set("=bad_name", "value")\n'
        'print(e.origin)'
    )
    assert lines[0] == "stdlib", f"expected 'stdlib', got {lines[0]}"


def test_err_record_has_stack_field():
    lines = _run(
        'import "std:env" as env\n'
        'let e = env.set("=bad_name", "value")\n'
        'print(type(e.stack))'
    )
    assert lines[0] == "list", f"expected list, got {lines[0]}"


if __name__ == "__main__":
    test_err_record_has_path_field()
    test_err_record_has_line_field()
    test_err_record_has_origin_field()
    test_err_record_has_stack_field()
    print("All #78 tests pass")
