# v5.15.1 — Gate 10 creator validation (pre-publish)

**Artifact:** `dist/nodus_lang-5.15.1-py3-none-any.whl`, built from the tagged
tree (`v5.15.1` → `d6f0abf`)

**Date:** 2026-11-07

5.15.1 is a patch carrying two fixes already merged to `main`:

- **#891** — run-state file paths are built from a validated id (path traversal).
  `graph_id` was reachable from guest `.nd` code via `resume_workflow(id)`; a
  traversing id read or deleted a `.json`/`.pkl` outside the state directory.
  A single `safe_state_id` in `state_paths.py` now gates every run-state path
  builder, and read/delete treat an invalid id as "not found". (Security)
- **#893** — nodus-lang works on its declared Python 3.10 floor. `project.py`
  did a bare `import tomllib` (stdlib only from 3.11) while its sibling had the
  `tomli` fallback, and `tomli` was not a dependency. Both loaders now share the
  guard, `tomli` is a dependency for `python_version < "3.11"`, and a
  `py310-floor` CI job installs the wheel on 3.10 and runs it.

plus the doc/tooling entries already in `[Unreleased]` (companion count → 36,
PyJWT for nodus-auth, `tests/closed_issues/` now collected by plain pytest).

## Gate 10a — dependent suites (before upload)

```
PYTHONPATH="src;." python -m tools.check_dependent_suites
```

Run on the release box with nothing else running (free memory ~1.0 GB; the run
completed with no timeouts). **Exit code 0.**

| companion | verdict | detail |
|---|---|---|
| nodus-mcp | PASS | 365 passed, 2 warnings in 36.79s |
| nodus-mcp-server | PASS | 45 passed, 2 warnings in 1.83s |
| nodus-extension | PASS | 126 passed in 17.77s |
| nodus-sdk | PASS | 132 passed, 2 skipped, 1 warning in 18.38s |
| nodus-native-memory-engine | PASS | 76 passed in 1.07s |
| nodus-jupyter | PASS | 32 passed in 1.25s |
| nodus-workflow-ai | PASS | 28 passed in 0.34s |
| nodus-a2a-wire | PASS | 188 passed in 13.45s |

All 8 dependent suites pass against 5.15.1 dev source — including `nodus-sdk`
(the construction that a missed Gate 10a broke at 5.0.3) and `nodus-mcp-server`
(floored at `>=5.15.0`).

## Gate 10b — adversarial probes against the wheel

Clean venv, wheel installed with the `[http]` extra, run from a directory
**outside the repo** with `--require-installed`:

```
python tests/eval/release_claims_probe.py --repo <repo> --require-installed
```

Probe header confirmed resolution to the installed package, not the source tree:

```
package  …/venv-val/Lib/site-packages/nodus
version  5.15.1
```

**137/137 probes passed. Exit code 0.** This cycle added two prose probes:

- `README names the 5.15.1 surface` — the path-traversal / 3.10-floor surface
  appears in the README.
- `no stale '5.15.0 is current' claim survives` — retargeted from 5.14.0; no
  document still calls 5.15.0 the current release.

The single `Sandbox error … Execution timed out` line on stderr is the #862
probe's expected result (a budget breach under a service returns rather than
hanging) and is reported as PASS.

## Other pre-tag checks

- `nodus_gate --versions` → 13/13 claims agree with 5.15.1
- `nodus_gate --closed-issues --section 5.15.1` → 2/2 (#891, #893)
- `ruff check src/ tests/` clean · `mypy src/nodus/` clean
- `twine check dist/*.whl` PASSED; wheel METADATA carries
  `tomli>=2.0.1; python_version < "3.11"`
- CI on PR #895 (merged `d6f0abf`): `security`, `probes`, `py310-floor`, `test`
  all green.
