# Nodus v4.0 — Design Doc 02: Datetime API

**Phase:** 1 (design docs)
**Status:** Locked
**Implements:** Decision 6 (Datetime API Shape) from `00-phase-0-decisions.md`
**Date:** 2026-05-26
**Maintainer:** Shawn Knight (Masterplanner25)

---

## Problem statement

v4.0 ships datetime handling as a Tier 1 orchestration stdlib namespace.
Decision 6 (Phase 0) locked the high-level shape: aware datetimes only,
Unix epoch milliseconds internal, `std:time` namespace, chrono-style
format tokens, IANA timezone identifiers. This doc specifies the API
surface in implementable detail.

Datetime is the third capability stdlib namespace after HTTP and
subprocess. The use case is narrower (timestamps, scheduling intervals,
duration math, format-and-parse for API boundaries) but the correctness
ceiling is high: timezone handling, DST transitions, and calendar
arithmetic produce subtle bugs in code that ignores them.

The design optimizes for the common orchestration patterns (UTC
internally, timezone awareness at I/O boundaries, duration arithmetic
between timestamps) while making the edge cases (DST gaps, ambiguous
times, month-end clamping) explicit rather than silent.

---

## What Phase 0 already settled

From Decision 6:

- Aware datetimes only (no naive datetimes)
- Internal representation: Unix epoch ms as `int`
- `std:time` namespace
- Calendar operations as stdlib functions, not type methods
- Duration as separate type
- Chrono-style format tokens (`yyyy-MM-dd HH:mm:ss`)
- `time.now()` returns UTC; `time.now_in(zone)` returns specific zone
- Err records use `kind: "time_error"` with `category` field
  (`"parse_error"`, `"invalid_zone"`, `"out_of_range"`, `"ambiguous"`)

This doc resolves:

- Datetime construction function set
- Datetime accessors
- Equality and comparison semantics
- Duration construction and arithmetic
- Calendar operation function set
- DST and ambiguous time handling
- Format token specification
- Locale handling decision
- Strict vs lenient parsing
- Implementation substrate (`zoneinfo` + `tzdata`)

---

## API surface

### Datetime construction

Seven public constructors for datetime values:

```
time.now()
time.now_in(zone)
time.parse(string, format, zone?, options?)
time.from_iso8601(string)
time.from_http_date(string)
time.from_epoch_ms(ms, zone?)
time.at(year, month, day, hour, minute, second, ms, zone, options?)
```

**`time.now()`** — current moment, UTC zone. The orchestration default;
internal representation uses epoch ms regardless, but the zone presented
is UTC.

**`time.now_in(zone)`** — current moment, presented in the named zone.
The instant is the same as `time.now()`; only the zone differs. Use this
for human-readable timestamps in user-facing output.

**`time.parse(string, format, zone?, options?)`** — format-driven parse.
Format string uses chrono tokens (see Format Reference). Optional zone
defaults to UTC if the format string does not include zone information.
Options: `{strict: false}` for lenient parsing (default is strict),
`{on_invalid: "shift_forward" | "shift_backward"}` for invalid times,
`{on_ambiguous: "earliest" | "latest"}` for fall-back times.

**`time.from_iso8601(string)`** — parse ISO 8601 / RFC 3339 datetime
strings. Accepts `2026-05-26T14:30:00Z`, `2026-05-26T14:30:00-07:00`,
`2026-05-26T14:30:00.123+00:00`, etc. No format string required; the
parser handles the standard variations.

**`time.from_http_date(string)`** — parse HTTP-date format per RFC 7231
§ 7.1.1.1. Accepts `"Sun, 06 Nov 1994 08:49:37 GMT"` and the IMF-fixdate
variants. Useful for parsing `Date:` and `Last-Modified:` HTTP headers
without constructing format strings for the obscure format.

**`time.from_epoch_ms(ms, zone?)`** — construct from Unix epoch
milliseconds. Optional zone defaults to UTC. The instant is identical
regardless of zone; only presentation differs.

**`time.at(year, month, day, hour, minute, second, ms, zone, options?)`**
— explicit field-based construction. Zone is required (no naive
datetimes per Decision 6). Options: `{on_invalid, on_ambiguous}` for DST
edge cases.

### Datetime accessors

Datetime values are accessed via field-style methods:

| Accessor | Type | Range |
|---|---|---|
| `dt.year` | int | (e.g., 2026) |
| `dt.month` | int | 1-12 |
| `dt.day` | int | 1-31 |
| `dt.hour` | int | 0-23 |
| `dt.minute` | int | 0-59 |
| `dt.second` | int | 0-59 |
| `dt.ms` | int | 0-999 |
| `dt.weekday` | int | 0-6 (0=Monday per ISO 8601) |
| `dt.day_of_year` | int | 1-366 |
| `dt.zone` | string | IANA zone name (e.g., `"America/Phoenix"`, `"UTC"`) |
| `dt.epoch_ms` | int | Unix epoch milliseconds |
| `dt.is_dst` | bool | `true` if zone is currently in DST |

**Weekday convention:** ISO 8601 (Monday=0). Users wanting US convention
(Sunday=0) write `(dt.weekday + 1) % 7`. The trade-off is documented;
the choice favors international standard alignment over US familiarity.

Decision 6 specified "calendar ops as stdlib functions, not type
methods." Pure field accessors are not calendar operations — they read
existing fields. Calendar arithmetic (add months, find start of week)
is in the function surface below.

### Datetime comparison

Datetime values compare by instant (epoch_ms). Zones do not affect
equality or ordering.

```nodus
let a = time.now()
let b = time.now_in("America/Phoenix")  // same instant, different presentation
a == b   // true: same epoch_ms

let now = time.now()
let later = time.add(now, time.minutes(5))
now < later  // true
```

Operators supported: `==`, `!=`, `<`, `>`, `<=`, `>=`.

For zone-equality checks (rare), users compare `dt.zone == other.zone`
directly. There is no separate zone-aware comparison operator.

### Duration construction

Six granularity-specific constructors plus one diff function:

```
time.ms(n)
time.seconds(n)
time.minutes(n)
time.hours(n)
time.days(n)
time.weeks(n)
time.duration_between(dt1, dt2)
```

`time.duration_between(dt1, dt2)` returns the duration `dt2 - dt1` (can
be negative if `dt2 < dt1`).

**No `time.months(n)` or `time.years(n)`.** Months and years are
calendar concepts, not fixed durations: a month is 28-31 days, a year
is 365 or 366. Use calendar arithmetic functions (`time.add_months`,
`time.add_years`) instead.

### Duration accessors

| Accessor | Type | Description |
|---|---|---|
| `d.total_ms` | int | Duration in milliseconds (signed) |
| `d.total_seconds` | float | Duration in seconds (signed, fractional) |
| `d.total_minutes` | float | Duration in minutes (signed, fractional) |
| `d.total_hours` | float | Duration in hours (signed, fractional) |
| `d.total_days` | float | Duration in days (signed, fractional) |

Duration components are not decomposed by default (no `d.minutes_part`,
`d.seconds_part`). Users who need to format a duration as `"1h 30m 5s"`
use modular arithmetic on `d.total_ms`.

### Duration comparison

Durations compare by total_ms.

```nodus
let a = time.minutes(5)
let b = time.seconds(300)
a == b   // true

let a = time.minutes(5)
let b = time.minutes(10)
a < b    // true
```

### Calendar operations

```
time.add(dt, duration)
time.subtract(dt, duration)
time.add_days(dt, n)
time.add_months(dt, n)
time.add_years(dt, n)
time.start_of_day(dt)
time.end_of_day(dt)
time.start_of_week(dt)
time.start_of_month(dt)
time.start_of_year(dt)
time.to_zone(dt, zone)
time.to_utc(dt)
```

**`time.add(dt, duration)`** — add a fixed duration to a datetime. The
result preserves the datetime's zone. Returns a new datetime.

**`time.subtract(dt, duration)`** — subtract a duration. Equivalent to
`time.add(dt, time.duration_between(dt, dt) - duration)` but provided
for readability.

**`time.add_days(dt, n)`** — add N calendar days. This is NOT the same
as `time.add(dt, time.days(n))` across DST boundaries. Adding a
duration of 24 hours might cross a DST transition and produce an
unexpected hour; `time.add_days` operates on the calendar day field
directly and preserves the hour/minute/second.

**`time.add_months(dt, n)`** — add N months. Clamps to the last day of
the target month for invalid dates: `time.add_months(jan31, 1)` returns
February 28 (or 29 in a leap year). Negative `n` for past dates.

**`time.add_years(dt, n)`** — add N years. Clamps Feb 29 to Feb 28 in
non-leap target years.

**`time.start_of_day(dt)`** — datetime at 00:00:00.000 the same calendar
day, same zone.

**`time.end_of_day(dt)`** — datetime at 23:59:59.999 the same calendar
day, same zone.

**`time.start_of_week(dt)`** — datetime at 00:00:00 Monday of the
calendar week containing `dt`, same zone. ISO 8601 weekday convention
applies.

**`time.start_of_month(dt)`** — datetime at 00:00:00 the first day of
the calendar month, same zone.

**`time.start_of_year(dt)`** — datetime at 00:00:00 January 1 of the
calendar year, same zone.

**`time.to_zone(dt, zone)`** — same instant, different zone
presentation. The epoch_ms is unchanged.

**`time.to_utc(dt)`** — shortcut for `time.to_zone(dt, "UTC")`.

### Formatting

```
time.format(dt, format)
```

Format string uses the token reference below. Literal text wraps in
single quotes. Returns a string. Returns err if the format string is
invalid (`category: "parse_error"`).

```nodus
time.format(dt, "yyyy-MM-dd HH:mm:ss")
// "2026-05-26 14:30:00"

time.format(dt, "yyyy-MM-dd 'at' HH:mm")
// "2026-05-26 at 14:30"

time.format(dt, "EEEE, MMMM d, yyyy")
// "Tuesday, May 26, 2026"

time.format(dt, "yyyy-MM-dd'T'HH:mm:ssZZZZ")
// "2026-05-26T14:30:00-07:00"
```

### Quick serialization helpers

Three shortcut functions for common output formats:

```
time.to_iso8601(dt)
time.to_http_date(dt)
time.to_epoch_ms(dt)
```

**`time.to_iso8601(dt)`** — equivalent to
`time.format(dt, "yyyy-MM-dd'T'HH:mm:ss.SSSZZZZ")`. The standard wire
format for APIs.

**`time.to_http_date(dt)`** — formats per RFC 7231 § 7.1.1.1
(`"Sun, 06 Nov 1994 08:49:37 GMT"`). The dt is converted to UTC before
formatting (HTTP-date is always UTC by spec).

**`time.to_epoch_ms(dt)`** — equivalent to `dt.epoch_ms`. Provided as
a function for consistency with the `to_` family.

---

## DST and edge-case handling

DST transitions create two failure modes:

### Spring-forward gap (invalid time)

On a spring-forward day, an hour does not exist. In America/New_York
on 2026-03-08, the clock jumps from 02:00:00 directly to 03:00:00. The
time `02:30:00` on that date does not exist.

```nodus
// Default: returns err
time.at(2026, 3, 8, 2, 30, 0, 0, "America/New_York")
// err: time_error, category: "out_of_range"

// Opt in to shift behavior
time.at(2026, 3, 8, 2, 30, 0, 0, "America/New_York", {on_invalid: "shift_forward"})
// returns datetime at 03:30:00 (shifted past the gap)

time.at(2026, 3, 8, 2, 30, 0, 0, "America/New_York", {on_invalid: "shift_backward"})
// returns datetime at 01:30:00 (shifted before the gap)
```

### Fall-back ambiguous time

On a fall-back day, an hour repeats. In America/New_York on 2026-11-01,
the clock falls back from 02:00:00 EDT to 01:00:00 EST. The time
`01:30:00` on that date occurs twice.

```nodus
// Default: returns err
time.at(2026, 11, 1, 1, 30, 0, 0, "America/New_York")
// err: time_error, category: "ambiguous"

// Opt in to disambiguation
time.at(2026, 11, 1, 1, 30, 0, 0, "America/New_York", {on_ambiguous: "earliest"})
// returns 01:30:00 EDT (the first occurrence)

time.at(2026, 11, 1, 1, 30, 0, 0, "America/New_York", {on_ambiguous: "latest"})
// returns 01:30:00 EST (the second occurrence)
```

### Calendar arithmetic across DST

`time.add(dt, time.hours(24))` adds 24 fixed hours. Across a DST
boundary, the result may be on a different calendar day or hour than
expected.

`time.add_days(dt, 1)` adds 1 calendar day, preserving the hour/minute/
second. Across a DST boundary, the result is on the next calendar day
at the same wall-clock time (which may be a different number of
absolute hours away).

Choose the right function for the use case:

- **Use `time.add(dt, time.hours(N))` for fixed-duration arithmetic.**
  Scheduling, intervals, performance timing.
- **Use `time.add_days(dt, N)` for calendar arithmetic.** "Same time
  tomorrow," "appointment in 3 days at 9am."

This distinction is one of the most common datetime bugs in production
code. The design surfaces both functions explicitly to make the choice
deliberate.

### Calendar arithmetic edge cases (month-end)

Adding months to a date near the end of a month requires clamping
when the target month has fewer days:

```nodus
let jan31 = time.at(2026, 1, 31, 0, 0, 0, 0, "UTC")
time.add_months(jan31, 1)
// 2026-02-28 (clamped; February has 28 days in 2026)

time.add_months(jan31, 13)
// 2027-02-28 (still clamped)

time.add_years(time.at(2024, 2, 29, 0, 0, 0, 0, "UTC"), 1)
// 2025-02-28 (clamped; 2025 is not a leap year)
```

Clamping matches the behavior of Python's dateutil, Java's
`java.time.LocalDate.plusMonths`, JavaScript's Temporal proposal, and
Rust's chrono. The choice aligns with ecosystem convention.

The alternative (rolling forward to the next month) is rejected: it
silently changes the calendar month, which is almost always a bug
rather than intended behavior.

---

## Format token reference

| Token | Meaning | Example output |
|---|---|---|
| `yyyy` | 4-digit year | `2026` |
| `yy` | 2-digit year | `26` |
| `MMMM` | Full month name | `May` |
| `MMM` | Short month name | `May` |
| `MM` | 2-digit month | `05` |
| `M` | Month, no leading zero | `5` |
| `dd` | 2-digit day of month | `26` |
| `d` | Day of month | `26` |
| `EEEE` | Full weekday name | `Tuesday` |
| `EEE` | Short weekday name | `Tue` |
| `HH` | 2-digit 24-hour | `14` |
| `H` | 24-hour, no leading zero | `14` |
| `hh` | 2-digit 12-hour | `02` |
| `h` | 12-hour, no leading zero | `2` |
| `mm` | 2-digit minute | `30` |
| `m` | Minute, no leading zero | `30` |
| `ss` | 2-digit second | `00` |
| `s` | Second, no leading zero | `0` |
| `SSS` | 3-digit milliseconds | `123` |
| `a` | AM/PM marker | `PM` |
| `Z` | Numeric timezone offset | `-0700` |
| `ZZZZ` | Full timezone offset | `-07:00` |
| `z` | Timezone abbreviation | `MST` |
| `zzzz` | Full timezone name | `Mountain Standard Time` |
| `VV` | IANA zone ID | `America/Phoenix` |

**Literal text:** wrap in single quotes. Two single quotes (`''`) escape
a literal single quote.

```
"yyyy-MM-dd 'at' HH:mm"          → "2026-05-26 at 14:30"
"yyyy-MM-dd''yy"                  → "2026-05-26'26"
```

**Format token errors:** invalid format strings produce err with
`category: "parse_error"` at format time. The library validates the
format string when first used.

---

## Locale handling

Format tokens that produce names (`MMMM`, `MMM`, `EEEE`, `EEE`, `a`)
output English by default in v4.0. No locale option is supported.

This is intentional scoping. Locale handling adds significant
complexity (locale data, fallback chains, locale-dependent number
formatting, RTL considerations) for marginal benefit to the
orchestration DSL use case. Orchestration scripts overwhelmingly
produce English-format timestamps for logs, APIs, and internal
records.

If real demand surfaces (multiple issues with concrete use cases),
a `locale` option is added as v4.x additive. Reconsideration trigger:
locale support requested in 10+ distinct issues across different use
cases.

---

## Parsing strictness

`time.parse` defaults to strict matching. Each format token expects an
exact width match:

```nodus
// Strict: MM token expects 2 digits
time.parse("2026-5-26", "yyyy-MM-dd")
// err: time_error, category: "parse_error", message includes
// "expected 2 digits for MM, got 1"

// Strict accepts the matching width
time.parse("2026-05-26", "yyyy-MM-dd")
// returns datetime

// Lenient: accepts 1 or 2 digits for variable-width tokens
time.parse("2026-5-26", "yyyy-MM-dd", "UTC", {strict: false})
// returns datetime
```

Strict-by-default catches a common class of bugs (sloppy date parsing
producing wrong years or months). Users who explicitly want lenient
parsing opt in.

ISO 8601 / RFC 3339 (parsed by `time.from_iso8601`) uses fixed-width
fields by spec. The strict-by-default behavior aligns with the most
common wire format.

---

## Err record shape

All `std:time` errors return err records with this shape:

```nodus
err {
    kind: "time_error",
    message: string,
    path: ..., line: ..., column: ..., stack: ...,
    payload: {
        category: string,
        input: string or nil,     # the input that caused the error (parse, at)
        format: string or nil,    # the format string (parse only)
        zone: string or nil,      # the zone name (invalid_zone)
        field: string or nil      # which field was out of range (out_of_range)
    }
}
```

**Category enumeration (four values):**

| Category | When emitted |
|---|---|
| `"parse_error"` | Invalid format string or input that doesn't match format; ISO 8601 / HTTP-date format mismatch |
| `"invalid_zone"` | IANA zone name not recognized |
| `"out_of_range"` | Field value out of range (month 13, day 32) or invalid time (DST gap) |
| `"ambiguous"` | Time falls in fall-back hour with no disambiguation option |

---

## Implementation outline

### Substrate: zoneinfo + tzdata fallback

`std:time` uses Python's stdlib `zoneinfo` module (Python 3.9+) for
IANA zone resolution. When system tzdata is unavailable or outdated,
the bundled `tzdata` package provides a fallback.

```toml
[project]
dependencies = ["httpx>=0.27,<1", "tzdata>=2024.1"]
```

Reasoning:

1. `zoneinfo` is the stdlib API for IANA timezones; mature and
   well-tested.
2. System tzdata varies by deployment: outdated on minimal containers,
   missing on some Windows configurations, unpredictable on macOS.
3. Bundled `tzdata` ensures consistent behavior across deployment
   environments. ~500KB cost.
4. `zoneinfo` automatically uses bundled `tzdata` when system tzdata
   is missing or outdated.

### Internal representation

Datetimes stored as a record:

```python
{
    "epoch_ms": int,
    "zone": str,
}
```

The zone is preserved for presentation (formatting, accessor methods).
Arithmetic operations work on `epoch_ms`. Field access (e.g., `dt.year`)
computes from `epoch_ms` and `zone` via `zoneinfo`.

Durations stored as a record:

```python
{
    "total_ms": int,
}
```

Signed; negative values represent durations going backward.

### Format token engine

A standard chrono-style format parser. Format strings are tokenized
into a list of (token, literal-text) pairs. The engine:

- Validates the format string at parse time
- Caches tokenized format strings (most orchestration scripts reuse
  formats)
- Produces output by iterating tokens against a datetime

The token set is closed (no extension API in v4.0). Future additions
are additive (new tokens that don't conflict with existing ones).

### ISO 8601 / RFC 3339 parser

`time.from_iso8601` accepts the following variations:

- `2026-05-26T14:30:00Z`
- `2026-05-26T14:30:00+00:00`
- `2026-05-26T14:30:00.123Z`
- `2026-05-26T14:30:00.123456Z` (sub-millisecond precision truncated to ms)
- `2026-05-26T14:30:00-07:00`
- `2026-05-26 14:30:00Z` (space separator accepted)

Outside this set, returns err. The parser rejects:
- Missing zone information (no Z, no offset)
- Invalid month/day combinations
- Years outside the supported range (1900-2099 for v4.0; matches
  zoneinfo's practical range)

### HTTP-date parser

`time.from_http_date` accepts:

- IMF-fixdate: `"Sun, 06 Nov 1994 08:49:37 GMT"` (preferred)
- RFC 850 obsolete: `"Sunday, 06-Nov-94 08:49:37 GMT"` (accepted)
- asctime obsolete: `"Sun Nov  6 08:49:37 1994"` (accepted)

All three formats are required by RFC 7231 § 7.1.1.1 for HTTP/1.1
clients. Output is always UTC zone.

---

## Open implementation questions for Phase 3B

1. **Year range support.** zoneinfo supports years roughly 1-9999, but
   DST rules for years before 1900 or after 2100 may be undefined for
   specific zones. Tentative: support 1900-2099 explicitly; outside
   that range, return err with `category: "out_of_range"`. Reconsider
   if users need historical or far-future dates.

2. **Performance of zone lookups.** zoneinfo creates new ZoneInfo
   objects on demand; the C implementation caches them. Verify caching
   behavior is sufficient for orchestration workloads that repeatedly
   create datetimes in the same zone.

3. **Thread safety of zoneinfo cache.** ZoneInfo objects are documented
   as thread-safe to read but not to construct. The Nodus VM is
   single-threaded by default; verify no thread-safety issues if Nodus
   is embedded in a multi-threaded host.

4. **Format string caching.** Format strings should be tokenized once
   per unique string. Implement an LRU cache or weakref dict; cap at
   ~100 entries to bound memory.

5. **Leap second handling.** zoneinfo and Unix epoch ms do not represent
   leap seconds (epoch ms assumes 86400 seconds per day always). Most
   orchestration use cases don't care. Document the limitation;
   reconsider only if a use case surfaces.

6. **`time.from_iso8601` precision.** Spec allows arbitrary fractional-
   second precision. Tentative: truncate (don't round) to milliseconds.
   Document explicitly.

---

## Capability surface ceiling

Per the capabilities-not-orchestration principle, the following are NOT
included in v4.0:

- **Calendar libraries beyond basic arithmetic.** Recurring events
  ("every Tuesday"), schedule patterns, business-day calculations,
  holiday detection. These are orchestration concerns; workflows
  compose datetime primitives into schedules. Possibly a `nodus-schedule`
  registry library in v5.x.

- **Locale-aware formatting.** English-only; reconsider in v4.x if real
  demand.

- **Astronomical / non-Gregorian calendars.** Julian dates, lunar
  calendars, Islamic/Hebrew/Buddhist calendars. Out of scope; would
  require substantial additional libraries.

- **Sub-millisecond precision.** Internal representation is millisecond
  precision. Microsecond and nanosecond use cases (high-precision
  benchmarking, financial timestamps) are out of scope. Possibly
  `nodus-precise-time` registry library if demand emerges.

- **Time series helpers.** Bucketing into intervals, downsampling,
  resampling. These are data-processing concerns; out of scope per
  orchestration DSL positioning.

- **Cron expression parsing.** Cron is a scheduling DSL of its own;
  ships with `nodus-scheduler` (v5.0 Tier 2 library, already filed).

### Reconsideration triggers

`std:time` scope expands if:

- Real user issues request additions (10+ across distinct use cases)
- A v4.0 library implementation requires a primitive only cleanly
  provided by `std:time`
- Locale support requested specifically (separate trigger from above)

---

## MCP and A2A consumer validation

### nodus-mcp consumer needs

MCP uses datetime in several places:

- ✓ Timestamps in log messages: `time.now()` for epoch ms; format with
  `time.to_iso8601(dt)` for human-readable output
- ✓ Cache TTL calculations: `time.add(dt, time.minutes(N))` for expiry
  timestamps, `time.duration_between(now, expiry)` for remaining time
- ✓ Request/response timing: `dt.epoch_ms` for high-resolution
  timestamps

### nodus-a2a consumer needs

A2A's spec uses ISO 8601 timestamps in several Task and Message fields:

- ✓ `time.from_iso8601(string)` for parsing incoming task timestamps
- ✓ `time.to_iso8601(dt)` for serializing outgoing timestamps
- ✓ Task status transitions: time arithmetic for SLA tracking
- ✓ Push notification scheduling: future datetimes via `time.add` /
  `time.add_days`

Both libraries' use cases are covered by the locked API surface.

---

## Migration impact

`std:time` is a new namespace in v4.0. No migration from v3.x.

---

## Bytecode impact

**No new opcodes required. `BYTECODE_VERSION` stays at 4.**

`std:time` is implemented as Python-side builtin functions registered
through the existing builtin registry. Datetime and duration values are
Nodus records (existing type) with methods that compute from epoch_ms
and zone. User code calls all `std:time` functions via the existing
`CALL_BUILTIN` opcode.

The frozen-bytecode contract from v1.0 is preserved by this design.
Compiled v3.x `.ndbc` files remain loadable in the v4.0 VM.

---

## Cross-references

- `docs/design/v4/00-phase-0-decisions.md` Decision 6 (datetime API)
- `docs/design/v4/01-http-api.md` (sibling design; HTTP Date header
  uses `time.from_http_date` and `time.to_http_date`)
- `docs/design/v4/04-subprocess-api.md` (sibling design; subprocess
  duration tracking uses `duration_ms`)
- `docs/language/LANGUAGE_VISION.md` principle #6 (capabilities not
  orchestration; scheduling/recurring events are out of scope)
- `docs/language/DESIGN.md` § "Capability surfaces stay narrow"
- `docs/language/STYLE_GUIDE.md` § "Retry, backoff, and recovery"
- `docs/governance/TECH_DEBT.md` (Phase 3B open questions appended)

---

## Phase 3B implementation handoff

When Phase 3B begins (time namespace implementation), the following
artifacts are ready:

1. This design doc (`02-datetime-api.md`)
2. Decision 6 (Phase 0)
3. Six open implementation questions enumerated above
4. Substrate locked: `zoneinfo` (Python 3.9+ stdlib) + `tzdata` package
5. Test surface to cover:
   - All 7 datetime constructors
   - All datetime accessors and comparison
   - All 6 duration constructors plus `duration_between`
   - All 12 calendar operation functions
   - Format and parse for all format tokens
   - DST edge cases: spring-forward gap, fall-back ambiguous time
   - Calendar edge cases: month-end clamping (Jan 31 + 1 month, Feb 29
     + 1 year)
   - ISO 8601 / RFC 3339 parser variations
   - HTTP-date parser (all three formats per RFC 7231)
   - Strict vs lenient parsing
   - Year-range boundary (1900, 2099)
   - Cross-zone arithmetic (adding hours vs days across DST)
   - Err categories: parse_error, invalid_zone, out_of_range, ambiguous

Estimated implementation effort: 2-3 days focused work for full
coverage including tests. DST edge cases and format token engine are
the most complex; basic arithmetic is straightforward.

---

**Phase 1 doc 02-datetime-api.md: COMPLETE.**
