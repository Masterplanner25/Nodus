"""`xs = list_push(xs, v)` does not appear in example code (#816).

`list_push` mutates in place and returns the list it was given, which is
documented (`standard-library.md`). The reassignment spelling produces the same
result and reads like a functional API returning a new list — so a reader who
learns lists from it has no reason to expect `let b = a` to alias, which is the
rule right next door in `types-and-values.md` §6.

It is worth a test rather than a one-time sweep because **the sweep found five
times what the issue named**. #816 cited two files; the idiom was in four, at
twenty sites, including `packages/nodus-scheduler` — real Nodus read as a
reference for how to write Nodus — and every one of the release probes. Nothing
checked, so it spread.

Two things this deliberately does **not** flag, because both are correct uses of
the return value:

* chaining — `list_push(list_push([], "a"), "b")`;
* binding the result of a push onto a literal, where there is no other name for
  the list — `let xs = list_push([1, 2], 3)`.

The pattern is narrow on purpose: a variable reassigned from a push *of itself*.

Prose that quotes the anti-pattern in order to warn about it is not a violation,
and is distinguished by being inside backticks. That is a real discriminator
rather than an allowlist — an allowlist of "lines that talk about it" goes stale
the moment someone rewords one.
"""

import pathlib
import re
import subprocess
import unittest

REPO = pathlib.Path(__file__).resolve().parents[1]

#: `name = list_push(name, ...)` / `name = push(name, ...)` — the same name on
#: both sides. `col.push` is included: it wraps `list_push` and shares its
#: semantics (finding F13 in `standard-library.md`).
REASSIGNMENT = re.compile(
    r"(?<!`)\b(?P<name>[A-Za-z_]\w*)\s*=\s*(?:[A-Za-z_]\w*\.)?(?:list_)?push\(\s*(?P=name)\s*,"
)


def tracked(*patterns: str) -> list[pathlib.Path]:
    out = subprocess.run(
        ["git", "ls-files", *patterns],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    return [REPO / line for line in out.stdout.split("\n") if line.strip()]


def offenders(paths) -> list[str]:
    found = []
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        try:
            shown = path.relative_to(REPO)
        except ValueError:
            # Not under the repo — a temp file from this file's own tests. The
            # relative form is for a readable failure message, not correctness.
            shown = path
        for number, line in enumerate(text.split("\n"), 1):
            # Backticked prose is explaining the trap, not committing it.
            if REASSIGNMENT.search(line) and "`" not in line:
                found.append(f"{shown}:{number}: {line.strip()}")
    return found


class TheIdiomIsGoneTests(unittest.TestCase):
    # closes: #816
    def test_no_nd_file_reassigns_a_list_from_a_push_of_itself(self):
        found = offenders(tracked("*.nd"))
        self.assertEqual(
            found,
            [],
            "`list_push` mutates in place and returns the same list, so the "
            "reassignment teaches a functional API that does not exist (#816). "
            "Use the bare `list_push(xs, v)`:\n  " + "\n  ".join(found),
        )

    def test_no_guide_example_reassigns_a_list_from_a_push_of_itself(self):
        found = offenders(tracked("docs/guide/*.md"))
        self.assertEqual(found, [], "\n  ".join(found))


class TheCheckCanFireTests(unittest.TestCase):
    """A negative assertion that cannot fail is worse than none (#815)."""

    def test_the_pattern_matches_the_shape_it_is_about(self):
        for line in (
            "xs = list_push(xs, 10)",
            "    seen = list_push(seen, previous)",
            "out = push(out, v)",
            "handlers = col.push(handlers, h)",
        ):
            with self.subTest(line=line):
                self.assertTrue(REASSIGNMENT.search(line), line)

    def test_the_pattern_leaves_correct_uses_alone(self):
        for line in (
            "list_push(xs, 10)",
            'let ys = list_push(list_push([], "a"), "b")',
            "let xs = list_push([1, 2], 3)",
            "out = push(other, v)",
            "let same = list_push(zs, 3)",
        ):
            with self.subTest(line=line):
                self.assertIsNone(REASSIGNMENT.search(line), line)

    def test_offenders_skips_backticked_prose_and_reports_bare_code(self):
        """Both halves against a real file, since `offenders` reads files.

        The first draft of this asserted `offenders([]) == []` and that a string
        contained a backtick — both trivially true, and neither touching the
        function. That is the #815 shape, in the file whose whole job is to stop
        an idiom coming back.
        """
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            prose = pathlib.Path(td) / "prose.md"
            prose.write_text(
                "Do not write `xs = list_push(xs, v)`; use the bare form.\n",
                encoding="utf-8",
            )
            code = pathlib.Path(td) / "code.nd"
            code.write_text("xs = list_push(xs, 10)\n", encoding="utf-8")

            self.assertEqual(offenders([prose]), [])
            self.assertEqual(len(offenders([code])), 1)
            self.assertIn("code.nd:1", offenders([code])[0])

    def test_the_sweep_reads_real_files(self):
        """Guards the other direction: a glob that matches nothing passes vacuously."""
        self.assertGreater(len(tracked("*.nd")), 50)
        self.assertGreater(len(tracked("docs/guide/*.md")), 10)


if __name__ == "__main__":
    unittest.main()
