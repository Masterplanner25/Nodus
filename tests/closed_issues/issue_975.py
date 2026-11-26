"""Closed-issue test for #975: no CLI path crashes on text stdout cannot encode.

On Windows, a redirected stdout is encoded with the system code page (cp1252
here). `nodus run` caught `UnicodeEncodeError` and fell back to UTF-8 bytes, but
`nodus dis`, `nodus ast` and `nodus run --dump-bytecode` printed with a bare
`print()` and exited 1 on a program holding `"→"`. It was one check written at
two of the places that print, plus a third copy in `nodus test`, with every
other site missing it.

The behaviour half runs each command in a subprocess with
`PYTHONIOENCODING=cp1252`, which gives stdout the encoding a Windows redirect
gets, on any OS. The source half is what keeps it fixed. A new command's
`print()` would crash the same way, so `nodus.cli`, `nodus.tooling` and
`nodus.testing` may not print to stdout except through
`nodus.support.console`.
"""
import ast
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).parents[2]
_PACKAGES = ("src/nodus/cli", "src/nodus/tooling", "src/nodus/testing")

_PROGRAM = '// arrow → here\nfn f() {\n    return "→"\n}\nprint(f())\n'


def _run(*args, cwd):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(_ROOT / "src")
    env["PYTHONIOENCODING"] = "cp1252"
    env.pop("PYTHONUTF8", None)
    return subprocess.run(
        [sys.executable, str(_ROOT / "nodus.py"), *args],
        cwd=cwd, env=env, capture_output=True, timeout=120,
    )


# closes: #975
class EveryCommandSurvivesAnUnencodableCharacter(unittest.TestCase):
    COMMANDS = [
        ("run",),
        ("dis",),
        ("ast",),
        ("run", "--dump-bytecode"),
        ("profile",),
        ("check",),
    ]

    def test_each_command(self):
        with tempfile.TemporaryDirectory() as directory:
            script = os.path.join(directory, "arrow.nd")
            with open(script, "w", encoding="utf-8") as handle:
                handle.write(_PROGRAM)
            for command in self.COMMANDS:
                with self.subTest(" ".join(command)):
                    proc = _run(*command, script, cwd=directory)
                    stderr = proc.stderr.decode("utf-8", errors="replace")
                    self.assertNotIn("UnicodeEncodeError", stderr)
                    self.assertEqual(proc.returncode, 0, stderr)

    def test_the_text_arrives_as_utf8(self):
        with tempfile.TemporaryDirectory() as directory:
            script = os.path.join(directory, "arrow.nd")
            with open(script, "w", encoding="utf-8") as handle:
                handle.write(_PROGRAM)
            for command in (("run",), ("dis",), ("ast",)):
                with self.subTest(" ".join(command)):
                    proc = _run(*command, script, cwd=directory)
                    self.assertIn("→".encode("utf-8"), proc.stdout)


class TheHelper(unittest.TestCase):
    def _stream(self, encoding):
        raw = io.BytesIO()
        return raw, io.TextIOWrapper(raw, encoding=encoding, newline="")

    def test_encodable_text_goes_through_the_text_layer(self):
        from nodus.support.console import write_stdout
        raw, stream = self._stream("cp1252")
        write_stdout("café\n", stream)
        stream.flush()
        self.assertEqual(raw.getvalue(), "café\n".encode("cp1252"))

    def test_unencodable_text_lands_after_what_was_buffered(self):
        # Two of the three old copies wrote the bytes without flushing the
        # text layer first, so the bytes could overtake earlier output.
        from nodus.support.console import write_stdout
        raw, stream = self._stream("cp1252")
        write_stdout("before ", stream)
        write_stdout("→\n", stream)
        stream.flush()
        self.assertEqual(raw.getvalue(), "before →\n".encode("utf-8"))

    def test_a_stream_with_no_buffer_still_raises(self):
        from nodus.support.console import write_stdout

        class NoBuffer:
            def write(self, text):
                text.encode("ascii")

            def flush(self):
                pass

        with self.assertRaises(UnicodeEncodeError):
            write_stdout("→", NoBuffer())


def _stdout_writes(path: Path):
    """`print()` calls with no `file=`, and `sys.stdout.write(...)` calls."""
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == "print":
            if not any(k.arg == "file" for k in node.keywords):
                yield node.lineno, "print()"
        elif (isinstance(func, ast.Attribute) and func.attr == "write"
              and isinstance(func.value, ast.Attribute) and func.value.attr == "stdout"
              and isinstance(func.value.value, ast.Name) and func.value.value.id == "sys"):
            yield node.lineno, "sys.stdout.write()"


# `nodus completion` writes its scripts as bytes, so a text-mode stdout cannot
# turn "\n" into "\r\n". This is its fallback for a stdout with no byte layer,
# and the scripts are ASCII.
_ALLOWED = {("src/nodus/cli/cli.py", "sys.stdout.write()"): 1}


class NothingPrintsAroundTheHelper(unittest.TestCase):
    def test_no_bare_stdout_write_in_the_cli_packages(self):
        counts = {}
        offenders = []
        for package in _PACKAGES:
            for path in sorted((_ROOT / package).rglob("*.py")):
                rel = path.relative_to(_ROOT).as_posix()
                for lineno, kind in _stdout_writes(path):
                    key = (rel, kind)
                    counts[key] = counts.get(key, 0) + 1
                    if counts[key] > _ALLOWED.get(key, 0):
                        offenders.append(f"{rel}:{lineno} {kind}")
        self.assertEqual(offenders, [], "use nodus.support.console.stdout_print / write_stdout")

    def test_the_scan_sees_a_bare_print(self):
        # The scan must not pass on its own blind spot.
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "m.py"
            path.write_text('import sys\nprint("x")\nprint("y", file=sys.stderr)\n'
                            'sys.stdout.write("z")\n', encoding="utf-8")
            found = sorted(kind for _, kind in _stdout_writes(path))
        self.assertEqual(found, ["print()", "sys.stdout.write()"])


if __name__ == "__main__":
    unittest.main()
