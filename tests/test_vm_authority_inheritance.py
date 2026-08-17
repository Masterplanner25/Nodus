"""A VM derived from another inherits all of its authority (#405).

The same bug shipped three times in one day, each time as **a check that lives on
one path while a sibling path bypasses it**:

- #392 — `inline_retries` was passed by one of five callers, so four entry points
  dropped step retries and returned success;
- #399 — the resume rebuild's placeholder result was missing the keys that appear
  on exactly the runs anyone resumes;
- #405 — the capability policy was not inherited by the child VM that
  `import "std:subprocess"` runs on, so the documented way to call subprocess
  walked around the jail.

Derivation sites are where this recurs, because each one hand-copies whatever its
author remembered. Sweeping them found two more leaks that had nothing to do with
the policy work:

| Site | Before |
|---|---|
| `VM._resume_target_vm` | lost 7 of 8 — `allowed_paths` jail → `None`, `allow_subprocess` `False` → `True` |
| `DAPServer` evaluate | carried `allowed_paths` only; the debug console could shell out of a jailed program |
| `ModuleLoader` module VM | correct |
| tool handler child VM | correct |

These tests hold the list and the sites together, so adding an authority-bearing
attribute without teaching the sites about it fails here rather than opening a
hole.
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, "C:/dev/Coding Language/src")

from nodus.runtime.capability import (  # noqa: E402
    AUTHORITY_ATTRIBUTES,
    SUBPROCESS,
    DenyList,
    inherit_authority,
)
from nodus.vm.vm import VM  # noqa: E402


def _jailed_parent(**overrides) -> VM:
    """A VM whose authority is non-default in every respect.

    Every value differs from the constructor default, so an attribute that is not
    inherited shows up as a difference rather than coincidentally matching.
    """
    vm = VM(
        [1], {}, code_locs=[(None, 0, 0)], source_path="parent.nd",
        allowed_paths=["."],
        allow_subprocess=False,
        allow_network=False,
        allow_env=False,
        allowed_commands=["echo"],
        allowed_hosts=["example.com"],
        **overrides,
    )
    vm.capability_policy = DenyList(SUBPROCESS)
    return vm


def _authority(vm) -> dict:
    return {name: getattr(vm, name, "<missing>") for name in AUTHORITY_ATTRIBUTES}


def _assert_inherited(case, parent, child):
    missing = {
        name: (value, _authority(child)[name])
        for name, value in _authority(parent).items()
        if _authority(child)[name] != value
    }
    case.assertEqual(
        missing, {},
        "authority lost when deriving a VM: "
        + ", ".join(f"{n}: parent={p!r} child={c!r}" for n, (p, c) in missing.items()),
    )


# closes: #405
class TheAttributeListIsComplete(unittest.TestCase):
    """The list is what every site copies, so it has to be right."""

    def test_every_constructor_sandbox_argument_is_named(self):
        # If a sandbox knob can be set at construction, it carries authority and
        # must be inherited. Read from the signature rather than hand-listed, so
        # a new constructor argument cannot slip past.
        import inspect

        params = set(inspect.signature(VM.__init__).parameters)
        sandbox_params = {
            p for p in params
            if p.startswith("allow") or p in ("fs_root", "allowed_paths")
        }
        missing = sandbox_params - set(AUTHORITY_ATTRIBUTES)
        self.assertEqual(
            missing, set(),
            f"VM.__init__ accepts {sorted(missing)}, which carry authority but are "
            f"not in AUTHORITY_ATTRIBUTES, so derived VMs will not inherit them",
        )

    def test_the_policy_itself_is_named(self):
        self.assertIn("capability_policy", AUTHORITY_ATTRIBUTES)


# closes: #405
class ResumeDoesNotEscapeTheJail(unittest.TestCase):
    """`_resume_target_vm` was the worst of the sites — 7 of 8 lost."""

    def test_the_resume_child_inherits_every_authority_attribute(self):
        parent = _jailed_parent()
        child = parent._resume_target_vm("g_not_registered_anywhere")
        self.assertIsNot(child, parent, "expected a derived VM for this case")
        _assert_inherited(self, parent, child)

    def test_the_filesystem_jail_specifically_survives(self):
        # Named on its own because `allowed_paths` going from a jail to None is
        # the difference between confined and unconfined, not a degree of it.
        parent = _jailed_parent()
        child = parent._resume_target_vm("g_not_registered_anywhere")
        self.assertEqual(child.allowed_paths, parent.allowed_paths)
        self.assertIsNotNone(child.allowed_paths)


# closes: #405
class ModuleBoundaryKeepsAuthority(unittest.TestCase):
    """End-to-end, and on a different attribute than the policy tests use.

    `test_capability_policy.py` covers the module boundary for
    `capability_policy`. This covers it for `allowed_paths`, so the boundary is
    checked on two independent kinds of authority rather than one.
    """

    def test_the_filesystem_jail_holds_across_a_stdlib_import(self):
        from nodus.runtime.embedding import NodusRuntime

        with tempfile.TemporaryDirectory() as jail, tempfile.TemporaryDirectory() as outside:
            target = os.path.join(outside, "escaped.txt").replace("\\", "/")
            source = (
                'import "std:fs" as fs\n'
                'fs.write("%s", "escaped")\n'
                'print("wrote")\n' % target
            )
            cwd = os.getcwd()
            os.chdir(jail)
            try:
                result = NodusRuntime(allowed_paths=[jail], timeout_ms=None).run_source(
                    source, filename="t.nd"
                )
            finally:
                os.chdir(cwd)
            self.assertFalse(
                result.get("ok"),
                "a stdlib module wrote outside allowed_paths — the module VM did "
                "not inherit the filesystem jail",
            )
            self.assertFalse(os.path.exists(os.path.join(outside, "escaped.txt")))


# closes: #405
class TheJailHoldsInCliModeToo(unittest.TestCase):
    """CLAUDE.md: a security-boundary fix needs both CLI and embedded coverage.

    The enforcement path differs between the two, and `allowed_paths` is named
    explicitly in that rule. The embedded half is above.
    """

    def test_cli_mode_refuses_a_write_outside_allowed_paths(self):
        import subprocess

        repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with tempfile.TemporaryDirectory() as jail, tempfile.TemporaryDirectory() as outside:
            target = os.path.join(outside, "escaped.txt").replace("\\", "/")
            script = os.path.join(jail, "t.nd")
            with open(script, "w", encoding="utf-8") as handle:
                handle.write(
                    'import "std:fs" as fs\n'
                    'fs.write("%s", "escaped")\n'
                    'print("wrote")\n' % target
                )
            env = dict(os.environ)
            env["PYTHONPATH"] = os.path.join(repo, "src")
            proc = subprocess.run(
                [sys.executable, os.path.join(repo, "nodus.py"), "run", script,
                 "--allow-paths", jail],
                cwd=jail, env=env, capture_output=True, text=True, timeout=120,
            )
            self.assertNotEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertFalse(os.path.exists(os.path.join(outside, "escaped.txt")))


# closes: #405
class TheHelperCopiesEverything(unittest.TestCase):
    def test_inherit_authority_copies_the_whole_list(self):
        parent = _jailed_parent()
        child = VM([], {}, code_locs=[], source_path=None)
        inherit_authority(child, parent)
        _assert_inherited(self, parent, child)

    def test_it_tolerates_a_missing_parent(self):
        child = VM([], {}, code_locs=[], source_path=None)
        inherit_authority(child, None)   # must not raise
        inherit_authority(None, child)


if __name__ == "__main__":
    unittest.main()
