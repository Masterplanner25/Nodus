"""Timing-based regression tests for I/O-bound coroutine concurrency.

These tests verify that fanning out N I/O-bound async HTTP calls across
coroutines actually OVERLAPS in wall-clock time, rather than running serially.
Unlike the mock-transport tests in ``test_http.py`` (which use an in-process
WSGI app and assert only correctness), these run against a real, concurrent
``ThreadingHTTPServer`` with measurable per-request latency, so serial execution
is observable.

Regression guard (ASYNC-MOD-001, #105):
    The idiomatic stdlib wrapper ``http.get_async`` previously fell back to the
    SYNC blocking path: calling the async builtin through a ``.nd`` module
    function (``fn get_async`` -> ``http_get_async``) ran it in a detached
    ``invoke_function -> run_closure`` frame that could not yield, so a
    ``current_task`` guard fell back to sync and fan-out was serial. The fix
    dispatches module functions in-VM when called from a scheduler coroutine, so
    the async yield propagates and the fan-out overlaps. These tests fail again
    if that regresses.

Expectations:
    * ``test_raw_async_builtin_overlaps``  -> PASSES (the thread-backed substrate
      overlaps; also confirms overlap is detectable on this host, guarding the
      wrapper test against false failures on a slow machine).
    * ``test_wrapper_async_overlaps``      -> PASSES (the idiomatic wrapper now
      overlaps too). Fails if ASYNC-MOD-001 regresses.

Self-calibrating: each test compares against a serial baseline measured on the
same host, so the threshold is a ratio, not an absolute time -- robust to load.
"""

import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from nodus.runtime.embedding import NodusRuntime
from nodus.services.agent_runtime import register_agent, unregister_agent

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

    @classmethod
    def _best_time(cls, src: str, runs: int = 3) -> float:
        # Best-of-N: a transient load spike on a busy CI runner can inflate one
        # timing; the fastest run reflects the true overlap capacity. Guards these
        # ratio assertions against flaking without weakening what they measure.
        return min(cls._time_source(src) for _ in range(runs))

    def _fanout_src(self, call: str) -> str:
        lines = [f'let co{i} = coroutine(fn() {{ let r = {call} }})' for i in range(_N)]
        lines += [f"spawn(co{i})" for i in range(_N)]
        lines += ["run_loop()"]
        return 'import "std:http" as http\n' + "\n".join(lines)

    def test_raw_async_builtin_overlaps(self):
        """Raw http_get_async builtin overlaps -- passes today (sanity + substrate)."""
        concurrent = self._best_time(self._fanout_src(f'http_get_async("{self._url}")'))
        self.assertLess(
            concurrent,
            self.serial * _OVERLAP_RATIO,
            f"raw http_get_async fan-out did not overlap: {concurrent:.2f}s "
            f"vs serial baseline {self.serial:.2f}s "
            f"(expected < {self.serial * _OVERLAP_RATIO:.2f}s). If this fails, the "
            f"host may be too loaded to observe overlap -- the wrapper test below "
            f"is then inconclusive.",
        )

    # closes: #295
    def test_concurrent_fanout_shares_one_http_client(self):
        """ASYNC-CAP-001 (#295): N async requests fanned out concurrently must share
        ONE httpx.Client.

        Deterministic guard (not timing-based, so it can't flake on a loaded CI
        runner): a check-then-set race in `_get_or_create_client` used to let every
        worker thread build its own client — each with a separate connection pool —
        so the requests could no longer share connections and the fan-out serialised
        toward ~2x instead of N. Now exactly one shared client is created.
        """
        import nodus.builtins.http_module as hm

        created = [0]
        Orig = hm._httpx.Client

        class _Counting(Orig):
            def __init__(self, *args, **kwargs):
                created[0] += 1
                super().__init__(*args, **kwargs)

        hm._httpx.Client = _Counting
        try:
            self._time_source(self._fanout_src(f'http_get_async("{self._url}")'))
        finally:
            hm._httpx.Client = Orig

        self.assertEqual(
            created[0], 1,
            f"a concurrent async fan-out must share one httpx.Client; "
            f"{created[0]} were created (the client-creation race regressed).",
        )

    # closes: #105
    def test_wrapper_async_overlaps(self):
        """Idiomatic http.get_async fan-out must overlap (ASYNC-MOD-001, #105).

        Regression guard: http.get_async (a std: module wrapper) previously fell
        back to the sync blocking path and ran serially. Module functions called
        from a scheduler coroutine now dispatch in-VM so the async yield
        propagates and the fan-out overlaps. Re-breaking that makes this fail.
        """
        concurrent = self._best_time(self._fanout_src(f'http.get_async("{self._url}", nil)'))
        self.assertLess(
            concurrent,
            self.serial * _OVERLAP_RATIO,
            f"http.get_async fan-out did NOT overlap (ran serially): "
            f"{concurrent:.2f}s vs serial baseline {self.serial:.2f}s "
            f"(expected < {self.serial * _OVERLAP_RATIO:.2f}s). The stdlib async "
            f"wrapper is silently falling back to the synchronous path.",
        )


class AsyncAgentConcurrencyTimingTests(unittest.TestCase):
    """agent_call_async fan-out must overlap (ASYNC-MOD-002, #294).

    Before the async agent builtin, `agent_call` was synchronous with no async
    variant, so fanning N agent calls across coroutines ran serially on the single
    cooperative scheduler thread. `agent_call_async` runs the handler on a daemon
    thread and suspends the caller via the `_io_channels` pattern, so the fan-out
    overlaps — verified here against a serial baseline measured on the same host.
    """

    _AGENT = "timing_agent"

    @classmethod
    def setUpClass(cls):
        def _slow(payload):
            time.sleep(_DELAY_S)
            return {"ok": True}

        register_agent(cls._AGENT, _slow, description="slow timing agent")
        # Warmup + serial baseline: N sequential synchronous agent_call.
        cls._time_source(f'let r = agent_call("{cls._AGENT}", {{}})')  # warmup
        serial_src = "\n".join(
            [f'let r{i} = agent_call("{cls._AGENT}", {{}})' for i in range(_N)]
        )
        cls.serial = cls._time_source(serial_src)

    @classmethod
    def tearDownClass(cls):
        unregister_agent(cls._AGENT)

    @staticmethod
    def _time_source(src: str) -> float:
        rt = NodusRuntime(timeout_ms=None, max_steps=None)
        t0 = time.monotonic()
        result = rt.run_source(src, filename="timing_agent.nd")
        elapsed = time.monotonic() - t0
        rt.shutdown()
        assert result.get("ok"), f"script failed: {result.get('error')}"
        return elapsed

    @classmethod
    def _best_time(cls, src: str, runs: int = 3) -> float:
        return min(cls._time_source(src) for _ in range(runs))

    def _fanout_src(self, call: str, imports: str = "") -> str:
        lines = [f'let co{i} = coroutine(fn() {{ let r = {call} }})' for i in range(_N)]
        lines += [f"spawn(co{i})" for i in range(_N)]
        lines += ["run_loop()"]
        return imports + "\n".join(lines)

    def test_raw_agent_call_async_overlaps(self):
        """Raw agent_call_async builtin fan-out overlaps (sanity + substrate)."""
        concurrent = self._best_time(
            self._fanout_src(f'agent_call_async("{self._AGENT}", {{}})')
        )
        self.assertLess(
            concurrent,
            self.serial * _OVERLAP_RATIO,
            f"agent_call_async fan-out did not overlap: {concurrent:.2f}s vs serial "
            f"baseline {self.serial:.2f}s (expected < {self.serial * _OVERLAP_RATIO:.2f}s). "
            f"If this fails, the host may be too loaded to observe overlap.",
        )

    # closes: #294
    def test_wrapper_agent_call_async_overlaps(self):
        """Idiomatic agent.call_async fan-out must overlap (ASYNC-MOD-002, #294).

        Regression guard: the module wrapper must propagate the async yield (same
        in-VM dispatch fix as ASYNC-MOD-001) so the fan-out overlaps rather than
        silently falling back to the synchronous path.
        """
        concurrent = self._best_time(
            self._fanout_src(
                f'agent.call_async("{self._AGENT}", {{}})',
                imports='import "std:agent" as agent\n',
            )
        )
        self.assertLess(
            concurrent,
            self.serial * _OVERLAP_RATIO,
            f"agent.call_async fan-out did NOT overlap (ran serially): {concurrent:.2f}s "
            f"vs serial baseline {self.serial:.2f}s (expected < {self.serial * _OVERLAP_RATIO:.2f}s). "
            f"The stdlib async wrapper is silently falling back to the synchronous path.",
        )


if __name__ == "__main__":
    unittest.main()
