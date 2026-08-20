"""`run_source` runs the source it is given, whatever `filename` names.

`filename` is a label -- it is what error messages interpolate, and
`embedding-nodus.md` says so under a heading called "Passing a filename". It was
also, silently, the program selector: whenever a file of that name existed,
`run_source` read the file and discarded the `source` argument, reporting
`ok=True` (#521). The program that ran therefore depended on the process CWD and
on what happened to be sitting in it.

There were two paths, and fixing either alone leaves the bug reachable:

1. `embedding._run_source_locked` branched on `os.path.isfile(filename)` and
   called `load_module_from_path`, which re-reads the file.
2. The bytecode cache is keyed on path + mtime, which identifies *the file*. A
   warm entry for `x.nd` would be served to a caller who passed different source
   under that name -- and compiling different source under that name would
   *write* an entry that later poisons `run_file`.

So the tests below are a truth table over (entry point) x (cache cold/warm) x
(source matches the file or not), rather than one call per bug.
"""
import inspect
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus.runtime.embedding import NodusRuntime  # noqa: E402
from nodus.runtime.module_loader import ModuleLoader  # noqa: E402

ON_DISK = 'fn main() { print("ON DISK") }\n'
PASSED = 'fn main() { print("PASSED STRING") }'


class _Workspace:
    """A directory holding `victim.nd`, entered so relative labels resolve."""

    def __enter__(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.__enter__()
        self.victim = os.path.join(self.dir, "victim.nd")
        with open(self.victim, "w", encoding="utf-8") as handle:
            handle.write(ON_DISK)
        os.makedirs(os.path.join(self.dir, "sub"), exist_ok=True)
        self.nested = os.path.join(self.dir, "sub", "nested.nd")
        with open(self.nested, "w", encoding="utf-8") as handle:
            handle.write(ON_DISK)
        self._cwd = os.getcwd()
        os.chdir(self.dir)
        return self

    def __exit__(self, *exc):
        os.chdir(self._cwd)
        return self._tmp.__exit__(*exc)

    @staticmethod
    def run_source(source, **kwargs):
        runtime = NodusRuntime(timeout_ms=None, max_steps=None)
        try:
            return runtime.run_source(source, **kwargs).get("stdout", "").strip()
        finally:
            runtime.shutdown()

    @staticmethod
    def run_file(path):
        runtime = NodusRuntime(timeout_ms=None, max_steps=None)
        try:
            return runtime.run_file(path).get("stdout", "").strip()
        finally:
            runtime.shutdown()


class TheLabelDoesNotSelectTheProgramTests(unittest.TestCase):
    # closes: #521
    def test_no_form_of_an_existing_path_substitutes_the_file(self):
        """Relative, dot-prefixed, absolute and nested all resolved to a real
        file, and every one of them ran it instead of the argument."""
        with _Workspace() as ws:
            labels = {
                "bare relative": "victim.nd",
                "dot-prefixed": os.path.join(".", "victim.nd"),
                "absolute": os.path.abspath("victim.nd"),
                "nested": os.path.join("sub", "nested.nd"),
            }
            for description, label in labels.items():
                with self.subTest(label=description):
                    self.assertEqual("PASSED STRING", ws.run_source(PASSED, filename=label))

    def test_a_label_naming_no_file_was_never_affected(self):
        """The control: this case always worked, and must keep working -- it is
        what every existing test in the suite relies on."""
        with _Workspace() as ws:
            self.assertEqual("PASSED STRING", ws.run_source(PASSED, filename="absent.nd"))
            self.assertEqual("PASSED STRING", ws.run_source(PASSED))

    def test_run_file_still_runs_the_file(self):
        """The half that is supposed to read from disk. `run_file` reads the file
        itself and forwards the text as `source`, so before the fix the loader
        re-read it and `run_file`'s own read was thrown away; its docstring's
        claim to be `run_source(open(path).read(), filename=path)` was true only
        by accident. Now it is true by construction."""
        with _Workspace() as ws:
            self.assertEqual("ON DISK", ws.run_file("victim.nd"))
            self.assertEqual("ON DISK", ws.run_file(os.path.abspath("victim.nd")))

    def test_relative_imports_still_resolve_against_the_label(self):
        """The one thing the old branch bought that was worth keeping: a label
        naming a real path still tells the loader where `./x.nd` resolves from.
        Deleting the branch outright would have broken this."""
        with _Workspace() as ws:
            with open(os.path.join(ws.dir, "sub", "helper.nd"), "w", encoding="utf-8") as handle:
                handle.write('export fn greet() { return "from helper" }\n')
            source = 'import "./helper.nd" as helper\nfn main() { print(helper.greet()) }'
            self.assertEqual(
                "from helper",
                ws.run_source(source, filename=os.path.join("sub", "nested.nd")),
            )


class TheCacheIsKeyedToTheFileNotTheLabelTests(unittest.TestCase):
    """The second path. A behaviour test with a cold cache passes on the broken
    tree, so every case here warms the cache first."""

    # closes: #521
    def test_a_warm_entry_for_the_file_is_not_served_to_different_source(self):
        with _Workspace() as ws:
            self.assertEqual("ON DISK", ws.run_file("victim.nd"))          # warms it
            self.assertEqual("PASSED STRING", ws.run_source(PASSED, filename="victim.nd"))

    # closes: #521
    def test_compiling_different_source_does_not_poison_the_file_entry(self):
        """The inverse, and the one that bit while writing this fix: guarding
        only the *read* left the write live, so running a differing source under
        the file's name stored that compile under the file's path+mtime key --
        and the next `run_file` got the caller's program."""
        with _Workspace() as ws:
            self.assertEqual("PASSED STRING", ws.run_source(PASSED, filename="victim.nd"))
            self.assertEqual("ON DISK", ws.run_file("victim.nd"))
            # And again, now that a legitimate entry exists.
            self.assertEqual("PASSED STRING", ws.run_source(PASSED, filename="victim.nd"))
            self.assertEqual("ON DISK", ws.run_file("victim.nd"))

    def test_matching_source_still_gets_a_cache_entry(self):
        """The fix must not disable caching for the caller that legitimately
        passes a file's own text -- which is what `tooling/runner.py` does for
        every `nodus run`. Silently losing the cache would be a real regression
        and no behaviour test would notice."""
        from nodus.runtime.bytecode_cache import load_cached_bytecode

        with _Workspace() as ws:
            self.assertEqual("ON DISK", ws.run_source(ON_DISK, filename="victim.nd"))
            self.assertIsNotNone(
                load_cached_bytecode(ws.dir, os.path.abspath("victim.nd")),
                "passing a file's own source under its own name must still cache",
            )


class OneDecisionNotTwoTests(unittest.TestCase):
    """Both cache-consult sites computed eligibility independently, which is how
    a fix lands on one path and not its sibling. They now share one method, and
    this fails if a third site starts deciding for itself."""

    def test_staleness_is_only_consulted_through_the_shared_predicate(self):
        callers = set()
        original = ModuleLoader._can_skip_reprocessing

        def recording(self, source_path):
            callers.add(inspect.stack()[1].function)
            return original(self, source_path)

        ModuleLoader._can_skip_reprocessing = recording
        try:
            with _Workspace() as ws:
                ws.run_file("victim.nd")
                ws.run_file("victim.nd")          # warm, so the read path runs too
                ws.run_source(PASSED, filename="victim.nd")
        finally:
            ModuleLoader._can_skip_reprocessing = original

        self.assertTrue(callers, "the staleness check never ran -- test proves nothing")
        self.assertEqual(
            {"_cache_is_authoritative"},
            callers,
            "a cache decision is being made outside `_cache_is_authoritative`; route "
            "it through there so the identity check cannot be skipped on one path",
        )


if __name__ == "__main__":
    unittest.main()
