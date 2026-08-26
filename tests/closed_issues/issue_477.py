"""Closed-issue test for #477: two distributions may not ship one Python module.

`nodus-a2a-wire` declared the distribution name `nodus-a2a`, taken by the
coordinator, so it could not be published at all. Renaming the distribution was
not sufficient: both projects also shipped a Python module called `nodus_a2a`, so
installing them together wrote one over the other. Measured before the fix —
installing the wire adapter on top of the published coordinator left
`AgentCoordinator`, `AgentRegistry` and `DeadLetterService` gone, with pip
reporting success. The wire module is `nodus_a2a_wire` now.

This is the NAME-COL-001 shape, which the in-tree modules already hit once
(`nodus_workflow` -> `nodus_lang_workflow`): the **distribution** name is what a
user types, the **module** name is what Python resolves, and fixing one does not
fix the other. #483 was the first half of that lesson at the distribution layer;
this is the second half at the import layer.

The check drives off `check_publish_drift.COMPANIONS` rather than a hand-written
list, so a companion added there is covered the day it lands — the "name the set
once and drive a test off the tuple" pattern from CLAUDE.md's recurring-shape
section. It is a pure-data check: no checkout is read and no network is used, so
it runs anywhere.
"""

import sys
from pathlib import Path

# closes: #477

_REPO_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(_REPO_ROOT))  # noqa: E402

from tools.check_publish_drift import COMPANIONS  # noqa: E402


def _module_name(package_dir: str) -> str:
    """`src/nodus_a2a_wire` and `nodus_flow` both reduce to the import name."""
    return package_dir.replace("\\", "/").rstrip("/").split("/")[-1]


def test_no_two_companions_ship_the_same_python_module():
    by_module: dict[str, list[str]] = {}
    for dist, (_root, package_dir) in COMPANIONS.items():
        by_module.setdefault(_module_name(package_dir), []).append(dist)

    collisions = {mod: sorted(d) for mod, d in by_module.items() if len(d) > 1}

    assert not collisions, (
        "Two published distributions ship the same Python module, so installing "
        "both writes one over the other and pip reports success either way. "
        "Rename the module, not just the distribution — see #477 and "
        "COMPANION_LIBRARY_CONTRACT.md. Collisions: "
        + "; ".join(f"{mod} <- {', '.join(dists)}" for mod, dists in collisions.items())
    )


def test_the_wire_adapter_kept_its_distinct_module():
    """The specific pair that collided, pinned so it cannot regress quietly."""
    assert _module_name(COMPANIONS["nodus-a2a"][1]) == "nodus_a2a"
    assert _module_name(COMPANIONS["nodus-a2a-wire"][1]) == "nodus_a2a_wire"
