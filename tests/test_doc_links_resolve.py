"""Every relative markdown link in a tracked document resolves to a real file.

`nodus_gate` checks a great deal about the docs — that documented symbols exist,
that code blocks run and produce the output claimed, that version claims agree —
and **nothing checked that a link goes anywhere**. So moving a document broke
links silently, and the only way to find out was for a reader to click one.

That is not hypothetical. Sorting `docs/governance/` from 63 documents into
governance / audits / history (2026-09-07) broke **eleven** links across six
files. All eleven were found by writing this check, not by reading the diff.

Scope, and why each bound is where it is:

* **Tracked files only.** `git ls-files`, so a scratch document in an ignored
  directory cannot fail the suite for a link into something equally local.
* **Relative links only.** An `http(s)://` target is a network question and
  would make this test flaky and slow; a link checker that needs the internet
  gets disabled the first week it goes red on someone's train.
* **`.md` targets only.** Links to source files move for different reasons and
  are covered by the gate's symbol phase.
* **Anchors are stripped, not verified.** `FILE.md#section` checks the file. A
  heading check is a real thing to want, and a separate one — a wrong anchor
  lands the reader on the right page.
"""

import pathlib
import re
import subprocess
import unittest

REPO = pathlib.Path(__file__).resolve().parents[1]

#: `[text](target.md)` or `[text](target.md#anchor)`. Deliberately not matching
#: reference-style links or bare URLs: this repo writes inline links, and a
#: pattern that tried to catch every form would report shapes nobody uses.
LINK = re.compile(r"\[([^\]]*)\]\(([^)#\s]+\.md)(#[^)]*)?\)")


def tracked_markdown() -> list[pathlib.Path]:
    out = subprocess.run(
        ["git", "ls-files", "*.md"], cwd=REPO, capture_output=True, text=True, check=True
    )
    return [REPO / line for line in out.stdout.split("\n") if line.strip()]


def broken_links(paths) -> list[str]:
    problems: list[str] = []
    for path in paths:
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for match in LINK.finditer(text):
            target = match.group(2)
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            if not (path.parent / target).resolve().is_file():
                rel = path.relative_to(REPO) if path.is_relative_to(REPO) else path
                problems.append(f"{rel}: [{match.group(1)[:40]}]({target})")
    return problems


class EveryDocLinkResolvesTests(unittest.TestCase):
    def test_no_tracked_document_links_to_a_missing_file(self):
        problems = broken_links(tracked_markdown())
        self.assertEqual(
            problems,
            [],
            f"{len(problems)} markdown link(s) point at a file that does not "
            f"exist. Moving a document means repointing what links to it:\n  "
            + "\n  ".join(problems),
        )

    def test_the_sweep_reads_a_real_corpus(self):
        """Guards the other direction: a glob matching nothing passes vacuously.

        The failure this test exists to catch is silence, so it must not be able
        to be silent for the wrong reason.
        """
        paths = tracked_markdown()
        self.assertGreater(len(paths), 100, "git ls-files returned almost nothing")
        found = sum(len(LINK.findall(p.read_text(encoding="utf-8"))) for p in paths if p.is_file())
        self.assertGreater(found, 100, "the link pattern matched almost nothing")


class TheCheckCanFireTests(unittest.TestCase):
    """A negative assertion that cannot fail is worse than none (#815)."""

    def _check(self, body: str, *, alongside: str | None = None) -> list[str]:
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            doc = root / "doc.md"
            doc.write_text(body, encoding="utf-8")
            if alongside:
                (root / alongside).write_text("x", encoding="utf-8")
            return broken_links([doc])

    def test_a_link_to_a_missing_file_is_reported(self):
        problems = self._check("See [the plan](GONE.md).\n")
        self.assertEqual(len(problems), 1)
        self.assertIn("GONE.md", problems[0])

    def test_a_link_to_a_present_file_is_not(self):
        """The control. Without it the case above passes for any broken matcher."""
        self.assertEqual(self._check("See [it](THERE.md).\n", alongside="THERE.md"), [])

    def test_an_anchor_does_not_change_the_answer(self):
        self.assertEqual(
            self._check("See [it](THERE.md#a-section).\n", alongside="THERE.md"), []
        )
        self.assertEqual(len(self._check("See [it](GONE.md#a-section).\n")), 1)

    def test_an_external_link_is_left_alone(self):
        self.assertEqual(
            self._check("See [it](https://example.invalid/GONE.md).\n"), []
        )

    def test_a_relative_parent_path_resolves(self):
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            (root / "sub").mkdir()
            (root / "TARGET.md").write_text("x", encoding="utf-8")
            doc = root / "sub" / "doc.md"
            doc.write_text("See [it](../TARGET.md).\n", encoding="utf-8")
            self.assertEqual(broken_links([doc]), [])
            doc.write_text("See [it](../MISSING.md).\n", encoding="utf-8")
            self.assertEqual(len(broken_links([doc])), 1)


if __name__ == "__main__":
    unittest.main()
