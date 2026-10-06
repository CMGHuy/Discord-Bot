"""v125: replay snapshots carry plan provenance from the PLANNED entry, never the fill."""
import numpy as np
import pandas as pd
import pytest

import swingbot.core.backtesting.backtest as bt
from swingbot import config
from swingbot.core.edge.context import entry_context, plan_provenance
from tests.conftest import make_ohlcv

ALL_SITES = [{"exit_model": "v1", "frictions": False}, {"exit_model": "v1", "frictions": True},
             {"exit_model": "v2", "scale_out": True}]


def _df(spread_pct):
    closes = np.full(120, 100.0)
    closes[81:] = 104.0
    return make_ohlcv(closes, spread_pct=spread_pct)


def _forced(monkeypatch, df, bar, **kwargs):
    bull = pd.Series(False, index=df.index)
    bear = pd.Series(False, index=df.index)
    bull.iloc[bar] = True
    monkeypatch.setattr(bt, "_vectorized_entries", lambda *args, **kw: (bull, bear))
    return bt.run_backtest("TEST", df, "EMA Crossover", "2w", **kwargs)


def _spy(monkeypatch):
    seen = []

    def spy(*args, **kwargs):
        seen.append(kwargs.get("entry"))
        return entry_context(*args, **kwargs)

    monkeypatch.setattr(bt, "entry_context", spy)
    return seen


@pytest.fixture(autouse=True)
def cap(monkeypatch):
    monkeypatch.setattr(config, "MAX_RISK_REWARD_RATIO", 2.5)


@pytest.mark.parametrize("kwargs", ALL_SITES)
def test_every_replay_site_passes_the_planned_entry(monkeypatch, kwargs):
    df = _df(1.0)
    seen = _spy(monkeypatch)
    trade = _forced(monkeypatch, df, 80, **kwargs).trades[0]
    assert seen == [100.0]                                       # Close[80], the planned entry
    # 1% spread: ATR ~1, stop 2 ATR (98), nearest ladder rung paying 1.5R is 103 -- a real rung
    assert (trade.take_profit, trade.context["target_capped"], trade.context["stop_clamped"]) == \
        (103.0, False, False)


@pytest.mark.parametrize("kwargs", ALL_SITES)
def test_a_target_on_the_cap_is_flagged_at_every_site(monkeypatch, kwargs):
    # 6% spread: ATR ~6, stop bounded to 2% (98), first ladder rung 106 > cap 105 -> synthetic 105
    trade = _forced(monkeypatch, _df(6.0), 80, **kwargs).trades[0]
    assert (trade.stop_loss, trade.take_profit) == (98.0, 105.0)
    assert trade.context["target_capped"] is True


def test_the_slipped_fill_would_have_hidden_the_cap(monkeypatch):
    trade = _forced(monkeypatch, _df(6.0), 80, exit_model="v1", frictions=True).trades[0]
    assert trade.entry != 100.0                                  # the fill slipped
    assert trade.context["target_capped"] is True                # from the trigger
    assert plan_provenance(trade.entry, trade.stop_loss, trade.take_profit, 2.5)["target_capped"] is False
