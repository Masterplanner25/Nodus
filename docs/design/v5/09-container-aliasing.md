# Container aliasing, and whether a copy surface is owed — #814

**Status: implemented.** The rule is documented and pinned; `copy(value)` shipped
with all three sub-decisions below taken as recommended. The aliasing rule is stated in
[`docs/guide/types-and-values.md` §6](../../guide/types-and-values.md) and pinned
by `tests/test_container_aliasing.py`. This document records why the rule is what
it is, what a copy surface would have to decide, and the one defect the
investigation turned up (#822).

## The rule

**Lists, maps and records are reference values. Assignment binds; it does not
copy.** Verified in five shapes — list alias, map alias, record alias, a
container reached through another, and across a function-call boundary — and in
four execution contexts: module top level, inside a function, inside a coroutine,
and inside a workflow step body. The behaviour is uniform, and was uniform before
anything asserted it.

This was not a decision made now. It is what the VM has always done; `#814` is
about the fact that nothing said so, nothing tested it, and
`docs/governance/ROADMAP.md` still carried *"Formalize value semantics for:
records / maps / lists"* as an open item. The rule is documented as-is rather
than changed, for two reasons:

- **It is the only rule consistent with the rest of the language.** Function
  arguments, container nesting and closure capture all already behave this way,
  so copy-on-assign would need a matching answer for each and would make
  `list_push(items, v)` inside a function a no-op from the caller's view.
- **Changing it is a breaking change to a Stable surface** with no reported harm
  behind it. #822 is a real defect, but it is about *state cells*, and it is
  fixable without changing what `let b = a` means.

### Binding and equality are different questions

Worth stating because #545 makes them look connected. Maps and lists compare
**structurally** while binding **by reference**, and records join them at 6.0.0.
Structural equality does not make a container a value: after that flip, two
records with equal fields will be `==`, and two names for one record will still
share every mutation. `RecordAliasingSurvivesTheEqualityFlipTests` pins both
halves so the changelog line for #545 cannot be read as "records became value
types".

## What is expressible today

Measured, not assumed:

| | Shallow copy | Deep copy |
|---|---|---|
| list | `col.map(xs, fn(x) { return x })` | no |
| map | `keys(m)` + a loop | no |
| record | **no** | **no** |

The record row is the gap that matters. `keys()` accepts a map and refuses a
record (`keys(x) expects a map`), so a record's fields cannot be enumerated and a
generic record copy **cannot be written in Nodus at all**. You can only rebuild
one field by field, which requires knowing every field — and silently produces a
wrong answer when a field is added later.

So "hand this container to something without letting it change under me" is
awkward for two of the three kinds and impossible for the third.

## Recommendation: a copy surface is owed

Three arguments, in order of weight:

1. **The record case has no workaround.** The other two rows are inconvenient;
   this one is a hole. A language whose stated domain is *building agentic hosts*
   asks people to hand data to step bodies and handlers constantly, and gives
   them no way to hand out a snapshot.
2. **The machinery already exists and is already used at boundaries.**
   `nodus/vm/runtime_values.py` has `clone_json_value`, and `agent_runtime` and
   `memory_runtime` already snapshot values crossing into them. The host has
   decided this question for itself; guests cannot ask it.
3. **#822's fix needs snapshotting internally.** Whatever option that issue
   takes, a state cell will have to copy on read, on write, or both. Exposing the
   same primitive is close to free once it exists.

Against, and the reason this is a recommendation rather than a merged change:
it is a new language surface, and two sub-decisions have to be made first.

### Sub-decision 1: deep, not shallow

**Deep.** Shallow is the option already expressible for lists and maps, and it is
the one that gives false confidence — a shallow copy of `{"inner": [1, 2]}`
still shares `inner`, which is exactly the case a reader thinks they have
protected themselves against. Deep is what "hand this out safely" means.

### Sub-decision 2: what to do with a value that cannot be copied

A record can hold a closure, a channel or a coroutine handle. None of those has a
meaningful copy.

**Refuse, with an error naming the field.** The language already draws this line
in the same place: a `state` cell holding a closure or a channel is refused at
persist time (#498), and a cell cannot hold a record at all for the same
serializability reason. Making `copy` refuse a live handle reuses a rule the
language has rather than inventing a second one — and the alternative, sharing
the uncopyable leaf, produces a "copy" that is not one, silently.

### Sub-decision 3: a global builtin, not `std:collections`

**A global `copy(value)`.** #814 suggested `std:collections`, and that is wrong
for one reason: **records are not collections.** The record case is the one that
motivates the surface, so putting it in a module named for collections makes the
central case the odd one out. Its neighbours — `len`, `keys`, `has_key`,
`list_push` — are all globals already.

Adding a global is safe here: guest code can shadow a builtin name with its own
`fn`, verified at 5.9.0 (#170) and again at 5.11.0, so a new global cannot
collide with an existing program.

## The defect this turned up: #822

A workflow `state` cell holds a live reference, so a step can change a cell's
recorded value **without writing to it** — by mutating the container it read
back — and the write-conflict machinery, which watches `cell = value`, does not
see it. Two declared writers warn and name both steps; one declared writer plus
one mutating reader is silent.

That is the recurring shape in the place where it costs most: the declared write
path is watched, the sibling path is not, and at 6.0.0 the declared path becomes
an *error* (#547) while the undeclared one stays silent — the wrong pressure to
put on people.

**Fixed, and the investigation found it worse than first reported.** The
headline turned out not to be the mutating reader but the *indexed write*:
`cell[i] = v` and `m["k"] = v` are ordinary, documented spellings, and both
bypassed the tracker entirely — no conflict warning, no `merge:` policy, nothing
for #547 to fire on, and a fold cell's declaration refusal lost as well. One
correction to the first write-up: **#578's barrier inference was never
affected**, because `_record_container_write` already walked an index chain to
its root at compile time. The compile-time half was right; the runtime half was
absent.

It also eliminated one of the four fix options. **Snapshot-on-read alone is not
viable**: `cell[i] = v` lowered to a read followed by an in-place mutation, so
returning a copy from the read would have discarded the write silently — turning
a working feature into a no-op. The read had to stop being the mutation path
first.

The fix is *ownership*, and it is the same idea `copy` embodies one level up: a
cell stores a copy, hands back a copy, and has exactly one deliberate exception,
`TrackedState.open_for_write`, which records a read and a write and then returns
the cell's own object so the compiler's in-place mutation lands. Both container
assignment forms route through it, asserted on the source — #518 was an
enumeration of assignment forms with a member missing, and a behaviour test only
covers the forms it knows about.

**It costs something, measured rather than waved at.** A scalar cell is
unchanged; growing a list cell in a loop is about +20%; the worst plausible
shape — a 200-element cell written by index 200 times — is **+57%**, because the
cost is O(cell size) per write rather than constant. That is the price of not
losing writes silently, and it is worth stating rather than discovering.

## What was done

- The rule is in `docs/guide/types-and-values.md` §6, with executed examples,
  the two places it bites, what can be copied today, and the record gap.
- `tests/test_container_aliasing.py` pins all five shapes across four execution
  contexts (#818).
- `ROADMAP.md`'s "Memory Model Clarification" item is updated: the
  formalization half is done, the cloning-helper half points here.
- #822 filed.

## What shipped

`copy(value)` is a global builtin, registered in `builtins/collections.py`,
classified as pure computation in `capability.py`, covered by
`tests/test_copy_builtin.py` and documented in both
`docs/guide/types-and-values.md` §6 and `docs/guide/standard-library.md`.

One thing the implementation added that the design above did not anticipate:
**shared structure is preserved rather than expanded**, via a memo keyed on
object identity. That is not a refinement — it is a requirement. All three
container kinds can hold a reference to themselves (`list_push(a, a)`,
`m["self"] = m`, `r.x = r`, all verified constructible), so a memo-less deep copy
hangs. Preserving sharing falls out of the same mechanism, and is the more
faithful answer anyway: a copy of a shape, not an expansion of it.

A second small thing: `type()` reports a `BuiltinMethod` as `unknown`, which
would have made the refusal message useless on exactly the values people meet it
on — the method fields of a stdlib record such as `std:hash`'s. The copy error
names it `method` itself rather than widening `type()`, which is a separate
surface with #609's type-name work staged against it.

## What is not done

- Field enumeration for records is **not** proposed here. It would make a
  generic record copy writable in Nodus, but it is a larger surface with its own
  questions (does it expose method fields? does it order?), and it is not needed
  if `copy` exists.
