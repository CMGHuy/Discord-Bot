"""V191-12: a band plan is stamped and dollar-checked before it is issued;
every band reason reaches the existing 'plan rejected (' line."""
import logging
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.core.edge.heat import trade_risk_pct
from swingbot.core.planning import account
from swingbot.core.planning import gap_sizing as gs
from swingbot.core.scanning import analyze, engine, scan_run
from tests.helpers import make_ohlcv

CFG = {"balance": 10_000.0, "risk_pct": 1.0, "sizing_mode": "risk_pct", "position_pct": 10.0,
       "max_position_pct": 100.0, "max_position_value_absolute": 0, "max_risk_amount_absolute": 0}


@pytest.fixture(autouse=True)
def env(monkeypatch):
    for name, value in [("PLAN_ENGINE_V2", "on"), ("CLAMP_STOP_TO_HARD_CAP", True),
                        ("MIN_RISK_REWARD_RATIO", 1.5), ("MAX_RISK_REWARD_RATIO", 2.5),
                        ("CONFLUENCE_ATR_STOP_FLOOR", 1.0), ("CONFLUENCE_ATR_TARGET_MODE", "rechoose"),
                        ("LONG_GAP_SIZING", False), ("SHORT_GAP_SIZING", True)]:
        monkeypatch.setattr(config, name, value)
    monkeypatch.setattr(account.opex, "size_mult", lambda *a, **k: 1.0)
    for mod in (account, analyze):
        monkeypatch.setattr(mod, "load_account_config", lambda: dict(CFG))


def _attach(stop, target, atr=4.0, direction="bullish", frame=None, now=None):
    scenario = SimpleNamespace(direction=direction, entry=100.0, stop_loss=stop, take_profit=target,
                               target_sources=["EMA21"], stop_sources=["Rolling support"],
                               atr14_pct=atr, stop_distance_pct=abs(100.0 - stop))
    item = SimpleNamespace(plan_v2=None, plan=scenario, previous_confirmed=None,
                           result=SimpleNamespace(ticker="AAPL", horizon_key="4w", trend=direction,
                                                  state_key="k", state_value="v"))
    df = make_ohlcv([100.0] * 60) if frame is None else frame
    engine.attach_plan_v2(item, scenario, df, "AAPL", "4w", level_map=None, now=now)
    return item


def test_a_band_plan_is_issued_with_its_stamp_and_a_dollar_safe_size():
    plan = _attach(99.0, 108.0).plan_v2
    assert (plan.stop_loss, plan.stop_moved_by) == (pytest.approx(96.0), "floor")
    assert plan.gap_sizing[gs.BAND_KEY] == pytest.approx(gs.worst_fill_distance(96.0, 4.25, "bullish"))
    shares = gs.size_for_plan(plan)["shares"]
    assert shares * plan.gap_sizing[gs.BAND_KEY] <= 100.0 + 1e-9
    # heat counts |entry - stop| x shares: a wider stop with fewer shares buys no extra heat
    assert trade_risk_pct({"entry": 100.0, "stop_loss": plan.stop_loss, "shares": shares}, 10_000.0) <= 1.0


def test_the_band_plan_is_stamped_exactly_once(monkeypatch):
    calls = []
    real = analyze.stamp_gap_sizing
    monkeypatch.setattr(analyze, "stamp_gap_sizing", lambda p, df: calls.append(1) or real(p, df))
    assert _attach(99.0, 108.0).plan_v2 is not None
    assert _attach(96.5, 108.0, atr=None).plan_v2 is not None      # today's plan, stamped as today
    assert calls == [1, 1]


@pytest.mark.parametrize("cfg,reason", [({"balance": 10.0}, "band_size_zero"),
                                        ({"sizing_mode": "account_pct"}, "risk_sizing")])
def test_a_band_plan_that_cannot_fit_the_budget_is_refused_and_logged(monkeypatch, caplog, cfg, reason):
    for mod in (account, analyze):
        monkeypatch.setattr(mod, "load_account_config", lambda: {**CFG, **cfg})
    item = _attach(80.0, 160.0, atr=10.0)                            # d 20% untouched in [10, 20]
    assert item.plan_v2 is None and item.plan_v2_rejected == reason
    with caplog.at_level(logging.INFO, logger=scan_run.log.name):
        scan_run._skip_rejected_plan(item, require_confirmation=False)
    assert f"plan rejected ({reason}" in caplog.text


@pytest.mark.parametrize("mode,target,reason", [("rechoose", 104.0, "band_no_target"),
                                                ("keep", 106.0, "band_rr_drop")])
def test_band_no_plan_reasons(monkeypatch, mode, target, reason):
    monkeypatch.setattr(config, "CONFLUENCE_ATR_TARGET_MODE", mode)
    stop, atr = (99.0, 4.0) if mode == "rechoose" else (96.5, 2.5)
    item = _attach(stop, target, atr=atr)
    assert item.plan_v2 is None and item.plan_v2_rejected == reason


def test_a_pre_band_plan_still_uses_risk_sizing_ok(monkeypatch):
    monkeypatch.setattr(config, "CONFLUENCE_ATR_STOP_FLOOR", 0.0)
    monkeypatch.setattr(analyze, "risk_sizing_ok", lambda plan: pytest.fail("consulted"))
    assert _attach(96.5, 108.0).plan_v2.stop_loss == pytest.approx(98.25)


def test_band_stamp_uses_only_completed_bars_at_attachment():
    df = make_ohlcv([100.0] * 61)
    now = datetime.combine(df.index[-1].date(), datetime.min.time(), tzinfo=timezone.utc).replace(hour=16)
    df.loc[df.index[-1], ["Open", "High", "Low", "Close"]] = [200.0, 220.0, 180.0, 210.0]
    full = _attach(99.0, 108.0, frame=df, now=now).plan_v2
    truncated = _attach(99.0, 108.0, frame=df.iloc[:-1], now=now).plan_v2
    assert full is not None and truncated is not None
    assert full.gap_sizing == truncated.gap_sizing
    assert full.stop_loss == truncated.stop_loss
