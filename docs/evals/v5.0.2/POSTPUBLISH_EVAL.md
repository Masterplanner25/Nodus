# Stage 5 — post-publish eval, v5.0.2

**Date:** 2026-08-17 · **Verdict: clean, no new findings.**

Run against the **published** package from PyPI, in a venv with no dev source on
the path and in a directory outside any Nodus project. Gate 10 asks "what can I
make fail?" against a local wheel; this asks "does this work the way a new user
would expect?" against the artifact they receive.

---

## 0. What this release is

Two correctness fixes, both of which a user is better off having:

- **#411** — `@exactly_once` and `@retry` were forgeable, and so was the workflow
  lowering via `workflow_state()`. Three lines of user code replaced the envelope
  the compiler injected, and the annotated body never ran.
- **#449** — the bytecode cache was not keyed on the nodus-lang version, so
  upgrading left cached modules compiled by the old compiler.

**#449 is why #411 could not ship alone.** Without it, a user with a warm
`.nodus/` would upgrade to the #411 fix and keep running the forgeable bytecode.

## 1. Install

```
$ pip install nodus-lang
$ nodus --version
Nodus 5.0.2
```

Resolved to 5.0.2 on the first attempt, with no index lag — unlike the 5.0.1
publish, where pip's cached index page briefly returned the previous version. Worth
noting only because that lag is intermittent, not fixed: the correct response
remains checking the simple index rather than re-uploading.

## 2. New-user flow

```
$ nodus init
Initialized Nodus project at …\work\
$ nodus run src/main.nd
hello from nodus
```

**Printed once.** That matters here: Gate 10 filed
[#453](https://github.com/Masterplanner25/Nodus/issues/453) for scripts executing
their top level *twice* when run by path from inside a Nodus project. The scaffold
path — `nodus init` then `nodus run src/main.nd` from the project root — is
**unaffected**, which narrows #453 usefully and means the flow a new user actually
follows is correct.

## 3. Both fixes, exercised from the published package

```
$ nodus run forge.nd
exactly_once: real          # was FORGED before #411

$ nodus run wf.nd
workflow: total is 1        # was 10000 before #411
```

```
same version   -> cache hit : True
bumped version -> cache hit : False      # #449
```

The first two are the actual exploits from the issue, run verbatim against what
PyPI serves. The third is the mechanism that makes the first two reach anyone who
upgrades.

## 4. Cross-checks against the release claims

| Claim | Verified how |
|---|---|
| "`@exactly_once` no longer forgeable" | the issue's own three-line reproduction, against the published wheel |
| "workflow lowering had the same hole" | `workflow_state()` shadow returns `total is 1`, not `10000` |
| "cache now keyed on nodus-lang version" | hit at the same version, miss at a bumped one |
| "no bytecode change" | Gate 10 opcode phase: 49 opcodes, `BYTECODE_VERSION` 4 |
| "no behaviour change for anyone not shadowing those names" | eval scripts byte-identical to 5.0.1 in matched conditions |
| README banner carries no version | corrected in 5.0.1's cycle; the PyPI page for 5.0.2 shows the current text |

That last row is the one 5.0.1 got wrong — its README edit landed *after* the tag,
so its PyPI page permanently shows a stale banner. For 5.0.2 the README was
finished before tagging, per the rule added in #448.

## 5. Findings

**None new.** Everything surfaced this cycle was found by Gate 10 or CI and is
already filed: #453 (double execution for in-project paths, pre-existing),
#452 (`test_task_yield`'s stderr assertion and the leaked handles behind it).

## 6. Known issues shipping, restated

#453, #452, #387 (a bare `VM()` has no limits — the structural twin of #411, still
open), #380. See the Gate 10 document §5.

## 7. Not covered

- **Windows only.** `py3-none-any` wheel, so platform risk is low, but untested
  elsewhere from this machine.
- **Upgrade-in-place from 4.x or 5.0.x.** Fresh venvs throughout. Note that #449
  makes the first run after any upgrade recompile every cached module — intended,
  and the point of the fix.
- **Coverage** not re-measured; the 76.82% baseline is over 200 tests stale.
