"""Timing-based regression tests for I/O-bound coroutine concurrency.

These tests verify that fanning out N I/O-bound async HTTP calls across
coroutines actually OVERLAPS in wall-clock time, rather than running serially.
Unlike the mock-transport tests in ``test_http.py`` (which use an in-process
WSGI app and assert only correctness), these run against a real, concurrent
``ThreadingHTTPServer`` with measurable per-request latency, so serial execution
is observable.

Known bug (these tests document it):
    The idiomatic stdlib wrapper ``http.get_async`` SILENTLY FALLS BACK TO THE
    SYNC BLOCKING PATH. ``_do_async_request`` only takes the async (thread-backed
    ``_io_channels``) path when ``coroutine is scheduler.current_task``; calling
    the builtin through a ``.nd`` module function (``fn get_async`` ->
    ``http_get_async``) runs it in a nested ``invoke_function -> execute`` frame
    that fails that check. Result: ``http.get_async`` fan-out is serial, while the
    raw ``http_get_async`` builtin overlaps.

Expectations:
    * ``test_raw_async_builtin_overlaps``  -> PASSES today (proves the
      thread-backed substrate works AND that overlap is detectable on this host;
      guards the wrapper test against false failures on a slow machine).
    * ``test_wrapper_async_overlaps``      -> FAILS today (the bug). It should
      start passing once the async guard is fixed to survive a module-function
      call frame.

Self-calibrating: each test compares against a serial baseline measured on the
same host, so the threshold is a ratio, not an absolute time -- robust to load.
"""

import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from nodus.runtime.embedding import NodusRuntime

_DELAY_S = 0.2   # per-request server latency
_N = 8           # fan-out width
# Overlap must make the fan-out at least this much faster than serial.
# Serial ratio ~= 1.0; even partial overlap (~2-3x) lands well under this.
_OVERLAP_RATIO = 0.65


class _SlowHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        time.sleep(_DELAY_S)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):  # silence the default stderr logging
        pass


class AsyncIOConcurrencyTimingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ThreadingHTTPServer.allow_reuse_address = True
        cls._server = ThreadingHTTPServer(("127.0.0.1", 0), _SlowHandler)
        cls._port = cls._server.server_address[1]
        cls._thread = threading.Thread(target=cls._server.serve_forever, daemon=True)
        cls._thread.start()
        cls._url = f"http://127.0.0.1:{cls._port}/"
        # Warm up (first request pays connection-pool setup) and measure the
        # serial baseline once: N sequential synchronous GETs.
        cls._time_source(f'let r = http_get("{cls._url}")')  # warmup
        serial_src = "\n".join(
            [f'let r{i} = http_get("{cls._url}")' for i in range(_N)]
        )
        cls.serial = cls._time_source(serial_src)

    @classmethod
    def tearDownClass(cls):
        cls._server.shutdown()
        cls._server.server_close()

    @staticmethod
    def _time_source(src: str) -> float:
        rt = NodusRuntime(timeout_ms=None, max_steps=None, allow_network=True)
        t0 = time.monotonic()
        result = rt.run_source(src, filename="timing.nd")
        elapsed = time.monotonic() - t0
        rt.shutdown()
        assert result.get("ok"), f"script failed: {result.get('error')}"
        return elapsed

    def _fanout_src(self, call: str) -> str:
        lines = [f'let co{i} = coroutine(fn() {{ let r = {call} }})' for i in range(_N)]
        lines += [f"spawn(co{i})" for i in range(_N)]
        lines += ["run_loop()"]
        return 'import "std:http" as http\n' + "\n".join(lines)

    def test_raw_async_builtin_overlaps(self):
        """Raw http_get_async builtin overlaps -- passes today (sanity + substrate)."""
        concurrent = self._time_source(self._fanout_src(f'http_get_async("{self._url}")'))
        self.assertLess(
            concurrent,
            self.serial * _OVERLAP_RATIO,
            f"raw http_get_async fan-out did not overlap: {concurrent:.2f}s "
            f"vs serial baseline {self.serial:.2f}s "
            f"(expected < {self.serial * _OVERLAP_RATIO:.2f}s). If this fails, the "
            f"host may be too loaded to observe overlap -- the wrapper test below "
            f"is then inconclusive.",
        )

    def test_wrapper_async_overlaps(self):
        """Idiomatic http.get_async fan-out must overlap -- FAILS today (the bug).

        http.get_async currently falls back to the sync blocking path (module
        function call frame fails the async guard), so this runs serially. Should
        flip to passing once the guard is fixed.
        """
        concurrent = self._time_source(self._fanout_src(f'http.get_async("{self._url}", nil)'))
        self.assertLess(
            concurrent,
            self.serial * _OVERLAP_RATIO,
            f"http.get_async fan-out did NOT overlap (ran serially): "
            f"{concurrent:.2f}s vs serial baseline {self.serial:.2f}s "
            f"(expected < {self.serial * _OVERLAP_RATIO:.2f}s). The stdlib async "
            f"wrapper is silently falling back to the synchronous path.",
        )


if __name__ == "__main__":
    unittest.main()
