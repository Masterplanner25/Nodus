"""Formatting twice is the same as formatting once (#739).

`nodus fmt` writes in place and `nodus fmt --check` compares a file to its own
formatting, so a formatter without a fixed point produces files it then rejects.
That is what happened: with `keep_trailing_comments` off, a same-line trailing
comment is demoted onto its own line, where re-parsing reads it as a **leading**
comment of the next statement — and the blank-line policy then puts the blank on
the other side of it. Two passes, two files, neither stable.

**A fixture suite cannot test this.** `tests/test_formatter_fixtures.py` does
assert idempotence, but every fixture input is already a fixed point, so the
second assertion re-checks a file with nothing left to move. The property holds
there because it cannot fail there. Testing it needs sources that have *not*
been formatted, which is what this file is.

The fix is in `format_program`: a demoted trailing comment is emitted where the
re-parse will put it, so the second pass formats the same shape the first pass
printed. The association between the comment and its original line is still
lost — that is what `keep_trailing_comments` is for — but the formatter no
longer disagrees with itself about where the comment went.
"""

import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))  # noqa: E402

from nodus.tooling.formatter import format_source  # noqa: E402

#: Deliberately unformatted, and every one has a trailing comment somewhere the
#: demotion has to travel through. A source that is already formatted proves
#: nothing here.
UNFORMATTED = {
    "trailing on an import, then a statement":
        'import "std:math" as math // why we need it\nlet a = 1\n',
    "trailing on the last statement":
        "let a = 1 // last\n",
    # A trailing comment with nothing after it re-parses as a standalone
    # `Comment` statement, which the blank-line rule treats as neither an import
    # nor a function. These three put the previous statement in each of the
    # states that rule cares about, because the tail once answered it by hand and
    # answered it differently.
    "trailing on the last import":
        'import "std:math" as math // t\n',
    "trailing on the last of several imports":
        'import "a.nd" as a\nimport "std:math" as math // t\n',
    "trailing on a function, at end of file":
        "fn f() {\n    return 1i\n} // done\n",
    "trailing between two functions":
        "fn a() {\n    return 1i\n} // about a\nfn b() {\n    return 2i\n}\n",
    "several trailing comments in a row":
        'import "std:math" as math // one\nimport "std:json" as json // two\nlet x = 1\n',
    "trailing inside a body":
        "fn f() {\n    let a = 1i // note\n    let b = 2i\n    return b\n}\n",
    "trailing next to a leading comment":
        "// leading\nlet a = 1 // trailing\n// another leading\nlet b = 2\n",
    # The interleaving: a carried trailing comment and the next statement's own
    # leading comment end up adjacent, with a blank line inserted between the
    # statements. Both have to land on the same side of that blank, in source
    # order, or the second pass reorders them.
    "carried and leading comments meet across a blank line":
        'import "std:math" as math // trailing on the import\n'
        "// leading on the let\n"
        "let a = 1\n",
    "trailing on a statement before a function":
        "let a = 1 // about a\nfn f() {\n    return 1i\n}\n",
    "unformatted spacing as well":
        'import{b,a}from "mod.nd" // t\nexport{z,y}\nfn add(a,b){return a+b}\n',
}


class FormattingTwiceChangesNothingTests(unittest.TestCase):
    # closes: #739
    def test_every_unformatted_source_reaches_a_fixed_point_in_one_pass(self):
        """One pass, not eventually. `fmt --check` compares against a single
        formatting, so converging on the third pass is still a rejected file."""
        for name, source in UNFORMATTED.items():
            with self.subTest(source=name):
                once = format_source(source)
                self.assertEqual(
                    once, format_source(once),
                    "formatting the output changed it again",
                )

    # closes: #739
    def test_the_same_holds_with_trailing_comments_kept(self):
        """The mode that keeps a trailing comment on its line never had the bug —
        nothing moves, so nothing can be re-read differently. Pinned so a fix
        aimed at the default mode cannot break the other one."""
        for name, source in UNFORMATTED.items():
            with self.subTest(source=name):
                once = format_source(source, keep_trailing_comments=True)
                self.assertEqual(
                    once, format_source(once, keep_trailing_comments=True)
                )

    # closes: #739
    def test_the_repositorys_own_files_are_fixed_points(self):
        """Weak on its own — every `.nd` file here has been formatted, so this
        would pass against a formatter that converged nowhere. It is here to
        catch the opposite failure: a fix that converges but changes what the
        tree already contains.

        **Driven off `git ls-files`, not `rglob`.** Globbing the working tree
        swept nine local virtualenvs holding installed copies of the stdlib —
        240 files of somebody else's release next to 61 of this repo's own
        source. That made the count environment-dependent (this test asserted
        `> 200` and CI collected 61), and it made the coverage claim wrong in
        the flattering direction: most of what was "checked" was a formatted
        artefact of an older release, not code anyone edits here.
        """
        listed = subprocess.run(
            ["git", "ls-files", "*.nd"],
            capture_output=True, text=True, cwd=str(_REPO_ROOT), timeout=120,
        )
        self.assertEqual(0, listed.returncode, listed.stderr)
        paths = [
            _REPO_ROOT / line
            for line in listed.stdout.splitlines()
            if line and "fixtures" not in Path(line).parts  # deliberately unformatted
        ]
        for path in paths:
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.relative_to(_REPO_ROOT).as_posix()):
                self.assertEqual(text, format_source(text))
        self.assertGreater(len(paths), 40, "the corpus sweep collected almost nothing")


class TheCliAcceptsWhatItJustWroteTests(unittest.TestCase):
    """The property stated the way a user meets it. `format_source` agreeing with
    itself is the mechanism; `fmt` then `fmt --check` is the contract, and CI and
    the pre-commit hook both depend on it."""

    # closes: #739
    def test_fmt_then_fmt_check_passes(self):
        source = 'import "std:math" as math // why we need it\nlet a = 1\n'
        env = dict(os.environ, PYTHONPATH=str(_REPO_ROOT / "src"))
        with TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "idem.nd")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(source)

            wrote = subprocess.run(
                [sys.executable, str(_REPO_ROOT / "nodus.py"), "fmt", path],
                capture_output=True, text=True, env=env, timeout=180,
            )
            self.assertEqual(0, wrote.returncode, wrote.stderr)

            checked = subprocess.run(
                [sys.executable, str(_REPO_ROOT / "nodus.py"), "fmt", "--check", path],
                capture_output=True, text=True, env=env, timeout=180,
            )
        self.assertNotIn(
            "not formatted", checked.stdout + checked.stderr,
            "fmt wrote a file that fmt --check rejects",
        )


if __name__ == "__main__":
    unittest.main()
