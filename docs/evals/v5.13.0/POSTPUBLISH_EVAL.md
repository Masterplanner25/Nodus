# v5.13.0 — Stage 5 post-publish eval

**Date:** 2026-09-08
**Artifact:** `nodus-lang==5.13.0` installed from PyPI into a fresh venv
**Verdict:** **PASS.** 5/5 checks. The release works as a new user would expect.

Stage 5 asks a different question from Gate 10: not *"what can I make fail?"* but
*"does this work the way someone who just installed it would expect?"* — against
the **published** artifact rather than a local wheel.

The reason it is a separate stage is #662: it was found here, by a program that
used two new features at once when neither was broken alone.

---

## The index lagged, and only an install settles it

The upload succeeded and returned the project URL. `pip install
nodus-lang==5.13.0` then failed for **nine minutes**, with 5.12.0 as the newest
version pip could see:

```
ERROR: Could not find a version that satisfies the requirement nodus-lang==5.13.0
       (from versions: …, 5.11.0, 5.12.0)
```

It installed on the 19th attempt of a 30-second poll. This is the documented
behaviour — PyPI's JSON API and simple index both lag after an upload, and
`Cache-Control: no-cache` does not prevent it — and it is why **only
`pip install <name>==<version>` is authoritative**. A reader checking the API in
that window would have concluded the upload failed and re-uploaded, which against
an immutable index is the expensive mistake.

Installed and resolved correctly, from a neutral CWD:

```
version: 5.13.0
from   : …/fresh/Lib/site-packages/nodus/__init__.py
```

---

## Checks

| # | Check | Result |
|---|---|---|
| 1 | `nodus --version` | `Nodus 5.13.0` |
| 2 | hello world runs | `hello from 5.13.0` |
| 3 | `copy()` + state ownership + `ensure_dir` **in one program** | `items=2 \| ensure_dir refused a file \| copy kept the original=1` |
| 4 | `nodus run` keeps its project-root jail | refused with *"escapes the project root"* |
| 5 | `llms.txt` and examples ship inside the wheel | `llms.txt True \| examples 11` |

### Check 3 is the one that matters

It is the whole release in one program, and each line proves a different fix:

```nd
workflow build {
    state manifest = ["seed"]

    step collect {
        let borrowed = manifest
        borrowed = push(borrowed, "smuggled")   // must NOT reach the cell
        return "collected"
    }

    step stamp after collect {
        manifest = push(copy(manifest), "recorded")
        return "stamped"
    }
}
```

`items=2` is the evidence for #822. `push` mutates in place and returns the same
list, so before the fix `borrowed` *was* the cell's list and the smuggled entry
would have landed in it — giving 3. Getting 2 means the cell handed back a copy,
the untracked mutation went nowhere, and only the explicit write in `stamp`
counted.

`ensure_dir refused a file` is #845 against the published artifact, and
`copy kept the original=1` is #814.

### Check 4 pins the asymmetry

`nodus serve` gained a filesystem jail this release and `nodus run` did not
change: it is still confined by *project root* through `fs_root`, a different
mechanism. The refusal message distinguishes them — *"escapes the project root"*
rather than *"blocked for path"* — so this check would notice if the CLI had been
quietly moved onto the service's jail.

---

## A defect found in the eval, not in the release

The combined program failed on its first run:

```
Syntax error at s.nd:12:10: Expected identifier, got 'record'
```

`record` is a reserved keyword, so `step record after collect` does not parse.
That is my test program's bug, not the release's — renaming the step to `stamp`
made it pass — and it is recorded because the failure reads at first glance like
a workflow-parsing regression in a freshly published version. The error message
is precise enough to have settled it immediately, which is the thing working.

---

## Follow-ups

None blocking. The two Stage 6 obligations `nodus_gate --consumers` already flags
(`nodus-run-action` and the wiki, both because `nodus_version` moved) are handled
in `STAGE6_DOWNSTREAM_SWEEP.md`.
