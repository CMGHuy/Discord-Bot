"""V229-3: arms C, A, B -- distance-preserving levels, the strictly-before
skip rule, frictions through screen.sides.net_r, zero frictions refused."""
import dataclasses
import datetime as dt
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "reports"))
from deferred_entry import arms  # noqa: E402
from deferred_entry import bars as tb  # noqa: E402
from swingbot import config  # noqa: E402
from swingbot.core.backtesting.screen.sides import net_r  # noqa: E402
from tests.scripts.v229_fixtures import et, five_min  # noqa: E402

D = dt.date(2026, 11, 3)
DAYS = ["2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06", "2026-11-09", "2026-11-10"]
OPENED = "2026-11-03 10:02"


@pytest.fixture(autouse=True)
def _frictions(monkeypatch):
    monkeypatch.setattr(config, "SLIPPAGE_BPS", 5.0, raising=False)
    monkeypatch.setattr(config, "COMMISSION_PER_TRADE", 1.0, raising=False)
    monkeypatch.setattr(config, "COMMISSION_RISK_BASIS", 100.0, raising=False)


def _price(frame, direction="bullish", entry=100.0, stop=98.0, tp1=104.0):
    return arms.price_arms(
        frame, direction=direction, entry=entry, stop=stop, tp1=tp1,
        opened_at=et(OPENED), deferral=tb.deferral_start(D),
        close=tb.session_close_utc(D), end=tb.horizon_end(D))


def test_shifted_levels_keep_the_plan_distances_both_ways():
    assert arms.shifted_levels(101.0, entry=100.0, stop=98.0, tp1=104.0) == (99.0, 105.0)
    assert arms.shifted_levels(99.0, entry=100.0, stop=102.0, tp1=96.0) == (101.0, 95.0)


def test_arm_a_fills_at_the_1530_open_with_shifted_levels():
    frame = five_min(DAYS, overrides={"2026-11-03 15:30": (101.0, 101.05, 100.95, 101.0)})
    out = _price(frame)
    assert set(out) == set(arms.ARMS)
    a = out["A"]
    assert (a.fill, a.stop, a.tp1, a.taken) == (101.0, 99.0, 105.0, True)
    assert out["C"].fill == 100.0 and out["C"].stop == 98.0


def test_every_arm_is_net_of_frictions_and_the_deferred_arms_pay_double_entry_slippage():
    frame = five_min(DAYS, overrides={"2026-11-03 15:30": (101.0, 101.05, 100.95, 101.0)})
    out = _price(frame)
    c, a = out["C"], out["A"]
    assert c.outcome == a.outcome == "timeout"
    assert c.r_net == pytest.approx(net_r(100.0, 100.0, 2.0, direction="long", days=0))
    assert a.r_net == pytest.approx(net_r(101.0, 100.0, 2.0, direction="long", days=0, entry_bps=10.0))
    assert a.r_gross == pytest.approx(-0.5) and a.r_net < a.r_gross
    assert c.r_gross == 0.0 and c.r_net < 0.0


@pytest.mark.parametrize("field, value", [("SLIPPAGE_BPS", 0.0), ("COMMISSION_PER_TRADE", 0.0)])
def test_zero_frictions_are_refused(monkeypatch, field, value):
    monkeypatch.setattr(config, field, value, raising=False)
    with pytest.raises(arms.FrictionsError):
        _price(five_min(DAYS))


def test_arm_b_skips_when_the_stop_traded_before_1530():
    frame = five_min(DAYS, overrides={"2026-11-03 11:00": (99.0, 99.0, 97.9, 98.5)})
    out = _price(frame)
    b = out["B"]
    assert (b.taken, b.outcome, b.r_net, b.r_gross, b.fill) == (False, "skipped", 0.0, 0.0, None)
    assert out["C"].outcome == "loss"


def test_arm_b_equals_arm_a_without_a_touch():
    frame = five_min(DAYS, overrides={"2026-11-03 11:00": (99.0, 99.0, 98.05, 98.5)})
    out = _price(frame)
    assert out["B"].taken and out["B"] == dataclasses.replace(out["A"], arm="B")


def test_a_touch_inside_the_entry_bar_is_excluded_like_the_control():
    frame = five_min(DAYS, overrides={"2026-11-03 10:00": (100.0, 100.1, 97.5, 99.9)})
    out = _price(frame)
    assert out["B"].taken
    assert out["C"].outcome == "timeout"


def test_a_touch_in_the_1530_bar_does_not_skip_arm_b():
    frame = five_min(DAYS, overrides={"2026-11-03 15:30": (100.0, 100.1, 97.0, 99.0)})
    out = _price(frame)
    assert out["B"].taken and out["B"].outcome == "loss"


@pytest.mark.parametrize("low", [97.9, 98.05])
def test_no_lookahead_removing_bars_from_1530_leaves_the_skip_decision_unchanged(low):
    frame = five_min(DAYS, overrides={"2026-11-03 11:00": (99.0, 99.0, low, 98.5),
                                      "2026-11-04 10:00": (99.0, 99.0, 90.0, 95.0)})
    deferral = tb.deferral_start(D)
    kwargs = dict(direction="bullish", stop=98.0, start=et(OPENED), deferral=deferral)
    truncated = frame[frame.index < deferral]
    assert arms.held_touched(truncated, **kwargs) == arms.held_touched(frame, **kwargs)


def test_no_deferral_bar_is_refused():
    frame = five_min(DAYS)
    frame = frame[~((frame.index >= tb.deferral_start(D)) & (frame.index < tb.session_close_utc(D)))]
    assert arms.deferral_bar(frame, tb.deferral_start(D), tb.session_close_utc(D)) is None
    with pytest.raises(ValueError, match="deferral"):
        _price(frame)


def test_bearish_arms_mirror_and_pay_borrow_over_calendar_days():
    frame = five_min(DAYS, overrides={"2026-11-03 11:00": (101.0, 102.1, 100.9, 101.5)})
    out = _price(frame, direction="bearish", entry=100.0, stop=102.0, tp1=96.0)
    assert out["C"].outcome == "loss" and not out["B"].taken
    a = out["A"]
    assert (a.stop, a.tp1) == (102.0, 96.0) and a.outcome == "timeout"
    held = (dt.date(2026, 11, 10) - D).days
    assert a.r_net == pytest.approx(
        net_r(100.0, 100.0, 2.0, direction="short", days=held, entry_bps=10.0))


def test_to_dict_carries_the_pair_keys_in_order():
    out = _price(five_min(DAYS))
    assert list(out["C"].to_dict()) == ["arm", "taken", "fill", "stop", "tp1", "outcome",
                                        "r_net", "r_gross", "exit_ts", "gap_stop"]
    assert out["C"].to_dict()["exit_ts"] == et("2026-11-10 15:55").isoformat()


def test_unknown_direction_and_zero_risk_are_refused():
    with pytest.raises(ValueError):
        _price(five_min(DAYS), direction="long")
    with pytest.raises(ValueError, match="risk"):
        _price(five_min(DAYS), stop=100.0)
