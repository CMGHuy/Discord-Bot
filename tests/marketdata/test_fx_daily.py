"""v205 L1-a: the daily FX rate rule, fx_daily.rate_before.

Every expected rate is a literal read off the fixture frame by hand, never a
recomputation through fx or fx_convert. The table memo's tests are
tests/marketdata/test_fx_daily_lookup.py (V205-12b)."""
import ast
import math
import pathlib
from datetime import date

import pandas as pd
import pytest

from swingbot.core.marketdata import fx_daily

SOURCE = pathlib.Path(fx_daily.__file__)


def _frame(closes, tz=None):
    index = pd.DatetimeIndex(list(closes), tz=tz)
    values = list(closes.values())
    return pd.DataFrame({"Open": values, "Close": values}, index=index)


def _frame_rows(rows, tz=None):
    """Duplicate or unsorted stamps: (stamp, close) pairs in frame order."""
    return pd.DataFrame({"Close": [c for _, c in rows]},
                        index=pd.DatetimeIndex([s for s, _ in rows], tz=tz))


WEEK = _frame({"2026-10-19": 0.91, "2026-10-20": 0.92, "2026-10-21": 0.93,
               "2026-10-22": 0.94, "2026-10-23": 0.95})


@pytest.mark.parametrize("day,expected", [
    (date(2026, 10, 19), None),                              # first bar: nothing before it
    (date(2026, 10, 20), (0.91, date(2026, 10, 19))),
    (date(2026, 10, 21), (0.92, date(2026, 10, 20))),        # strictly before: not 0.93
    (date(2026, 10, 24), (0.95, date(2026, 10, 23))),        # after the last bar
    (date(2026, 10, 26), (0.95, date(2026, 10, 23))),        # Monday after the weekend gap
    (date(2026, 10, 30), (0.95, date(2026, 10, 23))),        # 7 days after the bar: still served
    (date(2026, 10, 31), None),                              # 8 days: fx_missing, never stale
])
def test_last_positive_close_strictly_before_the_day(day, expected):
    assert fx_daily.rate_before(WEEK, day) == expected


def test_nan_and_non_positive_closes_are_skipped():
    frame = _frame({"2026-10-19": 0.91, "2026-10-20": float("nan"), "2026-10-21": 0.0,
                    "2026-10-22": -1.0})
    assert fx_daily.rate_before(frame, date(2026, 10, 23)) == (0.91, date(2026, 10, 19))


def test_a_string_close_is_coerced_or_skipped():
    frame = pd.DataFrame({"Close": ["0.9", "bad"]},
                         index=pd.DatetimeIndex(["2026-10-19", "2026-10-20"]))
    assert fx_daily.rate_before(frame, date(2026, 10, 21)) == (0.9, date(2026, 10, 19))


def test_duplicate_stamps_take_the_last_row_of_the_newest_date():
    frame = _frame_rows([("2026-10-19", 0.91), ("2026-10-20", 0.92), ("2026-10-20", 0.925)])
    assert fx_daily.rate_before(frame, date(2026, 10, 21)) == (0.925, date(2026, 10, 20))


def test_unsorted_stamps_take_the_newest_date_wherever_it_sits():
    frame = _frame_rows([("2026-10-21", 0.93), ("2026-10-19", 0.91), ("2026-10-20", 0.92)])
    assert fx_daily.rate_before(frame, date(2026, 10, 22)) == (0.93, date(2026, 10, 21))
    assert fx_daily.rate_before(frame, date(2026, 10, 21)) == (0.92, date(2026, 10, 20))


def test_a_tz_aware_index_keeps_its_own_wall_date():
    london = _frame({"2026-10-20 00:00": 0.92}, tz="Europe/London")
    assert fx_daily.rate_before(london, date(2026, 10, 21)) == (0.92, date(2026, 10, 20))
    assert fx_daily.rate_before(london, date(2026, 10, 20)) is None
    late_utc = _frame({"2026-10-20 23:00": 0.92}, tz="UTC")       # Berlin would say 10-21
    assert fx_daily.rate_before(late_utc, date(2026, 10, 21)) == (0.92, date(2026, 10, 20))


@pytest.mark.parametrize("frame", [None, pd.DataFrame(),
                                   pd.DataFrame({"Open": [1.0]}, index=pd.DatetimeIndex(["2026-10-19"]))])
def test_no_frame_no_rows_or_no_close_column_is_none(frame):
    assert fx_daily.rate_before(frame, date(2026, 10, 21)) is None


def test_the_answer_is_a_plain_float_and_date():
    rate, bar = fx_daily.rate_before(WEEK, date(2026, 10, 21))
    assert type(rate) is float and type(bar) is date and math.isfinite(rate)


def test_fallback_days_is_seven():
    assert fx_daily.FALLBACK_DAYS == 7


def test_the_module_imports_neither_fx_nor_admin_nor_flask():
    names = set()
    for node in ast.walk(ast.parse(SOURCE.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
    assert "swingbot.core.marketdata.fx" not in names
    assert not any(n.startswith(("swingbot.admin", "flask")) for n in names), names
