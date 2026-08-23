"""`nodus doctor` -- report what this environment actually resolves to.

The failure this exists for: a `.venv` holding an installed `nodus-lang` that
shadows a newer `src/` checkout.  The symptom is behaviour that contradicts the
code you are reading, and it costs an afternoon every time because nothing in
the normal output says which tree ran.  `CLAUDE.md` spends three paragraphs on
it and the release process already requires probes to print their resolved
package path and version -- this is that rule as a command anyone can run.

**Doctor never writes.**  It does not create `.nodus/`, touch the bytecode
cache, or migrate anything.  A diagnostic that mutates the thing it is
diagnosing is worse than no diagnostic, and this is exactly the command someone
reaches for when an install is already broken.  `test_doctor_does_not_write`
pins it.
"""

from __future__ import annotations

import os
import platform
import sys
from dataclasses import dataclass, field
from importlib import metadata
from importlib.util import find_spec
from pathlib import Path
from typing import Any

DIST_NAME = "nodus-lang"

OK = "ok"
WARN = "warn"
ERROR = "error"

_MARK = {OK: "  ok  ", WARN: " warn ", ERROR: " FAIL "}


@dataclass
class Check:
    name: str
    status: str
    detail: str
    #: Shown indented under the detail line; the "what do I do about it" half.
    hint: str | None = None
    data: dict[str, Any] = field(default_factory=dict)


def _package_dir() -> Path:
    """The directory the running `nodus` package code lives in.

    Derived from a *submodule*, not from `nodus.__file__`.  The repo-root
    `nodus.py` compatibility shim wins the import when the CWD is the checkout
    root, so `nodus.__file__` can name the shim while every line of code that
    actually runs comes from `src/nodus/`.  Asking a submodule where it lives
    cannot be fooled that way -- which is the whole point of this command.
    """
    from nodus.support import version as version_module

    return Path(version_module.__file__).resolve().parents[1]


def _resolved_package() -> Check:
    """Which tree is `import nodus` actually loading?"""
    import nodus
    from nodus.support.version import __version__

    package_dir = _package_dir()
    in_site_packages = any(
        part in {"site-packages", "dist-packages"} for part in package_dir.parts
    )
    origin = "installed package" if in_site_packages else "source checkout"
    detail = f"{__version__} from {origin} at {package_dir}"

    entry = Path(nodus.__file__).resolve() if getattr(nodus, "__file__", None) else None
    shimmed = entry is not None and entry.parent != package_dir
    if shimmed:
        detail += f" (imported via the shim at {entry})"

    return Check(
        "nodus package",
        OK,
        detail,
        data={
            "version": __version__,
            "path": str(package_dir),
            "origin": "site-packages" if in_site_packages else "source",
            "import_entry": str(entry) if entry else None,
        },
    )


def _version_gap() -> Check:
    """The installed distribution vs the module that actually imported.

    A mismatch means something is shadowing something else, and every later
    surprise in the session traces back here.
    """
    from nodus.support.version import __version__

    try:
        installed = metadata.version(DIST_NAME)
    except metadata.PackageNotFoundError:
        return Check(
            "version sync",
            WARN,
            f"{DIST_NAME} is not installed here; running {__version__} from source only",
            hint="Fine for development. `pip install -e .` if you want the console script to match.",
            data={"module": __version__, "installed": None},
        )
    if installed == __version__:
        return Check(
            "version sync",
            OK,
            f"installed {DIST_NAME}=={installed} matches the imported module",
            data={"module": __version__, "installed": installed},
        )
    return Check(
        "version sync",
        ERROR,
        f"imported module is {__version__} but installed {DIST_NAME} is {installed}",
        hint=(
            "The two disagree, so which one runs depends on sys.path -- the symptom is "
            'behaviour that contradicts the code you are reading. Prefix with '
            'PYTHONPATH=".../src" to force the checkout, or reinstall to match.'
        ),
        data={"module": __version__, "installed": installed},
    )


def _interpreter() -> Check:
    return Check(
        "interpreter",
        OK,
        f"{platform.python_implementation()} {platform.python_version()} at {sys.executable}",
        data={
            "implementation": platform.python_implementation(),
            "version": platform.python_version(),
            "executable": sys.executable,
        },
    )


def _optional_extras() -> Check:
    """Extras that change runtime behaviour by their presence alone.

    `@retry` falls back to the built-in `InMemoryEffectStore` without
    `nodus-lang[retry]`, which is why a suite can pass locally and fail on a
    clean runner.
    """
    present = find_spec("nodus_retry") is not None
    if present:
        return Check(
            "optional extras",
            OK,
            "nodus-retry is installed (@retry uses the durable effect store)",
            data={"nodus_retry": True},
        )
    return Check(
        "optional extras",
        WARN,
        "nodus-retry is not installed (@retry falls back to the in-memory effect store)",
        hint="`pip install nodus-lang[retry]` if you are testing @retry behaviour.",
        data={"nodus_retry": False},
    )


def _project(cwd: Path) -> Check:
    manifest = cwd / "nodus.toml"
    if not manifest.is_file():
        return Check(
            "project",
            OK,
            f"no nodus.toml in {cwd} (running in script mode)",
            data={"manifest": None},
        )
    try:
        from nodus.tooling.project import load_project, project_entry_path

        project = load_project(str(cwd))
        entry = project_entry_path(project) if project else None
    except Exception as exc:  # pragma: no cover - depends on a malformed manifest
        return Check(
            "project",
            ERROR,
            f"nodus.toml at {manifest} could not be read: {exc}",
            data={"manifest": str(manifest)},
        )
    if entry and not os.path.isfile(entry):
        return Check(
            "project",
            ERROR,
            f"entry point {entry} is declared but does not exist",
            data={"manifest": str(manifest), "entry": entry},
        )
    return Check(
        "project",
        OK,
        f"nodus.toml at {manifest}" + (f", entry {entry}" if entry else ""),
        data={"manifest": str(manifest), "entry": entry},
    )


def _store(cwd: Path) -> Check:
    """Report the workflow store without creating it.

    `LocalWorkflowStore.list_runs()` reads every record on every sweep, so the
    accumulated count is a real performance signal (#380) -- and this is the
    only place a user would ever see it.
    """
    runs_dir = cwd / ".nodus" / "workflow_framework" / "runs"
    if not runs_dir.is_dir():
        return Check(
            "workflow store",
            OK,
            f"no store under {cwd / '.nodus'} (nothing has run here yet)",
            data={"runs": 0},
        )
    try:
        count = sum(1 for entry in runs_dir.iterdir() if entry.suffix == ".json")
    except OSError as exc:  # pragma: no cover - permissions
        return Check("workflow store", WARN, f"{runs_dir} is unreadable: {exc}")
    status = WARN if count > 500 else OK
    check = Check(
        "workflow store",
        status,
        f"{count} recorded run(s) under {runs_dir}",
        data={"runs": count, "path": str(runs_dir)},
    )
    if status is WARN:
        check.hint = (
            "list_runs() scans every record, so sweeps get linearly slower (#380). "
            "`nodus workflow cleanup` prunes old snapshots."
        )
    return check


def run_checks(cwd: str | os.PathLike[str] | None = None) -> list[Check]:
    """Every check, in report order.  Performs no writes."""
    root = Path(cwd) if cwd is not None else Path.cwd()
    return [
        _resolved_package(),
        _version_gap(),
        _interpreter(),
        _optional_extras(),
        _project(root),
        _store(root),
    ]


def format_report(checks: list[Check]) -> str:
    lines = []
    for check in checks:
        lines.append(f"[{_MARK[check.status]}] {check.name}: {check.detail}")
        if check.hint:
            lines.append(f"           {check.hint}")
    failures = sum(1 for c in checks if c.status == ERROR)
    warnings = sum(1 for c in checks if c.status == WARN)
    lines.append("")
    if failures:
        lines.append(f"{failures} problem(s), {warnings} warning(s).")
    elif warnings:
        lines.append(f"No problems. {warnings} warning(s).")
    else:
        lines.append("No problems found.")
    return "\n".join(lines)


def to_json(checks: list[Check]) -> dict[str, Any]:
    return {
        "ok": all(c.status != ERROR for c in checks),
        "checks": [
            {
                "name": c.name,
                "status": c.status,
                "detail": c.detail,
                "hint": c.hint,
                **({"data": c.data} if c.data else {}),
            }
            for c in checks
        ],
    }
