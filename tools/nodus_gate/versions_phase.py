"""Versions phase: does the prose still agree with the version files?

`src/nodus/support/version.py` and `pyproject.toml` are the authority. Every
sentence that quotes them is a copy, and copies rot. This has happened in three
consecutive release cycles -- CLAUDE.md's SemVer paragraph read 5.0.1 through the
whole of 5.0.2, and `ECOSYSTEM_READINESS_ASSESSMENT.md` sat at v4.1.1 for four
releases and was *still* wrong at the 5.1.0 cut. CLAUDE.md names the failure in
writing ("No gate checks version strings") and it kept happening, because the
response was a list of places to check by hand and hand-checking is what failed.

Three checks, in increasing order of how much judgement they need:

1. **Sync.** `version.py` and `pyproject.toml` must agree. A hard failure: it is
   a build-correctness fact, not a documentation one.
2. **Registered claims.** Each entry in `tools/version_claims.json` locates one
   sentence that asserts a current value and says what it must equal. A claim
   that disagrees is a failure; so is a pattern that matches nothing, because a
   claim site that moved is exactly what this exists to catch.
3. **Discovery.** A sweep for claim-shaped lines that are *not* registered, so a
   new one cannot hide. Advisory -- it is a prompt to a human, and the cost of a
   false positive is a wasted glance, not a blocked merge.

**The authority is read as text, never imported.** Importing `nodus` to ask its
version would resolve through `sys.path`, and an installed `nodus-lang` shadowing
the checkout would have this gate compare the docs against the *wrong* version --
silently, and in the exact direction that hides a real mismatch. That shadowing is
a live hazard in this repo; it is what `nodus doctor` exists for. A gate that can
be fooled by the thing it is checking is not a gate.

**Why a manifest rather than a grep.** "X is current" goes stale; "as of X" does
not. README.md's release-history section names 5.0.4, 5.0.3, 5.0.1 and 5.0.0 and
is correct as written forever. Only a claim about the present is a defect, and no
regex over version tokens can tell the two apart -- so the claims are declared,
and the grep is demoted to a discovery aid that suggests rather than decides.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

_VERSION_PY = Path("src") / "nodus" / "support" / "version.py"
_PYPROJECT = "pyproject.toml"
_EVALS_DIR = Path("docs") / "evals"

_VERSION_TOKEN = re.compile(r"\bv?\d+\.\d+\.\d+\b")


@dataclass
class SyncStatus:
    version_py: str | None = None
    pyproject: str | None = None
    error: str | None = None

    @property
    def in_sync(self) -> bool:
        return (
            self.error is None
            and self.version_py is not None
            and self.version_py == self.pyproject
        )


@dataclass
class ClaimStatus:
    file: str
    expects: str
    expected: str
    why: str
    fix: str
    line: int = 0
    claimed: str | None = None
    text: str = ""

    @property
    def found(self) -> bool:
        return self.claimed is not None

    @property
    def ok(self) -> bool:
        return self.found and self.claimed == self.expected


@dataclass
class Unregistered:
    file: str
    line: int
    text: str
    marker: str


@dataclass
class VersionsResult:
    sync: SyncStatus = field(default_factory=SyncStatus)
    claims: list[ClaimStatus] = field(default_factory=list)
    unregistered: list[Unregistered] = field(default_factory=list)
    error: str | None = None

    @property
    def checks_run(self) -> int:
        return len(self.claims) + 1  # + the sync check

    @property
    def failures(self) -> list[ClaimStatus]:
        return [c for c in self.claims if not c.ok]

    @property
    def passed(self) -> int:
        return len(self.claims) - len(self.failures) + (1 if self.sync.in_sync else 0)

    @property
    def has_failure(self) -> bool:
        return bool(self.error) or not self.sync.in_sync or bool(self.failures)


def _read_version_py(root: Path) -> tuple[str | None, str | None]:
    """`__version__` out of version.py, by text.

    Deliberately not `from nodus.support.version import __version__` -- see the
    module docstring.
    """
    path = root / _VERSION_PY
    if not path.is_file():
        return None, f"authority file not found: {path}"
    match = re.search(
        r'^__version__\s*=\s*["\'](\d+\.\d+\.\d+[^"\']*)["\']',
        path.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    if match is None:
        return None, f"no __version__ assignment found in {path}"
    return match.group(1), None


def _read_pyproject_version(root: Path) -> tuple[str | None, str | None]:
    path = root / _PYPROJECT
    if not path.is_file():
        return None, f"{_PYPROJECT} not found at {path}"
    # Anchored to the [project] table's own `version = "..."`, which is the first
    # such assignment; a dependency pin later in the file must not match.
    match = re.search(
        r'^version\s*=\s*["\'](\d+\.\d+\.\d+[^"\']*)["\']',
        path.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    if match is None:
        return None, f"no top-level version assignment found in {path}"
    return match.group(1), None


def _latest_eval_version(root: Path) -> tuple[str | None, str | None]:
    """The newest `docs/evals/vX.Y.Z` directory, ordered numerically.

    String ordering would put v5.1.0 above v5.0.10, so the sort is on the parsed
    tuple.
    """
    evals = root / _EVALS_DIR
    if not evals.is_dir():
        return None, f"{_EVALS_DIR} not found"
    versions: list[tuple[tuple[int, int, int], str]] = []
    for entry in evals.iterdir():
        if not entry.is_dir():
            continue
        match = re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)", entry.name)
        if match:
            key = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
            versions.append((key, ".".join(match.groups())))
    if not versions:
        return None, f"no vX.Y.Z directories under {_EVALS_DIR}"
    versions.sort()
    return versions[-1][1], None


def _resolve_expectations(root: Path) -> tuple[dict[str, str], str | None]:
    version, err = _read_version_py(root)
    if err:
        return {}, err
    latest_eval, eval_err = _latest_eval_version(root)
    expectations = {"nodus_version": version or ""}
    if latest_eval is not None:
        expectations["latest_eval_version"] = latest_eval
    elif eval_err:
        # Not fatal on its own; only claims that ask for it will fail, and they
        # will say why.
        pass
    return expectations, None


def _check_claim(root: Path, entry: dict, expectations: dict[str, str]) -> ClaimStatus:
    expects = entry.get("expects", "nodus_version")
    status = ClaimStatus(
        file=entry.get("file", "?"),
        expects=expects,
        expected=expectations.get(expects, ""),
        why=entry.get("why", ""),
        fix=entry.get("fix", ""),
    )
    path = root / status.file
    if not path.is_file():
        status.text = f"file not found: {status.file}"
        return status
    try:
        pattern = re.compile(entry["pattern"])
    except (KeyError, re.error) as exc:
        status.text = f"bad pattern: {exc}"
        return status

    # `after` scopes the search to the part of the file below a marker line. It
    # exists because ECOSYSTEM_READINESS_ASSESSMENT.md repeats the sentence
    # "**Current version:** X" once per package, so the pattern alone cannot say
    # which one is nodus-lang's.
    after = entry.get("after")
    armed = after is None

    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not armed:
            if after in line:
                armed = True
            continue
        match = pattern.search(line)
        if match:
            status.line = number
            status.claimed = match.group(1)
            status.text = line.strip()
            break
    if not status.found and after is not None and not armed:
        status.text = f"anchor not found in {status.file}: {after!r}"
    return status


def _iter_scan_files(root: Path, patterns: list[str]):
    seen: set[Path] = set()
    for pattern in patterns:
        for path in sorted(root.glob(pattern)):
            if path.is_file() and path not in seen:
                seen.add(path)
                yield path


def _is_ignored(rel: str, line: str, ignore: list[dict]) -> bool:
    """Suppressions are per-line and must carry a reason.

    Kept deliberately narrow -- `file` plus a substring of the line, never a
    whole-file exemption -- so a *new* claim in an already-noisy file is still
    reported. Widening the marker list instead would have hidden the real
    unregistered claim this sweep found on its first run.
    """
    for entry in ignore:
        if entry.get("file") != rel:
            continue
        needle = entry.get("contains")
        if needle and needle in line:
            return True
    return False


def _discover_unregistered(
    root: Path, scan: dict, registered: set[tuple[str, int]], ignore: list[dict]
) -> list[Unregistered]:
    """Claim-shaped lines nobody declared.

    A line qualifies when it carries both a version token and a phrase that
    asserts currency. That pairing is what separates "5.1.0 is current" from
    "fixed in 5.0.3" without needing to understand either.
    """
    markers = [m.lower() for m in scan.get("currency_markers", [])]
    if not markers:
        return []
    found: list[Unregistered] = []
    for path in _iter_scan_files(root, scan.get("files", [])):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        rel = path.relative_to(root).as_posix()
        for number, line in enumerate(lines, start=1):
            if (rel, number) in registered:
                continue
            if not _VERSION_TOKEN.search(line):
                continue
            lowered = line.lower()
            marker = next((m for m in markers if m in lowered), None)
            if marker is None:
                continue
            if _is_ignored(rel, line, ignore):
                continue
            found.append(
                Unregistered(file=rel, line=number, text=line.strip(), marker=marker)
            )
    return found


def run_versions_phase(root: str) -> VersionsResult:
    root_path = Path(root)
    result = VersionsResult()

    version_py, py_err = _read_version_py(root_path)
    pyproject, proj_err = _read_pyproject_version(root_path)
    result.sync = SyncStatus(
        version_py=version_py, pyproject=pyproject, error=py_err or proj_err
    )
    if result.sync.error:
        result.error = result.sync.error
        return result

    manifest_path = root_path / "tools" / "version_claims.json"
    if not manifest_path.is_file():
        result.error = f"manifest not found: {manifest_path}"
        return result
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        result.error = f"manifest is not valid JSON: {exc}"
        return result

    expectations, exp_err = _resolve_expectations(root_path)
    if exp_err:
        result.error = exp_err
        return result

    registered: set[tuple[str, int]] = set()
    for entry in manifest.get("claims", []):
        status = _check_claim(root_path, entry, expectations)
        result.claims.append(status)
        if status.found:
            registered.add((Path(status.file).as_posix(), status.line))

    result.unregistered = _discover_unregistered(
        root_path, manifest.get("scan", {}), registered, manifest.get("ignore", [])
    )
    return result
