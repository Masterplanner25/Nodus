"""std:time — datetime and duration builtins for Nodus VM."""

import calendar
import re
import time as _sys_time
from datetime import datetime as _dt, timezone as _tz, timedelta as _td
from email.utils import parsedate_to_datetime as _parsedate_http
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from nodus.vm.vm import Record

_UTC = ZoneInfo("UTC")
_YEAR_MIN = 1900
_YEAR_MAX = 2099

_MONTH_FULL = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]
_MONTH_SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_WEEKDAY_FULL = [
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
]
_WEEKDAY_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# Format tokens ordered longest-first for greedy tokenizing
_FMT_TOKENS = [
    "ZZZZ", "zzzz", "MMMM", "EEEE", "yyyy", "SSS",
    "EEE", "MMM", "VV", "HH", "hh", "mm", "ss", "yy",
    "MM", "dd", "H", "h", "m", "s", "M", "d", "Z", "z", "a",
]


@lru_cache(maxsize=64)
def _get_zone(zone_name: str):
    try:
        return ZoneInfo(zone_name)
    except (ZoneInfoNotFoundError, KeyError):
        return None


@lru_cache(maxsize=128)
def _tokenize_fmt(fmt: str) -> tuple:
    """Return tuple of (kind, value) pairs where kind is 'token' or 'literal'."""
    tokens = []
    i = 0
    while i < len(fmt):
        if fmt[i] == "'":
            j = i + 1
            chars = []
            while j < len(fmt):
                if fmt[j] == "'":
                    if j + 1 < len(fmt) and fmt[j + 1] == "'":
                        chars.append("'")
                        j += 2
                    else:
                        j += 1
                        break
                else:
                    chars.append(fmt[j])
                    j += 1
            tokens.append(("literal", "".join(chars)))
            i = j
        else:
            matched = False
            for tok in _FMT_TOKENS:
                if fmt[i:i + len(tok)] == tok:
                    tokens.append(("token", tok))
                    i += len(tok)
                    matched = True
                    break
            if not matched:
                tokens.append(("literal", fmt[i]))
                i += 1
    return tuple(tokens)


_EPOCH_UTC = _dt(1970, 1, 1, tzinfo=_tz.utc)


def _local_from_epoch_ms(epoch_ms: int, tz) -> _dt:
    utc = _EPOCH_UTC + _td(milliseconds=epoch_ms)
    return utc.astimezone(tz)


def _utc_offset_parts(local: _dt):
    off = local.utcoffset()
    total_s = int(off.total_seconds())
    sign = "+" if total_s >= 0 else "-"
    total_s = abs(total_s)
    return sign, total_s // 3600, (total_s % 3600) // 60


def _render_fmt(fmt_tokens: tuple, local: _dt, tz) -> str:
    parts = []
    sign, h_off, m_off = _utc_offset_parts(local)
    for kind, val in fmt_tokens:
        if kind == "literal":
            parts.append(val)
            continue
        tok = val
        if tok == "yyyy":
            parts.append(f"{local.year:04d}")
        elif tok == "yy":
            parts.append(f"{local.year % 100:02d}")
        elif tok == "MMMM":
            parts.append(_MONTH_FULL[local.month - 1])
        elif tok == "MMM":
            parts.append(_MONTH_SHORT[local.month - 1])
        elif tok == "MM":
            parts.append(f"{local.month:02d}")
        elif tok == "M":
            parts.append(str(local.month))
        elif tok == "dd":
            parts.append(f"{local.day:02d}")
        elif tok == "d":
            parts.append(str(local.day))
        elif tok == "EEEE":
            parts.append(_WEEKDAY_FULL[local.weekday()])
        elif tok == "EEE":
            parts.append(_WEEKDAY_SHORT[local.weekday()])
        elif tok == "HH":
            parts.append(f"{local.hour:02d}")
        elif tok == "H":
            parts.append(str(local.hour))
        elif tok == "hh":
            h12 = local.hour % 12 or 12
            parts.append(f"{h12:02d}")
        elif tok == "h":
            parts.append(str(local.hour % 12 or 12))
        elif tok == "mm":
            parts.append(f"{local.minute:02d}")
        elif tok == "m":
            parts.append(str(local.minute))
        elif tok == "ss":
            parts.append(f"{local.second:02d}")
        elif tok == "s":
            parts.append(str(local.second))
        elif tok == "SSS":
            parts.append(f"{local.microsecond // 1000:03d}")
        elif tok == "a":
            parts.append("AM" if local.hour < 12 else "PM")
        elif tok == "Z":
            parts.append(f"{sign}{h_off:02d}{m_off:02d}")
        elif tok == "ZZZZ":
            parts.append(f"{sign}{h_off:02d}:{m_off:02d}")
        elif tok in ("z", "zzzz"):
            parts.append(local.tzname() or "UTC")
        elif tok == "VV":
            parts.append(getattr(tz, "key", "UTC"))
        else:
            parts.append(tok)
    return "".join(parts)


def _token_parse_regex(tok: str, strict: bool) -> str | None:
    """Return a regex group string for a format token (None = consume, don't capture)."""
    if tok == "yyyy": return r"\d{4}"
    if tok == "yy": return r"\d{2}"
    if tok == "MMMM": return "|".join(_MONTH_FULL)
    if tok == "MMM": return "|".join(_MONTH_SHORT)
    if tok == "MM": return r"\d{2}" if strict else r"\d{1,2}"
    if tok == "M": return r"\d{1}" if strict else r"\d{1,2}"
    if tok == "dd": return r"\d{2}" if strict else r"\d{1,2}"
    if tok == "d": return r"\d{1}" if strict else r"\d{1,2}"
    if tok == "EEEE": return "|".join(_WEEKDAY_FULL)
    if tok == "EEE": return "|".join(_WEEKDAY_SHORT)
    if tok == "HH": return r"\d{2}" if strict else r"\d{1,2}"
    if tok == "H": return r"\d{1,2}"
    if tok == "hh": return r"\d{2}" if strict else r"\d{1,2}"
    if tok == "h": return r"\d{1,2}"
    if tok == "mm": return r"\d{2}" if strict else r"\d{1,2}"
    if tok == "m": return r"\d{1,2}"
    if tok == "ss": return r"\d{2}" if strict else r"\d{1,2}"
    if tok == "s": return r"\d{1,2}"
    if tok == "SSS": return r"\d{3}"
    if tok == "a": return r"AM|PM"
    if tok == "Z": return r"[+-]\d{4}"
    if tok == "ZZZZ": return r"[+-]\d{2}:\d{2}|Z"
    if tok in ("z", "zzzz"): return r"[A-Z][A-Za-z0-9_/+-]*"
    if tok == "VV": return r"[A-Za-z][A-Za-z0-9_/+-]*"
    return None


@lru_cache(maxsize=64)
def _compile_parse_pattern(fmt_tokens: tuple, strict: bool):
    """Build a compiled regex and group-to-token mapping for parsing."""
    parts = []
    groups = []  # list of tokens in order of capture group
    for kind, val in fmt_tokens:
        if kind == "literal":
            parts.append(re.escape(val))
        else:
            grp = _token_parse_regex(val, strict)
            if grp is not None:
                parts.append(f"({grp})")
                groups.append(val)
    pattern = "^" + "".join(parts) + "$"
    return re.compile(pattern), groups


def register(vm, registry) -> None:
    """Register time_* builtins onto the registry."""

    # ── Error helpers ────────────────────────────────────────────────
    def _time_err(category, message, *, input=None, fmt=None, zone=None, field=None):
        return vm.make_err(
            "time_error",
            message,
            payload={
                "category": category,
                "input": input,
                "format": fmt,
                "zone": zone,
                "field": field,
            },
        )

    def _resolve_zone(zone_name):
        if zone_name is None:
            return _UTC, "UTC", None
        if not isinstance(zone_name, str):
            vm.runtime_error("type", "time: zone must be a string")
        tz = _get_zone(zone_name)
        if tz is None:
            return None, None, _time_err("invalid_zone", f"unknown timezone: {zone_name!r}", zone=zone_name)
        return tz, zone_name, None

    # ── Record factories ─────────────────────────────────────────────
    def _make_dt(epoch_ms: int, zone_name: str) -> Record:
        tz = _get_zone(zone_name)
        local = _local_from_epoch_ms(epoch_ms, tz)
        dst = local.dst()
        return Record({
            "epoch_ms": epoch_ms,
            "zone": zone_name,
            "year": local.year,
            "month": local.month,
            "day": local.day,
            "hour": local.hour,
            "minute": local.minute,
            "second": local.second,
            "ms": local.microsecond // 1000,
            "weekday": local.weekday(),
            "day_of_year": local.timetuple().tm_yday,
            "is_dst": bool(dst and dst.total_seconds() != 0),
        }, kind="datetime")

    def _make_dur(total_ms: int) -> Record:
        return Record({
            "total_ms": total_ms,
            "total_seconds": total_ms / 1000.0,
            "total_minutes": total_ms / 60_000.0,
            "total_hours": total_ms / 3_600_000.0,
            "total_days": total_ms / 86_400_000.0,
        }, kind="duration")

    def _require_dt(val, fname):
        if not isinstance(val, Record) or val.kind != "datetime":
            vm.runtime_error("type", f"{fname}: expected datetime, got {vm.builtin_type(val)}")

    def _require_dur(val, fname):
        if not isinstance(val, Record) or val.kind != "duration":
            vm.runtime_error("type", f"{fname}: expected duration, got {vm.builtin_type(val)}")

    def _to_py_int(v, name):
        if isinstance(v, float) and v.is_integer():
            return int(v)
        if isinstance(v, int) and not isinstance(v, bool):
            return v
        vm.runtime_error("type", f"time: {name} must be an integer")

    # ── DST-aware construction helper ────────────────────────────────
    def _construct_aware(year, month, day, hour, minute, second, ms_val, zone_name, options):
        tz = _get_zone(zone_name)
        on_invalid = None
        on_ambiguous = None
        if isinstance(options, dict):
            on_invalid = options.get("on_invalid")
            on_ambiguous = options.get("on_ambiguous")

        micro = ms_val * 1000
        try:
            naive = _dt(year, month, day, hour, minute, second, micro)
        except ValueError as exc:
            return _time_err("out_of_range", str(exc), field="day")

        fold0 = naive.replace(tzinfo=tz, fold=0)
        fold1 = naive.replace(tzinfo=tz, fold=1)
        utc_f0 = fold0.astimezone(_tz.utc)
        utc_f1 = fold1.astimezone(_tz.utc)
        em0 = int((utc_f0 - _EPOCH_UTC).total_seconds() * 1000)
        em1 = int((utc_f1 - _EPOCH_UTC).total_seconds() * 1000)

        if em0 == em1:
            return _make_dt(em0, zone_name)

        # Distinguish gap (spring-forward) from fold (fall-back) by round-trip check
        req = (hour, minute, second)
        rt0 = _local_from_epoch_ms(em0, tz)
        rt1 = _local_from_epoch_ms(em1, tz)
        rt0_hms = (rt0.hour, rt0.minute, rt0.second)
        rt1_hms = (rt1.hour, rt1.minute, rt1.second)

        if rt0_hms != req and rt1_hms != req:
            # Spring-forward gap: time doesn't exist
            ts_str = f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}"
            if on_invalid == "shift_forward":
                return _make_dt(em0, zone_name)
            if on_invalid == "shift_backward":
                return _make_dt(em1, zone_name)
            return _time_err("out_of_range",
                             f"invalid time {ts_str!r} in {zone_name!r} (spring-forward gap)",
                             zone=zone_name)
        else:
            # Fall-back fold: time is ambiguous
            ts_str = f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}"
            if on_ambiguous == "earliest":
                return _make_dt(em0, zone_name)
            if on_ambiguous == "latest":
                return _make_dt(em1, zone_name)
            return _time_err("ambiguous",
                             f"ambiguous time {ts_str!r} in {zone_name!r} (fall-back overlap)",
                             zone=zone_name)

    # ── Constructors ─────────────────────────────────────────────────
    def builtin_time_now():
        epoch_ms = int(_sys_time.time() * 1000)
        return _make_dt(epoch_ms, "UTC")

    def builtin_time_now_in(zone_name):
        tz, zn, err = _resolve_zone(zone_name)
        if err is not None:
            return err
        epoch_ms = int(_sys_time.time() * 1000)
        return _make_dt(epoch_ms, zn)

    def builtin_time_from_epoch_ms(ms, zone_name=None):
        ms = _to_py_int(ms, "ms")
        tz, zn, err = _resolve_zone(zone_name)
        if err is not None:
            return err
        return _make_dt(ms, zn)

    def builtin_time_at(year, month, day, hour, minute, second, ms, zone_name, options=None):
        year = _to_py_int(year, "year")
        month = _to_py_int(month, "month")
        day = _to_py_int(day, "day")
        hour = _to_py_int(hour, "hour")
        minute = _to_py_int(minute, "minute")
        second = _to_py_int(second, "second")
        ms = _to_py_int(ms, "ms")

        if not isinstance(zone_name, str):
            vm.runtime_error("type", "time.at: zone must be a string")

        if not (_YEAR_MIN <= year <= _YEAR_MAX):
            return _time_err("out_of_range", f"year {year} out of supported range [{_YEAR_MIN}, {_YEAR_MAX}]", field="year")
        if not (1 <= month <= 12):
            return _time_err("out_of_range", f"month {month} out of range [1, 12]", field="month")
        max_day = calendar.monthrange(year, month)[1]
        if not (1 <= day <= max_day):
            return _time_err("out_of_range", f"day {day} out of range [1, {max_day}]", field="day")
        if not (0 <= hour <= 23):
            return _time_err("out_of_range", f"hour {hour} out of range [0, 23]", field="hour")
        if not (0 <= minute <= 59):
            return _time_err("out_of_range", f"minute {minute} out of range [0, 59]", field="minute")
        if not (0 <= second <= 59):
            return _time_err("out_of_range", f"second {second} out of range [0, 59]", field="second")
        if not (0 <= ms <= 999):
            return _time_err("out_of_range", f"ms {ms} out of range [0, 999]", field="ms")

        tz, zn, err = _resolve_zone(zone_name)
        if err is not None:
            return err

        return _construct_aware(year, month, day, hour, minute, second, ms, zn, options)

    def builtin_time_from_iso8601(s):
        if not isinstance(s, str):
            vm.runtime_error("type", "time.from_iso8601: expected a string")
        # Accept: 2026-05-26T14:30:00Z, 2026-05-26T14:30:00+00:00, space sep, sub-ms
        s_norm = s.strip().replace(" ", "T")
        # Regex: yyyy-MM-ddTHH:mm:ss[.fff][Z|+HH:MM|-HH:MM]
        _ISO_RE = re.compile(
            r"^(\d{4})-(\d{2})-(\d{2})[T](\d{2}):(\d{2}):(\d{2})"
            r"(?:\.(\d+))?"
            r"(Z|[+-]\d{2}:\d{2}|[+-]\d{4})$"
        )
        m = _ISO_RE.match(s_norm)
        if not m:
            return _time_err("parse_error", f"invalid ISO 8601 string: {s!r}", input=s)
        year, month, day, hour, minute, second = (int(m.group(i)) for i in range(1, 7))
        frac_str = m.group(7)
        ms_val = 0
        if frac_str:
            ms_val = int((frac_str + "000")[:3])  # truncate to ms
        tz_str = m.group(8)
        if tz_str == "Z":
            utc_off = 0
        else:
            sign = 1 if tz_str[0] == "+" else -1
            t = tz_str[1:].replace(":", "")
            utc_off = sign * (int(t[:2]) * 3600 + int(t[2:4]) * 60)

        if not (_YEAR_MIN <= year <= _YEAR_MAX):
            return _time_err("out_of_range", f"year {year} out of range", input=s, field="year")
        if not (1 <= month <= 12):
            return _time_err("out_of_range", f"month {month} out of range", input=s, field="month")

        # Build naive UTC datetime
        try:
            naive_local = _dt(year, month, day, hour, minute, second, ms_val * 1000)
        except ValueError as exc:
            return _time_err("parse_error", str(exc), input=s)

        epoch_ms = int((naive_local - _dt(1970, 1, 1)).total_seconds() * 1000) - utc_off * 1000
        return _make_dt(epoch_ms, "UTC")

    def builtin_time_from_http_date(s):
        if not isinstance(s, str):
            vm.runtime_error("type", "time.from_http_date: expected a string")
        try:
            dt = _parsedate_http(s.strip())
            utc_dt = dt.astimezone(_tz.utc)
            epoch_ms = int((utc_dt - _EPOCH_UTC).total_seconds() * 1000)
            return _make_dt(epoch_ms, "UTC")
        except Exception:
            return _time_err("parse_error", f"invalid HTTP-date string: {s!r}", input=s)

    def builtin_time_parse(s, fmt, zone_name=None, options=None):
        if not isinstance(s, str):
            vm.runtime_error("type", "time.parse: expected a string")
        if not isinstance(fmt, str):
            vm.runtime_error("type", "time.parse: format must be a string")

        tz, zn, err = _resolve_zone(zone_name)
        if err is not None:
            return err

        strict = True
        if isinstance(options, dict):
            strict = options.get("strict", True)
            if strict is None:
                strict = True

        try:
            fmt_tokens = _tokenize_fmt(fmt)
            pat, group_toks = _compile_parse_pattern(fmt_tokens, strict)
        except Exception as exc:
            return _time_err("parse_error", f"invalid format string: {exc}", input=s, fmt=fmt)

        m = pat.match(s)
        if not m:
            return _time_err("parse_error",
                             f"input {s!r} does not match format {fmt!r}",
                             input=s, fmt=fmt)

        groups = m.groups()
        vals = dict(zip(group_toks, groups))

        # Extract fields
        def _iv(key, alt=None):
            if key in vals:
                return int(vals[key])
            if alt and alt in vals:
                return int(vals[alt])
            return None

        year = _iv("yyyy")
        if year is None and "yy" in vals:
            year = 2000 + int(vals["yy"])
        if year is None:
            return _time_err("parse_error", "format must include year token (yyyy or yy)", fmt=fmt)

        month = _iv("MM") or _iv("M")
        if month is None and "MMMM" in vals:
            month = _MONTH_FULL.index(vals["MMMM"]) + 1
        if month is None and "MMM" in vals:
            month = _MONTH_SHORT.index(vals["MMM"]) + 1
        if month is None:
            month = 1

        day = _iv("dd") or _iv("d") or 1
        hour = _iv("HH") or _iv("H") or _iv("hh") or _iv("h") or 0
        minute = _iv("mm") or _iv("m") or 0
        second = _iv("ss") or _iv("s") or 0
        ms_val = _iv("SSS") or 0

        # AM/PM adjustment
        if "a" in vals:
            ampm = vals["a"]
            if ampm == "PM" and hour < 12:
                hour += 12
            elif ampm == "AM" and hour == 12:
                hour = 0

        # Timezone override from format
        parse_zone_name = zn
        if "VV" in vals:
            vv_tz = _get_zone(vals["VV"])
            if vv_tz is None:
                return _time_err("invalid_zone", f"unknown timezone: {vals['VV']!r}", zone=vals["VV"])
            parse_zone_name = vals["VV"]
        elif "ZZZZ" in vals or "Z" in vals:
            offset_str = vals.get("ZZZZ") or vals.get("Z", "")
            if offset_str in ("Z", "+00:00", "+0000"):
                parse_zone_name = "UTC"
            else:
                sign = 1 if offset_str[0] == "+" else -1
                digits = offset_str[1:].replace(":", "")
                h_off = int(digits[:2])
                m_off = int(digits[2:4])
                off_sec = sign * (h_off * 3600 + m_off * 60)
                fixed_tz = _tz(offset=_td(seconds=off_sec))
                try:
                    naive = _dt(year, month, day, hour, minute, second, ms_val * 1000)
                    aware = naive.replace(tzinfo=fixed_tz)
                    utc_aware = aware.astimezone(_tz.utc)
                    epoch_ms = int((utc_aware - _EPOCH_UTC).total_seconds() * 1000)
                    return _make_dt(epoch_ms, zn)
                except ValueError as exc:
                    return _time_err("parse_error", str(exc), input=s, fmt=fmt)

        return _construct_aware(year, month, day, hour, minute, second, ms_val, parse_zone_name,
                                options)

    # ── Duration constructors ────────────────────────────────────────
    def builtin_time_ms(n):
        n = _to_py_int(n, "n")
        return _make_dur(n)

    def builtin_time_seconds(n):
        n = _to_py_int(n, "n")
        return _make_dur(n * 1000)

    def builtin_time_minutes(n):
        n = _to_py_int(n, "n")
        return _make_dur(n * 60_000)

    def builtin_time_hours(n):
        n = _to_py_int(n, "n")
        return _make_dur(n * 3_600_000)

    def builtin_time_days(n):
        n = _to_py_int(n, "n")
        return _make_dur(n * 86_400_000)

    def builtin_time_weeks(n):
        n = _to_py_int(n, "n")
        return _make_dur(n * 604_800_000)

    def builtin_time_duration_between(dt1, dt2):
        _require_dt(dt1, "time.duration_between")
        _require_dt(dt2, "time.duration_between")
        return _make_dur(dt2.fields["epoch_ms"] - dt1.fields["epoch_ms"])

    # ── Calendar operations ──────────────────────────────────────────
    def builtin_time_add(dt, dur):
        _require_dt(dt, "time.add")
        _require_dur(dur, "time.add")
        return _make_dt(dt.fields["epoch_ms"] + dur.fields["total_ms"], dt.fields["zone"])

    def builtin_time_subtract(dt, dur):
        _require_dt(dt, "time.subtract")
        _require_dur(dur, "time.subtract")
        return _make_dt(dt.fields["epoch_ms"] - dur.fields["total_ms"], dt.fields["zone"])

    def _calendar_op(dt, fname):
        _require_dt(dt, fname)
        zone_name = dt.fields["zone"]
        tz = _get_zone(zone_name)
        local = _local_from_epoch_ms(dt.fields["epoch_ms"], tz)
        return local, zone_name, tz

    def builtin_time_add_days(dt, n):
        local, zone_name, tz = _calendar_op(dt, "time.add_days")
        n = _to_py_int(n, "n")
        target = local.replace(tzinfo=None) + _td(days=n)
        return _construct_aware(target.year, target.month, target.day,
                                target.hour, target.minute, target.second,
                                target.microsecond // 1000, zone_name, None)

    def builtin_time_add_months(dt, n):
        local, zone_name, tz = _calendar_op(dt, "time.add_months")
        n = _to_py_int(n, "n")
        month = local.month - 1 + n
        year = local.year + month // 12
        month = month % 12 + 1
        max_day = calendar.monthrange(year, month)[1]
        day = min(local.day, max_day)
        return _construct_aware(year, month, day, local.hour, local.minute, local.second,
                                local.microsecond // 1000, zone_name, None)

    def builtin_time_add_years(dt, n):
        local, zone_name, tz = _calendar_op(dt, "time.add_years")
        n = _to_py_int(n, "n")
        year = local.year + n
        max_day = calendar.monthrange(year, local.month)[1]
        day = min(local.day, max_day)
        return _construct_aware(year, local.month, day, local.hour, local.minute, local.second,
                                local.microsecond // 1000, zone_name, None)

    def builtin_time_start_of_day(dt):
        local, zone_name, tz = _calendar_op(dt, "time.start_of_day")
        return _construct_aware(local.year, local.month, local.day, 0, 0, 0, 0, zone_name, None)

    def builtin_time_end_of_day(dt):
        local, zone_name, tz = _calendar_op(dt, "time.end_of_day")
        return _construct_aware(local.year, local.month, local.day, 23, 59, 59, 999, zone_name, None)

    def builtin_time_start_of_week(dt):
        local, zone_name, tz = _calendar_op(dt, "time.start_of_week")
        # Go back to Monday (weekday 0)
        days_back = local.weekday()
        mon = local.replace(tzinfo=None) - _td(days=days_back)
        return _construct_aware(mon.year, mon.month, mon.day, 0, 0, 0, 0, zone_name, None)

    def builtin_time_start_of_month(dt):
        local, zone_name, tz = _calendar_op(dt, "time.start_of_month")
        return _construct_aware(local.year, local.month, 1, 0, 0, 0, 0, zone_name, None)

    def builtin_time_start_of_year(dt):
        local, zone_name, tz = _calendar_op(dt, "time.start_of_year")
        return _construct_aware(local.year, 1, 1, 0, 0, 0, 0, zone_name, None)

    def builtin_time_to_zone(dt, zone_name):
        _require_dt(dt, "time.to_zone")
        tz, zn, err = _resolve_zone(zone_name)
        if err is not None:
            return err
        return _make_dt(dt.fields["epoch_ms"], zn)

    def builtin_time_to_utc(dt):
        _require_dt(dt, "time.to_utc")
        return _make_dt(dt.fields["epoch_ms"], "UTC")

    # ── Formatting ───────────────────────────────────────────────────
    def builtin_time_format(dt, fmt):
        _require_dt(dt, "time.format")
        if not isinstance(fmt, str):
            vm.runtime_error("type", "time.format: format must be a string")
        try:
            fmt_tokens = _tokenize_fmt(fmt)
        except Exception as exc:
            return _time_err("parse_error", f"invalid format string: {exc}", fmt=fmt)
        tz = _get_zone(dt.fields["zone"])
        local = _local_from_epoch_ms(dt.fields["epoch_ms"], tz)
        return _render_fmt(fmt_tokens, local, tz)

    # ── Serialization helpers ────────────────────────────────────────
    def builtin_time_to_iso8601(dt):
        _require_dt(dt, "time.to_iso8601")
        result = builtin_time_format(dt, "yyyy-MM-dd'T'HH:mm:ss.SSSZZZZ")
        return result

    def builtin_time_to_http_date(dt):
        _require_dt(dt, "time.to_http_date")
        # RFC 7231: "Sun, 06 Nov 1994 08:49:37 GMT"
        utc_dt = _make_dt(dt.fields["epoch_ms"], "UTC")
        tz = _UTC
        local = _local_from_epoch_ms(utc_dt.fields["epoch_ms"], tz)
        day_name = _WEEKDAY_SHORT[local.weekday()]
        month_name = _MONTH_SHORT[local.month - 1]
        return f"{day_name}, {local.day:02d} {month_name} {local.year:04d} {local.hour:02d}:{local.minute:02d}:{local.second:02d} GMT"

    def builtin_time_to_epoch_ms(dt):
        _require_dt(dt, "time.to_epoch_ms")
        return dt.fields["epoch_ms"]

    # ── Registration ─────────────────────────────────────────────────
    registry.add("time_now", 0, builtin_time_now)
    registry.add("time_now_in", 1, builtin_time_now_in)
    registry.add("time_from_epoch_ms", (1, 2), builtin_time_from_epoch_ms)
    registry.add("time_at", (8, 9), builtin_time_at)
    registry.add("time_from_iso8601", 1, builtin_time_from_iso8601)
    registry.add("time_from_http_date", 1, builtin_time_from_http_date)
    registry.add("time_parse", (2, 3, 4), builtin_time_parse)
    registry.add("time_ms", 1, builtin_time_ms)
    registry.add("time_seconds", 1, builtin_time_seconds)
    registry.add("time_minutes", 1, builtin_time_minutes)
    registry.add("time_hours", 1, builtin_time_hours)
    registry.add("time_days", 1, builtin_time_days)
    registry.add("time_weeks", 1, builtin_time_weeks)
    registry.add("time_duration_between", 2, builtin_time_duration_between)
    registry.add("time_add", 2, builtin_time_add)
    registry.add("time_subtract", 2, builtin_time_subtract)
    registry.add("time_add_days", 2, builtin_time_add_days)
    registry.add("time_add_months", 2, builtin_time_add_months)
    registry.add("time_add_years", 2, builtin_time_add_years)
    registry.add("time_start_of_day", 1, builtin_time_start_of_day)
    registry.add("time_end_of_day", 1, builtin_time_end_of_day)
    registry.add("time_start_of_week", 1, builtin_time_start_of_week)
    registry.add("time_start_of_month", 1, builtin_time_start_of_month)
    registry.add("time_start_of_year", 1, builtin_time_start_of_year)
    registry.add("time_to_zone", 2, builtin_time_to_zone)
    registry.add("time_to_utc", 1, builtin_time_to_utc)
    registry.add("time_format", 2, builtin_time_format)
    registry.add("time_to_iso8601", 1, builtin_time_to_iso8601)
    registry.add("time_to_http_date", 1, builtin_time_to_http_date)
    registry.add("time_to_epoch_ms", 1, builtin_time_to_epoch_ms)
