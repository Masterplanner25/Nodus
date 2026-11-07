# v5.15.1 — Stage 5 post-publish eval

**Artifact:** `nodus-lang==5.15.1` installed from **PyPI** into a fresh venv
**Date:** 2026-11-07
**Index page:** https://pypi.org/project/nodus-lang/5.15.1/

## Install

```
python -m venv venv-stage5
venv-stage5/Scripts/python -m pip install "nodus-lang==5.15.1"
```

Resolved on the **first attempt** — no index lag this cycle. Exit 0.

## Checks (run from a directory outside the repo)

| # | Check | Result |
|---|---|---|
| 1 | `nodus` resolves to the installed package | `…/venv-stage5/Lib/site-packages/nodus` |
| 2 | the CLI reports 5.15.1 | `Nodus 5.15.1` |
| 3 | a program runs | `fn main() { print(6i * 7i) }` → `42` |
| 4 | the #893 TOML-loader surface imports | `import nodus.tooling.project, nodus.tooling.user_config` → OK |

The install was on Python 3.11, so `tomli` was correctly **not** pulled in (the
conditional dependency applies only to `python_version < "3.11"`). The 3.10 path
itself is exercised by the `py310-floor` CI job, which installs the wheel on a
3.10 interpreter and runs it; it passed on PR #895.

## Verdict

**Pass.** The published artifact installs cleanly, reports the right version, runs
a program, and imports the loaders that #893 repaired. The security fix (#891) and
the 3.10 floor (#893) are the release's substance and are both covered by the Gate
10 probes and dependent suites run against the identical wheel before upload
(`CREATOR_VALIDATION.md`).
