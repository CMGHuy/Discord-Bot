"""v176 live-book counterfactual: a live give-back exit vs the flag-off exit from daily bars."""
import sys
from pathlib import Path

import pytest

from tests.helpers import make_ohlcv

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "reports"))

import giveback_live_counterfactual as glc  # noqa: E402

FLOOR = 100.0 + (2.0 / 3.0) * 10.0
BEAR_FLOOR = 100.0 - (2.0 / 3.0) * 10.0


def _plan(direction="bullish", **leg_kw):
    bull = direction == "bullish"
    leg = {"fraction": 0.5, "exit_price": 114.0 if bull else 86.0, "r": 2.8,
           "reason": "tp1_runner_trail", "closed_at": "2021-01-07T15:00:00+00:00",
           "stop_source": "giveback", "giveback_pct": 5.0,
           "giveback_extreme": 120.0 if bull else 80.0, "giveback_stop": 114.0 if bull else 84.0}
    leg.update(leg_kw)
    return {"plan_id": "p1", "ticker": "AAA", "direction": direction, "status": "CLOSED",
            "entry_price": 100.0, "stop_loss": 95.0 if bull else 105.0,
            "tp1": 110.0 if bull else 90.0, "tp2": None, "trail_atr_mult": 50.0,
            "legs_realized": [{"fraction": 0.5, "exit_price": 110.0, "r": 2.0,
                               "reason": "tp1_partial"}, leg]}


FLAT = [(100.0, 101.0, 99.0, 100.0)] * 3                  # 2021-01-04..06


def test_long_runner_would_have_ridden_to_the_floor():
    bars = make_ohlcv(FLAT + [(115.0, 116.0, 113.0, 113.5),   # exit day 01-07
                              (113.5, 114.0, 108.0, 109.0),
                              (109.0, 110.0, 106.0, 106.5)], start="2021-01-04")
    out = glc.counterfactual_exit(_plan(), bars)
    assert out["exit_date"] == "2021-01-07"
    assert out["cf_start_stop"] == pytest.approx(FLOOR)      # chandelier at mult 50 is far below
    assert out["cf_reason"] == "floor"
    assert out["cf_date"] == "2021-01-11"
    assert out["cf_exit"] == pytest.approx(FLOOR)
    assert out["cf_r"] == pytest.approx((FLOOR - 100.0) / 5.0)
    assert out["delta_r"] == pytest.approx(2.8 - (FLOOR - 100.0) / 5.0)


def test_a_gap_through_the_floor_fills_at_the_open():
    bars = make_ohlcv(FLAT + [(115.0, 116.0, 113.0, 113.5), (104.0, 105.0, 103.0, 104.5)],
                      start="2021-01-04")
    out = glc.counterfactual_exit(_plan(), bars)
    assert out["cf_exit"] == pytest.approx(104.0)


def test_short_runner_never_stopped_is_marked_open_at_the_last_close():
    bars = make_ohlcv(FLAT + [(85.0, 87.0, 84.5, 86.5), (86.5, 90.0, 85.0, 89.0)],
                      start="2021-01-04")
    out = glc.counterfactual_exit(_plan("bearish"), bars)
    assert out["cf_start_stop"] == pytest.approx(BEAR_FLOOR)
    assert out["cf_reason"] == "open"
    assert out["cf_exit"] == pytest.approx(89.0)
    assert out["cf_r"] == pytest.approx((100.0 - 89.0) / 5.0)


def test_no_bars_from_the_exit_day_is_reported_not_guessed():
    bars = make_ohlcv(FLAT, start="2021-01-04")
    assert glc.counterfactual_exit(_plan(), bars)["cf_reason"] == "no_bars"


def test_only_closed_plans_with_a_giveback_runner_leg_are_counted():
    trail = _plan(stop_source="trail")
    still_open = dict(_plan(), status="PARTIAL")
    assert [p["plan_id"] for p in glc.giveback_plans([_plan(), trail, still_open])] == ["p1"]


def test_main_withholds_a_conclusion_below_thirty(monkeypatch, capsys):
    bars = make_ohlcv(FLAT + [(115.0, 116.0, 113.0, 113.5)], start="2021-01-04")
    monkeypatch.setattr(glc, "_records", lambda: [_plan()])
    monkeypatch.setattr(glc, "_bars", lambda ticker: bars)
    assert glc.main([]) == 0
    out = capsys.readouterr().out
    assert "no conclusion below 30 give-back exits" in out
    assert "AAA" in out
