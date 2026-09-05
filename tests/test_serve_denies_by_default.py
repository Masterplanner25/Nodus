"""`nodus serve` confines the code it is sent (#754).

`POST /execute` runs submitted source through the same machinery as `nodus run`,
and so inherited its defaults: `allow_subprocess`, `allow_network` and
`allow_env` were all `True`, with no capability policy and **no flag able to
change any of it**. The identical source through `NodusRuntime` was refused,
because #405 made all three deny by default.

The CLI's permissiveness is a decision with a stated reason — what
deny-by-default protects is work you did not fully author, and a developer
running a script they just wrote is not that. That reasoning does not survive
the trip to a network endpoint. `serve` was permissive because it happened to
call the same runner, not because anyone decided it should be.

Two things this file is careful about:

- **A control that must run.** The first probe for this issue wrapped its code
  in `fn main()` and read the resulting empty stdout as "not blocked", when the
  program had simply never executed. Every case here is paired with a program
  that must succeed, so "refused" can be told apart from "never ran".
- **Both directions.** A test that only asserts the service denies is satisfied
  by someone denying on the CLI path too, which would break `nodus run` and
  contradict a decision recorded in `CLAUDE.md` and `SECURITY_POSTURE.md`.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))  # noqa: E402

from nodus import NodusRuntime  # noqa: E402
from nodus.services.server import RuntimeService  # noqa: E402

CONTROL = 'print("the program ran")\n'

SUBPROCESS = (
    'import "std:subprocess" as sp\n'
    'let r = sp.run(["cmd", "/c", "echo hi"])\n'
    'print("exit=\\(r.exit_code)")\n'
)
NETWORK = (
    'import "std:http" as http\n'
    'let r = http.get("http://127.0.0.1:9/")\n'
    'print("done")\n'
)
ENV = (
    'import "std:env" as env\n'
    'print("path=\\(env.get("PATH") != nil)")\n'
)

CASES = {
    "allow_subprocess": SUBPROCESS,
    "allow_network": NETWORK,
    "allow_env": ENV,
}


def _refused(result) -> bool:
    return (not result.get("ok")) and (result.get("error") or {}).get("kind") == "sandbox"


class ServeCaseMixin:
    def setUp(self):
        self._cwd = os.getcwd()
        self._tmp = tempfile.TemporaryDirectory(prefix="nodus754-")
        os.chdir(self._tmp.name)
        self._services = []

    def tearDown(self):
        for service in self._services:
            close = getattr(service, "close", None)
            if callable(close):
                close()
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def service(self, **kwargs):
        svc = RuntimeService(**kwargs)
        self._services.append(svc)
        return svc


class SubmittedCodeIsConfinedTests(ServeCaseMixin, unittest.TestCase):
    # closes: #754
    def test_the_control_runs(self):
        """Without this the refusals below could all be 'the program never
        executed' — which is exactly how the first probe for this issue read a
        vacuous result as a reproduction."""
        result = self.service().execute({"code": CONTROL, "filename": "c.nd"})
        self.assertTrue(result["ok"], result.get("error"))
        self.assertIn("the program ran", result["stdout"])

    # closes: #754
    def test_each_capability_is_denied(self):
        svc = self.service()
        for flag, source in CASES.items():
            with self.subTest(capability=flag):
                result = svc.execute({"code": source, "filename": f"{flag}.nd"})
                self.assertTrue(
                    _refused(result),
                    f"submitted code reached {flag}: {result.get('stdout')!r} "
                    f"{result.get('error')}",
                )

    # closes: #754
    def test_the_refusal_names_the_flag_to_grant(self):
        """The denial contract downstream depends on (#443): `kind` is
        `sandbox` and the message contains the granting flag's name."""
        result = self.service().execute({"code": SUBPROCESS, "filename": "s.nd"})
        self.assertEqual("sandbox", result["error"]["kind"])
        self.assertIn("allow_subprocess", result["error"]["message"])

    # closes: #754
    def test_it_now_matches_the_embedded_runtime(self):
        """The point of the change: two front doors onto the same threat model
        should answer the same way."""
        svc = self.service()
        for flag, source in CASES.items():
            with self.subTest(capability=flag):
                self.assertEqual(
                    _refused(NodusRuntime().run_source(source)),
                    _refused(svc.execute({"code": source, "filename": "x.nd"})),
                )


class TheOperatorCanGrantTests(ServeCaseMixin, unittest.TestCase):
    # closes: #754
    def test_a_granted_capability_works(self):
        result = self.service(allow_subprocess=True).execute(
            {"code": SUBPROCESS, "filename": "s.nd"}
        )
        self.assertTrue(result["ok"], result.get("error"))
        self.assertIn("exit=0", result["stdout"])

    # closes: #754
    def test_granting_one_does_not_grant_the_others(self):
        svc = self.service(allow_subprocess=True)
        for flag, source in (("allow_network", NETWORK), ("allow_env", ENV)):
            with self.subTest(capability=flag):
                self.assertTrue(_refused(svc.execute({"code": source, "filename": "x.nd"})))

    # closes: #754
    def test_an_allowlist_narrows_a_granted_capability(self):
        """`--allowed-commands` is a second bound *inside* the grant, so a
        server that must run one tool need not permit every executable."""
        svc = self.service(allow_subprocess=True, allowed_commands=["echo"])
        result = svc.execute({"code": SUBPROCESS, "filename": "s.nd"})
        self.assertTrue(_refused(result))
        self.assertIn("allowed_commands", result["error"]["message"])


class EveryRouteIsConfinedTests(ServeCaseMixin, unittest.TestCase):
    """Not just `/execute`.

    `graph` reached the runner by a **different** call — `run_source(...)` with
    the path settings passed by hand — so it was a second implementation of "how
    is a VM for this service confined", and one that structurally could not
    learn a capability flag: `run_source` builds its own VM and takes no such
    argument. That is the recurring shape, and it is why this test covers routes
    rather than the one the issue happened to name.
    """

    ROUTES = {
        "execute": lambda svc, src: svc.execute({"code": src, "filename": "r.nd"}),
        "graph": lambda svc, src: svc.graph({"code": src, "filename": "r.nd"}),
        "workflow_run": lambda svc, src: svc.workflow_run({"code": src, "filename": "r.nd"}),
        "goal_run": lambda svc, src: svc.goal_run({"code": src, "filename": "r.nd"}),
    }

    # closes: #754
    def test_no_route_leaks_a_capability(self):
        svc = self.service()
        for name, call in self.ROUTES.items():
            with self.subTest(route=name):
                self.assertTrue(
                    _refused(call(svc, SUBPROCESS)),
                    f"route {name} ran a subprocess for submitted code",
                )

    #: Ordinary code each route can actually accept. `workflow_run` and
    #: `goal_run` need a declaration to find, so passing them a plain script
    #: fails with "No workflow definition found" — a green complement test
    #: against that would be measuring the wrong refusal.
    ORDINARY = {
        "execute": CONTROL,
        "graph": CONTROL,
        "workflow_run": (
            "workflow w { step a { return 1i } }\n"
            'fn main() { run_workflow(w); print("the program ran") }\n'
        ),
        "goal_run": (
            "goal g { step a { return 1i } }\n"
            'fn main() { run_goal(g); print("the program ran") }\n'
        ),
    }

    # closes: #754
    def test_every_route_still_runs_ordinary_code(self):
        """The complement, so the test above cannot be satisfied by a route
        that is simply broken."""
        svc = self.service()
        for name, call in self.ROUTES.items():
            with self.subTest(route=name):
                result = call(svc, self.ORDINARY[name])
                self.assertTrue(result.get("ok"), f"{name}: {result.get('error')}")


class TheCliDefaultIsUnchangedTests(unittest.TestCase):
    """`nodus run` stays permissive — the decision, not an oversight."""

    # closes: #754
    def test_the_cli_path_still_permits_subprocess(self):
        from nodus.tooling import runner

        with tempfile.TemporaryDirectory(prefix="nodus754cli-") as tmp:
            cwd = os.getcwd()
            os.chdir(tmp)
            try:
                result, _vm = runner.run_source(SUBPROCESS, filename="s.nd", timeout_ms=20000)
            finally:
                os.chdir(cwd)
        self.assertTrue(result.get("ok"), result.get("error"))


if __name__ == "__main__":
    unittest.main()
