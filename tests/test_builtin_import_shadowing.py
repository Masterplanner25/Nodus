"""A named import of a builtin name is refused, not silently ignored (#680).

`VM._op_call` resolves `self.builtins` **before** locals and globals, so a name
bound by `import { name } from "..."` is never reached if a builtin shares it.
The program then fails somewhere else entirely — with an arity error naming
neither the import nor the shadowing:

    import { sleep } from "./mod.nd"
    sleep(1i, 2i)
    -> Call error: sleep expected 1 args, got 2

Found while adding a `join` builtin for #395/#157, which collided with
`std:strings.join` and broke this repo's own example. The verb was renamed, but
that treats one symptom: **adding any builtin is otherwise a silent breaking
change** for programs importing a name that matches it.

**The builtin has to keep winning, so this is refused rather than reordered.**
`register_function` refuses to override a builtin precisely so a host can rely on
a builtin name meaning the builtin — `tests/test_downstream_contracts.py` calls
that a security boundary, because a guest that could redefine a guarded name
would walk past the guard. Letting an *import* take the name is the same hole
through a second door.

Refusing cannot break a working program: the import already did nothing. What it
changes is a silent wrong answer into a message naming the collision and the
namespace form that does work.
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus.builtins.nodus_builtins import BUILTIN_NAMES  # noqa: E402
from nodus.runtime.embedding import NodusRuntime  # noqa: E402
from nodus.tooling.runner import run_source  # noqa: E402

_MODULE = (
    "export { sleep, helper }\n"
    'fn sleep(a, b) { return "mine" }\n'
    'fn helper() { return "ok" }\n'
)


def _project(tmp: str) -> str:
    with open(os.path.join(tmp, "mod.nd"), "w", encoding="utf-8") as handle:
        handle.write(_MODULE)
    return tmp


def _run(tmp: str, source: str, name: str = "main.nd") -> dict:
    path = os.path.join(tmp, name)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(source)
    result, _vm = run_source(source, filename=path, timeout_ms=None, project_root=tmp)
    return result


# closes: #680
class NamedImportOfABuiltinIsRefusedTests(unittest.TestCase):
    def test_the_import_is_refused_with_the_colliding_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            _project(tmp)
            result = _run(tmp, 'import { sleep } from "./mod.nd"\nfn main() { print(sleep(1i, 2i)) }\n')

        self.assertFalse(result["ok"])
        message = (result.get("error") or {}).get("message", "")
        self.assertIn("'sleep'", message)
        self.assertIn("built-in function name", message)

    def test_the_message_suggests_the_namespace_form_that_works(self):
        """A refusal without the alternative is a dead end. The namespace import
        binds the module, not the name, so it is unaffected by the collision."""
        with tempfile.TemporaryDirectory() as tmp:
            _project(tmp)
            result = _run(tmp, 'import { sleep } from "./mod.nd"\nfn main() { print(1i) }\n')

        message = (result.get("error") or {}).get("message", "")
        self.assertIn("as mod", message)
        self.assertIn("mod.sleep", message)

    def test_the_suggested_alias_is_a_legal_identifier(self):
        """The naive derivation (last path segment) yields `mod.nd`, which does
        not parse. A fix suggestion that is itself a syntax error is worse than
        no suggestion."""
        with tempfile.TemporaryDirectory() as tmp:
            _project(tmp)
            result = _run(tmp, 'import { sleep } from "./mod.nd"\nfn main() { print(1i) }\n')

        message = (result.get("error") or {}).get("message", "")
        self.assertNotIn("as mod.nd", message)
        self.assertNotIn("mod.nd.sleep", message)

    def test_nodus_check_reports_it_too(self):
        """It has to be visible before running, or the refusal only helps people
        who already hit the bug."""
        from nodus.tooling.runner import check_source

        with tempfile.TemporaryDirectory() as tmp:
            _project(tmp)
            path = os.path.join(tmp, "main.nd")
            source = 'import { sleep } from "./mod.nd"\nfn main() { print(1i) }\n'
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(source)
            result = check_source(source, filename=path, project_root=tmp)

        self.assertFalse(result["ok"])
        self.assertIn("built-in function name", (result.get("error") or {}).get("message", ""))


# closes: #680
class NonCollidingImportsAreUntouchedTests(unittest.TestCase):
    """The compatibility half, and the larger one: only a name that actually
    collides is refused."""

    def test_a_named_import_that_does_not_collide_still_works(self):
        with tempfile.TemporaryDirectory() as tmp:
            _project(tmp)
            result = _run(tmp, 'import { helper } from "./mod.nd"\nfn main() { print(helper()) }\n')

        self.assertTrue(result["ok"], result.get("error"))
        self.assertIn("ok", result.get("stdout") or "")

    def test_the_namespace_form_of_a_colliding_name_works(self):
        """`std:strings.join`, `std:fs.exists`, `async.sleep` — thirteen stdlib
        functions share a builtin name, and every one of them is reached this
        way. Refusing the namespace form would break the stdlib."""
        result = NodusRuntime(timeout_ms=None).run_source(
            'import "std:strings" as strings\n'
            'fn main() { print(strings.join(["a", "b"], "-")) }\n'
        )
        self.assertTrue(result["ok"], result.get("error"))
        self.assertIn("a-b", result.get("stdout") or "")

    def test_a_module_defining_the_name_itself_is_unaffected(self):
        """Only *imports* are refused. A module-level `fn` of the same name is
        resolved before builtins by `_op_call`, so it already wins and always
        did — a different question with a different answer."""
        result = NodusRuntime(timeout_ms=None).run_source(
            'fn exists(a, b) { return "mine" }\n'
            "fn main() { print(exists(1i, 2i)) }\n"
        )
        self.assertTrue(result["ok"], result.get("error"))
        self.assertIn("mine", result.get("stdout") or "")


# closes: #680
class CollisionSurfaceTests(unittest.TestCase):
    """How large the collision surface actually is, asserted rather than assumed.

    Thirteen stdlib exports share a builtin name. That is why the refusal names
    the namespace alternative instead of simply saying no: the namespace form is
    how every one of them is meant to be reached.
    """

    def _stdlib_collisions(self) -> dict[str, list[str]]:
        import pathlib
        import re

        root = pathlib.Path(__file__).resolve().parents[1] / "src" / "nodus" / "stdlib"
        found: dict[str, list[str]] = {}
        for path in root.glob("*.nd"):
            text = path.read_text(encoding="utf-8", errors="replace")
            for match in re.finditer(r"^fn ([a-z_][a-z0-9_]*)", text, re.M):
                if match.group(1) in BUILTIN_NAMES:
                    found.setdefault(match.group(1), []).append(path.stem)
        return found

    def test_the_known_collisions_are_still_reachable_by_namespace(self):
        collisions = self._stdlib_collisions()
        self.assertIn("sleep", collisions)
        self.assertIn("exists", collisions)
        self.assertGreaterEqual(
            len(collisions), 10,
            "the collision surface shrank -- if a builtin or stdlib export was "
            "renamed, check the refusal message still names a real alternative",
        )


if __name__ == "__main__":
    unittest.main()
