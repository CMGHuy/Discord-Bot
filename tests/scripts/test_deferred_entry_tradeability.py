"""V229-4: the tradeability record -- shifted levels against the day so far,
overnight gaps, the 15:30 bar, plan validity, event days, entry-bar stops."""
import datetime as dt
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "reports"))
from deferred_entry import arms  # noqa: E402
from deferred_entry import bars as tb  # noqa: E402
from deferred_entry import tradeability as tr  # noqa: E402
from swingbot import config  # noqa: E402
from swingbot.core.market import opex  # noqa: E402
from tests.scripts.v229_fixtures import et, five_min  # noqa: E402

D = dt.date(2026, 11, 3)
DAYS = ["2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06", "2026-11-09", "2026-11-10"]
OPENED = et("2026-11-03 10:02")
OVERRIDES = {
    "2026-11-03 11:00": (99.0, 99.2, 98.5, 99.0),      # day low so far 98.5 (stop 98 holds)
    "2026-11-03 15:25": (100.5, 100.7, 100.4, 100.6),  # price as 15:30 arrives
    "2026-11-03 15:30": (101.0, 101.05, 100.95, 101.0),
    "2026-11-04 09:30": (100.8, 100.85, 100.75, 100.8),  # overnight gap +0.8 over the 100 close
}
NO_FLAGS = {"earnings_after_close": False, "monthly_opex": False, "fomc": False, "event_day": False}


@pytest.fixture(autouse=True)
def _frictions(monkeypatch):
    monkeypatch.setattr(config, "SLIPPAGE_BPS", 5.0, raising=False)
    monkeypatch.setattr(config, "COMMISSION_PER_TRADE", 1.0, raising=False)


def _record(frame, **extra):
    priced = arms.price_arms(frame, direction="bullish", entry=100.0, stop=98.0, tp1=104.0,
                             opened_at=OPENED, deferral=tb.deferral_start(D),
                             close=tb.session_close_utc(D), end=tb.horizon_end(D))
    bar = arms.deferral_bar(frame, tb.deferral_start(D), tb.session_close_utc(D))
    kwargs = dict(direction="bullish", entry=100.0, stop=98.0, tp1=104.0, opened_at=OPENED,
                  deferral=bar.name, arms=priced, plan_created_at="2026-11-02 14:00:00+00",
                  expiry_bars="5", closed_at=et("2026-11-03 13:00"), live_reason="tp1",
                  flags=NO_FLAGS)
    kwargs.update(extra)
    return tr.record(frame, **kwargs)


def test_record_has_exactly_the_ledger_keys():
    out = _record(five_min(DAYS, overrides=OVERRIDES))
    assert set(out) == {
        "fill_vs_entry_r", "fill_above_entry", "shifted_stop_above_day_low", "day_low",
        "day_low_vs_stop_r", "price_1530_vs_entry_r", "first_gap_r", "bar_1530",
        "plan_expired", "sessions_since_plan", "entry_bar_stopout", *tr.FLAG_KEYS}
    assert set(out["first_gap_r"]) == {"C", "A", "B"}
    assert set(out["bar_1530"]) == {"volume", "range_r", "open_vs_last_close_r"}


def test_record_values_on_a_crafted_day():
    out = _record(five_min(DAYS, overrides=OVERRIDES))
    assert out["fill_vs_entry_r"] == pytest.approx(0.5) and out["fill_above_entry"] is True
    assert out["day_low"] == pytest.approx(98.5)
    assert out["shifted_stop_above_day_low"] is True          # shifted stop 99 > 98.5
    assert out["day_low_vs_stop_r"] == pytest.approx(0.25)
    assert out["price_1530_vs_entry_r"] == pytest.approx(0.3)
    assert out["first_gap_r"] == pytest.approx({"C": 0.4, "A": 0.4, "B": 0.4})
    assert out["bar_1530"]["volume"] == 1000.0
    assert out["bar_1530"]["range_r"] == pytest.approx(0.05)
    assert out["bar_1530"]["open_vs_last_close_r"] == pytest.approx(0.5)
    assert (out["plan_expired"], out["sessions_since_plan"]) == (False, 1)
    assert out["entry_bar_stopout"] is False


def test_skipped_arm_b_and_same_day_exits_have_no_gap():
    frame = five_min(DAYS, overrides={"2026-11-03 11:00": (99.0, 99.0, 97.9, 98.5),
                                      "2026-11-04 09:30": (100.8, 100.85, 100.75, 100.8)})
    out = _record(frame)
    assert out["first_gap_r"]["B"] is None      # skipped
    assert out["first_gap_r"]["C"] is None      # stopped at 11:00 on the entry day
    assert out["first_gap_r"]["A"] == pytest.approx(0.4)
    assert out["day_low_vs_stop_r"] == pytest.approx(-0.05)


def test_no_lookahead_day_extreme_ignores_bars_from_1530():
    frame = five_min(DAYS, overrides={**OVERRIDES, "2026-11-03 15:40": (100.0, 100.0, 90.0, 95.0)})
    deferral = tb.deferral_start(D)
    kwargs = dict(direction="bullish", session_start=tb.session_open(D), deferral=deferral)
    assert tr.day_extreme(frame, **kwargs) == tr.day_extreme(frame[frame.index < deferral], **kwargs)
    assert tr.day_extreme(frame, **kwargs) == pytest.approx(98.5)
    short = dict(kwargs, direction="bearish")
    assert tr.day_extreme(frame, **short) == pytest.approx(100.7)


@pytest.mark.parametrize("closed, reason, expected", [
    ("2026-11-03 10:04", "loss", True),
    ("2026-11-03 10:04", "STOP", True),
    ("2026-11-03 10:06", "loss", False),
    ("2026-11-03 10:04", "tp1_partial", False),
    (None, "loss", False),
])
def test_entry_bar_stopout(closed, reason, expected):
    frame = five_min([D])
    closed_at = None if closed is None else et(closed)
    assert tr.entry_bar_stopout(frame, opened_at=OPENED, closed_at=closed_at,
                                live_reason=reason) is expected


@pytest.mark.parametrize("created, expiry, expected", [
    ("2026-10-28 14:00:00+00", "3", (True, 4)),    # 29, 30, Nov 2, Nov 3
    ("2026-10-28 14:00:00+00", "5", (False, 4)),
    ("2026-10-28 14:00:00+00", "", (None, 4)),
    ("", "5", (None, None)),
])
def test_plan_expired_under_its_own_rule(created, expiry, expected):
    assert tr.plan_expired(created, expiry, D) == expected


def _lookup(*stamps):
    return lambda ticker: list(stamps)


def test_earnings_after_the_close_on_the_entry_date():
    after = dt.datetime(2026, 11, 3, 16, 5, tzinfo=tb.ET)
    before = dt.datetime(2026, 11, 3, 8, 0, tzinfo=tb.ET)
    naive_after = dt.datetime(2026, 11, 3, 16, 30)
    assert tr.event_flags("AAPL", D, earnings_lookup=_lookup(after))["earnings_after_close"] is True
    assert tr.event_flags("AAPL", D, earnings_lookup=_lookup(before))["earnings_after_close"] is False
    assert tr.event_flags("AAPL", D, earnings_lookup=_lookup(naive_after))["event_day"] is True
    other = dt.datetime(2026, 11, 4, 16, 5, tzinfo=tb.ET)
    assert tr.event_flags("AAPL", D, earnings_lookup=_lookup(other)) == NO_FLAGS


def test_a_failing_earnings_lookup_is_unknown_not_an_error():
    def boom(ticker):
        raise RuntimeError("network")
    out = tr.event_flags("AAPL", D, earnings_lookup=boom)
    assert out["earnings_after_close"] is None and out["event_day"] is False


def test_monthly_opex_and_fomc_days():
    opex_day = opex.monthly_expiration(2026, 11)
    assert tr.event_flags("AAPL", opex_day, earnings_lookup=_lookup())["monthly_opex"] is True
    fomc = tr.event_flags("AAPL", dt.date(2026, 10, 28), earnings_lookup=_lookup())
    assert fomc["fomc"] is True and fomc["event_day"] is True
