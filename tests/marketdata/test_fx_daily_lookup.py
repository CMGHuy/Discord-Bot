"""v205 L1-a: fx_daily.lookup over the fx_daily_rates memo (version-keyed, 60 s check).

Every expected rate is a literal from the fake table, never a recomputation."""
from datetime import date, datetime, timezone

import pytest

from swingbot.core.infra import swallowed as sw
from swingbot.core.marketdata import fx_daily


class FakeRates:
    def __init__(self, rows):
        self.rows = list(rows)
        self.at = datetime(2026, 11, 4, 7, 0, tzinfo=timezone.utc)
        self.version_calls = 0
        self.load_calls = 0
        self.fail = False

    def version(self, *, conn=None):
        self.version_calls += 1
        if self.fail:
            raise RuntimeError('relation "fx_daily_rates" does not exist')
        return len(self.rows), self.at

    def all_rates(self, *, conn=None):
        self.load_calls += 1
        return sorted(self.rows, key=lambda r: (r["base"], r["account"], r["day"]))


def _rate(day, rate, bar, base="USD", account="EUR"):
    return {"base": base, "account": account, "day": day, "rate": rate, "bar_date": bar}


class Clock:
    def __init__(self):
        self.now = 5000.0

    def __call__(self):
        return self.now


@pytest.fixture
def table(monkeypatch):
    repo = FakeRates([
        _rate(date(2026, 11, 2), 0.86, date(2026, 10, 30)),     # Monday: Friday's close
        _rate(date(2026, 11, 3), 0.87, date(2026, 11, 2)),
        _rate(date(2026, 11, 3), 1.15, date(2026, 11, 2), base="GBP"),
    ])
    fx_daily.reset_memo()
    monkeypatch.setattr(fx_daily, "fx_daily_rate_repo", lambda: repo)
    yield repo
    fx_daily.reset_memo()


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(fx_daily, "_clock", c)
    return c


def test_an_exact_row_wins(table, clock):
    assert fx_daily.lookup("USD", "EUR", date(2026, 11, 2)) == 0.86
    assert fx_daily.lookup("USD", "EUR", date(2026, 11, 3)) == 0.87
    assert fx_daily.lookup("GBP", "EUR", date(2026, 11, 3)) == 1.15


def test_a_missing_day_falls_back_to_the_nearest_earlier_row_within_seven_days(table, clock):
    assert fx_daily.lookup("USD", "EUR", date(2026, 11, 4)) == 0.87      # bar 11-02, 2 days
    assert fx_daily.lookup("USD", "EUR", date(2026, 11, 9)) == 0.87      # bar 11-02, 7 days
    assert fx_daily.lookup("USD", "EUR", date(2026, 11, 10)) is None     # 8 days: fx_missing


def test_before_the_first_row_or_an_unknown_pair_is_none(table, clock):
    assert fx_daily.lookup("USD", "EUR", date(2026, 11, 1)) is None
    assert fx_daily.lookup("ZAR", "EUR", date(2026, 11, 3)) is None
    assert fx_daily.lookup("USD", "GBP", date(2026, 11, 3)) is None


def test_an_empty_table_is_none_and_loads_once(table, clock):
    table.rows.clear()
    assert fx_daily.lookup("USD", "EUR", date(2026, 11, 3)) is None
    assert fx_daily.lookup("USD", "EUR", date(2026, 11, 4)) is None
    assert (table.version_calls, table.load_calls) == (1, 1)


def test_the_version_is_checked_at_most_once_per_minute(table, clock):
    for _ in range(50):
        fx_daily.lookup("USD", "EUR", date(2026, 11, 5))                  # a missing key, every call
    assert (table.version_calls, table.load_calls) == (1, 1)
    clock.now += fx_daily.VERSION_CHECK_S - 1
    fx_daily.lookup("USD", "EUR", date(2026, 11, 5))
    assert (table.version_calls, table.load_calls) == (1, 1)
    clock.now += 2
    fx_daily.lookup("USD", "EUR", date(2026, 11, 5))
    assert (table.version_calls, table.load_calls) == (2, 1)              # same version: no reload


def test_a_new_row_shows_after_the_next_version_check(table, clock):
    assert fx_daily.lookup("USD", "EUR", date(2026, 11, 4)) == 0.87
    table.rows.append(_rate(date(2026, 11, 4), 0.88, date(2026, 11, 3)))
    table.at = datetime(2026, 11, 4, 7, 0, 5, tzinfo=timezone.utc)
    assert fx_daily.lookup("USD", "EUR", date(2026, 11, 4)) == 0.87      # inside the minute
    clock.now += fx_daily.VERSION_CHECK_S
    assert fx_daily.lookup("USD", "EUR", date(2026, 11, 4)) == 0.88
    assert table.load_calls == 2


def test_an_unreadable_table_is_none_swallowed_and_checked_again_a_minute_later(table, clock):
    before = sw.snapshot().get("marketdata.fx_daily.lookup", {}).get("count", 0)
    table.fail = True
    assert fx_daily.lookup("USD", "EUR", date(2026, 11, 3)) is None
    assert fx_daily.lookup("USD", "EUR", date(2026, 11, 3)) is None
    assert table.version_calls == 1                                       # not one query per amount
    assert sw.snapshot()["marketdata.fx_daily.lookup"]["count"] == before + 1
    table.fail = False
    clock.now += fx_daily.VERSION_CHECK_S
    assert fx_daily.lookup("USD", "EUR", date(2026, 11, 3)) == 0.87


def test_a_read_error_keeps_the_loaded_memo(table, clock):
    assert fx_daily.lookup("USD", "EUR", date(2026, 11, 3)) == 0.87
    table.fail = True
    clock.now += fx_daily.VERSION_CHECK_S
    assert fx_daily.lookup("USD", "EUR", date(2026, 11, 3)) is None      # the failing call
    assert fx_daily.lookup("USD", "EUR", date(2026, 11, 3)) == 0.87      # the kept memo
    assert table.version_calls == 2


def test_reset_memo_forces_a_reload(table, clock):
    fx_daily.lookup("USD", "EUR", date(2026, 11, 3))
    fx_daily.reset_memo()
    fx_daily.lookup("USD", "EUR", date(2026, 11, 3))
    assert table.load_calls == 2


def test_the_answer_is_never_one_for_a_missing_rate(table, clock):
    answers = [fx_daily.lookup(base, "EUR", date(2026, 11, d))
               for base in ("USD", "GBP", "ZAR") for d in range(1, 15)]
    assert 1.0 not in answers and None in answers
