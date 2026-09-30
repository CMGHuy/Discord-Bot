"""v113 §1-§2: the 1w horizon ships masked for every strategy; `cells` admits exact pairs."""
import pandas as pd
import pytest

from swingbot.core.market import entry_filters as ef
from swingbot.core.market import mtf
from swingbot.core.market import strategy_types as st
from tests.horizon_iteration import iterations, offenders

LEGACY = ("2w", "4w", "2m", "3m", "4m", "5m", "6m", "7m", "8m", "9m")


def test_1w_values_are_the_spec_table():
    assert st.HORIZONS["1w"] == {
        "label": "3-7 day swing", "ema_fast": 5, "ema_slow": 8, "vwap_window": 5,
        "fib_lookback": 10, "sr_lookback": 5, "atr_stop_multiple": 1.5,
        "max_risk_pct": 2.0, "sr_stop_pct": 2.0, "sr_target_min_pct": 2.0,
        "sr_target_max_pct": 5.0, "max_holding_days": 7, "rs_window": 10,
        "min_reward_pct": 2.0,
    }
    assert st.MIN_BARS["1w"] == 20


def test_1w_is_first_and_the_legacy_order_is_unchanged():
    assert list(st.HORIZONS)[0] == "1w"
    assert st.LEGACY_HORIZONS == LEGACY
    assert st.MASKED_BY_DEFAULT_HORIZONS == ("1w",)
    assert all("min_reward_pct" not in st.HORIZONS[hk] for hk in LEGACY)


def test_mtf_ladder_puts_1w_below_2w_and_leaves_the_rest_alone():
    assert mtf.adjacent_horizon("1w") == "2w"
    assert mtf.adjacent_horizon("2w") == "4w"
    assert mtf.adjacent_horizon("9m") is None


def test_every_registered_strategy_is_masked_on_1w_by_default():
    for strategy in ef.ENTRY_FUNCS:
        for direction in ("bullish", "bearish"):
            assert not st.admits(strategy, direction, "1w"), (strategy, direction)


def _pre_v113_allowed(strategy, direction, horizon_key):
    """Verbatim copy of the nested rule entries_for carried before v113."""
    gates = st.STRATEGY_GATES.get(strategy)
    if not gates:
        return True
    horizons = gates.get("horizons")
    by_direction = gates.get("horizons_by_direction") or {}
    directions = gates.get("directions")
    if directions is not None and direction not in directions:
        return False
    permitted = by_direction.get(direction, horizons)
    return permitted is None or horizon_key in permitted


def test_admits_equals_the_pre_v113_rule_on_every_legacy_pair():
    for strategy in ef.ENTRY_FUNCS:
        for direction in ("bullish", "bearish"):
            for horizon in LEGACY:
                assert st.admits(strategy, direction, horizon) == _pre_v113_allowed(
                    strategy, direction, horizon), (strategy, direction, horizon)


def test_a_cell_admits_exactly_one_pair(monkeypatch):
    monkeypatch.setitem(st.STRATEGY_GATES, "MACD", {
        "directions": ("bullish",), "horizons": ("3m",), "cells": {("bearish", "1w")}})
    assert st.admits("MACD", "bearish", "1w")
    assert not st.admits("MACD", "bullish", "1w")
    assert not st.admits("MACD", "bearish", "3m")
    assert st.admits("MACD", "bullish", "3m")
    assert not st.admits("MACD", "bullish", "4m")


def test_a_cell_on_a_legacy_horizon_adds_to_the_axes(monkeypatch):
    monkeypatch.setitem(st.STRATEGY_GATES, "VWAP", {
        "directions": ("bullish",), "horizons": ("4w",), "cells": {("bullish", "2w")}})
    assert st.admits("VWAP", "bullish", "2w") and st.admits("VWAP", "bullish", "4w")
    assert not st.admits("VWAP", "bearish", "2w") and not st.admits("VWAP", "bullish", "2m")


def test_cells_work_on_a_fully_masked_strategy(monkeypatch):
    monkeypatch.setitem(st.STRATEGY_GATES, "Probe", {"directions": (), "cells": {("bearish", "1w")}})
    assert st.admits("Probe", "bearish", "1w")
    assert not st.admits("Probe", "bearish", "2w") and not st.admits("Probe", "bullish", "1w")


def test_live_horizons_is_legacy_until_a_cell_admits_1w(monkeypatch):
    assert st.live_horizons() == LEGACY
    monkeypatch.setitem(st.STRATEGY_GATES, "Probe", {"directions": (), "cells": {("bearish", "1w")}})
    assert st.live_horizons() == ("1w", *LEGACY)


def test_entries_for_masks_1w_and_honours_a_cell(market_df):
    raw_bull, raw_bear = ef.ENTRY_FUNCS["RSI Divergence"](market_df, "1w", None)
    bull, bear = ef.entries_for("RSI Divergence", market_df, "1w")
    assert not bull.any() and not bear.any()
    with ef.gate_override("RSI Divergence", {"cells": {("bearish", "1w")}}):
        bull, bear = ef.entries_for("RSI Divergence", market_df, "1w")
    assert not bull.any()
    pd.testing.assert_series_equal(bear, raw_bear, check_names=False)
    assert raw_bull.any() or raw_bear.any(), "fixture must fire at least once on 1w"


def test_iteration_finder_catches_every_form(tmp_path):
    source = "\n".join([
        "a = [k for k in HORIZONS]",
        "for k, h in HORIZONS.items(): pass",
        "b = list(HORIZONS.keys())",
        "c = {'all', *HORIZONS.keys()}",
        "d = len(HORIZONS)",
        "e = HORIZONS['2w']",
        "f = 'x' in HORIZONS",
        "g = {k: v for k, v in other.items() if k in HORIZONS}",
    ])
    path = tmp_path / "probe.py"
    path.write_text(source, encoding="utf-8")
    assert [n for n, _ in iterations(path)] == [1, 2, 3, 4, 5]
