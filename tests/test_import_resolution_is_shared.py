"""The editor and the runtime resolve an import the same way (#598).

`resolve_import_path` — "which file does this import mean" — existed twice: 159
lines in `runtime/module_loader.py` and 55 in `tooling/loader.py`, 38% similar.
`nodus lsp` and `tooling/diagnostics.py` import from the second, so the editor
answered a question the runtime also answers, differently.

The short copy had **no entry-point lookup**, which is how a pip-installed
companion library ships its `.nd` files (`docs/guide/library-entry-points.md`).
So `import "nodus-mcp"` resolved when run and read as `Import not found` in the
editor — a false error on correct code, which trains people to ignore the panel.

Four more functions around it (`import_error`, `ensure_project_root`,
`resolve_with_extensions`, `try_resolve_with_extensions`) were **byte-identical**
copies, so this was never a deliberate difference of purpose. There was no
structural reason for it either: `tooling/loader.py` already imported
`ModuleLoader` from the module it was forking.

The fork is gone. These tests keep it gone — both by identity, and by behaviour
over a corpus of import forms, because "they are the same object" stops being
true the moment someone re-adds a wrapper.
"""

import os
import pathlib
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from nodus.runtime import module_loader as runtime_loader  # noqa: E402
from nodus.tooling import loader as tooling_loader  # noqa: E402

# Re-exported by `tooling/loader.py` because `nodus lsp` and
# `tooling/diagnostics.py` import them from there.
SHARED = ("resolve_import_path", "ensure_project_root", "import_error")

# Removed outright rather than re-exported: nothing outside the runtime consumes
# them, and `resolve_import_path` reaches them through its own module. They are
# checked below only for *absence*, so a future copy is still caught.
REMOVED = ("resolve_with_extensions", "try_resolve_with_extensions")


# closes: #598
class OneResolverTests(unittest.TestCase):

    def test_the_tooling_module_re_exports_the_runtime_functions(self):
        """Identity, not similarity. A copy that happens to agree today is what
        this was: four of the five were byte-identical and still drifted."""
        for name in SHARED:
            with self.subTest(function=name):
                self.assertIs(
                    getattr(tooling_loader, name), getattr(runtime_loader, name),
                    f"{name} is defined twice again — the editor and the runtime "
                    f"can now disagree about imports (#598)",
                )

    def test_the_tooling_module_defines_none_of_them_itself(self):
        """Asserted on the source, because a re-export can be shadowed by a
        later `def` in the same file and identity would still pass at import
        time only until someone reorders it."""
        source = (REPO / "src/nodus/tooling/loader.py").read_text(encoding="utf-8")
        for name in SHARED + REMOVED:
            with self.subTest(function=name):
                self.assertNotIn(f"\ndef {name}(", source,
                                 f"tooling/loader.py defines its own {name} again")


class BothPathsResolveTheSameCorpusTests(unittest.TestCase):
    """Behaviour, over the import forms the language has.

    Identity makes this redundant *today*. It is here for the day someone
    reintroduces a wrapper for a good reason — then this is what says whether the
    two still agree.
    """

    CORPUS = (
        "std:strings",          # a stdlib module
        "std:channel",          # built-ins masquerading as a module: a specific error
        "nodus-mcp",            # a pip-installed companion, via the nodus.nd entry point
        "no-such-package",      # a plain miss
        "std:",                 # malformed std import
        "bad:",                 # malformed package import
        "../escape",            # a relative path leaving the project root
    )

    def _resolve(self, fn, target, base):
        try:
            return ("ok", os.path.basename(fn(target, base, {"project_root": base},
                                              None, "t.nd")))
        except Exception as exc:  # both raise LangRuntimeError/LangSyntaxError
            return (type(exc).__name__, str(exc))

    def test_every_form_resolves_identically(self):
        with tempfile.TemporaryDirectory() as base:
            for target in self.CORPUS:
                with self.subTest(target=target):
                    self.assertEqual(
                        self._resolve(runtime_loader.resolve_import_path, target, base),
                        self._resolve(tooling_loader.resolve_import_path, target, base),
                        f'the editor and the runtime disagree about import "{target}"',
                    )

    def test_a_pip_installed_companion_resolves(self):
        """The case that made this user-visible.

        Skipped rather than silently passing when no companion is installed — a
        corpus entry that resolves to "not found" on both sides would agree while
        proving nothing.
        """
        from importlib.metadata import entry_points

        eps = entry_points()
        group = eps.select(group="nodus.nd") if hasattr(eps, "select") else eps.get("nodus.nd", [])
        names = [e.name for e in group]
        if not names:
            self.skipTest("no nodus.nd entry point installed in this environment")

        with tempfile.TemporaryDirectory() as base:
            kind, value = self._resolve(
                tooling_loader.resolve_import_path, names[0], base
            )
            self.assertEqual("ok", kind,
                             f'the editor could not resolve "{names[0]}", which the '
                             f"runtime resolves — that is the #598 symptom")

    def test_the_builtin_not_a_module_message_survives(self):
        """`import "std:channel"` gets a specific, actionable error rather than a
        generic miss. It was the runtime's alone; CLAUDE.md lists it as a quirk
        people hit routinely."""
        with tempfile.TemporaryDirectory() as base:
            _kind, message = self._resolve(
                tooling_loader.resolve_import_path, "std:channel", base
            )
            self.assertIn("built-in", message)
            self.assertNotIn("Import not found", message)


if __name__ == "__main__":
    unittest.main()
