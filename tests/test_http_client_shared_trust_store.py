"""The TLS trust store is built once per process, not once per VM (#855).

`httpx.Client()` builds a fresh `SSLContext` and loads the certifi CA bundle
from disk every time -- 380-995 ms on the box this was found on -- and the
runtime keeps one client per root VM. So every `NodusRuntime` paid it on its
first HTTP call, every `nodus serve` request paid it (one VM per request), and
in an async fan-out the N worker threads all waited on the client lock while
one of them paid it, which measured as the fan-out serialising: 1.9 s for
6 x 300 ms requests cold, 0.33 s warm. `tests/test_async_concurrency_timing.py`
never saw it because its `setUpClass` issues a warm-up request.

The context is built once now and handed to every client as `verify=`. The
per-VM client and its connection pool stay per VM; only the trust store --
identical for every VM in the process -- is shared.
"""

import pathlib
import sys
import unittest
from unittest import mock

REPO = pathlib.Path(__file__).resolve().parents[1]
SRC = REPO / "src"
sys.path.insert(0, str(SRC))

from nodus.builtins import http_module  # noqa: E402
from nodus.vm.vm import VM  # noqa: E402


@unittest.skipUnless(http_module._HTTPX_AVAILABLE, "httpx not installed")
# closes: #855
class SharedTrustStoreTests(unittest.TestCase):

    def setUp(self):
        # Start from a process that has not built one yet, and put it back.
        self._saved = http_module._ssl_context
        http_module._ssl_context = None
        self.addCleanup(setattr, http_module, "_ssl_context", self._saved)

    def test_the_context_is_built_once_across_many_vms(self):
        real = http_module._httpx.create_ssl_context
        calls = []

        def counting():
            calls.append(1)
            return real()

        with mock.patch.object(http_module._httpx, "create_ssl_context", counting):
            clients = [http_module._get_or_create_client(VM([], {})) for _ in range(5)]
        self.assertEqual(len(calls), 1, "the CA bundle was loaded more than once")
        # Five VMs, five clients -- the pool is still per VM ...
        self.assertEqual(len({id(c) for c in clients}), 5)

    def test_every_client_is_built_with_the_shared_context(self):
        """Assert on the construction: a client built without `verify=` goes
        back to loading the bundle itself, and no timing test would name it."""
        captured = []
        real_client = http_module._httpx.Client

        class Recording(real_client):
            def __init__(self, *args, **kwargs):
                captured.append(kwargs.get("verify"))
                super().__init__(*args, **kwargs)

        with mock.patch.object(http_module._httpx, "Client", Recording):
            http_module._get_or_create_client(VM([], {}))
            http_module._get_or_create_client(VM([], {}))
        self.assertEqual(len(captured), 2)
        self.assertIsNotNone(captured[0])
        self.assertIs(captured[0], captured[1])
        self.assertIs(captured[0], http_module._ssl_context)

    def test_the_source_has_one_client_construction_and_it_passes_verify(self):
        src = (SRC / "nodus" / "builtins" / "http_module.py").read_text(encoding="utf-8")
        constructions = [ln.strip() for ln in src.splitlines() if "_httpx.Client(" in ln and not ln.strip().startswith("#")]
        self.assertEqual(len(constructions), 1, constructions)
        self.assertIn("verify=ssl_context", constructions[0])


if __name__ == "__main__":
    unittest.main()
