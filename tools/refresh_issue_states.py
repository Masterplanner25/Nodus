"""Refresh `tools/issue_states.json`, the issue-state cache `nodus_gate --open-claims` reads.

    python -m tools.refresh_issue_states

The gate never calls the network: a phase that needs something absent on CI
ends up skipping there, and a check that skips where it matters is not a check
(see `consumers_phase.py`). So the states are cached here and committed, and
this tool is the only thing that writes them. It uses the `gh` CLI, which must
be authenticated.

**The cache can only be as fresh as its last refresh.** An issue closed since
then still reads as open, so a doc calling it open is not flagged until the
next refresh. The miss errs in the quiet direction, and the release sequence
refreshes before running the phase strict, which bounds it to one cycle.

Exit codes: 0 written, 1 `gh` failed or returned something unusable.
"""

from __future__ import annotations

import datetime as _dt
import json
import subprocess
import sys
from pathlib import Path

REPO = "Masterplanner25/Nodus"
CACHE = Path(__file__).resolve().parent / "issue_states.json"

_COMMENT = [
    "Issue states for `nodus_gate --open-claims` (#931). Written only by",
    "`python -m tools.refresh_issue_states`; do not edit by hand.",
    "",
    "Issues only: a pull request shares the number space but is never listed.",
    "A number in neither list is unknown to this cache (a PR, or an issue filed",
    "since the refresh), and the phase reports a claim about one as unknown",
    "rather than guessing.",
]


def fetch_states(repo: str = REPO) -> dict[int, str]:
    proc = subprocess.run(
        ["gh", "issue", "list", "--repo", repo, "--state", "all", "--limit", "10000",
         "--json", "number,state"],
        capture_output=True, text=True, encoding="utf-8",
    )
    if proc.returncode != 0:
        raise RuntimeError(f"gh issue list failed: {proc.stderr.strip()}")
    rows = json.loads(proc.stdout)
    states: dict[int, str] = {}
    for row in rows:
        state = str(row["state"]).upper()
        if state not in ("OPEN", "CLOSED"):
            raise RuntimeError(f"unexpected state {state!r} for #{row['number']}")
        states[int(row["number"])] = state
    if not states:
        raise RuntimeError("gh returned no issues; refusing to write an empty cache")
    return states


def render(states: dict[int, str], today: str) -> str:
    payload = {
        "_comment": _COMMENT,
        "repo": REPO,
        "refreshed": today,
        "open": sorted(n for n, s in states.items() if s == "OPEN"),
        "closed": sorted(n for n, s in states.items() if s == "CLOSED"),
    }
    return json.dumps(payload, indent=2) + "\n"


def main() -> int:
    try:
        states = fetch_states()
    except (RuntimeError, OSError, ValueError) as exc:
        print(f"refresh failed: {exc}", file=sys.stderr)
        return 1
    CACHE.write_text(render(states, _dt.date.today().isoformat()), encoding="utf-8")
    n_open = sum(1 for s in states.values() if s == "OPEN")
    print(f"wrote {CACHE.name}: {len(states)} issues, {n_open} open")
    return 0


if __name__ == "__main__":
    sys.exit(main())
