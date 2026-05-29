"""3B.2: std:time — datetime/duration/calendar namespace."""

import io
import unittest
from contextlib import redirect_stdout

import nodus as lang
from nodus.runtime.module_loader import ModuleLoader

_HDR = 'import "std:time" as time\n'


def run_src(src: str):
    vm = lang.VM([], {}, code_locs=[], source_path="main.nd")
    _loader = ModuleLoader(project_root=None, vm=vm)
    buf = io.StringIO()
    with redirect_stdout(buf):
        _loader.load_module_from_source(_HDR + src, module_name="main.nd")
    return buf.getvalue().splitlines(), vm


def lines(src):
    out, _ = run_src(src)
    return out


def first(src):
    return lines(src)[0]


class DatetimeConstructorTests(unittest.TestCase):

    def test_now_returns_datetime(self):
        self.assertEqual(first('print(type(time.now()))'), "datetime")

    def test_now_zone_is_utc(self):
        self.assertEqual(first('print(time.now().zone)'), "UTC")

    def test_now_year_reasonable(self):
        out = first('print(time.now().year > 2020)')
        self.assertEqual(out, "true")

    def test_now_in_returns_datetime(self):
        self.assertEqual(first('print(type(time.now_in("America/Phoenix")))'), "datetime")

    def test_now_in_zone_preserved(self):
        self.assertEqual(first('print(time.now_in("America/Phoenix").zone)'), "America/Phoenix")

    def test_now_in_invalid_zone_returns_err(self):
        out = first('print(type(time.now_in("Fake/Zone")))'),
        self.assertIn("error", str(out))

    def test_from_epoch_ms_basic(self):
        # 2026-05-27T00:00:00Z = ?
        out = first('let dt = time.from_epoch_ms(0)\nprint(dt.year)')
        self.assertEqual(out, "1970")

    def test_from_epoch_ms_with_zone(self):
        out = first('let dt = time.from_epoch_ms(0, "UTC")\nprint(dt.zone)')
        self.assertEqual(out, "UTC")

    def test_at_basic(self):
        out = first('let dt = time.at(2026, 5, 27, 12, 0, 0, 0, "UTC")\nprint(dt.year)')
        self.assertEqual(out, "2026")

    def test_at_all_fields(self):
        out = lines('let dt = time.at(2026, 5, 27, 14, 30, 45, 123, "UTC")\nprint(dt.month)\nprint(dt.day)\nprint(dt.hour)\nprint(dt.minute)\nprint(dt.second)\nprint(dt.ms)')
        self.assertEqual(out, ["5", "27", "14", "30", "45", "123"])

    def test_at_invalid_zone_returns_err(self):
        out = first('print(type(time.at(2026, 5, 27, 12, 0, 0, 0, "Bad/Zone")))')
        self.assertEqual(out, "error")

    def test_at_out_of_range_month(self):
        out = first('print(type(time.at(2026, 13, 1, 0, 0, 0, 0, "UTC")))')
        self.assertEqual(out, "error")

    def test_at_out_of_range_day(self):
        out = first('print(type(time.at(2026, 2, 30, 0, 0, 0, 0, "UTC")))')
        self.assertEqual(out, "error")

    def test_at_out_of_range_year(self):
        out = first('print(type(time.at(1800, 1, 1, 0, 0, 0, 0, "UTC")))')
        self.assertEqual(out, "error")

    def test_at_year_range_min(self):
        out = first('let dt = time.at(1900, 1, 1, 0, 0, 0, 0, "UTC")\nprint(dt.year)')
        self.assertEqual(out, "1900")

    def test_at_year_range_max(self):
        out = first('let dt = time.at(2099, 12, 31, 0, 0, 0, 0, "UTC")\nprint(dt.year)')
        self.assertEqual(out, "2099")


class DatetimeAccessorTests(unittest.TestCase):

    def setUp(self):
        # 2026-05-27T14:30:45.123Z is a Wednesday (weekday=2)
        self._base = 'let dt = time.at(2026, 5, 27, 14, 30, 45, 123, "UTC")\n'

    def test_year(self):
        self.assertEqual(first(self._base + 'print(dt.year)'), "2026")

    def test_month(self):
        self.assertEqual(first(self._base + 'print(dt.month)'), "5")

    def test_day(self):
        self.assertEqual(first(self._base + 'print(dt.day)'), "27")

    def test_hour(self):
        self.assertEqual(first(self._base + 'print(dt.hour)'), "14")

    def test_minute(self):
        self.assertEqual(first(self._base + 'print(dt.minute)'), "30")

    def test_second(self):
        self.assertEqual(first(self._base + 'print(dt.second)'), "45")

    def test_ms(self):
        self.assertEqual(first(self._base + 'print(dt.ms)'), "123")

    def test_weekday_wednesday(self):
        # 2026-05-27 is a Wednesday → weekday = 2
        self.assertEqual(first(self._base + 'print(dt.weekday)'), "2")

    def test_day_of_year(self):
        # May 27 = 31+28+31+30+31+27 = 147
        self.assertEqual(first(self._base + 'print(dt.day_of_year)'), "147")

    def test_zone(self):
        self.assertEqual(first(self._base + 'print(dt.zone)'), "UTC")

    def test_epoch_ms(self):
        # Known epoch_ms for 2026-05-27T14:30:45.123Z
        out = first(self._base + 'print(dt.epoch_ms > 0)')
        self.assertEqual(out, "true")

    def test_is_dst_utc(self):
        self.assertEqual(first(self._base + 'print(dt.is_dst)'), "false")

    def test_type_is_datetime(self):
        self.assertEqual(first(self._base + 'print(type(dt))'), "datetime")


class DatetimeComparisonTests(unittest.TestCase):

    def test_equality_same_instant(self):
        src = ('let a = time.at(2026, 5, 27, 12, 0, 0, 0, "UTC")\n'
               'let b = time.at(2026, 5, 27, 12, 0, 0, 0, "UTC")\n'
               'print(a == b)')
        self.assertEqual(first(src), "true")

    def test_equality_different_zone_same_instant(self):
        # Compare by epoch_ms regardless of zone
        src = ('let a = time.from_epoch_ms(1000, "UTC")\n'
               'let b = time.from_epoch_ms(1000, "America/Phoenix")\n'
               'print(a == b)')
        self.assertEqual(first(src), "true")

    def test_ordering_lt(self):
        src = ('let a = time.at(2026, 5, 27, 12, 0, 0, 0, "UTC")\n'
               'let b = time.add(a, time.minutes(5))\n'
               'print(a < b)')
        self.assertEqual(first(src), "true")

    def test_ordering_gt(self):
        src = ('let a = time.at(2026, 5, 27, 12, 0, 0, 0, "UTC")\n'
               'let b = time.add(a, time.minutes(5))\n'
               'print(b > a)')
        self.assertEqual(first(src), "true")

    def test_ne(self):
        src = ('let a = time.at(2026, 5, 27, 12, 0, 0, 0, "UTC")\n'
               'let b = time.add(a, time.seconds(1))\n'
               'print(a != b)')
        self.assertEqual(first(src), "true")


class DurationTests(unittest.TestCase):

    def test_ms_constructor(self):
        self.assertEqual(first('print(time.ms(500).total_ms)'), "500")

    def test_seconds_constructor(self):
        self.assertEqual(first('print(time.seconds(2).total_ms)'), "2000")

    def test_minutes_constructor(self):
        self.assertEqual(first('print(time.minutes(1).total_ms)'), "60000")

    def test_hours_constructor(self):
        self.assertEqual(first('print(time.hours(1).total_ms)'), "3600000")

    def test_days_constructor(self):
        self.assertEqual(first('print(time.days(1).total_ms)'), "86400000")

    def test_weeks_constructor(self):
        self.assertEqual(first('print(time.weeks(1).total_ms)'), "604800000")

    def test_duration_between(self):
        src = ('let a = time.at(2026, 5, 27, 12, 0, 0, 0, "UTC")\n'
               'let b = time.add(a, time.hours(1))\n'
               'print(time.duration_between(a, b).total_ms)')
        self.assertEqual(first(src), "3600000")

    def test_duration_between_negative(self):
        src = ('let a = time.at(2026, 5, 27, 12, 0, 0, 0, "UTC")\n'
               'let b = time.add(a, time.hours(1))\n'
               'print(time.duration_between(b, a).total_ms)')
        self.assertEqual(first(src), "-3600000")

    def test_duration_accessors_total_seconds(self):
        self.assertEqual(first('print(time.minutes(2).total_seconds)'), "120.0")

    def test_duration_comparison_eq(self):
        src = ('let a = time.minutes(5)\nlet b = time.seconds(300)\nprint(a == b)')
        self.assertEqual(first(src), "true")

    def test_duration_comparison_lt(self):
        src = ('let a = time.minutes(5)\nlet b = time.minutes(10)\nprint(a < b)')
        self.assertEqual(first(src), "true")

    def test_type_is_duration(self):
        self.assertEqual(first('print(type(time.seconds(1)))'), "duration")


class CalendarOpTests(unittest.TestCase):

    def _dt(self, y, mo, d, h=0, mi=0, s=0, ms=0, zone="UTC"):
        return f'let dt = time.at({y}, {mo}, {d}, {h}, {mi}, {s}, {ms}, "{zone}")\n'

    def test_add_fixed_duration(self):
        src = self._dt(2026, 5, 27, 12) + 'let r = time.add(dt, time.hours(2))\nprint(r.hour)'
        self.assertEqual(first(src), "14")

    def test_subtract_duration(self):
        src = self._dt(2026, 5, 27, 12) + 'let r = time.subtract(dt, time.hours(2))\nprint(r.hour)'
        self.assertEqual(first(src), "10")

    def test_add_days(self):
        src = self._dt(2026, 5, 27) + 'let r = time.add_days(dt, 5)\nprint(r.day)'
        self.assertEqual(first(src), "1")  # May 27 + 5 = June 1

    def test_add_days_same_time(self):
        src = self._dt(2026, 5, 27, 14, 30) + 'let r = time.add_days(dt, 1)\nprint(r.hour)'
        self.assertEqual(first(src), "14")  # hour preserved

    def test_add_months_basic(self):
        src = self._dt(2026, 1, 15) + 'let r = time.add_months(dt, 3)\nprint(r.month)'
        self.assertEqual(first(src), "4")

    def test_add_months_clamp_jan31(self):
        # Jan 31 + 1 month = Feb 28 (2026 not leap year)
        src = self._dt(2026, 1, 31) + 'let r = time.add_months(dt, 1)\nprint(r.day)'
        self.assertEqual(first(src), "28")

    def test_add_months_negative(self):
        src = self._dt(2026, 3, 15) + 'let r = time.add_months(dt, -1)\nprint(r.month)'
        self.assertEqual(first(src), "2")

    def test_add_years_basic(self):
        src = self._dt(2026, 5, 27) + 'let r = time.add_years(dt, 1)\nprint(r.year)'
        self.assertEqual(first(src), "2027")

    def test_add_years_clamp_feb29(self):
        # Feb 29, 2024 + 1 year = Feb 28, 2025
        src = self._dt(2024, 2, 29) + 'let r = time.add_years(dt, 1)\nprint(r.day)'
        self.assertEqual(first(src), "28")

    def test_start_of_day(self):
        src = self._dt(2026, 5, 27, 14, 30, 45, 123) + 'let r = time.start_of_day(dt)\nprint(r.hour)\nprint(r.minute)\nprint(r.second)'
        self.assertEqual(lines(src), ["0", "0", "0"])

    def test_end_of_day(self):
        src = self._dt(2026, 5, 27) + 'let r = time.end_of_day(dt)\nprint(r.hour)\nprint(r.minute)\nprint(r.second)'
        self.assertEqual(lines(src), ["23", "59", "59"])

    def test_start_of_week_wednesday(self):
        # 2026-05-27 is Wednesday; start of week = Monday 2026-05-25
        src = self._dt(2026, 5, 27) + 'let r = time.start_of_week(dt)\nprint(r.day)'
        self.assertEqual(first(src), "25")

    def test_start_of_month(self):
        src = self._dt(2026, 5, 27) + 'let r = time.start_of_month(dt)\nprint(r.day)'
        self.assertEqual(first(src), "1")

    def test_start_of_year(self):
        src = self._dt(2026, 5, 27) + 'let r = time.start_of_year(dt)\nprint(r.month)\nprint(r.day)'
        self.assertEqual(lines(src), ["1", "1"])

    def test_to_zone(self):
        src = self._dt(2026, 5, 27, 12) + 'let r = time.to_zone(dt, "America/Phoenix")\nprint(r.zone)'
        self.assertEqual(first(src), "America/Phoenix")

    def test_to_utc(self):
        src = self._dt(2026, 5, 27, 12, zone="America/Phoenix") + 'let r = time.to_utc(dt)\nprint(r.zone)'
        self.assertEqual(first(src), "UTC")

    def test_to_zone_preserves_epoch_ms(self):
        src = self._dt(2026, 5, 27, 12) + (
            'let r = time.to_zone(dt, "America/Phoenix")\n'
            'print(r.epoch_ms == dt.epoch_ms)'
        )
        self.assertEqual(first(src), "true")


class FormatTests(unittest.TestCase):

    def _fmt(self, fmt_str):
        # 2026-05-27T14:30:45.123Z is a Wednesday
        src = ('let dt = time.at(2026, 5, 27, 14, 30, 45, 123, "UTC")\n'
               f'print(time.format(dt, "{fmt_str}"))')
        return first(src)

    def test_yyyy(self):
        self.assertEqual(self._fmt("yyyy"), "2026")

    def test_yy(self):
        self.assertEqual(self._fmt("yy"), "26")

    def test_MMMM(self):
        self.assertEqual(self._fmt("MMMM"), "May")

    def test_MMM(self):
        self.assertEqual(self._fmt("MMM"), "May")

    def test_MM(self):
        self.assertEqual(self._fmt("MM"), "05")

    def test_M(self):
        self.assertEqual(self._fmt("M"), "5")

    def test_dd(self):
        self.assertEqual(self._fmt("dd"), "27")

    def test_d(self):
        self.assertEqual(self._fmt("d"), "27")

    def test_EEEE(self):
        self.assertEqual(self._fmt("EEEE"), "Wednesday")

    def test_EEE(self):
        self.assertEqual(self._fmt("EEE"), "Wed")

    def test_HH(self):
        self.assertEqual(self._fmt("HH"), "14")

    def test_H(self):
        self.assertEqual(self._fmt("H"), "14")

    def test_hh(self):
        self.assertEqual(self._fmt("hh"), "02")

    def test_h(self):
        self.assertEqual(self._fmt("h"), "2")

    def test_mm(self):
        self.assertEqual(self._fmt("mm"), "30")

    def test_ss(self):
        self.assertEqual(self._fmt("ss"), "45")

    def test_SSS(self):
        self.assertEqual(self._fmt("SSS"), "123")

    def test_a_pm(self):
        self.assertEqual(self._fmt("a"), "PM")

    def test_a_am(self):
        src = ('let dt = time.at(2026, 5, 27, 9, 0, 0, 0, "UTC")\n'
               'print(time.format(dt, "a"))')
        self.assertEqual(first(src), "AM")

    def test_ZZZZ_utc(self):
        self.assertEqual(self._fmt("ZZZZ"), "+00:00")

    def test_Z_utc(self):
        self.assertEqual(self._fmt("Z"), "+0000")

    def test_VV(self):
        self.assertEqual(self._fmt("VV"), "UTC")

    def test_literal_text(self):
        src = ('let dt = time.at(2026, 5, 27, 14, 30, 0, 0, "UTC")\n'
               "print(time.format(dt, \"yyyy-MM-dd 'at' HH:mm\"))")
        self.assertEqual(first(src), "2026-05-27 at 14:30")

    def test_full_datetime_format(self):
        self.assertEqual(self._fmt("yyyy-MM-dd HH:mm:ss"), "2026-05-27 14:30:45")

    def test_iso8601_format(self):
        self.assertEqual(self._fmt("yyyy-MM-dd'T'HH:mm:ssZZZZ"), "2026-05-27T14:30:45+00:00")


class SerializationTests(unittest.TestCase):

    def test_to_iso8601(self):
        src = ('let dt = time.at(2026, 5, 27, 14, 30, 45, 123, "UTC")\n'
               'print(time.to_iso8601(dt))')
        out = first(src)
        self.assertIn("2026-05-27T14:30:45", out)
        self.assertIn("00:00", out)

    def test_to_http_date(self):
        src = ('let dt = time.at(2026, 5, 27, 14, 30, 45, 0, "UTC")\n'
               'print(time.to_http_date(dt))')
        out = first(src)
        self.assertIn("27", out)
        self.assertIn("GMT", out)
        self.assertIn("2026", out)

    def test_to_epoch_ms(self):
        src = ('let dt = time.at(2026, 5, 27, 12, 0, 0, 0, "UTC")\n'
               'print(time.to_epoch_ms(dt) == dt.epoch_ms)')
        self.assertEqual(first(src), "true")

    def test_from_iso8601_basic(self):
        src = ('let dt = time.from_iso8601("2026-05-27T14:30:00Z")\n'
               'print(dt.year)\nprint(dt.hour)')
        self.assertEqual(lines(src), ["2026", "14"])

    def test_from_iso8601_with_offset(self):
        src = ('let dt = time.from_iso8601("2026-05-27T14:30:00+00:00")\n'
               'print(dt.zone)')
        self.assertEqual(first(src), "UTC")

    def test_from_iso8601_with_millis(self):
        src = ('let dt = time.from_iso8601("2026-05-27T14:30:00.123Z")\n'
               'print(dt.ms)')
        self.assertEqual(first(src), "123")

    def test_from_iso8601_space_sep(self):
        src = ('let dt = time.from_iso8601("2026-05-27 14:30:00Z")\n'
               'print(dt.year)')
        self.assertEqual(first(src), "2026")

    def test_from_iso8601_invalid_returns_err(self):
        src = ('let dt = time.from_iso8601("not-a-date")\n'
               'print(type(dt))')
        self.assertEqual(first(src), "error")

    def test_from_iso8601_no_zone_returns_err(self):
        src = ('let dt = time.from_iso8601("2026-05-27T14:30:00")\n'
               'print(type(dt))')
        self.assertEqual(first(src), "error")

    def test_from_http_date_imf(self):
        src = ('let dt = time.from_http_date("Sun, 06 Nov 1994 08:49:37 GMT")\n'
               'print(dt.year)\nprint(dt.month)\nprint(dt.day)')
        self.assertEqual(lines(src), ["1994", "11", "6"])

    def test_from_http_date_invalid(self):
        src = ('let dt = time.from_http_date("not a date")\nprint(type(dt))')
        self.assertEqual(first(src), "error")


class ParseTests(unittest.TestCase):

    def test_parse_basic_date(self):
        src = ('let dt = time.parse("2026-05-27", "yyyy-MM-dd", "UTC")\n'
               'print(dt.year)\nprint(dt.month)\nprint(dt.day)')
        self.assertEqual(lines(src), ["2026", "5", "27"])

    def test_parse_datetime(self):
        src = ('let dt = time.parse("2026-05-27 14:30:45", "yyyy-MM-dd HH:mm:ss", "UTC")\n'
               'print(dt.hour)\nprint(dt.minute)\nprint(dt.second)')
        self.assertEqual(lines(src), ["14", "30", "45"])

    def test_parse_strict_rejects_single_digit_month(self):
        src = ('let dt = time.parse("2026-5-27", "yyyy-MM-dd", "UTC")\n'
               'print(type(dt))')
        self.assertEqual(first(src), "error")

    def test_parse_lenient_accepts_single_digit_month(self):
        src = ('let dt = time.parse("2026-5-27", "yyyy-MM-dd", "UTC", {"strict": false})\n'
               'print(dt.month)')
        self.assertEqual(first(src), "5")

    def test_parse_month_name(self):
        src = ('let dt = time.parse("May 27 2026", "MMMM dd yyyy", "UTC")\n'
               'print(dt.month)')
        self.assertEqual(first(src), "5")

    def test_parse_invalid_returns_err(self):
        src = ('let dt = time.parse("not-a-date", "yyyy-MM-dd", "UTC")\n'
               'print(type(dt))')
        self.assertEqual(first(src), "error")


class DSTTests(unittest.TestCase):

    def test_spring_forward_gap_returns_err(self):
        # America/New_York spring 2026: 2026-03-08 02:30:00 doesn't exist
        src = ('let dt = time.at(2026, 3, 8, 2, 30, 0, 0, "America/New_York")\n'
               'print(type(dt))')
        self.assertEqual(first(src), "error")

    def test_spring_forward_err_category(self):
        src = ('let dt = time.at(2026, 3, 8, 2, 30, 0, 0, "America/New_York")\n'
               'print(dt.payload["category"])')
        self.assertEqual(first(src), "out_of_range")

    def test_spring_forward_shift_forward(self):
        src = ('let dt = time.at(2026, 3, 8, 2, 30, 0, 0, "America/New_York", {"on_invalid": "shift_forward"})\n'
               'print(type(dt))')
        self.assertEqual(first(src), "datetime")

    def test_spring_forward_shift_backward(self):
        src = ('let dt = time.at(2026, 3, 8, 2, 30, 0, 0, "America/New_York", {"on_invalid": "shift_backward"})\n'
               'print(type(dt))')
        self.assertEqual(first(src), "datetime")

    def test_fall_back_ambiguous_returns_err(self):
        # America/New_York fall 2026: 2026-11-01 01:30:00 is ambiguous
        src = ('let dt = time.at(2026, 11, 1, 1, 30, 0, 0, "America/New_York")\n'
               'print(type(dt))')
        self.assertEqual(first(src), "error")

    def test_fall_back_err_category(self):
        src = ('let dt = time.at(2026, 11, 1, 1, 30, 0, 0, "America/New_York")\n'
               'print(dt.payload["category"])')
        self.assertEqual(first(src), "ambiguous")

    def test_fall_back_earliest(self):
        src = ('let a = time.at(2026, 11, 1, 1, 30, 0, 0, "America/New_York", {"on_ambiguous": "earliest"})\n'
               'let b = time.at(2026, 11, 1, 1, 30, 0, 0, "America/New_York", {"on_ambiguous": "latest"})\n'
               'print(a < b)')
        self.assertEqual(first(src), "true")

    def test_add_hours_vs_add_days_across_dst(self):
        # This just tests both work without error across a DST boundary
        src = ('let dt = time.at(2026, 3, 7, 14, 0, 0, 0, "America/New_York")\n'
               'let a = time.add(dt, time.hours(24))\n'
               'let b = time.add_days(dt, 1)\n'
               'print(type(a))\nprint(type(b))')
        self.assertEqual(lines(src), ["datetime", "datetime"])


class ErrRecordTests(unittest.TestCase):

    def test_invalid_zone_err_kind(self):
        src = ('let dt = time.at(2026, 5, 27, 12, 0, 0, 0, "Bad/Zone")\n'
               'print(dt.kind)')
        self.assertEqual(first(src), "time_error")

    def test_invalid_zone_err_category(self):
        src = ('let dt = time.at(2026, 5, 27, 12, 0, 0, 0, "Bad/Zone")\n'
               'print(dt.payload["category"])')
        self.assertEqual(first(src), "invalid_zone")

    def test_out_of_range_err_kind(self):
        src = ('let dt = time.at(2026, 13, 1, 0, 0, 0, 0, "UTC")\n'
               'print(dt.kind)')
        self.assertEqual(first(src), "time_error")

    def test_out_of_range_err_category(self):
        src = ('let dt = time.at(2026, 13, 1, 0, 0, 0, 0, "UTC")\n'
               'print(dt.payload["category"])')
        self.assertEqual(first(src), "out_of_range")

    def test_parse_error_kind(self):
        src = ('let dt = time.from_iso8601("bad")\nprint(dt.kind)')
        self.assertEqual(first(src), "time_error")

    def test_parse_error_category(self):
        src = ('let dt = time.from_iso8601("bad")\nprint(dt.payload["category"])')
        self.assertEqual(first(src), "parse_error")


if __name__ == "__main__":
    unittest.main()
