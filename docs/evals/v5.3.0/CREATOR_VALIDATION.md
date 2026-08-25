# v5.3.0 — Creator Validation (Gate 10)

Adversarial validation of the **built wheel**, in a clean venv, before upload.
Prompt: `docs/governance/EVAL_PREPUBLISH.md`.

| | |
|---|---|
| Artifact | `dist/nodus_lang-5.3.0-py3-none-any.whl` (built from the `v5.3.0` tree) |
| Tag | `v5.3.0` → `62af1be` |
| Venv | `%TEMP%\g10venv`, `pip install <wheel>`, no other packages |
| Resolved | `C:\...\g10venv\Lib\site-packages\nodus` · **5.3.0** |
| Date | 2026-08-25 |
| Verdict | **PASS** |

The resolved package path and version are printed by every probe before its
results. Validating the wrong tree is the failure mode this gate has already had
once — 5.0.3 passed with 32 green probes against a tree that was not the one
shipped, and broke `nodus-sdk` at construction.

---

## Part a — dependent suites, before the upload

```
companion                      verdict   detail
------------------------------------------------------------------------------
nodus-mcp                      PASS      363 passed in 45.51s
nodus-mcp-server               PASS      25 passed in 0.96s
nodus-extension                PASS      126 passed in 22.78s
nodus-sdk                      PASS      99 passed in 5.57s
nodus-native-memory-engine     PASS      76 passed in 0.26s
nodus-jupyter                  PASS      32 passed in 1.67s

All 6 dependent suites pass.          exit 0
```

721 companion tests. Run with nothing else going, per the concurrency rule — a
red verdict from this gate is only believable if it is the only thing running.

This is the part that exists because **testing a project against itself cannot
find what it breaks in consumers**. 5.3.0 touches `NodusRuntime.__init__`
(`writable_paths=`, `worker_dispatcher=`) and `VM.__init__`, which is exactly the
shape that broke `nodus-sdk` at 5.0.3 — a base class adding a name a subclass had
made a property.

---

## Part b — probes against the wheel

```
  package   C:\Users\shawn\AppData\Local\Temp\g10venv\Lib\site-packages\nodus
  version   5.3.0

24/24 probes passed
```

Nine are new for this release, one per claim:

| Probe | Result |
|---|---|
| a deny-everything policy reaches tool/syscall/agent/memory | 10 capabilities; `memory_put` denied as `memory.write` |
| every builtin is classified | 287 = 60 governed + 227 not |
| a syscall's declared capability is enforced | `sys.v1.memory.put` refused by a policy denying `memory.write` |
| `writable_paths` splits context from editable files | readable context, editable subtree, refusal names the reason |
| `nodus.toml` refuses what it does not read | `[project]` refused with the fix named; `entry` selects the file |
| an unhonoured `worker:` warns | warns, names both remedies, announces the flag day |
| a conditional edge is marked and drawn | `on:` labels, `when` dashes, both formats |
| a step guard error names `when` | names its own clause and points at the idiom |
| prose does not describe the pre-5.3.0 surface | no artifact still describes the smaller vocabulary |

### What the prose probe caught, before the tag

`docs/governance/ECOSYSTEM_COVERAGE_ANALYSIS.md` still recorded
`SyscallSpec.capability` as **"declarative metadata, never enforced"** — a
sentence #478 had made false. Every code gate was green at the time.

This is the **second consecutive cycle** where the pre-tag prose probe found
something nothing else could; at 5.1.0 it caught four artifacts describing a
task-status vocabulary the release did not have, one of them `README.md`. Run
after the tag, neither correction would have been possible.

Two fixes to the probe harness itself, both from this run:

- **`CHANGELOG.md` is excluded from the stale-prose sweep.** It flagged the 5.3.0
  entries describing what had been fixed. Recording what *was* is a changelog's
  job.
- **The reporter reconfigures stdout to utf-8.** It raised `UnicodeEncodeError`
  on cp1252 while printing the real finding above, turning a caught defect into a
  traceback. A probe that dies while reporting is worse than no probe.

---

## Part c — adversarial pass

Nine attempts to defeat what the release says it enforces. All held.

| Attempt | Outcome |
|---|---|
| escape `writable_paths` via `src/../ctx/x` | refused — `readable but not writable` |
| escape via an absolute path outside both lists | refused |
| `append_file` / `mkdir` unscoped while `write_file` is scoped | both refused |
| reach memory through `syscall` when the policy denies | refused at the `syscall` gate |
| reach a tool through `action tool` when `tool_call` is denied | policy saw `tool.invoke` |
| register a syscall with a capability no policy can name | `ValueError`, known set listed |
| hide `[secret]` beside valid tables in `nodus.toml` | refused, table named |
| write into read-only context via a subprocess redirect | refused |
| `DenyList("anything.i.like")` | `ValueError` |

### One probe was worthless and was caught

The subprocess-redirect attempt initially reported `HELD` with `no error`, which
is the wrong shape for a boundary test — a refusal should carry a refusal. It had
passed **vacuously**: the option is `stdout: "path"`, not `stdout_file:`, so no
redirect was ever configured and nothing was written for the jail to refuse.

Re-run against both targets, it is a real test:

```
WRITABLE target  -> created: True  | ok: True
READ-ONLY target -> created: False | kind: sandbox
    subprocess stdout redirect blocked: path 'ctx/leak.txt' is readable but not writable
```

This is the failure mode `CLAUDE.md` records for negative assertions — three
written in one session could not fail. The rule that caught it: for every
boundary claim, confirm the permitted case actually succeeds, or "it did not
happen" proves nothing.

---

## Part d — the CLI, from the installed console script

```
$ nodus --version
Nodus 5.3.0

$ nodus run h.nd
hello from 2

$ nodus doctor
[  ok  ] nodus package: 5.3.0 from installed package at ...\g10venv\Lib\site-packages\nodus
[  ok  ] version sync: installed nodus-lang==5.3.0 matches the imported module
[  ok  ] interpreter: CPython 3.11.9 ...
[ warn ] optional extras: nodus-retry is not installed
[  ok  ] project: no nodus.toml ... (running in script mode)

$ nodus run --help
  --allow-paths PATHS        Restrict file I/O to colon-separated paths
  --writable-paths PATHS     Subset of those that may be written (default: all)
```

`doctor` resolves the installed package rather than a checkout, and the new flag
is documented where it is parsed.

---

## What this did not cover

- **Upgrade in place.** A fresh venv only. `pip install --upgrade` over an
  existing 5.2.0 is Stage 5's business; the bytecode cache keys on the
  nodus-lang version, so a stale `.nodus/` is the thing to watch.
- **The `nodus.toml` break, against a real third-party project.** #490 refuses
  input that previously loaded. The two manifests on record were checked by hand;
  there is no way to survey manifests that exist elsewhere.
- **Platforms.** Windows 11, CPython 3.11.9. CI covers Linux for the suite but
  not this wheel.
- **`allow_subprocess=True` plus `writable_paths`.** The runtime's own writes and
  a subprocess's redirect targets are scoped; what a *spawned child* writes is
  not, and cannot be. Stated in the runbook rather than left implicit.
