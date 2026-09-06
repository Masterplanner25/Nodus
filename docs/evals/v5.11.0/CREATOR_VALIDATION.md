# v5.11.0 — Gate 10 creator validation

**Verdict: ship.** Both halves pass against the built wheel on the first build.
No defect stopped this release, which makes the interesting part of this record
what the *sequence* caught before the tag rather than what the gate caught after
it.

| | |
|---|---|
| Tag | `v5.11.0` → `0855740` |
| Artifacts | `nodus_lang-5.11.0-py3-none-any.whl`, `nodus_lang-5.11.0.tar.gz`, `twine check` **PASSED** |
| Gate 10a | **6/6 dependent suites**, 721 tests, exit 0 — no re-runs needed |
| Gate 10b | **105/105 probes** against the installed wheel, `--require-installed` satisfied |
| Suite | 3,729 collected |
| `nodus_gate --all` | 9 phases green · `--closed-issues --section 5.11.0` 12/12 · `--versions` 13/13 against 5.11.0 |

---

## 1. Gate 10a — dependent suites, before the upload

```
nodus-mcp                      PASS      363 passed in 56.52s
nodus-mcp-server               PASS      25 passed, 1 warning in 1.63s
nodus-extension                PASS      126 passed in 40.93s
nodus-sdk                      PASS      99 passed in 9.14s
nodus-native-memory-engine     PASS      76 passed in 3.65s
nodus-jupyter                  PASS      32 passed in 2.41s
```

Exit **0** on the first run, with nothing else running. No recorded flake was
consulted, so the verdict rests on a clean result rather than on
`dependent_flakes.json` classifying one away.

This gate exists because 5.0.3 shipped past 32 green probes and broke
`nodus-sdk` at construction: nothing in a self-validation constructs a
dependent. It remains the only check that would catch that class.

## 2. Gate 10b — 105 probes against the wheel

Run from `…/scratchpad/gate10b`, **outside the repo**, with
`--require-installed`. The resolution was confirmed before the run:

```
resolved: C:\dev\Coding Language\.venv-validation\Lib\site-packages\nodus
version: 5.11.0
```

That check is not ceremony. Run from the repo root the *same interpreter*
reports:

```
resolved: C:\dev\Coding Language
```

— the repo-root `nodus.py` shim shadowing the installed package, which is how
5.0.3, 5.5.0 and 5.6.0 were each validated against the wrong tree. It was
reproduced deliberately this cycle to confirm the trap is still live and the
guard still catches it.

### The 11 probes new this cycle

| claim | measured against the wheel |
|---|---|
| an absolute deadline removes the drift a relative sleep adds | relative **703 ms** vs absolute **500 ms**, on the program's own clock |
| a past deadline yields rather than starving siblings | interleaving `a0 b a1 a2` |
| `spawn_after` defers the spawn itself | body ran **125 ms** in |
| `std:loop.every` holds a fixed period | five 100 ms periods around 30 ms of work: **500 ms** |
| `run_after`, because `after` is reserved | `loop.after` does not parse; `loop.run_after` works |
| a program can see its own sleep | 200 ms sleep reads back as **218 ms** |
| `barrier: true` makes readers wait for writers | reader saw both writers with no `after` clause |
| a conditional barrier writer is refused | refused at declaration, message naming the barrier |
| a module can spawn a wrapper around a caller's closure | ran, and read a root-level `let` (#783, #786) |
| nothing still calls 5.10.0 current | no document does |
| the README names the new surface | `sleep_until`, `spawn_after`, `std:loop`, `barrier` all present |

Timings are measured on the **program's own clock** (`runtime.time_ms()`), not
wall time, so they assert the release's claim rather than how fast this box is.

## 3. What the sequence caught that the gate could not

Two findings landed before the tag, which is where they had to land.

### `--versions` found 10 stale claims, after the bump

The gate passes by definition before step 2 and is only informative after it —
which is why the sequence re-runs it there. Ten claims across seven files still
said 5.10.0, including `llms.txt` (which ships **inside the wheel**) and both
project instruction templates a user copies into their own repo.

### Two of the shipped skill's "non-negotiable rules" were false

`skills/nodus.skill` is what an agent installs and reads as fact. Both were
checked by running them, not by reading:

| rule | claimed | actual |
|---|---|---|
| 1 | a module-top-level `let` is read-only inside a function — use a quoted-key map | writable since 5.8.0 (#671): `let total = 0i; fn bump() { total = total + 5i }` → **10** |
| 6 | `spawn()` rejects a function | accepts a zero-arg function since #718: `spawn(fn() { print("hi") })` → **runs** |

Rule 1 was worse than merely stale: it prescribed a workaround for a defect that
no longer exists. This is the same failure CLAUDE.md already records for this
file, recurring — the file is guidance that ships, and nothing derives it from
the runtime, so only someone running its examples can find it.

## 4. Method note: one probe of mine was vacuous on first write

The barrier-refusal probe asserted only that the program failed:

```python
assert not result.get("ok") or text.strip()
```

A program can fail for reasons that have nothing to do with the claim, so that
passes on a build where barriers do not exist at all. It now asserts the refusal
*message* names the barrier and the conditional write.

The two prose probes were falsified against a doctored copy of the tree —
restoring a stale `5.10.0` and deleting `sleep_until` from the README each turn
one red. A probe that has never been seen to fail is not evidence.

## 5. Not covered here

- **Stage 5** (`POSTPUBLISH_EVAL.md`) — against the published package, after upload.
- **Stage 6** (`STAGE6_DOWNSTREAM_SWEEP.md`) — companion ranges, publish drift,
  non-PyPI consumers.

Gate 10 answers *"what can I make fail against a local wheel?"*. Neither of the
other two questions is answered by it, and 5.7.0's history is the reason all
three are separate records.
