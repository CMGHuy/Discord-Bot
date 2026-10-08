"""v128: /strategycharts is display, not signal -- it keeps every unfilled FVG whatever the mode."""
from swingbot import config
from swingbot.core.charts import trade_chart
from swingbot.core.market import levels
from swingbot.core.market.strategy_types import HORIZONS
from tests.market.fvg_frames import witness_frame


def test_strategy_charts_keep_every_gap_when_the_mode_is_off(monkeypatch, tmp_path):
    seen = {}

    def fake_collect(df, h, current_price, trendline_candidates=None, params=None):
        seen["params"] = params
        return []

    monkeypatch.setattr(config, "FVG_LEVELS_MODE", "off")
    monkeypatch.setattr(levels, "collect_candidate_levels", fake_collect)
    result = trade_chart.generate_all_strategy_charts("TEST", witness_frame(), "bullish", "3m",
                                                      str(tmp_path), HORIZONS["3m"])
    assert seen["params"].fvg_levels_mode == "all"
    assert set(result) == set(levels.ALL_STRATEGY_FAMILIES)


def test_display_params_override_only_the_fvg_mode(monkeypatch):
    monkeypatch.setattr(config, "FVG_LEVELS_MODE", "off")
    params = trade_chart._display_params()
    assert params.fvg_levels_mode == "all"
    assert params.avwap_levels_enabled == config.AVWAP_LEVELS_ENABLED
