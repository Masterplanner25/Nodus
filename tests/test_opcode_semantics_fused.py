"""Semantic spec for the fused instructions (#969).

Each fused instruction is *defined* as the stable sequence it replaces, so each
spec here runs that sequence on one VM and the fused instruction on another,
from identical state, and requires the same outcome: the same stack, the same
locals, the same branch, or the same error kind and message.

The optimizer emits these; the compiler never does. The last classes check the
optimizer's side: where it may fuse, and that whole programs behave the same
with and without it.
"""

import sys
import unittest

sys.path.insert(0, "C:/dev/Coding Language/src")

from nodus.compiler.optimizer import fuse_instructions  # noqa: E402
from nodus.runtime.diagnostics import LangRuntimeError  # noqa: E402
from nodus.runtime.embedding import NodusRuntime  # noqa: E402
from nodus.runtime.module import LiveBinding, NodusModule  # noqa: E402
from nodus.vm.types import Cell, Frame, Record  # noqa: E402
from nodus.vm.vm import VM  # noqa: E402

SPECIFIED = (
    "LOAD_LOCAL_FIELD",
    "JUMP_IF_LOCAL_NE_CONST",
    "ENTER",
)


def vm_with_locals(values, *, stack=(), slots=None) -> VM:
    vm = VM([], {}, code_locs=[], source_path=None)
    frame = Frame(return_ip=0, locals={}, fn_name="f", call_line=None, call_col=None,
                  call_path=None, closure=None)
    frame.locals_array = list(values)
    frame.locals_name_to_slot = slots
    vm.frames = [frame]
    vm.stack = list(stack)
    vm.ip = 0
    return vm


def outcome(vm: VM, instrs) -> tuple:
    """Run `instrs` in order from ip 0; report the state or the error."""
    try:
        for instr in instrs:
            vm._dispatch[instr[0]](instr)
    except LangRuntimeError as err:
        return ("error", err.kind, str(err).split("\n")[0])
    frame = vm.frames[-1]
    return ("ok", list(vm.stack), list(frame.locals_array or []), dict(frame.locals), vm.ip)


def module_with(**exports) -> NodusModule:
    """A minimal module, as `test_opcode_semantics_core.module_with` builds one."""
    return NodusModule(name="m", path="<test>", bytecode=[], functions={}, code_locs=[],
                       globals=dict(exports), exports=dict(exports))


class LoadLocalField(unittest.TestCase):
    def cases(self):
        rec = Record({"tok": "ID", "n": 1})
        return {
            "record": rec,
            "a record in a cell": Cell(rec),
            "a missing field": Record({"other": 1}),
            "a map": {"tok": "ID"},
            "nil": None,
            "a string": "tok",
            "a module export": module_with(tok="from module"),
            "a module without the export": module_with(other=1),
        }

    def test_same_as_load_local_idx_then_load_field(self):
        for name, value in self.cases().items():
            with self.subTest(case=name):
                seq = outcome(vm_with_locals([value]),
                              [("LOAD_LOCAL_IDX", 0), ("LOAD_FIELD", "tok")])
                fused = outcome(vm_with_locals([value]), [("LOAD_LOCAL_FIELD", 0, "tok")])
                if seq[0] == "ok":
                    # The sequence advanced ip twice, the fused instruction once.
                    self.assertEqual(seq[:4], fused[:4])
                    self.assertEqual((seq[4], fused[4]), (2, 1))
                else:
                    self.assertEqual(seq, fused)

    def test_a_live_binding(self):
        binding = LiveBinding.__new__(LiveBinding)
        binding.get = lambda: Record({"tok": "STR"})  # type: ignore[method-assign]
        fused = outcome(vm_with_locals([binding]), [("LOAD_LOCAL_FIELD", 0, "tok")])
        self.assertEqual(fused[1], ["STR"])


class JumpIfLocalNeConst(unittest.TestCase):
    PAIRS = [("ID", "ID"), ("ID", "STR"), (1, 1.0), (1, True), (True, True),
             (None, None), ("1", 1), (2 ** 53 + 1, 2 ** 53), ("", ""), (0, False)]

    def test_same_branch_as_the_four_instruction_sequence(self):
        for value, const in self.PAIRS:
            for wrap in (False, True):
                local = Cell(value) if wrap else value
                with self.subTest(value=value, const=const, cell=wrap):
                    seq_vm = vm_with_locals([local])
                    outcome(seq_vm, [("LOAD_LOCAL_IDX", 0), ("PUSH_CONST", const), ("EQ",)])
                    # Run the JUMP_IF_FALSE from its own address, 3.
                    seq_vm.ip = 3
                    seq_vm._dispatch["JUMP_IF_FALSE"](("JUMP_IF_FALSE", 99))
                    seq_jumped = seq_vm.ip == 99

                    fused_vm = vm_with_locals([local])
                    fused_vm._dispatch["JUMP_IF_LOCAL_NE_CONST"](
                        ("JUMP_IF_LOCAL_NE_CONST", 0, const, 99))
                    fused_jumped = fused_vm.ip == 99

                    self.assertEqual(fused_jumped, seq_jumped)
                    self.assertEqual(fused_vm.stack, seq_vm.stack)
                    if not fused_jumped:
                        self.assertEqual(fused_vm.ip, 1)


class Enter(unittest.TestCase):
    def test_same_as_frame_size_then_store_args(self):
        slots = {"a": 0, "b": 1}
        seq = outcome(vm_with_locals([], stack=["x", 10, 20], slots=slots),
                      [("FRAME_SIZE", 3), ("STORE_ARG", "b"), ("STORE_ARG", "a")])
        fused = outcome(vm_with_locals([], stack=["x", 10, 20], slots=slots),
                        [("ENTER", 3, ("a", "b"))])
        self.assertEqual(seq[:4], fused[:4])
        self.assertEqual(fused[1], ["x"])
        self.assertEqual(fused[2], [10, 20, None])

    def test_a_parameter_whose_slot_a_later_local_shares_a_name_with(self):
        # #949: the slot map says where a parameter lives; ENTER uses it as STORE_ARG does.
        slots = {"text": 0, "other": 1}
        seq = outcome(vm_with_locals([], stack=["v"], slots=slots),
                      [("FRAME_SIZE", 2), ("STORE_ARG", "text")])
        fused = outcome(vm_with_locals([], stack=["v"], slots=slots),
                        [("ENTER", 2, ("text",))])
        self.assertEqual(seq[:4], fused[:4])

    def test_too_few_arguments_underflow_the_same_way(self):
        seq = outcome(vm_with_locals([], stack=[1], slots={"a": 0, "b": 1}),
                      [("FRAME_SIZE", 2), ("STORE_ARG", "b"), ("STORE_ARG", "a")])
        fused = outcome(vm_with_locals([], stack=[1], slots={"a": 0, "b": 1}),
                        [("ENTER", 2, ("a", "b"))])
        self.assertEqual(seq[0], "error")
        self.assertEqual(seq, fused)


class WhereTheOptimizerFuses(unittest.TestCase):
    LOCS = [(None, None, None)] * 8

    def test_the_four_instruction_compare(self):
        code = [("LOAD_LOCAL_IDX", 0), ("PUSH_CONST", "ID"), ("EQ",), ("JUMP_IF_FALSE", 6),
                ("PUSH_CONST", 1), ("POP",), ("HALT",)]
        out, _, _ = fuse_instructions(code, {}, self.LOCS[:7])
        self.assertEqual(out[0], ("JUMP_IF_LOCAL_NE_CONST", 0, "ID", 3))
        self.assertEqual(out[3], ("HALT",))

    def test_not_across_a_jump_target(self):
        # Something jumps to the EQ, so the sequence is not one unit.
        code = [("LOAD_LOCAL_IDX", 0), ("PUSH_CONST", "ID"), ("EQ",), ("JUMP_IF_FALSE", 6),
                ("JUMP", 2), ("POP",), ("HALT",)]
        out, _, _ = fuse_instructions(code, {}, self.LOCS[:7])
        self.assertNotIn("JUMP_IF_LOCAL_NE_CONST", [i[0] for i in out])

    def test_the_first_instruction_may_be_a_jump_target(self):
        code = [("JUMP", 1), ("LOAD_LOCAL_IDX", 0), ("LOAD_FIELD", "tok"), ("POP",), ("HALT",)]
        out, _, _ = fuse_instructions(code, {}, self.LOCS[:5])
        self.assertEqual(out[0], ("JUMP", 1))
        self.assertEqual(out[1], ("LOAD_LOCAL_FIELD", 0, "tok"))

    def test_a_function_without_parameters_keeps_frame_size(self):
        code = [("FRAME_SIZE", 2), ("PUSH_CONST", None), ("RETURN",)]
        out, _, _ = fuse_instructions(code, {}, self.LOCS[:3])
        self.assertEqual(out[0], ("FRAME_SIZE", 2))


class WholeProgramsWithAndWithout(unittest.TestCase):
    PROGRAMS = {
        "token dispatch": (
            'fn kind_of(t) {\n'
            '    if (t.kind == "ID") { return "name" }\n'
            '    if (t.kind == "NUM") { return "number" }\n'
            '    let k = t.kind\n'
            '    if (k == "(") { return "paren" }\n'
            '    return "other"\n'
            '}\n'
            'for k in ["ID", "NUM", "(", "x"] { print(kind_of(record { kind: k })) }\n'
        ),
        "numeric equality across int and float": (
            "fn same(n) {\n"
            "    let v = n\n"
            "    if (v == 1.0) { return \"one\" }\n"
            "    return \"not one\"\n"
            "}\n"
            "print(same(1i))\nprint(same(2i))\nprint(same(true))\n"
        ),
        "a missing field is the same error": (
            "fn f(r) {\n    let x = r\n    return x.missing\n}\nprint(f(record { a: 1i }))\n"
        ),
        "a field read on a map is the same error": (
            'fn f(m) {\n    let x = m\n    return x.a\n}\nprint(f({"a": 1i}))\n'
        ),
        "loops and closures": (
            "fn f(xs) {\n"
            "    let out = []\n"
            "    for x in xs {\n"
            "        if (x == 2i) { continue }\n"
            "        push(out, fn() { return x * 10i })\n"
            "    }\n"
            "    return out\n"
            "}\n"
            "for g in f([1i, 2i, 3i]) { print(g()) }\n"
        ),
    }

    def run_both(self, src):
        results = []
        for optimize in (False, True):
            r = NodusRuntime(timeout_ms=None).run_source(src, optimize=optimize)
            err = r.get("error") or {}
            results.append((r.get("ok"), r.get("stdout"), err.get("kind") or err.get("type"),
                            err.get("message"), err.get("line")))
        return results

    # closes: #969
    def test_every_program(self):
        for name, src in self.PROGRAMS.items():
            with self.subTest(program=name):
                plain, optimized = self.run_both(src)
                self.assertEqual(optimized, plain)

    def test_the_fused_instructions_are_really_used(self):
        from nodus.runtime.module_loader import ModuleLoader
        src = self.PROGRAMS["token dispatch"]
        code, _f, _l = ModuleLoader(project_root=None).compile_only(src, module_name="m.nd", optimize=True)
        ops = {instr[0] for instr in code["instructions"]}
        self.assertTrue({"LOAD_LOCAL_FIELD", "JUMP_IF_LOCAL_NE_CONST", "ENTER"} <= ops, ops)
        code, _f, _l = ModuleLoader(project_root=None).compile_only(src, module_name="m.nd", optimize=False)
        ops = {instr[0] for instr in code["instructions"]}
        self.assertFalse({"LOAD_LOCAL_FIELD", "JUMP_IF_LOCAL_NE_CONST", "ENTER"} & ops, ops)


if __name__ == "__main__":
    unittest.main()
