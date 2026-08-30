"""`extern`: a program declares the host surface it requires (#489).

Before this, a `.nd` program calling host-provided functions had no way to say
so, and two things followed:

1. `nodus check` could not catch a typo in any program that uses host functions,
   because it could not tell a typo from a name the host would supply;
2. a host could not verify a program before running it — you found out when the
   call failed, partway through a run that had already had effects.

Both are closed by one declaration, and **strictness is per file**: a program
with no `extern` behaves exactly as it did. That is the compatible answer the
issue reaches, and it is why the pre-existing permissiveness is still pinned (in
`test_check_enters_step_bodies.py`) rather than deleted.

Worth recording, because the issue's own cross-note says otherwise: that pinned
test does **not** flip. Its program declares nothing, so it stays accepted, and
it becomes the control proving undeclared files are untouched.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus.frontend.lexer import tokenize  # noqa: E402
from nodus.frontend.parser import Parser  # noqa: E402
from nodus.runtime.embedding import NodusRuntime  # noqa: E402
from nodus.tooling.formatter import format_source  # noqa: E402
from nodus.tooling.runner import check_source, run_source  # noqa: E402

DECLARED = 'extern delegate(who: string, task: string) -> string\n'
PROGRAM = DECLARED + 'fn main() { print(delegate("researcher", "find it")) }\n'


class ParsingTests(unittest.TestCase):
    def test_a_declaration_parses_with_types_and_a_return(self):
        stmts = Parser(tokenize(DECLARED)).parse()
        self.assertEqual(len(stmts), 1)
        self.assertEqual(stmts[0].name, "delegate")
        self.assertEqual([p.name for p in stmts[0].params], ["who", "task"])
        self.assertEqual(stmts[0].return_type, "string")

    def test_types_and_return_are_optional(self):
        stmts = Parser(tokenize("extern ping()\n")).parse()
        self.assertEqual(stmts[0].params, [])
        self.assertIsNone(stmts[0].return_type)

    def test_extern_is_still_usable_as_an_identifier(self):
        """Contextual, like every keyword added since 4.1.0.

        Reserving it would break any program that used `extern` as a name, for
        no gain — the declaration is unambiguous from its position.
        """
        result = NodusRuntime(timeout_ms=None).run_source(
            "fn main() { let extern = 41i; print(extern + 1i) }"
        )
        self.assertTrue(result["ok"], result.get("error"))
        self.assertIn("42", result.get("stdout") or "")

    def test_a_declaration_inside_a_block_is_refused(self):
        with self.assertRaises(Exception) as caught:
            Parser(tokenize("fn main() { extern foo() }")).parse()
        self.assertIn("top of the file", str(caught.exception))

    def test_a_duplicate_parameter_is_refused(self):
        with self.assertRaises(Exception) as caught:
            Parser(tokenize("extern f(a: string, a: int)")).parse()
        self.assertIn("twice", str(caught.exception))

    def test_an_unknown_type_is_refused_rather_than_warned(self):
        """An error on arrival, unlike #609's staged annotation warning.

        `extern` is new, so nothing can already rely on a misspelling being
        ignored — the same reasoning that made `returns:` an error in #479. A
        type that silently meant "any" would make the declaration inert.
        """
        with self.assertRaises(Exception) as caught:
            Parser(tokenize("extern f(a: strng)")).parse()
        self.assertIn("did you mean 'string'", str(caught.exception))

    def test_the_formatter_round_trips_a_declaration(self):
        once = format_source("extern  delegate(who:string,task:string)->string\n")
        self.assertEqual(once.strip(), "extern delegate(who: string, task: string) -> string")
        self.assertEqual(format_source(once), once)


class CheckStrictnessTests(unittest.TestCase):
    # closes: #489
    def test_declaring_a_surface_makes_an_unknown_name_an_error(self):
        """The reported gap: `nodus check` could not tell a typo from a host call."""
        typo = DECLARED + 'fn main() { print(delegat("a", "b")) }\n'
        result = check_source(typo, filename="t.nd")
        self.assertFalse(result["ok"])
        self.assertIn("delegat", (result.get("error") or {}).get("message", ""))

    def test_a_declared_name_is_accepted(self):
        self.assertTrue(check_source(PROGRAM, filename="t.nd")["ok"])

    def test_a_file_with_no_extern_is_unchanged(self):
        """The compatibility guarantee. Strictness is opt-in per file.

        Without this the feature would reject every embedded program written
        before declarations existed.
        """
        result = check_source(
            'fn main() { print(totally_made_up_function(1i, 2i)) }\n', filename="t.nd"
        )
        self.assertTrue(result["ok"], result.get("error"))


class HostPreflightTests(unittest.TestCase):
    def test_an_unregistered_extern_is_refused_before_running(self):
        result = NodusRuntime(timeout_ms=None).run_source(PROGRAM)
        self.assertFalse(result["ok"])
        self.assertIn("has not registered", (result.get("error") or {}).get("message", ""))

    def test_a_registered_extern_runs(self):
        runtime = NodusRuntime(timeout_ms=None)
        runtime.register_function(
            "delegate", lambda who, task: f"{who} handled '{task}'", arity=2
        )
        result = runtime.run_source(PROGRAM)
        self.assertTrue(result["ok"], result.get("error"))
        self.assertIn("researcher handled 'find it'", result.get("stdout") or "")

    def test_nothing_runs_when_a_declaration_is_unmet(self):
        """The point of checking up front rather than at the call.

        A behavioural assertion on `ok` alone would pass even if the refusal
        happened after the program had already had effects.
        """
        calls: list[str] = []
        runtime = NodusRuntime(timeout_ms=None)
        runtime.register_function(
            "delegate", lambda who, task: calls.append(task) or "x", arity=2
        )
        result = runtime.run_source(
            DECLARED + "extern absent() -> nil\n"
            'fn main() { print(delegate("a", "b")) }\n'
        )
        self.assertFalse(result["ok"])
        self.assertIn("absent", (result.get("error") or {}).get("message", ""))
        self.assertEqual(calls, [], "the program ran despite an unmet declaration")

    def test_a_builtin_counts_as_supplied(self):
        """Declaring a builtin is redundant, not wrong.

        Refusing it would make the declaration a trap for anyone who wrote down
        their whole surface.

        Note a builtin whose name is a *reserved* token (`print`) cannot be
        spelled as an extern at all — it is not an identifier — which is a
        property of the keyword, not of this feature.
        """
        result = NodusRuntime(timeout_ms=None).run_source(
            'extern len(value: any) -> int\nfn main() { print(len("ok")) }\n'
        )
        self.assertTrue(result["ok"], result.get("error"))

    def test_a_program_with_no_extern_is_not_pre_flighted(self):
        runtime = NodusRuntime(timeout_ms=None)
        runtime.register_function("delegate", lambda who, task: "ok", arity=2)
        result = runtime.run_source('fn main() { print(delegate("a", "b")) }')
        self.assertTrue(result["ok"], result.get("error"))


class CliCallSiteMessageTests(unittest.TestCase):
    """`nodus run` does not pre-flight, and it should not (#664).

    The CLI has no way to register a host function, so pre-flighting the way
    `NodusRuntime` does would refuse *every* program declaring an extern --
    breaking the workflow the feature exists for, which is writing a program
    locally before embedding it. The divergence is the decision; the message
    was the defect. A user who has just written `extern notify(...)` was told
    `Undefined function: notify`, which is the pre-#489 wording and mentions
    nothing they wrote.
    """

    def _write(self, root, code, name="callext.nd"):
        path = os.path.join(root, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(code)
        return path

    def _run(self, root, path):
        """Run an already-written file.

        Rewriting the file per run is what a first draft of this did, and it
        moves the mtime -- which is half the bytecode cache key, so every run
        was cold and the warm-path test below could not fail. Write once, run
        twice.
        """
        with open(path, "r", encoding="utf-8") as handle:
            code = handle.read()
        result, _vm = run_source(code, filename=path, timeout_ms=None, project_root=root)
        return result

    # closes: #664
    def test_the_call_site_error_names_the_declaration(self):
        with tempfile.TemporaryDirectory() as root:
            result = self._run(root, self._write(root, PROGRAM))
        self.assertFalse(result["ok"])
        message = (result.get("error") or {}).get("message", "")
        self.assertIn("Undefined function: delegate", message)
        self.assertIn("extern", message)
        self.assertIn("register_function", message)

    def test_the_hint_survives_the_bytecode_cache(self):
        """The second run of any script reads the cache, and a cached module is
        never parsed. Deriving the declaration from the AST alone would give the
        hint cold and drop it warm -- #394, #521 and #400 were each half-fixed
        exactly that way. Asserting on run 2 is the whole test."""
        with tempfile.TemporaryDirectory() as root:
            path = self._write(root, PROGRAM)
            first = self._run(root, path)
            self.assertTrue(
                os.path.isdir(os.path.join(root, ".nodus", "cache")),
                "no cache was written, so run 2 would not exercise the warm path",
            )
            second = self._run(root, path)
        for label, result in (("cold", first), ("warm", second)):
            with self.subTest(run=label):
                self.assertIn("extern", (result.get("error") or {}).get("message", ""))

    def test_a_name_nobody_declared_keeps_the_plain_message(self):
        """The hint is for a name the program said it expected. An ordinary typo
        must not be told to go register a host function."""
        with tempfile.TemporaryDirectory() as root:
            result = self._run(
                root, self._write(root, "fn main() { print(notify(1i)) }\n", name="typo.nd")
            )
        self.assertFalse(result["ok"])
        message = (result.get("error") or {}).get("message", "")
        self.assertIn("Undefined function: notify", message)
        self.assertNotIn("extern", message)

    def test_a_declared_name_used_as_a_value_gets_the_hint_too(self):
        """Two undefined-name messages, one question. Naming the declaration at
        the call site and not in value position is the sibling-path shape."""
        with tempfile.TemporaryDirectory() as root:
            result = self._run(
                root,
                self._write(
                    root,
                    DECLARED + "fn main() { let f = delegate; print(f) }\n",
                    name="valext.nd",
                ),
            )
        self.assertFalse(result["ok"])
        message = (result.get("error") or {}).get("message", "")
        self.assertIn("Undefined variable: delegate", message)
        self.assertIn("register_function", message)


class KeywordIsDiscoverableTests(unittest.TestCase):
    def test_extern_is_named_in_the_keyword_set(self):
        """#480's lesson: a word the parser matches from a bare literal is
        invisible to editor grammars, docs and `nodus_gate --consumers`."""
        from nodus.frontend.lexer import ALL_KEYWORDS, EXTERN_KEYWORDS

        self.assertIn("extern", EXTERN_KEYWORDS)
        self.assertIn("extern", ALL_KEYWORDS)


if __name__ == "__main__":
    unittest.main()
