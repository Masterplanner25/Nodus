# Gate 10 — creator validation, v5.0.4

**Date:** 2026-08-17 · **Verdict: clean, no findings.**

Run against the wheel built from the tagged tree (`v5.0.4` → `717c766`), installed
into a clean venv with no dev source on the path, outside any Nodus project.

```
$ nodus --version
Nodus 5.0.4
```

5.0.4 exists to repair one thing 5.0.3 broke, and to close the gate gap that let
it ship. Both are validated below.

---

## 0. Dependent suites — **new, and the point of this release**

This step did not exist for 5.0.3, which is why 5.0.3 shipped broken.

```
companion                      verdict   detail
------------------------------------------------------------------------------
nodus-mcp                      PASS      363 passed
nodus-mcp-server               PASS      25 passed
nodus-extension                PASS      126 passed
nodus-sdk                      PASS      99 passed
nodus-native-memory-engine     PASS      76 passed
nodus-jupyter                  PASS      32 passed

All 6 dependent suites pass.
```

`tools/check_dependent_suites.py`, run **before** the upload. A missing checkout
exits 2 rather than passing — an unrun suite covers nothing.

**Why it is here.** Gate 10 passed 5.0.3 cleanly: 32 adversarial probes, all
green. It validates nodus-lang *against itself*, and nothing in it constructs a
dependent. Stage 6 does, and caught the break — but Stage 6 is post-publish, and
PyPI is immutable. The defect was found one release too late and cost a 5.0.4.

## 1. The 5.0.3 regression specifically

`NodusRuntime.__init__` assigned `self.memory_store`; `nodus_sdk.NodusSDKRuntime`
subclasses it with `memory_store` as a **read-only property** holding its own
vector store. Against the 5.0.4 wheel:

```
subclass with a read-only memory_store property constructs: True
its property is untouched: True
Nodus memory still works: v
```

nodus-sdk is back to 99 passed **with no change on its side**, so the repair
travels to users through a nodus-lang release rather than requiring every
companion to move.

## 2. Standard eval scripts

| Script | 5.0.3 | 5.0.4 |
|---|---|---|
| `quirk_probe.nd` | 45 lines | 45 lines |
| `language_exerciser.nd` | 52 lines | 52 lines |
| `framework_capabilities.nd` | 39 lines | 39 lines |

Identical, all exit 0.

## 3. Adversarial probes

The full 5.0.3 probe set re-run against this wheel: **32 checks, all pass** —
#453 main-once, #387 call-depth cap, #424 handler bounded, #185 memory isolation
with its `share_process_state` escape hatch, #390 runner resolution, #396/#425,
the 5.0.1–5.0.2 surfaces, the CLI's deliberate deny-by-default exemption, the
Floor with its control write, and `--help` not executing.

## 4. Gates

| Gate | Result |
|---|---|
| Dependent suites (**step 0**) | 6/6 pass |
| `ruff check src/ tests/ tools/` | clean |
| `nodus_gate --all` | PASS — 135 symbols, 239 blocks, 6 contracts, 26 opcode checks |
| CI on PR #462 | both test jobs pass on a clean runner |
| Full suite (local) | 2,213 passed, 3 skipped, **3 failed in 10m11s** — see below |

### The local suite was not green, and this is why that did not block

Three failures. Two pass in isolation. The third,
`test_long_running_task_rotates_with_budget`, is the flake `CLAUDE.md` names by
name, failing on `Execution timed out`.

The same suite ran **2,214 passed / 0 failed in 7m47s** earlier the same day, and
the entire source diff since `v5.0.3` is a **4-line private rename** plus
comments — which cannot affect scheduler timing, IEEE754 division, or print
buffering. CI on a clean runner passed both jobs.

`CLAUDE.md`'s standing instruction for this pattern is to re-run alone and let CI
arbitrate, which is what happened. Recorded rather than smoothed over: a reader
should be able to see that this release shipped with a red local run and why that
was judged acceptable.

## 5. Known issues shipping

Unchanged from 5.0.3: #452, #457, #400, #401, #334. See the v5.0.3 Gate 10
document §4.

## 6. Not covered

- **Coverage** not re-measured; the 76.82% baseline is now well over 300 tests stale.
- **Windows only.** `py3-none-any` wheel, so platform risk is low.
- The dependent-suite gate runs each companion against **this checkout**, not
  against the built wheel in a clean venv. That is faster and catches the API-shape
  breaks this class of defect produces; it would not catch a packaging-only fault.
