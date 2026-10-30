"""V191-9: replay admission builds the band from the as-of window only."""
import dataclasses

import pytest

from swingbot import config
from swingbot.core.backtesting import backtest_scenarios as bs
from swingbot.core.market import atr_band, levels
from swingbot.core.scanning.gating import scenario_gate_inputs
from swingbot.scan_params import ScanParams
from tests.market.test_atr_band import _frame

HORIZON = {"bars": 60, "label": "4w", "sr_target_min_pct": 8.0, "max_risk_pct": 3.0}


@pytest.fixture
def spy(monkeypatch):
    seen = []
    real = levels.build_scenarios

    def _spy(*args, **kwargs):
        seen.append(kwargs.get("band"))
        return real(*args, **kwargs)

    monkeypatch.setattr(bs.levels, "build_scenarios", _spy)
    monkeypatch.setattr(bs, "levels_asof", lambda *a, **k: (
        [levels.Level(99.0, ["Rolling S/R"])], [levels.Level(108.0, ["Rolling S/R"])]))
    return seen


def _params(k):
    # admission pinned (legacy-gate values) so a config default never decides the test
    return dataclasses.replace(ScanParams.from_config(), confluence_atr_stop_floor=k,
                               min_reward_pct=3.0, min_stop_distance_pct=2.0,
                               max_stop_loss_pct=7.0, min_risk_reward_ratio=1.5)


def test_gate_inputs_carry_the_floor():
    assert scenario_gate_inputs(_params(1.0), HORIZON)["atr_stop_floor"] == 1.0
    assert scenario_gate_inputs(_params(0.0), HORIZON)["atr_stop_floor"] == 0.0


def test_floor_off_passes_no_band(spy):
    bs.scenarios_at("XYZ", _frame(n=80), 59, "4w", _params(0.0), {})
    assert spy == [None]


def test_floor_on_reads_the_window_through_bar_i_only(spy):
    df = _frame(n=80)
    bs.scenarios_at("XYZ", df, 59, "4w", _params(1.0), {})
    df.iloc[60, df.columns.get_loc("High")] = 500.0         # the bar after the creating bar
    bs.scenarios_at("XYZ", df, 59, "4w", _params(1.0), {})
    bs.scenarios_at("XYZ", df.iloc[:60], 59, "4w", _params(1.0), {})
    assert spy[0] == spy[1] == spy[2] == atr_band.AtrBand(1.0, 4.0)
    assert spy[0].atr_pct == pytest.approx(4.0)


def test_floor_on_admits_the_one_percent_stop_the_legacy_gates_refuse(spy):
    off = bs.scenarios_at("XYZ", _frame(n=80), 59, "4w", _params(0.0), {})[-1]
    on = bs.scenarios_at("XYZ", _frame(n=80), 59, "4w", _params(1.0), {})[-1]
    assert [s.direction for s in off] == []
    assert [s.direction for s in on] == ["bullish"]


def test_legacy_gates_take_the_floor_from_config(monkeypatch):
    monkeypatch.setattr(config, "CONFLUENCE_ATR_STOP_FLOOR", 1.0)
    params, legacy = bs._replay_params(None, bs.CONFLUENCE_GATES)
    assert legacy and params.confluence_atr_stop_floor == 1.0
    assert params.min_stop_distance_pct == 2.0                # the legacy floor, bypassed by the band
