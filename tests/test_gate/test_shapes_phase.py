"""Tests for the shapes phase — the recurring bug shape, caught mechanically.

The phase exists because twenty-one instances of "a correct check that only one
of several paths goes through" were each found by a human asking "what else has
this shape?" after a bug report. Its job is to ask that first.

What is tested here is mostly the phase's *failure* modes, because a detector
that silently stops detecting is worse than none — it converts "nobody looked"
into "the gate is green". Every assertion below was checked against a tree where
the thing it guards was broken.
"""

import ast
import io
import json
import os
import pathlib
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))          # noqa: E402
sys.path.insert(0, str(REPO / "src"))  # noqa: E402

from tools.nodus_gate.shapes_phase import (  # noqa: E402
    MIN_BODY_STATEMENTS,
    _species_a,
    _species_b,
    _species_d,
    run_shapes_phase,
)

MANIFEST = REPO / "tools" / "shape_manifest.json"


def _tree(source: str):
    return ast.parse(source)


def _body(indent: int = 4) -> str:
    """A body comfortably over MIN_BODY_STATEMENTS, at the caller's indent.

    Indent-aware because a method body needs eight spaces and a module-level one
    needs four. A fixed 4-space string raised IndentationError inside `class K`,
    reported from `ast.parse` rather than from the assertion — which reads like
    the detector failing when it is the fixture that is wrong.
    """
    pad = " " * indent
    return "\n".join(f"{pad}v{i} = {i}" for i in range(MIN_BODY_STATEMENTS + 2))


BODY = _body()


class SpeciesADetectionTests(unittest.TestCase):
    """One question, N implementations."""

    def test_same_name_and_params_in_two_modules_is_a_finding(self):
        src = f"def decide(a, b):\n{BODY}\n    return v1\n"
        findings = _species_a([("a.py", _tree(src)), ("b.py", _tree(src))])
        self.assertEqual(1, len(findings))
        self.assertEqual("A:decide(a,b)", findings[0].key)
        self.assertEqual(2, findings[0].sites)

    def test_the_same_name_with_different_params_is_not(self):
        """The discriminator that makes this usable.

        Name alone gives 84 hits on this repo, nearly all coincidence (`write`,
        `visit`, `check`). Requiring the parameter list to match cuts it to 22
        and keeps every known true positive.
        """
        a = f"def decide(a, b):\n{BODY}\n    return v1\n"
        b = f"def decide(x, y, z):\n{BODY}\n    return v1\n"
        self.assertEqual([], _species_a([("a.py", _tree(a)), ("b.py", _tree(b))]))

    def test_two_definitions_in_one_module_are_not_a_finding(self):
        src = (f"def decide(a, b):\n{BODY}\n    return v1\n\n"
               f"class K:\n    def decide(self, a, b):\n{_body(8)}\n        return v1\n")
        self.assertEqual([], _species_a([("a.py", _tree(src))]))

    def test_a_trivial_body_is_not_a_finding(self):
        """A one-line accessor sharing a name is a coincidence, not a decision."""
        src = "def decide(a, b):\n    return a\n"
        self.assertEqual([], _species_a([("a.py", _tree(src)), ("b.py", _tree(src))]))

    def test_self_and_cls_are_ignored_when_comparing_signatures(self):
        free = f"def decide(a, b):\n{BODY}\n    return v1\n"
        meth = f"class K:\n    def decide(self, a, b):\n{_body(8)}\n        return v1\n"
        findings = _species_a([("a.py", _tree(free)), ("b.py", _tree(meth))])
        self.assertEqual(1, len(findings),
                         "a function and a method answering the same question "
                         "should still be compared")


class SpeciesBDetectionTests(unittest.TestCase):
    """One vocabulary, two enumerations — one of them short."""

    def test_a_near_subset_is_a_finding(self):
        a = 'FORMS = {"=", "x[i] =", "x.f ="}\n'
        b = 'FORMS = {"=", "x[i] =", "x.f =", "+="}\n'
        findings = _species_b([("a.py", _tree(a)), ("b.py", _tree(b))])
        self.assertEqual(1, len(findings))
        self.assertIn("+=", findings[0].key)

    def test_a_small_set_inside_a_big_one_is_not(self):
        """Two different vocabularies, not one with a member missing.

        Without this the phase reported 43 species-B hits on this repo, mostly
        comparing the full builtin list against unrelated six-item sets.
        """
        a = 'SMALL = {"a", "b", "c"}\n'
        b = "BIG = {" + ", ".join(f'"{c}"' for c in "abcdefghijklmnop") + "}\n"
        self.assertEqual([], _species_b([("a.py", _tree(a)), ("b.py", _tree(b))]))

    def test_identical_vocabularies_are_not_a_finding(self):
        src = 'FORMS = {"a", "b", "c", "d"}\n'
        self.assertEqual([], _species_b([("a.py", _tree(src)), ("b.py", _tree(src))]))

    def test_the_key_does_not_contain_line_numbers(self):
        """So the manifest survives an edit above the collection."""
        a = 'FORMS = {"=", "x[i] =", "x.f ="}\n'
        b = 'FORMS = {"=", "x[i] =", "x.f =", "+="}\n'
        first = _species_b([("a.py", _tree(a)), ("b.py", _tree(b))])[0].key
        shifted = _species_b([("a.py", _tree("# pad\n# pad\n" + a)),
                              ("b.py", _tree("# pad\n" + b))])[0].key
        self.assertEqual(first, shifted)


class SpeciesDDetectionTests(unittest.TestCase):
    """Process-global state shared by every participant."""

    def test_a_global_rebound_name_is_a_finding(self):
        src = "STATE = None\n\ndef set_it(v):\n    global STATE\n    STATE = v\n"
        keys = [f.key for f in _species_d([("a.py", _tree(src))])]
        self.assertIn("D:a.py::STATE", keys)

    def test_a_mutated_container_is_a_finding(self):
        src = "REG = {}\n\ndef add(k, v):\n    REG[k] = v\n"
        keys = [f.key for f in _species_d([("a.py", _tree(src))])]
        self.assertIn("D:a.py::REG", keys)

    def test_a_read_only_lookup_table_is_not(self):
        """Subscript *reads* are not shared mutable state.

        Counting them buried the real hits under a pile of frozen month-name and
        escape-map constants — 26 findings instead of 14.
        """
        src = "MONTHS = ['jan', 'feb']\n\ndef name(i):\n    return MONTHS[i]\n"
        self.assertEqual([], _species_d([("a.py", _tree(src))]))


class ManifestContractTests(unittest.TestCase):
    """The manifest is the baseline; a broken one must not read as a pass."""

    def test_the_repo_baseline_is_clean(self):
        """Every shape in the tree is recorded, so a new one stands out.

        If this fails, either something new was introduced — triage it — or a
        recorded one was fixed, in which case delete its entry.
        """
        result = run_shapes_phase(REPO)
        self.assertIsNone(result.error)
        self.assertEqual([], [f.key for f in result.new])
        self.assertEqual([], [f.key for f in result.grown])
        self.assertEqual([], result.stale_entries)

    def test_every_entry_states_a_reason(self):
        """`why` must record what was established. An entry reading 'looks fine'
        is how a real one gets lost — the lesson dependent_flakes.json carries."""
        entries = json.loads(io.open(MANIFEST, encoding="utf-8").read())["entries"]
        for key, entry in entries.items():
            with self.subTest(entry=key):
                self.assertIn(entry.get("verdict"), ("intentional", "tracked"))
                self.assertGreaterEqual(
                    len(entry.get("why", "")), 40,
                    f"{key} needs a real reason, not a placeholder")

    def test_a_missing_manifest_is_a_failure_not_a_pass(self):
        """The check may not succeed by being unable to run — the rule
        `--consumers` already follows."""
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "src"))
            result = run_shapes_phase(pathlib.Path(tmp))
            self.assertIsNotNone(result.error)

    def test_an_unreadable_manifest_is_a_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "src"))
            os.makedirs(os.path.join(tmp, "tools"))
            io.open(os.path.join(tmp, "tools", "shape_manifest.json"),
                    "w", encoding="utf-8").write("{ not json")
            result = run_shapes_phase(pathlib.Path(tmp))
            self.assertIsNotNone(result.error)
            self.assertIn("could not be read", result.error)


class GrowthTests(unittest.TestCase):
    """A recorded duplication that gains another copy.

    This is the hole the first version of the phase had: the key is name+params,
    so a THIRD implementation of an already-listed function matched the existing
    entry and reported nothing. Found by probing the detector with a deliberate
    duplicate of `resolve_import_path` and watching it say `0 new`.
    """

    def _run_in(self, tmp, sources, entries):
        os.makedirs(os.path.join(tmp, "src"), exist_ok=True)
        os.makedirs(os.path.join(tmp, "tools"), exist_ok=True)
        for name, text in sources.items():
            io.open(os.path.join(tmp, "src", name), "w", encoding="utf-8").write(text)
        io.open(os.path.join(tmp, "tools", "shape_manifest.json"),
                "w", encoding="utf-8").write(json.dumps({"entries": entries}))
        return run_shapes_phase(pathlib.Path(tmp))

    def test_a_third_copy_of_a_recorded_duplication_is_reported(self):
        src = f"def decide(a, b):\n{BODY}\n    return v1\n"
        entries = {"A:decide(a,b)": {"verdict": "tracked", "why": "x" * 50, "sites": 2}}
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run_in(tmp, {"a.py": src, "b.py": src, "c.py": src}, entries)
            self.assertEqual([], result.new, "the key is known, so not 'new'")
            self.assertEqual(["A:decide(a,b)"], [f.key for f in result.grown])
            self.assertEqual(3, result.grown[0].sites)
            self.assertEqual(2, result.grown[0].recorded_sites)

    def test_the_recorded_count_matching_is_silent(self):
        src = f"def decide(a, b):\n{BODY}\n    return v1\n"
        entries = {"A:decide(a,b)": {"verdict": "tracked", "why": "x" * 50, "sites": 2}}
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run_in(tmp, {"a.py": src, "b.py": src}, entries)
            self.assertEqual([], result.new)
            self.assertEqual([], result.grown)

    def test_an_entry_matching_nothing_is_reported_stale(self):
        entries = {"A:gone(x,y)": {"verdict": "tracked", "why": "x" * 50}}
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run_in(tmp, {}, entries)
            self.assertEqual(["A:gone(x,y)"], result.stale_entries)


if __name__ == "__main__":
    unittest.main()
