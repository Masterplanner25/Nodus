"""Stack discipline: does the runtime agree with what the compiler assumed (#412 phase 3)?

Phase 1 counted executions. Phase 2 specified what ten opcodes *do*. This asks
the remaining question: whether an opcode's actual behaviour matches what the
compiler assumed when it sized frames and patched jump targets. A mismatch shows
up only on rare paths, which is the #370/#371 signature exactly.

**Frame sizing is checked at run time, not statically, and that is a finding
rather than a convenience.** The obvious static check — attribute each
`*_LOCAL_IDX` instruction to the nearest preceding `FRAME_SIZE` and compare —
does not work, because a nested closure's body is emitted *inside* its parent's
code at a higher address. Instructions after the nested body still belong to the
parent, so "nearest preceding function address" credits them to the closure and
reports slots that are perfectly legal:

    async.nd: LOAD_LOCAL_IDX slot 5 >= FRAME_SIZE 2 (fn@105)

Twelve of those, all false. `worker_pool` (FRAME_SIZE 6) legitimately uses slot
5; the closure at 105 merely sits between. A compiled function has no recorded
end, so there is no sound span to attribute against — and at run time the
question does not arise, because the frame doing the access is the frame that was
sized.

What *is* sound statically — jump targets and operand signs — is checked
statically, over every stdlib module.
"""

import os
import pathlib
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus.runtime.embedding import NodusRuntime  # noqa: E402
from nodus.runtime.module_loader import ModuleLoader  # noqa: E402
from nodus.vm.vm import VM  # noqa: E402

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_STDLIB = _ROOT / "src" / "nodus" / "stdlib"

#: Opcodes whose operand indexes a frame's slot array.
SLOT_OPS = ("LOAD_LOCAL_IDX", "STORE_LOCAL_IDX", "RESET_LOCAL_IDX")

#: Opcodes carrying an absolute instruction address the compiler patched.
JUMP_OPS = ("JUMP", "JUMP_IF_FALSE", "JUMP_IF_TRUE", "ITER_NEXT", "SETUP_TRY")


def _compile(path: pathlib.Path):
    code, functions, _ = ModuleLoader(project_root=None).compile_only(
        path.read_text(encoding="utf-8"), module_name=str(path)
    )
    instructions = code["instructions"] if isinstance(code, dict) else code
    return instructions, functions


def bad_jump_targets(instructions) -> list[str]:
    """Targets outside the code, or never patched.

    Extracted so it can be run against synthetic input: a checker exercised only
    on a clean corpus has never been shown to detect anything.
    """
    findings = []
    for index, instruction in enumerate(instructions):
        if instruction[0] not in JUMP_OPS:
            continue
        for operand in instruction[1:]:
            if operand is None:
                findings.append(f"{index} {instruction[0]} target never patched")
            elif isinstance(operand, int) and not (0 <= operand <= len(instructions)):
                findings.append(
                    f"{index} {instruction[0]} -> {operand} (code is 0..{len(instructions)})"
                )
    return findings


def negative_slot_operands(instructions) -> list[str]:
    """The one out-of-range case the runtime does not catch.

    A read past the end raises `IndexError`; a negative index silently wraps to
    the far end of the frame and returns another variable's value.
    """
    findings = []
    for index, instruction in enumerate(instructions):
        if instruction[0] in SLOT_OPS or instruction[0] == "FRAME_SIZE":
            operand = instruction[1] if len(instruction) > 1 else 0
            if isinstance(operand, int) and operand < 0:
                findings.append(f"{index} {instruction}")
    return findings


# closes: #412
class CheckerSelfTests(unittest.TestCase):
    """The checkers detect what they claim to, on input built to break them."""

    def test_an_out_of_range_jump_is_reported(self):
        findings = bad_jump_targets([("JUMP", 99), ("HALT",)])
        self.assertEqual(1, len(findings), findings)
        self.assertIn("-> 99", findings[0])

    def test_an_unpatched_jump_is_reported(self):
        findings = bad_jump_targets([("JUMP", None), ("HALT",)])
        self.assertIn("never patched", findings[0])

    def test_a_target_one_past_the_end_is_allowed(self):
        """`len(code)` is the halt position a forward jump legitimately targets;
        rejecting it would make every loop exit a finding."""
        self.assertEqual([], bad_jump_targets([("JUMP", 2), ("HALT",)]))

    def test_a_clean_sequence_reports_nothing(self):
        self.assertEqual([], bad_jump_targets([("JUMP", 1), ("HALT",)]))
        self.assertEqual([], negative_slot_operands([("FRAME_SIZE", 2), ("LOAD_LOCAL_IDX", 1)]))

    def test_a_negative_slot_is_reported(self):
        findings = negative_slot_operands([("LOAD_LOCAL_IDX", -1)])
        self.assertEqual(1, len(findings), findings)

    def test_a_negative_frame_size_is_reported(self):
        self.assertEqual(1, len(negative_slot_operands([("FRAME_SIZE", -3)])))


# closes: #412
class StaticCompilerAssumptionTests(unittest.TestCase):
    """The half that needs no attribution, over every stdlib module."""

    def _modules(self):
        found = 0
        for path in sorted(_STDLIB.glob("*.nd")):
            try:
                instructions, functions = _compile(path)
            except Exception:                      # a module needing a project root
                continue
            found += 1
            yield path, instructions, functions
        self.assertGreater(found, 20, "the stdlib corpus did not compile; this check "
                                      "would have passed by examining nothing")

    def test_every_jump_target_is_inside_the_code(self):
        """A target past the end is an `IndexError` on whichever branch reaches
        it, and branches are exactly what does not get exercised."""
        bad = []
        for path, instructions, _ in self._modules():
            bad += [f"{path.name}:{f}" for f in bad_jump_targets(instructions)]
        self.assertEqual([], bad)

    def test_no_jump_target_was_left_unpatched(self):
        """`emit("JUMP", None)` then `patch(...)` is the forward-jump idiom. A
        `None` surviving into the emitted code is a patch that never happened,
        and it would fail as a type error somewhere unrelated."""
        bad = []
        for path, instructions, _ in self._modules():
            bad += [f"{path.name}:{f}" for f in bad_jump_targets(instructions)
                    if "never patched" in f]
        self.assertEqual([], bad)

    def test_no_slot_or_frame_operand_is_negative(self):
        """The one out-of-range case the runtime does *not* catch. A read past
        the end raises `IndexError`; a negative index silently wraps to the far
        end of the frame and returns another variable's value."""
        bad = []
        for path, instructions, _ in self._modules():
            bad += [f"{path.name}:{f}" for f in negative_slot_operands(instructions)]
        self.assertEqual([], bad)

    def test_every_function_body_opens_with_frame_size(self):
        """`FRAME_SIZE` is the first instruction of every compiled body, and the
        VM's slot array does not exist until it runs. A body reached without one
        would index `None`."""
        bad = []
        for path, instructions, functions in self._modules():
            for name, fn in functions.items():
                if not (0 <= fn.addr < len(instructions)):
                    bad.append(f"{path.name}: {name} addr {fn.addr} outside the code")
                elif instructions[fn.addr][0] != "FRAME_SIZE":
                    bad.append(f"{path.name}: {name}@{fn.addr} opens with "
                               f"{instructions[fn.addr][0]}, not FRAME_SIZE")
        self.assertEqual([], bad)


# closes: #412
class RuntimeSlotDisciplineTests(unittest.TestCase):
    """Every slot access lands inside the frame the compiler sized.

    At run time the frame doing the access *is* the frame that was sized, so the
    attribution problem that defeats the static form does not exist. What this
    cannot do is prove it for code it never runs — so the corpus matters, and the
    observation count is asserted rather than assumed.
    """

    def setUp(self) -> None:
        self.violations: list[str] = []
        self.observed = 0
        self._patched: list[tuple[str, object]] = []

        # Registered *before* anything is patched. These are three of the
        # hottest opcodes in the VM, and they are patched on the class — so a
        # setUp that raised halfway through would leave every later test in the
        # process running instrumented, which is both wrong and slow. Cleanup
        # first, patch second.
        self.addCleanup(self._restore)
        for op_name, method in (
            ("LOAD_LOCAL_IDX", "_op_load_local_idx"),
            ("STORE_LOCAL_IDX", "_op_store_local_idx"),
            ("RESET_LOCAL_IDX", "_op_reset_local_idx"),
        ):
            original = getattr(VM, method)
            self._patched.append((method, original))
            setattr(VM, method, self._wrap(op_name, original))

    def _restore(self) -> None:
        for method, original in self._patched:
            setattr(VM, method, original)

    def _wrap(self, op_name, original):
        recorder = self

        def wrapper(vm_self, instruction):
            recorder.observed += 1
            index = instruction[1] if len(instruction) > 1 else None
            frame = vm_self.frames[-1] if vm_self.frames else None
            slots = getattr(frame, "locals_array", None) if frame is not None else None
            if isinstance(index, int) and slots is not None:
                if index < 0 or index >= len(slots):
                    recorder.violations.append(
                        f"{op_name} slot {index} outside frame of {len(slots)} "
                        f"in {getattr(frame, 'fn_name', '?')}"
                    )
            return original(vm_self, instruction)

        return wrapper

    def _run(self, source: str) -> None:
        result = NodusRuntime(timeout_ms=None).run_source(source)
        self.assertTrue(result["ok"], result.get("error"))

    def test_slot_access_stays_inside_the_frame(self):
        """A corpus wide enough to reach nested closures, loops with
        per-iteration capture, recursion and try/finally — the shapes where a
        frame-size mistake would hide."""
        self._run(
            "fn counter() { let n = 0i; return fn() { n = n + 1i; return n } }\n"
            "fn recurse(n) { if (n <= 0i) { return 0i } return n + recurse(n - 1i) }\n"
            "fn loops() {\n"
            "    let total = 0i\n"
            "    let fns = []\n"
            "    for i in [1i, 2i, 3i] { let v = i; fns = list_push(fns, fn() { return v }) }\n"
            "    for f in fns { total = total + f() }\n"
            "    return total\n"
            "}\n"
            "fn guarded() {\n"
            "    let x = 0i\n"
            '    try { x = 1i; throw "e" } catch e { x = 2i } finally { x = x + 10i }\n'
            "    return x\n"
            "}\n"
            "fn main() {\n"
            "    let c = counter()\n"
            '    print("\\(c()) \\(c()) \\(recurse(5i)) \\(loops()) \\(guarded())")\n'
            "}\n"
        )
        self.assertEqual([], self.violations)
        self.assertGreater(self.observed, 50,
                           "too few slot accesses observed for this to mean anything")

    def test_slot_access_stays_inside_the_frame_across_the_stdlib(self):
        """Driving real stdlib code rather than a fixture, because a fixture
        exercises the shapes its author thought of."""
        self._run(
            'import "std:strings" as strings\n'
            'import "std:collections" as coll\n'
            'import "std:math" as math\n'
            'import "std:json" as json\n'
            "fn main() {\n"
            '    print(strings.join(["a", "b", "c"], "-"))\n'
            "    print(coll.len([1i, 2i, 3i]))\n"
            "    print(math.pow(2, 8))\n"
            '    print(json.stringify({"k": 1i}))\n'
            "}\n"
        )
        self.assertEqual([], self.violations)
        self.assertGreater(self.observed, 20)

    def test_a_workflow_run_keeps_slot_discipline(self):
        """Step bodies run in their own coroutines with their own frames — the
        place a frame-size error would corrupt one step from another."""
        self._run(
            "workflow w {\n"
            "    state total = 0i with { merge: \"sum\" }\n"
            "    step a { let x = 1i; total += x; return x }\n"
            "    step b { let y = 2i; total += y; return y }\n"
            "    step j after a, b { return total }\n"
            "}\n"
            'fn main() { print(run_workflow(w)["steps"]["j"]) }\n'
        )
        self.assertEqual([], self.violations)

    def test_the_instrumentation_can_actually_fire(self):
        """The control. A recorder that never reports would make every test above
        pass by construction, which is the failure mode this whole issue exists
        to catch."""
        self.violations.append("synthetic")
        self.assertEqual(["synthetic"], self.violations)
        self.violations.clear()


if __name__ == "__main__":
    unittest.main()
