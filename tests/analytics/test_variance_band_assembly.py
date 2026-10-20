"""v175 § 1: ``variance_band(closed)``, the whole band.

Books are built on dated weeks starting Monday 2025-01-06; every trade
closes at 20:00 UTC (15:00 or 16:00 in New York, the same date). Entry 100,
stop 99, bullish: a trade's R is ``exit_price - 100`` and its dollar risk
is ``shares * 1``. ``FAST`` shrinks the bootstrap so the file stays quick;
the timing test runs the real sizes.
"""
import time
from datetime import date, timedelta

import numpy as np
import pytest

from swingbot.core.analytics import variance_band as vb
from swingbot.core.analytics.variance_band import CloseDay

MONDAY = date(2025, 1, 6)
FAST = {"paths": 2_000, "outer": 20, "outer_paths": 200}
POSITIVE = (2.0, -1.0, -1.0, 2.0, -1.0)            # +1R every 5-day week
NEGATIVE = (-1.0, -1.0, 2.0, -1.0, -1.0)           # -2R every 5-day week
NOISY = (2.0, -1.0, -1.0, -1.0, 2.0, -1.0, 2.0, -1.0, -1.0, 0.5)   # mean +0.05R
FULL_KEYS = {"status", "scope", "asof", "days", "weeks", "pool", "composition",
             "horizons", "current", "expr", "dollars"}


def _dates(per_week, start_week=0):
    """Dates: ``per_week[i]`` consecutive days from the Monday of week i."""
    out = []
    for w, k in enumerate(per_week, start=start_week):
        out += [MONDAY + timedelta(days=7 * w + i) for i in range(k)]
    return out


def _trade(r, d, *, plan_id="plan-1", shares=10.0, horizon="swing"):
    return {"entry": 100.0, "stop_loss": 99.0, "direction": "bullish",
            "exit_price": 100.0 + r, "closed_at": f"{d.isoformat()}T20:00:00+00:00",
            "status": "loss" if r < 0 else "win", "plan_id": plan_id,
            "shares": shares, "horizon_key": horizon}


def _book(dates, pattern=POSITIVE, **kw):
    return [_trade(pattern[i % len(pattern)], d, **kw) for i, d in enumerate(dates)]


def _band(closed):
    return vb.variance_band(closed, **FAST)


def test_99_close_days_are_insufficient():
    book = _book(_dates([5] * 19 + [4]))                 # 99 days over 20 weeks
    assert _band(book) == {"status": "insufficient", "scope": "whole_book",
                           "days": 99, "weeks": 20}


def test_19_weeks_are_insufficient():
    book = _book(_dates([7] * 6 + [5] * 13))             # 107 days over 19 weeks
    assert _band(book) == {"status": "insufficient", "scope": "whole_book",
                           "days": 107, "weeks": 19}


def test_an_empty_book_is_insufficient():
    assert _band([]) == {"status": "insufficient", "scope": "whole_book",
                         "days": 0, "weeks": 0}


def test_trades_without_r_do_not_count_toward_the_floor():
    book = _book(_dates([5] * 20))
    book[0] = {**book[0], "exit_price": None}
    assert _band(book)["status"] == "insufficient"


def test_full_band_shape_at_100_days_over_20_weeks():
    dates = _dates([5] * 20)
    band = _band(_book(dates))
    assert set(band) == FULL_KEYS
    assert (band["status"], band["scope"], band["pool"]) == ("ok", "whole_book", "v2")
    assert (band["days"], band["weeks"]) == (100, 20)
    assert band["asof"] == dates[-1].isoformat()
    assert [h["horizon"] for h in band["horizons"]] == [20, 50]
    assert [h["weeks_span"] for h in band["horizons"]] == [4.0, 10.0]
    for entry in band["horizons"]:
        assert set(entry) == {"horizon", "weeks_span", "run", "drawdown"}
        assert set(entry["run"]) == set(entry["drawdown"]) == {"p80", "p95", "p95_lo", "p95_hi"}
    assert set(band["current"]) == {"run", "run_age_days", "drawdown", "drawdown_age_days",
                                    "run_zone", "drawdown_zone", "zone"}
    assert set(band["expr"]) == {"value", "n", "start", "end", "ci", "not_positive"}


def test_band_is_reproducible():
    book = _book(_dates([5] * 22), pattern=NOISY)
    assert _band(book) == _band(book)


def test_pool_is_v2_once_v2_alone_reaches_the_floor():
    legacy = _book(_dates([5] * 6), plan_id=None)                   # 30 days, weeks 0-5
    v2 = _book(_dates([5] * 20, start_week=6))                      # 100 days, weeks 6-25
    band = _band(legacy + v2)
    assert (band["pool"], band["days"], band["weeks"]) == ("v2", 100, 20)
    assert band["composition"]["days_by_era"] == {"v2": 100, "legacy": 30}
    assert band["expr"]["n"] == 100
    assert band["expr"]["start"] == (MONDAY + timedelta(weeks=6)).isoformat()


def test_pool_is_the_whole_book_until_v2_reaches_the_floor():
    legacy = _book(_dates([5] * 12), plan_id=None)                  # 60 days
    v2 = _book(_dates([5] * 10, start_week=12))                     # 50 days
    band = _band(legacy + v2)
    assert (band["pool"], band["days"], band["weeks"]) == ("all", 110, 22)
    assert band["composition"]["days_by_era"] == {"v2": 50, "legacy": 60}
    assert band["expr"]["n"] == 110


def test_pool_trades_and_era_of():
    v2 = _book(_dates([5] * 20))
    legacy = _book(_dates([5] * 2, start_week=30), plan_id=None)
    assert vb.era_of(v2[0]) == "v2"
    assert vb.era_of(legacy[0]) == "legacy"
    assert vb.era_of({**v2[0], "plan_id": ""}) == "legacy"
    assert vb.pool_trades(v2 + legacy) == (v2, "v2")
    assert vb.pool_trades(v2[:-1] + legacy) == (v2[:-1] + legacy, "all")


def test_composition_counts_trades_per_horizon_with_unknown():
    dates = _dates([5] * 20)
    book = _book(dates[:60], horizon="swing") + _book(dates[60:90], horizon="position")
    book += _book(dates[90:], horizon=None)
    book.append(_trade(2.0, dates[0], horizon="swing", plan_id=None))   # same date, legacy
    assert vb.composition(book) == {
        "days_by_era": {"v2": 100, "legacy": 1},
        "trades_by_horizon": {"position": 30, "swing": 61, "unknown": 10},
    }


def test_expr_positive_book_has_no_caveat():
    dates = _dates([5] * 20)
    expr = _band(_book(dates))["expr"]
    assert expr["value"] == pytest.approx(0.2)
    assert expr["n"] == 100
    assert (expr["start"], expr["end"]) == (dates[0].isoformat(), dates[-1].isoformat())
    assert expr["ci"][0] > 0
    assert expr["not_positive"] is False


def test_expr_not_positive_when_negative():
    expr = _band(_book(_dates([5] * 20), pattern=NEGATIVE))["expr"]
    assert expr["value"] == pytest.approx(-0.4)
    assert expr["not_positive"] is True


def test_expr_not_positive_when_the_interval_includes_zero():
    expr = _band(_book(_dates([5] * 20), pattern=NOISY))["expr"]
    assert expr["value"] > 0
    assert expr["ci"][0] <= 0 <= expr["ci"][1]
    assert expr["not_positive"] is True


def test_expr_block_values_are_rounded_and_input_order_free():
    book = _book(_dates([5] * 20), pattern=NOISY)
    days = vb.close_days(book)
    forward = vb.expr_block(book, days)
    backward = vb.expr_block(list(reversed(book)), days)
    assert forward == backward
    assert forward["value"] == round(forward["value"], 3)
    assert all(v == round(v, 3) for v in forward["ci"])


def test_expr_block_of_an_empty_pool():
    assert vb.expr_block([], []) == {"value": None, "n": 0, "start": None, "end": None,
                                     "ci": None, "not_positive": True}


def test_dollars_from_the_median_per_trade_risk():
    dates = _dates([5] * 20)
    book = _book(dates[:50], shares=10.0) + _book(dates[50:], shares=30.0)
    book[0] = {**book[0], "shares": 20.0}        # risks: 49 x 10, 1 x 20, 50 x 30
    band = _band(book)
    assert band["dollars"] == {"median_risk": 25.0,
                               "drawdown_usd": round(band["current"]["drawdown"] * 25.0, 2)}


def test_dollars_omitted_when_no_trade_has_shares():
    band = _band(_book(_dates([5] * 20), shares=None))
    assert band["status"] == "ok"
    assert "dollars" not in band


def test_dollars_block_skips_zero_risk_and_missing_prices():
    trade = _trade(-1.0, MONDAY)
    assert vb.dollars_block([{**trade, "shares": 0}], 2.0) is None
    assert vb.dollars_block([{**trade, "stop_loss": 100.0}], 2.0) is None
    assert vb.dollars_block([{**trade, "entry": None}], 2.0) is None
    assert vb.dollars_block([trade], 2.5) == {"median_risk": 10.0, "drawdown_usd": 25.0}


def _band50(run=(2, 4), drawdown=(3.0, 5.0)):
    return {"horizon": 50, "weeks_span": 10.0,
            "run": {"p80": run[0], "p95": run[1], "p95_lo": run[1], "p95_hi": run[1]},
            "drawdown": {"p80": drawdown[0], "p95": drawdown[1],
                         "p95_lo": drawdown[1], "p95_hi": drawdown[1]}}


def _days(*rs, start=date(2026, 3, 2)):
    return [CloseDay(start + timedelta(days=i), r, vb.day_kind(r)) for i, r in enumerate(rs)]


@pytest.mark.parametrize("losses, run_zone", [(2, "normal"), (3, "rough"), (4, "rough"),
                                              (5, "outside")])
def test_current_run_zone_boundaries(losses, run_zone):
    days = _days(*([10.0] + [-0.2] * losses))       # small losses: drawdown stays normal
    current = vb.current_state(days, _band50())
    assert current["run"] == losses
    assert current["run_zone"] == run_zone
    assert current["drawdown_zone"] == "normal"
    assert current["zone"] == run_zone


@pytest.mark.parametrize("drawdown, dd_zone", [(3.0, "normal"), (3.5, "rough"), (5.0, "rough"),
                                               (5.5, "outside")])
def test_current_drawdown_zone_boundaries(drawdown, dd_zone):
    days = _days(10.0, -drawdown)                   # one loss day: run 1, normal
    current = vb.current_state(days, _band50())
    assert current["drawdown"] == drawdown
    assert current["drawdown_zone"] == dd_zone
    assert current["run_zone"] == "normal"
    assert current["zone"] == dd_zone


def test_current_state_ages_are_inclusive_calendar_days():
    days = _days(2.0, -1.0, 0.0, -1.0)              # 2026-03-02 .. 2026-03-05
    current = vb.current_state(days, _band50())
    assert (current["run"], current["run_age_days"]) == (2, 3)          # 03-03 to 03-05
    assert (current["drawdown"], current["drawdown_age_days"]) == (2.0, 4)  # peak 03-02


def test_current_state_at_a_peak_has_no_ages():
    current = vb.current_state(_days(-1.0, 2.0), _band50())
    assert current == {"run": 0, "run_age_days": None, "drawdown": 0.0,
                       "drawdown_age_days": None, "run_zone": "normal",
                       "drawdown_zone": "normal", "zone": "normal"}


def test_tie_band_skips_rough():
    days = _days(*([10.0] + [-0.2] * 5))
    current = vb.current_state(days, _band50(run=(4, 4)))
    assert current["run_zone"] == "outside"


@pytest.mark.slow
def test_one_full_size_band_on_300_close_days_is_fast():
    rng = np.random.default_rng(7)
    pattern = tuple(rng.choice([-1.0, 1.5, 0.0], size=300, p=[0.5, 0.4, 0.1]))
    book = _book(_dates([5] * 60), pattern=pattern)
    started = time.process_time()
    band = vb.variance_band(book)
    elapsed = time.process_time() - started
    assert band["status"] == "ok"
    assert elapsed < 5.0, f"variance_band took {elapsed:.1f}s of CPU"
