"""Closed-issue test for #483: a package may not take a language construct's name.

`nodus-workflow` on PyPI was a standalone asyncio DAG runner, not the engine
behind the `workflow` keyword. The name read as though it were, and that
misreading is on the record: Audit 03 F1 attributed the standalone package's
architecture to the language core, concluded the project had "forked its own
thesis", and made resolving it its top recommendation of five. It stood in
`EXTERNAL_AUDIT_LEDGER.md` as a confirmed finding for months. The package is
`nodus-flow` as of 0.2.0, and `COMPANION_LIBRARY_CONTRACT.md` §8b carries the
general rule.

The regression this guards is a documentation one, because that is where it
lives: nothing in nodus-lang's *code* names the package. Two assertions —

1. the rule is still stated, and
2. no first-party doc presents `nodus-<keyword>` as a current package.

The second drives off `lexer.KEYWORDS` rather than a hand-written list of names,
which is the point: a *new* keyword automatically reserves its `nodus-` name, so
the third instance fails the suite the day it lands instead of being noticed by
an auditor months later. That is the "name the set once and drive a test off the
tuple" pattern CLAUDE.md prescribes for the recurring bug shape, applied to a
naming collision rather than a code path.
"""

import re
import sys
from pathlib import Path

# closes: #483

_REPO_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(_REPO_ROOT / "src"))  # noqa: E402

from nodus.frontend.lexer import KEYWORDS  # noqa: E402

_CONTRACT = _REPO_ROOT / "docs" / "governance" / "COMPANION_LIBRARY_CONTRACT.md"

# Reader-facing documents that present the ecosystem as a list of installables.
# These are where a wrong name is actually met.
_ECOSYSTEM_DOCS = [
    _REPO_ROOT / "docs" / "ecosystem" / "README.md",
    _REPO_ROOT / "docs" / "ecosystem" / "PACKAGE_QUICK_REF.md",
]

# A mention is exempt when the same line says the name is historical. Kept
# deliberately narrow: "it is deprecated" must be *on the line*, so a stale row
# cannot inherit an exemption from a paragraph elsewhere in the file.
_HISTORICAL = re.compile(
    r"was\s|formerly|deprecat|renamed|superseded|#483", re.IGNORECASE
)


def test_reserved_construct_name_rule_is_stated():
    text = _CONTRACT.read_text(encoding="utf-8")
    assert "## 8b." in text, (
        "COMPANION_LIBRARY_CONTRACT.md must keep the reserved-name section (§8b). "
        "It is the rule that prevents the third instance of #483."
    )
    assert "must be the implementation of" in text, (
        "§8b must still state the rule itself: a first-party distribution named "
        "nodus-<X>, where <X> is a language construct, must be the implementation "
        "of <X> or must not use the name."
    )


def test_no_language_construct_name_is_presented_as_a_current_package():
    offenders = []
    for doc in _ECOSYSTEM_DOCS:
        for lineno, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
            if _HISTORICAL.search(line):
                continue
            for keyword in sorted(KEYWORDS):
                # Word-boundary on the right so `nodus-workflow` does not match
                # inside `nodus-workflow-ai`, which is a different package.
                if re.search(rf"\bnodus-{re.escape(keyword)}\b", line):
                    offenders.append(
                        f"{doc.relative_to(_REPO_ROOT).as_posix()}:{lineno} "
                        f"-> nodus-{keyword}"
                    )
    assert not offenders, (
        "A distribution named after a language construct is presented as a current "
        "first-party package. Per COMPANION_LIBRARY_CONTRACT.md §8b it must either "
        "be the implementation of that construct or use a different name; if the "
        "mention is historical, say so on the same line. Offending lines:\n  "
        + "\n  ".join(offenders)
    )
