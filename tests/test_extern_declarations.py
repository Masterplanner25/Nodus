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
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus.frontend.lexer import tokenize  # noqa: E402
from nodus.frontend.parser import Parser  # noqa: E402
from nodus.runtime.embedding import NodusRuntime  # noqa: E402
from nodus.tooling.formatter import format_source  # noqa: E402
from nodus.tooling.runner import check_source  # noqa: E402

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


class KeywordIsDiscoverableTests(unittest.TestCase):
    def test_extern_is_named_in_the_keyword_set(self):
        """#480's lesson: a word the parser matches from a bare literal is
        invisible to editor grammars, docs and `nodus_gate --consumers`."""
        from nodus.frontend.lexer import ALL_KEYWORDS, EXTERN_KEYWORDS

        self.assertIn("extern", EXTERN_KEYWORDS)
        self.assertIn("extern", ALL_KEYWORDS)


if __name__ == "__main__":
    unittest.main()
