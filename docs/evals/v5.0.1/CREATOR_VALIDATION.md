# Gate 10 — creator validation, v5.0.1

**Date:** 2026-08-17 · **Verdict: clean, no findings.**

Run against the wheel built from the tagged tree (`v5.0.1` → `e871495`),
installed into a clean venv with no dev source on the path:

```
nodus_lang-5.0.1-py3-none-any.whl
$ nodus --version
Nodus 5.0.1
```

This is a patch release whose entire content came from a downstream adoption
report on 5.0.0 (aindy-runtime). So the probes below are weighted toward the
question that actually matters here — *does the thing we just promised hold in the
artifact we are about to publish?* — rather than toward re-exercising the language.

---

## 1. Standard eval scripts

All three run to completion against the wheel, and their output is **byte-identical**
to the same scripts run against dev source:

| Script | Result | vs dev source |
|---|---|---|
| `quirk_probe.nd` | exit 0, 90 lines | identical |
| `language_exerciser.nd` | exit 0, 104 lines | identical |
| `framework_capabilities.nd` | exit 0, 78 lines | identical |

The comparison is the point. A patch release that only adds exports and tests
should produce no behavioural difference, and "identical" is a stronger statement
than "exit 0".

## 2. Adversarial probes

Eleven probes, each written to try to make a 5.0.1 claim false. **All pass.**

| # | Probe | What it would have caught |
|---|---|---|
| P1 | `GATED_BUILTINS` importable and complete from the wheel | The new export missing from the built artifact, or the 31/7/18/6 counts drifting |
| P2 | `register_all` contains no hardcoded gated names | The registry keeping a stale duplicate of the list — the drift the export exists to prevent |
| P3 | Constructor shape | A confinement flag defaulting to `True`, losing keyword-only, or `**kwargs` reappearing |
| P4 | Denial contract | `kind` not `"sandbox"`, or a message that no longer names the flag |
| P5 | All 31 gated builtins present as blocked stubs | A gated builtin going *missing* rather than blocked — which reads to a user as a typo, not a refusal |
| P6 | `active_vm()` lifecycle + `_get_active_vm()` alias | The new accessor not shipping, or diverging from the alias downstream pins |
| P7 | `register_function` refuses builtin override | The security boundary that lets a host install a fail-loud guard under a guest-reachable name |
| P8 | Granting `allow_subprocess=True` restores the real builtin | A gate that blocks permanently rather than conditionally |
| P9 | **CLI is still not deny-by-default** | The deliberate CLI exemption being "fixed" into consistency |
| P10 | The Floor still blocks writes into `.nodus/` | A guest forging run records |
| P11 | `nodus <cmd> --help` exits 0 without executing | #353, the bug that recurred four times |

### P10 was a false pass on the first run, and is recorded because of it

The probe originally asserted only that the `.nodus/` write returned `ok=False`.
It did — with `Undefined variable: fs`, because the script never imported
`std:fs`. The assertion was **true for the wrong reason**, and would have passed
just as happily against a runtime with no Floor at all.

Rewritten with a control: an *ordinary* write must succeed in the same sandbox
before the `.nodus/` write is judged. Both halves now checked, plus that no file
appears on disk:

```
control  ordinary write ok = True | None
floor    .nodus/ write ok = False | kind = sandbox
         | Blocked: writing to the runtime's own state directory is never permitted ('.nodus/…')
```

Worth stating plainly rather than quietly fixing: a probe that cannot fail is
indistinguishable from a probe that passes, and this one was one line away from
being reported as evidence.

## 3. Gates

| Gate | Result |
|---|---|
| Full suite | **2,138 passed, 3 skipped, 0 failures** in 7m46s (2,140 collected) |
| `ruff check src/ tests/ tools/` | clean |
| `nodus_gate --static` | PASS — 135/135 symbols |
| `nodus_gate --runtime` | PASS — 239/239 blocks |
| `nodus_gate --contracts` | PASS — 6/6 |
| `nodus_gate --opcodes` | PASS — 26/26, 49 opcodes, `BYTECODE_VERSION` 4 |
| `nodus_gate --closed-issues --section 5.0.1` | PASS — **5/5** referenced issues have tests |
| CI on PR #446 | both test jobs pass (5m17s, 5m21s); security pass |

The closed-issues phase was re-run scoped to `5.0.1` rather than trusting the
default, which after the section cut scans an empty `[Unreleased]` and reports a
pass that checked nothing.

**The suite slowdown from the 5.0.0 cut was transient.** 7m46s with zero failures,
against ~18 min and intermittent subprocess failures naming a different test each
run on 2026-08-16/17. `CLAUDE.md` asked for this to be re-measured rather than
assumed; it has been, and the paragraph is updated.

## 4. Downstream constraint check

New this release, and the reason the release exists:

```
Do published companions admit nodus-lang 5.0.1?

companion                    published  nodus-lang range           verdict
------------------------------------------------------------------------------
nodus-mcp                    0.1.3      >=4.0.0                    ok
nodus-mcp-server             0.1.12     >=4.0.5                    ok
nodus-extension              0.1.1      >=4.0.0                    ok
nodus-sdk                    0.1.2      >=4.0.0                    ok
nodus-native-memory-engine   0.1.1      >=4.0.0                    ok
nodus-jupyter                0.1.0      >=4.0.0                    ok
```

Verified end-to-end in a clean venv as well — nodus-lang 5.0.0 plus nodus-mcp,
nodus-extension, nodus-sdk, nodus-mcp-server and nodus-jupyter install together,
a script runs, and deny-by-default still refuses `subprocess_run`.

## 5. Known issues shipping with this release

Unchanged from 5.0.0; none is introduced or worsened here.

- **#411** — `@exactly_once` is forgeable: the lowering calls shadowable names, so
  a program can replace the envelope the compiler injected into it. This is the
  highest-signal open issue, because the domain statement rests on
  `@exactly_once` being the project's best "you cannot forget it" property.
- **#387** — a directly constructed `VM()` has no limits at all; every guard lives
  in a wrapper. Structural twin of #411 and of this codebase's recurring bug shape.
- **#380** — bounding the local workflow store's scan cost (prune by count, or an
  index instead of a full rescan).
- 19 governance docs still carry the self-contradicting "needs review before repo
  commit and push" marker, having been committed and pushed on 2026-05-29.

## 6. Not covered

- **Coverage was not re-measured.** The 76.82% baseline dates from 2026-08-07 at
  1,878 tests and is now 262 tests stale. It is a floor, not a reading. Not a
  blocker for a patch that only adds tests, but it should stop being carried
  forward as though current.
- **No new `.nd` language surface**, so the formatter round-trip and checker
  categories of the standard prompt are exercised only via the eval scripts and
  the suite, not separately.
- **Marketplace / GitHub Action surfaces.** `nodus-vscode` 0.1.2 and
  `nodus-run-action` v1.0.0 are unaffected — 5.0.1 adds no keyword and changes no
  syntax — so neither needs a republish. Confirmed by inspection, not by tooling;
  neither is on PyPI and the constraint check cannot see them.
