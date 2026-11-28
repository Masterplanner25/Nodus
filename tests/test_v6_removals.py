"""The D2 and D3 removals at 6.0.0: surfaces deprecated for years, gone.

`docs/migration/v6.0-staged-flips.md` "Surfaces removed" is the user-facing
list. `.tl` source files are covered in `test_nodus.py` (the CLI refuses one by
name; the resolver no longer looks for one). The rest are here: each removal is
asserted to be absent, and each replacement to work, so a revert of either half
fails.
"""

import importlib
import os
import sys
import unittest
import warnings
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus.runtime.embedding import NodusRuntime  # noqa: E402

REPO = Path(__file__).resolve().parents[1]


class LegacyLaunchersAreGone(unittest.TestCase):
    """D2: `language.py` / `language.bat`, and the `nodus.main.language` module."""

    def test_the_root_launchers_are_gone(self):
        self.assertFalse((REPO / "language.py").exists())
        self.assertFalse((REPO / "language.bat").exists())

    def test_the_module_launcher_is_gone(self):
        # Checked on disk, not by importing: importing anything under the
        # `nodus.main` package binds that package over the `nodus.main()`
        # function for the rest of the process, and later tests call it.
        self.assertFalse((REPO / "src" / "nodus" / "main" / "language.py").exists())

    def test_the_replacements_still_exist(self):
        self.assertTrue((REPO / "nodus.py").is_file())
        self.assertTrue((REPO / "src" / "nodus" / "main" / "nodus.py").is_file())


class TheReexportShimIsGone(unittest.TestCase):
    """D2: `nodus.tooling.tiny_vm_lang_functions` re-exported the package."""

    def test_the_shim_cannot_be_imported(self):
        with self.assertRaises(ModuleNotFoundError):
            importlib.import_module("nodus.tooling.tiny_vm_lang_functions")

    def test_the_package_exports_what_it_re_exported(self):
        import nodus

        self.assertTrue(callable(nodus.main))


class LastVmIsGone(unittest.TestCase):
    """D3: `NodusRuntime._last_vm` warned on every read; `active_vm()` replaces it."""

    def test_the_property_is_gone(self):
        rt = NodusRuntime()
        rt.run_source('print("x")')
        self.assertFalse(hasattr(type(rt), "_last_vm"))
        with self.assertRaises(AttributeError):
            rt._last_vm  # noqa: B018

    def test_active_vm_returns_the_last_run_without_warning(self):
        rt = NodusRuntime()
        self.assertIsNone(rt.active_vm())
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            rt.run_source('print("x")')
            vm = rt.active_vm()
        self.assertIsNotNone(vm)
        self.assertEqual([], [str(w.message) for w in caught if "active_vm" in str(w.message)])
        rt.reset()
        self.assertIsNone(rt.active_vm())


if __name__ == "__main__":
    unittest.main()
