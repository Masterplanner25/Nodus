# v5.17.0 — Gate 10 creator validation (pre-publish)

**Artifact:** `nodus_lang-5.17.0-py3-none-any.whl` and `nodus_lang-5.17.0.tar.gz`,
built from a clean worktree of the tagged tree (`v5.17.0` → `1f45496`)

**Date:** 2026-11-22

5.17.0 is a minor. Its theme is **throughput** (#173):

- **Compile-to-Python, Experimental and opt-in.** It's turned on with
  `nodus run --compile`, `NodusRuntime(compile_functions=True)` or
  `NODUS_COMPILE_FUNCTIONS`. The parser written in Nodus parses its own source
  about 2.3× faster with it.
- **#987: a call into a module reuses an idle child VM** instead of building one.
  A loop of 2,000 standard-library calls runs about 8× faster.
- **#969: three fused instructions**, provisional, which take `BYTECODE_VERSION`
  to 5.
- **The defects that writing a Nodus frontend in Nodus turned up:**
  - #949: a parameter is nil when a later local reuses its name;
  - #952: a `return` leaves values on the caller's stack;
  - #957: `let` is lexical;
  - #950 and #954: `nodus fmt` defects.
- **Code in an imported module now runs within the caller's step limit and
  deadline.**
- **New string builtins:** `substring`, `str_span` and `str_span_until`.

## Gate 10a — dependent suites (before upload)

```
PYTHONPATH="src;." python -m tools.check_dependent_suites
```

Run with nothing else going, at 0.7 GB free. No timeouts. It took three rounds
to reach a verdict.

**Round 1: exit 1.** Three companions failed the same test:

| companion | failing test |
|---|---|
| nodus-extension | `test_invariants.py::TestBytecodeVersionUnchanged::test_bytecode_version_is_4` |
| nodus-native-memory-engine | `test_invariants.py::TestNoBytecodeVersionChange::test_nodus_bytecode_version_still_4` |
| nodus-a2a-wire | `test_invariants.py::test_no_new_opcodes` |

Each was meant to guarantee that the companion adds no opcodes. Each did it by
asserting **nodus-lang's** `BYTECODE_VERSION == 4`. That's nodus-lang's number,
which no companion can change, so the test guarded nothing in the companion. It
failed when #969 took the version to 5 through nodus-lang's own extension
process. Every other test in the three suites passed: 125, 75 and 187. No
companion behaviour broke.

**This is the gate working.** A dependent suite that would have gone red against
the published 5.17.0 was caught before the upload. These three companions have no
CI of their own, so this gate is the only place their tests run.

Each test was rewritten to check the companion instead. In a fresh interpreter,
importing every module of the package must leave a nodus VM's opcode set exactly
as it is without the package. The package's source must also never reach for
the VM's dispatch table or the bytecode version. Both halves were made to fail
first, with an import that adds an opcode, and in a2a-wire also a source line
reading `vm._dispatch`. The fixes are test-only, and nothing is republished:

- Masterplanner25/nodus-a2a-wire#2
- Masterplanner25/nodus-extension#4
- Masterplanner25/nodus-native-memory-engine#4

**Round 2: exit 1, against the fixed checkouts.** The three fixed suites passed.
nodus-mcp, which passed 376/376 in round 1, failed one test:
`test_streamable_http_end_to_end.py::test_host_routes_and_middleware_share_the_app`,
with `ConnectionAbortedError: [WinError 10053]`. The connection was aborted on
the unauthenticated POST the test expects a 401 for.

**Diagnosed, not re-run until green:**

- **The failing request never reaches nodus.** The Starlette authentication
  middleware refuses it before the tool layer.
- **Serial full-suite re-runs: one failed, one passed (376/376).** Across four
  runs the test failed twice. Intermittent.
- **Interleaved against the v5.16.0 source,** the single test ran 10 times each:
  0/10 failed on 5.16.0 and 1/10 on 5.17.0. At this rate that can't tell the two
  versions apart.
- **Reproduced without nodus.** A script with only Starlette, the same
  authentication middleware and uvicorn on a thread sent 500 unauthenticated
  POSTs with a body. 23 ended in `ConnectionAbortedError` and 4 in
  `ConnectionResetError`, with `nodus` never imported. The server answers 401
  and closes before reading the request body, and Windows reports the abort to a
  client still sending it.

So it's a Windows race in the test's HTTP harness, independent of nodus-lang. It
goes into `tools/dependent_flakes.json` with this evidence, so the next gate
classifies it instead of someone re-deriving it.

**Verdict:** every dependent suite passes against 5.17.0, except one test that
fails without nodus loaded at all.

| companion | verdict | detail (round 2; nodus-mcp from the serial re-run) |
|---|---|---|
| nodus-mcp | PASS | 376 passed, 2 warnings in 49.23s |
| nodus-mcp-server | PASS | 78 passed, 2 warnings in 11.59s |
| nodus-extension | PASS | 126 passed in 23.87s |
| nodus-sdk | PASS | 132 passed, 2 skipped, 1 warning in 16.02s |
| nodus-native-memory-engine | PASS | 76 passed in 1.73s |
| nodus-jupyter | PASS | 32 passed in 1.18s |
| nodus-workflow-ai | PASS | 28 passed in 0.34s |
| nodus-a2a-wire | PASS | 188 passed in 15.01s |

## Gate 10b — adversarial probes against the wheel

The wheel was installed into `.venv-validation` (upgraded in place, from 5.16.0)
with the `[http]` extra. The probes ran from `%TEMP%`, outside the repo, with
`--require-installed`:

```
package   C:\dev\Coding Language\.venv-validation\Lib\site-packages\nodus
version   5.17.0
```

**153/153 probes passed. Exit code 0.** Ten are new this cycle, written before
the tag. CI's `probes` job also ran them against its own wheel on PR #990.

- **Compiled runs match interpreted ones.** One program uses a loop, `*` and
  `%`, a closure called through a value, and a stdlib module call. It runs with
  `compile_functions` off and on. It gives the same output and the same
  instruction count both ways, with functions compiled only when it's on.
- **`nodus run --compile`** is accepted and runs the program.
- **`substring`, `str_span` and `str_span_until`** give the documented results,
  and a user `fn` of each name shadows the builtin.
- **Code in an imported module is bounded.**
  `NodusRuntime(max_steps=1000)` stops `s.repeat("a", 200000i)`, and its
  instructions are counted.
- **A loop of 50 module calls builds one child VM** (#987).
- **`let` is lexical** (#957):
  - a shadowing `let` reads the parameter;
  - a read before a block's own `let` sees the outer value;
  - a `let`-bound function recurses.
- **`BYTECODE_VERSION` is 5,** in the package and in `nodus stability`.
- **No current document says the bytecode is 4 or the opcode set is frozen
  at 49.** See below.
- **The README names the 5.17.0 surface.**
- **No document still calls 5.16.0 current.**

The single `Sandbox error … Execution timed out` line on stderr is the #862
probe's expected result, reported as PASS.

## Found while preparing the release

**#969 left nine current-state documents saying `BYTECODE_VERSION` 4 and the
opcode set "frozen at 49".** `nodus_gate --opcodes` passed throughout, because
it reads only some of the documents that make the claim. They were corrected
in the release PR, with dated history left alone. The probe added for them then
found two more that the first sweep had missed, in `README.md` and
`llms-full.txt`. README is the PyPI page, so that one would have been permanent.

**`skills/nodus.skill` taught that a closure cannot assign an outer `let`.** That
has been false since 5.8.0 (#671). Both cases were run on the tree before the
section was rewritten.

**`docs/AGENT_EXPERIENCE.md` called #939 open.** It's fixed in this release;
found by `nodus_gate --open-claims --strict` after refreshing the issue states.

**`docs/governance/COMPATIBILITY.md`'s timeline stops at v5.0.0, marked
current.** That's 22 releases unrecorded. It's too large for a release PR and is
filed as #991.

**Three behaviour changes** now have rows in the release sequence's "What is not
additive" table:
- module code within the caller's bounds;
- lexical `let`;
- a durable continuation saved by 5.16.0 does not resume across the bytecode
  bump.

Module calls reusing a child VM is internal and has no row; the probes above
cover it.

## Other pre-tag checks

- `ruff check src/ tests/` clean · `mypy src/nodus/ --no-site-packages` 0 errors
- `nodus_gate --all` before the bump: every phase PASS (runtime 303/303,
  closed-issues 16/16, shapes 0 new, flips 6 staged)
- `nodus_gate --open-claims --strict` PASS after `tools.refresh_issue_states`
- `nodus_gate --closed-issues --section 5.17.0` → 16/16
- `nodus_gate --versions` after the bump → 13/13 against 5.17.0
- `twine check` PASSED on both artifacts
- CI on PR #990 (merged as `1f45496`): `compiled`, `probes`, `py310-floor`,
  `pypy`, `security`, `test` all green on both runs
