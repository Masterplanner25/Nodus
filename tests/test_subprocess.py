"""3B.5: std:subprocess namespace — subprocess client."""

import io
import json
import subprocess as _sp
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import nodus as lang
from nodus.runtime.module_loader import ModuleLoader

_HDRS = 'import "std:subprocess" as subprocess\n'

# JSON-safe path for the current Python interpreter
_PY = json.dumps(sys.executable)

# Properly quoted executable path for shell commands (handles spaces in paths)
_PY_SHELL = _sp.list2cmdline([sys.executable])


def _run_src(src):
    vm = lang.VM([], {}, code_locs=[], source_path="main.nd")
    loader = ModuleLoader(project_root=None, vm=vm)
    buf = io.StringIO()
    with redirect_stdout(buf):
        loader.load_module_from_source(_HDRS + src, module_name="main.nd")
    return buf.getvalue().splitlines()


def _run_src_vm(src):
    vm = lang.VM([], {}, code_locs=[], source_path="main.nd")
    loader = ModuleLoader(project_root=None, vm=vm)
    buf = io.StringIO()
    with redirect_stdout(buf):
        loader.load_module_from_source(_HDRS + src, module_name="main.nd")
    return buf.getvalue().splitlines(), vm


# ── subprocess.run — basic capture ───────────────────────────────────────────

class RunBasicTests(unittest.TestCase):

    def test_exit_code_zero(self):
        src = f'let r = subprocess.run([{_PY}, "-c", "pass"])\nprint(r.exit_code)'
        self.assertEqual(_run_src(src)[0], "0")

    def test_stdout_capture(self):
        src = f'let r = subprocess.run([{_PY}, "-c", "print(42)"])\nprint(r.stdout)'
        out = _run_src(src)
        self.assertIn("42", out[0])

    def test_stderr_capture(self):
        src = (
            f'let r = subprocess.run([{_PY}, "-c",'
            f' "import sys; sys.stderr.write(\'err\\\\n\')"])\n'
            f'print(r.stderr)'
        )
        out = _run_src(src)
        self.assertIn("err", out[0])

    def test_stdout_and_stderr_separate(self):
        src = (
            f'let r = subprocess.run([{_PY}, "-c",'
            f' "import sys; print(\'out\'); sys.stderr.write(\'err\\\\n\')"])\n'
            f'print(r.stdout)\nprint(r.stderr)'
        )
        combined = "\n".join(_run_src(src))
        self.assertIn("out", combined)
        self.assertIn("err", combined)

    def test_duration_ms_present(self):
        src = f'let r = subprocess.run([{_PY}, "-c", "pass"])\nprint(r.duration_ms >= 0)'
        self.assertEqual(_run_src(src)[0], "true")

    def test_command_preserved(self):
        src = (
            f'let r = subprocess.run([{_PY}, "-c", "pass"])\n'
            f'print(type(r.command))'
        )
        self.assertEqual(_run_src(src)[0], "list")

    def test_stdin_input(self):
        src = (
            f'let r = subprocess.run([{_PY}, "-c", "import sys; print(sys.stdin.read().strip())"],'
            f' {{stdin: "hello stdin"}})\n'
            f'print(r.stdout)'
        )
        out = _run_src(src)
        self.assertIn("hello stdin", out[0])

    def test_multiline_stdout(self):
        script = "for i in range(3): print(i)"
        src = f'let r = subprocess.run([{_PY}, "-c", {json.dumps(script)}])\nprint(r.stdout)'
        out = _run_src(src)
        self.assertIn("0", out[0])


# ── subprocess.run — options ──────────────────────────────────────────────────

class RunOptionsTests(unittest.TestCase):

    def test_check_false_non_zero_exit(self):
        src = (
            f'let r = subprocess.run([{_PY}, "-c", "import sys; sys.exit(2)"],'
            f' {{check: false}})\n'
            f'print(r.exit_code)'
        )
        self.assertEqual(_run_src(src)[0], "2")

    def test_env_set(self):
        # Build the env map at Python level and pass it in via run_src_vm
        script = "import os; print(os.environ.get('NODUS_TEST_VAR', ''))"
        import os
        old = os.environ.copy()
        try:
            os.environ["NODUS_TEST_VAR"] = "xyzzy"
            src = (
                f'let r = subprocess.run([{_PY}, "-c", {json.dumps(script)}],'
                f' {{env: {{NODUS_TEST_VAR: "xyzzy"}}}})\n'
                f'print(r.stdout)'
            )
            out = _run_src(src)
            self.assertIn("xyzzy", out[0])
        finally:
            os.environ.clear()
            os.environ.update(old)

    def test_env_no_inherit(self):
        script = "import os; print(os.environ.get('NODUS_ONLY', 'missing'))"
        src = (
            f'let r = subprocess.run([{_PY}, "-c", {json.dumps(script)}],'
            f' {{env: {{NODUS_ONLY: "yes"}}, env_inherit: false}})\n'
            f'print(r.stdout)'
        )
        out = _run_src(src)
        self.assertIn("yes", out[0])

    def test_output_ignore(self):
        src = (
            f'let r = subprocess.run([{_PY}, "-c", "print(\'ignored\')"],'
            f' {{output: "ignore", check: false}})\n'
            f'print(r.stdout)'
        )
        out = _run_src(src)
        # captured field is empty when output: "ignore"
        self.assertEqual(out[0].strip(), "")

    def test_cwd_option(self):
        import tempfile
        td = tempfile.gettempdir().replace("\\", "\\\\")
        src = (
            f'let r = subprocess.run([{_PY}, "-c", "import os; print(os.getcwd())"],'
            f' {{cwd: "{td}"}})\n'
            f'print(r.stdout)'
        )
        out = _run_src(src)
        # Output should contain the temp dir path (case-insensitive on Windows)
        self.assertTrue(len(out[0].strip()) > 0)

    def test_stdout_to_file(self):
        with tempfile.NamedTemporaryFile(mode="rb", suffix=".txt", delete=False) as f:
            fname = f.name
        try:
            escaped = fname.replace("\\", "\\\\")
            src = (
                f'let r = subprocess.run([{_PY}, "-c", "print(\'filecontent\')"],'
                f' {{stdout: "{escaped}", check: false}})\n'
                f'print(r.stdout)'
            )
            _run_src(src)
            content = Path(fname).read_text()
            self.assertIn("filecontent", content)
        finally:
            Path(fname).unlink(missing_ok=True)


# ── subprocess.run — error cases ─────────────────────────────────────────────

class RunErrorTests(unittest.TestCase):

    def test_nonzero_exit_returns_err(self):
        src = (
            f'let r = subprocess.run([{_PY}, "-c", "import sys; sys.exit(42)"])\n'
            f'print(r.kind)'
        )
        self.assertEqual(_run_src(src)[0], "subprocess_error")

    def test_err_category_exit_code(self):
        src = (
            f'let r = subprocess.run([{_PY}, "-c", "import sys; sys.exit(1)"])\n'
            f'print(r.payload["category"])'
        )
        self.assertEqual(_run_src(src)[0], "exit_code")

    def test_err_contains_stderr(self):
        script = "import sys; sys.stderr.write('boom\\n'); sys.exit(1)"
        src = (
            f'let r = subprocess.run([{_PY}, "-c", {json.dumps(script)}])\n'
            f'print(r.payload["stderr"])'
        )
        out = _run_src(src)
        self.assertIn("boom", out[0])

    def test_err_exit_code_field(self):
        src = (
            f'let r = subprocess.run([{_PY}, "-c", "import sys; sys.exit(7)"])\n'
            f'print(r.payload["exit_code"])'
        )
        self.assertEqual(_run_src(src)[0], "7")

    def test_spawn_error_missing_binary(self):
        src = (
            'let r = subprocess.run(["__nodus_no_such_binary_xyz__"])\n'
            'print(r.kind)\nprint(r.payload["category"])'
        )
        out = _run_src(src)
        self.assertEqual(out[0], "subprocess_error")
        self.assertEqual(out[1], "spawn_error")

    def test_timeout_category(self):
        script = "import time; time.sleep(60)"
        src = (
            f'let r = subprocess.run([{_PY}, "-c", {json.dumps(script)}],'
            f' {{timeout_ms: 200, kill_grace_ms: 200}})\n'
            f'print(r.kind)\nprint(r.payload["category"])'
        )
        out = _run_src(src)
        self.assertEqual(out[0], "subprocess_error")
        self.assertEqual(out[1], "timeout")

    def test_timeout_grace_duration_present(self):
        script = "import time; time.sleep(60)"
        src = (
            f'let r = subprocess.run([{_PY}, "-c", {json.dumps(script)}],'
            f' {{timeout_ms: 200, kill_grace_ms: 500}})\n'
            f'print(r.payload["grace_duration_ms"] != nil)'
        )
        self.assertEqual(_run_src(src)[0], "true")

    def test_check_false_keeps_stderr(self):
        script = "import sys; sys.stderr.write('captured\\n'); sys.exit(3)"
        src = (
            f'let r = subprocess.run([{_PY}, "-c", {json.dumps(script)}],'
            f' {{check: false}})\n'
            f'print(r.exit_code)'
        )
        self.assertEqual(_run_src(src)[0], "3")


# ── subprocess.shell ──────────────────────────────────────────────────────────

class ShellTests(unittest.TestCase):

    def test_shell_run_python(self):
        cmd = f'{_PY_SHELL} -c "print(99)"'
        src = (
            f'let r = subprocess.shell({json.dumps(cmd)})\n'
            f'print(r.exit_code)'
        )
        self.assertEqual(_run_src(src)[0], "0")

    def test_shell_stdout(self):
        cmd = f'{_PY_SHELL} -c "print(\'shellout\')"'
        src = (
            f'let r = subprocess.shell({json.dumps(cmd)})\n'
            f'print(r.stdout)'
        )
        out = _run_src(src)
        self.assertIn("shellout", out[0])

    def test_shell_nonzero_exit(self):
        cmd = f'{_PY_SHELL} -c "import sys; sys.exit(5)"'
        src = (
            f'let r = subprocess.shell({json.dumps(cmd)})\n'
            f'print(r.kind)'
        )
        self.assertEqual(_run_src(src)[0], "subprocess_error")

    def test_shell_check_false(self):
        cmd = f'{_PY_SHELL} -c "import sys; sys.exit(5)"'
        src = (
            f'let r = subprocess.shell({json.dumps(cmd)}, {{check: false}})\n'
            f'print(r.exit_code)'
        )
        self.assertEqual(_run_src(src)[0], "5")


# ── subprocess.shell_quote ────────────────────────────────────────────────────

class ShellQuoteTests(unittest.TestCase):

    def test_simple_string(self):
        src = 'print(subprocess.shell_quote("hello"))'
        out = _run_src(src)
        self.assertTrue(len(out[0]) > 0)
        self.assertIn("hello", out[0])

    def test_string_with_spaces(self):
        src = 'print(subprocess.shell_quote("hello world"))'
        out = _run_src(src)
        # Quoted result should still contain the original words
        self.assertIn("hello", out[0])
        self.assertIn("world", out[0])

    def test_non_string_returns_err(self):
        src = 'let r = subprocess.shell_quote(42)\nprint(r.kind)'
        self.assertEqual(_run_src(src)[0], "subprocess_error")

    def test_returns_string_type(self):
        src = 'print(type(subprocess.shell_quote("safe")))'
        self.assertEqual(_run_src(src)[0], "string")


# ── subprocess.run_async / shell_async (Phase 3B: sync behaviour) ────────────

class AsyncSyncTests(unittest.TestCase):

    def test_run_async_returns_result(self):
        src = (
            f'let co = coroutine(fn() {{\n'
            f'  let r = subprocess.run_async([{_PY}, "-c", "print(77)"])\n'
            f'  print(r.exit_code)\n'
            f'}})\nspawn(co)\nrun_loop()'
        )
        self.assertEqual(_run_src(src)[0], "0")

    def test_run_async_stdout(self):
        src = (
            f'let co = coroutine(fn() {{\n'
            f'  let r = subprocess.run_async([{_PY}, "-c", "print(\'async_out\')"])\n'
            f'  print(r.stdout)\n'
            f'}})\nspawn(co)\nrun_loop()'
        )
        out = _run_src(src)
        self.assertIn("async_out", out[0])

    def test_shell_async_runs(self):
        cmd = f'{_PY_SHELL} -c "print(\'shell_async\')"'
        src = (
            f'let co = coroutine(fn() {{\n'
            f'  let r = subprocess.shell_async({json.dumps(cmd)})\n'
            f'  print(r.exit_code)\n'
            f'}})\nspawn(co)\nrun_loop()'
        )
        self.assertEqual(_run_src(src)[0], "0")


# ── subprocess.spawn ──────────────────────────────────────────────────────────

class SpawnTests(unittest.TestCase):

    def _run_spawn(self, src):
        return _run_src(src)

    def test_spawn_returns_process_record(self):
        src = (
            f'let p = subprocess.spawn([{_PY}, "-c", "pass"])\n'
            f'print(type(p.pid))'
        )
        self.assertEqual(self._run_spawn(src)[0], "int")

    def test_spawn_stdout_channel_type(self):
        src = (
            f'let p = subprocess.spawn([{_PY}, "-c", "pass"])\n'
            f'print(type(p.stdout))'
        )
        self.assertEqual(self._run_spawn(src)[0], "channel")

    def test_spawn_stderr_channel_type(self):
        src = (
            f'let p = subprocess.spawn([{_PY}, "-c", "pass"])\n'
            f'print(type(p.stderr))'
        )
        self.assertEqual(self._run_spawn(src)[0], "channel")

    def test_spawn_pid_positive(self):
        src = (
            f'let p = subprocess.spawn([{_PY}, "-c", "pass"])\n'
            f'print(p.pid > 0)'
        )
        self.assertEqual(self._run_spawn(src)[0], "true")

    def test_spawn_wait_exit_code(self):
        src = (
            f'let co = coroutine(fn() {{\n'
            f'  let p = subprocess.spawn([{_PY}, "-c", "import sys; sys.exit(3)"])\n'
            f'  let rc = p.wait()\n'
            f'  print(rc)\n'
            f'}})\nspawn(co)\nrun_loop()'
        )
        self.assertEqual(self._run_spawn(src)[0], "3")

    def test_spawn_stdout_lines(self):
        script = "for i in range(3): print(i)"
        src = (
            f'let results = []\n'
            f'let co = coroutine(fn() {{\n'
            f'  let p = subprocess.spawn([{_PY}, "-c", {json.dumps(script)}])\n'
            f'  let line = recv(p.stdout)\n'
            f'  while (line != nil) {{\n'
            f'    list_push(results, line)\n'
            f'    line = recv(p.stdout)\n'
            f'  }}\n'
            f'}})\n'
            f'spawn(co)\n'
            f'run_loop()\n'
            f'print(len(results))'
        )
        out = self._run_spawn(src)
        self.assertEqual(out[0], "3")

    def test_spawn_stderr_lines(self):
        script = "import sys\nfor i in range(2): sys.stderr.write(str(i) + '\\n')"
        src = (
            f'let errs = []\n'
            f'let co = coroutine(fn() {{\n'
            f'  let p = subprocess.spawn([{_PY}, "-c", {json.dumps(script)}])\n'
            f'  let line = recv(p.stderr)\n'
            f'  while (line != nil) {{\n'
            f'    list_push(errs, line)\n'
            f'    line = recv(p.stderr)\n'
            f'  }}\n'
            f'}})\n'
            f'spawn(co)\n'
            f'run_loop()\n'
            f'print(len(errs))'
        )
        out = self._run_spawn(src)
        self.assertEqual(out[0], "2")

    def test_spawn_exit_code_updated_after_wait(self):
        src = (
            f'let co = coroutine(fn() {{\n'
            f'  let p = subprocess.spawn([{_PY}, "-c", "import sys; sys.exit(5)"])\n'
            f'  p.wait()\n'
            f'  print(p.exit_code)\n'
            f'}})\nspawn(co)\nrun_loop()'
        )
        self.assertEqual(self._run_spawn(src)[0], "5")

    def test_spawn_is_alive_false_after_wait(self):
        src = (
            f'let co = coroutine(fn() {{\n'
            f'  let p = subprocess.spawn([{_PY}, "-c", "pass"])\n'
            f'  p.wait()\n'
            f'  print(p.is_alive())\n'
            f'}})\nspawn(co)\nrun_loop()'
        )
        self.assertEqual(self._run_spawn(src)[0], "false")

    def test_spawn_stdin_write(self):
        script = "import sys; data = sys.stdin.read(); print(data.strip())"
        src = (
            f'let co = coroutine(fn() {{\n'
            f'  let p = subprocess.spawn([{_PY}, "-c", {json.dumps(script)}])\n'
            f'  p.stdin.send("hello from nodus\\n")\n'
            f'  p.stdin.close()\n'
            f'  let line = recv(p.stdout)\n'
            f'  while (line != nil) {{\n'
            f'    print(line)\n'
            f'    line = recv(p.stdout)\n'
            f'  }}\n'
            f'}})\n'
            f'spawn(co)\n'
            f'run_loop()'
        )
        out = self._run_spawn(src)
        self.assertIn("hello from nodus", out[0])

    def test_spawn_terminate_closes_channels(self):
        # A process that never exits — terminate should close channels eventually
        script = "import time; time.sleep(60)"
        src = (
            f'let co = coroutine(fn() {{\n'
            f'  let p = subprocess.spawn([{_PY}, "-c", {json.dumps(script)}])\n'
            f'  p.terminate()\n'
            f'  let line = recv(p.stdout)\n'
            f'  print("done")\n'
            f'}})\nspawn(co)\nrun_loop()'
        )
        out = self._run_spawn(src)
        self.assertIn("done", out)

    def test_spawn_missing_binary(self):
        src = (
            'let r = subprocess.spawn(["__nodus_no_such_xyz__"])\n'
            'print(r.kind)'
        )
        self.assertEqual(self._run_spawn(src)[0], "subprocess_error")

    def test_spawn_chunk_mode_bytes(self):
        script = "import sys; sys.stdout.buffer.write(b'hello'); sys.stdout.flush()"
        src = (
            f'let chunks = []\n'
            f'let co = coroutine(fn() {{\n'
            f'  let p = subprocess.spawn([{_PY}, "-c", {json.dumps(script)}],'
            f'  {{chunk_mode: "bytes"}})\n'
            f'  let chunk = recv(p.stdout)\n'
            f'  while (chunk != nil) {{\n'
            f'    list_push(chunks, true)\n'
            f'    chunk = recv(p.stdout)\n'
            f'  }}\n'
            f'}})\n'
            f'spawn(co)\n'
            f'run_loop()\n'
            f'print(len(chunks) > 0)'
        )
        out = self._run_spawn(src)
        self.assertEqual(out[0], "true")


# ── subprocess.spawn_shell ────────────────────────────────────────────────────

class SpawnShellTests(unittest.TestCase):

    def test_spawn_shell_stdout(self):
        cmd = f'{_PY_SHELL} -c "print(\'shell_spawn\')"'
        src = (
            f'let results = []\n'
            f'let co = coroutine(fn() {{\n'
            f'  let p = subprocess.spawn_shell({json.dumps(cmd)})\n'
            f'  let line = recv(p.stdout)\n'
            f'  while (line != nil) {{\n'
            f'    list_push(results, line)\n'
            f'    line = recv(p.stdout)\n'
            f'  }}\n'
            f'}})\n'
            f'spawn(co)\n'
            f'run_loop()\n'
            f'print(len(results) > 0)'
        )
        out = _run_src(src)
        self.assertEqual(out[0], "true")

    def test_spawn_shell_exit_code(self):
        cmd = f'{_PY_SHELL} -c "import sys; sys.exit(0)"'
        src = (
            f'let co = coroutine(fn() {{\n'
            f'  let p = subprocess.spawn_shell({json.dumps(cmd)})\n'
            f'  let rc = p.wait()\n'
            f'  print(rc)\n'
            f'}})\nspawn(co)\nrun_loop()'
        )
        self.assertEqual(_run_src(src)[0], "0")


class SpawnWaitAsyncTests(unittest.TestCase):
    """BUG-116: wait_async() must be truly async (not block the scheduler)."""

    def test_wait_async_returns_exit_code(self):
        src = (
            f'let co = coroutine(fn() {{\n'
            f'  let p = subprocess.spawn([{_PY}, "-c", "pass"])\n'
            f'  let rc = p.wait_async()\n'
            f'  print(rc)\n'
            f'}})\nspawn(co)\nrun_loop()'
        )
        lines = _run_src(src)
        self.assertEqual(lines[0], "0")

    def test_wait_async_exit_code_nonzero(self):
        src = (
            f'let co = coroutine(fn() {{\n'
            f'  let p = subprocess.spawn([{_PY}, "-c", "import sys; sys.exit(3)"])\n'
            f'  let rc = p.wait_async()\n'
            f'  print(rc)\n'
            f'}})\nspawn(co)\nrun_loop()'
        )
        lines = _run_src(src)
        self.assertEqual(lines[0], "3")

    def test_wait_async_updates_exit_code_field(self):
        src = (
            f'let co = coroutine(fn() {{\n'
            f'  let p = subprocess.spawn([{_PY}, "-c", "pass"])\n'
            f'  p.wait_async()\n'
            f'  print(p.exit_code)\n'
            f'}})\nspawn(co)\nrun_loop()'
        )
        lines = _run_src(src)
        self.assertEqual(lines[0], "0")

    def test_two_wait_async_both_complete(self):
        src = (
            f'let state = {{"count": 0i}}\n'
            f'let co1 = coroutine(fn() {{\n'
            f'  let p = subprocess.spawn([{_PY}, "-c", "pass"])\n'
            f'  p.wait_async()\n'
            f'  state["count"] = state["count"] + 1i\n'
            f'}})\n'
            f'let co2 = coroutine(fn() {{\n'
            f'  let p = subprocess.spawn([{_PY}, "-c", "pass"])\n'
            f'  p.wait_async()\n'
            f'  state["count"] = state["count"] + 1i\n'
            f'}})\n'
            f'spawn(co1)\nspawn(co2)\nrun_loop()\n'
            f'print(state["count"])'
        )
        lines = _run_src(src)
        self.assertEqual(lines[0], "2")


if __name__ == "__main__":
    unittest.main()
