"""The documented `NodusRuntime` defaults agree with the constructor.

The `allow_*` capability switches flipped to deny-by-default at v5.0.0 (#405). The
prose in `OPERATOR_OR_EMBEDDER_RUNBOOK.md` was corrected at 5.3.0 — and the
**table three lines above it**, plus the whole parameter list in `EMBEDDING.md`,
went on saying `True` for the seven releases after that. Both were found by
reading `NodusRuntime.__init__` while documenting an unrelated parameter.

One question — *what is this parameter's default* — answered in three places,
one of them updated. That is this codebase's signature defect shape in
documentation form, and the fix that generalises is the same one it always is:
**derive the answer instead of restating it.** A doc cannot import the
signature, so the next best thing is a test that reads both and compares.

The failure this guards against is not a typo. It is a *reversal that reads as
advice*: "set `False` unless scripts must shell out" tells an embedder to opt out
of a capability they must in fact opt into, and it is wrong in the direction that
costs them a guarantee they think they have.

**`_locate` asserting it found something is the load-bearing part.** A scan that
silently matches nothing passes forever and checks nothing — the failure mode
that has bitten source-assertions in this repo more than once. If a document
stops documenting a parameter, that is itself a finding, so this test fails
rather than quietly narrowing.
"""

import inspect
import re
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))  # noqa: E402

from nodus import NodusRuntime  # noqa: E402

#: Parameters whose default is a bare bool, so a document can state it exactly.
#: Derived, not listed -- a new bool flag joins automatically and must be
#: documented, which is the point.
BOOL_PARAMS = {
    name: parameter.default
    for name, parameter in inspect.signature(NodusRuntime.__init__).parameters.items()
    if isinstance(parameter.default, bool)
}

#: Each document, and the shapes in which it states a default. Both were written
#: from the two real spellings in the tree; a third spelling elsewhere is not
#: covered and would need adding here.
DOCUMENTS = {
    "docs/runtime/OPERATOR_OR_EMBEDDER_RUNBOOK.md": (
        # | `allow_subprocess` | `bool` | **`False`** (#405) | ...
        r"^\|\s*`{name}`\s*\|[^|]*\|\s*\**`(?P<value>True|False)`",
    ),
    "docs/runtime/EMBEDDING.md": (
        # - `allow_subprocess` (bool, default `False`): ...
        r"^-\s*`{name}`\s*\([^)]*default\s*`(?P<value>True|False)`",
    ),
}


def _locate(text: str, pattern: str, name: str, where: str) -> list[str]:
    found = [
        match.group("value")
        for match in re.finditer(
            pattern.format(name=re.escape(name)), text, re.MULTILINE
        )
    ]
    assert found, (
        f"{where} states no default for `{name}` in the expected shape. Either the "
        f"parameter went undocumented -- a finding in itself -- or the document "
        f"changed spelling and this test's pattern needs updating. It must not "
        f"pass by matching nothing."
    )
    return found


class DocumentedDefaultsTests(unittest.TestCase):
    # closes: #167
    def test_the_capability_switches_are_documented_as_denying(self):
        """The specific reversal, stated plainly so a failure names it."""
        for flag in ("allow_subprocess", "allow_network", "allow_env"):
            with self.subTest(flag=flag):
                self.assertFalse(
                    BOOL_PARAMS[flag],
                    "deny-by-default is the #405 contract; if this is now True "
                    "the change is breaking and every document must move with it",
                )

    # closes: #167
    def test_every_document_states_the_real_default(self):
        for relative, patterns in DOCUMENTS.items():
            text = (_REPO_ROOT / relative).read_text(encoding="utf-8")
            for pattern in patterns:
                for name, default in BOOL_PARAMS.items():
                    with self.subTest(document=relative, parameter=name):
                        for stated in _locate(text, pattern, name, relative):
                            self.assertEqual(
                                str(default), stated,
                                f"{relative} says `{name}` defaults to {stated}; "
                                f"NodusRuntime.__init__ says {default}",
                            )


if __name__ == "__main__":
    unittest.main()
