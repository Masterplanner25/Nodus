"""The bytecode cache must notice a content change the mtime does not (#704).

`cache_key` is `sha256(abspath + "\\0" + mtime_ns)`, and the stored payload records
`mtime_ns`. Neither depends on what the file *contains*. So any edit that lands
inside the platform's mtime resolution is invisible: the key matches, validation
passes, and a **stale program runs**.

That window is not hypothetical, and it is not only PyPy's:

    five rapid rewrites, each with different content
      CPython 3.11 / Windows   2 distinct cache keys out of 5
      PyPy 7.3.23 / Windows    2 distinct cache keys out of 5

CPython's `st_mtime_ns` here has roughly millisecond granularity, so the window
is small but real. PyPy on Windows reports whole seconds, so the window is a full
second and the collision is close to certain — which is how this surfaced: a
resume-validation test wrote a workflow, ran it, rewrote the file with an extra
step, and resumed. The rebuild got the **original** workflow from cache, so the
topology guard compared the old shape against itself, found nothing wrong, and
resumed a run whose workflow had changed (#704).

The tests below force identical mtimes with `os.utime` rather than racing the
clock. A timing-dependent test would pass on a fast machine and fail on a slow
one, which is the property that hid this.

This is the fourth time the cache has been a sibling path — #521 (which program
`run_source` runs), #400 (does inspection execute), #394 (a mark that survived
compilation but not serialization). Those were about *what* was cached. This one
is about the key itself.
"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus.runtime.bytecode_cache import (  # noqa: E402
    cache_key,
    load_cached_bytecode,
    source_mtime_ns,
    write_cached_bytecode,
)
from nodus.runtime.embedding import NodusRuntime  # noqa: E402


class _CacheCase(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.path = os.path.join(self.root, "prog.nd")

    def write(self, source: str, *, mtime_ns: int | None = None) -> int:
        with open(self.path, "w", encoding="utf-8") as handle:
            handle.write(source)
        if mtime_ns is not None:
            os.utime(self.path, ns=(mtime_ns, mtime_ns))
        return source_mtime_ns(self.path)


# closes: #704
class CacheKeyDependsOnContentTests(_CacheCase):

    def test_two_different_programs_at_one_mtime_do_not_share_an_entry(self):
        """The whole defect in one assertion. Same path, same mtime, different
        source: the cache must not answer the second with the first."""
        first_mtime = self.write("fn main() { print(1i) }\n")
        from nodus.runtime.module_loader import ModuleLoader  # noqa: PLC0415

        loader = ModuleLoader(project_root=self.root)
        unit = loader.compile_module_bytecode(self.path) if hasattr(
            loader, "compile_module_bytecode") else None
        if unit is None:                      # compile through the public path
            NodusRuntime(timeout_ms=None, allowed_paths=[self.root]).run_file(self.path)
            unit = load_cached_bytecode(self.root, self.path)
        self.assertIsNotNone(unit, "the first program should be cached")
        write_cached_bytecode(self.root, self.path, unit)

        # Same file, different content, mtime forced back to the first value.
        self.write("fn main() { print(2i) }\n", mtime_ns=first_mtime)
        self.assertEqual(first_mtime, source_mtime_ns(self.path),
                         "the mtime must be identical for this test to mean anything")

        stale = load_cached_bytecode(self.root, self.path)
        self.assertIsNone(
            stale,
            "the cache returned an entry compiled from different source at the "
            "same mtime — a stale program would run (#704)",
        )

    def test_the_program_that_runs_is_the_program_on_disk(self):
        """End to end, which is what a user experiences. `run_file` twice over a
        rewritten file at one mtime must print the second program's output."""
        mtime = self.write('fn main() { print("first") }\n')
        runtime = NodusRuntime(timeout_ms=None, allowed_paths=[self.root])
        first = runtime.run_file(self.path)
        self.assertIn("first", first["stdout"])

        self.write('fn main() { print("second") }\n', mtime_ns=mtime)
        second = NodusRuntime(timeout_ms=None,
                              allowed_paths=[self.root]).run_file(self.path)
        self.assertIn(
            "second", second["stdout"],
            "a rewritten file at the same mtime ran the previous program from "
            "cache (#704)",
        )
        self.assertNotIn("first", second["stdout"])

    def test_an_unchanged_file_still_hits_the_cache(self):
        """The control. A fix that simply disabled the cache would pass every
        test above and cost the thing the cache exists for."""
        self.write('fn main() { print("stable") }\n')
        NodusRuntime(timeout_ms=None, allowed_paths=[self.root]).run_file(self.path)
        hit = load_cached_bytecode(self.root, self.path)
        self.assertIsNotNone(
            hit, "an untouched file must still be served from cache")

    def test_the_key_alone_cannot_distinguish_content(self):
        """Names the mechanism, so a future reader does not have to re-derive it:
        `cache_key` is a function of path and mtime only. That is *why* the
        payload has to carry the content, and it is what makes the window
        platform-dependent — CPython ~ms here, PyPy whole seconds."""
        mtime = self.write("fn main() { print(1i) }\n")
        key_a = cache_key(self.path, mtime)
        self.write("fn main() { print(2i) }\n", mtime_ns=mtime)
        key_b = cache_key(self.path, source_mtime_ns(self.path))
        self.assertEqual(
            key_a, key_b,
            "if these ever differ the key has started depending on content and "
            "this module's premise should be revisited",
        )


if __name__ == "__main__":
    unittest.main()
