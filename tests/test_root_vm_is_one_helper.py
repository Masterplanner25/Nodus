"""One answer to "which VM is the root of this call" (#751).

`_root_vm(vm)` — the walk up the `_caller_vm` chain — was implemented four
times, privately, in four builtin modules. Byte-identical, and `test_module`'s
copy said so in its own docstring ("Same pattern as tool_module._root_vm").

**It is the `_caller_vm` chain, which is why four copies mattered more than
tidiness.** #691 and #696 were both "which chunk was this closure compiled
against", and the sharpest thing they left is that `_is_foreign_closure`
*implied* `_caller_vm is not None` while two callers leaned on the implication
rather than stating it — so one way of reaching the code was invisible to
everyone including the people who wrote the guards. Four private answers to the
same question about the same chain is that material.

`ThereIsExactlyOneImplementationTests` asserts on the source, because behaviour
cannot tell one helper from four that agree — which they did, for as long as
nobody widened what the walk has to handle.

The gate could not see it either: species A applied its size threshold as a
whole-group veto, and `subprocess_module`'s copy is the identical walk *without*
a docstring — seven statements against eight — so that one short copy suppressed
the finding for all four while the phase reported `0 new` (#736).
"""

import ast
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))  # noqa: E402

from nodus.vm.vm_chain import root_vm  # noqa: E402

BUILTIN_MODULES = ("http_module", "subprocess_module", "test_module", "tool_module")


class _Link:
    """The only thing the walk touches is `_caller_vm`."""

    def __init__(self, caller=None):
        self._caller_vm = caller


class TheWalkItselfTests(unittest.TestCase):
    # closes: #751
    def test_a_vm_with_no_caller_is_its_own_root(self):
        lone = _Link()
        self.assertIs(lone, root_vm(lone))

    # closes: #751
    def test_it_walks_to_the_far_end_of_the_chain(self):
        root = _Link()
        middle = _Link(root)
        leaf = _Link(middle)
        self.assertIs(root, root_vm(leaf))

    # closes: #751
    def test_a_missing_attribute_ends_the_walk(self):
        """`getattr(..., None)` rather than attribute access, so an object that
        never had `_caller_vm` is a root rather than an AttributeError. The four
        copies all did this; keeping it is not incidental."""

        class Bare:
            pass

        bare = Bare()
        self.assertIs(bare, root_vm(bare))


class ThereIsExactlyOneImplementationTests(unittest.TestCase):
    """Asserted on the source. Four copies that agree are indistinguishable from
    one helper until somebody changes what the walk must handle."""

    def _module_source(self, name: str) -> str:
        return (_REPO_ROOT / "src" / "nodus" / "builtins" / f"{name}.py").read_text(
            encoding="utf-8"
        )

    # closes: #751
    def test_no_builtin_module_defines_its_own(self):
        for name in BUILTIN_MODULES:
            with self.subTest(module=name):
                tree = ast.parse(self._module_source(name))
                defined = {
                    node.name
                    for node in ast.walk(tree)
                    if isinstance(node, ast.FunctionDef)
                }
                self.assertNotIn(
                    "_root_vm", defined,
                    "import it from nodus.vm.vm_chain rather than writing a fifth",
                )

    # closes: #751
    def test_each_imports_the_shared_one(self):
        """The other half — the assertion above is satisfied just as well by a
        module that stopped walking the chain at all."""
        for name in BUILTIN_MODULES:
            with self.subTest(module=name):
                self.assertIn(
                    "from nodus.vm.vm_chain import root_vm as _root_vm",
                    self._module_source(name),
                )

    # closes: #751
    def test_nothing_in_the_tree_walks_the_chain_by_hand(self):
        """A fifth copy would most likely arrive inline rather than as a named
        function, where the shapes detector could never see it.

        The VM's own single-hop reads of `_caller_vm` are a different question —
        "delegate reflection to my caller" — and are not a root walk, so the
        pattern this looks for is the loop, not the attribute.
        """
        offenders = []
        for path in sorted((_REPO_ROOT / "src").rglob("*.py")):
            if path.name == "vm_chain.py":
                continue
            # utf-8-sig, not utf-8: two files under src/ carry a BOM
            # (main/language.py and tooling/tiny_vm_lang_functions.py), and
            # `ast.parse` rejects U+FEFF. The repo's own `_read_file` opens with
            # this encoding for the same reason.
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            for loop in ast.walk(tree):
                if not isinstance(loop, ast.While):
                    continue
                reads_caller = any(
                    isinstance(node, ast.Call)
                    and getattr(node.func, "id", None) == "getattr"
                    and len(node.args) >= 2
                    and isinstance(node.args[1], ast.Constant)
                    and node.args[1].value == "_caller_vm"
                    for node in ast.walk(loop)
                )
                if reads_caller:
                    offenders.append(f"{path.relative_to(_REPO_ROOT).as_posix()}:{loop.lineno}")
        self.assertEqual(
            [], offenders,
            "an inline walk up the _caller_vm chain -- use nodus.vm.vm_chain.root_vm",
        )


class TheExplanationTravelledWithItTests(unittest.TestCase):
    """`tool_module`'s docstring was the only record of *why* the traversal
    exists — stdlib builtins close over a per-call child VM, so mutating it
    discards the write. Left behind, the helper reads as defensive `getattr`
    noise and the next reader deletes it or writes a fifth."""

    # closes: #751
    def test_the_reason_is_recorded_where_the_helper_now_lives(self):
        source = (_REPO_ROOT / "src" / "nodus" / "vm" / "vm_chain.py").read_text(
            encoding="utf-8"
        )
        for fragment in ("invoke_function", "child", "registration time"):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, source)


if __name__ == "__main__":
    unittest.main()
