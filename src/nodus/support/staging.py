"""Warnings about behaviour that is staged to change at the next major.

A staged flip is a promise made to a user *now* about a release that has not
happened. `nodus/support/staged_flips.json` is the register and `nodus_gate --flips` keeps it
honest; this module is how one of those promises reaches the person who has to
act on it.

**Why a category of its own.** The default workflow store's notice (#174/#797)
was a plain `DeprecationWarning`, raised from `nodus/vm/vm.py` — and Python's
default filters ignore `DeprecationWarning` outside `__main__`. Measured at
5.11.0 with three runs in the store: `nodus run` printed nothing, and the
identical command under `python -W always` printed the full notice. So the one
flip in the cohort that costs *state* rather than a build had a notice **no CLI
user had ever seen**, for the whole of its deprecation window.

`COMPATIBILITY_MODEL.md` §5.1 makes "the CLI emits a warning" one of three
required deprecation signals, so on this project's own rule that was not yet a
deprecation, and §5.2's clock had arguably not started.

The fix is not to stop using `warnings`. An embedder should keep being able to
filter these, count them, or turn them into errors — that is what the warnings
machinery is for, and `StagedFlipWarning` subclasses `DeprecationWarning` so
every filter already written for the general case still catches it. What was
missing is a way for the **CLI** to say "show me exactly the warnings a user
must act on before the next major" without unsuppressing every deprecation in
every library it imports. A category is that handle.

It is deliberately narrower than "a Nodus deprecation". `_last_vm` and
`nodus.tooling.loader.run_source()` are deprecated too, and they are not staged
flips: they are surfaces going away, not behaviour changing under a program that
keeps working. Those stay plain `DeprecationWarning`s.
"""

from __future__ import annotations

import json
import os
import warnings


class StagedFlipWarning(DeprecationWarning):
    """Behaviour that changes at the next major and is registered in the manifest.

    A `DeprecationWarning` subclass on purpose: an embedder filtering
    `DeprecationWarning` keeps catching these, and one that wants only the
    breaking-at-the-major subset can name this instead.
    """


def warn_staged_flip(message: str, *, stacklevel: int = 2) -> None:
    """Announce a registered staged flip.

    `stacklevel` is relative to the caller, as with `warnings.warn` — the extra
    frame this function adds is accounted for here so callers do not have to.
    """
    warnings.warn(message, StagedFlipWarning, stacklevel=stacklevel + 1)


#: Where to accumulate what a run actually hits. Unset means record nothing,
#: which is the default and costs nothing.
REPORT_ENV = "NODUS_STAGED_FLIP_REPORT"


def report_path() -> str | None:
    """The report file, or None when nobody asked for one."""
    value = os.environ.get(REPORT_ENV)
    return value or None


def record_staged_flip(flip: str, message: str, *, where: str | None = None) -> None:
    """Note that a run hit a staged flip, if a report was asked for.

    **Records; it does not emit.** Each site keeps announcing itself exactly as
    it did -- some through `warn_staged_flip`, some by printing to stderr, and
    an embedder reads two of them out of `result["stderr"]`. Routing emission
    through here as well would change all of that at once for the sake of
    tidiness, and the warning text is asserted on in several places.

    So this is the one thing the sites share: the *fact* that a flip was hit.
    `flip` is a key in `nodus/support/staged_flips.json`, which is what lets a
    report join back to the register.

    Why a file rather than an in-process list: the exposure worth collecting is
    the one a whole test suite finds, and a suite is many runs -- often many
    processes. JSON Lines, appended, so concurrent writers interleave whole
    records rather than corrupting each other's.

    Never raises. A report that cannot be written is not a reason to fail the
    program being reported on.
    """
    path = report_path()
    if not path:
        return
    record = {"flip": flip, "message": message}
    if where:
        record["where"] = where
    try:
        directory = os.path.dirname(os.path.abspath(path))
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        return


def read_staged_flip_report(path: str | None = None) -> list[dict]:
    """Records written by earlier runs, newest last, malformed lines skipped.

    A half-written line is possible if a process died mid-append, and that is
    not a reason to refuse the rest of the report.
    """
    target = path or report_path()
    if not target:
        return []
    try:
        with open(target, "r", encoding="utf-8") as handle:
            lines = handle.readlines()
    except OSError:
        return []
    out = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if isinstance(record, dict) and isinstance(record.get("flip"), str):
            out.append(record)
    return out
