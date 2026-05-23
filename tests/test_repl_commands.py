import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout

from nodus.runtime.module_loader import ModuleLoader
from nodus.tooling.repl import (
    HELP_TEXT,
    ReplCommand,
    ReplState,
    describe_runtime_type,
    execute_repl_command,
    format_expression_ast,
    is_complete_chunk,
    parse_repl_command,
    _execute_source,
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
        handled, output, should_exit, should_reload = execute_repl_command(make_state(), ":help")
        self.assertTrue(handled)
        self.assertEqual(output, HELP_TEXT)
        self.assertFalse(should_exit)
        self.assertFalse(should_reload)

    def test_help_includes_all_commands(self):
        self.assertIn(":modules", HELP_TEXT)
        self.assertIn(":reload", HELP_TEXT)
        self.assertIn(":ast", HELP_TEXT)
        self.assertIn(":dis", HELP_TEXT)
        self.assertIn(":type", HELP_TEXT)
        self.assertIn(":quit", HELP_TEXT)

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
        handled, output, should_exit, should_reload = execute_repl_command(make_state(), ":ast 1 + 2")
        self.assertTrue(handled)
        self.assertIn("Binary(+)", output)
        self.assertFalse(should_exit)
        self.assertFalse(should_reload)

    def test_dis_command(self):
        handled, output, should_exit, should_reload = execute_repl_command(make_state(), ":dis 1 + 2")
        self.assertTrue(handled)
        self.assertIn("PUSH_CONST 1.0", output)
        self.assertIn("PUSH_CONST 2.0", output)
        self.assertIn("ADD", output)
        self.assertIn("RETURN", output)
        self.assertFalse(should_exit)
        self.assertFalse(should_reload)

    def test_type_command_list(self):
        handled, output, should_exit, should_reload = execute_repl_command(make_state(), ":type [1, 2, 3]")
        self.assertTrue(handled)
        self.assertEqual(output, "List<number>")
        self.assertFalse(should_exit)
        self.assertFalse(should_reload)

    def test_type_command_map(self):
        handled, output, should_exit, should_reload = execute_repl_command(make_state(), ':type ({"a": 1})')
        self.assertTrue(handled)
        self.assertEqual(output, "Map<string,number>")
        self.assertFalse(should_exit)
        self.assertFalse(should_reload)

    def test_modules_command_empty(self):
        handled, output, should_exit, should_reload = execute_repl_command(make_state(), ":modules")
        self.assertTrue(handled)
        self.assertEqual(output, "No modules imported.")
        self.assertFalse(should_exit)
        self.assertFalse(should_reload)

    def test_modules_command_with_imports(self):
        state = ReplState(
            globals={},
            fn_defs={},
            import_state={"loaded": {"/path/to/lib.nd", "/path/to/utils.nd"}},
        )
        handled, output, should_exit, should_reload = execute_repl_command(state, ":modules")
        self.assertTrue(handled)
        self.assertIn("lib.nd", output)
        self.assertIn("utils.nd", output)
        self.assertFalse(should_exit)
        self.assertFalse(should_reload)

    def test_reload_command(self):
        handled, output, should_exit, should_reload = execute_repl_command(make_state(), ":reload")
        self.assertTrue(handled)
        self.assertIsNone(output)
        self.assertFalse(should_exit)
        self.assertTrue(should_reload)

    def test_unknown_command_message(self):
        handled, output, should_exit, should_reload = execute_repl_command(make_state(), ":xyz")
        self.assertTrue(handled)
        self.assertIn("Unknown REPL command ':xyz'", output)
        self.assertIn(":help", output)
        self.assertFalse(should_exit)
        self.assertFalse(should_reload)

    def test_describe_runtime_type_mixed_list(self):
        self.assertEqual(describe_runtime_type([1, "x"]), "List<mixed>")


class ReplErrorDeduplicationTests(unittest.TestCase):
    """Task 4.3: verify _execute_source raises rather than printing errors internally."""

    def test_missing_import_raises_not_prints(self):
        with tempfile.TemporaryDirectory() as td:
            state = ReplState(globals={}, fn_defs={}, import_state={"loaded": set(), "loading": set(), "exports": {}, "modules": {}, "module_ids": {}, "project_root": None})
            loader = ModuleLoader(project_root=td)
            buf = io.StringIO()
            with redirect_stdout(buf):
                with self.assertRaises(Exception):
                    _execute_source(state, loader, 'import { x } from "nonexistent_module_xyz"\n')
            self.assertEqual(buf.getvalue(), "", "error was printed inside _execute_source instead of raised")

    def test_runtime_error_raises_not_prints(self):
        state = ReplState(globals={}, fn_defs={}, import_state={"loaded": set(), "loading": set(), "exports": {}, "modules": {}, "module_ids": {}, "project_root": None})
        loader = ModuleLoader(project_root=os.getcwd())
        buf = io.StringIO()
        with redirect_stdout(buf):
            with self.assertRaises(Exception):
                _execute_source(state, loader, "let x = 1 / 0\n")
        self.assertEqual(buf.getvalue(), "", "error was printed inside _execute_source instead of raised")


if __name__ == "__main__":
    unittest.main()
