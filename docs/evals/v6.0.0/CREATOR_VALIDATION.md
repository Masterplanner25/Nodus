# v6.0.0 — Gate 10 creator validation (pre-publish)

**Artifacts:** `nodus_lang-6.0.0-py3-none-any.whl` (195 files) and
`nodus_lang-6.0.0.tar.gz`, built from the tagged tree (`v6.0.0` → `ab423f6`, the
merge of PR #1034). The checkout had no tracked changes, and every one of the
sdist's 545 files is a tracked file, so nothing untracked was packaged.

**Date:** 2026-11-28

6.0.0 is the first major since 5.0.0 and adds no features. It lands the seven
staged flips and the D2/D3 removals, each in its own PR (#1026–#1033):

| flip | PR | what changes |
|---|---|---|
| #917 rebuild effects | #1026 | resuming a stored run refuses a top-level effect; `NODUS_REBUILD_EFFECTS=allow` |
| #798 `worker:` | #1027 | a `worker:` with no registered dispatcher fails the workflow before any step runs |
| #1021 library `run_loop()` | #1028 | a runtime error, naming `wait(task)` |
| #547 concurrent write | #1029 | a lost update fails the run with `workflow_error` |
| #609 type names | #1030 | an unknown type name is a syntax error |
| #545 record `==` | #1031 | records compare by kind and fields |
| #797 default store | #1032 | SQLite by default; a JSON store holding runs SQLite lacks is refused, not hidden |
| D2, D3 | #1033 | `.tl`, the `language` launchers, `tiny_vm_lang_functions`, `NodusRuntime._last_vm` removed |

## Wheel contents

Checked by listing the wheel, not by reading the build config:

- no `.tl` file, no `nodus/main/language.py`, no `tiny_vm_lang_functions`;
- `nodus/support/staged_flips.json` and `nodus/llms.txt` present;
- `version.py` reads `__version__ = "6.0.0"`.

## Gate 10a — dependent suites (before upload)

```
PYTHONPATH="src;." python -m tools.check_dependent_suites
```

Run against the release branch at `cae0b29`, whose tree is the tagged tree, with
nothing else going. **It exited 1, and no failure was a code break.**

| companion | verdict | detail |
|---|---|---|
| nodus-mcp | FAIL → pass | 1 failed, 375 passed; the one is a recorded flake |
| nodus-mcp-server | FAIL → pass | 6 failed, 72 passed; checkout state, see below |
| nodus-extension | PASS | 126 passed in 21.52s |
| nodus-sdk | PASS | 132 passed, 2 skipped, 1 warning in 15.37s |
| nodus-native-memory-engine | PASS | 76 passed in 1.51s |
| nodus-jupyter | PASS | 32 passed in 1.46s |
| nodus-workflow-ai | PASS | 28 passed in 0.52s |
| nodus-a2a-wire | PASS | 188 passed in 14.80s |

- **nodus-mcp:** `test_streamable_http_end_to_end.py::test_host_routes_and_middleware_share_the_app`
  matched its recorded flake. Re-run serially three times: 3/3 passed.
- **nodus-mcp-server: the #797 refusal, working as designed.** All six failures
  were `ok: False` with `StrandedRunsError`: the checkout's
  `.nodus/workflow_framework/runs/` holds **215 JSON run records**, and with no
  backend configured the 6.0.0 default store refuses to open while they are not
  in SQLite. Re-run with `NODUS_RUN_STATE_ROOT` pointed at an empty directory:
  **78 passed**. The 215 records were left untouched: the checkout also holds a
  `claude_desktop_config.json` and server logs, so they may be real runs, and
  migrating them is the owner's decision (`nodus workflow migrate-store --to
  sqlite` there, or `NODUS_WORKFLOW_STORE_BACKEND=local`).
- **D3 is answered:** no companion read `NodusRuntime._last_vm` or imported
  `nodus.tooling.tiny_vm_lang_functions`, and none assumed the JSON store was
  the default.

**A gap in the gate, recorded rather than fixed mid-release:** it runs each suite
in the companion's own checkout, so run state left there by earlier runs can
fail a suite on a release that breaks no code. Isolating run state per suite
(`NODUS_RUN_STATE_ROOT`) would separate the two. A follow-up, not this release.

## Gate 10b — adversarial probes against the wheel

The wheel was installed into `.venv-validation`, upgraded in place with
`--force-reinstall --no-deps`. `%TEMP%` held **no** JSON run records: the 951
left by earlier cycles' probe runs were moved aside during the #797 work, since
the default store would otherwise refuse them (EXP-014). The probes ran from
`%TEMP%`, outside the repo, with `--require-installed`.

**186/186 probes passed, twice. Exit code 0.** Six are new this cycle, written
before the tag:

- every flip has landed, and the packaged register stages none (0 staged, 7
  landed, each `landed_in: 6.0.0`);
- a rebuild refuses a top-level effect by default, `NODUS_REBUILD_EFFECTS=allow`
  lets it through, and an ordinary run is not treated as a rebuild (#917);
- the D2/D3 surfaces are gone from the installed package, a `.tl` import names
  the rename, and `active_vm()` returns the last run's VM;
- the migration guide has a section for every landed flip, read off the
  register;
- the README names the 6.0.0 surface;
- no document still calls 5.21.0 the current release.

The flip PRs had already rewritten the probes that pinned 5.x behaviour (union of
records, record `==`, the default store, `durable_spawn`, `--staged`).

### A finding: a server sweeper dies if its SQLite file disappears

The first of the two runs printed a traceback from a `RuntimeService` sweeper
thread, `sqlite3.OperationalError: no such table: workflow_runs`; the second did
not. The cause is two things together:

- **The probe leaked services.** `probe_serve_denies_submitted_code` (#754) builds three
  `RuntimeService`s in a temporary directory and never closes them, so their
  sweepers outlive the directory. Harness code; fixed in the eval-records PR.
- **The SQLite store does not survive its file being deleted.** Each operation
  reconnects, and `sqlite3.connect` creates a new, empty file, so the next sweep
  hits a database with no schema. The sweeper thread then dies, and wait
  deadlines stop being enforced, silently. The 5.x JSON store recreated its
  directory and listed nothing. Reachable only by deleting the store under a
  running server. Not a release blocker; filed as #1035.

## Verdict

**Ready to publish.** No code break in any dependent suite, every probe green
against the installed wheel, and the one new finding is an edge case outside the
release's claims.
