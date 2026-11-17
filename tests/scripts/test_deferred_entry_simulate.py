"""V229-2: the single-leg race -- stop before target, breakeven protecting
later bars only, the five-session mark, gap fills, and parity with the
backtest's round-1 walk on a no-gap path."""
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "reports"))
from deferred_entry import bars as tb  # noqa: E402
from deferred_entry import simulate as sim  # noqa: E402
from swingbot.core.planning.exit_sim import _single_leg_exit_walk  # noqa: E402
from swingbot.core.planning.plan_types import PlanStatus, TradePlanV2  # noqa: E402
from tests.scripts.v229_fixtures import et, five_min  # noqa: E402

DAY = "2026-11-03"
LONG = dict(direction="bullish", fill=100.0, stop=98.0, tp1=104.0)  # trigger at 102
SHORT = dict(direction="bearish", fill=100.0, stop=102.0, tp1=96.0)
END = et("2026-11-03 16:00")


def _race(frame, start="2026-11-03 10:05", end=END, **levels):
    return sim.race(frame, start=et(start), end=end, **(levels or LONG))


def test_stop_is_checked_before_target_inside_one_bar():
    frame = five_min([DAY], overrides={f"{DAY} 10:30": (100.0, 104.5, 97.9, 100.0)})
    out = _race(frame)
    assert (out.outcome, out.exit_price, out.exit_ts) == ("loss", 98.0, et(f"{DAY} 10:30"))
    assert sim.gross_r(out, direction="bullish", fill=100.0, risk=2.0) == pytest.approx(-1.0)


def test_target_reached_is_a_win_at_tp1():
    frame = five_min([DAY], overrides={f"{DAY} 10:30": (101.0, 105.0, 100.9, 104.5)})
    out = _race(frame)
    assert (out.outcome, out.exit_price) == ("win", 104.0)
    assert sim.gross_r(out, direction="bullish", fill=100.0, risk=2.0) == pytest.approx(2.0)


def test_breakeven_move_protects_later_bars_only():
    frame = five_min([DAY], overrides={
        f"{DAY} 10:30": (100.5, 102.3, 99.5, 102.0),   # reaches 102, dips below the fill
        f"{DAY} 10:35": (101.0, 101.2, 99.8, 100.0)})  # the moved stop is hit here
    out = _race(frame)
    assert out.outcome == "scratch" and out.stop_moved
    assert out.exit_ts == et(f"{DAY} 10:35") and out.exit_price == 100.0
    assert sim.gross_r(out, direction="bullish", fill=100.0, risk=2.0) == 0.0


def test_timeout_marks_to_the_close_of_the_fifth_session_after_entry():
    days = ["2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06",
            "2026-11-09", "2026-11-10", "2026-11-11"]
    frame = five_min(days, overrides={"2026-11-10 15:55": (100.0, 100.4, 99.9, 100.3),
                                      "2026-11-11 10:00": (99.0, 99.0, 90.0, 91.0)})
    out = _race(frame, end=tb.horizon_end(pd.Timestamp(DAY).date()))
    assert out.outcome == "timeout"
    assert out.exit_ts == et("2026-11-10 15:55") and out.exit_price == 100.3


def test_gap_through_the_stop_at_a_session_open_fills_at_the_open():
    frame = five_min([DAY, "2026-11-04"],
                     overrides={"2026-11-04 09:30": (97.0, 97.5, 96.5, 97.2)})
    out = _race(frame, end=et("2026-11-04 16:00"))
    assert (out.outcome, out.exit_price, out.gap_stop) == ("loss", 97.0, True)
    assert sim.gross_r(out, direction="bullish", fill=100.0, risk=2.0) == pytest.approx(-1.5)


def test_a_mid_session_open_through_the_stop_fills_at_the_open_without_the_gap_flag():
    frame = five_min([DAY], overrides={f"{DAY} 11:00": (97.5, 97.8, 97.0, 97.6)})
    out = _race(frame)
    assert (out.outcome, out.exit_price, out.gap_stop) == ("loss", 97.5, False)


def test_bars_before_start_and_at_end_are_not_raced():
    frame = five_min([DAY], overrides={f"{DAY} 10:00": (99.0, 99.0, 97.0, 98.5),
                                       f"{DAY} 15:00": (99.0, 99.0, 97.0, 98.5)})
    out = _race(frame, start="2026-11-03 10:05", end=et(f"{DAY} 15:00"))
    assert out.outcome == "timeout" and out.exit_ts == et(f"{DAY} 14:55")


@pytest.mark.parametrize("bar, outcome, price, r", [
    ((100.0, 102.2, 99.9, 101.0), "loss", 102.0, -1.0),
    ((99.0, 99.1, 95.8, 96.0), "win", 96.0, 2.0),
])
def test_bearish_mirror(bar, outcome, price, r):
    frame = five_min([DAY], overrides={f"{DAY} 10:30": bar})
    out = _race(frame, **SHORT)
    assert (out.outcome, out.exit_price) == (outcome, price)
    assert sim.gross_r(out, direction="bearish", fill=100.0, risk=2.0) == pytest.approx(r)


def test_no_bars_in_the_window():
    out = _race(five_min([DAY]), start="2026-11-03 16:30", end=et("2026-11-03 17:00"))
    assert out == sim.Race("no_bars", None, None, False, False)
    assert sim.gross_r(out, direction="bullish", fill=100.0, risk=2.0) == 0.0
    assert sim.race(None, start=et(f"{DAY} 10:00"), end=END, **LONG).outcome == "no_bars"


def test_unknown_direction_and_zero_risk_are_refused():
    with pytest.raises(ValueError, match="direction"):
        _race(five_min([DAY]), direction="long", fill=100.0, stop=98.0, tp1=104.0)
    with pytest.raises(ValueError, match="risk"):
        sim.gross_r(sim.Race("loss", 98.0, None, False, False),
                    direction="bullish", fill=100.0, risk=0.0)


def _plan():
    return TradePlanV2(
        plan_id="p", ticker="XYZ", created_at=DAY, source="confluence",
        strategy="S/R Confluence", horizon_key="4w", direction="bullish", entry_type="stop_entry",
        trigger_price=100.0, entry_price=None, expiry_bars=5, stop_loss=98.0, tp1=104.0,
        tp1_fraction=0.5, tp2=None, breakeven_trigger_fraction=0.5, trail_atr_mult=2.0,
        quality_score=0, quality_breakdown=[], badge="WEAK", badge_stats={},
        status=PlanStatus.PENDING, acceptance_level=None)


@pytest.mark.parametrize("overrides", [
    {f"{DAY} 10:30": (99.0, 99.2, 97.5, 98.0)},                                    # loss
    {f"{DAY} 10:30": (101.0, 104.2, 100.9, 104.0)},                                # win
    {f"{DAY} 10:30": (100.5, 102.3, 99.5, 102.0), f"{DAY} 10:35": (101.0, 101.2, 99.8, 100.0)},
    {},                                                                            # timeout
])
def test_parity_with_the_backtest_round_one_walk_on_a_no_gap_path(overrides):
    frame = five_min([DAY], overrides=overrides)
    k = list(frame.index).index(et(f"{DAY} 10:00"))
    walk = _single_leg_exit_walk(frame, k, 100.0, _plan(), len(frame))
    out = sim.race(frame, start=frame.index[k + 1], end=END, **LONG)
    assert out.outcome == walk.outcome
    assert out.exit_price == pytest.approx(walk.legs[0]["exit_price"])
