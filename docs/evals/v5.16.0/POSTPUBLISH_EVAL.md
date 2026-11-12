# v5.16.0 — Stage 5 post-publish eval

**Artifact:** `nodus-lang==5.16.0` installed from **PyPI**
**Date:** 2026-11-11
**Index page:** https://pypi.org/project/nodus-lang/5.16.0/

## Install

```
.venv-postpublish/Scripts/python -m pip install --no-cache-dir --upgrade "nodus-lang[http]==5.16.0"
```

The venv was upgraded in place, not recreated (Application Control blocks unseen
native DLLs on this machine). The install resolved on the **first attempt**, with
no index lag this cycle.

## Checks (run from the session scratchpad, outside the repo, no `PYTHONPATH`)

| # | Check | Result |
|---|---|---|
| 1 | `nodus` resolves to the installed package | `…\.venv-postpublish\Lib\site-packages\nodus` |
| 2 | the CLI reports 5.16.0 | `Nodus 5.16.0` |
| 3 | a program runs | `fn main() { print(6i * 7i) }` → `42` |
| 4 | the README's durable example, with `NODUS_WORKFLOW_STORE_BACKEND=sqlite` | `fetching job-42` / `uploading 3`, exit 0 |
| 5 | the same key again | no output, exit 0: a finished key does nothing |
| 6 | the same program on the default store | refused: `durable_spawn needs a workflow store whose claims are exclusive across processes…`, naming the fix |
| 7 | the release probes against the PyPI install (`--require-installed`) | **143/143**, including the real-crash resume probe |

Check 4 is the README text as written, with `fetch` and `upload` defined so it
runs. It is what a reader of the PyPI page would try first.

## Verdict

**Pass.** The published artifact installs, reports the right version, runs a
program, and does what the README says durable coroutines do: the first run does
the work, the second does nothing, and a store that cannot make the guarantee is
refused with the fix named. Crash-and-resume is exercised by probe 7 against the
same install, with a real process death.
