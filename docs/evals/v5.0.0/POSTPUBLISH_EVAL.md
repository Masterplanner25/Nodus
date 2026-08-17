# Stage 5 — post-publish eval, v5.0.0

**Against the published package**, installed fresh from PyPI. Template:
[`EVAL_STAGE4_TEMPLATE.md`](../../governance/EVAL_STAGE4_TEMPLATE.md); prompt:
[`EVAL_POSTPUBLISH.md`](../../governance/EVAL_POSTPUBLISH.md).

| | |
|---|---|
| Installed | `pip install nodus-lang==5.0.0` into a fresh venv |
| `nodus --version` | `Nodus 5.0.0` |
| Summary line | *"An orchestration DSL and embedded runtime for hosting agentic systems"* |
| Date | 2026-08-17 |
| Verdict | **PASS — no findings** |

This asks a different question from Gate 10. Gate 10 asks *"what can I make
fail?"* against a locally built wheel. This asks **"does it work the way someone
arriving from the README would expect?"** against what PyPI actually serves —
including whether the docs describe the thing that shipped.

---

## Probes

| # | What a new user does | Result |
|---|---|---|
| S1 | `nodus init` then `nodus run`, straight from the README | `rc=0` both; prints `hello from nodus` |
| S2 | Hello world via the CLI | `rc=0` |
| S3 | A workflow with `with { retries: 2 }` — the headline construct | `attempts=3 step=3` — retries honoured end to end (#392) |
| S4 | The embedding quickstart from the guide | `ok=True`, output `3` |
| S5 | A new embedder hits deny-by-default | `ok=False`, and the message tells them the fix: *"pass `allow_subprocess=True` to NodusRuntime to allow it"* |
| S6 | …and following that instruction | `ok=True`, output `ran` |
| S7 | The new `goal … over …`, exactly as the guide teaches it | see below |
| S8 | `--help` and `nodus stability` | `rc=0` both |

### S7 reproduces the guide verbatim

`docs/guide/workflows-and-tasks.md` §7.1 publishes this output. The published
package produced it character for character:

```
score is now 40.0
score is now 80.0
score is now 120.0
true
3.0
```

That is the check worth having: the documentation example and the shipped
artifact agree, rather than the docs describing an intention.

### S5 is the one that matters for this release

The breaking change is only defensible if the failure is self-explaining. A user
whose code stops working gets:

```
Blocked: subprocess execution is not granted;
         pass allow_subprocess=True to NodusRuntime to allow it
```

— which names the fix rather than reporting the flag's current value. Following
it works (S6). This was the design intent; S5/S6 confirm it survived to the
published artifact.

## Cross-checks against the release claims

- **Deny-by-default is real for embedders** (S5) and **absent for the CLI** (S2,
  S3, S7 all shell out or run freely with no flags). The deliberate split holds
  in the published package.
- **`goal … over …` is usable** from a clean install with no extra setup (S7).
- **Retries are honoured** on the CLI path (S3), which was #392's whole point.

## Findings

**None.**

## Known issues shipping, restated

Carried from [`CREATOR_VALIDATION.md`](CREATOR_VALIDATION.md) §4 so this document
stands alone:

- ~~**`nodus-vscode` is not republished.**~~ **Resolved 2026-08-17** — 0.1.2 is
  live on the Marketplace and the five `goal` keywords highlight. See
  [`STAGE6_DOWNSTREAM_SWEEP.md`](STAGE6_DOWNSTREAM_SWEEP.md) §5.
- **Three docs still reference 4.2.0** as current — `README.md`,
  `RELEASE_GATES.md`, `real-world-integration.md`. Deliberately deferred: no gate
  checks version strings, so this is cosmetic and is the first task of the next
  cycle rather than a blocker for this one.
- The pre-existing `test_scheduler_fairness` flake, and the build machine's
  unreliable local suite (see Gate 10 §4). CI on a clean runner passed every PR.

## Not covered

- No load or soak testing of the capability layer.
- The deferred capability work (layered rule sources, approval caching,
  attenuation, `ask` → `workflow_wait`) is unimplemented, so there is nothing to
  evaluate.
- Companion packages are Stage 6, not this document.
