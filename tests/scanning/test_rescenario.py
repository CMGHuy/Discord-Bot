"""v171 D5: the per-horizon scenario seam and rescenario at a re-quoted price."""
import dataclasses

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.market import levels
from swingbot.core.edge import gates as gates_mod
from swingbot.core.scanning import analyze
from tests.scanning.test_engine_v2_plans import _structured_df

HF = {"min_reward_pct": 0.5, "max_stop_loss_pct": 50.0, "min_stop_distance_pct": 0.0,
      "min_risk_reward_ratio": 0.01, "mtf_adjacent_gate": False,
      "confluence_deviation_pct": 1.0}


@pytest.fixture
def loose(monkeypatch):
    monkeypatch.setitem(analyze.HORIZONS["4w"], "sr_target_min_pct", 1.0)


def _items(df):
    stats = analyze._scan_one("T0", df, ["4w"], None, None, 0, 0, hard_filters=dict(HF))
    assert stats["items"], "the structured frame must build a 4w scenario"
    return stats["items"]


def test_horizon_scenarios_matches_the_inline_calls(loose):
    df = _structured_df()
    h, price = analyze.HORIZONS["4w"], float(df["Close"].iloc[-1])
    build = analyze._horizon_scenarios(df, h, price, None, dict(HF))
    cands = levels.collect_candidate_levels(df, h, price, trendline_candidates=None)
    sup, res = levels.build_level_map(df, h, price, candidates=cands)
    oracle = levels.build_scenarios(
        price, sup, res, max(HF["min_reward_pct"], h["sr_target_min_pct"] * 0.15),
        atr_floor=levels.atr_floor_pct(df, price, h), min_stop_distance_pct=0.0,
        max_stop_distance_pct=max(HF["max_stop_loss_pct"], h.get("max_risk_pct", 50.0)),
        min_risk_reward=0.01, block_bullish=analyze.veto_bullish_for(df))
    assert [(s.direction, s.entry, s.stop_loss, s.take_profit) for s in build.scenarios] == \
           [(s.direction, s.entry, s.stop_loss, s.take_profit) for s in oracle]
    assert [lv.price for lv in build.supports] == [lv.price for lv in sup]


def test_default_hard_filters_reads_config(monkeypatch):
    monkeypatch.setattr(config, "MIN_REWARD_PCT", 4.5)
    assert analyze._default_hard_filters()["min_reward_pct"] == 4.5
    assert set(analyze._default_hard_filters()) == set(HF)


def test_default_hard_filters_keeps_a_given_snapshot(monkeypatch):
    monkeypatch.setattr(config, "MIN_REWARD_PCT", 4.5)
    given = dict(HF)
    assert analyze._default_hard_filters(given) is given
    assert analyze._default_hard_filters({})["min_reward_pct"] == 4.5


def test_scan_items_carry_scan_price_candidates_and_filters(loose):
    df = _structured_df()
    item = _items(df)[0]
    assert item.scan_price == pytest.approx(float(df["Close"].iloc[-1]))
    assert item.trendline_candidates is not None
    assert item.hard_filters == HF


def test_rescenario_at_the_scan_price_reproduces_the_scenario(loose):
    df = _structured_df()
    item = next(i for i in _items(df) if i.level_map is not None)
    again = analyze.rescenario(item, df, item.scan_price)
    assert again is not None
    assert (again.direction, again.entry, again.stop_loss, again.take_profit) == (
        item.plan.direction, item.plan.entry, item.plan.stop_loss, item.plan.take_profit)


def test_rescenario_rebuilds_at_the_new_price_from_the_stored_inputs(loose, monkeypatch):
    df = _structured_df()
    item = _items(df)[0]
    seen = {}
    real_collect, real_build = levels.collect_candidate_levels, levels.build_scenarios

    def collect(df_, h, price, trendline_candidates=None):
        seen["collect"] = (price, trendline_candidates)
        return real_collect(df_, h, price, trendline_candidates=trendline_candidates)

    def build(price, *a, **k):
        seen["build_price"] = price
        return real_build(price, *a, **k)

    monkeypatch.setattr(levels, "collect_candidate_levels", collect)
    monkeypatch.setattr(levels, "build_scenarios", build)
    new = item.scan_price * 1.003
    out = analyze.rescenario(item, df, new)
    assert seen["collect"][0] == new and seen["collect"][1] is item.trendline_candidates
    assert seen["build_price"] == new
    if out is not None:
        assert out.entry == pytest.approx(new) and out.direction == item.plan.direction


def test_rescenario_updates_the_level_map_only_when_kept(loose, monkeypatch):
    df = _structured_df()
    item = _items(df)[0]
    before = item.level_map
    other = "bearish" if item.plan.direction == "bullish" else "bullish"
    fake = analyze.HorizonBuild(None, ["S"], ["R"],
                                [dataclasses.replace(item.plan, direction=other)])
    monkeypatch.setattr(analyze, "_horizon_scenarios", lambda *a, **k: fake)
    monkeypatch.setattr(gates_mod, "filter_headroom", lambda s, sup, res: (list(s), []))
    assert analyze.rescenario(item, df, item.scan_price) is None
    assert item.level_map is before
    same = analyze.HorizonBuild(None, ["S"], ["R"], [item.plan])
    monkeypatch.setattr(analyze, "_horizon_scenarios", lambda *a, **k: same)
    assert analyze.rescenario(item, df, item.scan_price) is item.plan
    assert item.level_map == (["S"], ["R"])


def test_rescenario_reruns_the_headroom_filter(loose, monkeypatch):
    df = _structured_df()
    item = _items(df)[0]
    monkeypatch.setattr(gates_mod, "filter_headroom", lambda s, sup, res: ([], list(s)))
    assert analyze.rescenario(item, df, item.scan_price) is None


def test_rescenario_without_a_frame_or_a_price_is_none(loose):
    df = _structured_df()
    item = _items(df)[0]
    assert analyze.rescenario(item, None, 100.0) is None
    assert analyze.rescenario(item, df, 0.0) is None
    assert analyze.rescenario(item, df, None) is None


def test_rescenario_reads_only_the_scan_frame(loose):
    """NO-LOOKAHEAD: the frame is the scan's, truncated at its last bar; the
    rebuild never appends, splices or mutates a bar."""
    full = _structured_df()
    extra = full.iloc[[-1]].copy()
    extra.index = [full.index[-1] + pd.offsets.BDay(1)]
    full = pd.concat([full, extra * 1.05])
    trunc = full.iloc[:-1].copy()
    snapshot = trunc.copy()
    item = _items(trunc)[0]
    a = analyze.rescenario(item, trunc, item.scan_price * 1.002)
    b = analyze.rescenario(item, full.iloc[:-1], item.scan_price * 1.002)
    assert trunc.equals(snapshot)
    assert (a is None) == (b is None)
    if a is not None:
        assert (a.entry, a.stop_loss, a.take_profit) == (b.entry, b.stop_loss, b.take_profit)
