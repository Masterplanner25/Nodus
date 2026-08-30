"""Stage 6: has a companion drifted from what it published?

The question this answers is "does the code on PyPI match the code in the
checkout" -- i.e. is there work sitting in a companion's `main` that users
cannot get. It answers it by **downloading the published sdist and comparing
file contents**, which is the only method that actually answers it.

Git heuristics do not. Counting commits since the version bump gave **four false
positives** during the v4.2.0 sweep: a commit can touch only docs, only CI, or
only tests, and none of those change what an installer receives. Conversely a
clean `git status` proves nothing, because the drift is between the *tag* and
*main*, not between main and the working tree.

Scope is deliberate:

- **Python sources under the package directory** -- what `import` gets.
- **The declared dependency list** -- a floated or tightened range is a
  publishable change even when no source byte moved, and the 5.0.0 cycle was
  broken by exactly that (five companions capping `nodus-lang<5.0.0`).

Docs, tests, CI config and packaging metadata other than dependencies are out:
they are real changes, but they are not what an installed package is.

Usage:
    python -m tools.check_publish_drift              # all known companions
    python -m tools.check_publish_drift nodus-sdk    # just one

Exit 0 when nothing has drifted, 1 when something has, 2 when a companion could
not be checked -- which is not a pass.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import sys
import tarfile
import urllib.error
import urllib.request
import zipfile

# name -> (local checkout, python package directory inside it)
COMPANIONS: dict[str, tuple[str, str]] = {
    "nodus-mcp": (r"C:\dev\nodus-mcp", "src/nodus_mcp"),
    "nodus-sdk": (r"C:\dev\nodus-sdk", "nodus_sdk"),
    "nodus-extension": (r"C:\dev\nodus-extension", "src/nodus_extension"),
    "nodus-mcp-server": (r"C:\dev\nodus-mcp-server", "nodus_mcp_server"),
    "nodus-jupyter": (r"C:\dev\nodus-jupyter", "nodus_jupyter"),
    "nodus-native-memory-engine": (r"C:\dev\nodus-native-memory-engine", "nodus_native_memory_engine"),
    "nodus-memory": (r"C:\dev\nodus-memory", "nodus_memory"),
    "nodus-a2a": (r"C:\dev\nodus-a2a", "nodus_a2a"),
    "nodus-store-sql": (r"C:\dev\nodus-store-sql", "src/nodus_store_sql"),
    # #483: published as `nodus-workflow` until 0.2.0 and never tracked here under
    # either name, so a published first-party package sat outside the drift sweep.
    # The local directory keeps its old name; only the distribution was renamed.
    # #477: published 2026-08-26. Module is `nodus_a2a_wire`, deliberately NOT
    # `nodus_a2a` — the coordinator above ships that one, and both distributions
    # writing it clobbered each other.
    "nodus-a2a-wire": (r"C:\codev\a2a-wire-pub", "src/nodus_a2a_wire"),
    "nodus-flow": (r"C:\dev\nodus-workflow", "nodus_flow"),
    # #93: published 2026-08-30, the first companion whose floor required an
    # unreleased nodus-lang. Added here in the publishing commit -- the
    # nodus-flow comment above records what happens otherwise.
    "nodus-workflow-ai": (r"C:\dev\nodus-workflow-ai", "nodus_workflow_ai"),
}

PYPI = "https://pypi.org/pypi/{name}/json"


def _fetch_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def _published_files(name: str) -> tuple[str, dict[str, str], list[str]]:
    """(version, {relative path: sha256}, requires_dist) for the latest release.

    Prefers the sdist: a wheel has already dropped anything not installed, which
    is most of what we want to compare, but the sdist keeps the layout the
    checkout has.
    """
    meta = _fetch_json(PYPI.format(name=name))
    version = meta["info"]["version"]
    requires = list(meta["info"].get("requires_dist") or [])
    urls = meta["releases"].get(version, [])

    sdist = next((u for u in urls if u["packagetype"] == "sdist"), None)
    wheel = next((u for u in urls if u["packagetype"] == "bdist_wheel"), None)
    chosen = sdist or wheel
    if chosen is None:
        raise RuntimeError(f"{name} {version} has no downloadable artifact")

    with urllib.request.urlopen(chosen["url"], timeout=120) as response:
        blob = response.read()

    digests: dict[str, str] = {}
    if chosen is sdist:
        with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tar:
            for member in tar.getmembers():
                if not member.isfile() or not member.name.endswith(".py"):
                    continue
                handle = tar.extractfile(member)
                if handle is None:
                    continue
                # strip the leading "<name>-<version>/" directory
                rel = member.name.split("/", 1)[1] if "/" in member.name else member.name
                digests[rel] = hashlib.sha256(handle.read()).hexdigest()
    else:
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            for info in zf.infolist():
                if info.is_dir() or not info.filename.endswith(".py"):
                    continue
                digests[info.filename] = hashlib.sha256(zf.read(info)).hexdigest()
    return version, digests, requires


def _local_files(root: str, package_dir: str) -> dict[str, str]:
    base = os.path.join(root, package_dir.replace("/", os.sep))
    digests: dict[str, str] = {}
    if not os.path.isdir(base):
        return digests
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in {"__pycache__"} and not d.endswith(".egg-info")]
        for filename in filenames:
            if not filename.endswith(".py"):
                continue
            full = os.path.join(dirpath, filename)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            with open(full, "rb") as handle:
                digests[rel] = hashlib.sha256(handle.read()).hexdigest()
    return digests


def _compare(name: str, root: str, package_dir: str) -> tuple[str, list[str]]:
    version, published, requires = _published_files(name)
    local = _local_files(root, package_dir)
    if not local:
        return "SKIP", [f"no package directory at {package_dir}"]

    # Only compare paths under the package directory -- the sdist also carries
    # setup.py, tests and so on, which are out of scope by design.
    prefix = package_dir.rstrip("/") + "/"
    pub = {k: v for k, v in published.items() if k.startswith(prefix)}
    if not pub:
        return "SKIP", [f"published artifact has nothing under {prefix}"]

    notes: list[str] = []
    for path in sorted(set(pub) | set(local)):
        in_pub, in_loc = pub.get(path), local.get(path)
        if in_pub is None:
            notes.append(f"only in checkout:  {path}")
        elif in_loc is None:
            notes.append(f"only in published: {path}")
        elif in_pub != in_loc:
            notes.append(f"differs:           {path}")
    verdict = "DRIFT" if notes else "ok"
    return verdict, notes or [f"{len(pub)} files identical to {version}"]


def main(argv: list[str]) -> int:
    wanted = argv[1:] or sorted(COMPANIONS)
    print("Does each companion's published code match its checkout?\n")
    print(f"{'companion':28s} {'verdict':8s} detail")
    print("-" * 78)

    drifted, skipped = [], []
    details: dict[str, list[str]] = {}
    for name in wanted:
        if name not in COMPANIONS:
            print(f"{name:28s} {'SKIP':8s} not a known companion")
            skipped.append(name)
            continue
        root, package_dir = COMPANIONS[name]
        if not os.path.isdir(root):
            print(f"{name:28s} {'SKIP':8s} no checkout at {root}")
            skipped.append(name)
            continue
        try:
            verdict, notes = _compare(name, root, package_dir)
        except (urllib.error.URLError, RuntimeError, KeyError, OSError) as exc:
            print(f"{name:28s} {'SKIP':8s} {type(exc).__name__}: {exc}")
            skipped.append(name)
            continue
        head = notes[0] if len(notes) == 1 else f"{len(notes)} file(s) differ"
        print(f"{name:28s} {verdict:8s} {head}")
        if verdict == "DRIFT":
            drifted.append(name)
            details[name] = notes
        elif verdict == "SKIP":
            skipped.append(name)

    for name in drifted:
        print(f"\n  {name}:")
        for note in details[name][:20]:
            print(f"    {note}")
        if len(details[name]) > 20:
            print(f"    ... and {len(details[name]) - 20} more")

    print()
    if drifted:
        print(f"{len(drifted)} companion(s) have unpublished source changes: {', '.join(drifted)}")
        print("Each needs a release, or an explicit note saying why the drift is intended.")
    if skipped:
        print(f"{len(skipped)} companion(s) could not be checked: {', '.join(skipped)}")
        print("A companion that could not be checked is not a companion that passed.")
    if not drifted and not skipped:
        print(f"All {len(wanted)} companions match what they published.")
    return 1 if drifted else (2 if skipped else 0)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
