# v5.18.0 — Gate 10 creator validation (pre-publish)

**Artifact:** `nodus_lang-5.18.0-py3-none-any.whl` and `nodus_lang-5.18.0.tar.gz`,
built from a clean worktree of the tagged tree (`v5.18.0` → `415f952`)

**Date:** 2026-11-26

5.18.0 is a minor because it adds a public builtin, `str_join`. It has six
entries and no single theme. They are the four smaller issues left after 5.17.0,
plus two found while fixing them:

- **#999 (security): `max_memory_mb` is checked whenever `VM.execute` returns.**
  It was sampled only every 256 instructions. A run that went past the ceiling
  and ended within one interval returned `ok=True`.
- **#992 and #998 (performance): `std:strings.repeat` and `std:strings.join`
  are linear.** `join` calls the new `str_join` builtin. 300,000 items took
  16.3 s and now take 0.07 s.
- **#975 (fix): one stdout writer with a UTF-8 fallback** for the CLI, tooling
  and `nodus test`. `nodus dis`, `nodus ast` and `--dump-bytecode` crashed on a
  cp1252 stdout.
- **#991 (fix): `COMPATIBILITY.md`'s release timeline is frozen at v5.2.0** and
  says so.
- **#978 (tooling): `nodus_gate --shapes` sees every standard mutable
  container.**

## Gate 10a — dependent suites (before upload)

```
PYTHONPATH="src;." python -m tools.check_dependent_suites
```

Run with nothing else going. **Exit 0 on the first round**, with no timeouts and
no recorded flakes matched.

| companion | verdict | detail |
|---|---|---|
| nodus-mcp | PASS | 376 passed, 2 warnings in 47.01s |
| nodus-mcp-server | PASS | 78 passed, 2 warnings in 8.22s |
| nodus-extension | PASS | 126 passed in 19.58s |
| nodus-sdk | PASS | 132 passed, 2 skipped, 1 warning in 16.40s |
| nodus-native-memory-engine | PASS | 76 passed in 2.16s |
| nodus-jupyter | PASS | 32 passed in 1.11s |
| nodus-workflow-ai | PASS | 28 passed in 0.35s |
| nodus-a2a-wire | PASS | 188 passed in 14.72s |

No companion uses the name `str_join`. That was checked with a search of every
`.nd` and `.py` file under `C:/dev` outside virtualenvs, before the builtin was
added.

## Gate 10b — adversarial probes against the wheel

The wheel was installed into `.venv-validation`, upgraded in place from 5.17.0
with `--force-reinstall --no-deps`. The extras the probes need were already
installed there. The probes ran from `%TEMP%`, outside the repo, with
`--require-installed`:

```
package   C:\dev\Coding Language\.venv-validation\Lib\site-packages\nodus
version   5.18.0
```

**160/160 probes passed. Exit code 0.** Seven are new this cycle, written before
the tag. CI's `probes` job also ran them against its own wheel on PR #1002.

- **#999, the ceiling on exit:** `NodusRuntime(max_memory_mb=16)` refuses one
  64 MB allocation followed by the end of the program, with kind `sandbox`. This
  is a few instructions, far fewer than one sampling interval.
- **#999, the message:** an allocation Python cannot satisfy reports
  "Out of memory" instead of an empty message.
- **#998 and #992, the cost:** under `max_steps=500`, a 100,000-item `join` and
  a 100,000-copy `repeat` both finish, in 47 instructions together. The loops
  they replaced took about 25 instructions per item and 13 per copy.
- **`str_join`:** it gives the documented results, and `join` keeps its old
  ones. A string's characters are its items, and one item ignores `sep`. A user
  `fn str_join` shadows the builtin.
- **#975:** `nodus dis` on a program holding `→`, with
  `PYTHONIOENCODING=cp1252`, exits 0 and writes the arrow as UTF-8.
- **The README names the 5.18.0 surface.**
- **No document still calls 5.17.0 current.**

The single `Sandbox error … Execution timed out` line on stderr is the #862
probe's expected result, reported as PASS.

## Found while preparing the release

**A test leaned on `strings.join`'s old loop.**
`test_stack_discipline.py::test_slot_access_stays_inside_the_frame_across_the_stdlib`
required more than 20 slot accesses, and the loop supplied most of them. With the
builtin it saw 8, and CI failed on #998's PR. It is not a slot violation, since
there were none. It now drives `collections.list_sum` as well. It is the same
shape as #992, where tests used `repeat` as a deliberately long loop.

**#917 is 6.0.0 work, not a 5.18.0 item.** Its warning phase shipped in 5.16.0
(#919). What remains is the flip at the major, from `"warn"` to `"refuse"`.

**Two behaviour changes** have rows in the release sequence's "What is not
additive" table:
- a run past `max_memory_mb` that ends within one interval now fails;
- `join` on a map of two or more entries gives a `type` error instead of a
  `key` error.

## Other pre-tag checks

- `ruff check src/ tests/` clean · `mypy src/nodus/ --no-site-packages` 0 errors
- `nodus_gate --all` before the bump: every phase PASS (runtime 303/303,
  closed-issues 6/6, shapes 0 new, flips 6 staged)
- `nodus_gate --open-claims --strict` PASS after `tools.refresh_issue_states`
- `nodus_gate --closed-issues --section 5.18.0` → 6/6
- `nodus_gate --versions` after the bump → 13/13 against 5.18.0
- `nodus_gate --consumers`: advisory STALE for `nodus-run-action` and the wiki,
  whose pinned version moved. That is Stage 6 work, after the publish.
- `twine check` PASSED on both artifacts
- CI on PR #1002 (merged as `415f952`): `compiled`, `probes`, `py310-floor`,
  `pypy`, `security`, `test` all green on both runs. The full suite was left to
  CI because the box had 1.2 GB free.
