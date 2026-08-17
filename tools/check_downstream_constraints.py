"""Does every published companion's `nodus-lang` range admit this version?

Stage 6 of the release sequence asks exactly this, and for v5.0.0 it was answered
by reading six `pyproject.toml` files by eye and transcribing them into a table.
Five of the six transcriptions dropped the upper bound, so the sweep recorded
"no companion caps its range" when in fact only one of the six could install
alongside the new release at all. `pip install nodus-lang==5.0.0 nodus-mcp` was
`ResolutionImpossible` for a full day before a downstream team reported it.

The failure is not carelessness that more care would fix. `>=4.0.0,<5.0.0` reads
as admitting 4.x, which is what the eye is checking for; the clause that forbids
5.0.0 is at the far end of the string. Ask a machine.

Two things this checks that reading a local checkout cannot:

- It reads **published** metadata from the index, not `pyproject.toml`. What
  blocks a user's `pip install` is what is on PyPI, which is a *previous* release
  of the companion — a floated cap sitting unreleased in `main` helps nobody.
- It resolves the actual version against the actual specifier with `packaging`,
  rather than pattern-matching the string.

Usage::

    python -m tools.check_downstream_constraints
    python -m tools.check_downstream_constraints --version 5.1.0   # pre-flight a bump

Exit status is 0 only when every published companion admits the version. Network
failure exits non-zero: an unanswered question is not a pass.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

from packaging.requirements import Requirement
from packaging.version import Version

# Companions that declare a `nodus-lang` dependency, published to PyPI.
#
# Packages with no nodus-lang dependency (nodus-a2a, nodus-memory,
# nodus-store-sql, nodus-workflow) cannot be blocked by a range and are omitted.
# nodus-vscode and nodus-run-action are not on PyPI at all — the VSIX is manual
# and the action pins a version in YAML — so they stay hand-checked at Gate 3b.
COMPANIONS = [
    "nodus-mcp",
    "nodus-mcp-server",
    "nodus-extension",
    "nodus-sdk",
    "nodus-native-memory-engine",
    "nodus-jupyter",
]

PYPI_JSON = "https://pypi.org/pypi/{}/json"


def current_version() -> str:
    from nodus.support.version import __version__

    return __version__


def fetch(package: str) -> tuple[str, list[str]]:
    """Return (published version, its nodus-lang requirement strings)."""
    req = urllib.request.Request(
        PYPI_JSON.format(package),
        headers={"Cache-Control": "no-cache", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as fh:
        data = json.load(fh)
    requires = data["info"].get("requires_dist") or []
    return data["info"]["version"], [r for r in requires if "nodus-lang" in r]


def admits(requirement: str, version: str) -> bool:
    """Does this Requires-Dist string admit `version`?

    `prereleases=True` so a release candidate is judged by the specifier rather
    than silently excluded by packaging's default.
    """
    return Requirement(requirement).specifier.contains(Version(version), prereleases=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--version",
        default=None,
        help="version to check (default: this checkout's nodus-lang version)",
    )
    args = parser.parse_args(argv)
    version = args.version or current_version()

    print(f"Do published companions admit nodus-lang {version}?\n")
    print(f"{'companion':<28} {'published':<10} {'nodus-lang range':<26} verdict")
    print("-" * 78)

    blocked: list[tuple[str, str, str]] = []
    errors: list[str] = []

    for name in COMPANIONS:
        try:
            published, reqs = fetch(name)
        except (urllib.error.URLError, OSError, KeyError, ValueError) as exc:
            errors.append(f"{name}: {exc}")
            print(f"{name:<28} {'?':<10} {'UNREACHABLE':<26} ERROR")
            continue

        if not reqs:
            print(f"{name:<28} {published:<10} {'(no nodus-lang dep)':<26} n/a")
            continue

        for req in reqs:
            spec = str(Requirement(req).specifier) or "(any)"
            if admits(req, version):
                print(f"{name:<28} {published:<10} {spec:<26} ok")
            else:
                print(f"{name:<28} {published:<10} {spec:<26} BLOCKED")
                blocked.append((name, published, spec))

    print()
    if errors:
        print("Could not reach the index for:")
        for err in errors:
            print(f"  - {err}")
        print("\nAn unanswered question is not a pass.")
        return 2

    if blocked:
        print(f"{len(blocked)} companion(s) cannot install alongside nodus-lang {version}:\n")
        for name, published, spec in blocked:
            print(f"  {name} {published} requires nodus-lang{spec}")
        print(
            "\nUsers of these packages cannot install the release. Float or widen the\n"
            "range and republish the companion; a fix sitting unreleased in `main`\n"
            "does not help, because pip reads the published metadata."
        )
        return 1

    print(f"All {len(COMPANIONS)} companions admit nodus-lang {version}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
