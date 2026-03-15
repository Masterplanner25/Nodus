import unittest

from nodus.tooling.repl import (
    HELP_TEXT,
    ReplCommand,
    ReplState,
    describe_runtime_type,
    execute_repl_command,
    format_expression_ast,
    is_complete_chunk,
    parse_repl_command,
)


def make_state() -> ReplState:
    return ReplState(globals={}, fn_defs={}, import_state={})


class ReplCommandTests(unittest.TestCase):
    def test_parse_repl_command(self):
        command = parse_repl_command(":ast 1 + 2")
        self.assertEqual(command, ReplCommand(name="ast", arg="1 + 2"))
        self.assertIsNone(parse_repl_command("1 + 2"))

    def test_multiline_completion_tracks_braces(self):
        self.assertFalse(is_complete_chunk(["fn add(a, b) {", "return a + b"]))
        self.assertTrue(is_complete_chunk(["fn add(a, b) {", "return a + b", "}"]))

    def test_help_command(self):
        handled, output, should_exit = execute_repl_command(make_state(), ":help")
        self.assertTrue(handled)
        self.assertEqual(output, HELP_TEXT)
        self.assertFalse(should_exit)

    def test_ast_output(self):
        output = format_expression_ast("1 + 2 * 3")
        self.assertEqual(
            output,
            "\n".join(
                [
                    "Binary(+)",
                    "  Number(1)",
                    "  Binary(*)",
                    "    Number(2)",
                    "    Number(3)",
                ]
            ),
        )

    def test_ast_command(self):
        handled, output, should_exit = execute_repl_command(make_state(), ":ast 1 + 2")
        self.assertTrue(handled)
        self.assertIn("Binary(+)", output)
        self.assertFalse(should_exit)

    def test_dis_command(self):
        handled, output, should_exit = execute_repl_command(make_state(), ":dis 1 + 2")
        self.assertTrue(handled)
        self.assertIn("PUSH_CONST 1.0", output)
        self.assertIn("PUSH_CONST 2.0", output)
        self.assertIn("ADD", output)
        self.assertIn("RETURN", output)
        self.assertFalse(should_exit)

    def test_type_command_list(self):
        handled, output, should_exit = execute_repl_command(make_state(), ":type [1, 2, 3]")
        self.assertTrue(handled)
        self.assertEqual(output, "List<number>")
        self.assertFalse(should_exit)

    def test_type_command_map(self):
        handled, output, should_exit = execute_repl_command(make_state(), ':type ({"a": 1})')
        self.assertTrue(handled)
        self.assertEqual(output, "Map<string,number>")
        self.assertFalse(should_exit)

    def test_describe_runtime_type_mixed_list(self):
        self.assertEqual(describe_runtime_type([1, "x"]), "List<mixed>")


if __name__ == "__main__":
    unittest.main()
