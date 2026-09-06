# Can a project tell whether it is ready for 6.0.0? (gate G3)

**Status: design, not decided. 2026-09-06, against 5.11.0.**
**Gate:** G3 in `docs/governance/V6_0_PLAN.md` — *"a project can enumerate its
own exposure without waiting to hit each path at runtime."*
**Register:** `tools/v6_flips.json`, checked by `nodus_gate --flips`.

## The problem

6.0.0 is flip-only (D5): five behaviours that warn today start failing. A user's
whole migration is "fix what the warnings told you about" — which assumes the
warnings told you.

G2 fixed *visibility*: every flip now warns on a path a user actually runs. It
did not fix *enumerability*. Four of the five only speak when the situation
arises at runtime, on the code path a particular run happens to take, so a
project can hold every one of these defects and see none of them. **"I ran it
and got no warnings" is not an answer**, and it is the answer people will act on.

## What is actually determinable

Measured against 5.11.0 by probing each one, not inferred from the code.

| Flip | Statically enumerable? | Where the answer comes from |
|---|---|---|
| #609 unknown type name | **Yes, fully** | the parser already records `unknown_type_names`; `nodus check` reports them, and `nodus run` does too since G2 |
| #547 concurrent write | **Yes, fully — and better than the runtime** | `cell_usage` (step → reads/writes) plus the graph's ordering relation, both known at lowering time |
| `worker:` with no dispatcher | **The declarations, fully** | `step.options["worker"]`. Whether a dispatcher *will* be registered is a deployment fact, not a source one |
| #174 default store | **Yes, fully** | not a source question at all — does the local store hold runs |
| #545 record equality | **No** | needs the runtime type of both `==` operands, and annotations are optional and unenforced |

**Four of five. The fifth is inherently dynamic**, and saying so plainly is
better than a check that looks complete and is not.

### #547 is the interesting one, and the static answer is *stronger*

The runtime detector reads `workflow_state` — what actually happened. But which
step writes which cell is known at lowering time (`cell_usage`, built by one AST
walk in `_StateRewriter`), and so is the ordering relation (`_cell_relation`).

Probed on a three-step workflow with two cells:

```
workflow race {
    state total = 0i
    state safe = 0i with { merge: "any" }
    step a { total = 1i; safe = 1i; return "a" }
    step b { total = 2i; safe = 2i; return "b" }
    step c after a { total = 3i; return "c" }
}
```

| | reports |
|---|---|
| runtime warning | `total`, steps **a and b** |
| static analysis | `total`: **(a,b)** and **(b,c)**; `safe`: (a,b), suppressed by its declared `merge: "any"` |

Two things to take from that. The static pass correctly excludes **(a,c)** —
`c after a` orders them — so it is not merely "every pair that touches the cell".
And it found **(b,c)**, a real exposure this run did not hit: `b` and `c` are
unordered, both write `total`, and either can win. **The runtime warning is
interleaving-dependent; the static one is not.**

So for #547 the static answer is a superset of the dynamic one, with no false
negatives, and the declared-policy filter (`merge: "any"` / a fold) is available
from the same AST.

### #545 is the one that cannot be answered statically

`Record.__eq__` decides at comparison time; the warning fires when identity says
"not equal" and a field-by-field comparison says "equal". Answering that from
source needs the types of both operands, and Nodus annotations are optional,
unenforced, and — until 6.0.0 — silently ignored when misspelled.

A syntactic approximation ("`==` where an operand is a `record {…}` literal")
would find the textbook case and miss every real one, where the records come
from a function return or a list element. **A check that reports "0 issues" on a
codebase full of them is worse than no check.**

The honest answer for #545 is dynamic: run the program, or its tests, and
collect what the warning says. That argues for the second half below.

## Two halves, and neither is sufficient alone

**1. A static scan** covering #609, #547, `worker:` and #174 — the four that can
be answered without executing anything.

**2. A way to accumulate the dynamic findings** across a run or a test suite,
for #545 and as confirmation for the rest. The warnings already exist and are
precise; what is missing is that they are transient stderr lines, so a full test
run tells you nothing you did not read as it scrolled past. An env var naming a
report file (`NODUS_STAGED_FLIP_REPORT`) would make `nodus test` produce an
exposure list as a side effect.

The report must say **which of the five it actually checked**, per flip, and
which it cannot. Silence from a check that never looked is the failure this whole
cohort is about.

## Where the surface should live — open

Three candidates, none obviously right, which is why this is a design doc.

| | Fits because | Does not fit because |
|---|---|---|
| **`nodus check --staged`** | `check` is already *the* static-analysis command, and #609's answer is already there | `check` is per-file; readiness is project-wide, and #174 is a filesystem question with no file to check |
| **`nodus doctor --staged`** | `doctor` is already project-scoped, already aggregates independent `Check`s with a JSON mode, and #174 fits it exactly | `doctor` is about the *environment* — the install, the version gap, the project layout — not about your code |
| **a new subcommand** | one obvious place, holds both halves, discoverable | a command that exists for one migration window is a real cost, and this project has removed surfaces for less (#794) |

**Recommendation: `nodus doctor --staged`.** `doctor` already has the shape this
needs — project-scoped, a list of independent checks, structured output — and
the objection to it is about *convention* rather than mechanics. The alternative
argument is real, though: readiness is a question about your code, and doctor has
never been.

**Name it for the durable question, not the version.** `--staged` (or
`--next-major`), never `--v6`. `tools/v6_flips.json` is already shaped to be "the
flips staged for the next major"; a command called `--v6` needs replacing at
7.0.0, and a version in a flag name is the same class of claim as *"X is
current"* in prose, which `nodus_gate --versions` exists because of.

## What this is not

- **Not a fixer.** It reports; the user edits. Four of the five have a remedy
  already named in the warning text.
- **Not a gate.** `nodus_gate --flips` is for this repo's maintainers and
  answers a different question — *is every promise registered* — not *is your
  project exposed*.
- **Not a replacement for the warnings.** They are the signal for someone who
  never runs this command, which will be most people.

## Open decisions

- **R1 — Which surface?** See the table. Blocks implementation.
- **R2 — Does the dynamic half ship with the static half, or after?** The static
  half is the larger win and can stand alone; #545 is the only flip that needs
  the dynamic one, and it is the least destructive of the five.
- **R3 — Does the `worker:` check report every declaration, or try to guess
  whether a dispatcher will exist?** Reporting every declaration is honest and
  slightly noisy; guessing is neither.
- **R4 — Is a clean report allowed to say "ready"?** Given #545 cannot be
  checked statically, a green static run does not mean ready. The wording has to
  carry that, or the tool tells a comfortable lie — which is precisely the
  failure mode of the notice in #797.
