"""A cached module must not run `main()` twice (#453).

`auto_run_main` exists so a script that merely *defines* `main()` still runs it.
It is suppressed when the module's own top level already calls `main()`, so a
script ending in `main()` is not executed twice.

That suppression read the AST — and returned `False` whenever `parsed is None`,
which is precisely the state of a module loaded from the bytecode cache. So the
guard held on the first run and was bypassed on every run after it:

    $ nodus run script.nd      # cold cache
    M
    $ nodus run script.nd      # warm cache
    M
    M

Silent, with no error and nothing in the output to suggest a second execution.
Any script ending in `main()` doubled its side effects from its second run
onward — which is the failure `@exactly_once` exists to prevent, arriving by a
completely different route.

It is the shape `CLAUDE.md` documents: a correct check that one path goes through
and a sibling path skips. The fix carries the answer with the bytecode instead of
recomputing it from an AST that is not always there.
"""

import contextlib
import io
import os
import tempfile
import unittest

from nodus.runtime.module_loader import ModuleLoader

MAIN_CALLED = 'fn main() { print("M") }\nmain()\n'
MAIN_UNCALLED = 'fn main() { print("M") }\n'
NO_MAIN = 'fn other() { print("M") }\nother()\n'


def run_twice(source: str) -> tuple[int, int]:
    """Load a module in two separate loaders, returning the 'M' count for each.

    A fresh `ModuleLoader` per run is what makes this a real test: the second one
    finds the bytecode cache warm, which is the state the bug lived in. Reusing a
    loader would return the memoised module and execute nothing.
    """
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "s.nd")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(source)

        counts = []
        for _ in range(2):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                loader = ModuleLoader(project_root=td)
                loader.load_module_from_path(path, auto_run_main=True)
            counts.append(buf.getvalue().count("M"))
        return counts[0], counts[1]


class TestMainRunsOncePerRun(unittest.TestCase):
    # closes: #453
    def test_a_script_that_calls_main_runs_it_once_when_cached(self):
        cold, warm = run_twice(MAIN_CALLED)
        self.assertEqual(cold, 1, "cold run should execute main exactly once")
        self.assertEqual(
            warm, 1,
            "warm (cached) run executed main twice — the auto-run-main guard was "
            "bypassed because the cached module has no AST (#453)",
        )

    def test_auto_run_main_still_fires_for_an_uncalled_main(self):
        """The positive control, and the reason the guard cannot simply be deleted.

        Suppressing `auto_run_main` unconditionally would fix the doubling and
        break the feature: a script that only *defines* `main()` would do nothing.
        """
        cold, warm = run_twice(MAIN_UNCALLED)
        self.assertEqual((cold, warm), (1, 1))

    def test_a_script_with_no_main_is_unaffected(self):
        cold, warm = run_twice(NO_MAIN)
        self.assertEqual((cold, warm), (1, 1))

    def test_the_doubling_does_not_return_on_a_third_run(self):
        """The cache is rewritten as well as read; a later run must stay correct."""
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "s.nd")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(MAIN_CALLED)
            for attempt in range(3):
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    ModuleLoader(project_root=td).load_module_from_path(
                        path, auto_run_main=True
                    )
                self.assertEqual(
                    buf.getvalue().count("M"), 1, f"run {attempt + 1} executed main twice"
                )


class TestTheAnswerTravelsWithTheBytecode(unittest.TestCase):
    """Assert on the mechanism, not only the behaviour.

    A behaviour test passes for any fix, including one that re-parses the source on
    every cached load — which would work and quietly discard the cache's benefit.
    These pin *how* the answer survives.
    """

    # closes: #453
    def test_the_flag_is_written_into_the_cached_metadata(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "s.nd")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(MAIN_CALLED)
            loader = ModuleLoader(project_root=td)
            metadata = loader._build_metadata(
                os.path.abspath(path), base_dir=td, source=MAIN_CALLED, source_path=path
            )
            payload = loader._serialize_module_metadata(metadata)
        self.assertIn("has_top_level_main_call", payload)
        self.assertTrue(payload["has_top_level_main_call"])

    def test_the_flag_is_read_back_from_cached_metadata(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "s.nd")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(MAIN_CALLED)
            # First load populates the cache.
            ModuleLoader(project_root=td).load_module_from_path(path, auto_run_main=True)
            # Second loader reads it back without parsing.
            loader = ModuleLoader(project_root=td)
            from nodus.runtime.bytecode_cache import load_cached_bytecode

            cached = load_cached_bytecode(td, os.path.abspath(path))
            self.assertIsNotNone(cached, "expected the module to be cached")
            recovered = loader._build_metadata_from_cached_bytecode(
                os.path.abspath(path), cached
            )
        self.assertIsNotNone(recovered)
        self.assertIsNone(recovered.parsed, "this path is the one with no AST")
        self.assertTrue(
            recovered.has_top_level_main_call,
            "the recorded answer did not survive the cache round-trip (#453)",
        )

    def test_an_unknown_answer_assumes_main_was_called(self):
        """Fail toward running main once too few rather than once too many.

        A script that appears to do nothing is obvious and gets investigated. A
        script that silently repeats every side effect is not — that is the bug
        this issue was.
        """
        from nodus.runtime.module_loader import ModuleMetadata
        from nodus.frontend.ast.ast_nodes import ModuleInfo

        blank = ModuleMetadata(
            module_id="m",
            exports=set(),
            import_names=set(),
            import_specs=[],
            export_from_specs=[],
            module_info=ModuleInfo(
                path="m", defs=set(), exports=set(), imports={}, aliases={},
                explicit_exports=False, qualified={},
            ),
            parsed=None,
        )
        loader = ModuleLoader()
        self.assertTrue(loader._has_top_level_main_call(blank))


if __name__ == "__main__":
    unittest.main()
