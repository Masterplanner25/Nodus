# nodus-scheduler

Cron, interval, and calendar schedules for Nodus workflows — as **pure
functions**. Answers one question:

> Given a schedule, when does it next fire?

Nothing here parks a run, writes to a store, or executes anything. That is
deliberate, and it is the whole design: since **#176** the runtime already owns
the firing, so a scheduler library does not need a daemon.

Status: reference implementation (#88). Not published.

## How a schedule actually runs

`workflow_wait(..., {on_timeout: "resume"})` turns a deadline into a schedule.
The run parks, the process exits, and a later `nodus workflow sweep` releases the
wait and carries the workflow on. A resumed step that arms its successor recurs
indefinitely.

```nodus
import "../src/scheduler.nd" as sched

workflow nightly {
    step park {
        return workflow_wait("tick", record {deadline_ms: sched.next_delay_ms("0 3 * * *"), on_timeout: "resume"})
    }
    step work after park {
        // ... the actual job ...
        run_workflow(nightly)          // arm tomorrow's
        return "rearmed"
    }
}
```

Then, from an ordinary system cron — the only daemon involved:

```
*/5 * * * *   cd /srv/jobs && nodus workflow sweep
```

The sweep's period bounds **latency**, not correctness: each run's own
`deadline_ms` decides what is due, so a five-minute cron does not turn a 03:00
job into a 03:05 job by more than the sweep interval.

Measured, three separate sweep processes:

```
sweep 1: 'beat at 2026-09-03T01:26:03.860+00:00'
sweep 2: 'beat at 2026-09-03T01:26:08.111+00:00'
sweep 3: 'beat at 2026-09-03T01:26:10.959+00:00'
```

## API

| Function | Returns |
|---|---|
| `parse(expr)` | the field sets, or throws |
| `next_after(expr, dt)` | the next firing strictly after `dt`, or `nil` |
| `next(expr)` | `next_after(expr, now)` |
| `next_delay_ms(expr)` | milliseconds from now to the next firing — the `deadline_ms` |
| `after_ms/seconds/minutes/hours/days(n)` | a fixed interval from now |
| `delay_until(dt)` | milliseconds until `dt`, floored at 0 |
| `cron_weekday(dt)` | a `std:time` datetime's cron day-of-week |

## Cron syntax

Five fields: `minute hour day-of-month month day-of-week`.

Per field: `*`, `N`, `A-B`, `*/N`, `A-B/N`, `N/M`, and comma-separated lists of
those. Day-of-week is `0-7` with both `0` and `7` meaning Sunday.

Two behaviours worth stating, because getting either wrong produces a schedule
that still looks like it works:

- **The day fields are a union.** When *both* day-of-month and day-of-week are
  restricted, a day matches if **either** does — standard cron. So
  `0 0 13 * 5` is "the 13th, and every Friday", not "Friday the 13th". Reading it
  as an intersection fires roughly a hundred times less often. (Verified by
  mutation: flipping it moves the test case from 2026-09-04 to 2026-11-13, which
  is a Friday the 13th.)
- **`N` and `N/M` differ.** `5` is minute 5 alone; `5/20` is 5, 25, 45 — the bare
  value becomes the *start* of a range once a step is given.

Not supported: `L`, `W`, `#`, `?`, `@yearly`-style nicknames, and seconds. Each
would be additive; none is implemented rather than half-implemented.

## Intervals are not cron

`*/5` is wall-clock aligned — it fires at :00, :05, :10, so every job armed with
it stampedes together. `after_minutes(5)` is five minutes from *now*. Both are
useful; they are not substitutes, which is why both exist.

## Running the tests

```
cd packages/nodus-scheduler
nodus test tests/scheduler_test.nd
```

26 cases. `tests/test_nodus_scheduler_package.py` in the repo suite runs the same
file, so CI covers it.

Every expected instant in the suite is hand-computed and named in its case, and
the fixed origin is a **Thursday** — cron day-of-week 4, `std:time` weekday 3.
That off-by-one shifts every weekly schedule by a day and still looks like a
working schedule, so it gets its own assertion.

## Why this is written in Nodus

Every other pure-logic candidate in `docs/ecosystem/WHY_PYTHON_NOT_NODUS.md` is
consumed by a Python host. This one's only caller is a `.nd` step body computing
a `deadline_ms`, so a Python implementation would have to be bridged back into
Nodus to be usable at all. Full reasoning, and the measurements behind it, in
`docs/ecosystem/NODUS_SCHEDULER.md`.

One consequence to know before editing: `nodus fmt` demotes a same-line trailing
comment onto its own line, and the result does not survive a second pass — so
`fmt` can write a file that `fmt --check` then rejects (issue 739). Keep comments
on their own line and it does not arise.
