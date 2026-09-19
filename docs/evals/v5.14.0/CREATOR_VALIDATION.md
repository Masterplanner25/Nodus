# v5.14.0 — Gate 10 creator validation (pre-publish)

**Date:** 2026-09-18
**Artifact:** `dist/nodus_lang-5.14.0-py3-none-any.whl`, built from the tagged
tree (`v5.14.0` → `4bf86bb`)
**Verdict:** **PASS.** Both halves green. Cleared to publish.

Gate 10 asks *"what can I make fail?"* against a local wheel, before anything
immutable exists. Two halves, and the first is not optional: 5.0.3 shipped with
32 green probes and broke `nodus-sdk` at construction, because probes validate
nodus-lang against itself and nothing in them constructs a dependent.

---

## 10a — dependent suites, before the upload

```
PYTHONPATH="…/src;…" python -m tools.check_dependent_suites
```

Run with nothing else going — the release PR's CI was on a remote runner, and
no local suite, gate or server was running.

| companion | verdict | detail |
|---|---|---|
| nodus-mcp | PASS | 363 passed in 37.30s |
| nodus-mcp-server | PASS | 27 passed, 2 warnings in 1.64s |
| nodus-extension | PASS | 126 passed in 21.48s |
| nodus-sdk | PASS | 99 passed, 1 warning in 4.39s |
| nodus-native-memory-engine | PASS | 76 passed in 2.38s |
| nodus-jupyter | PASS | 32 passed in 1.58s |
| nodus-workflow-ai | PASS | 28 passed in 0.40s |
| nodus-a2a-wire | PASS | 188 passed in 13.58s |

**All 8 dependent suites pass — exit code 0.** 939 tests. nodus-mcp-server is
27 rather than last cycle's 25: its 0.1.13 (cut 2026-09-17, during this
cycle's example sweep) added the two HTTP-transport tests that would have
caught the `--http` mode that had never worked.

Exit 0 is the only pass. **2** would mean a checkout was missing or a suite
timed out, and **3** would mean every failure matched a recorded flake — neither
is a pass.

---

## 10b — adversarial probes against the wheel

```
cd $TEMP                                   # outside the repo
.venv-validation/Scripts/python.exe tests/eval/release_claims_probe.py \
    --repo "C:/dev/Coding Language" --require-installed
```

```
  package   C:\dev\Coding Language\.venv-validation\Lib\site-packages\nodus
  version   5.14.0
  import    …\.venv-validation\Lib\site-packages\nodus\__init__.py
```

**129/129 probes passed** against `nodus_lang-5.14.0-py3-none-any.whl` installed
into the validation venv **with the `[http]` extra**. Exit code 0.

The extra matters this cycle. The #855 probe asserts the TLS trust store is
built once per process, and it *refuses* to run without httpx rather than
passing vacuously — which is how the release PR's first `probes` CI run went
red: the job installed the bare wheel. The job installs `[http]` now. A probe
that cannot see what it claims to check should say so, and this one did.

### Falsified

`--time-limit` was renamed in the README in place and the run re-done:
**128/129**, the README probe naming the missing token. Restored from git.

### What the 5.14.0 probes assert

Eight were written **before the tag**, per the rule this project keeps: they
read the release's *claims*, and at 5.1.0 writing them early caught four
artifacts describing a vocabulary the release did not have.

| probe | what would have to break |
|---|---|
| #857: `serve` takes `--time-limit`; a request may lower it, not raise it; malformed refused | the flag disappears from the table, the ceiling stops holding, `min()` becomes `max()`, or a bad `timeout_ms` is silently ignored (#791's shape) |
| #862: a step past the budget under a service **returns** | the worker thread's exception escapes the accounting again and the request hangs — the probe runs it on a daemon thread with a 60 s bound so a regression is a red probe, not a hung gate |
| #858: `/workflow/run` runs a self-running program's flow once, and names *that* run | the second run comes back, or the response's `graph_id` stops matching the one the program saw |
| #856: a nested cross-module fan-out returns every inner result | the foreign-context adoption regresses and inner coroutines are dropped silently again — three temp modules, the judge-panel shape |
| #855: the trust store is built once per process | `create_ssl_context` is called per client again |
| #857: `workflow run` and `workflow-run` take `--time-limit` in seconds | either form goes back to milliseconds; the default-budget control must still time out or the probe proves nothing |
| README names the 5.14.0 surface | the permanent PyPI page stops describing what shipped |
| no stale "5.13.0 is current" claim survives | prose still calling the previous release current |

### The count moved, and a guard asked why

The eight went into `main()` in the same edit (the 5.13.0 lesson: `@probe`
wraps, it does not register), and the count moved 121 → 129 on the first run.
`test_release_probe_flags.py` then failed: it asserts the *number* of literal
`cli([...])` sites so a new argv it cannot read is not silently unchecked.
Three new sites, all literal, count updated 10 → 13 with the reason on the
line.

One of those three had been written as `cli(["workflow", "run", …])` — which
`main()` reads with `"workflow"` as the program name and dispatches to nothing,
exit 0. The probe's own control (the default budget *must* time out) was what
caught it. The trap is documented two screens above in the same file.

---

## Artifact checks

| check | result |
|---|---|
| `twine check dist/*` | PASSED, both |
| wheel built from the tagged tree | `v5.14.0` → `4bf86bb` |
| version files agree | `version.py` and `pyproject.toml` both 5.14.0 |
| `llms.txt` packaged copy in step | `tools.sync_llms_txt` re-run after the version-claim edits |
| `nodus_gate --versions` | 13/13 after the bump (9 were stale before it, in 6 files; 3 carried the old publish date) |
| `--closed-issues --section 5.14.0` | 5/5 |
| `nodus_gate --all` | all phases pass; consumers 1/3 in step (the two per-bump flags, Stage 6) |
| full suite (Gate 1) | 4030 passed, 0 failed |

---

## Follow-ups, not blockers

- **`nodus_gate --consumers` reports two stale**, both because `nodus_version`
  moved: `nodus-run-action` (pinned `version:` in its README) and the wiki. The
  wiki edit is substantive this cycle — the Security page did not know a step
  could hang the server through 5.13.0. Stage 6.
- **`nodus-mcp-server#3`** — the mcp 2.x port — is open and unrelated to this
  release; 0.1.13's `<2` pin makes fresh installs work.
