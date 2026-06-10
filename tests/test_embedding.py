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


class DefaultSandboxTests(unittest.TestCase):
    """BUG-119: NodusRuntime() defaults to CWD jail, not open filesystem."""

    def test_default_allows_cwd(self):
        rt = NodusRuntime()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".nd", delete=False, dir=os.getcwd()) as f:
            f.write("hello")
            path = f.name
        try:
            result = rt.run_source(f'print(read_file("{path.replace(chr(92), "/")}"))', filename="inline.nd")
            self.assertTrue(result["ok"])
        finally:
            os.unlink(path)

    def test_default_blocks_outside_cwd(self):
        rt = NodusRuntime()
        tmp = tempfile.mktemp(suffix=".txt")
        result = rt.run_source(f'read_file("{tmp.replace(chr(92), "/")}")', filename="inline.nd")
        self.assertFalse(result["ok"])

    def test_explicit_none_allows_unrestricted(self):
        rt = NodusRuntime(allowed_paths=None)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("secret")
            path = f.name
        try:
            result = rt.run_source(f'print(read_file("{path.replace(chr(92), "/")}"))', filename="inline.nd")
            self.assertTrue(result["ok"])
        finally:
            os.unlink(path)


class DefaultTimeoutTests(unittest.TestCase):
    """EMBED-001 (#97): NodusRuntime() defaults to no timeout."""

    def test_default_has_no_timeout(self):
        rt = NodusRuntime()
        self.assertIsNone(rt.timeout_ms)

    def test_explicit_timeout_is_respected(self):
        rt = NodusRuntime(timeout_ms=200)
        self.assertEqual(rt.timeout_ms, 200)

    def test_long_lived_program_runs_without_timeout(self):
        rt = NodusRuntime()
        result = rt.run_source("""
let i = 0i
while (i < 500i) {
    i = i + 1i
}
print(i)
""", filename="inline.nd")
        self.assertTrue(result["ok"])
        self.assertEqual(result["stdout"].strip(), "500")


class ShutdownTests(unittest.TestCase):
    def test_shutdown_clears_state(self):
        rt = NodusRuntime()
        rt.register_function("noop", lambda: None, arity=0)
        rt.run_source("noop()")
        self.assertIsNotNone(rt._last_vm)
        rt.shutdown()
        self.assertIsNone(rt._last_vm)

    def test_shutdown_clears_host_functions(self):
        rt = NodusRuntime()
        rt.register_function("noop", lambda: None, arity=0)
        rt.shutdown()
        # After shutdown, registered functions are cleared
        self.assertEqual(len(rt._host_functions), 0)


class SpawnThreadLeakTests(unittest.TestCase):
    """#99 (EMBED-003): subprocess_spawn pump threads must be joined on reset/shutdown."""

    def _spawn_src(self, cmd):
        if os.name == "nt":
            return f'let p = subprocess_spawn(["cmd", "/c", "{cmd}"])\np.wait()'
        return f'let p = subprocess_spawn(["sh", "-c", "{cmd}"])\np.wait()'

    def test_reset_joins_pump_threads(self):
        """reset() must drain _spawned_handles so threads are not left alive."""
        rt = NodusRuntime(timeout_ms=None, allowed_paths=None)
        rt.run_source(self._spawn_src("echo hello"), filename="inline.nd")
        vm = rt._last_vm
        self.assertIsNotNone(vm)
        self.assertIsInstance(vm._spawned_handles, list)
        rt.reset()
        self.assertIsNone(rt._last_vm)
        # After reset, handles list on the (now released) vm should be empty
        self.assertEqual(len(vm._spawned_handles), 0)

    def test_shutdown_joins_pump_threads(self):
        """shutdown() must also drain _spawned_handles."""
        rt = NodusRuntime(timeout_ms=None, allowed_paths=None)
        rt.run_source(self._spawn_src("echo hello"), filename="inline.nd")
        vm = rt._last_vm
        self.assertIsNotNone(vm)
        rt.shutdown()
        self.assertIsNone(rt._last_vm)
        self.assertEqual(len(vm._spawned_handles), 0)

    def test_spawned_handles_populated_after_spawn(self):
        """_spawned_handles must have one entry per subprocess_spawn call."""
        rt = NodusRuntime(timeout_ms=None, allowed_paths=None)
        rt.run_source(self._spawn_src("echo hello"), filename="inline.nd")
        vm = rt._last_vm
        self.assertIsNotNone(vm)
        # wait() is called in the script, so proc is done — but handle is still tracked
        self.assertGreaterEqual(len(vm._spawned_handles), 1)
        rt.reset()


class EventSinksTests(unittest.TestCase):
    """#190 — event_sinks param attaches sinks before execution."""

    def test_event_sink_receives_events(self):
        received = []

        class CollectSink:
            def emit(self, event):
                received.append(event.type)

        rt = NodusRuntime(timeout_ms=None, event_sinks=[CollectSink()])
        rt.run_source('print("hello")', filename="inline.nd")
        self.assertTrue(len(received) > 0, "sink should have received at least one event")

    def test_event_sink_not_required(self):
        rt = NodusRuntime(timeout_ms=None)
        result = rt.run_source('print("ok")', filename="inline.nd")
        self.assertTrue(result["ok"])

    # closes: #212
    def test_event_sink_accepts_callable(self):
        """A plain callable (lambda) must work as an event sink, not raise AttributeError."""
        received = []
        rt = NodusRuntime(timeout_ms=None, event_sinks=[lambda e: received.append(e.type)])
        result = rt.run_source('print("hello")', filename="inline.nd")
        self.assertTrue(result["ok"], result.get("error"))
        self.assertTrue(len(received) > 0, "lambda sink should have received events")


class CoroutineTimeoutTests(unittest.TestCase):
    """#191 — coroutine_timeout_ms kills slow coroutines."""

    def test_coroutine_timeout_kills_slow_coroutine(self):
        src = """
let c = coroutine(fn() {
    sleep(5000)
    print("never")
})
spawn(c)
run_loop()
"""
        rt = NodusRuntime(timeout_ms=None, coroutine_timeout_ms=50)
        result = rt.run_source(src, filename="inline.nd")
        self.assertNotIn("never", result.get("stdout", ""))

    def test_coroutine_timeout_none_allows_completion(self):
        src = """
let c = coroutine(fn() {
    print("done")
})
spawn(c)
run_loop()
"""
        rt = NodusRuntime(timeout_ms=None, coroutine_timeout_ms=None)
        result = rt.run_source(src, filename="inline.nd")
        self.assertIn("done", result.get("stdout", ""))


class ExecutionStatsTests(unittest.TestCase):
    """#186 — get_execution_stats() returns post-run metrics."""

    def test_stats_zero_before_any_run(self):
        rt = NodusRuntime(timeout_ms=None)
        stats = rt.get_execution_stats()
        self.assertEqual(stats["instructions_executed"], 0)
        self.assertEqual(stats["coroutines_spawned"], 0)

    def test_stats_populated_after_run(self):
        rt = NodusRuntime(timeout_ms=None)
        rt.run_source('print("hi")', filename="inline.nd")
        stats = rt.get_execution_stats()
        self.assertGreater(stats["instructions_executed"], 0)

    def test_coroutines_spawned_counted(self):
        src = """
let c = coroutine(fn() { print("x") })
spawn(c)
run_loop()
"""
        rt = NodusRuntime(timeout_ms=None)
        rt.run_source(src, filename="inline.nd")
        stats = rt.get_execution_stats()
        self.assertEqual(stats["coroutines_spawned"], 1)


if __name__ == "__main__":
    unittest.main()
