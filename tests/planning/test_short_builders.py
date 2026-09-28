"""v104 §3 sizing: structure stop verbatim (<= max_risk_pct) or no plan; targets below entry."""
import numpy as np
import pytest

from swingbot import config
from swingbot.core.backtesting.backtest import run_backtest
from swingbot.core.market import short_entries as se
from swingbot.core.market.entry_filters import DEFAULT_PARAMS, gate_override
from swingbot.core.market.indicators import atr
from swingbot.core.planning import short_builders as sb
from swingbot.core.planning.builders import build_strategy_plan
from tests.helpers import make_ohlcv
from tests.market.test_short_entries import HZ, PAD

# b=40 breaks out, t=41 traps; 20 quiet bars after so an uncapped short can
# run to its 14-bar 2w timeout inside the frame (stop 103 and TP1 ~96.5 are never touched).
TRAP = [(100.5, 102.5, 100.0, 102.0), (101.5, 102.0, 100.0, 100.5)]


@pytest.fixture(autouse=True)
def rr(monkeypatch):
    monkeypatch.setattr(config, "MIN_RISK_REWARD_RATIO", 1.5, raising=False)
    monkeypatch.setattr(config, "MAX_RISK_REWARD_RATIO", 2.5, raising=False)
    monkeypatch.setattr(config, "LEVEL_LIFECYCLE_STOPS_ENABLED", False, raising=False)


def _inputs():
    df = make_ohlcv(PAD + TRAP + [(100.0, 101.0, 99.0, 100.0)] * 20, start="2015-01-02")
    t = 41
    return df, t, float(df["Close"].iloc[t]), float(atr(df, 14).iloc[t])


def test_plan_short_uses_the_structure_stop_and_a_lower_target():
    df, t, entry, atr_val = _inputs()
    stop, tp1, candidates = sb.plan_short(df, t, "Bull Trap", HZ, "bearish", entry=entry, atr_val=atr_val)
    assert stop == pytest.approx(se.structure_at("Bull Trap", df, t, HZ)["stop"])
    risk = stop - entry
    assert entry - tp1 >= 1.5 * risk - 1e-9 and entry - tp1 <= 2.5 * risk + 1e-9
    assert 99.0 in candidates


def test_plan_short_refuses_bullish_and_non_signal_bars():
    df, t, entry, atr_val = _inputs()
    assert sb.plan_short(df, t, "Bull Trap", HZ, "bullish", entry=entry, atr_val=atr_val) is None
    assert sb.plan_short(df, t - 1, "Bull Trap", HZ, "bearish", entry=entry, atr_val=atr_val) is None


def test_plan_short_drops_a_stop_beyond_max_risk_pct(monkeypatch):
    df, t, entry, atr_val = _inputs()
    monkeypatch.setattr(sb, "structure_at", lambda *a, **k: {"stop": entry * 1.05, "target_a": np.nan,
                                                             "target_b": np.nan})
    assert sb.plan_short(df, t, "Bull Trap", HZ, "bearish", entry=entry, atr_val=atr_val) is None  # 5% > 3% (2w)


def test_hold_cap_reads_the_earnings_setting(monkeypatch):
    df, t, _, _ = _inputs()
    assert sb.short_hold_cap(df, t, "Bull Trap") is None                        # hold
    assert sb.short_hold_cap(df, t, "MACD") is None
    monkeypatch.setitem(DEFAULT_PARAMS["Bull Trap"], "earnings", "exit_before")
    with pytest.raises(ValueError):
        sb.short_hold_cap(df, t, "Bull Trap")
    df["evt_bars_to_next"] = np.nan
    assert sb.short_hold_cap(df, t, "Bull Trap") is None
    df.loc[df.index[t], "evt_bars_to_next"] = 4
    assert sb.short_hold_cap(df, t, "Bull Trap") == 3


def test_build_strategy_plan_builds_the_short():
    df, t, _, _ = _inputs()
    plan = build_strategy_plan(df, t, ticker="TEST", strategy="Bull Trap", horizon_key=HZ, direction="bearish")
    assert plan is not None and plan.direction == "bearish" and plan.stop_loss > plan.trigger_price > plan.tp1
    assert plan.trail_atr_mult == 2.5 and plan.tp2 is None          # spec §3: trail 2.5, TP2 off


def test_backtest_trades_the_short_and_honours_the_hold_cap(monkeypatch):
    df, t, _, _ = _inputs()
    with gate_override("Bull Trap", {"directions": ("bearish",)}):
        free = run_backtest("TEST", df, "Bull Trap", HZ, exit_model="v2", scale_out=True)
        monkeypatch.setitem(DEFAULT_PARAMS["Bull Trap"], "earnings", "exit_before")
        df["evt_bars_to_next"] = np.nan
        df.loc[df.index[t], "evt_bars_to_next"] = 3
        capped = run_backtest("TEST", df, "Bull Trap", HZ, exit_model="v2", scale_out=True)
    assert len(free.trades) == 1 and free.trades[0].direction == "bearish"
    assert len(capped.trades) == 1 and capped.trades[0].holding_days <= 2
