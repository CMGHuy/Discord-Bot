"""autopsy.cuts: the fourteen categorical cuts and their coverage rules."""
import datetime as dt
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "reports"))

from autopsy import cells, cuts  # noqa: E402
from autopsy.rows import BookRow  # noqa: E402
from swingbot.core.market.opex import monthly_expiration  # noqa: E402
from swingbot.core.marketdata import universe  # noqa: E402


def _keys(sector_of=None):
    return dict(cuts.categorical_cuts(sector_of or {}))


def test_the_cut_names_are_the_contract_in_order():
    assert [name for name, _ in cuts.categorical_cuts({})] == [
        "strategy_horizon", "direction", "ticker", "sector_today", "regime", "weekday",
        "friday_entry", "weekend_hold", "earnings_proximity", "opex_week",
        "fomc_proximity", "atr_pct_bucket", "session_bucket", "alert_hour"]


def test_a_bare_row_is_uncovered_by_every_cut():
    assert all(key(BookRow()) is None for key in _keys().values())


def test_plain_field_cuts():
    row = BookRow(strategy="RSI", horizon="2w", direction="bullish", ticker="AAA",
                  regime2_state="bull_quiet", session_bucket="open", plan_hour=9)
    keys = _keys({"AAA": "Technology"})
    assert keys["strategy_horizon"](row) == "RSI|2w"
    assert (keys["direction"](row), keys["ticker"](row)) == ("bullish", "AAA")
    assert (keys["regime"](row), keys["session_bucket"](row)) == ("bull_quiet", "open")
    assert keys["sector_today"](row) == "Technology"
    assert keys["sector_today"](BookRow(ticker="ZZZ")) is None
    assert keys["alert_hour"](row) == "09"


def test_weekday_friday_entry_and_weekend_hold():
    keys = _keys()
    thursday = BookRow(entry_date="2026-03-19", exit_date="2026-03-23")
    friday = BookRow(entry_date="2026-03-20", exit_date="2026-03-20")
    assert (keys["weekday"](thursday), keys["friday_entry"](thursday)) == ("Thu", "no")
    assert (keys["weekday"](friday), keys["friday_entry"](friday)) == ("Fri", "yes")
    assert keys["weekend_hold"](thursday) == "yes"
    assert keys["weekend_hold"](friday) == "no"
    assert keys["weekend_hold"](BookRow(entry_date="2026-03-19")) is None


@pytest.mark.parametrize("days, bucket", [(-2, "past"), (0, "le_5d"), (5, "le_5d"),
                                          (6, "6_20d"), (20, "6_20d"), (21, "gt_20d")])
def test_earnings_buckets(days, bucket):
    assert _keys()["earnings_proximity"](BookRow(days_to_earnings=days)) == bucket


def test_opex_week_is_the_iso_week_of_the_monthly_expiration():
    assert monthly_expiration(2026, 3) == dt.date(2026, 3, 20)
    key = _keys()["opex_week"]
    assert key(BookRow(entry_date="2026-03-17")) == "opex_week"
    assert key(BookRow(entry_date="2026-03-24")) == "other"


def test_fomc_in_hold_and_coverage():
    key = _keys()["fomc_proximity"]
    assert key(BookRow(entry_date="2026-03-16", exit_date="2026-03-20")) == "fomc_in_hold"
    assert key(BookRow(entry_date="2026-03-02", exit_date="2026-03-06")) == "no_fomc"
    assert key(BookRow(entry_date="2025-12-29", exit_date="2026-01-30")) is None
    assert key(BookRow(entry_date="2027-12-01", exit_date="2028-01-05")) is None


@pytest.mark.parametrize("atr_pct, bucket", [(0.9, "lt_1.5"), (1.5, "1.5_3"), (2.99, "1.5_3"),
                                             (3.0, "3_5"), (5.0, "ge_5")])
def test_atr_pct_buckets(atr_pct, bucket):
    assert _keys()["atr_pct_bucket"](BookRow(atr_pct=atr_pct)) == bucket


def test_the_sector_map_degrades_to_empty(monkeypatch):
    def broken(name):
        raise OSError("no universe file")
    monkeypatch.setattr(universe, "sector_map", broken)
    assert cuts.load_sector_map() == {}


def test_the_sector_map_is_upper_cased_and_drops_blanks(monkeypatch):
    monkeypatch.setattr(universe, "sector_map", lambda name: {"aaa": "Tech", "BBB": ""})
    assert cuts.load_sector_map() == {"AAA": "Tech"}


def test_notes_label_sector_fomc_and_the_omitted_macro_cuts():
    assert "not point-in-time" in cuts.CUT_NOTES["sector_today"]
    assert "CPI and NFP omitted" in cuts.CUT_NOTES["macro"]
    assert "2026-01-01" in cuts.CUT_NOTES["fomc_proximity"]
    assert "earnings_proximity" in cuts.CUT_NOTES


def test_a_categorical_cut_feeds_cut_cells():
    trades = [BookRow(row_kind="trade", ticker="AAA", direction=d, entry_date=f"2026-03-0{i + 2}",
                      gross_r=r, net_r=r)
              for i, (d, r) in enumerate([("bullish", 1.0), ("bearish", -1.0), ("bullish", 0.5)])]
    out = cells.cut_cells("direction", trades, _keys()["direction"], n_resamples=50, seed=42)
    assert [(c.id, c.n) for c in out] == [("direction=bearish", 1), ("direction=bullish", 2)]


def test_strategy_horizon_needs_both_fields():
    key = _keys()["strategy_horizon"]
    assert key(BookRow(strategy="RSI")) is None
    assert key(BookRow(horizon="2w")) is None


@pytest.mark.parametrize("entry, exit_date, expected", [
    ("2026-03-20", "2026-03-21", "no"),
    ("2026-03-21", "2026-03-23", "no"),
    ("2026-03-20", "2026-03-22", "yes"),
    ("2026-03-21", "2026-03-29", "yes"),
])
def test_weekend_hold_excludes_entry_and_exit(entry, exit_date, expected):
    row = BookRow(entry_date=entry, exit_date=exit_date)
    assert _keys()["weekend_hold"](row) == expected


@pytest.mark.parametrize("entry, exit_date, expected", [
    ("2026-01-01", "2026-01-02", "no_fomc"),
    ("2026-03-18", "2026-03-18", "fomc_in_hold"),
    ("2027-12-08", "2027-12-08", "fomc_in_hold"),
    ("2027-12-08", "2027-12-09", None),
])
def test_fomc_includes_decision_day_and_honors_last_covered_day(entry, exit_date, expected):
    row = BookRow(entry_date=entry, exit_date=exit_date)
    assert _keys()["fomc_proximity"](row) == expected
