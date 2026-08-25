"""A reused loader refuses different source under one module name (#457).

`ModuleLoader` memoises by module id, and `"<memory>"` is the default id -- so
compiling two different snippets through one loader silently returned the
first one's bytecode for both. The failure surfaced somewhere else entirely
(it cost a half-measurement during #387: a bounded-recursion snippet "ran
away" because the runaway snippet's bytecode came back for it).

Refused loudly now, option (2) of the issue: same name + different source
raises, naming the remedy. Same name + same source still returns the memo
(re-loading a module is legal), and load-from-path (`source=None`) is exempt.
All three memo-consult sites are guarded through one helper, per the
sibling-path rule.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus.runtime.module_loader import ModuleLoader  # noqa: E402


# closes: #457
class LoaderSnippetReuseTests(unittest.TestCase):
    def test_different_source_under_one_name_is_refused(self):
        loader = ModuleLoader()
        loader.compile_only("fn f() { return 1i }\n", module_name="<memory>")
        with self.assertRaises(Exception) as caught:
            loader.compile_only("fn f() { return 2i }\n", module_name="<memory>")
        self.assertIn("different source", str(caught.exception))
        self.assertIn("fresh ModuleLoader", str(caught.exception))

    def test_same_source_still_returns_the_memo(self):
        """Falsifiability control: re-compiling the same source is legal and
        must not raise -- that is the memo working as intended."""
        loader = ModuleLoader()
        source = "fn f() { return 1i }\n"
        first, _, _ = loader.compile_only(source, module_name="<memory>")
        second, _, _ = loader.compile_only(source, module_name="<memory>")
        self.assertEqual(first, second)

    def test_distinct_names_compile_independently(self):
        loader = ModuleLoader()
        a, _, _ = loader.compile_only("fn f() { return 1i }\n", module_name="<a>")
        b, _, _ = loader.compile_only("fn f() { return 2i }\n", module_name="<b>")
        self.assertNotEqual(a, b)

    def test_full_load_path_is_guarded_too(self):
        """The issue's shape on `load_module_from_source` -- the third
        memo-consult site (`_load_module`'s `self._modules`)."""
        from nodus.vm.vm import VM

        vm = VM([], {}, code_locs=[])
        loader = ModuleLoader(vm=vm)
        loader.load_module_from_source("let x = 1i\n", module_name="<memory>")
        with self.assertRaises(Exception) as caught:
            loader.load_module_from_source("let x = 2i\n", module_name="<memory>")
        self.assertIn("different source", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
