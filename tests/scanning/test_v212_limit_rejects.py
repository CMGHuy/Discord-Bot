"""v212 on the live attach path (spec rule 9): a drop is recorded with its
bare-token reason and logged by the existing 'plan rejected (' line; a kept
limit reaches item.plan_v2 as a PENDING limit; knob 0 changes nothing."""
import logging
import re
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.core.planning.builders import LIMIT_DROP_REASONS
from swingbot.core.scanning import engine, scan_run
from tests.helpers import make_ohlcv


@pytest.fixture(autouse=True)
def v2_on(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    monkeypatch.setattr(config, "CLAMP_STOP_TO_HARD_CAP", True)
    monkeypatch.setattr(config, "MIN_RISK_REWARD_RATIO", 1.5)
    monkeypatch.setattr(config, "MAX_RISK_REWARD_RATIO", 2.5)


def _scenario(stop, target, direction="bullish", entry=100.0):
    return SimpleNamespace(direction=direction, entry=entry, stop_loss=stop, take_profit=target,
                           target_sources=["EMA21"], stop_sources=["Rolling support"])


def _ranged(entry):
    """A frame whose 20-bar range holds every target: not a breakout
    (scenario_is_breakout), so the plan enters at market, the only entry
    type v212 converts."""
    return make_ohlcv([entry] * 49 + [(entry, entry * 1.12, entry * 0.88, entry)] + [entry] * 10)


def _attach(scenario):
    item = SimpleNamespace(plan_v2=None)
    engine.attach_plan_v2(item, scenario, _ranged(scenario.entry),
                          "AAPL", "4w", level_map=None)
    return item


@pytest.mark.parametrize("direction,stop,target", [("bullish", 96.5, 108.0),
                                                    ("bearish", 103.6, 92.0)])
def test_stop_beyond_two_percent_of_the_limit_is_rejected_with_its_reason(
        monkeypatch, direction, stop, target):
    monkeypatch.setattr(config, "CONFLUENCE_LIMIT_ENTRY_F", 0.5)   # 98.25/96.25 = 2.04%
    item = _attach(_scenario(stop, target, direction=direction))
    assert item.plan_v2 is None
    assert item.plan_v2_rejected == "limit_stop_beyond_cap"


def test_kept_limit_is_attached_pending(monkeypatch):
    ref = _attach(_scenario(96.5, 108.0)).plan_v2
    monkeypatch.setattr(config, "CONFLUENCE_LIMIT_ENTRY_F", 2 / 3)
    plan = _attach(_scenario(96.5, 108.0)).plan_v2
    assert (plan.entry_type, plan.trigger_price, plan.stop_loss) == ("limit", 97.67, 96.25)
    assert (plan.status, plan.expiry_bars, plan.limit_entry_f) == ("PENDING", 3, 2 / 3)
    assert plan.tp1 == ref.tp1 == plan.limit_cancel_level


def test_knob_zero_keeps_the_clamped_market_plan():
    plan = _attach(_scenario(96.5, 108.0)).plan_v2
    assert (plan.entry_type, plan.stop_loss, plan.limit_entry_f) == ("market", pytest.approx(98.25), None)


def test_unclamped_plan_is_untouched_with_the_knob_on(monkeypatch):
    monkeypatch.setattr(config, "CONFLUENCE_LIMIT_ENTRY_F", 0.5)
    assert _attach(_scenario(98.5, 104.0)).plan_v2.entry_type == "market"


def test_no_target_is_still_no_qualifying_target(monkeypatch):
    monkeypatch.setattr(config, "CONFLUENCE_LIMIT_ENTRY_F", 0.5)
    assert _attach(_scenario(98.5, 100.5)).plan_v2_rejected == "no_qualifying_target"


@pytest.mark.parametrize("reason", LIMIT_DROP_REASONS)
def test_reason_survives_the_export_grep(caplog, reason):
    item = SimpleNamespace(plan=SimpleNamespace(stop_distance_pct=3.5), plan_v2_rejected=reason,
                           result=SimpleNamespace(ticker="AAPL", horizon_key="4w", trend="up"))
    with caplog.at_level(logging.INFO):
        scan_run._skip_rejected_plan(item, require_confirmation=False)
    # scripts/ops/export_book_rows.sh reads "(<reason>[,)]" after "plan rejected ("
    assert re.search(r"plan rejected \(([a-z_]+)[,)]", caplog.text).group(1) == reason
