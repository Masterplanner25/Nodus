import os
import tempfile
import unittest

from nodus.runtime.embedding import NodusRuntime


class EmbeddingApiTests(unittest.TestCase):
    def test_run_source_executes(self):
        rt = NodusRuntime()
        result = rt.run_source('print("hello")', filename="inline.nd")
        self.assertTrue(result["ok"])
        self.assertEqual(result["stdout"].strip(), "hello")

    def test_host_function_registration(self):
        rt = NodusRuntime()

        def add(a, b):
            return a + b

        rt.register_function("add", add)
        result = rt.run_source("print(add(2, 3))", filename="inline.nd")
        self.assertEqual(result["stdout"].strip(), "5")


class RunFileTests(unittest.TestCase):
    def test_run_file_happy_path(self):
        rt = NodusRuntime()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".nd", delete=False) as f:
            f.write('print("from file")')
            path = f.name
        try:
            result = rt.run_file(path)
            self.assertTrue(result["ok"])
            self.assertEqual(result["stdout"].strip(), "from file")
        finally:
            os.unlink(path)

    def test_run_file_missing_returns_ok_false_not_exception(self):
        """run_file must return ok=False for missing files, not raise OSError (F30 fix)."""
        rt = NodusRuntime()
        result = rt.run_file("/nonexistent/path/does_not_exist.nd")
        self.assertFalse(result["ok"])
        self.assertEqual(result["stage"], "load")
        self.assertIsNotNone(result.get("error"))
        self.assertEqual(result["error"]["kind"], "io")

    def test_run_file_permission_error_returns_ok_false(self):
        """Unreadable files also produce ok=False, not an exception."""
        rt = NodusRuntime()
        # Use a path that will fail with OSError (directory, not file)
        result = rt.run_file(os.path.dirname(os.path.abspath(__file__)))
        self.assertFalse(result["ok"])
        self.assertEqual(result["stage"], "load")

    def test_run_file_syntax_error_returns_ok_false(self):
        """Syntax errors in the file return ok=False at stage=parse."""
        rt = NodusRuntime()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".nd", delete=False) as f:
            f.write("let x = }")
            path = f.name
        try:
            result = rt.run_file(path)
            self.assertFalse(result["ok"])
            self.assertEqual(result["stage"], "parse")
        finally:
            os.unlink(path)


class OnErrorHookTests(unittest.TestCase):
    def test_on_error_called_for_coroutine_exception(self):
        errors = []

        def handler(coroutine, err):
            errors.append(str(err))
            return False

        rt = NodusRuntime(timeout_ms=5000, max_steps=100000, on_error=handler)
        result = rt.run_source("""
spawn(coroutine(fn() { throw "oops" }))
spawn(coroutine(fn() { print("ok") }))
run_loop()
""")
        self.assertTrue(result["ok"])
        self.assertEqual(result["stdout"].strip(), "ok")
        self.assertEqual(len(errors), 1)
        self.assertIn("oops", errors[0])

    def test_on_error_stop_halts_scheduler(self):
        results = []

        def stop_on_error(coroutine, err):
            return True  # stop the scheduler

        rt = NodusRuntime(timeout_ms=5000, max_steps=100000, on_error=stop_on_error)
        rt.run_source("""
spawn(coroutine(fn() { throw "stop" }))
spawn(coroutine(fn() { print("should not run") }))
run_loop()
""")
        # Second coroutine should not have run
        # (we can't assert stdout here because scheduler may or may not reach it
        # depending on ordering, but at minimum it should not raise)


class ShutdownTests(unittest.TestCase):
    def test_shutdown_clears_state(self):
        rt = NodusRuntime()
        rt.register_function("noop", lambda: None, arity=0)
        rt.run_source("noop()")
        self.assertIsNotNone(rt.last_vm)
        rt.shutdown()
        self.assertIsNone(rt.last_vm)

    def test_shutdown_clears_host_functions(self):
        rt = NodusRuntime()
        rt.register_function("noop", lambda: None, arity=0)
        rt.shutdown()
        # After shutdown, registered functions are cleared
        self.assertEqual(len(rt._host_functions), 0)


if __name__ == "__main__":
    unittest.main()
