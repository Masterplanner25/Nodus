"""Binary file read and write, and the sandbox guard that covers them (#170).

`std:fs` could only read and write UTF-8 text. `builtin_write_file` opens with
`encoding='utf-8'` and there is no binary mode, so a Nodus program could not
write a compiled artifact — which the Runtime Readiness audit recorded as a
Stage 3 bootstrap gap: *to write a Nodus compiler in Nodus, the compiler must be
able to write compiled bytecode files.*

**Bytes are a list of integers 0-255, not a new value type.** The issue lists a
`Bytes` type as "consider", and it is deliberately not taken: a real byte type
needs indexing, slicing, concatenation, equality, a literal syntax and JSON
serialisation before it is usable, and none of those are needed to close the
gap. A list of ints already has all six. If a `Bytes` type arrives later it can
be a representation change behind the same two builtins.

**The part that needed care is that a filesystem builtin answers to two
mechanisms, not one**, and #467 is what happens when only one is wired:
`FS_READ` was declared and attached to nothing, so reads reached
`_ensure_path_allowed` and were still invisible to a `CapabilityPolicy` — "the
map, not the chokepoint". So the new builtins go through both, and
`FilesystemBuiltinsAreSandboxedTests` drives off `BUILTIN_CAPABILITIES` rather
than off a list written here, so a *future* filesystem builtin is covered
whether or not anyone remembers this file.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # noqa: E402

from nodus.runtime.capability import (  # noqa: E402
    BUILTIN_CAPABILITIES,
    FS_READ,
    FS_WRITE,
)
from nodus.runtime.embedding import NodusRuntime  # noqa: E402


def q(path) -> str:
    """A path as a Nodus string literal. Backslashes are not escapes here."""
    return '"' + str(path).replace("\\", "/") + '"'


class _FsCase(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def run_nodus(self, source: str, *, allowed=None):
        rt = NodusRuntime(timeout_ms=None, max_steps=None,
                          allowed_paths=[str(self.dir)] if allowed is None else allowed)
        return rt.run_source(source)

    def run_ok(self, source: str) -> str:
        result = self.run_nodus(source)
        self.assertTrue(result["ok"], result.get("error") or result)
        return result["stdout"]


# closes: #170
class BinaryRoundTripTests(_FsCase):

    def test_bytes_survive_a_write_and_read(self):
        target = self.dir / "out.bin"
        out = self.run_ok(f"""
import "std:fs" as fs
fn main() {{
    let data = [0i, 1i, 127i, 128i, 254i, 255i]
    fs.write_bytes({q(target)}, data)
    print(fs.read_bytes({q(target)}))
}}
""")
        self.assertIn("[0, 1, 127, 128, 254, 255]", out)

    def test_bytes_that_are_not_valid_utf8_survive(self):
        """The reason the pair exists. `0x80` and `0xFF` are not valid UTF-8, so
        the text path cannot carry them in either direction."""
        target = self.dir / "raw.bin"
        target.write_bytes(bytes([0x80, 0xFF, 0xFE]))
        out = self.run_ok(f"""
import "std:fs" as fs
fn main() {{ print(fs.read_bytes({q(target)})) }}
""")
        self.assertIn("[128, 255, 254]", out)

    def test_reading_the_same_file_as_text_is_an_error(self):
        """The control for the test above: text mode does not merely mangle
        these bytes, it refuses them — so `read_file` was never a workaround."""
        target = self.dir / "raw.bin"
        target.write_bytes(bytes([0x80, 0xFF]))
        out = self.run_ok(f"""
import "std:fs" as fs
fn main() {{ let r = fs.read({q(target)}); print("kind=\\(r.kind)") }}
""")
        self.assertIn("kind=io_error", out)

    def test_a_ctrl_z_byte_is_not_end_of_file(self):
        """0x1A ends a file in Windows text mode. Binary mode must not care —
        and this is the failure that would pass on Linux and lose data here."""
        target = self.dir / "eof.bin"
        target.write_bytes(bytes([1, 0x1A, 2]))
        out = self.run_ok(f"""
import "std:fs" as fs
fn main() {{ print(len(fs.read_bytes({q(target)}))) }}
""")
        self.assertIn("3", out)

    def test_no_newline_translation_happens(self):
        r"""Windows text mode turns `\n` into `\r\n` on write. Three bytes in,
        three bytes out."""
        target = self.dir / "nl.bin"
        out = self.run_ok(f"""
import "std:fs" as fs
fn main() {{
    fs.write_bytes({q(target)}, [10i, 13i, 10i])
    print(fs.read_bytes({q(target)}))
}}
""")
        self.assertIn("[10, 13, 10]", out)
        self.assertEqual(bytes([10, 13, 10]), target.read_bytes())

    def test_an_empty_list_writes_an_empty_file(self):
        target = self.dir / "empty.bin"
        out = self.run_ok(f"""
import "std:fs" as fs
fn main() {{
    fs.write_bytes({q(target)}, [])
    print(len(fs.read_bytes({q(target)})))
}}
""")
        self.assertIn("0", out)
        self.assertEqual(b"", target.read_bytes())

    def test_a_write_replaces_rather_than_appends(self):
        target = self.dir / "twice.bin"
        out = self.run_ok(f"""
import "std:fs" as fs
fn main() {{
    fs.write_bytes({q(target)}, [1i, 2i, 3i])
    fs.write_bytes({q(target)}, [9i])
    print(fs.read_bytes({q(target)}))
}}
""")
        self.assertIn("[9]", out)

    def test_a_missing_file_reports_the_same_error_shape_as_read_file(self):
        out = self.run_ok(f"""
import "std:fs" as fs
fn main() {{
    let r = fs.read_bytes({q(self.dir / "absent.bin")})
    print("kind=\\(r.kind)")
}}
""")
        self.assertIn("kind=io_error", out)


# closes: #170
class ByteValidationTests(_FsCase):
    """Every element is checked *before* the file is opened.

    A partial write would be worse than a refusal: the caller sees an error and
    a file that exists with some of the data in it. Each case below asserts the
    error **and** that no file was created.
    """

    def _refuse(self, literal: str, kind: str, fragment: str):
        target = self.dir / "never.bin"
        result = self.run_nodus(f"""
import "std:fs" as fs
fn main() {{ fs.write_bytes({q(target)}, {literal}) }}
""")
        self.assertFalse(result["ok"], f"{literal} should be refused")
        self.assertEqual(kind, result["error"]["kind"])
        self.assertIn(fragment, result["error"]["message"])
        self.assertFalse(target.exists(),
                         "a refused write must not leave a file behind")

    def test_a_value_above_255_is_refused(self):
        self._refuse("[256i]", "value", "element 0 is 256, outside 0-255")

    def test_a_negative_value_is_refused(self):
        self._refuse("[0i - 1i]", "value", "outside 0-255")

    def test_a_non_integer_element_is_refused_and_names_its_index(self):
        self._refuse('[1i, 2i, "x"]', "type", "element 2 is not an integer")

    def test_a_bool_element_is_refused(self):
        """`isinstance(True, int)` holds in Python. `true` is not a byte here,
        the same call the VM's own `DIV` makes about the int fast path."""
        self._refuse("[true]", "type", "element 0 is not an integer")

    def test_a_float_element_is_refused(self):
        self._refuse("[1.5]", "type", "element 0 is not an integer")

    def test_a_nil_element_is_refused(self):
        self._refuse("[nil]", "type", "element 0 is not an integer")

    def test_a_non_list_argument_is_refused(self):
        self._refuse('"abc"', "type", "expects a list of integers 0-255")

    def test_the_boundary_values_are_accepted(self):
        """The control. If 0 and 255 were refused the tests above would pass for
        the wrong reason."""
        target = self.dir / "bounds.bin"
        self.run_ok(f"""
import "std:fs" as fs
fn main() {{ fs.write_bytes({q(target)}, [0i, 255i]) }}
""")
        self.assertEqual(bytes([0, 255]), target.read_bytes())


# closes: #170
class BinaryIoIsSandboxedTests(_FsCase):
    """The new builtins are confined by the same two mechanisms as the old ones."""

    def test_a_read_outside_allowed_paths_is_refused(self):
        with tempfile.TemporaryDirectory() as elsewhere:
            secret = Path(elsewhere) / "secret.bin"
            secret.write_bytes(bytes([1, 2]))
            result = self.run_nodus(f"""
import "std:fs" as fs
fn main() {{ print(fs.read_bytes({q(secret)})) }}
""")
        self.assertFalse(result["ok"])
        self.assertEqual("sandbox", result["error"]["kind"])

    def test_a_write_outside_allowed_paths_is_refused(self):
        with tempfile.TemporaryDirectory() as elsewhere:
            target = Path(elsewhere) / "planted.bin"
            result = self.run_nodus(f"""
import "std:fs" as fs
fn main() {{ fs.write_bytes({q(target)}, [1i]) }}
""")
            self.assertFalse(result["ok"])
            self.assertEqual("sandbox", result["error"]["kind"])
            self.assertFalse(target.exists())

    def test_the_floor_forbids_writing_into_the_runtimes_own_state(self):
        """Unbypassable, and not covered by `allowed_paths`: a guest that can
        write into `.nodus/` can forge workflow run records. The binary writer
        must not be the way around a rule the text writer enforces."""
        target = self.dir / ".nodus" / "forged.bin"
        result = self.run_nodus(f"""
import "std:fs" as fs
fn main() {{ fs.write_bytes({q(target)}, [1i]) }}
""")
        self.assertFalse(result["ok"])
        self.assertEqual("sandbox", result["error"]["kind"])
        self.assertIn("state directory", result["error"]["message"])

    def test_the_denial_message_names_the_builtin(self):
        """Embedders contract on `kind` plus the flag name, not the sentence
        (#443) — but a denial that named no builtin would be unactionable."""
        with tempfile.TemporaryDirectory() as elsewhere:
            result = self.run_nodus(f"""
import "std:fs" as fs
fn main() {{ fs.write_bytes({q(Path(elsewhere) / "x.bin")}, [1i]) }}
""")
        self.assertIn("write_file_bytes", result["error"]["message"])


# closes: #170
class FilesystemBuiltinsAreSandboxedTests(_FsCase):
    """Every builtin *classified* as touching the filesystem must actually check.

    Driven off `BUILTIN_CAPABILITIES` rather than a list written here, so a new
    filesystem builtin is covered whether or not anyone remembers this file.
    That is the half #467 was: `FS_READ` was declared and attached to nothing,
    and the classification looked like coverage while providing none. The
    reverse direction — a filesystem builtin classified as authority-free — is
    already refused by `test_every_builtin_is_classified` (#473), which requires
    every builtin to be on one list or the other.

    Deliberately behavioural rather than a source scan. A source test for "calls
    `_ensure_path_allowed`" is unsound in both directions here: `hash_*_file`
    reach it through a local helper and would read as uncovered, while the
    subprocess builtins call it for `cwd` and redirects and would read as
    filesystem builtins when their capability is `subprocess`.
    """

    # A second argument for the arity-2 writers. Two shapes, so a new builtin
    # with either arity is handled; anything else fails loudly below rather than
    # being skipped, because a skipped check is not a passing one.
    SECOND_ARG = {"write_file_bytes": "[1i]"}
    DEFAULT_SECOND_ARG = '"payload"'

    def _fs_builtins(self) -> dict:
        return {name: cap for name, cap in BUILTIN_CAPABILITIES.items()
                if cap in (FS_READ, FS_WRITE)}

    def test_there_is_at_least_one_of_each_kind(self):
        """A guard on the guard: if the classification were renamed, the sweep
        below would iterate nothing and pass."""
        caps = set(self._fs_builtins().values())
        self.assertEqual({FS_READ, FS_WRITE}, caps)
        self.assertGreater(len(self._fs_builtins()), 10)

    def test_every_classified_filesystem_builtin_refuses_a_path_outside_the_sandbox(self):
        rt = NodusRuntime(timeout_ms=None, max_steps=None,
                          allowed_paths=[str(self.dir)])
        # `active_vm()` is None until something has run, and the arities are read
        # from the live registry rather than a table here so a changed signature
        # shows up as a wrong call rather than a silently skipped builtin.
        rt.run_source("fn main() { }")
        arities = {name: info.arity for name, info in rt.active_vm().builtins.items()}

        with tempfile.TemporaryDirectory() as elsewhere:
            outside = Path(elsewhere) / "target"
            outside.write_bytes(b"data")
            for name in sorted(self._fs_builtins()):
                arity = arities.get(name)
                with self.subTest(builtin=name, arity=arity):
                    self.assertIsNotNone(arity, f"{name} is classified but not registered")
                    if arity == 1:
                        call = f"{name}({q(outside)})"
                    elif arity == 2:
                        second = self.SECOND_ARG.get(name, self.DEFAULT_SECOND_ARG)
                        call = f"{name}({q(outside)}, {second})"
                    else:
                        self.fail(
                            f"{name} has arity {arity}; this sweep only knows how "
                            f"to call arity 1 and 2. Add a call shape rather than "
                            f"excluding it — an unchecked filesystem builtin is "
                            f"exactly what this test exists to catch (#170/#467)."
                        )
                    result = rt.run_source(f"fn main() {{ {call} }}")
                    self.assertFalse(
                        result["ok"],
                        f"{name} reached a path outside allowed_paths without refusing",
                    )
                    self.assertEqual(
                        "sandbox", result["error"]["kind"],
                        f"{name} failed for some reason other than the sandbox: "
                        f"{result['error']}",
                    )


# closes: #170
class BuiltinNamesMatchTheLiveRegistryTests(unittest.TestCase):
    """Step 3 of the add-a-builtin contract, enforced rather than remembered.

    `builtins/__init__.py` documents three steps: implement it, `registry.add`
    it, and add the name to `BUILTIN_NAMES`. Only the first two have any effect
    at runtime, so step 3 is the one that gets forgotten — **this change forgot
    it**, and the failure surfaced two files away as "classified but not a
    builtin", which names the symptom rather than the omission.

    `BUILTIN_NAMES` is the set every capability totality check is measured
    against (`test_every_builtin_is_classified`), so a builtin missing from it
    is not merely undocumented: it is **exempt from classification**, and a new
    one with real authority can be added without any check noticing. That is
    what #616 recorded after the fact.

    The equality is checked in both directions and is independent of the
    capability flags — a withheld group is registered as refusing stubs, so the
    names are present either way.
    """

    def _live_builtins(self, **kwargs) -> set:
        rt = NodusRuntime(timeout_ms=None, **kwargs)
        rt.run_source("fn main() { }")
        return set(rt.active_vm().builtins)

    def test_the_registry_and_builtin_names_agree(self):
        from nodus.builtins.nodus_builtins import BUILTIN_NAMES  # noqa: PLC0415
        live = self._live_builtins()
        self.assertEqual(
            set(), live - set(BUILTIN_NAMES),
            "registered builtin(s) missing from BUILTIN_NAMES — they are exempt "
            "from every capability totality check until added (step 3 of the "
            "contract in builtins/__init__.py)",
        )
        self.assertEqual(
            set(), set(BUILTIN_NAMES) - live,
            "BUILTIN_NAMES lists name(s) nothing registers; a stale name reads "
            "as coverage and provides none",
        )

    def test_the_set_does_not_depend_on_the_capability_flags(self):
        """A withheld group is replaced by refusing stubs, not removed. If that
        ever changed, the check above would pass or fail depending on which
        flags the test happened to use."""
        self.assertEqual(
            self._live_builtins(),
            self._live_builtins(allow_subprocess=True, allow_network=True,
                                allow_env=True),
        )


# closes: #170
class FilesystemBuiltinsReachACapabilityPolicyTests(_FsCase):
    """The other half of #467, and the half that actually failed there.

    `_ensure_path_allowed` enforces `allowed_paths` and the Floor. A
    `CapabilityPolicy` is a *separate* mechanism consulted at
    `VM.call_builtin`, and it can only see a builtin that
    `BUILTIN_CAPABILITIES` names. #467 was a builtin reaching the chokepoint and
    still being invisible to the policy — "the map, not the chokepoint" — so the
    sweep above would have passed while the bug was live.

    This asserts the policy is *consulted*, not that it denies: the paths are
    inside the sandbox and the policy allows, so what is under test is whether
    the request reaches it at all.
    """

    def test_every_classified_filesystem_builtin_is_visible_to_a_policy(self):
        from nodus.runtime.capability import (  # noqa: PLC0415
            CapabilityDecision,
            CapabilityPolicy,
        )

        class Recorder(CapabilityPolicy):
            def __init__(self):
                self.seen: list[tuple] = []

            def check(self, request):
                self.seen.append((request.target, request.capability))
                return CapabilityDecision.allow()

        fs_builtins = {name: cap for name, cap in BUILTIN_CAPABILITIES.items()
                       if cap in (FS_READ, FS_WRITE)}
        # Real targets, so a builtin that validates before consulting the policy
        # is not excused by an argument error.
        (self.dir / "file.txt").write_text("data", encoding="utf-8")
        (self.dir / "sub").mkdir()
        target = q(self.dir / "file.txt")

        for name in sorted(fs_builtins):
            with self.subTest(builtin=name):
                policy = Recorder()
                rt = NodusRuntime(timeout_ms=None, max_steps=None,
                                  allowed_paths=[str(self.dir)],
                                  capability_policy=policy)
                rt.run_source("fn main() { }")
                arity = rt.active_vm().builtins[name].arity
                if arity == 1:
                    call = f"{name}({target})"
                else:
                    second = (FilesystemBuiltinsAreSandboxedTests.SECOND_ARG
                              .get(name,
                                   FilesystemBuiltinsAreSandboxedTests.DEFAULT_SECOND_ARG))
                    call = f"{name}({target}, {second})"
                rt.run_source(f"fn main() {{ {call} }}")
                requested = dict(policy.seen)
                self.assertIn(
                    name, requested,
                    f"{name} is classified {fs_builtins[name]!r} but a "
                    f"CapabilityPolicy never saw it — the map says one thing and "
                    f"the chokepoint another (#467)",
                )
                self.assertEqual(fs_builtins[name], requested[name])


if __name__ == "__main__":
    unittest.main()
