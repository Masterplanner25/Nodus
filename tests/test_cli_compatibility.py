import io
import json
import os
import tempfile
import threading
import time
import unittest
import urllib.request
from contextlib import redirect_stdout

import nodus as lang
from nodus.services.server import run_in_thread


class CliCompatibilityTests(unittest.TestCase):
    def test_cli_run_still_outputs(self):
        with tempfile.TemporaryDirectory() as td:
            script = os.path.join(td, "hello.nd")
            with open(script, "w", encoding="utf-8") as f:
                f.write('print("hello")\n')
            buf = io.StringIO()
            with redirect_stdout(buf):
                exit_code = lang.main(["nodus", "run", script])
            self.assertEqual(exit_code, 0)
            self.assertIn("hello", buf.getvalue())

    def test_cli_graph_command_outputs_plan(self):
        # A runtime-constructed graph: `nodus graph` no longer executes its
        # target by default (#400), so planning this shape needs --execute.
        code = """
let A = task(fn() { return 1 }, nil)
let plan = plan_graph([A])
"""
        with tempfile.TemporaryDirectory() as td:
            script = os.path.join(td, "graph.nd")
            with open(script, "w", encoding="utf-8") as f:
                f.write(code)
            buf = io.StringIO()
            with redirect_stdout(buf):
                exit_code = lang.main(["nodus", "graph", script, "--execute"])
            self.assertEqual(exit_code, 0)
            payload = json.loads(buf.getvalue().strip())
            self.assertIn("graph_id", payload)
            self.assertIn("nodes", payload)

    def test_cli_test_examples_command(self):
        exit_code = lang.main(["nodus", "test-examples"])
        self.assertEqual(exit_code, 0)

    # closes: #770
    def test_cli_serve_command_starts_and_stops(self):
        """#770: it must also stop, and the branch it takes must be decided.

        This started a real server in a daemon thread, slept 50 ms, asserted the
        thread was alive, and left it running. Measured over a full suite run:
        the server thread and the `RuntimeService` sweeper underneath it were
        still alive **3245 tests later**, and sweepers at that call site built
        1034 VMs against the shared repo-root `.nodus/` store while unrelated
        tests were using it -- the documented signature of this box's "flaky
        machine" (#769, and #591/#632 before it).

        It also depended on the environment without saying so. `serve()` uses
        uvicorn when FastAPI is installed and the stdlib `ThreadingHTTPServer`
        otherwise, so which server this exercised depended on whether an extra
        happened to be present -- and `uvicorn.run()` returns no handle, which
        is why the leak could not be cleaned up. The branch is pinned here and
        the uvicorn half is covered by the test below.

        `serve()` hands both the service and the server to `start_http_server`,
        so wrapping that captures the pair without changing what is under test:
        the command, its argument parsing and its server construction all still
        run for real -- and the server now answers a request, which the sleep
        never established.
        """
        from nodus.services import server as server_module

        started = threading.Event()
        captured = {}
        original_start = server_module.start_http_server
        original_fastapi = server_module.FASTAPI_AVAILABLE

        def capturing(service, host, port):
            server = original_start(service, host, port)
            captured["service"] = service
            captured["server"] = server
            started.set()
            return server

        def run_server():
            lang.main(["nodus", "serve", "--host", "127.0.0.1", "--port", "0", "--allow-paths", "."])

        server_module.start_http_server = capturing
        server_module.FASTAPI_AVAILABLE = False
        thread = threading.Thread(target=run_server, daemon=True)
        try:
            thread.start()
            self.assertTrue(
                started.wait(timeout=10.0), "the CLI never started a server"
            )
            self.assertTrue(thread.is_alive())
            port = captured["server"].server_address[1]
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/health", timeout=10.0
            ) as response:
                self.assertEqual("ok", json.loads(response.read())["status"])
        finally:
            server_module.start_http_server = original_start
            server_module.FASTAPI_AVAILABLE = original_fastapi
            server = captured.get("server")
            if server is not None:
                server.shutdown()
                server.server_close()
            service = captured.get("service")
            if service is not None:
                service.close()
            thread.join(timeout=10.0)

        self.assertFalse(
            thread.is_alive(),
            "the serve thread outlived the test; every test after this one "
            "would share its sweeper and its store",
        )
        self.assertFalse(
            captured["service"]._sweeper_thread.is_alive(),
            "the service sweeper outlived the test -- stopping the server is "
            "not enough, which is #632's lesson",
        )

    # closes: #770
    def test_cli_serve_uses_uvicorn_when_fastapi_is_installed(self):
        """The other half of the branch, and the reason the test above pins it.

        Nothing asserted which server `nodus serve` runs, so the answer moved
        with the environment. `uvicorn.run` is stubbed rather than called: it
        blocks and offers no handle, which is exactly what made the leak
        unfixable in place.
        """
        from nodus.services import server as server_module

        if not (server_module.FASTAPI_AVAILABLE and server_module.UVICORN_AVAILABLE):
            self.skipTest("fastapi/uvicorn not installed")

        captured = {}
        original_run = server_module.uvicorn.run
        original_service = server_module.RuntimeService

        def fake_run(app, **kwargs):
            captured["app"] = app
            captured["kwargs"] = kwargs

        def capturing_service(*args, **kwargs):
            service = original_service(*args, **kwargs)
            captured["service"] = service
            return service

        # `serve()` never closes its service, and correctly so -- in production
        # it runs until the process ends. A test that makes it *return* owns
        # that cleanup, which the first version of this test did not: its
        # sweeper leaked, and leakwatch caught it.
        server_module.uvicorn.run = fake_run
        server_module.RuntimeService = capturing_service
        try:
            exit_code = lang.main(
                ["nodus", "serve", "--host", "127.0.0.1", "--port", "0", "--allow-paths", "."]
            )
        finally:
            server_module.uvicorn.run = original_run
            server_module.RuntimeService = original_service
            service = captured.get("service")
            if service is not None:
                service.close()

        self.assertEqual(0, exit_code)
        self.assertIn("app", captured, "the CLI did not reach uvicorn")
        self.assertEqual("127.0.0.1", captured["kwargs"]["host"])
        self.assertFalse(captured["service"]._sweeper_thread.is_alive())

    def test_cli_snapshot_restore_worker_auth_token(self):
        token = "cli-token"
        server, thread = run_in_thread("127.0.0.1", 0, allowed_paths=["."], auth_token=token)
        port = server.server_address[1]
        try:
            time.sleep(0.05)
            os.environ["NODUS_SERVER_TOKEN"] = token
            buf = io.StringIO()
            with redirect_stdout(buf):
                exit_code = lang.main(["nodus", "snapshot", "dummy", "--host", "127.0.0.1", "--port", str(port)])
            self.assertEqual(exit_code, 1)

            buf = io.StringIO()
            with redirect_stdout(buf):
                exit_code = lang.main(["nodus", "snapshot", "dummy", "--host", "127.0.0.1", "--port", str(port), "--auth-token", token])
            self.assertEqual(exit_code, 1)

            buf = io.StringIO()
            with redirect_stdout(buf):
                exit_code = lang.main(["nodus", "snapshots", "--host", "127.0.0.1", "--port", str(port), "--auth-token", token])
            self.assertEqual(exit_code, 0)

            buf = io.StringIO()
            with redirect_stdout(buf):
                exit_code = lang.main(["nodus", "restore", "dummy", "--host", "127.0.0.1", "--port", str(port), "--auth-token", token])
            self.assertEqual(exit_code, 1)

            os.environ["NODUS_SERVER_TOKEN"] = "wrong-token"
            buf = io.StringIO()
            with redirect_stdout(buf):
                exit_code = lang.main(["nodus", "snapshots", "--host", "127.0.0.1", "--port", str(port)])
            self.assertEqual(exit_code, 1)

            os.environ["NODUS_SERVER_TOKEN"] = token
            def run_worker():
                try:
                    lang.main(["nodus", "worker", "--host", "127.0.0.1", "--port", str(port)])
                except Exception:
                    return

            worker_thread = threading.Thread(target=run_worker, daemon=True)
            worker_thread.start()
            time.sleep(0.05)
            self.assertTrue(worker_thread.is_alive())
        finally:
            os.environ.pop("NODUS_SERVER_TOKEN", None)
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
