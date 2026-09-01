# v5.9.0 — Gate 10 creator validation

**Verdict: ship.** Both halves of Gate 10 pass, against the built wheel rather
than the checkout.

| | |
|---|---|
| Tag | `v5.9.0` → `ea9af85` |
| Artifacts | `nodus_lang-5.9.0-py3-none-any.whl`, `nodus_lang-5.9.0.tar.gz`, `twine check` PASSED |
| Gate 10a | **6/6 dependent suites pass**, 721 tests, exit 0 |
| Gate 10b | **88/88 probes pass** against the installed wheel |
| Suite | 3,353 passed, 8 skipped |
| `nodus_gate --all` | 9 phases green |

---

## Gate 10a — dependent suites, before the upload

Run with nothing else going, per the rule added after 5.1.0 reported a spurious
`nodus-mcp FAIL` while a clean-venv probe ran alongside it.

```
companion                      verdict   detail
nodus-mcp                      PASS      363 passed in 54.15s
nodus-mcp-server               PASS      25 passed in 2.79s
nodus-extension                PASS      126 passed in 85.20s
nodus-sdk                      PASS      99 passed in 14.22s
nodus-native-memory-engine     PASS      76 passed in 1.84s
nodus-jupyter                  PASS      32 passed in 3.78s

All 6 dependent suites pass.      EXIT=0
```

Exit **0**, not 3 — no failure matched a recorded flake, because there were no
failures. Worth stating explicitly, since 3 is not a pass and reads similar in a
summary.

This gate exists because 5.0.3 shipped without it: #185 assigned
`self.memory_store` on `NodusRuntime`, `nodus_sdk.NodusSDKRuntime` defines that
name as a read-only property, and every construction of the subclass raised. Gate
10b passed that release with 32 green probes, because it validates nodus-lang
against itself and nothing in it constructs a dependent. `nodus-sdk` is in the
list above for that reason.

---

## Gate 10b — the wrong-tree trap fired again, fifth cycle running

Before the probes, the sanity check — and it caught the thing it exists to catch:

```
$ cd "C:/dev/Coding Language"
$ .venv-validation/Scripts/python.exe -c "import nodus; print(nodus.__file__)"
version 5.9.0
path C:\dev\Coding Language\nodus.py          <-- the REPO shim, not the wheel
```

A clean venv with only the wheel installed, and `import nodus` still resolved to
the source tree — because the repo-root `nodus.py` shim inserts `src/` on
`sys.path` and re-execs from there, and Python puts the working directory first.
Nothing in `pip list` hints at it.

From outside the repo:

```
$ cd "C:/Users/shawn/AppData/Local/Temp"
$ .venv-validation/Scripts/python.exe -c "import nodus; print(nodus.__file__)"
version 5.9.0
path ...\.venv-validation\Lib\site-packages\nodus\__init__.py
```

The probe run therefore carries its resolved path in the header, and
`--require-installed` exits 2 rather than relying on anyone reading it:

```
========================================================================
  package   C:\dev\Coding Language\.venv-validation\Lib\site-packages\nodus
  version   5.9.0
  import    ...\.venv-validation\Lib\site-packages\nodus\__init__.py
  repo      C:\dev\Coding Language
========================================================================
                            88/88 probes passed
```

That is five cycles in which this has fired (5.0.3 shipped past it; 5.5.0, 5.6.0,
5.8.0 and now 5.9.0 caught it). It is not a lapse anyone is going to stop making
— the mechanical guard is the answer, and it works.

---

## The five new probes

Written **before the tag**, per the rule that these are the only check reading the
release's *claims* rather than its code. Run after the tag, any correction they
force is impossible.

| probe | asserts |
|---|---|
| #691 | a callback into a module runs **inside a step body**, and the step is recorded |
| #696 | a closure a module **returns** works at top level, upvalues intact |
| #704 | a file rewritten at the same mtime runs the new program, not the cached one |
| #170 | bytes survive a round trip that text mode refuses (`0x80`, `0x1A`, `0xFF`) |
| prose | nothing still calls 5.8.0 the current release |

Every behaviour probe runs **in the position its documentation points at**. That
is #691's lesson rather than a stylistic preference: `retry.until` shipped in
5.8.0 with a full suite, nine gate phases and 83 release probes behind it and did
not work inside a step body, because every one of them ran in `fn main()`. A
probe that exercises the easy position proves the easy position.

The #691 probe asserts two things, not one: that `got 7` appears **and** that the
step is recorded as `"a": "ok"`. The original defect printed nothing after the
module call and reported `failed: []` with `steps: {}` — a probe checking only for
an absent error would have passed against it.

---

## Two probe defects found before tagging

Both mine, both caught by running the probes rather than reading them.

### 1. Absolute paths in a Nodus `import`

The first draft interpolated the module's absolute path into the import
statement. Nodus refused it — `Invalid package import: path escapes dependency
directory` — which is correct behaviour and a probe bug.

### 2. A relative import resolves against the CWD, not the `filename` label

Switching to `import "./m.nd"` moved the failure rather than fixing it:
`Import not found: './m.nd' (tried <scratchpad>/m.nd, ...)`. The probe passed
`filename=` pointing into the temp directory and expected imports to resolve from
there. They do not — `filename` is a **label**, and that is #521 exactly: *"a real
path only decides where relative imports resolve from"*, and `run_source` is not
given one.

Fixed by writing a real `main.nd` into the temp directory and using `run_file`,
which is the route the regression tests already take for the same reason.

Neither was a product defect, and both would have been discovered after the tag
had the probes been written at step 8 instead of before step 6.

---

## Supporting gates

| gate | result |
|---|---|
| suite | 3,353 passed, 8 skipped (3,132 at the 5.8.0 cut) |
| ruff / mypy / `nodus fmt --check` | clean |
| keyword coverage | 13 passed |
| `nodus_gate --all` | static 140/140, runtime 270/270, closed-issues 6/6, contracts 6/6, opcodes 29/29, consumers 2/2, shapes 0 new, versions 13/13, invariants 4/4 |
| `--closed-issues --section 5.9.0` | 6/6, re-run **after** the cut |
| `--versions` after the bump | **10 of 13 claims were stale**; all fixed |
| `twine check` | PASSED on both artifacts |

The `--versions` re-run is the one worth recording. Before the bump it passes by
definition; after it, it named ten stale sentences across seven files — including
all four skill and project-template files, which a user copies into their own
project as a standing instruction file. Four of those lines also carried
`published 2026-08-30`, a date the gate does not check and which would have
shipped wrong.

CLAUDE.md contains seventeen occurrences of `5.8.0` and exactly **one** is a
claim; the rest are historical statements that must not change. Editing by
registered line number rather than by search-and-replace is what keeps that true.

---

## Verdict

**Ship.** Nothing found in Gate 10 blocks the upload. The two defects above were
in the probes, are fixed, and are recorded here because the *timing* of their
discovery is the reusable part: they were findable only because the probes were
written before the tag.
