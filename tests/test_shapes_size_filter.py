"""`--shapes` species A: the size threshold filters sites, not groups (#736).

`MIN_BODY_STATEMENTS` exists to keep trivial functions out — below it, a shared
name is a coincidence rather than a shared decision. It was applied as a
**whole-group veto**:

    if any(n < MIN_BODY_STATEMENTS for _, _, n in sites):
        continue

so one small sibling suppressed every genuine implementation beside it. A
trivial body is not evidence of a duplicated question; a trivial body *next to
two substantial ones* is not evidence of its absence.

It hid three groups in this tree, two of them real: `_root_vm(vm)` byte-identical
in three builtin modules, and `run()` byte-identical across the DAP and LSP
servers. Both are recorded in `tools/shape_manifest.json` now.

The cost of the veto scales with the number of small same-named functions in the
tree, so the detector was quietly weakening as the codebase grew — while
reporting `0 new`, which is the reading that costs most. `#480` and the
`--consumers` keyword miss are the same lesson: a check that goes *quiet* is
worse than one that fails.

`test_a_small_body_alone_is_still_not_a_finding` is the one that keeps this
honest. Removing the veto must not become removing the threshold — that would
report every `write`/`visit`/`check` pair in `src/` and get the phase switched
off, which is how a noisy detector dies.
"""

import ast
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))  # noqa: E402

from tools.nodus_gate.shapes_phase import (  # noqa: E402
    MIN_BODY_STATEMENTS,
    _species_a,
)


def trees(**sources):
    """`{"a_py": "SRC"}` -> the (rel, tree) pairs the phase consumes."""
    return [(rel.replace("_py", ".py"), ast.parse(src)) for rel, src in sources.items()]


def body(name: str, statements: int, params: str = "") -> str:
    """A function with exactly `statements` statements, for threshold tests."""
    lines = [f"def {name}({params}):"]
    lines += [f"    x{i} = {i}" for i in range(statements - 1)]
    lines.append("    return 0")
    return "\n".join(lines) + "\n"


def keys(findings) -> set[str]:
    return {finding.key for finding in findings}


class TheThresholdFiltersSitesTests(unittest.TestCase):
    # closes: #736
    def test_a_small_sibling_no_longer_hides_the_real_ones(self):
        """The defect. Two substantial implementations in two files, plus one
        trivial function of the same name — which used to veto the whole group.
        """
        big = MIN_BODY_STATEMENTS + 2
        found = _species_a(trees(
            a_py=body("resolve", big, "vm"),
            b_py=body("resolve", big, "vm"),
            c_py=body("resolve", 2, "vm"),
        ))
        self.assertIn("A:resolve(vm)", keys(found))

    # closes: #736
    def test_the_small_site_is_not_counted_among_them(self):
        """It is filtered, not merely tolerated — otherwise `sites` would drift
        and the manifest's growth check would compare against a wrong number."""
        big = MIN_BODY_STATEMENTS + 2
        found = _species_a(trees(
            a_py=body("resolve", big, "vm"),
            b_py=body("resolve", big, "vm"),
            c_py=body("resolve", 2, "vm"),
        ))
        finding = next(f for f in found if f.key == "A:resolve(vm)")
        self.assertEqual(2, finding.sites)
        self.assertTrue(all("c.py" not in line for line in finding.detail))

    # closes: #736
    def test_a_small_body_alone_is_still_not_a_finding(self):
        """The threshold's actual job, unchanged. Removing the veto must not
        become removing the threshold: below it a shared name is coincidence,
        and reporting every `write`/`visit`/`check` pair is how a detector gets
        switched off."""
        found = _species_a(trees(
            a_py=body("write", 2, "value"),
            b_py=body("write", 2, "value"),
        ))
        self.assertEqual(set(), keys(found))

    # closes: #736
    def test_one_substantial_site_and_one_trivial_is_not_a_finding(self):
        """After filtering there is one implementation left, and one is not a
        duplicated question. The group conditions are re-applied to the
        survivors rather than to the original list."""
        found = _species_a(trees(
            a_py=body("resolve", MIN_BODY_STATEMENTS + 2, "vm"),
            b_py=body("resolve", 2, "vm"),
        ))
        self.assertEqual(set(), keys(found))

    # closes: #736
    def test_two_substantial_sites_in_one_file_is_not_a_finding(self):
        """The distinct-files condition also re-applies to the survivors. It is
        a separate rule from the threshold and was not part of this fix — pinned
        so that filtering sites cannot quietly widen the detector."""
        big = MIN_BODY_STATEMENTS + 2
        source = body("resolve", big, "vm") + "\n" + body("resolve", big, "vm").replace(
            "def resolve", "def resolve"
        )
        found = _species_a([("a.py", ast.parse(source))])
        self.assertEqual(set(), keys(found))


class TheRealFindingsItWasHidingTests(unittest.TestCase):
    """Reconstructed from the tree, so the test says what was actually being
    lost rather than only that a filter changed."""

    # closes: #736
    def test_the_root_vm_shape(self):
        """Four builtin modules each walking `_caller_vm` to the root.

        The reconstruction includes the fourth on purpose. Three carry a
        docstring and come to exactly eight statements — the threshold — and the
        one in `subprocess_module.py` is the identical walk *without* a
        docstring, so it counts seven. Under the group veto that single short
        copy hid the other three.

        That is the defect at its sharpest: the copy that was one line shorter
        suppressed the finding for all of them, and the phase reported `0 new`
        the whole time.
        """
        walk = (
            "def _root_vm(vm):\n"
            '    """Return the root-most VM in the _caller_vm chain."""\n'
            "    root = vm\n"
            "    while True:\n"
            "        parent = getattr(root, '_caller_vm', None)\n"
            "        if parent is None:\n"
            "            return root\n"
            "        root = parent\n"
        )
        # Exactly 8 statements, as the real ones are -- the docstring counts,
        # which is why all three sit precisely *on* the threshold and any
        # trivial namesake elsewhere in the tree used to veto them.
        counted = len(
            [s for s in ast.walk(ast.parse(walk).body[0]) if isinstance(s, ast.stmt)]
        )
        self.assertEqual(
            MIN_BODY_STATEMENTS, counted,
            "the reconstruction must match the real size, or it tests nothing",
        )
        # The same walk with no docstring: one statement fewer, one below the
        # threshold. This is `subprocess_module.py`'s copy.
        short = walk.replace(
            '    """Return the root-most VM in the _caller_vm chain."""\n', ""
        )
        self.assertEqual(
            MIN_BODY_STATEMENTS - 1,
            len([s for s in ast.walk(ast.parse(short).body[0]) if isinstance(s, ast.stmt)]),
        )

        found = _species_a(trees(
            http_py=walk, tool_py=walk, test_py=walk, subprocess_py=short
        ))
        self.assertIn(
            "A:_root_vm(vm)", keys(found),
            "the short copy must not veto the three real ones",
        )
        finding = next(f for f in found if f.key == "A:_root_vm(vm)")
        self.assertEqual(3, finding.sites, "the sub-threshold copy is not counted")
        self.assertTrue(
            all("subprocess.py" not in line for line in finding.detail),
            "and it is not listed either -- it is filtered, not tolerated",
        )


class TheManifestRecordsThemTests(unittest.TestCase):
    """A finding that is real and unrecorded fails `--strict`; one that is
    recorded must say *why*. These three were classified by reading all eight
    bodies, not by their names."""

    def _entries(self) -> dict:
        import json
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        return json.loads(
            (root / "tools" / "shape_manifest.json").read_text(encoding="utf-8")
        )["entries"]

    # closes: #736
    def test_all_three_are_recorded_with_a_reason(self):
        entries = self._entries()
        for key in ("A:_root_vm(vm)", "A:run()", "A:_worker()"):
            with self.subTest(finding=key):
                self.assertIn(key, entries, "an unrecorded finding fails --strict")
                entry = entries[key]
                self.assertIn(entry["verdict"], {"intentional", "tracked"})
                self.assertGreater(
                    len(entry["why"]), 80, "the manifest asks what was established"
                )

    # closes: #736
    def test_none_of_them_was_silenced(self):
        """`intentional` silences a finding forever, and the manifest says to be
        stingy with it. All three are real debt in some form — including
        `_worker`, whose cross-file grouping is coincidence but whose two
        same-file bodies are genuine near-duplicates the detector structurally
        cannot report on their own."""
        entries = self._entries()
        for key in ("A:_root_vm(vm)", "A:run()", "A:_worker()"):
            with self.subTest(finding=key):
                self.assertEqual("tracked", entries[key]["verdict"])


if __name__ == "__main__":
    unittest.main()
