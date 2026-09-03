# `nodus-scheduler`

**Status:** reference implementation (#88). Not published.
**Tier:** 2 — infrastructure primitives.
**Depends on:** `std:time`, `std:strings`, `std:math`. No Python.
**Written in:** Nodus — see *Why this one is not Python* below.

---

## Summary

Given a schedule, when does it next fire? That is the whole library.

It does not run anything, hold state, or start a process. Cron expressions,
fixed intervals and calendar rules become a **number of milliseconds**, which is
what `workflow_wait` takes. Everything after that already exists.

---

## Why the scope is this small

The issue asked for "a registry library providing cron, interval, and
calendar-based scheduling for workflows", and listed among its dependencies *"a
scheduling daemon or in-process scheduler (design open)"*. That open design was
[#176](https://github.com/Masterplanner25/Nodus/issues/176), and #88 was
deliberately blocked on it — building first would have baked in whichever answer
the implementer assumed.

**#176 answered it: the runtime owns the timer, and the host owns re-invocation.**

- `workflow_wait(..., {deadline_ms: N, on_timeout: "resume"})` parks a run until
  a time.
- `nodus workflow sweep` releases it and carries the workflow on.
- A resumed step that arms its successor recurs indefinitely.

Nothing auto-executes, and that is a security decision rather than an
ergonomics one: a run record carries the program's whole source (#499), so a
runtime that rehydrated on startup would run whatever the working directory's
store happened to hold.

So the daemon is an ordinary system cron calling the sweep, and the durable state
is the workflow store. What was left of #88 is arithmetic.

### What the runtime already gives, with no library

| #88's scope sketch | status |
|---|---|
| `scheduler.at(datetime, workflow)` | **native** — the delay to that instant |
| `scheduler.interval(duration, workflow)` | **native** — a resumed step arms its successor |
| `scheduler.cron(expr, workflow)` | the firing is native; parsing the expression is not |
| timezone handling | `std:time` carries zones through all its arithmetic |

Recurrence needed [#733](https://github.com/Masterplanner25/Nodus/issues/733)
first. A resumed step arming its own successor fired **exactly once**: the
successor was created mid-sweep, so orphan adoption reached it before the release
partition did, and adoption released its wait without resuming it — leaving the
run `running`, steps `pending`, unrecoverable, reporting success. Fixed, and the
recurrence measured across four processes.

---

## Why this one is not Python

`WHY_PYTHON_NOT_NODUS.md` says pure-logic packages are the migration frontier but
Python-first for now, and names concrete language gaps — "dynamic typing, no
first-class bytes, no substring/slice builtin". Its test is the Rule of Three:
**don't rewrite in Nodus until the rewrite is a win, not a fight.**

Two things make this the case that passes that test.

**The gap it names does not bind here.** Checked rather than assumed — full
cron-field parsing works today:

```
expr "*/15 2 * * 1-5"  ->  fields: 5
  minute field "*/15"  ->  step parts ["*", "15"]
  weekday "1-5" contains dash: true  ->  range 1 to 5  ->  as int: 6
```

`strings.split` covers what a slice builtin would be for, and `math.parse_int`
closes the rest.

**The consumer is the real argument.** Every pure-logic candidate that document
lists — `nodus-a2a`, `nodus-approvals`, `nodus-agent` — is consumed by a Python
host. This one's only caller is a `.nd` step body computing a `deadline_ms`:

```nodus
step park {
    return workflow_wait("tick", record {deadline_ms: sched.next_delay_ms("0 3 * * *"), on_timeout: "resume"})
}
```

A Python implementation would have to be bridged back into Nodus to be used at
all. *That* is the fight; writing it in Nodus is the win.

Verified rather than assumed, because this is exactly the position where
cross-module calls used to fail silently (#691, fixed in 5.9.0): a module
function called from inside a step body computes the delay and the schedule
fires.

---

## Public surface

| Function | Returns |
|---|---|
| `parse(expr)` | the five field sets plus `dom_any` / `dow_any`, or throws |
| `next_after(expr, dt)` | the next firing strictly after `dt`, or `nil` |
| `next(expr)` | `next_after(expr, time.now())` |
| `next_delay_ms(expr)` | milliseconds from now to the next firing |
| `after_ms/seconds/minutes/hours/days(n)` | a fixed interval from now |
| `delay_until(dt)` | milliseconds until `dt`, floored at 0 |
| `cron_weekday(dt)` | a datetime's cron day-of-week |

**A delay, not an instant.** `next_delay_ms` returns a duration because the
arming process and the sweeping process are different processes. An absolute
timestamp handed to the store would be re-read against whichever clock swept —
the class of defect #725 was filed for.

---

## Two decisions that are easy to get backwards

**The day fields are a union.** When *both* day-of-month and day-of-week are
restricted, standard cron matches a day if **either** does. `0 0 13 * 5` means
"the 13th, and every Friday" — not "Friday the 13th". Reading it as an
intersection produces a schedule that fires roughly a hundred times less often
and still looks like it works. Pinned by mutation: flipping the operator moves
the test case from 2026-09-04 to 2026-11-13, which is indeed a Friday the 13th.

**Day-of-week is numbered differently in the two systems.** Cron is
0=Sunday..6=Saturday; `std:time`'s `weekday` is 0=Monday..6=Sunday, Python's
convention. Converted in one named function, `cron_weekday`, because the failure
is a silent one-day shift on every weekly schedule. Removing the conversion turns
four test cases red, each off by exactly a day.

---

## Search strategy

`next_after` walks **days**, not minutes. A yearly schedule is half a million
minutes away and stepping those in the interpreter is not a plan; per candidate
day the work is bounded by the field sizes, so the worst case is a few thousand
cheap comparisons.

The horizon is 1500 days — four years — because February 29th is the one
legitimate schedule that can skip three consecutive years. A schedule that cannot
fire at all (`0 0 30 2 *`) returns `nil` rather than looping.

---

## Not implemented

`L`, `W`, `#`, `?`, `@yearly`-style nicknames, and seconds resolution. Each is
additive; none is half-implemented, and `parse` refuses what it does not
understand rather than accepting it and meaning something else.

Also out of scope: `nodus-sdk#5`, whether an APScheduler job in that bridge can
invoke a Nodus workflow. That is a question about that bridge, not about
schedules.

---

## Tests

26 cases in `packages/nodus-scheduler/tests/scheduler_test.nd`, run by
`tests/test_nodus_scheduler_package.py` so CI covers them. Every expected instant
is hand-computed and named in its case; the fixed origin is a Thursday, chosen so
the weekday conversion is load-bearing in most of the suite.

---

## Acceptance criteria before publishing

1. A repo of its own, and a row in `docs/ecosystem/README.md` — a package with no
   row there is invisible to the ecosystem count *and* to the drift sweep.
2. A decision on distribution. This is a `.nd` module, so PyPI is a poor fit and
   the Nodus registry is the right channel. The question is open, and is why this
   is a reference implementation rather than a release.
3. Somewhere to record its runtime floor. It needs **nodus-lang >= 5.9.0** —
   `on_timeout: "resume"` is 5.9.0, and recurrence additionally needs #733 —
   and **no mechanism currently tracks that for a `.nd` package**.
   `UNPUBLISHED_COMPANIONS` in `tools/check_downstream_constraints.py` is the
   obvious candidate and is the wrong one: it resolves *published PyPI* metadata,
   so it can neither read nor check a Nodus-registry module. Recorded as a gap
   rather than filed against the wrong tool, because the fix depends on (2).
