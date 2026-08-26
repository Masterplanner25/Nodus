"""`nodus docs` — where the guide, the index and the agent skills live (#605).

Nothing in an installed `nodus-lang` used to lead anywhere. The wheel ships
Python and `stdlib/*.nd`; `llms.txt`, `docs/` and `skills/` are repo-only. The
README points at them, but with relative links, and PyPI's renderer strips those
entirely — fetched the live page and `llms.txt`, `nodus.skill` and
`project-CLAUDE.md` were not rendered as links at all. So an agent working inside
a venv, which is where this was reported from, had no next step.

This is the only one of the three fixes that reaches that agent: it runs from the
install itself.

**The URLs are pinned to the running version, not to `main`.** An agent on 5.2.0
reading `main`'s guide is how the skill came to teach a `timeout_ms` default that
had been removed two releases earlier. `docs.nodus` is deliberately absent from
this list because it does not exist; a plausible-looking dead link is worse than
none.
"""

from __future__ import annotations

import os

from nodus.support.version import __version__

REPO = "https://github.com/Masterplanner25/Nodus"


def _tag_base() -> str:
    """Blob root for the *running* version, falling back to `main`.

    A dev build (`5.5.0` before its tag exists) would 404 against a tag, so the
    caller gets `main` and is told which it got.
    """
    return f"{REPO}/blob/v{__version__}"


def bundled_llms_txt() -> str | None:
    """Path to the `llms.txt` shipped inside the package, if it is there.

    Ships as package data from #605 onward. Returns None on an older install
    rather than raising, so `nodus docs` still works there and simply says the
    file is not bundled.
    """
    candidate = os.path.join(os.path.dirname(os.path.dirname(__file__)), "llms.txt")
    return candidate if os.path.isfile(candidate) else None


def report() -> dict:
    base = _tag_base()
    bundled = bundled_llms_txt()
    return {
        "version": __version__,
        "bundled_llms_txt": bundled,
        "entries": [
            {
                "name": "llms.txt",
                "what": "machine-readable project index — start here if you are an agent",
                "where": bundled or f"{base}/llms.txt",
                "local": bundled is not None,
            },
            {
                "name": "llms-full.txt",
                "what": "full content summaries for indexers",
                "where": f"{base}/llms-full.txt",
                "local": False,
            },
            {
                "name": "Getting started",
                "what": "the guide, and the index of every other guide page",
                "where": f"{base}/docs/guide/getting-started.md",
                "local": False,
            },
            {
                "name": "Embedding",
                "what": "NodusRuntime, and the capability defaults that deny by default "
                        "since v5.0.0",
                "where": f"{base}/docs/guide/embedding-nodus.md",
                "local": False,
            },
            {
                "name": "Claude Code skill",
                "what": "drop in .claude/commands/ — idioms, gotchas, verified examples",
                "where": f"{base}/skills/nodus.skill",
                "local": False,
            },
            {
                "name": "Codex / AGENTS.md",
                "what": "the same material as a project AGENTS.md",
                "where": f"{base}/skills/project-AGENTS.md",
                "local": False,
            },
            {
                "name": "CLAUDE.md template",
                "what": "copy to your project root as CLAUDE.md",
                "where": f"{base}/skills/project-CLAUDE.md",
                "local": False,
            },
        ],
    }


def format_report(data: dict) -> str:
    lines = [
        f"Nodus {data['version']} — documentation and agent material",
        "",
    ]
    for entry in data["entries"]:
        marker = "local" if entry["local"] else "web"
        lines.append(f"  {entry['name']}")
        lines.append(f"    {entry['what']}")
        lines.append(f"    [{marker}] {entry['where']}")
        lines.append("")
    if data["bundled_llms_txt"] is None:
        lines.append("`llms.txt` is not bundled in this install — links point at the")
        lines.append(f"v{data['version']} tag on GitHub.")
    else:
        lines.append("Links are pinned to this version, not `main`: a guide describing a")
        lines.append("different release is how agent guidance goes quietly wrong.")
    return "\n".join(lines)
