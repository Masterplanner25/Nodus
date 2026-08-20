# Stage 5 — post-publish eval, v5.1.0

Date: 2026-08-20 · <https://pypi.org/project/nodus-lang/5.1.0/>

Stage 5 asks a different question from Gate 10. Gate 10 asks *"what can I make fail
against the artifact I built?"*. This asks **"does this work the way a new user would
expect?"** — against the package actually on PyPI, installed the way a stranger would
install it.

---

## 1. A new user installs it

Fresh venv from a system Python, no `PYTHONPATH`, no local checkout on the path:

```
$ pip install nodus-lang
Name: nodus-lang
Version: 5.1.0
Summary: An orchestration DSL and embedded runtime for hosting agentic systems

$ nodus --version
Nodus 5.1.0
```

Plain `pip install nodus-lang` resolves to 5.1.0 — the resolver picks the new release
rather than pinning back to something older, which is not automatic when companions
carry caps (see §3).

## 2. It does what the release notes say

The full adversarial probe suite, re-run unchanged against the **published** package:

```
nodus package: ...\stage5\Lib\site-packages\nodus\__init__.py
version:       5.1.0

13/13 probes passed
```

Every headline claim of the release holds on the published artifact: step guards in
both directions and their compile-time check, `on: ["failed"]` / `on: ["skipped"]`,
refusal of end-of-run conclusions as join options, `omitted` for a declared outcome
that never occurs, `+=` into workflow state (#518), `durable: false`, refusal of the
unimplemented fold policies, `filename=` as a label (#521), deny-by-default, and the
SQLite cursor lifetime (#516).

Standard scripts through the published CLI:

```
quirk_probe              ALL QUIRKS CONFIRMED
language_exerciser       ALL EXERCISES PASSED
framework_capabilities   ALL FRAMEWORK PROBES PASSED
```

## 3. The ecosystem is installable alongside it

**This is the check v5.0.0 failed**, and it is why this section exists. At 5.0.0 five
of six companions published `nodus-lang<5.0.0`, so `pip install nodus-lang==5.0.0
nodus-mcp` was `ResolutionImpossible` and the release was unadoptable for anyone using
the ecosystem. The Stage 6 sweep asked the right question and transcribed five of six
ranges with the upper bound dropped. It was found by an outside team, not by us.

Done here by installation, not by reading:

```
$ pip install nodus-lang==5.1.0 nodus-mcp nodus-sdk nodus-extension \
              nodus-mcp-server nodus-jupyter
(exit 0)

nodus-extension           0.1.2
nodus-jupyter             0.1.0
nodus-lang                5.1.0
nodus-mcp                 0.1.3
nodus-mcp-server          0.1.12
nodus-protocol            0.1.0
nodus-retry               0.2.0
nodus-schema              0.1.0
nodus-sdk                 0.1.2
```

No backtracking, no resolution failure, and `nodus-lang` stays at 5.1.0 rather than
being dragged back by a cap.

Independently, resolving *published* metadata with `packaging` rather than by eye:

```
nodus-mcp                    0.1.3      >=4.0.0     ok
nodus-mcp-server             0.1.12     >=4.0.5     ok
nodus-extension              0.1.2      >=4.0.0     ok
nodus-sdk                    0.1.2      >=4.0.0     ok
nodus-native-memory-engine   0.1.1      >=4.0.0     ok
nodus-jupyter                0.1.0      >=4.0.0     ok

All 6 companions admit nodus-lang 5.1.0.
```

The reason this is resolved by tool and not by reading: `>=4.0.0,<5.0.0` reads as
"admits 4.x", which is what the eye checks for, and the clause that forbids the new
version sits at the far end of the string.

## 4. First-run experience

A workflow written from the README's own vocabulary, run by the published CLI:

```nodus
workflow greet {
    state name = "world"
    step build { return "hello, \(name)" }
    step shout after build { return "\(build)!" }
}
```

```
$ nodus run hello.nd
hello, world!
{"build": "completed", "shout": "completed"}

$ nodus check hello.nd
hello.nd: OK
```

`statuses` appears without being asked for, which is the point of it.

## 5. Findings

**None blocking.** Two observations, neither a defect:

- `nodus fmt --check` reports a hand-written file as unformatted. Correct behaviour —
  the file was typed by hand and not run through `fmt` — but worth knowing that the
  first thing a new user writes will usually fail a format check until formatted.
- The `nodus.nd` entry-point group is empty for a bare `nodus-lang` install. Expected:
  that group is how companions contribute `.nd` roots, and none is installed here.

## 6. Not covered

- Windows only.
- No load or soak testing of the published package.
- The behaviour change in #521 was verified to be *fixed*; no attempt was made to
  survey real embedders for reliance on the old behaviour. The README and `CLAUDE.md`
  both carry the upgrade note.
