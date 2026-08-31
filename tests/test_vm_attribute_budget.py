"""The `VM` instance-attribute budget, and why there is one (#702).

PyPy stores an instance's attributes in a compact map and its JIT specialises
attribute reads against that map — **up to 80 attributes**. Past that it falls
back to dict storage, the specialisation is lost, and every attribute read in
the dispatch loop deoptimises.

Measured on a generated class with a single attribute read in a loop, nothing to
do with Nodus:

    attrs   PyPy               CPython
    79      786M reads/sec     25.5M
    80       71.5M  <- cliff   26.9M
    90       72.6M             26.4M

**CPython is flat across the whole range.** That is the reason this file exists:
the cliff is structurally invisible to every benchmark, gate and CI job this
project runs, all of which are CPython.

`VM.__init__` sat at 79 attributes. #488 — a goal-budget feature that touches
nothing in the dispatch loop — made it 80, and cost ~9x of PyPy throughput
(21.7M to 2.4M instructions/sec on the same probe). It shipped in v5.6.0 and
survived three releases with every gate green. Confirmed incidental rather than
specific to that feature: adding a single *unrelated* attribute to `__init__` at
the parent commit reproduces the drop exactly.

So the number below is not a style preference. It is a cliff edge, and the only
thing that can see it is a test that counts.

**When this fails**, do not raise the limit. Options, cheapest first:

1. Make the new attribute a **class-level default** if it is a constant with no
   constructor parameter behind it — reads resolve through the class and an
   instance entry appears only when something writes one. Five attributes were
   moved that way to make room; see the block at the top of `class VM`.
2. Group related attributes behind one small object.
3. `__slots__` on `VM` removes the cliff outright (measured: 717M reads/sec at
   80 attributes, versus 68M without) but forbids the dynamic assignment
   `module.py` and `embedding.py` rely on, so it is a real design change rather
   than a quick fix.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus.vm.vm import VM  # noqa: E402

# PyPy's storage-strategy threshold. An instance holding *more* than this many
# attributes loses map-based storage. Named once; both checks below drive off it.
PYPY_MAP_ATTRIBUTE_LIMIT = 80

# Headroom deliberately left below the limit, so the next attribute added is a
# conversation rather than an outage. Raise the *headroom* only with a measured
# reason; never raise `PYPY_MAP_ATTRIBUTE_LIMIT`, which is PyPy's number.
HEADROOM = 1


def bare_vm() -> VM:
    return VM([], {}, code_locs=[], source_path=None)


# closes: #702
class VmAttributeBudgetTests(unittest.TestCase):

    def test_a_bare_vm_stays_under_the_pypy_map_limit(self):
        count = len(bare_vm().__dict__)
        self.assertLess(
            count, PYPY_MAP_ATTRIBUTE_LIMIT - HEADROOM + 1,
            f"VM.__init__ now creates {count} instance attributes. PyPy loses "
            f"map-based storage above {PYPY_MAP_ATTRIBUTE_LIMIT}, which cost ~9x "
            f"throughput when it happened in v5.6.0 (#702). Read this module's "
            f"docstring before changing the limit — the fix is to shed an "
            f"attribute, not to raise the number.",
        )

    def test_a_runtime_built_vm_stays_under_it_too(self):
        """`NodusRuntime` is the path an embedder takes, and it may set
        attributes the constructor does not. A bare VM passing means nothing if
        the one real programs actually run is over the line."""
        from nodus.runtime.embedding import NodusRuntime  # noqa: PLC0415

        runtime = NodusRuntime(timeout_ms=None)
        runtime.run_source("fn main() { }")
        vm = runtime.active_vm()
        count = len(vm.__dict__)
        self.assertLess(
            count, PYPY_MAP_ATTRIBUTE_LIMIT - HEADROOM + 1,
            f"a VM built through NodusRuntime holds {count} instance "
            f"attributes, over the PyPy budget (#702). The extras beyond a bare "
            f"VM are: {sorted(set(vm.__dict__) - set(bare_vm().__dict__))}",
        )

    def test_the_hoisted_defaults_are_readable_and_not_instance_attributes(self):
        """The mechanism the headroom depends on: a class-level default answers
        the read without occupying an instance slot. If someone reinstates one
        of these as `self.x = ...` the count silently rises again, and the count
        test above is the only thing that would notice — this names them so the
        failure explains itself."""
        vm = bare_vm()
        for name, expected in (("_resume_origin", None), ("budget_meters", None),
                               ("trace_errors", False), ("last_graph_plan", None),
                               ("trace_count", 0)):
            with self.subTest(attribute=name):
                self.assertEqual(expected, getattr(vm, name),
                                 f"{name} must still read as {expected!r}")
                self.assertNotIn(
                    name, vm.__dict__,
                    f"{name} is back in the instance dict; it was hoisted to a "
                    f"class-level default to buy headroom under the PyPy limit "
                    f"(#702)",
                )

    def test_writing_a_hoisted_default_still_works_per_instance(self):
        """Hoisting must not make these read-only or shared. A write creates an
        ordinary instance attribute and must not leak to another VM."""
        one, two = bare_vm(), bare_vm()
        one.trace_errors = True
        self.assertIs(True, one.trace_errors)
        self.assertIs(False, two.trace_errors, "the write leaked across instances")
        self.assertIn("trace_errors", one.__dict__)
        self.assertNotIn("trace_errors", two.__dict__)


if __name__ == "__main__":
    unittest.main()
