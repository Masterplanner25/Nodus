# v5.2.0 — Post-Publish Eval (Stage 5)

Against the **published** package, installed the way a new user installs it.
Prompt: `docs/governance/EVAL_POSTPUBLISH.md`.

| | |
|---|---|
| Package | <https://pypi.org/project/nodus-lang/5.2.0/> |
| Install | `pip install nodus-lang` into a fresh venv |
| Resolved | `nodus-lang 5.2.0` |
| Date | 2026-08-24 |
| Verdict | **PASS** |

Distinct from Gate 10 by design: Gate 10 asks *"what can I make fail?"* against a
local wheel; this asks *"does this work the way a new user would expect?"* against
the artifact on PyPI. The two have caught different things — 5.0.3 passed Gate 10
and was caught here.

---

## 1. Install and identify

```
$ pip install nodus-lang
$ nodus --version
Nodus 5.2.0
```

`pip install nodus-lang` with no version pin resolves to 5.2.0, so the release is
what a new user gets. No dependency conflicts, no build step — the wheel is pure
Python.

---

## 2. First program

```nodus
fn main() {
    print("hello from \(1i + 1i)")
}
```

```
$ nodus run hello.nd
hello from 2
```

---

## 3. The headline feature, as documented

The release's lede is that concurrent branches no longer lose a state write.
Typed from the README's own description:

```nodus
workflow tally {
    state counter = 0i with { merge: "sum" }
    step a { sleep(20i); counter += 1i; return 1i }
    step b { sleep(20i); counter += 1i; return 2i }
    step done after a, b { return 0i }
}
```

```
$ nodus run fold.nd
counter=2
```

`2`, with a real suspension between the read and the write — the case that
silently produced `1` in every prior release.

---

## 4. The three new commands

| command | result |
|---|---|
| `nodus doctor` | exit 0, reports the installed package and matching version sync |
| `nodus completion bash` | emits the script with its install line as a header comment |
| `nodus graph show g.nd` | renders the four-step diamond as Mermaid |

```
$ nodus graph show g.nd
flowchart TD
    %% build
    n0["fetch"]
    n1["compile"]
    n2["lint"]
    n3["package"]
    n0 --> n1
    n0 --> n2
    n1 --> n3
    n2 --> n3
```

**`nodus doctor` closes #535.** That issue recorded that doctor could not diagnose
the version gap it exists for, because it was not in any published release —
against an installed package it simply answered `Unknown command: doctor`. It is
now in one, and answers correctly from the installed console script.

---

## 5. The undeclared-cell path a new user actually hits

A user who does *not* read the merge documentation writes the racy version. What
they get:

```
$ nodus run race.nd
warning: steps a and b both wrote state 'x' while running concurrently and each
read it before writing, so one update was lost; only b's write survives. Declare
`with { merge: "sum" }` (or "append") to combine them, or `merge: "any"` if you
meant last-write-wins. This becomes an error in 6.0.0.

x=1
```

This is the important new-user check for this release. The warning:

- **fires** — the lost update is not silent, which it was through 5.1.0;
- **names both remedies**, so the next step needs no documentation lookup;
- **announces the flag day**, so the deprecation is discoverable from the tool
  rather than only from `COMPATIBILITY.md`;
- **still returns a result** rather than failing the run, which is correct for
  5.x and is what #547 changes at 6.0.0.

---

## 6. What this did not cover

- **Upgrade in place.** This is a fresh venv. `pip install --upgrade nodus-lang`
  over an existing 5.1.0 is untested, and the bytecode cache keys on the
  nodus-lang version, so a stale `.nodus/` is the thing to watch.
- **Optional extras.** `nodus-lang[retry]` not installed; `doctor` correctly warns
  that `@retry` falls back to the in-memory effect store.
- **Companion co-install.** Covered by Stage 6, which resolves published metadata
  rather than trusting a range read by eye.
- **Platforms.** Windows 11, CPython 3.11.9 only.
- **zsh / fish completion** — emitted but not executed; see #536.
