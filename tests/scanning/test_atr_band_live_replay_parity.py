"""V191-10: live and replay admit the same band scenario and build the same
band plan from it -- replay's legacy 2.0% floor and live's 1.75% are both
bypassed by the band, and both refuse d = 1.0% with the floor off."""
from datetime import datetime, timezone

import pytest

from swingbot import config
from swingbot.core.backtesting import backtest_scenarios as bs
from swingbot.core.market import levels
from swingbot.core.market.strategy import HORIZONS
from swingbot.core.planning.plan_engine import build_confluence_plan
from swingbot.core.scanning import analyze, scan_run
from tests.market.test_atr_band import _frame

SAT = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)   # no forming bar
MAP = ([levels.Level(99.0, ["Rolling S/R"])], [levels.Level(108.0, ["Rolling S/R"])])


@pytest.fixture(autouse=True)
def stubs(monkeypatch):
    monkeypatch.setattr(levels, "collect_candidate_levels", lambda *a, **k: [])
    monkeypatch.setattr(levels, "build_level_map", lambda *a, **k: MAP)
    monkeypatch.setattr(bs, "levels_asof", lambda *a, **k: MAP)
    monkeypatch.setattr(analyze, "veto_bullish_for", lambda df: False)
    monkeypatch.setattr(config, "CLAMP_STOP_TO_HARD_CAP", True)
    monkeypatch.setattr(config, "MIN_RISK_REWARD_RATIO", 1.5)
    monkeypatch.setattr(config, "MAX_RISK_REWARD_RATIO", 2.5)
    monkeypatch.setattr(config, "MIN_STOP_DISTANCE_PCT", 1.75)
    monkeypatch.setattr(config, "MIN_REWARD_PCT", 3.0)
    monkeypatch.setattr(config, "MAX_STOP_LOSS_PCT", 7.0)


def _both(monkeypatch, k):
    monkeypatch.setattr(config, "CONFLUENCE_ATR_STOP_FLOOR", k)
    df = _frame(n=80)
    live = analyze._horizon_scenarios(df, HORIZONS["4w"], 100.0, [], scan_run._hard_filters_snapshot(),
                                      ticker="XYZ", now=SAT).scenarios
    params, _ = bs._replay_params(None, bs.CONFLUENCE_GATES)
    replay = bs.scenarios_at("XYZ", df, len(df) - 1, "4w", params, {})[-1]
    return df, [s for s in live if s.direction == "bullish"], [s for s in replay if s.direction == "bullish"]


def test_floor_off_both_refuse_a_one_percent_stop(monkeypatch):
    _, live, replay = _both(monkeypatch, 0.0)
    assert live == [] and replay == []


def test_floor_on_both_admit_and_build_the_same_band_plan(monkeypatch):
    df, (live,), (replay,) = _both(monkeypatch, 1.0)
    assert live.atr14_pct == replay.atr14_pct == pytest.approx(4.0)
    plans = [build_confluence_plan(sc, df, ticker="XYZ", horizon_key="4w",
                                   primary_strategy="S/R Confluence") for sc in (live, replay)]
    key = [(p.stop_loss, p.stop_ceiling_pct, p.stop_moved_by, p.tp1) for p in plans]
    assert key[0] == key[1] == (pytest.approx(96.0), pytest.approx(4.25), "floor", pytest.approx(108.0))
