"""Warnings about behaviour that is staged to change at the next major.

A staged flip is a promise made to a user *now* about a release that has not
happened. `tools/v6_flips.json` is the register and `nodus_gate --flips` keeps it
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
