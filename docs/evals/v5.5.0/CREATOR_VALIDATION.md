# v5.5.0 — Creator validation (Gate 10)

Pre-publish. Run against the wheel built from the tagged tree, before upload.

```
package   .../cleanvenv/Lib/site-packages/nodus
version   5.5.0
tag       v5.5.0 -> 8e6509f0fdc585fd34077f242a917c5da3189bd8 (== HEAD)
wheel     dist/nodus_lang-5.5.0-py3-none-any.whl
```

---

## The header did its job on its first use this cycle

`Gate 10` requires probes to print the resolved package path before their results,
because validating the wrong tree is the failure this gate has already had once — 5.0.3
passed with 32 green probes against a tree that was not the one being shipped.

That is exactly what happened here, and the header caught it:

```
  package   C:\dev\Coding Language\src\nodus        <- the SOURCE, not the wheel
  version   5.5.0
```

The cause is worth writing down because it will recur: the clean venv had the wheel
installed correctly (`pip list` showed `nodus-lang 5.5.0`), but the command ran with the
**repo root as CWD**, and Python puts the working directory first on `sys.path`. The
repo-root `nodus.py` shim shadowed the installed package. Re-run from a neutral directory,
it resolved to `site-packages` as intended.

Both numbers agreed — `version 5.5.0` either way — so nothing but the path line would have
revealed it.

---

## Gate 10a — dependent suites, before the upload

`python -m tools.check_dependent_suites`, run with nothing else going.

| companion | result |
|---|---|
| nodus-mcp | 363 passed |
| nodus-mcp-server | 25 passed |
| nodus-extension | 126 passed |
| nodus-sdk | 99 passed |
| nodus-native-memory-engine | 76 passed |
| nodus-jupyter | 32 passed |

**721 companion tests green, exit 0** — not exit 3, so no recorded flake was involved and
nothing needed a serial re-run. This is the gate that exists because 5.0.3 shipped past 32
green self-probes and broke `nodus-sdk` at construction: a project tested against itself
cannot find what it breaks in a consumer.

---

## Gate 10b, part one — release-claim probes

`tests/eval/release_claims_probe.py`, the durable script from 5.2.0, extended with 12
probes for 5.5.0. **47/47 pass** against the wheel.

**Written before the tag**, per the rule that has now paid four cycles running — and it
paid again, together with the post-bump `--versions` run. Between them they found **twelve
artifacts still naming 5.4.0 as current**, including `CLAUDE.md`'s own `.venv`-gap
paragraph, which had been updated earlier in this same session and went stale again the
moment the version moved. Run after the tag, the README half of that correction would have
been impossible.

Two of the new probes were confirmed falsifiable by mutation:

| mutation | result |
|---|---|
| a stale "current version" claim reappears in `llms.txt` | 46/47 — **RED** |
| the skill regains the removed `timeout_ms=200` advice | 46/47 — **RED** |

### A blanket replace nearly shipped four false history claims

Fixing the stale-version findings, a `5.4.0 -> 5.5.0` sweep over `skills/nodus.skill`
rewrote **historical** statements as well as current ones — turning "`try { } finally { }`
needs no `catch` (v5.4.0)" into "(v5.5.0)" for four features that shipped in 5.4.0.
Caught by reading every rewritten line rather than trusting the count. The distinction the
version-claims registry encodes — *"X is current"* goes stale, *"as of X"* does not —
applies to the fix as much as to the prose.

---

## Gate 10b, part two — adversarial boundaries

Ten boundaries, each attacking a claim this release makes. **10/10 held.**

| # | boundary | verdict |
|---|---|---|
| A1 | a step body reached through a coroutine | HELD |
| A1b | a step body reached through `std:retry` | HELD |
| A2 | the step guard against a **warm bytecode cache** | HELD |
| A3 | a guest writing into **relocated** run state | HELD |
| A4 | the embedded runtime still denies by default | HELD |
| A5 | `nodus docs` naming a bundled index that exists | HELD |
| A6 | both resolvers on malformed and package import forms | HELD |
| A7 | the new diagnostic cases firing on **valid** programs | HELD |
| A8 | a relocated run leaving run state in the CWD | HELD |
| A9 | a request with no graph receiving someone else's | HELD |

**Every negative assertion is paired with a control observed to fire.** A2 asserts a cache
directory exists before treating runs 2–3 as evidence about a warm cache. A3 pairs the
denied write with an ordinary write in the same sandbox that must succeed — otherwise the
denial could be the sandbox refusing everything. A7 ends with a real typo that must still
be reported, or "no false positives" would be indistinguishable from "reports nothing".
A9 asserts the first request actually produced a graph before concluding the second got
none of it.

That discipline exists because 5.4.0 shipped a probe that reported HELD while proving
nothing — its control could not fire in either mode.

### A9 could not run at first, and that is not a pass

It failed with `ModuleNotFoundError: No module named 'fastapi'`. `nodus.services.api`
imports FastAPI, which is an optional extra and absent from a bare install. An unrun probe
covers nothing, so the extra was installed and A9 completed properly rather than being
recorded as an environment quirk.

---

## What is in the wheel

Verified directly rather than assumed, since #605 is partly a packaging change:

```
llms.txt in the wheel: True
stdlib .nd count     : 27
total entries        : 176
```

`nodus docs` resolves that bundled index from `site-packages` (9,745 bytes) and pins every
web link to `/blob/v5.5.0/`, not `main` — an agent on an older release reading main's guide
is how the shipped skill came to teach a default removed two releases earlier.

---

## Verdict

**Ship.** 721 companion tests, 47/47 claim probes, 10/10 adversarial boundaries, all
against the wheel from the tagged tree, with the resolved path printed and checked.

One obligation carried forward: `nodus-run-action` pins 5.4.0 in its README and needs
republishing. `nodus_gate --consumers` reports it, advisory by design, and it belongs to
Stage 6 after this publishes.
