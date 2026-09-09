"""`nodus serve` confines the filesystem too (#843).

#754 gave the service deny-by-default for subprocess, network and environment.
The filesystem was not part of it, and `RuntimeService` defaulted
`allowed_paths=None` -- which the VM reads as "fall back to `fs_root`", while
the service builds its VMs with `source_path=None` and therefore no `fs_root`.
Both halves of the fallback absent means no restriction at all. Code arriving
over `POST /execute` could read `/etc/passwd` or write into a startup directory,
verified off disk against a running server before this was fixed.

**A second defect sat underneath it, and it is the reason the positive cases
here matter more than the negative ones.** `_apply_runtime_policies` assigned
`vm.allowed_paths` raw, skipping the normalisation `VM.__init__` does. A root
then stayed as the caller spelled it while `_ensure_path_allowed` compares
against `normcase(realpath(...))`, so on Windows they never matched and the jail
denied *everything* -- including files inside the directory the operator named.
`nodus serve --allow-paths <dir>` was broken that way, which is worse than an
unconfined server in one respect: it is the documented mitigation.

A test that only asserted "outside is denied" would have passed against that
bug, since everything was denied. Every case below is therefore paired with an
access that must **succeed**, so "confined" can be told apart from "inert".

The CLI is deliberately not confined this way, and that direction is asserted
too: a fix that quietly jailed `nodus run` would contradict a decision recorded
in `CLAUDE.md`, `SECURITY_POSTURE.md` and the v5.0 migration guide.
"""

from __future__ import annotations

import inspect
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))  # noqa: E402

from nodus.runtime.capability import SANDBOX_DEFAULT  # noqa: E402
from nodus.services import server as server_module  # noqa: E402
from nodus.services.server import RuntimeService  # noqa: E402

READ = 'import "std:fs" as fs\nprint(fs.read("{path}"))\n'
WRITE = 'import "std:fs" as fs\nfs.write("{path}", "x")\nprint("wrote")\n'


def _fwd(p: str) -> str:
    """Forward slashes: a Windows path needs no escaping in an `.nd` literal."""
    return str(p).replace("\\", "/")


def _refused(result) -> bool:
    return (not result.get("ok")) and (result.get("error") or {}).get("kind") == "sandbox"


def _ran(result) -> bool:
    return bool(result.get("ok"))


class ServeFilesystemConfinementTests(unittest.TestCase):
    def setUp(self):
        self._original_cwd = os.getcwd()
        self.inside = tempfile.mkdtemp()
        self.outside = tempfile.mkdtemp()
        (Path(self.inside) / "local.txt").write_text("inside", encoding="utf-8")
        (Path(self.outside) / "secret.txt").write_text("secret", encoding="utf-8")
        os.chdir(self.inside)
        self.addCleanup(os.chdir, self._original_cwd)

    def _service(self, **kwargs) -> RuntimeService:
        service = RuntimeService(**kwargs)
        self.addCleanup(service.close)
        return service

    # -- the default -----------------------------------------------------------

    # closes: #843
    def test_a_default_service_denies_reading_outside_its_directory(self):
        service = self._service()
        target = _fwd(os.path.join(self.outside, "secret.txt"))
        self.assertTrue(_refused(service.execute({"code": READ.format(path=target)})))

    def test_a_default_service_denies_writing_outside_its_directory(self):
        service = self._service()
        target = _fwd(os.path.join(self.outside, "planted.txt"))
        self.assertTrue(_refused(service.execute({"code": WRITE.format(path=target)})))
        self.assertFalse(
            (Path(self.outside) / "planted.txt").exists(),
            "the write was reported as refused and happened anyway",
        )

    def test_a_default_service_still_permits_its_own_directory(self):
        """The control. Without it, the normalisation bug reads as a pass."""
        service = self._service()
        read = service.execute({"code": READ.format(path="local.txt")})
        self.assertTrue(_ran(read), f"read inside the jail was refused: {read.get('error')}")
        self.assertEqual("inside", (read.get("stdout") or "").strip())
        self.assertTrue(_ran(service.execute({"code": WRITE.format(path="out.txt")})))

    # -- an explicit grant -----------------------------------------------------

    def test_an_explicit_allow_paths_permits_that_directory(self):
        """`--allow-paths <dir>` denied files inside `<dir>` before #843."""
        service = self._service(allowed_paths=[self.inside])
        read = service.execute({"code": READ.format(path="local.txt")})
        self.assertTrue(
            _ran(read),
            "a directory the operator explicitly allowed was still refused; the "
            "roots are probably not normalised the way the comparison expects",
        )
        self.assertEqual("inside", (read.get("stdout") or "").strip())

    def test_an_explicit_allow_paths_still_denies_elsewhere(self):
        service = self._service(allowed_paths=[self.inside])
        target = _fwd(os.path.join(self.outside, "secret.txt"))
        self.assertTrue(_refused(service.execute({"code": READ.format(path=target)})))

    def test_an_explicit_none_remains_unrestricted(self):
        """The escape hatch stays, and stays something a caller must ask for."""
        service = self._service(allowed_paths=None)
        target = _fwd(os.path.join(self.outside, "secret.txt"))
        result = service.execute({"code": READ.format(path=target)})
        self.assertTrue(_ran(result))
        self.assertEqual("secret", (result.get("stdout") or "").strip())

    # -- the shape, asserted on the source -------------------------------------

    def test_the_service_default_is_the_sentinel_not_none(self):
        """`None` cannot express "the caller said nothing", which was the bug."""
        default = inspect.signature(RuntimeService.__init__).parameters["allowed_paths"].default
        self.assertIs(
            default, SANDBOX_DEFAULT,
            "a plain None default reads as 'no restriction configured' and "
            "behaves as 'no restriction at all'",
        )

    def test_path_policy_is_installed_through_the_normalising_setter(self):
        """A raw assignment here is the defect underneath #843, so pin it."""
        source = inspect.getsource(RuntimeService._apply_runtime_policies)
        self.assertIn("set_path_policy", source)
        for attribute in ("vm.allowed_paths =", "vm.writable_paths ="):
            self.assertNotIn(
                attribute, source,
                f"{attribute} bypasses normalisation; use vm.set_path_policy",
            )

    def test_every_service_entry_point_defaults_to_the_sentinel(self):
        """`serve` and `run_in_thread` must not re-default to None on the way in."""
        for name in ("serve", "run_in_thread"):
            with self.subTest(entry_point=name):
                fn = getattr(server_module, name)
                default = inspect.signature(fn).parameters["allowed_paths"].default
                self.assertIs(default, SANDBOX_DEFAULT)


class TheCLIUsesADifferentMechanism(unittest.TestCase):
    """The other direction, so a serve fix cannot silently change `nodus run`.

    The CLI is **not** unconfined on the filesystem, and an earlier draft of this
    file asserted that it was. `nodus run` is jailed to the *project root*
    through `fs_root`, derived from the script's own location -- a different
    mechanism from `allowed_paths`, reached by a different branch, and untouched
    by #843. The documented CLI/serve asymmetry is about subprocess, network and
    environment; the filesystem was jailed on both, just differently.

    Pinning the mechanism rather than the outcome is what makes this test
    useful: both paths refuse, so an assertion on "refused" alone would pass if
    the CLI were quietly switched onto the service's cwd jail.
    """

    def _run(self, cwd: str, script: Path) -> subprocess.CompletedProcess:
        env = dict(os.environ, PYTHONPATH=str(_REPO_ROOT / "src"))
        return subprocess.run(
            [sys.executable, "-m", "nodus", "run", str(script), "--time-limit", "30"],
            capture_output=True, text=True, cwd=cwd, env=env, timeout=120,
        )

    def test_nodus_run_refuses_by_project_root_not_by_allowed_paths(self):
        inside = tempfile.mkdtemp()
        outside = tempfile.mkdtemp()
        (Path(outside) / "readable.txt").write_text("reachable", encoding="utf-8")
        script = Path(inside) / "p.nd"
        script.write_text(
            'import "std:fs" as fs\n'
            "fn main() {\n"
            f'    print(fs.read("{_fwd(Path(outside) / "readable.txt")}"))\n'
            "}\n"
            "main()\n",
            encoding="utf-8",
        )
        proc = self._run(inside, script)
        self.assertNotEqual(0, proc.returncode)
        self.assertIn(
            "escapes the project root", proc.stderr,
            "the CLI refused, but with the `allowed_paths` message rather than "
            "the project-root one -- it has been moved onto the service's jail",
        )

    def test_nodus_run_still_reads_its_own_directory(self):
        """The control: the CLI refusing everything would also pass the above."""
        inside = tempfile.mkdtemp()
        (Path(inside) / "local.txt").write_text("inside", encoding="utf-8")
        script = Path(inside) / "p.nd"
        script.write_text(
            'import "std:fs" as fs\n'
            'fn main() {\n    print(fs.read("local.txt"))\n}\nmain()\n',
            encoding="utf-8",
        )
        proc = self._run(inside, script)
        self.assertEqual(0, proc.returncode, proc.stderr[:200])
        self.assertEqual("inside", proc.stdout.strip())


if __name__ == "__main__":
    unittest.main()
