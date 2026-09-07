"""Assignment binds a reference; it does not copy (#814).

`let b = a` gives a second name for one container. Mutating through either name
is visible through both, for lists, maps and records alike, at any nesting depth
and across a call boundary.

Nothing asserted that before this file. The behaviour is long-standing and
uniform, but it lived only in the VM's object model, so an unrelated change to
how containers are stored or passed could have altered it and left the suite
green. That is the same exposure `test_status_vocabulary.py` and
`test_name_resolution_agreement.py` were written to close for their questions.

**These are characterization tests, not a ratified contract.** #814 asks the
open question — state the rule in the guide, and decide whether a copy surface
is owed, since "hand this container to a step without letting it mutate mine" is
currently inexpressible. If that issue decides to change the semantics rather
than document them, this file is what has to be updated, deliberately, in the
same commit. That is the point of writing it down: today the change would be
silent.

The contexts matter as much as the cases. Aliasing is asserted from a plain
function, a coroutine and a **workflow step body**, because this project has
been caught once by exactly that gap -- every test and probe for `retry.until`
ran inside `fn main()`, so a step-body-only defect survived the full suite, nine
gate phases and 83 release probes (#691). A workflow author closing over a list
declared outside the workflow is the case most likely to surprise someone, so it
is the case most worth pinning.

Related: record `==` becomes structural at 6.0.0 (#545,
`docs/design/v6/00-record-equality.md`). That flip changes *comparison*, not
*binding* -- records will still alias exactly as asserted here, the way lists and
maps already do. `RecordAliasingSurvivesTheEqualityFlipTests` says so, so the
changelog line for #545 cannot be read as "records became value types".
"""

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


class ListAliasingTests(unittest.TestCase):
    # closes: #814
    def test_a_second_name_for_a_list_shares_its_elements(self):
        src = """
let a = [1, 2, 3]
let b = a
b[0] = 999
print(a[0])
"""
        self.assertEqual(run_program(src), ["999.0"])

    def test_the_alias_sees_writes_made_through_the_original(self):
        """Both directions, because a one-way check passes on a copy-on-write model."""
        src = """
let a = [1, 2, 3]
let b = a
a[2] = 555
print(b[2])
"""
        self.assertEqual(run_program(src), ["555.0"])

    def test_a_list_passed_to_a_function_is_mutated_in_the_caller(self):
        src = """
fn overwrite(lst) { lst[0] = 777 }
let arg = [1]
overwrite(arg)
print(arg[0])
"""
        self.assertEqual(run_program(src), ["777.0"])

    def test_a_list_reached_through_a_container_is_the_same_list(self):
        src = """
let outer = {"inner": [1, 2]}
let ref = outer["inner"]
ref[0] = 88
print(outer["inner"][0])
"""
        self.assertEqual(run_program(src), ["88.0"])

    def test_list_push_appends_to_the_caller_s_list(self):
        """`list_push` mutates in place and returns the same list, as documented.

        The reassignment idiom `xs = list_push(xs, v)` used in some examples
        reads as a functional API and is what #816 is about; both spellings are
        asserted here so the in-place half is not left implicit.
        """
        src = """
let xs = [1, 2]
let ys = list_push(xs, 3)
print(len(xs))
ys[0] = 42
print(xs[0])
"""
        self.assertEqual(run_program(src), ["3", "42.0"])


class MapAliasingTests(unittest.TestCase):
    def test_a_second_name_for_a_map_shares_its_entries(self):
        src = """
let m = {"k": 1}
let m2 = m
m2["k"] = 5
print(m["k"])
"""
        self.assertEqual(run_program(src), ["5.0"])

    def test_a_key_added_through_the_alias_is_visible_on_the_original(self):
        src = """
let m = {"k": 1}
let m2 = m
m2["fresh"] = 2
print(has_key(m, "fresh"))
"""
        self.assertEqual(run_program(src), ["true"])

    def test_a_map_passed_to_a_function_is_mutated_in_the_caller(self):
        src = """
fn overwrite(m) { m["k"] = 777 }
let arg = {"k": 1}
overwrite(arg)
print(arg["k"])
"""
        self.assertEqual(run_program(src), ["777.0"])


class RecordAliasingTests(unittest.TestCase):
    def test_a_second_name_for_a_record_shares_its_fields(self):
        src = """
let p = record {x: 1}
let q = p
q.x = 99
print(p.x)
"""
        self.assertEqual(run_program(src), ["99.0"])

    def test_a_record_passed_to_a_function_is_mutated_in_the_caller(self):
        src = """
fn overwrite(r) { r.x = 777 }
let arg = record {x: 1}
overwrite(arg)
print(arg.x)
"""
        self.assertEqual(run_program(src), ["777.0"])

    def test_a_nested_record_is_shared_by_the_outer_record(self):
        src = """
let inner = record {v: 1}
let outer = record {child: inner}
outer.child.v = 42
print(inner.v)
"""
        self.assertEqual(run_program(src), ["42.0"])


class RecordAliasingSurvivesTheEqualityFlipTests(unittest.TestCase):
    """#545 changes how records *compare*, not how they *bind*.

    After 6.0.0 two records with equal fields are `==`. They are still two
    records: mutating one will not change the other, and two names for *one*
    record will still share. Both halves are asserted so the flip cannot be read
    as "records became value types" -- which is the model a reader would infer
    from the changelog line alone.
    """

    def test_two_separately_built_records_are_independent(self):
        src = """
let p = record {x: 1}
let q = record {x: 1}
q.x = 99
print(p.x)
"""
        self.assertEqual(run_program(src), ["1.0"])

    def test_but_two_names_for_one_record_are_not(self):
        src = """
let p = record {x: 1}
let q = p
q.x = 99
print(p.x)
"""
        self.assertEqual(run_program(src), ["99.0"])


class AliasingHoldsInEveryExecutionContextTests(unittest.TestCase):
    """The same question, asked where the answer is actually used (#691).

    A construct documented for use inside a step body must be tested inside a
    step body; the top-level cases above take a different path through the VM.
    """

    def test_a_coroutine_mutates_a_list_its_caller_can_see(self):
        src = """
let a = [1]
let c = coroutine(fn() { a[0] = 777 })
spawn(c)
run_loop()
print(a[0])
"""
        self.assertEqual(run_program(src), ["777.0"])

    def test_a_step_body_mutates_a_list_declared_outside_the_workflow(self):
        src = """
let a = [1]
workflow w {
    step touch {
        a[0] = 777
        return "ok"
    }
}
let r = run_workflow(w)
print(a[0])
"""
        self.assertEqual(run_program(src, source_path="aliasing.nd"), ["777.0"])

    def test_a_step_body_mutates_a_record_declared_outside_the_workflow(self):
        src = """
let p = record {x: 1}
workflow w {
    step touch {
        p.x = 99
        return "ok"
    }
}
let r = run_workflow(w)
print(p.x)
"""
        self.assertEqual(run_program(src, source_path="aliasing.nd"), ["99.0"])


if __name__ == "__main__":
    unittest.main()
