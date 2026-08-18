# Stage 5 — post-publish eval, v5.0.3

**Date:** 2026-08-17 · **Verdict: clean, no new findings.**

Run against the **published** package from PyPI, in a fresh venv with no dev source
on the path and outside any Nodus project.

---

## 0. What this release is

Seven fixes, six sharing one shape: a guarantee that held on one path and not its
sibling. The load-bearing question for this eval is whether each actually reaches a
user through the artifact PyPI serves — not merely whether it works in the tree.

## 1. Install

```
$ pip install nodus-lang
$ nodus --version
Nodus 5.0.3
```

### The index lag recurred, and was handled by checking rather than re-uploading

The first fresh install returned **5.0.2**. The simple index already listed 5.0.3:

```
index versions: ['5.0.0', '5.0.1', '5.0.2', '5.0.3']
```

so this was propagation, not a failed upload — the same behaviour recorded in the
5.0.1 eval. A second fresh venv installed 5.0.3 immediately.

This is now the second of three publishes where the first check after upload
reported the previous version. It is worth treating as normal rather than as a
signal: **check the simple index; never re-upload on the strength of a first
check.** A re-upload would fail here (PyPI rejects duplicate filenames), but the
same reflex against a Marketplace or a GitHub release is destructive, and release
immutability makes the GitHub case permanent.

## 2. New-user flow

```
$ nodus init
Initialized Nodus project at …\work\
$ nodus run src/main.nd
hello from nodus
$ nodus run src/main.nd        # again — the #453 case
hello from nodus
```

Printed once both times. Worth noting the scaffold was never affected by #453: it
does not use the `fn main()` + `main()` pattern, so the second run had nothing to
double. The path a new user actually follows was correct before and after.

## 3. All seven fixes, exercised from the published package

```
#453  main() runs once on a cached second run: [1, 1]
#387  bare VM call-depth cap: True
#424  4s handler bounded to 0.31s
#185  B reads A's secret: nil (want nil)
#390  bare VM falls back to global runner: True
#396  check catches a cycle: True
#425  resume says not found: True
```

Each is the issue's own reproduction, run against what PyPI serves rather than
against the tree.

## 4. Cross-checks against the release claims

| Claim | Verified how |
|---|---|
| "a script ending in `main()` ran it twice" | `[1, 1]` across a cold and a warm run |
| "a bare `VM()` had no call-depth cap" | `max_frames == MAX_STACK_DEPTH` on a bare VM |
| "a host agent handler had no timeout" | a 4 s handler returns in 0.31 s |
| "two runtimes shared memory" | B reads `nil`, not A's secret |
| "workflow runs had no owner" | a bare VM still falls back to the global runner — no embedding API broke |
| "no bytecode change" | Gate 10 opcode phase: 49 opcodes, `BYTECODE_VERSION` 4 |
| README banner is current | packaged `Description-Content-Type: text/markdown`, "Recent: 5.0.3" present in the wheel metadata **before** the tag |

That last row is the one 5.0.1 got wrong — its README edit landed after the tag, so
its PyPI page permanently shows a stale banner. Checked in the built wheel this
time, before uploading.

## 5. Findings

**None.** Everything surfaced this cycle was found by Gate 10 or CI and is already
filed: #452, #457, #400, #401, #334. See the Gate 10 document §4.

## 6. Not covered

- **Windows only.** `py3-none-any` wheel, so platform risk is low, but untested
  elsewhere from this machine.
- **Upgrade-in-place from 5.0.x.** Fresh venvs throughout. Note #449 (5.0.2) means
  the first run after upgrading recompiles cached modules — which is what makes
  this release's compiler-level fixes (#453 especially) actually apply.
- **Coverage** not re-measured; the 76.82% baseline is 336 tests stale.
